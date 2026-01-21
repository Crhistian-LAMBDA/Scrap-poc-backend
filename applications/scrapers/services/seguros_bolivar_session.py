"""Servicio de scraping autenticado (JSF) para Seguros Bolívar.

Regla de negocio CRÍTICA (alcance):
- Este proyecto es exclusivamente de consulta/validación.
- NO debe ejecutar desistimientos ni acciones irreversibles.
- En especial, NO debe interactuar con flujos del contrato Cto.11052.

Este módulo implementa:
- Autenticación server-side (según el código entregado por el usuario)
- O uso de sesión existente vía header Cookie pegado (opcional)

Nota: No se persiste ninguna cookie; solo se usa en memoria.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from http.cookies import SimpleCookie
import html as html_stdlib
import re
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup


@dataclass
class BolivarResult:
    radicado: str
    ok: bool
    estado_raw: str | None
    estado_normalizado: str | None
    asegurado: str | None
    consulted_at: str
    error: str | None


class SegurosBolivarSession:
    """Sesión autenticada para consultas (READ-ONLY).

    Soporta 2 modos:
    - cookie_header: header Cookie pegado (sesión ya autenticada)
    - use_server_auth=True: login con credenciales del servidor (env vars)
    """

    def __init__(
        self,
        cookie_header: str | None = None,
        *,
        use_server_auth: bool = False,
    ):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

        self.cookie_header = (cookie_header or "").strip()
        self.use_server_auth = bool(use_server_auth)

        self.user_id = os.getenv("LIBERTADOR_USER")
        self.password = os.getenv("LIBERTADOR_PASS")
        self.poliza = os.getenv("LIBERTADOR_POLIZA")
        self.view_state_value: str | None = None

        fecha_actual = datetime.now()
        self.primer_dia_mes = fecha_actual.replace(day=1).strftime("%d/%m/%Y")

        if self.cookie_header:
            self._apply_cookie_header(self.cookie_header)

        self._is_authenticated = False

        # URL de consulta (solo lectura)
        self.index_url = (
            "https://www.segurosbolivar.com/indemnizaciones-web/pages/index.xhtml"
        )

    # --- Helpers de cookies ---


    def _apply_cookie_header(self, cookie_header: str) -> None:
        value = (cookie_header or "").strip()
        if not value:
            return
        if value.lower().startswith("cookie:"):
            value = value.split(":", 1)[1].strip()

        # Mucha gente pega cookies en varias líneas; unificamos a formato estándar.
        # Acepta:
        #   a=b\nJSESSIONID=...\nX=Y
        # o
        #   a=b; JSESSIONID=...; X=Y
        value = value.replace("\r", "")
        value = "; ".join([p.strip() for p in re.split(r"[\n;]+", value) if p.strip()])

        parsed = SimpleCookie()
        parsed.load(value)
        for key, morsel in parsed.items():
            self.session.cookies.set(key, morsel.value)

    def ensure_authenticated(self) -> None:
        if self._is_authenticated:
            return

        if self.cookie_header:
            # Sesión ya autenticada; el ViewState se obtiene en el primer GET real.
            self._is_authenticated = True
            return

        if not self.use_server_auth:
            raise ValueError(
                "No hay cookie de sesión. Envía 'cookie' o activa 'use_server_auth'."
            )

        if not self.user_id or not self.password:
            raise ValueError(
                "Faltan variables de entorno LIBERTADOR_USER/LIBERTADOR_PASS para autenticar."
            )

        self.authenticate()
        self._is_authenticated = True

    # --- Helpers de JSF (ViewState / markup) ---

    def _refresh_view_state_from_html(self, html_text: str) -> None:
        text = html_text or ""
        lower = text.lower()

        # JSF partial-response puede traer ViewState en XML
        if "<partial-response" in lower:
            try:
                root = ET.fromstring(text)
                for elem in root.iter():
                    if not (isinstance(elem.tag, str) and elem.tag.lower().endswith("update")):
                        continue
                    elem_id = (elem.attrib.get("id") or "").lower()
                    if "javax.faces.viewstate" in elem_id:
                        value = ("".join(elem.itertext()) or "").strip()
                        if value:
                            self.view_state_value = value
                            return
            except Exception:
                # Si falla el XML, caemos al parseo HTML tradicional.
                pass

        soup = BeautifulSoup(text, "html.parser")
        view_state_input = soup.find("input", {"name": "javax.faces.ViewState"})
        if view_state_input and view_state_input.get("value"):
            self.view_state_value = view_state_input.get("value")

    def _unwrap_jsf_partial_response(self, response_text: str) -> str:
        """Si la respuesta es JSF partial-response, extrae el HTML dentro de <update>.

        JSF suele devolver XML con CDATA y/o HTML escapado (entities).
        Para parseo de DOM, necesitamos materializar ese HTML.
        """

        text = response_text or ""
        lower = text.lower()
        if "<partial-response" not in lower:
            return text

        try:
            root = ET.fromstring(text)
        except Exception:
            return text

        chunks: list[str] = []
        for elem in root.iter():
            if not (isinstance(elem.tag, str) and elem.tag.lower().endswith("update")):
                continue

            chunk = ("".join(elem.itertext()) or "").strip()
            if not chunk:
                continue

            # En algunos casos viene escapado: &lt;table&gt;...
            chunk = html_stdlib.unescape(chunk)
            chunks.append(chunk)

        return "\n".join(chunks) if chunks else text

    def _get_index(self) -> str:
        resp = self.session.get(self.index_url, timeout=30)
        resp.raise_for_status()
        self._refresh_view_state_from_html(resp.text)
        return resp.text

    # --- Helpers de forms (selección FormIndex / campo busqueda / botón submit) ---

    def _find_search_form(self, html_text: str):
        soup = BeautifulSoup(html_text, "html.parser")

        forms = soup.find_all("form")
        if not forms:
            return None

        # 1) Preferir el formulario que contenga el input/textarea de búsqueda.
        busqueda_forms = []
        for form in forms:
            busqueda_input = form.find(
                lambda tag: tag.name in {"input", "textarea"}
                and (
                    (tag.get("name") or "").lower().endswith("busqueda")
                    or (tag.get("id") or "").lower().endswith("busqueda")
                )
            )
            if busqueda_input is not None:
                busqueda_forms.append(form)

        if busqueda_forms:
            # Si existe FormIndex, es el flujo real del botón BUSCAR.
            # En esta pantalla hay múltiples <form> con ViewState (menu, diálogos, etc.).
            # Postear al form equivocado hace que la búsqueda no se ejecute.
            for form in busqueda_forms:
                fid = (form.get("id") or "").strip()
                fname = (form.get("name") or "").strip()
                if fid == "FormIndex" or fname == "FormIndex":
                    return form

            # Si no, preferir el que postea a index.xhtml.
            for form in busqueda_forms:
                action = (form.get("action") or "").lower()
                if action.endswith("/pages/index.xhtml") or action.endswith("index.xhtml"):
                    return form

            return busqueda_forms[0]

        # 2) Si no hay busqueda, preferimos el primer form con ViewState.
        for form in forms:
            if form.find("input", {"name": "javax.faces.ViewState"}):
                return form

        # 3) Fallback: primer form
        return forms[0]

    def _extract_estado_from_html(self, html_text: str) -> str:

        # --- Parseo HTML: primero datosSolicitud, luego heurísticas ---
        # Detectar y desempaquetar respuestas JSF partial-response
        candidate_markup = self._unwrap_jsf_partial_response(html_text)
        soup = BeautifulSoup(candidate_markup, "html.parser")

        full_text = " ".join(soup.stripped_strings)
        full_text_lower = full_text.lower()

        # Nota: NO podemos usar una heurística global de "sin resultados" antes
        # de extraer el estado. Esta pantalla contiene múltiples tablas con el
        # texto "No se encontraron resultados." (p. ej. Motivos de Objeciones)
        # incluso cuando el radicado SÍ existe y datosSolicitud viene poblado.

        # 1) Regla específica confirmada por HTML real:
        #    table#datosSolicitud contiene un label "Estado Siniestro:" y el
        #    label inmediatamente siguiente es el valor.
        # En JSF los IDs suelen venir con prefijos (ej: form:datosSolicitud).
        datos_tables = []
        for table in soup.find_all("table"):
            table_id = (table.get("id") or "").strip()
            if table_id.lower().endswith("datossolicitud"):
                datos_tables.append(table)

        for datos in datos_tables:
            # Camino robusto: buscar por contención (espacios/saltos/colon).
            label_estado = datos.find(
                "label", string=re.compile(r"estado\s*siniestro", flags=re.I)
            )
            if label_estado:
                next_label = label_estado.find_next("label")
                if next_label:
                    val = next_label.get_text(" ", strip=True)
                    if val:
                        return self._normalize_estado(val)

            labels = datos.find_all("label")
            for i, lab in enumerate(labels):
                key = lab.get_text(" ", strip=True)
                if not key:
                    continue
                if "estado siniestro" in key.lower():
                    if i + 1 < len(labels):
                        val = labels[i + 1].get_text(" ", strip=True)
                        if val:
                            return self._normalize_estado(val)

        # Heurísticas de "sin resultados" (solo si NO aparece datosSolicitud)
        if any(
            marker in full_text_lower
            for marker in (
                "no se encontraron",
                "sin resultados",
                "no existen registros",
                "no existe",
                "no encontrado",
            )
        ):
            return "NO ENCONTRADO"

        # 2) Fallback: Buscar un bloque/tabla de "informacion"
        candidates = []
        for table in soup.find_all("table"):
            table_id = (table.get("id") or "").lower()
            table_class = " ".join(table.get("class") or []).lower()
            if "informacion" in table_id or "informacion" in table_class:
                candidates.append(table)

        # También aceptar contenedores con id "informacion" aunque no sea table
        info_container = soup.find(id=re.compile("informacion", re.I))
        if info_container and info_container not in candidates:
            candidates.append(info_container)

        def extract_from_table_like(node) -> str | None:
            # Buscar fila con etiqueta "Estado"
            for tr in node.find_all("tr"):
                cells = tr.find_all(["th", "td"])
                if len(cells) < 2:
                    continue
                key = cells[0].get_text(" ", strip=True)
                val = cells[1].get_text(" ", strip=True)
                if not key or not val:
                    continue
                if "estado" in key.lower():
                    return val
            return None

        for node in candidates:
            val = extract_from_table_like(node)
            if val:
                return self._normalize_estado(val)

        # Si no hay tabla, intentar encontrar un label "Estado" cercano
        estado_label = None
        for tag in soup.find_all(text=re.compile(r"\bestado\b", re.I)):
            t = (tag or "").strip()
            if not t:
                continue
            if re.search(r"\bestado\b", t, flags=re.I):
                estado_label = tag
                break

        if estado_label:
            parent = estado_label.parent
            # Buscar texto "hermano" próximo
            if parent:
                next_text = parent.find_next(string=True)
                if next_text:
                    candidate = str(next_text).strip()
                    if candidate and candidate.lower() != str(estado_label).strip().lower():
                        return self._normalize_estado(candidate)

        # Último recurso: regex sobre todo el texto
        m = re.search(
            r"\b(desistid[oa]|reportad[oa]|sin\s+desistir|no\s+ha\s+pagado)\b",
            full_text_lower,
        )
        if m:
            return self._normalize_estado(m.group(0))

        # Si el HTML tiene contenido pero no logramos extraer estado,
        # devolvemos algo útil (texto literal reducido) en vez de NO ENCONTRADO.
        compact = re.sub(r"\s+", " ", full_text).strip()
        if compact:
            # Evitar respuestas gigantes
            return compact[:180]

        return "NO ENCONTRADO"

    def _extract_label_value_from_datos_solicitud(
        self, datos_table: BeautifulSoup, label_pattern: re.Pattern[str]
    ) -> str | None:
        label = datos_table.find("label", string=label_pattern)
        if not label:
            return None
        next_label = label.find_next("label")
        if not next_label:
            return None
        value = next_label.get_text(" ", strip=True)
        return value or None

    def _extract_info_from_html(self, html_text: str) -> tuple[str | None, str | None]:
        """Extrae (estado_raw, asegurado) desde la tabla datosSolicitud.

        Importante: esta extracción es estricta a datosSolicitud para evitar falsos
        positivos en otras tablas/diálogos de la pantalla.
        """

        candidate_markup = self._unwrap_jsf_partial_response(html_text)
        soup = BeautifulSoup(candidate_markup, "html.parser")

        datos_table = None
        for table in soup.find_all("table"):
            table_id = (table.get("id") or "").strip().lower()
            if table_id.endswith("datossolicitud"):
                datos_table = table
                break

        if not datos_table:
            return None, None

        estado_raw = self._extract_label_value_from_datos_solicitud(
            datos_table, re.compile(r"estado\s*siniestro", flags=re.I)
        )
        asegurado = self._extract_label_value_from_datos_solicitud(
            datos_table, re.compile(r"\b(inquilino|asegurado)\b", flags=re.I)
        )

        return estado_raw, asegurado

    def get_info_for_radicado(self, radicado: str) -> tuple[str, str, str | None]:
        """Consulta el portal por radicado y retorna (estado_raw, estado_normalizado, asegurado)."""

        solicitud = (radicado or "").strip()
        if not solicitud:
            return "NO ENCONTRADO", "NO ENCONTRADO", None

        self.ensure_authenticated()

        index_html = self._get_index()
        if not self.view_state_value:
            raise Exception("No se encontró javax.faces.ViewState en index.xhtml")

        form = self._find_search_form(index_html)
        if not form:
            raise Exception("No se encontró formulario de consulta en index.xhtml")

        action = form.get("action") or self.index_url
        post_url = urljoin(self.index_url, action)

        # Recolectar inputs ocultos del form
        payload: dict[str, str] = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue

            itype = (inp.get("type") or "").lower()
            value = inp.get("value") or ""

            if name == "javax.faces.ViewState":
                continue

            if itype == "hidden":
                payload[name] = value

        # Determinar el nombre real del campo "busqueda" dentro del form
        busqueda_name = None
        for inp in form.find_all(["input", "textarea"]):
            name = inp.get("name")
            _id = inp.get("id")
            haystack = f"{name or ''} {_id or ''}".lower()
            if "busqueda" in haystack:
                busqueda_name = name or _id
                break

        if not busqueda_name:
            busqueda_name = "busqueda"

        payload[busqueda_name] = solicitud
        payload["javax.faces.ViewState"] = self.view_state_value

        # Incluir el botón submit para disparar el submit esperado por JSF.
        submit_name = None
        candidates: list[tuple[str, str]] = []  # (name, text_value)
        for btn in form.find_all(["button", "input"]):
            btype = (btn.get("type") or "").lower()
            if btn.name == "input":
                if btype and btype not in {"submit", "image"}:
                    continue
            name = btn.get("name") or btn.get("id")
            if not name:
                continue

            text_value = btn.get("value") or btn.get_text(" ", strip=True) or ""
            candidates.append((name, text_value))

        for name, text_value in candidates:
            hay = f"{name} {text_value}".lower()
            if any(k in hay for k in ("buscar", "busca", "consulta", "consult", "search")):
                submit_name = name
                break

        if not submit_name:
            for name, _text_value in candidates:
                if re.fullmatch(r"j_idt\d+", name) or re.search(r"\bj_idt\d+\b", name):
                    submit_name = name
                    break

        if not submit_name and len(candidates) == 1:
            submit_name, _text_value = candidates[0]

        if submit_name:
            payload[submit_name] = submit_name

        resp = self.session.post(
            post_url,
            data=payload,
            headers={"Referer": self.index_url},
            timeout=30,
        )
        resp.raise_for_status()

        self._refresh_view_state_from_html(resp.text)

        estado_raw, asegurado = self._extract_info_from_html(resp.text)
        if not estado_raw:
            return "NO ENCONTRADO", "NO ENCONTRADO", asegurado

        return estado_raw, self._normalize_estado(estado_raw), asegurado

    def _normalize_estado(self, raw: str) -> str:
        text = (raw or "").strip()
        if not text:
            return "NO ENCONTRADO"

        lower = text.lower()
        # Normalización a los 3 estados clave
        if lower == "nuevo":
            return "SIN DESISTIR"
        if "desist" in lower:
            return "DESISTIDO"
        if "report" in lower:
            return "REPORTADO"
        if "sin desist" in lower or "no ha pagado" in lower or "sin pagar" in lower:
            return "SIN DESISTIR"

        # Si no es explícito, devolvemos el literal (en mayúsculas para consistencia)
        return re.sub(r"\s+", " ", text).strip().upper()

    def authenticate(self):
        """Autenticación server-side (código del usuario).

        Mantener como base; el resto de métodos de scraping/consulta se integran aparte.
        """

        url_post = "https://registro.segurosbolivar.com/nidp/idff/sso"
        params = {
            "id": "620",
            "sid": "0",
            "option": "credential",
            "target": "https://www.segurosbolivar.com/indemnizaciones-web/login.html",
        }

        data = {
            "Num_Documento": self.user_id,
            "Ecom_User_ID": self.user_id,
            "Ecom_Password": self.password,
            "form": "INGRESA",
        }

        self.session.post(url_post, params=params, data=data)

        r = self.session.get(
            "https://www.segurosbolivar.com/indemnizaciones-web/login.html",
            allow_redirects=False,
        )

        for _ in range(3):
            if r.status_code in (301, 302, 303, 307, 308):
                location = r.headers.get("Location")
                if not location:
                    break
                r = self.session.get(location, allow_redirects=False)

        self.session.post(
            "https://www.segurosbolivar.com/indemnizaciones-web/Ingreso",
            params={"nov-ss-ff-silent": "", "mastercdnff-indemnizacion-web3310": ""},
            data={
                "login": self.user_id,
                "rol": "WSINMOB01",
                "nov-ss-ff-Npst": "mastercdnff-indemnizacion-web3310",
            },
        )

        landing_response = self.session.get(
            "https://www.segurosbolivar.com/indemnizaciones-web/pages/index.xhtml",
            allow_redirects=False,
        )

        if landing_response.status_code in (301, 302, 303, 307, 308):
            final_url = landing_response.headers.get("Location")
            if not final_url:
                raise Exception("Redirect sin Location en landing.")
            final_response = self.session.get(final_url)
        else:
            final_response = landing_response

        soup = BeautifulSoup(final_response.text, "html.parser")
        view_state_input = soup.find("input", {"name": "javax.faces.ViewState"})

        if not view_state_input:
            raise Exception("No se encontró ViewState.")

        self.view_state_value = view_state_input.get("value")

    def get_status_for_radicado(self, radicado: str) -> str:
        """Consulta el portal JSF por radicado y retorna un estado textual.

        Implementación pendiente: requiere los métodos de consulta/parseo del portal.
        IMPORTANTE: este método debe ser READ-ONLY (no clicks de desistimiento).
        """

        _estado_raw, estado_normalizado, _asegurado = self.get_info_for_radicado(radicado)
        return estado_normalizado
