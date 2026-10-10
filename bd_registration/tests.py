"""
bd_registration/tests.py
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient
from django.utils import timezone

from bd_master.models import RegistrationType
from geography.models import District, ULB, Zone, Ward
from users.models import UserRole

from .models import (
    AdoptedBirthRegistration,
    Application,
    ApplicationDocument,
    ApplicationStatus,
    BirthRegistration,
    DeathRegistration,
    ServiceType,
    StillBirthRegistration,
)

User = get_user_model()


def make_user(username='testuser', role=UserRole.DA):
    return User.objects.create_user(
        username=username, email=f'{username}@test.com', password='testpass123',
        first_name='Test', last_name='User', role=role,
    )


def make_geo():
    district = District.objects.create(code='JPN', name='Jaipur')
    ulb      = ULB.objects.create(code='JMC', name='Jaipur MC', district=district, ulb_type='NAGAR_NIGAM')
    zone     = Zone.objects.create(code='Z1', name='Zone 1', ulb=ulb)
    ward     = Ward.objects.create(code='W1', name='Ward 1', zone=zone)
    return district, ulb, zone, ward


def make_rtype(code='BIRTH_NORMAL', name='Normal Birth', category='BIRTH'):
    return RegistrationType.objects.create(code=code, name=name, event_category=category)


def make_application(user, district, ulb, rtype, state_code='RJ'):
    return Application.objects.create(
        service_type=ServiceType.BIRTH,
        registration_type=rtype,
        district=district,
        ulb=ulb,
        state_code=state_code,
        submitted_by=user,
        date_of_reporting=date.today(),
    )


class PageViewTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def _load(self, url_name):
        from django.test import Client as DjangoClient
        c = DjangoClient()
        c.force_login(self.user)
        return c.get(reverse(url_name))

    # Case 1
    def test_birth_page_loads(self):
        self.assertEqual(self._load('birth_registration').status_code, 200)

    def test_death_page_loads(self):
        self.assertEqual(self._load('death_registration').status_code, 200)

    def test_still_birth_page_loads(self):
        self.assertEqual(self._load('still_birth_registration').status_code, 200)

    def test_adopted_birth_page_loads(self):
        self.assertEqual(self._load('adopted_birth_registration').status_code, 200)

    # Case 2
    def test_unauthenticated_redirected(self):
        from django.test import Client as DjangoClient
        c = DjangoClient()
        r = c.get(reverse('birth_registration'))
        self.assertIn(r.status_code, [302, 403])


class DraftCreationTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.district, self.ulb, _, _ = make_geo()
        self.rtype = make_rtype()

    # Case 3
    def test_birth_draft_created(self):
        app = make_application(self.user, self.district, self.ulb, self.rtype)
        br = BirthRegistration.objects.create(application=app, date_of_birth=date.today() - timedelta(5), sex='MALE')
        self.assertEqual(app.status, ApplicationStatus.DRAFT)
        self.assertIn('BD-', app.application_number)
        self.assertEqual(br.registration_number, '')

    # Case 4
    def test_death_draft_created(self):
        rt = make_rtype('DEATH_NORMAL', 'Normal Death', 'DEATH')
        app = Application.objects.create(service_type=ServiceType.DEATH, registration_type=rt, district=self.district, ulb=self.ulb, state_code='RJ', submitted_by=self.user)
        dr = DeathRegistration.objects.create(application=app, deceased_first_name='John', date_of_death=date.today() - timedelta(3), sex='MALE')
        self.assertEqual(app.status, ApplicationStatus.DRAFT)
        self.assertEqual(dr.registration_number, '')

    # Case 5
    def test_still_birth_draft_created(self):
        rt = make_rtype('BIRTH_STILL', 'Still Birth', 'STILL_BIRTH')
        app = Application.objects.create(service_type=ServiceType.STILL_BIRTH, registration_type=rt, district=self.district, ulb=self.ulb, state_code='RJ', submitted_by=self.user)
        sbr = StillBirthRegistration.objects.create(application=app, date_of_birth=date.today() - timedelta(2), sex='FEMALE')
        self.assertEqual(app.status, ApplicationStatus.DRAFT)

    # Case 6
    def test_adopted_birth_draft_created(self):
        rt = make_rtype('BIRTH_ADOPTED', 'Adopted Birth', 'BIRTH')
        app = Application.objects.create(service_type=ServiceType.ADOPTED_BIRTH, registration_type=rt, district=self.district, ulb=self.ulb, state_code='RJ', submitted_by=self.user)
        abr = AdoptedBirthRegistration.objects.create(application=app, date_of_birth=date(2020, 1, 1), sex='MALE')
        self.assertEqual(app.status, ApplicationStatus.DRAFT)


class DateValidationTests(TestCase):
    def setUp(self):
        self.district, self.ulb, _, _ = make_geo()
        self.rtype = make_rtype()
        self.user = make_user('dv_user')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _make_birth_app(self, reporting, dob):
        app = Application.objects.create(service_type=ServiceType.BIRTH, registration_type=self.rtype, district=self.district, ulb=self.ulb, state_code='RJ', submitted_by=self.user, date_of_reporting=reporting)
        BirthRegistration.objects.create(application=app, date_of_birth=dob, sex='MALE')
        return app

    # Case 7
    def test_reporting_before_dob_rejected(self):
        dob = date.today() - timedelta(5)
        app = self._make_birth_app(dob - timedelta(1), dob)
        r = self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        self.assertEqual(r.status_code, 400)

    # Case 8
    def test_future_death_date_rejected(self):
        rt = make_rtype('DEATH_NRM2', 'Death', 'DEATH')
        app = Application.objects.create(service_type=ServiceType.DEATH, registration_type=rt, district=self.district, ulb=self.ulb, state_code='RJ', submitted_by=self.user, date_of_reporting=date.today())
        DeathRegistration.objects.create(application=app, deceased_first_name='Jane', date_of_death=date.today() + timedelta(3), sex='FEMALE')
        r = self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        self.assertEqual(r.status_code, 400)

    # Case 9
    def test_future_birth_date_rejected(self):
        app = self._make_birth_app(date.today(), date.today() + timedelta(2))
        r = self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        self.assertEqual(r.status_code, 400)


class ApplicationNumberTests(TestCase):
    def test_application_number_format(self):
        district, ulb, _, _ = make_geo()
        rtype = make_rtype('BN2', 'Birth Normal 2')
        user = make_user('apn_user')
        app = Application.objects.create(service_type=ServiceType.BIRTH, registration_type=rtype, district=district, ulb=ulb, state_code='RJ', submitted_by=user)
        self.assertRegex(app.application_number, r'^BD-\d{4}-\d{6}$')


class SubmissionWorkflowTests(TestCase):
    def setUp(self):
        self.district, self.ulb, _, _ = make_geo()
        self.rtype = make_rtype('WF_B', 'WF Birth')
        self.user = make_user('wf_user')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _make(self, dob=None, reporting=None):
        dob = dob or date.today() - timedelta(5)
        reporting = reporting or date.today()
        app = Application.objects.create(service_type=ServiceType.BIRTH, registration_type=self.rtype, district=self.district, ulb=self.ulb, state_code='RJ', submitted_by=self.user, date_of_reporting=reporting)
        BirthRegistration.objects.create(application=app, date_of_birth=dob, sex='MALE')
        return app

    # Case 11
    def test_submit_changes_status(self):
        app = self._make()
        r = self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        self.assertEqual(r.status_code, 200)
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)

    # Case 12
    def test_submitted_at_populated(self):
        app = self._make()
        self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        app.refresh_from_db()
        self.assertIsNotNone(app.submitted_at)

    # Case 13
    def test_no_reg_number_on_submit(self):
        app = self._make()
        self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        app.birth_registration.refresh_from_db()
        self.assertEqual(app.birth_registration.registration_number, '')

    # Case 14
    def test_reg_number_generated_at_register(self):
        app = self._make()
        app.status = ApplicationStatus.APPROVED
        app.save(update_fields=['status'])
        r = self.client.post(f'/api/bd-registration/applications/{app.pk}/register/')
        self.assertEqual(r.status_code, 200)
        app.birth_registration.refresh_from_db()
        self.assertRegex(app.birth_registration.registration_number, r'^BD-REG-\d{4}-\d{6}$')

    # Case 15
    def test_date_of_registration_at_register(self):
        app = self._make()
        app.status = ApplicationStatus.APPROVED
        app.save(update_fields=['status'])
        self.client.post(f'/api/bd-registration/applications/{app.pk}/register/')
        app.birth_registration.refresh_from_db()
        self.assertIsNotNone(app.birth_registration.date_of_registration)

    # Case 16
    def test_invalid_transition_rejected(self):
        app = self._make()
        r = self.client.post(f'/api/bd-registration/applications/{app.pk}/approve/')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data.get('code'), 'invalid_transition')


class DelayCalculationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=make_user('delay_user'))

    # Case 17
    def test_delay_check_normal(self):
        today = date.today()
        r = self.client.post('/api/bd-registration/delay-check/', {'event_date': str(today - timedelta(5)), 'date_of_reporting': str(today), 'state_code': 'RJ'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['delay_category'], 'NORMAL')

    def test_delay_check_delayed_30(self):
        today = date.today()
        r = self.client.post('/api/bd-registration/delay-check/', {'event_date': str(today - timedelta(25)), 'date_of_reporting': str(today), 'state_code': 'RJ'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['delay_category'], 'DELAYED_30_DAYS')

    def test_delay_reporting_before_event_rejected(self):
        today = date.today()
        r = self.client.post('/api/bd-registration/delay-check/', {'event_date': str(today), 'date_of_reporting': str(today - timedelta(1)), 'state_code': 'RJ'})
        self.assertEqual(r.status_code, 400)


class DocumentTests(TestCase):
    def setUp(self):
        self.district, self.ulb, _, _ = make_geo()
        self.rtype = make_rtype('DOC_B', 'Doc Birth')
        self.user = make_user('doc_user')
        self.app = Application.objects.create(service_type=ServiceType.BIRTH, registration_type=self.rtype, district=self.district, ulb=self.ulb, submitted_by=self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    # Case 18
    def test_documents_attach_to_application(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile('test.pdf', b'PDF', content_type='application/pdf')
        doc = ApplicationDocument.objects.create(application=self.app, file=f, original_filename='test.pdf', uploaded_by=self.user)
        self.assertEqual(doc.application, self.app)
        self.assertEqual(self.app.documents.count(), 1)

    def test_document_list_endpoint(self):
        r = self.client.get(f'/api/bd-registration/applications/{self.app.pk}/documents/')
        self.assertEqual(r.status_code, 200)


class SecurityTests(TestCase):
    def setUp(self):
        self.district, self.ulb, _, _ = make_geo()
        self.rtype = make_rtype('SEC_B', 'Sec Birth')
        self.owner = make_user('sec_owner')
        self.app = Application.objects.create(service_type=ServiceType.BIRTH, registration_type=self.rtype, district=self.district, ulb=self.ulb, submitted_by=self.owner)
        rt_d = make_rtype('SEC_D', 'Sec Death', 'DEATH')
        self.death_app = Application.objects.create(service_type=ServiceType.DEATH, registration_type=rt_d, district=self.district, ulb=self.ulb, submitted_by=self.owner)
        self.dr = DeathRegistration.objects.create(application=self.death_app, deceased_first_name='Dec', date_of_death=date.today() - timedelta(2), sex='MALE', cause_of_death='Heart failure')

    # Case 19
    def test_unauthenticated_submit_rejected(self):
        r = APIClient().post(f'/api/bd-registration/applications/{self.app.pk}/submit/')
        self.assertEqual(r.status_code, 401)

    # Case 20
    def test_cause_of_death_not_in_public_response(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        r = client.get(f'/api/bd-registration/deaths/{self.dr.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('cause_of_death', r.data)
