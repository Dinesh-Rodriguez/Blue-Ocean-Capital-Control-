from django.urls import re_path
from .consumers import TenantConsumer

websocket_urlpatterns = [re_path(r"ws/updates/$", TenantConsumer.as_asgi())]
