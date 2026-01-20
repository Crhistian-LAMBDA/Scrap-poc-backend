# scrap_dj/applications/sources/constants.py

from django.db import models  # Choices tipados para modelos Django


class SourceKey(models.TextChoices):
    # Fuente 1: Posts (JSONPlaceholder)
    POSTS = "posts", "posts"
    # Fuente 2: Users (ReqRes)
    USERS = "users", "users"
    # Fuente 3: Bitcoin (CoinDesk)
    BITCOIN = "bitcoin", "bitcoin"
    # Fuente 4: Quotes (Quotes to Scrape)
    QUOTES = "quotes", "quotes"
    # Fuente 5: Books (Books to Scrape)
    BOOKS = "books", "books"


class SourceType(models.TextChoices):
    # Tipos soportados por el POC (según documentación)
    API = "api", "API"
    ENDPOINT = "endpoint", "endpoint"
    HTML = "html", "HTML"


# Config inicial (predefinida) para sembrar la BD después.
# Nota: esto NO acepta URLs del usuario; es allowlist controlada por el proyecto.
DEFAULT_SOURCES = [
    {
        "key": SourceKey.POSTS,
        "label": "Posts",
        "type": SourceType.API,
        "base_url": "https://jsonplaceholder.typicode.com",
        "path": "/posts",
    },
    {
        "key": SourceKey.USERS,
        "label": "Users",
        "type": SourceType.API,
        "base_url": "https://reqres.in",
        "path": "/api/users",
    },
    {
        "key": SourceKey.BITCOIN,
        "label": "Bitcoin",
        "type": SourceType.API,
        "base_url": "https://api.coindesk.com",
        "path": "/v1/bpi/currentprice.json",
    },
    {
        "key": SourceKey.QUOTES,
        "label": "Quotes",
        "type": SourceType.HTML,
        "base_url": "https://quotes.toscrape.com",
        "path": "/",
    },
    {
        "key": SourceKey.BOOKS,
        "label": "Books",
        "type": SourceType.HTML,
        "base_url": "https://books.toscrape.com",
        "path": "/",
    },
]