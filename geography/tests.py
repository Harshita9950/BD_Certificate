from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from .models import District, ULB, ULBType, Zone, Ward
from users.models import User, UserRole, UserOrganisationalScope


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_district(code='D01', name='Test District'):
    return District.objects.create(code=code, name=name)


def make_ulb(district, code='U01', name='Test ULB', ulb_type=ULBType.NAGAR_NIGAM):
    return ULB.objects.create(district=district, code=code, name=name, ulb_type=ulb_type)


def make_zone(ulb, code='Z01', name='Test Zone'):
    return Zone.objects.create(ulb=ulb, code=code, name=name)


def make_ward(zone, code='W01', name='Test Ward'):
    return Ward.objects.create(zone=zone, code=code, name=name)


def make_user(email, role=UserRole.OFFICER, ulb_code='U01'):
    return User.objects.create_user(
        email=email, username=email.split('@')[0].lower(),
        password='Pass123!', first_name='Test', last_name='User',
        role=role, ulb_code=ulb_code,
    )


# ── District ──────────────────────────────────────────────────────────────────

class DistrictModelTest(TestCase):

    def test_create_district(self):
        d = make_district()
        self.assertEqual(d.code, 'D01')
        self.assertTrue(d.is_active)
        self.assertIsNotNone(d.created_at)

    def test_str(self):
        d = make_district()
        self.assertIn('D01', str(d))

    def test_code_is_unique(self):
        make_district('D01')
        with self.assertRaises(IntegrityError):
            make_district('D01', name='Duplicate')

    def test_inactive_district(self):
        d = District.objects.create(code='D02', name='Old', is_active=False)
        self.assertFalse(d.is_active)


# ── ULB ───────────────────────────────────────────────────────────────────────

class ULBModelTest(TestCase):

    def setUp(self):
        self.district = make_district()

    def test_create_ulb(self):
        ulb = make_ulb(self.district)
        self.assertEqual(ulb.district, self.district)
        self.assertEqual(ulb.ulb_type, ULBType.NAGAR_NIGAM)
        self.assertTrue(ulb.is_active)

    def test_str(self):
        ulb = make_ulb(self.district)
        self.assertIn('U01', str(ulb))

    def test_ulb_code_unique(self):
        make_ulb(self.district, 'U01')
        with self.assertRaises(IntegrityError):
            make_ulb(self.district, 'U01', name='Dup')

    def test_multiple_ulb_types(self):
        u1 = make_ulb(self.district, 'U01', ulb_type=ULBType.NAGAR_NIGAM)
        u2 = make_ulb(self.district, 'U02', ulb_type=ULBType.NAGAR_PARISHAD)
        u3 = make_ulb(self.district, 'U03', ulb_type=ULBType.NAGAR_PALIKA)
        self.assertEqual(u1.ulb_type, 'NAGAR_NIGAM')
        self.assertEqual(u2.ulb_type, 'NAGAR_PARISHAD')
        self.assertEqual(u3.ulb_type, 'NAGAR_PALIKA')

    def test_district_protect_on_delete(self):
        make_ulb(self.district)
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.district.delete()

    def test_multiple_ulbs_per_district(self):
        make_ulb(self.district, 'U01')
        make_ulb(self.district, 'U02', name='Second ULB')
        self.assertEqual(self.district.ulbs.count(), 2)


# ── Zone ──────────────────────────────────────────────────────────────────────

class ZoneModelTest(TestCase):

    def setUp(self):
        self.district = make_district()
        self.ulb      = make_ulb(self.district)

    def test_create_zone(self):
        z = make_zone(self.ulb)
        self.assertEqual(z.ulb, self.ulb)
        self.assertTrue(z.is_active)

    def test_str(self):
        z = make_zone(self.ulb)
        self.assertIn(self.ulb.code, str(z))

    def test_zone_code_unique_within_ulb(self):
        make_zone(self.ulb, 'Z01')
        with self.assertRaises(IntegrityError):
            make_zone(self.ulb, 'Z01', name='Dup')

    def test_same_zone_code_different_ulb_allowed(self):
        ulb2 = make_ulb(self.district, 'U02', name='Second ULB')
        make_zone(self.ulb, 'Z01')
        z2 = make_zone(ulb2, 'Z01', name='Zone in ULB2')
        self.assertEqual(z2.code, 'Z01')

    def test_ulb_protect_on_delete(self):
        make_zone(self.ulb)
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.ulb.delete()


# ── Ward ──────────────────────────────────────────────────────────────────────

class WardModelTest(TestCase):

    def setUp(self):
        self.district = make_district()
        self.ulb      = make_ulb(self.district)
        self.zone     = make_zone(self.ulb)

    def test_create_ward(self):
        w = make_ward(self.zone)
        self.assertEqual(w.zone, self.zone)
        self.assertTrue(w.is_active)

    def test_str(self):
        w = make_ward(self.zone)
        self.assertIn(self.ulb.code, str(w))

    def test_ward_code_unique_within_zone(self):
        make_ward(self.zone, 'W01')
        with self.assertRaises(IntegrityError):
            make_ward(self.zone, 'W01', name='Dup')

    def test_same_ward_code_different_zone_allowed(self):
        z2 = make_zone(self.ulb, 'Z02', name='Zone 2')
        make_ward(self.zone, 'W01')
        w2 = make_ward(z2, 'W01', name='Ward in Z2')
        self.assertEqual(w2.code, 'W01')

    def test_zone_protect_on_delete(self):
        make_ward(self.zone)
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.zone.delete()

    def test_inactive_ward_excluded_from_default_view_queryset(self):
        make_ward(self.zone, 'W01')
        Ward.objects.create(zone=self.zone, code='W02', name='Old', is_active=False)
        active = Ward.objects.filter(is_active=True)
        self.assertEqual(active.count(), 1)


# ── Full hierarchy chain ──────────────────────────────────────────────────────

class GeographyHierarchyTest(TestCase):

    def test_full_chain(self):
        d = make_district('DX', 'District X')
        u = make_ulb(d, 'UX', 'ULB X')
        z = make_zone(u, 'ZX', 'Zone X')
        w = make_ward(z, 'WX', 'Ward X')

        self.assertEqual(w.zone.ulb.district, d)
        self.assertEqual(d.ulbs.first(), u)
        self.assertEqual(u.zones.first(), z)
        self.assertEqual(z.wards.first(), w)

    def test_multiple_ulb_isolation(self):
        d = make_district()
        u1 = make_ulb(d, 'U01', 'ULB 1')
        u2 = make_ulb(d, 'U02', 'ULB 2')
        z1 = make_zone(u1, 'Z01')
        z2 = make_zone(u2, 'Z01', name='Zone in ULB2')

        self.assertNotEqual(z1.ulb, z2.ulb)
        self.assertEqual(Zone.objects.filter(ulb=u1).count(), 1)
        self.assertEqual(Zone.objects.filter(ulb=u2).count(), 1)


# ── User organisational assignment ───────────────────────────────────────────

class UserOrgAssignmentTest(TestCase):

    def setUp(self):
        self.district = make_district()
        self.ulb      = make_ulb(self.district)
        self.zone     = make_zone(self.ulb)
        self.ward     = make_ward(self.zone)

    def test_user_assigned_to_ulb_fk(self):
        user = make_user('officer@test.com')
        user.ulb_fk = self.ulb
        user.save()
        self.assertEqual(user.ulb_fk, self.ulb)
        self.assertEqual(user.ulb_fk.district, self.district)

    def test_user_assigned_to_zone_fk(self):
        user = make_user('zone@test.com')
        user.ulb_fk  = self.ulb
        user.zone_fk = self.zone
        user.save()
        self.assertEqual(user.zone_fk.ulb, self.ulb)

    def test_user_assigned_to_ward_fk(self):
        user = make_user('ward@test.com')
        user.ulb_fk  = self.ulb
        user.zone_fk = self.zone
        user.ward_fk = self.ward
        user.save()
        self.assertEqual(user.ward_fk.zone, self.zone)

    def test_user_ulb_code_char_field_still_works(self):
        user = make_user('compat@test.com', ulb_code='U01')
        self.assertEqual(user.ulb_code, 'U01')

    def test_ulb_protect_prevents_delete_when_user_assigned(self):
        user = make_user('p@test.com')
        user.ulb_fk = self.ulb
        user.save()
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.ulb.delete()


# ── UserOrganisationalScope ───────────────────────────────────────────────────

class UserOrganisationalScopeTest(TestCase):

    def setUp(self):
        self.district = make_district()
        self.ulb      = make_ulb(self.district)
        self.zone     = make_zone(self.ulb)
        self.ward     = make_ward(self.zone)
        self.user     = make_user('scope@test.com')

    def test_ulb_level_scope(self):
        scope = UserOrganisationalScope.objects.create(
            user=self.user,
            scope_level=UserOrganisationalScope.ScopeLevel.ULB,
            ulb=self.ulb,
        )
        self.assertEqual(scope.scope_level, 'ULB')
        self.assertIsNone(scope.zone)
        self.assertIsNone(scope.ward)

    def test_zone_level_scope(self):
        scope = UserOrganisationalScope.objects.create(
            user=self.user,
            scope_level=UserOrganisationalScope.ScopeLevel.ZONE,
            ulb=self.ulb,
            zone=self.zone,
        )
        self.assertEqual(scope.zone, self.zone)
        self.assertIsNone(scope.ward)

    def test_ward_level_scope(self):
        scope = UserOrganisationalScope.objects.create(
            user=self.user,
            scope_level=UserOrganisationalScope.ScopeLevel.WARD,
            ulb=self.ulb,
            zone=self.zone,
            ward=self.ward,
        )
        self.assertEqual(scope.ward, self.ward)

    def test_multiple_scopes_per_user(self):
        ulb2  = make_ulb(self.district, 'U02', 'Second ULB')
        zone2 = make_zone(ulb2, 'Z02', 'Zone in ULB2')
        UserOrganisationalScope.objects.create(
            user=self.user, scope_level='ZONE', ulb=self.ulb, zone=self.zone
        )
        UserOrganisationalScope.objects.create(
            user=self.user, scope_level='ZONE', ulb=ulb2, zone=zone2
        )
        self.assertEqual(self.user.org_scopes.count(), 2)

    def test_scope_isolation_between_ulbs(self):
        u2 = make_user('other@test.com', ulb_code='U02')
        ulb2 = make_ulb(self.district, 'U02', 'ULB 2')
        UserOrganisationalScope.objects.create(
            user=self.user, scope_level='ULB', ulb=self.ulb
        )
        UserOrganisationalScope.objects.create(
            user=u2, scope_level='ULB', ulb=ulb2
        )
        u1_ulbs = [s.ulb for s in self.user.org_scopes.all()]
        u2_ulbs = [s.ulb for s in u2.org_scopes.all()]
        self.assertNotIn(ulb2, u1_ulbs)
        self.assertNotIn(self.ulb, u2_ulbs)

    def test_inactive_scope(self):
        scope = UserOrganisationalScope.objects.create(
            user=self.user, scope_level='ULB', ulb=self.ulb, is_active=False
        )
        active = self.user.org_scopes.filter(is_active=True)
        self.assertEqual(active.count(), 0)


# ── API endpoints ─────────────────────────────────────────────────────────────

class GeographyAPITest(TestCase):

    def setUp(self):
        self.client   = APIClient()
        self.user     = make_user('api@test.com')
        self.district = make_district('D01', 'API District')
        self.ulb      = make_ulb(self.district, 'U01')
        self.zone     = make_zone(self.ulb, 'Z01')
        self.ward     = make_ward(self.zone, 'W01')

    def test_district_list_requires_auth(self):
        r = self.client.get('/api/geography/districts/')
        self.assertIn(r.status_code, [401, 403])

    def test_district_list_authenticated(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get('/api/geography/districts/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_ulb_list_authenticated(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get('/api/geography/ulbs/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_zone_list_authenticated(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get('/api/geography/zones/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_ward_list_authenticated(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get('/api/geography/wards/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_inactive_records_excluded(self):
        District.objects.create(code='D99', name='Inactive', is_active=False)
        self.client.force_authenticate(user=self.user)
        r = self.client.get('/api/geography/districts/')
        codes = [item['code'] for item in r.data['results']]
        self.assertNotIn('D99', codes)

    def test_endpoints_are_read_only(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.post('/api/geography/districts/', {'code': 'X', 'name': 'X'})
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
