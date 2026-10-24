from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

@database_sync_to_async
def user_from_token(token):
    try:
        validated = JWTAuthentication().get_validated_token(token)
        return get_user_model().objects.get(id=validated["user_id"])
    except (InvalidToken, TokenError, KeyError, get_user_model().DoesNotExist, TypeError):
        return None

class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        scope["user"] = await user_from_token(query.get("token", [None])[0])
        return await self.app(scope, receive, send)
