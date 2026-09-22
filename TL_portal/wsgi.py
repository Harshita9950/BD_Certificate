"""
WSGI config for TL_portal.
Set DJANGO_SETTINGS_MODULE to 'TL_portal.settings' in the production
server environment (gunicorn, uWSGI, etc.).
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TL_portal.settings')

application = get_wsgi_application()
