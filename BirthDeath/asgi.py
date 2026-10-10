"""
ASGI config for BirthDeath.
Prepared for future async support (Django Channels, etc.).
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'BirthDeath.settings')

application = get_asgi_application()
