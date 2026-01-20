# scrap_dj/applications/sources/models.py

from django.db import models  # Modelos base de Django
from .constants import SourceKey, SourceType  # Enum/choices oficiales del proyecto


class Source(models.Model):
    # Identificador interno fijo (allowlist controlada por el proyecto)
    key = models.CharField(
        max_length=32,  # Tamaño suficiente para keys cortas
        choices=SourceKey.choices,  # Solo keys permitidas
        unique=True,  # Una fila por source_key
    )

    # Nombre visible (UI / admin)
    label = models.CharField(
        max_length=100,  # Texto corto para UI
    )

    # Tipo de extracción (API / endpoint / HTML)
    type = models.CharField(
        max_length=16,  # 'endpoint' es lo más largo aquí
        choices=SourceType.choices,  # Solo tipos permitidos
    )

    # Config fija (NO viene del usuario)
    base_url = models.URLField(
        max_length=300,  # URLs razonables
    )

    # Path relativo dentro del dominio base (ej: '/posts', '/api/users', '/')
    path = models.CharField(
        max_length=200,  # Rutas cortas
        default="/",  # Por defecto home
    )

    # Switch para deshabilitar una fuente sin borrar registros
    enabled = models.BooleanField(
        default=True,  # Activa por defecto
    )

    # Auditoría simple
    created_at = models.DateTimeField(
        auto_now_add=True,  # Fecha de creación
    )
    updated_at = models.DateTimeField(
        auto_now=True,  # Fecha de última actualización
    )

    class Meta:
        # Orden estable al listar
        ordering = ["key"]  # Orden alfabético por key

    def __str__(self) -> str:
        # Representación útil en admin/shell
        return f"{self.key} ({self.type})"  # Ej: posts (api)






