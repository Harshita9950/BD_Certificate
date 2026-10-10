"""
WSGI config for BirthDeath.
Set DJANGO_SETTINGS_MODULE to 'BirthDeath.settings' in the production
server environment (gunicorn, uWSGI, etc.).
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'BirthDeath.settings')

application = get_wsgi_application()
