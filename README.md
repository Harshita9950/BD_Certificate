# TL_portal — Municipal Trade Licence Management System

Django REST API backend for managing the complete Trade Licence lifecycle
in Urban Local Bodies (ULBs). Designed to be reusable across municipalities
and states, with a future-safe pluggable authentication architecture.

---

## Technology Stack

| Layer         | Technology                          |
|---------------|-------------------------------------|
| Language      | Python 3.11 / 3.12                  |
| Framework     | Django 4.2 LTS                      |
| API           | Django REST Framework 3.15          |
| Auth          | Django Session Authentication + CSRF|
| Database      | PostgreSQL (psycopg2-binary)        |
| CORS          | django-cors-headers                 |
| Env Config    | python-dotenv                       |
| Frontend      | React + Vite (separate repository)  |

---

## Project Structure

```
Trade_License/
│
├── manage.py
│
├── TL_portal/                  ← Django project package
│   ├── __init__.py
│   ├── settings.py             ← Single settings file, env-driven
│   ├── urls.py                 ← Root URL dispatcher
│   ├── asgi.py
│   └── wsgi.py
│
├── users/                      ← Custom User model, roles, auth
│   ├── migrations/
│   ├── urls/
│   │   ├── auth.py             ← /api/auth/* endpoints
│   │   └── users.py            ← /api/users/* endpoints
│   ├── models.py               ← User, Role, Permission, CentralIdentity, …
│   ├── auth_backends.py        ← LocalAuthBackend + CentralSSOBackend stub
│   ├── views.py
│   ├── serializers.py
│   ├── admin.py
│   └── tests.py
│
├── trade_license/              ← Trade Licence business domain
│   ├── migrations/
│   ├── models.py               ← Application models (Phase 2+)
│   ├── views.py
│   ├── serializers.py
│   ├── urls.py
│   ├── admin.py
│   └── tests.py
│
├── requirements.txt
├── .env.example                ← Commit this
├── .env                        ← DO NOT commit — in .gitignore
├── .gitignore
└── README.md
```

---

## Trade Licence Lifecycle

```
Citizen Registration / Login
  → New Application
    → Applicant Details
    → Business Details
    → Premises Details
    → Trade / Sub-Trade Selection
    → Document Upload
    → Submission
      → Scrutiny (Clerk / DA)
        → Deficiency Notice (if required) → Applicant Responds
      → Inspection Assignment → Inspector Field Report
      → Officer Review → Approved / Rejected
        → Fee Calculation (configurable rules — no hard-coded rates)
        → Demand Note Generated
        → Payment
          → Licence Generated
            → Renewal / Modification / Transfer / Enforcement
```

---

## Local Setup

### 1. Clone and create virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

Open `.env` and set at minimum:
- `SECRET_KEY` — generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD` — your PostgreSQL credentials

### 4. Create the PostgreSQL database

```sql
CREATE DATABASE tl_portal_db;
-- If using a dedicated user:
CREATE USER tl_user WITH PASSWORD 'your-password';
GRANT ALL PRIVILEGES ON DATABASE tl_portal_db TO tl_user;
```

### 5. Run migrations

```bash
python manage.py migrate
```

### 6. Create a superuser

```bash
python manage.py createsuperuser
```

### 7. Start the development server

```bash
python manage.py runserver
```

- API root: `http://127.0.0.1:8000/api/`
- Admin panel: `http://127.0.0.1:8000/admin/`

---

## API Endpoints (Foundation)

| Method | Endpoint                   | Description                        | Auth        |
|--------|----------------------------|------------------------------------|-------------|
| GET    | `/api/auth/csrf/`          | Get CSRF cookie (call on startup)  | Public      |
| POST   | `/api/auth/login/`         | Local login → creates session      | Public      |
| POST   | `/api/auth/logout/`        | Destroy session                    | Session     |
| GET    | `/api/auth/status/`        | Check session / get current user   | Session     |
| POST   | `/api/users/register/`     | Citizen self-registration          | Public      |
| GET    | `/api/users/profile/`      | View own profile                   | Session     |
| PATCH  | `/api/users/profile/`      | Update own profile                 | Session     |

---

## Authentication Architecture

### Mode 1 — Local Login (Active)

```
User opens Trade Licence portal
    ↓
GET /api/auth/csrf/          ← browser receives CSRF cookie
    ↓
POST /api/auth/login/        ← email + password + X-CSRFToken header
    ↓
LocalAuthBackend.authenticate()
    ↓
Django session created (server-side DB, HttpOnly cookie)
    ↓
All subsequent API calls use session cookie automatically
    ↓
Every protected endpoint verifies the session
    ↓
Dashboard / application
```

### Mode 2 — Central Portal / SSO (Future — not yet active)

```
User opens Central Portal
    ↓
Authenticates with Central Portal credentials
    ↓
Central Portal verifies application access (TRADE_LICENSE)
    ↓
Central Portal issues trusted identity assertion
    ↓
Trade Licence portal receives assertion at /api/auth/sso/callback/
    ↓
CentralSSOBackend.authenticate() validates assertion
    ↓
Maps Central Identity → local User (via CentralIdentity model)
    ↓
Checks UserApplicationAccess(TRADE_LICENSE)
    ↓
Django session created — user lands on Dashboard
    ↓
No second login screen
```

### Pluggable Backend Design

The `AUTHENTICATION_BACKENDS` setting in `TL_portal/settings.py` controls
which backends are active:

```python
AUTHENTICATION_BACKENDS = [
    'users.auth_backends.LocalAuthBackend',
    # 'users.auth_backends.CentralSSOBackend',   ← uncomment when ready
]
```

Adding the Central SSO provider requires:
1. Implementing `CentralSSOBackend.authenticate()` in `users/auth_backends.py`
2. Uncommenting the backend in settings
3. Setting `CENTRAL_SSO_ENABLED=True` and the `CENTRAL_SSO_*` env vars
4. Adding the SSO callback URL to `users/urls/auth.py`

No other application code needs to change.

---

## Session & CSRF Security

| Principle                          | Implementation                                   |
|------------------------------------|--------------------------------------------------|
| Session stored server-side         | `SESSION_ENGINE = django.contrib.sessions.backends.db` |
| Session cookie is HttpOnly         | `SESSION_COOKIE_HTTPONLY = True`                 |
| CSRF middleware always enabled     | `django.middleware.csrf.CsrfViewMiddleware`      |
| CSRF cookie readable by JS         | `CSRF_COOKIE_HTTPONLY = False`                   |
| Frontend sends X-CSRFToken header  | Required for POST/PUT/PATCH/DELETE               |
| No tokens in localStorage          | Sessions only — no JWT for browser clients       |
| Cookies scoped correctly           | `SESSION_COOKIE_SAMESITE = Lax`                  |

---

## Role & Permission Architecture

Roles and permissions are database-driven — nothing is hard-coded.

```
User → role (CharField)
         ↓
      Role (DB record)
         ↓
      Permission (DB records)
         e.g. application.approve, inspection.assign, license.generate
```

Predefined roles (bootstrap reference — stored in DB):
`CITIZEN`, `DA`, `HEALTH_OFFICER`, `CHO`, `ACCOUNTANT`, `RI`,
`ZONE_OFFICER`, `COMMISSIONER`, `AUDITOR`, `ADMIN`

---

## Application-Level Authorization

`UserApplicationAccess` records which applications each user may access.
This is the hook for Central Portal multi-application routing.

```
User A → TRADE_LICENSE   → Allowed
User A → UD_TAX          → Allowed
User B → TRADE_LICENSE   → Not Allowed (no access record)
```

---

## User Models

| Model                 | Purpose                                                    |
|-----------------------|------------------------------------------------------------|
| `User`                | Central user record — all actors share this model          |
| `Role`                | Database-driven role with assigned permissions             |
| `Permission`          | Named permission string (e.g. `application.approve`)       |
| `UserApplicationAccess` | Which applications a user is authorized for              |
| `CentralIdentity`     | Maps local User ↔ Central Portal identity (SSO readiness) |
| `UserLoginLog`        | Immutable audit log of every login event                   |

---

## Production Deployment Checklist

- [ ] Set `DEBUG=False`
- [ ] Generate a strong `SECRET_KEY`
- [ ] Set `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`
- [ ] Set `SESSION_COOKIE_SECURE=True` and `CSRF_COOKIE_SECURE=True`
- [ ] Configure PostgreSQL with a dedicated application user
- [ ] Run `python manage.py collectstatic`
- [ ] Use gunicorn behind nginx
- [ ] Configure HTTPS / TLS termination at the proxy
- [ ] Set up log rotation
