import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import projects.routing
import social_proof.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            projects.routing.websocket_urlpatterns +
            social_proof.routing.websocket_urlpatterns
        )
    ),
})
