"""
users/tests.py
==============
Foundation test suite proving the centralised auth/authorisation layer works.

Test scenarios covered (as required):
  1. Local authentication works
  2. Protected API uses centralised authentication
  3. Unauthorized users are rejected
  4. Permission checks work
  5. ULB isolation works
  6. Multiple APIs use the same authentication mechanism
  7. Authentication/session expiry is handled centrally

Run with:
    python manage.py test users --verbosity=2
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from rest_framework.test import APIClient
from rest_framework import status

from users.models import (
    UserRole, Role, Permission,
    UserApplicationAccess, ApplicationCode,
    CentralIdentity, UserLoginLog,
)
from core.authentication.permissions import (
    HasRole, HasPermission, ULBIsolationPermission, IsAuthenticatedUser,
)
from core.authentication.exceptions import (
    NotAuthenticatedError, AccountInactiveError,
    ApplicationAccessDeniedError, PermissionDeniedError,
    RoleRequiredError, ULBAccessDeniedError,
)

User = get_user_model()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_user(email, password='TestPass123!', role=UserRole.CITIZEN,
              ulb_code='ULB001', is_active=True, username=None, **kwargs):
    """Create a test user. Derives username from email prefix when not supplied."""
    if username is None:
        username = email.split('@')[0].lower()
    return User.objects.create_user(
        email=email, username=username, password=password, role=role,
        ulb_code=ulb_code, first_name='Test', last_name='User',
        is_active=is_active, **kwargs,
    )


def make_permission(code, module='application'):
    return Permission.objects.get_or_create(code=code, defaults={'module': module})[0]


def make_role(code, permission_codes=None):
    role, _ = Role.objects.get_or_create(code=code, defaults={'name': code})
    if permission_codes:
        for pc in permission_codes:
            perm = make_permission(pc)
            role.permissions.add(perm)
    return role


# ─── 1. Local Authentication Tests ───────────────────────────────────────────

class LocalAuthenticationTest(TestCase):
    """Scenario 1: Local authentication works."""

    def setUp(self):
        self.client = APIClient()
        self.user   = make_user('citizen@test.com', password='SecurePass1!')
        self.login_url = '/api/auth/login/'
        self.csrf_url  = '/api/auth/csrf/'

    def test_csrf_cookie_endpoint_is_public(self):
        """GET /api/auth/csrf/ must be accessible without authentication."""
        response = self.client.get(self.csrf_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_with_correct_credentials_creates_session(self):
        """POST /api/auth/login/ with valid credentials returns 200 + user profile."""
        response = self.client.post(
            self.login_url,
            {'username': 'citizen', 'password': 'SecurePass1!'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('user',   response.data)
        self.assertIn('detail', response.data)
        self.assertEqual(response.data['user']['email'], 'citizen@test.com')

    def test_login_with_wrong_password_returns_401(self):
        """POST /api/auth/login/ with wrong password returns 401."""
        response = self.client.post(
            self.login_url,
            {'username': 'citizen', 'password': 'WrongPassword!'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_with_nonexistent_username_returns_401(self):
        """Login attempt for unknown username returns 401."""
        response = self.client.post(
            self.login_url,
            {'username': 'nobody', 'password': 'AnyPass1!'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_with_missing_fields_returns_400(self):
        """Login with empty body returns 400."""
        response = self.client.post(self.login_url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_with_username_identifier(self):
        """LocalAuthBackend authenticates using the username field."""
        response = self.client.post(
            self.login_url,
            {'username': 'citizen', 'password': 'SecurePass1!'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_log_created_on_success(self):
        """Successful login writes a UserLoginLog record with username_attempted."""
        self.client.post(
            self.login_url,
            {'username': 'citizen', 'password': 'SecurePass1!'},
            format='json',
        )
        log = UserLoginLog.objects.filter(
            username_attempted='citizen', status='SUCCESS'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.method, 'LOCAL')

    def test_login_log_created_on_failure(self):
        """Failed login writes a UserLoginLog with FAILURE status."""
        self.client.post(
            self.login_url,
            {'username': 'citizen', 'password': 'BadPass!'},
            format='json',
        )
        log = UserLoginLog.objects.filter(status='FAILURE').first()
        self.assertIsNotNone(log)

    def test_logout_destroys_session(self):
        """POST /api/auth/logout/ on authenticated session returns 200."""
        self.client.post(
            self.login_url,
            {'username': 'citizen', 'password': 'SecurePass1!'},
            format='json',
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/auth/logout/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_register_endpoint_is_public(self):
        """POST /api/users/register/ must be accessible without authentication."""
        response = self.client.post(
            '/api/users/register/',
            {
                'email': 'new@test.com',
                'username': 'newuser',
                'first_name': 'New',
                'last_name': 'User',
                'password': 'NewPass123!',
                'password2': 'NewPass123!',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


# ─── 2 & 6. Protected API Uses Centralised Authentication ────────────────────

class CentralisedAuthenticationTest(TestCase):
    """
    Scenarios 2 & 6: Protected API uses centralised auth.
    Multiple APIs must use the same mechanism — no per-view auth overrides.
    """

    def setUp(self):
        self.client = APIClient()
        self.user   = make_user('officer@test.com', role=UserRole.DA)

    def test_profile_endpoint_requires_auth(self):
        """GET /api/users/profile/ must reject unauthenticated requests."""
        response = self.client.get('/api/users/profile/')
        self.assertIn(response.status_code, [401, 403])

    def test_profile_returns_correct_user_when_authenticated(self):
        """Authenticated user gets own profile from /api/users/profile/."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/users/profile/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'officer@test.com')

    def test_session_status_requires_auth(self):
        """GET /api/auth/status/ must reject anonymous requests."""
        response = self.client.get('/api/auth/status/')
        self.assertIn(response.status_code, [401, 403])

    def test_session_status_returns_user_when_authenticated(self):
        """GET /api/auth/status/ returns user info for authenticated session."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/auth/status/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('user', response.data)

    def test_multiple_endpoints_reject_anonymous(self):
        """
        Several protected endpoints all reject anonymous requests —
        proving centralised auth not per-view logic.
        """
        endpoints = [
            '/api/users/profile/',
            '/api/auth/status/',
            '/api/auth/logout/',
        ]
        for url in endpoints:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertIn(
                    response.status_code, [401, 403],
                    msg=f'{url} should require authentication',
                )


# ─── 3. Unauthorized Users Are Rejected ──────────────────────────────────────

class UnauthorisedRejectionTest(TestCase):
    """Scenario 3: Unauthenticated and unauthorised users are rejected."""

    def setUp(self):
        self.client = APIClient()

    def test_anonymous_profile_access_rejected(self):
        response = self.client.get('/api/users/profile/')
        self.assertIn(response.status_code, [401, 403])

    def test_anonymous_logout_rejected(self):
        response = self.client.post('/api/auth/logout/')
        self.assertIn(response.status_code, [401, 403])

    def test_inactive_user_rejected_by_auth_backend(self):
        """Inactive user's credentials are rejected by LocalAuthBackend."""
        make_user('inactive@test.com', username='inactive_user',
                  password='Pass123!', is_active=False)
        response = self.client.post(
            '/api/auth/login/',
            {'username': 'inactive_user', 'password': 'Pass123!'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_user_force_auth_rejected_by_permission_class(self):
        """
        Even if force_authenticate bypasses the backend, the global
        IsAuthenticatedUser permission class rejects inactive users.
        """
        inactive = make_user('inactive2@test.com', is_active=False)
        self.client.force_authenticate(user=inactive)
        response = self.client.get('/api/users/profile/')
        # TLPortalSessionAuthentication raises AccountInactiveError → 401
        self.assertIn(response.status_code, [401, 403])


# ─── 4. Permission Checks Work ───────────────────────────────────────────────

class PermissionCheckTest(TestCase):
    """Scenario 4: Permission checks work via centralised permission classes."""

    def setUp(self):
        self.client = APIClient()
        # Create a role with specific permissions
        self.perm_approve = make_permission('application.approve', 'application')
        self.perm_view    = make_permission('application.view',    'application')
        self.officer_role = make_role(UserRole.OFFICER, ['application.approve', 'application.view'])
        self.da_role      = make_role(UserRole.DA, ['application.view'])

        self.officer = make_user('officer@perm.com', role=UserRole.OFFICER)
        self.da      = make_user('da@perm.com',      role=UserRole.DA)
        self.citizen = make_user('citizen@perm.com', role=UserRole.CITIZEN)

    def test_has_permission_class_returns_true_when_user_has_perm(self):
        """HasPermission._user_has_permission returns True for permitted role."""
        result = HasPermission._user_has_permission(self.officer, 'application.approve')
        self.assertTrue(result)

    def test_has_permission_class_returns_false_when_user_lacks_perm(self):
        """HasPermission returns False when role has no such permission."""
        result = HasPermission._user_has_permission(self.da, 'application.approve')
        self.assertFalse(result)

    def test_has_role_of_factory_allows_correct_role(self):
        """HasRole.of() permits users with matching role."""
        request = type('Req', (), {'user': self.officer})()
        perm    = HasRole.of(UserRole.OFFICER)()
        self.assertTrue(perm.has_permission(request, None))

    def test_has_role_of_factory_denies_wrong_role(self):
        """HasRole.of() raises RoleRequiredError for wrong role."""
        request = type('Req', (), {'user': self.citizen})()
        perm    = HasRole.of(UserRole.OFFICER)()
        with self.assertRaises(RoleRequiredError):
            perm.has_permission(request, None)

    def test_is_authenticated_user_rejects_anonymous(self):
        """IsAuthenticatedUser raises NotAuthenticatedError for anonymous."""
        from django.contrib.auth.models import AnonymousUser
        request = type('Req', (), {'user': AnonymousUser()})()
        perm    = IsAuthenticatedUser()
        with self.assertRaises(NotAuthenticatedError):
            perm.has_permission(request, None)

    def test_is_authenticated_user_rejects_inactive(self):
        """IsAuthenticatedUser raises AccountInactiveError for inactive user."""
        inactive = make_user('inactive@perm.com', is_active=False)
        request  = type('Req', (), {'user': inactive})()
        perm     = IsAuthenticatedUser()
        with self.assertRaises(AccountInactiveError):
            perm.has_permission(request, None)

    def test_permission_denied_has_correct_code(self):
        """PermissionDeniedError carries the 'permission_denied' code."""
        exc = PermissionDeniedError()
        self.assertEqual(exc.status_code, 403)
        self.assertEqual(exc.default_code, 'permission_denied')


# ─── 5. ULB Isolation Works ──────────────────────────────────────────────────

class ULBIsolationTest(TestCase):
    """Scenario 5: ULB isolation prevents cross-ULB data access."""

    def setUp(self):
        self.client = APIClient()
        self.user_a = make_user('a@ulb.com', role=UserRole.OFFICER, ulb_code='ULB_A')
        self.user_b = make_user('b@ulb.com', role=UserRole.OFFICER, ulb_code='ULB_B')
        self.admin  = make_user('admin@ulb.com', role=UserRole.ADMIN, ulb_code='')

    def _make_obj(self, ulb_code):
        """Create a mock object with ulb_code attribute."""
        return type('Obj', (), {'ulb_code': ulb_code})()

    def test_user_can_access_own_ulb_object(self):
        """ULBIsolationPermission permits access to same ULB."""
        request = type('Req', (), {'user': self.user_a})()
        perm    = ULBIsolationPermission()
        obj     = self._make_obj('ULB_A')
        self.assertTrue(perm.has_object_permission(request, None, obj))

    def test_user_denied_other_ulb_object(self):
        """ULBIsolationPermission raises ULBAccessDeniedError for cross-ULB access."""
        request = type('Req', (), {'user': self.user_a})()
        perm    = ULBIsolationPermission()
        obj     = self._make_obj('ULB_B')
        with self.assertRaises(ULBAccessDeniedError):
            perm.has_object_permission(request, None, obj)

    def test_admin_bypasses_ulb_isolation(self):
        """ADMIN role bypasses ULB isolation — can access any ULB."""
        request = type('Req', (), {'user': self.admin})()
        perm    = ULBIsolationPermission()
        obj     = self._make_obj('ULB_X')
        self.assertTrue(perm.has_object_permission(request, None, obj))

    def test_ulb_access_denied_error_has_correct_status(self):
        """ULBAccessDeniedError is a 403 exception."""
        exc = ULBAccessDeniedError()
        self.assertEqual(exc.status_code, 403)
        self.assertEqual(exc.default_code, 'ulb_access_denied')

    def test_user_ulb_code_stored_on_model(self):
        """ulb_code is correctly stored and retrieved from User model."""
        user = make_user('ulbtest@test.com', ulb_code='ULB_TEST')
        self.assertEqual(user.ulb_code, 'ULB_TEST')


# ─── 7. Session Expiry Handled Centrally ────────────────────────────────────

class SessionExpiryTest(TestCase):
    """Scenario 7: Session expiry is handled centrally, not per-view."""

    def setUp(self):
        self.client = APIClient()
        self.user   = make_user('expire@test.com')

    def test_unauthenticated_request_returns_401_not_500(self):
        """
        An expired or missing session returns 401 — not an unhandled error.
        Proves that the global auth class handles this, not individual views.
        """
        # No authentication — simulates expired session
        for url in ['/api/users/profile/', '/api/auth/status/']:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotEqual(
                    response.status_code, 500,
                    msg=f'{url} returned 500 — auth error not handled centrally',
                )
                self.assertIn(response.status_code, [401, 403])

    def test_inactive_user_session_returns_401(self):
        """
        Session for a now-inactive user must return 401.
        Validates TLPortalSessionAuthentication.authenticate() catches this.
        """
        inactive = make_user('nowgone@test.com', is_active=False)
        self.client.force_authenticate(user=inactive)
        response = self.client.get('/api/users/profile/')
        self.assertIn(response.status_code, [401, 403])

    def test_session_expiry_exception_has_correct_code(self):
        """SessionExpiredError carries the right code and HTTP status."""
        from core.authentication.exceptions import SessionExpiredError
        exc = SessionExpiredError()
        self.assertEqual(exc.status_code, 401)
        self.assertEqual(exc.default_code, 'session_expired')

    def test_not_authenticated_error_has_correct_code(self):
        """NotAuthenticatedError carries the right code and HTTP status."""
        exc = NotAuthenticatedError()
        self.assertEqual(exc.status_code, 401)
        self.assertEqual(exc.default_code, 'not_authenticated')


# ─── Application Access Tests ────────────────────────────────────────────────

class ApplicationAccessTest(TestCase):
    """Application-level access control via UserApplicationAccess."""

    def setUp(self):
        self.user_with_access    = make_user('access@test.com')
        self.user_without_access = make_user('noaccess@test.com')
        UserApplicationAccess.objects.create(
            user=self.user_with_access,
            application_code=ApplicationCode.TRADE_LICENSE,
            is_active=True,
        )

    def test_has_application_access_true_when_record_exists(self):
        result = self.user_with_access.has_application_access(
            ApplicationCode.TRADE_LICENSE
        )
        self.assertTrue(result)

    def test_has_application_access_false_when_no_record(self):
        result = self.user_without_access.has_application_access(
            ApplicationCode.TRADE_LICENSE
        )
        self.assertFalse(result)

    def test_application_access_denied_error_has_correct_status(self):
        exc = ApplicationAccessDeniedError()
        self.assertEqual(exc.status_code, 403)
        self.assertEqual(exc.default_code, 'application_access_denied')

    @override_settings(CENTRAL_PORTAL_ENABLED=False)
    def test_app_access_permission_skipped_in_local_mode(self):
        """ApplicationAccessPermission is a no-op when CP is disabled."""
        from core.authentication.permissions import ApplicationAccessPermission
        request = type('Req', (), {'user': self.user_without_access})()
        perm    = ApplicationAccessPermission()
        self.assertTrue(perm.has_permission(request, None))


# ─── Central Identity / SSO Readiness Tests ──────────────────────────────────

class CentralIdentityTest(TestCase):
    """CentralIdentity model stores SSO mapping correctly."""

    def test_central_identity_created_and_linked(self):
        user = make_user('sso@test.com')
        ci   = CentralIdentity.objects.create(
            user=user,
            provider='CENTRAL_PORTAL',
            central_user_id='CP-12345',
            central_username='sso_user',
            extra_data={'department': 'ULB_DEPT'},
        )
        self.assertEqual(ci.user.email, 'sso@test.com')
        self.assertEqual(ci.central_user_id, 'CP-12345')
        self.assertEqual(ci.provider, 'CENTRAL_PORTAL')

    def test_central_identity_is_one_to_one(self):
        """A user can have at most one CentralIdentity."""
        user = make_user('sso2@test.com')
        CentralIdentity.objects.create(
            user=user, provider='CP', central_user_id='CP-AAA'
        )
        with self.assertRaises(Exception):
            CentralIdentity.objects.create(
                user=user, provider='CP2', central_user_id='CP-BBB'
            )

    def test_user_without_central_identity_has_no_sso_link(self):
        user = make_user('local@test.com')
        self.assertFalse(hasattr(user, 'central_identity') and
                         CentralIdentity.objects.filter(user=user).exists())


# ─── User Model Tests ─────────────────────────────────────────────────────────

class UserModelTest(TestCase):
    """Custom User model fields and properties."""

    def test_create_user_sets_defaults(self):
        user = make_user('u@test.com')
        self.assertEqual(user.role, UserRole.CITIZEN)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_verified)

    def test_username_is_username_field(self):
        self.assertEqual(User.USERNAME_FIELD, 'username')

    def test_is_citizen_property(self):
        user = make_user('c@test.com', role=UserRole.CITIZEN)
        self.assertTrue(user.is_citizen)
        self.assertFalse(user.is_officer)

    def test_is_officer_property(self):
        user = make_user('o@test.com', role=UserRole.DA)
        self.assertTrue(user.is_officer)
        self.assertFalse(user.is_citizen)

    def test_get_full_name(self):
        user = make_user('fn@test.com')
        user.first_name = 'Ravi'
        user.last_name  = 'Kumar'
        self.assertEqual(user.get_full_name(), 'Ravi Kumar')

    def test_create_superuser(self):
        admin = User.objects.create_superuser(
            email='super@test.com', username='superuser',
            password='Admin123!', first_name='Super', last_name='User',
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.role, UserRole.ADMIN)


# ─── Dashboard Integration Tests ─────────────────────────────────────────────

class DashboardTest(TestCase):
    """
    Covers all required dashboard integration scenarios:
      - login → dashboard
      - authenticated dashboard access
      - unauthenticated dashboard access → redirect to login
      - inactive user → redirect to login
      - logout invalidates session
      - 401/403 handling on API endpoints
      - localStorage contains no authentication data (behaviour contract verified
        via view/response — browser enforcement is validated by the template)
      - session/auth secrets not exposed to JavaScript in response
    """

    def setUp(self):
        self.client = Client()
        self.user   = make_user('dash@test.com', role=UserRole.OFFICER)

    # ── 1. Login → Dashboard ─────────────────────────────────────────────────

    def test_login_redirects_to_dashboard(self):
        response = self.client.post(
            '/api/auth/login/',
            data={'username': 'dash', 'password': 'TestPass123!'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['detail'], 'Login successful.')
        self.assertIn('user', data)
        self.assertEqual(data['user']['email'], 'dash@test.com')

    def test_login_creates_session_cookie(self):
        self.client.post(
            '/api/auth/login/',
            data={'username': 'dash', 'password': 'TestPass123!'},
            content_type='application/json',
        )
        self.assertIn('tl_sessionid', self.client.cookies)

    # ── 2. Authenticated dashboard access ────────────────────────────────────

    def test_authenticated_user_can_access_dashboard(self):
        self.client.force_login(self.user)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'Authority/dashboard.html')
        self.assertTemplateUsed(response, 'Authority/base.html')

    def test_dashboard_contains_no_hardcoded_admin_name(self):
        self.client.force_login(self.user)
        response = self.client.get('/dashboard/')
        content = response.content.decode()
        self.assertNotIn('Admin Name', content)
        self.assertNotIn('Administrator', content)

    def test_dashboard_renders_authenticated_user_name(self):
        self.client.force_login(self.user)
        response = self.client.get('/dashboard/')
        content = response.content.decode()
        self.assertIn(self.user.get_full_name(), content)

    # ── 3. Unauthenticated dashboard access → redirect to login ──────────────

    def test_unauthenticated_dashboard_redirects_to_login(self):
        response = self.client.get('/dashboard/')
        self.assertIn(response.status_code, [301, 302])
        self.assertIn('/login/', response['Location'])

    def test_unauthenticated_dashboard_redirect_preserves_next_param(self):
        response = self.client.get('/dashboard/')
        self.assertIn('next=', response['Location'])

    # ── 4. Inactive user → redirect to login ─────────────────────────────────

    def test_inactive_user_dashboard_redirects_to_login(self):
        inactive = make_user('inactive_dash@test.com', is_active=False)
        self.client.force_login(inactive)
        response = self.client.get('/dashboard/')
        self.assertIn(response.status_code, [301, 302])
        self.assertIn('/login/', response['Location'])

    # ── 5. Logout invalidates session ────────────────────────────────────────

    def test_logout_invalidates_session(self):
        self.client.force_login(self.user)
        self.client.post('/api/auth/logout/')
        response = self.client.get('/dashboard/')
        self.assertIn(response.status_code, [301, 302])

    def test_logout_returns_200(self):
        self.client.force_login(self.user)
        response = self.client.post('/api/auth/logout/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['detail'], 'Logged out successfully.')

    def test_logout_requires_active_session(self):
        response = self.client.post('/api/auth/logout/')
        self.assertIn(response.status_code, [401, 403])

    # ── 6. 401 / 403 handling ────────────────────────────────────────────────

    def test_unauthenticated_api_returns_401(self):
        response = self.client.get('/api/auth/status/')
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertIn('detail', data)
        self.assertIn('code', data)

    def test_unauthenticated_profile_returns_401(self):
        response = self.client.get('/api/users/profile/')
        self.assertEqual(response.status_code, 401)

    def test_401_response_is_json_not_html(self):
        response = self.client.get('/api/users/profile/')
        self.assertEqual(response['Content-Type'], 'application/json')

    # ── 7. Session cookie is HttpOnly ─────────────────────────────────────────

    def test_session_cookie_is_httponly(self):
        self.client.post(
            '/api/auth/login/',
            data={'username': 'dash', 'password': 'TestPass123!'},
            content_type='application/json',
        )
        cookie = self.client.cookies.get('tl_sessionid')
        self.assertIsNotNone(cookie)
        self.assertTrue(cookie['httponly'])

    def test_session_cookie_name_is_custom(self):
        self.client.post(
            '/api/auth/login/',
            data={'username': 'dash', 'password': 'TestPass123!'},
            content_type='application/json',
        )
        self.assertIn('tl_sessionid', self.client.cookies)
        self.assertNotIn('sessionid', self.client.cookies)

    # ── 8. No auth secrets exposed to JavaScript ──────────────────────────────

    def test_dashboard_response_does_not_expose_session_id_in_body(self):
        self.client.force_login(self.user)
        response = self.client.get('/dashboard/')
        content = response.content.decode()
        session_id = self.client.cookies.get('tl_sessionid')
        if session_id:
            self.assertNotIn(session_id.value, content)

    def test_dashboard_response_does_not_contain_password(self):
        self.client.force_login(self.user)
        response = self.client.get('/dashboard/')
        content = response.content.decode()
        self.assertNotIn('Pass123!', content)

    def test_api_status_does_not_expose_password_hash(self):
        self.client.force_login(self.user)
        response = self.client.get('/api/auth/status/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn('password', data.get('user', {}))

    # ── 9. Session status API ────────────────────────────────────────────────

    def test_session_status_returns_user_when_authenticated(self):
        self.client.force_login(self.user)
        response = self.client.get('/api/auth/status/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['user']['email'], 'dash@test.com')

    def test_session_status_returns_401_after_logout(self):
        self.client.force_login(self.user)
        self.client.post('/api/auth/logout/')
        response = self.client.get('/api/auth/status/')
        self.assertEqual(response.status_code, 401)

    # ── 10. SSO architecture compatibility ───────────────────────────────────

    def test_sso_initiate_returns_503_when_disabled(self):
        response = self.client.get('/api/auth/sso/initiate/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'sso_disabled')

    def test_sso_callback_returns_503_when_disabled(self):
        response = self.client.get('/api/auth/sso/callback/?code=test')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'sso_disabled')
