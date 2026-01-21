# scrap_dj/applications/scrapers/services/api_posts.py

import requests  # Librería HTTP requerida por la HU
from requests import Response  # Tipado de respuesta HTTP
from requests.exceptions import RequestException, Timeout  # Errores comunes de requests


JSONPLACEHOLDER_POSTS_URL = "https://jsonplaceholder.typicode.com/posts"  # Fuente fija POC
DEFAULT_TIMEOUT_SECONDS = 10  # Timeout razonable para POC


class ScraperHttpError(Exception):
    # Error para representar respuestas HTTP no exitosas
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code  # Código HTTP recibido
        self.message = message  # Mensaje resumido
        super().__init__(f"HTTP {status_code}: {message}")  # Mensaje base


def fetch_posts(timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> list[dict]:
    # Ejecuta request a la API pública y retorna lista de dicts normalizados
    try:
        # Petición GET a fuente fija (no viene del usuario)
        res: Response = requests.get(JSONPLACEHOLDER_POSTS_URL, timeout=timeout_seconds)

        # Manejo explícito de status HTTP (criterio HU)
        if res.status_code != 200:
            raise ScraperHttpError(
                status_code=res.status_code,  # Guardar status real
                message="Respuesta inválida de la fuente",  # Mensaje controlado
            )

        # Parseo JSON (puede fallar si la fuente devuelve algo raro)
        data = res.json()

        # Validación mínima de estructura esperada
        if not isinstance(data, list):
            raise ValueError("La fuente devolvió un formato inesperado (no es lista).")

        # Normalización mínima: campos esperados por el POC
        items: list[dict] = []
        for row in data:
            # Cada item debe ser un dict; si no, se ignora
            if not isinstance(row, dict):
                continue

            # Construye el item con campos mínimos definidos por la HU
            items.append(
                {
                    "id": row.get("id"),  # ID externo
                    "userId": row.get("userId"),  # Relación con usuario
                    "title": row.get("title"),  # Título
                    "body": row.get("body"),  # Contenido
                }
            )

        return items

    except Timeout as exc:
        # Timeout: se maneja como error de conectividad
        raise TimeoutError("Timeout al conectar con la fuente.") from exc
    except RequestException as exc:
        # Errores de red, DNS, conexión, etc.
        raise ConnectionError("No se pudo conectar a la fuente.") from exc
    except ValueError as exc:
        # JSON inválido o formato inesperado
        raise ValueError("La fuente devolvió un formato inesperado.") from exc