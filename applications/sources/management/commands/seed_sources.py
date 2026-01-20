# scrap_dj/applications/sources/management/commands/seed_sources.py

from django.core.management.base import BaseCommand  # Base para comandos Django
from django.db import transaction  # Transacción para operaciones atómicas

from applications.sources.constants import DEFAULT_SOURCES  # Config oficial (allowlist)
from applications.sources.models import Source  # Modelo de fuentes en BD


class Command(BaseCommand):
    # Ayuda visible en `python manage.py help`
    help = "Crea/actualiza las fuentes predefinidas del POC (idempotente)."

    def handle(self, *args, **options):
        # Contadores para reporte final
        created_count = 0  # Nuevas fuentes creadas
        updated_count = 0  # Fuentes existentes actualizadas

        # Asegura que todas las operaciones se hagan juntas o ninguna
        with transaction.atomic():
            for item in DEFAULT_SOURCES:
                # Soporta TextChoices (tienen `.value`) o strings
                key_value = item["key"].value if hasattr(item["key"], "value") else str(item["key"])
                type_value = item["type"].value if hasattr(item["type"], "value") else str(item["type"])

                # update_or_create: si existe, actualiza; si no, crea
                obj, created = Source.objects.update_or_create(
                    key=key_value,  # Llave única por fuente
                    defaults={
                        "label": item["label"],  # Nombre visible
                        "type": type_value,  # Tipo (api/endpoint/html)
                        "base_url": item["base_url"],  # Dominio base fijo
                        "path": item.get("path", "/"),  # Ruta relativa
                        "enabled": True,  # Activa por defecto (POC)
                    },
                )

                # Actualiza contadores y escribe feedback
                if created:
                    created_count += 1  # Se creó una nueva fila
                    self.stdout.write(self.style.SUCCESS(f"CREATED: {obj.key} ({obj.type})"))
                else:
                    updated_count += 1  # Se actualizó una fila existente
                    self.stdout.write(self.style.WARNING(f"UPDATED: {obj.key} ({obj.type})"))

        # Resumen final del comando
        self.stdout.write(self.style.SUCCESS(f"Done. created={created_count}, updated={updated_count}"))

                        

