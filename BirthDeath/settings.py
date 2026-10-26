"""
BirthDeath/settings.py
========================
Municipal Birth & Death Certificate Management System — Master Settings
=======================================================================
Single settings file. All sensitive and environment-specific values
come from .env via python-dotenv.  No secrets are hard-coded.

CHANGE AUTHENTICATION ONCE — ENTIRE APPLICATION FOLLOWS IT.
  To switch or add an auth provider:
    1. Update AUTHENTICATION_BACKENDS below (or .env)
    2. Update REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] below
    3. Set CENTRAL_PORTAL_ENABLED + CENTRAL_PORTAL_* env vars
    → No individual view, API, model or template needs to change.
"""

from pathlib import Path
from dotenv import load_dotenv
import os

# ─── Base path & .env ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


# ─── Core ────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ['SECRET_KEY']
DEBUG       = os.getenv('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')]


# ─── Installed Applications ───────────────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'corsheaders',
    'django_filters',
]

LOCAL_APPS = [
    'core',           # Central auth/authorisation infrastructure
    'users',          # Custom User model, roles, permissions
    'geography',      # State, District, ULB, Zone, Ward master
    'bd_master',      # BD Master configuration layer
    'bd_registration', # Birth & Death registration
    'workflow_master',
    'fee_master',
    'payments',       # Payment orders and transactions (cash + Razorpay)
    'certificate_updation',  # Certificate correction/updation requests
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# ─── Middleware ───────────────────────────────────────────────────────────────
# ORDER MATTERS — do not rearrange without understanding the implications.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',                      # Before CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',       # Loads session
    'core.authentication.middleware.SessionValidationMiddleware', # Flushes bad sessions
    'core.authentication.middleware.ApplicationAccessMiddleware', # CP app-access gate
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',                  # CSRF — do NOT remove
    'django.contrib.auth.middleware.AuthenticationMiddleware',    # Sets request.user
    'core.authentication.middleware.TLPortalAuthMiddleware',      # Attaches auth_context (needs request.user)
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# ─── URLs / WSGI / ASGI ──────────────────────────────────────────────────────
ROOT_URLCONF    = 'BirthDeath.urls'
WSGI_APPLICATION = 'BirthDeath.wsgi.application'


# ─── Templates ───────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # Injects auth_user, auth_role, auth_permissions etc. into all templates
                'core.authentication.context_processors.auth_context',
            ],
        },
    },
]


# ─── Custom User Model ───────────────────────────────────────────────────────
AUTH_USER_MODEL = 'users.User'


# ─── Authentication Backends ─────────────────────────────────────────────────
# This list is the SINGLE control point for authentication providers.
# Adding a new provider = add one line here. Nothing else changes.
#
# Current: LocalAuthBackend only (MODE 1 — local login)
# Future:  Uncomment CentralSSOBackend when CP integration is ready (MODE 2)
AUTHENTICATION_BACKENDS = [
    'users.auth_backends.LocalAuthBackend',
    # 'users.auth_backends.CentralSSOBackend',  # Uncomment when CP is ready
]


# ─── Database (PostgreSQL) ───────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     os.environ['DB_NAME'],
        'USER':     os.environ['DB_USER'],
        'PASSWORD': os.environ['DB_PASSWORD'],
        'HOST':     os.getenv('DB_HOST', 'localhost'),
        'PORT':     os.getenv('DB_PORT', '5432'),
        'OPTIONS':  {'connect_timeout': 10},
    }
}


# ─── Session ─────────────────────────────────────────────────────────────────
# Server-side DB sessions. The browser holds only an HttpOnly signed cookie.
# No tokens stored in localStorage.
SESSION_ENGINE              = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_NAME         = os.getenv('SESSION_COOKIE_NAME',    'bd_sessionid')
SESSION_COOKIE_HTTPONLY     = True
SESSION_COOKIE_SAMESITE     = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
SESSION_COOKIE_SECURE       = os.getenv('SESSION_COOKIE_SECURE',   'False') == 'True'
SESSION_COOKIE_AGE          = int(os.getenv('SESSION_COOKIE_AGE',  str(60 * 15)))
SESSION_EXPIRE_AT_BROWSER_CLOSE = os.getenv('SESSION_EXPIRE_AT_BROWSER_CLOSE', 'False') == 'True'
SESSION_SAVE_EVERY_REQUEST  = True


# ─── CSRF ────────────────────────────────────────────────────────────────────
# CSRF is ENABLED for all unsafe methods (POST/PUT/PATCH/DELETE).
# The frontend reads bd_csrftoken and sends it as X-CSRFToken header.
# Do NOT disable CSRF to make API calls "easier".
CSRF_COOKIE_NAME     = os.getenv('CSRF_COOKIE_NAME',     'bd_csrftoken')
CSRF_COOKIE_HTTPONLY = False   # Must be False — JS reads this cookie
CSRF_COOKIE_SAMESITE = os.getenv('CSRF_COOKIE_SAMESITE', 'Lax')
CSRF_COOKIE_SECURE   = os.getenv('CSRF_COOKIE_SECURE',   'False') == 'True'
CSRF_HEADER_NAME     = 'HTTP_X_CSRFTOKEN'

_csrf_trusted = os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost:5173,http://localhost:3000')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_trusted.split(',') if o.strip()]


# ─── CORS ────────────────────────────────────────────────────────────────────
CORS_ALLOW_CREDENTIALS = True  # Required — cookies must be sent cross-origin

_cors_origins = os.getenv('CORS_ALLOWED_ORIGINS', '')
if _cors_origins:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins.split(',') if o.strip()]
else:
    CORS_ALLOW_ALL_ORIGINS = DEBUG  # Dev fallback only — never True in production

CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type',
    'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
]


# ─── Django REST Framework ───────────────────────────────────────────────────
# These are GLOBAL defaults — individual views must not override
# authentication_classes or implement their own session/token checks.
# Only exceptional per-endpoint permission changes are allowed at view level.
REST_FRAMEWORK = {
    # ── Single authentication class for the whole application ──
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'core.authentication.authentication.TLPortalSessionAuthentication',
    ],

    # ── Every endpoint requires authentication unless AllowAny is explicit ──
    'DEFAULT_PERMISSION_CLASSES': [
        'core.authentication.permissions.IsAuthenticatedUser',
    ],

    # ── Centralised exception handler — consistent error envelope ──
    'EXCEPTION_HANDLER': 'core.authentication.authentication.custom_exception_handler',

    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    'NON_FIELD_ERRORS_KEY': 'errors',
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%S',
}

# Add browsable API and BasicAuth in development only
if DEBUG:
    REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ]
    REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = [
        'core.authentication.authentication.TLPortalSessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',  # Dev convenience only
    ]


# ─── Password Validation ─────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ─── Internationalisation ────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = os.getenv('TIME_ZONE', 'Asia/Kolkata')
USE_I18N      = True
USE_TZ        = True


# ─── Static & Media ──────────────────────────────────────────────────────────
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'templates' / 'static']

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ─── Default PK ──────────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ─── Login URL ───────────────────────────────────────────────────────────────
LOGIN_URL          = '/api/auth/login/'
LOGIN_REDIRECT_URL = '/'


# ─── Email ───────────────────────────────────────────────────────────────────
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST          = os.getenv('EMAIL_HOST',          'smtp.gmail.com')
    EMAIL_PORT          = int(os.getenv('EMAIL_PORT',      '587'))
    EMAIL_USE_TLS       = os.getenv('EMAIL_USE_TLS',       'True') == 'True'
    EMAIL_HOST_USER     = os.getenv('EMAIL_HOST_USER',     '')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
    DEFAULT_FROM_EMAIL  = os.getenv('DEFAULT_FROM_EMAIL',  'noreply@municipality.gov.in')


# ─── File Upload ─────────────────────────────────────────────────────────────
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024


# ─── Logging ─────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '[{levelname}] {asctime} {name} {message}', 'style': '{'},
        'simple':  {'format': '[{levelname}] {message}',                  'style': '{'},
    },
    'handlers': {
        'console': {
            'class':     'logging.StreamHandler',
            'formatter': 'simple' if DEBUG else 'verbose',
        },
    },
    'root': {'handlers': ['console'], 'level': 'DEBUG' if DEBUG else 'WARNING'},
    'loggers': {
        'django.db.backends': {'handlers': ['console'], 'level': 'INFO',  'propagate': False},
        'core.authentication': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
        'users':               {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
        'birth_death':         {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
    },
}


# ─── Production security hardening ───────────────────────────────────────────
if not DEBUG:
    SECURE_HSTS_SECONDS            = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD            = True
    SECURE_SSL_REDIRECT            = True
    SESSION_COOKIE_SECURE          = True
    CSRF_COOKIE_SECURE             = True
    SECURE_BROWSER_XSS_FILTER      = True
    SECURE_CONTENT_TYPE_NOSNIFF    = True
    X_FRAME_OPTIONS                = 'DENY'


# ══════════════════════════════════════════════════════════════════════════════
# CENTRAL PORTAL / SSO CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
# All values read from .env. No credentials are hard-coded.
# These settings feed into core/authentication/ exclusively.
# Business modules must never read these settings directly.
#
# To activate SSO:
#   1. Set CENTRAL_PORTAL_ENABLED=True
#   2. Fill all CENTRAL_PORTAL_* values
#   3. Uncomment CentralSSOBackend in AUTHENTICATION_BACKENDS above
#   4. Add sso/callback/ URL is already wired in BirthDeath/urls.py
#   → No other change needed anywhere in the application
# ──────────────────────────────────────────────────────────────────────────────

CENTRAL_PORTAL_ENABLED          = os.getenv('CENTRAL_PORTAL_ENABLED',          'False') == 'True'
CENTRAL_PORTAL_URL              = os.getenv('CENTRAL_PORTAL_URL',              '')
CENTRAL_PORTAL_CLIENT_ID        = os.getenv('CENTRAL_PORTAL_CLIENT_ID',        '')
CENTRAL_PORTAL_CLIENT_SECRET    = os.getenv('CENTRAL_PORTAL_CLIENT_SECRET',    '')
CENTRAL_PORTAL_REDIRECT_URI     = os.getenv('CENTRAL_PORTAL_REDIRECT_URI',     '')
CENTRAL_PORTAL_APPLICATION_CODE = os.getenv('CENTRAL_PORTAL_APPLICATION_CODE', 'BIRTH_DEATH')
CENTRAL_PORTAL_LOGIN_URL        = os.getenv('CENTRAL_PORTAL_LOGIN_URL',        '')
CENTRAL_PORTAL_CALLBACK_URL     = os.getenv('CENTRAL_PORTAL_CALLBACK_URL',     '')
CENTRAL_PORTAL_LOGOUT_URL       = os.getenv('CENTRAL_PORTAL_LOGOUT_URL',       '')
CENTRAL_PORTAL_PROPAGATE_LOGOUT = os.getenv('CENTRAL_PORTAL_PROPAGATE_LOGOUT', 'False') == 'True'


# ══════════════════════════════════════════════════════════════════════════════
# RAZORPAY PAYMENT GATEWAY
# ══════════════════════════════════════════════════════════════════════════════
# Keys are loaded exclusively from .env — never hard-coded.
# RAZORPAY_KEY_ID   is safe to expose to the browser (used in checkout.js).
# RAZORPAY_KEY_SECRET must NEVER leave the server — used only for server-side
#   HMAC-SHA256 signature verification in payments/views.py.
#
# To activate online payments:
#   1. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env
#   2. Set RAZORPAY_CURRENCY if not INR
#   3. No other file needs to change — views.py reads these settings.
# ──────────────────────────────────────────────────────────────────────────────

RAZORPAY_KEY_ID     = os.getenv('RAZORPAY_KEY_ID',     '')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET', '')
RAZORPAY_CURRENCY   = os.getenv('RAZORPAY_CURRENCY',   'INR')
