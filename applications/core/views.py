# n_scrap/scrap_dj/applications/core/views.py
# Endpoint mínimo para comprobar que DRF está instalado y funcionando.



from rest_framework.decorators import api_view # Decorador DRF para vistas simples
from rest_framework.response import Response # Respuesta DRF

@api_view(['GET']) # Solo permitimos GET para este health check
def health(request):
    # Respuesta mínima para confirmar que el backend responde y DRF está activo
    return Response({"status": "ok"})

@api_view(["POST"])
def scrape(request):
    source = request.data.get("source")
    query = request.data.get("query")

    items = [
        {"id": 1, "source": source, "title": f"{query} - producto 1", "price": 10.99},
        {"id": 2, "source": source, "title": f"{query} - producto 2", "price": 19.99},
    ]

    return Response({"source": source, "query": query, "items": items})