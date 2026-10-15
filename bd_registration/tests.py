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


# ─────────────────────────────────────────────────────────────────────────────
# PAYMENT PENDING STATUS TESTS  (Step 2)
# ─────────────────────────────────────────────────────────────────────────────

from unittest.mock import patch
from decimal import Decimal
from bd_registration.services import DelayResult
from bd_master.models import DelayCategory


def _make_delay_result(fee=Decimal('0.00'), category='NORMAL'):
    """Helper to build a DelayResult with controllable fee and category."""
    return DelayResult(
        delay_days=5,
        delay_category=category,
        is_normal=(category == 'NORMAL'),
        fee_code='BD.REG_NORMAL' if fee == Decimal('0.00') else 'BD.LATE_30',
        applicable_fee=fee,
        currency='INR',
        requires_authority=False,
        authority_code=None,
        authority_name=None,
        authority_notes='',
        requires_form_14=False,
        requires_affidavit=False,
        requires_permission_order=False,
        required_document_codes=[],
        required_document_names=[],
        rule_reference='',
        rule_code='',
        error='',
    )


class PaymentPendingStatusTests(TestCase):
    """
    Verify that PAYMENT_PENDING is inserted between DRAFT and SUBMITTED
    when the backend-calculated fee is non-zero, and bypassed for zero-fee
    (FREE) registrations.
    """

    def setUp(self):
        self.district, self.ulb, _, _ = make_geo()
        self.rtype  = make_rtype('PP_B', 'PP Birth')
        self.user   = make_user('pp_user')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _make_birth_app(self, dob_offset=5, reporting_offset=0):
        """Create a DRAFT Application with a BirthRegistration."""
        dob       = date.today() - timedelta(dob_offset)
        reporting = date.today() - timedelta(reporting_offset)
        app = Application.objects.create(
            service_type=ServiceType.BIRTH,
            registration_type=self.rtype,
            district=self.district,
            ulb=self.ulb,
            state_code='RJ',
            submitted_by=self.user,
            date_of_reporting=reporting,
        )
        BirthRegistration.objects.create(
            application=app, date_of_birth=dob, sex='MALE',
        )
        return app

    # ── Case A: zero-fee registration skips PAYMENT_PENDING ──────────────────

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_zero_fee_goes_directly_to_submitted(self, mock_calc):
        """
        When applicable_fee == 0 (FREE), submit should transition
        DRAFT → SUBMITTED without stopping at PAYMENT_PENDING.
        """
        mock_calc.return_value = _make_delay_result(fee=Decimal('0.00'), category='NORMAL')

        app = self._make_birth_app()
        r   = self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')

        self.assertEqual(r.status_code, 200, r.data)
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)
        self.assertFalse(r.data.get('payment_required', True))

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_zero_fee_submitted_at_is_set(self, mock_calc):
        """submitted_at must be populated for FREE submissions."""
        mock_calc.return_value = _make_delay_result(fee=Decimal('0.00'), category='NORMAL')
        app = self._make_birth_app()
        self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        app.refresh_from_db()
        self.assertIsNotNone(app.submitted_at)

    # ── Case B: non-zero fee transitions to PAYMENT_PENDING ──────────────────

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_nonzero_fee_transitions_to_payment_pending(self, mock_calc):
        """
        When applicable_fee > 0, submit should transition
        DRAFT → PAYMENT_PENDING (not SUBMITTED).
        """
        mock_calc.return_value = _make_delay_result(
            fee=Decimal('20.00'), category='DELAYED_30_DAYS'
        )
        app = self._make_birth_app(dob_offset=25)
        r   = self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')

        self.assertEqual(r.status_code, 200, r.data)
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING)
        self.assertTrue(r.data.get('payment_required'))

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_payment_pending_response_includes_fee_details(self, mock_calc):
        """Response must include applicable_fee, fee_code and currency."""
        mock_calc.return_value = _make_delay_result(
            fee=Decimal('20.00'), category='DELAYED_30_DAYS'
        )
        app = self._make_birth_app(dob_offset=25)
        r   = self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')

        self.assertIn('applicable_fee', r.data)
        self.assertIn('fee_code',       r.data)
        self.assertIn('currency',       r.data)
        self.assertEqual(r.data['applicable_fee'], '20.00')

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_payment_pending_submitted_at_not_set(self, mock_calc):
        """submitted_at must be NULL while in PAYMENT_PENDING."""
        mock_calc.return_value = _make_delay_result(
            fee=Decimal('20.00'), category='DELAYED_30_DAYS'
        )
        app = self._make_birth_app(dob_offset=25)
        self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        app.refresh_from_db()
        self.assertIsNone(app.submitted_at)

    # ── Case C: status-history correctness ───────────────────────────────────

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_history_records_payment_pending_transition(self, mock_calc):
        """ApplicationStatusHistory must record DRAFT → PAYMENT_PENDING."""
        mock_calc.return_value = _make_delay_result(
            fee=Decimal('50.00'), category='DELAYED_1_YEAR'
        )
        app = self._make_birth_app(dob_offset=100)
        self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')

        history = app.status_history.order_by('changed_at')
        actions  = [h.action for h in history]
        self.assertIn('PAYMENT_PENDING', actions)
        last = history.last()
        self.assertEqual(last.new_status, ApplicationStatus.PAYMENT_PENDING)

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_history_records_submitted_for_free(self, mock_calc):
        """ApplicationStatusHistory must record DRAFT → SUBMITTED for FREE."""
        mock_calc.return_value = _make_delay_result(fee=Decimal('0.00'))
        app = self._make_birth_app()
        self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')

        history = app.status_history.order_by('changed_at')
        last    = history.last()
        self.assertEqual(last.action, 'SUBMITTED')
        self.assertEqual(last.new_status, ApplicationStatus.SUBMITTED)

    # ── Case D: confirm-payment action ───────────────────────────────────────

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_confirm_payment_transitions_to_submitted(self, mock_calc):
        """
        confirm-payment must move PAYMENT_PENDING → SUBMITTED when a PAID
        PaymentOrder exists.
        """
        from payments.models import PaymentOrder, PaymentMethod, PaymentOrderStatus

        mock_calc.return_value = _make_delay_result(
            fee=Decimal('20.00'), category='DELAYED_30_DAYS'
        )
        app = self._make_birth_app(dob_offset=25)
        self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING)

        # Simulate the payments app marking the order PAID.
        order = PaymentOrder.objects.create(
            application=app,
            fee_code='BD.LATE_30',
            amount=Decimal('20.00'),
            currency='INR',
            payment_method=PaymentMethod.CASH,
            status=PaymentOrderStatus.PAID,
            created_by=self.user,
        )

        r = self.client.post(
            f'/api/bd-registration/applications/{app.pk}/confirm-payment/'
        )
        self.assertEqual(r.status_code, 200, r.data)
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)
        self.assertTrue(r.data.get('payment_confirmed'))

    def test_confirm_payment_without_paid_order_rejected(self):
        """confirm-payment must be rejected if no PAID PaymentOrder exists."""
        app = self._make_birth_app()
        app.status = ApplicationStatus.PAYMENT_PENDING
        app.save(update_fields=['status'])

        r = self.client.post(
            f'/api/bd-registration/applications/{app.pk}/confirm-payment/'
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn(r.data.get('code'), ['payment_order_missing', 'payment_not_confirmed'])

    def test_confirm_payment_from_wrong_status_rejected(self):
        """confirm-payment must be rejected for a DRAFT application."""
        app = self._make_birth_app()
        # app is DRAFT, not PAYMENT_PENDING
        r = self.client.post(
            f'/api/bd-registration/applications/{app.pk}/confirm-payment/'
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data.get('code'), 'invalid_transition')

    # ── Case E: cancel still works from PAYMENT_PENDING ──────────────────────

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_cancel_from_payment_pending(self, mock_calc):
        """An application in PAYMENT_PENDING must be cancellable."""
        mock_calc.return_value = _make_delay_result(
            fee=Decimal('20.00'), category='DELAYED_30_DAYS'
        )
        app = self._make_birth_app(dob_offset=25)
        self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING)

        r = self.client.post(
            f'/api/bd-registration/applications/{app.pk}/cancel/'
        )
        self.assertEqual(r.status_code, 200, r.data)
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.CANCELLED)

    # ── Case F: submit is idempotency-safe ────────────────────────────────────

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_double_submit_rejected(self, mock_calc):
        """Submitting an already-PAYMENT_PENDING application must return 400."""
        mock_calc.return_value = _make_delay_result(
            fee=Decimal('20.00'), category='DELAYED_30_DAYS'
        )
        app = self._make_birth_app(dob_offset=25)
        self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        # Second submit attempt
        r = self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data.get('code'), 'invalid_transition')


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW ASSIGNMENT TESTS  (Step 3)
# ─────────────────────────────────────────────────────────────────────────────

from unittest.mock import patch
from workflow_master.models import Workflow, WorkflowStep
from users.models import ApplicationCode


def _seed_workflow_for_ulb(ulb):
    """
    Create the BD_DEFAULT workflow + SURVEY_MAIL step for a ULB.
    Mirrors what seed_bd_workflow does; uses get_or_create so safe to
    call multiple times in tests.
    """
    workflow, _ = Workflow.objects.get_or_create(
        ulb=ulb,
        application_type=ApplicationCode.BIRTH_DEATH,
        code='BD_DEFAULT',
        defaults={
            'name':      'Birth & Death Registration — Default Workflow',
            'is_active': True,
        },
    )
    step1, _ = WorkflowStep.objects.get_or_create(
        workflow=workflow,
        step_number=1,
        defaults={
            'code':      'SURVEY_MAIL',
            'name':      'Survey Mail',
            'role_code': 'DA',
            'is_active': True,
        },
    )
    WorkflowStep.objects.get_or_create(
        workflow=workflow,
        step_number=2,
        defaults={
            'code':      'SCRUTINY',
            'name':      'Scrutiny',
            'role_code': 'DA',
            'is_active': True,
        },
    )
    return workflow, step1


class WorkflowAssignmentTests(TestCase):
    """
    Verify that assign_workflow() is called correctly by the submission
    and confirm-payment paths, and that PAYMENT_PENDING applications are
    NOT assigned a workflow until payment is confirmed.
    """

    def setUp(self):
        self.district, self.ulb, _, _ = make_geo()
        self.rtype  = make_rtype('WA_B', 'WA Birth')
        self.user   = make_user('wa_user')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        # Seed the workflow for this ULB
        self.workflow, self.step1 = _seed_workflow_for_ulb(self.ulb)

    def _make_birth_app(self, dob_offset=5):
        app = Application.objects.create(
            service_type=ServiceType.BIRTH,
            registration_type=self.rtype,
            district=self.district,
            ulb=self.ulb,
            state_code='RJ',
            submitted_by=self.user,
            date_of_reporting=date.today(),
        )
        BirthRegistration.objects.create(
            application=app,
            date_of_birth=date.today() - timedelta(dob_offset),
            sex='MALE',
        )
        return app

    # ── Case 1: zero-fee submit assigns workflow ──────────────────────────────

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_zero_fee_submit_assigns_workflow(self, mock_calc):
        """
        A zero-fee application must have workflow and current_step set
        after a successful submit.
        """
        mock_calc.return_value = _make_delay_result(
            fee=Decimal('0.00'), category='NORMAL'
        )
        app = self._make_birth_app()
        r   = self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')

        self.assertEqual(r.status_code, 200, r.data)
        app.refresh_from_db()

        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)
        self.assertIsNotNone(app.workflow_id,    'workflow must be assigned')
        self.assertIsNotNone(app.current_step_id, 'current_step must be assigned')
        self.assertEqual(app.workflow.code,      'BD_DEFAULT')
        self.assertEqual(app.current_step.code,  'SURVEY_MAIL')
        self.assertEqual(app.current_step.step_number, 1)

    # ── Case 2: PAYMENT_PENDING must NOT have workflow ────────────────────────

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_payment_pending_not_assigned_workflow(self, mock_calc):
        """
        An application halted at PAYMENT_PENDING must not get a workflow.
        The workflow is assigned only after payment is confirmed.
        """
        mock_calc.return_value = _make_delay_result(
            fee=Decimal('20.00'), category='DELAYED_30_DAYS'
        )
        app = self._make_birth_app(dob_offset=25)
        self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING)
        self.assertIsNone(app.workflow_id,     'workflow must NOT be assigned yet')
        self.assertIsNone(app.current_step_id, 'current_step must NOT be assigned yet')

    # ── Case 3: confirm-payment assigns workflow ──────────────────────────────

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_confirm_payment_assigns_workflow(self, mock_calc):
        """
        After confirm-payment (PAYMENT_PENDING → SUBMITTED), workflow and
        current_step must be set to step 1 (SURVEY_MAIL).
        """
        from payments.models import PaymentOrder, PaymentMethod, PaymentOrderStatus

        mock_calc.return_value = _make_delay_result(
            fee=Decimal('20.00'), category='DELAYED_30_DAYS'
        )
        app = self._make_birth_app(dob_offset=25)
        self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING)

        # Simulate payments app marking order PAID
        PaymentOrder.objects.create(
            application=app,
            fee_code='BD.LATE_30',
            amount=Decimal('20.00'),
            currency='INR',
            payment_method=PaymentMethod.CASH,
            status=PaymentOrderStatus.PAID,
            created_by=self.user,
        )

        r = self.client.post(
            f'/api/bd-registration/applications/{app.pk}/confirm-payment/'
        )
        self.assertEqual(r.status_code, 200, r.data)
        app.refresh_from_db()

        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)
        self.assertIsNotNone(app.workflow_id,     'workflow must be assigned after payment')
        self.assertIsNotNone(app.current_step_id, 'current_step must be assigned after payment')
        self.assertEqual(app.workflow.code,      'BD_DEFAULT')
        self.assertEqual(app.current_step.code,  'SURVEY_MAIL')

    # ── Case 4: assignment is idempotent ──────────────────────────────────────

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_workflow_assignment_is_idempotent(self, mock_calc):
        """
        Calling assign_workflow twice on the same application must not
        change the already-assigned workflow or step.
        """
        from bd_registration.workflow_service import assign_workflow

        mock_calc.return_value = _make_delay_result(
            fee=Decimal('0.00'), category='NORMAL'
        )
        app = self._make_birth_app()
        self.client.post(f'/api/bd-registration/applications/{app.pk}/submit/')
        app.refresh_from_db()

        wf_id_first   = app.workflow_id
        step_id_first = app.current_step_id

        # Call again — must be a no-op
        assign_workflow(app)
        app.refresh_from_db()

        self.assertEqual(app.workflow_id,     wf_id_first,   'workflow unchanged')
        self.assertEqual(app.current_step_id, step_id_first, 'step unchanged')

    # ── Case 5: seed command is idempotent ────────────────────────────────────

    def test_seed_bd_workflow_is_idempotent(self):
        """
        Running _seed_workflow_for_ulb twice for the same ULB must not
        create duplicate Workflow or WorkflowStep records.
        """
        before_wf    = Workflow.objects.filter(ulb=self.ulb).count()
        before_steps = WorkflowStep.objects.filter(
            workflow__ulb=self.ulb
        ).count()

        # Run again
        _seed_workflow_for_ulb(self.ulb)

        after_wf    = Workflow.objects.filter(ulb=self.ulb).count()
        after_steps = WorkflowStep.objects.filter(
            workflow__ulb=self.ulb
        ).count()

        self.assertEqual(before_wf,    after_wf,    'no duplicate workflows')
        self.assertEqual(before_steps, after_steps, 'no duplicate steps')

    # ── Case 6: no workflow configured → submission still succeeds ────────────

    @patch('bd_registration.views.DelayCalculationService.calculate')
    def test_missing_workflow_does_not_block_submission(self, mock_calc):
        """
        If no workflow is seeded for the ULB, submission must still succeed
        (workflow fields stay null — non-fatal).
        """
        # Use a different ULB with no workflow seeded
        district2 = District.objects.create(code='KKK', name='Kota')
        ulb2      = ULB.objects.create(
            code='KMC', name='Kota MC',
            district=district2, ulb_type='NAGAR_NIGAM'
        )
        app = Application.objects.create(
            service_type=ServiceType.BIRTH,
            registration_type=self.rtype,
            district=district2,
            ulb=ulb2,
            state_code='RJ',
            submitted_by=self.user,
            date_of_reporting=date.today(),
        )
        BirthRegistration.objects.create(
            application=app,
            date_of_birth=date.today() - timedelta(5),
            sex='FEMALE',
        )

        mock_calc.return_value = _make_delay_result(
            fee=Decimal('0.00'), category='NORMAL'
        )
        r = self.client.post(
            f'/api/bd-registration/applications/{app.pk}/submit/'
        )

        self.assertEqual(r.status_code, 200, r.data)
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)
        self.assertIsNone(app.workflow_id,     'no workflow — stays null')
        self.assertIsNone(app.current_step_id, 'no step — stays null')

    # ── Case 7: correct step_number=1 is chosen even if created out-of-order ──

    def test_first_step_is_lowest_step_number(self):
        """
        assign_workflow must pick the step with the lowest step_number,
        regardless of DB insertion order.
        """
        from bd_registration.workflow_service import assign_workflow

        # Insert step 3 before step 1 for the existing workflow
        wf = self.workflow
        WorkflowStep.objects.get_or_create(
            workflow=wf, step_number=3,
            defaults={'code': 'VERIFY', 'name': 'Verify', 'role_code': 'OFFICER',
                      'is_active': True},
        )

        app = Application.objects.create(
            service_type=ServiceType.BIRTH,
            registration_type=self.rtype,
            district=self.district, ulb=self.ulb,
            state_code='RJ', submitted_by=self.user,
            status=ApplicationStatus.SUBMITTED,
            date_of_reporting=date.today(),
            submitted_at=timezone.now(),
        )
        BirthRegistration.objects.create(
            application=app, date_of_birth=date.today() - timedelta(3), sex='MALE'
        )

        assign_workflow(app)
        app.refresh_from_db()

        self.assertEqual(app.current_step.step_number, 1)
        self.assertEqual(app.current_step.code, 'SURVEY_MAIL')


# ─────────────────────────────────────────────────────────────────────────────
# END-TO-END INTEGRATION TESTS  (complete flow)
# Covers all 6 scenarios from the task specification.
# ─────────────────────────────────────────────────────────────────────────────

import hashlib
import hmac as hmac_mod
from decimal import Decimal
from unittest.mock import patch

from payments.models import (
    PaymentMethod, PaymentOrder, PaymentOrderStatus,
    PaymentTransaction, PaymentTransactionStatus,
)
from workflow_master.models import Workflow, WorkflowStep
from users.models import ApplicationCode


# ── shared helpers ────────────────────────────────────────────────────────────

def _seed_workflow_e2e(ulb):
    wf, _ = Workflow.objects.get_or_create(
        ulb=ulb,
        application_type=ApplicationCode.BIRTH_DEATH,
        code='BD_DEFAULT',
        defaults={'name': 'BD Default', 'is_active': True},
    )
    WorkflowStep.objects.get_or_create(
        workflow=wf, step_number=1,
        defaults={'code': 'SURVEY_MAIL', 'name': 'Survey Mail',
                  'role_code': 'DA', 'is_active': True},
    )
    return wf


def _free_delay_result():
    from bd_registration.services import DelayResult
    return DelayResult(
        delay_days=5, delay_category='NORMAL', is_normal=True,
        fee_code='BD.REG_NORMAL', applicable_fee=Decimal('0.00'), currency='INR',
        requires_authority=False, authority_code=None, authority_name=None,
        authority_notes='', requires_form_14=False, requires_affidavit=False,
        requires_permission_order=False,
        required_document_codes=[], required_document_names=[],
        rule_reference='', rule_code='', error='',
    )


def _paid_delay_result(fee=Decimal('20.00')):
    from bd_registration.services import DelayResult
    return DelayResult(
        delay_days=25, delay_category='DELAYED_30_DAYS', is_normal=False,
        fee_code='BD.LATE_30', applicable_fee=fee, currency='INR',
        requires_authority=False, authority_code=None, authority_name=None,
        authority_notes='', requires_form_14=False, requires_affidavit=False,
        requires_permission_order=False,
        required_document_codes=[], required_document_names=[],
        rule_reference='', rule_code='', error='',
    )


def _sign(order_id, payment_id, secret='test_secret'):
    msg = f'{order_id}|{payment_id}'.encode()
    return hmac_mod.new(secret.encode(), msg, hashlib.sha256).hexdigest()


class EndToEndFlowTests(TestCase):
    """
    Full integration tests covering all 6 scenarios from the task spec:

    Scenario 1: Zero-fee application → SUBMITTED → Survey Mail → Inbox
    Scenario 2: Cash payment → SUBMITTED → Survey Mail → Inbox
    Scenario 3: Razorpay payment → SUBMITTED → Survey Mail → Inbox
    Scenario 4: Failed / cancelled / invalid-signature do NOT advance
    Scenario 5: Duplicate submissions do NOT duplicate payments or tasks
    Scenario 6: Unpaid PAYMENT_PENDING does NOT advance
    """

    FAKE_SECRET = 'test_secret'

    def setUp(self):
        self.district, self.ulb, _, _ = make_geo()
        self.rtype  = make_rtype('E2E_B', 'E2E Birth')
        self.user   = make_user('e2e_user')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        _seed_workflow_e2e(self.ulb)

    def _submit_birth_app(self, dob_offset=5, delay_result=None):
        """
        Submit a birth application via the atomic endpoint.
        Returns the Application instance.
        """
        if delay_result is None:
            delay_result = _free_delay_result()

        dob       = date.today() - timedelta(dob_offset)
        reporting = date.today()

        with patch('bd_registration.views.DelayCalculationService.calculate',
                   return_value=delay_result):
            r = self.client.post('/api/bd-registration/birth-applications/', {
                'registration_type':  self.rtype.pk,
                'state_code':         'RJ',
                'district':           self.district.pk,
                'ulb':                self.ulb.pk,
                'date_of_reporting':  str(reporting),
                'date_of_birth':      str(dob),
                'sex':                'MALE',
                'action':             'submit',
            })
        self.assertIn(r.status_code, [200, 201], r.data)
        app_id = r.data['id']
        return Application.objects.get(pk=app_id)

    def _create_cash_order(self, app):
        return PaymentOrder.objects.create(
            application=app, fee_code='BD.LATE_30', amount=Decimal('20.00'),
            currency='INR', payment_method=PaymentMethod.CASH,
            status=PaymentOrderStatus.PENDING, created_by=self.user,
        )

    def _create_online_order(self, app, rzp_order_id='order_e2e_001'):
        return PaymentOrder.objects.create(
            application=app, fee_code='BD.LATE_30', amount=Decimal('20.00'),
            currency='INR', payment_method=PaymentMethod.ONLINE,
            status=PaymentOrderStatus.PENDING, created_by=self.user,
            razorpay_order_id=rzp_order_id,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # SCENARIO 1: Zero-fee application goes straight to SUBMITTED + Survey Mail
    # ──────────────────────────────────────────────────────────────────────────

    def test_s1_zero_fee_reaches_survey_mail(self):
        """
        A zero-fee application must:
        1. Submit without hitting PAYMENT_PENDING
        2. Status == SUBMITTED
        3. Workflow assigned (BD_DEFAULT, step 1 = SURVEY_MAIL)
        4. Appear in the inbox
        """
        app = self._submit_birth_app(dob_offset=5, delay_result=_free_delay_result())

        self.assertEqual(app.status, ApplicationStatus.SUBMITTED,
                         'Zero-fee app must be SUBMITTED immediately')
        self.assertIsNotNone(app.workflow_id, 'Workflow must be assigned')
        self.assertEqual(app.current_step.code, 'SURVEY_MAIL')

        # Must appear in inbox (non-DRAFT)
        dc = self.client.__class__()
        dc.force_login(self.user)
        inbox = dc.get(reverse('application_inbox'))
        self.assertEqual(inbox.status_code, 200)
        self.assertContains(inbox, app.application_number)

    def test_s1_zero_fee_no_payment_order_created(self):
        """Zero-fee app must not produce a PaymentOrder."""
        app = self._submit_birth_app(dob_offset=5, delay_result=_free_delay_result())
        self.assertFalse(
            PaymentOrder.objects.filter(application=app).exists(),
            'No PaymentOrder should be created for a zero-fee application',
        )

    # ──────────────────────────────────────────────────────────────────────────
    # SCENARIO 2: Cash payment → SUBMITTED → Survey Mail → Inbox
    # ──────────────────────────────────────────────────────────────────────────

    def test_s2_cash_payment_reaches_survey_mail(self):
        """
        After cash collection:
        1. Application advances to SUBMITTED
        2. Workflow assigned at step SURVEY_MAIL
        3. PaymentOrder status == PAID
        4. PaymentTransaction status == CAPTURED
        """
        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING)

        order = self._create_cash_order(app)

        r = self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'receipt_number': 'RCP-E2E-001', 'payment_date': str(date.today())},
        )
        self.assertEqual(r.status_code, 200, r.data)

        app.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)
        self.assertEqual(app.current_step.code, 'SURVEY_MAIL')
        self.assertEqual(order.status, PaymentOrderStatus.PAID)
        self.assertTrue(
            PaymentTransaction.objects.filter(
                payment_order=order, status=PaymentTransactionStatus.CAPTURED
            ).exists()
        )

    def test_s2_cash_payment_review_page_accessible(self):
        """PAYMENT_PENDING app's review page must return 200."""
        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING)

        dc = self.client.__class__()
        dc.force_login(self.user)
        r = dc.get(reverse('application_review', args=[app.pk]))
        self.assertEqual(r.status_code, 200)

    def test_s2_detail_page_accessible_after_cash_payment(self):
        """After payment, detail page must return 200 (not redirect to review)."""
        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())
        order = self._create_cash_order(app)
        self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'receipt_number': 'RCP-E2E-002', 'payment_date': str(date.today())},
        )
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)

        dc = self.client.__class__()
        dc.force_login(self.user)
        r = dc.get(reverse('application_detail', args=[app.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.get('Location', ''), reverse('application_review', args=[app.pk]))

    # ──────────────────────────────────────────────────────────────────────────
    # SCENARIO 3: Razorpay payment → SUBMITTED → Survey Mail → Inbox
    # ──────────────────────────────────────────────────────────────────────────

    @patch('payments.views.settings')
    def test_s3_razorpay_valid_signature_reaches_survey_mail(self, mock_settings):
        """
        After valid Razorpay signature verification:
        1. Application advances to SUBMITTED
        2. Step == SURVEY_MAIL
        3. PaymentOrder PAID, transaction CAPTURED
        """
        mock_settings.RAZORPAY_KEY_SECRET = self.FAKE_SECRET

        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())
        order = self._create_online_order(app, 'order_rzp_e2e_001')

        payment_id = 'pay_rzp_e2e_001'
        sig = _sign('order_rzp_e2e_001', payment_id, self.FAKE_SECRET)

        r = self.client.post(
            f'/api/payments/orders/{order.pk}/verify-payment/',
            {'razorpay_payment_id': payment_id,
             'razorpay_order_id':   'order_rzp_e2e_001',
             'razorpay_signature':  sig},
        )
        self.assertEqual(r.status_code, 200, r.data)

        app.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)
        self.assertEqual(app.current_step.code, 'SURVEY_MAIL')
        self.assertEqual(order.status, PaymentOrderStatus.PAID)

    # ──────────────────────────────────────────────────────────────────────────
    # SCENARIO 4: Failed / cancelled / invalid-signature do NOT advance
    # ──────────────────────────────────────────────────────────────────────────

    @patch('payments.views.settings')
    def test_s4_invalid_signature_does_not_advance(self, mock_settings):
        """Bad Razorpay signature must NOT advance the application."""
        mock_settings.RAZORPAY_KEY_SECRET = self.FAKE_SECRET

        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())
        order = self._create_online_order(app, 'order_badsig_001')

        r = self.client.post(
            f'/api/payments/orders/{order.pk}/verify-payment/',
            {'razorpay_payment_id': 'pay_badsig_001',
             'razorpay_order_id':   'order_badsig_001',
             'razorpay_signature':  'completely_wrong_signature'},
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['code'], 'signature_invalid')

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING,
                         'App must remain PAYMENT_PENDING after bad signature')
        self.assertIsNone(app.workflow_id, 'Workflow must not be assigned')

    def test_s4_cancelled_order_does_not_advance(self):
        """Cancelling a PaymentOrder must NOT advance the application."""
        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())
        order = self._create_cash_order(app)

        r = self.client.post(f'/api/payments/orders/{order.pk}/cancel/')
        self.assertEqual(r.status_code, 200)

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING,
                         'Cancelling payment must not advance application')

    def test_s4_collect_on_wrong_method_does_not_advance(self):
        """Trying cash-collect on an ONLINE order must be rejected and not advance."""
        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())
        order = self._create_online_order(app, 'order_wrongmethod_001')

        r = self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'receipt_number': 'RCP-WRONG', 'payment_date': str(date.today())},
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['code'], 'wrong_payment_method')

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING)

    # ──────────────────────────────────────────────────────────────────────────
    # SCENARIO 5: Duplicate submissions / callbacks do NOT duplicate
    # ──────────────────────────────────────────────────────────────────────────

    def test_s5_duplicate_cash_collect_returns_409(self):
        """A second collect-cash on an already-PAID order must return 409."""
        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())
        order = self._create_cash_order(app)

        # First collection — succeeds
        r1 = self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'receipt_number': 'RCP-DUP-001', 'payment_date': str(date.today())},
        )
        self.assertEqual(r1.status_code, 200)

        # Second collection — must be rejected
        r2 = self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'receipt_number': 'RCP-DUP-002', 'payment_date': str(date.today())},
        )
        self.assertEqual(r2.status_code, 409)
        self.assertEqual(r2.data['code'], 'already_paid')

        # Only one PaymentTransaction must exist
        self.assertEqual(
            PaymentTransaction.objects.filter(payment_order=order).count(), 1,
            'Duplicate collect must not create a second transaction',
        )

        # Only one SURVEY_MAIL step assignment
        app.refresh_from_db()
        self.assertEqual(app.current_step.code, 'SURVEY_MAIL')

    @patch('payments.views.settings')
    def test_s5_duplicate_razorpay_payment_id_returns_409(self, mock_settings):
        """A second verify with the same razorpay_payment_id must return 409."""
        mock_settings.RAZORPAY_KEY_SECRET = self.FAKE_SECRET

        app1_rtype = make_rtype('E2E_B2', 'E2E Birth 2')
        app2_rtype = make_rtype('E2E_B3', 'E2E Birth 3')

        app1 = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())
        # Manually create second app
        app2 = Application.objects.create(
            service_type=ServiceType.BIRTH, registration_type=app2_rtype,
            district=self.district, ulb=self.ulb, state_code='RJ',
            submitted_by=self.user, date_of_reporting=date.today(),
            status=ApplicationStatus.PAYMENT_PENDING,
        )
        BirthRegistration.objects.create(
            application=app2, date_of_birth=date.today() - timedelta(26), sex='FEMALE',
        )

        order1 = self._create_online_order(app1, 'order_rzp_dup_001')
        order2 = self._create_online_order(app2, 'order_rzp_dup_002')

        payment_id = 'pay_rzp_dup_001'
        sig1 = _sign('order_rzp_dup_001', payment_id, self.FAKE_SECRET)
        sig2 = _sign('order_rzp_dup_002', payment_id, self.FAKE_SECRET)

        # First verify — succeeds
        r1 = self.client.post(
            f'/api/payments/orders/{order1.pk}/verify-payment/',
            {'razorpay_payment_id': payment_id,
             'razorpay_order_id':   'order_rzp_dup_001',
             'razorpay_signature':  sig1},
        )
        self.assertEqual(r1.status_code, 200)

        # Second verify with same payment_id — must be rejected
        r2 = self.client.post(
            f'/api/payments/orders/{order2.pk}/verify-payment/',
            {'razorpay_payment_id': payment_id,
             'razorpay_order_id':   'order_rzp_dup_002',
             'razorpay_signature':  sig2},
        )
        self.assertEqual(r2.status_code, 409)
        self.assertEqual(r2.data['code'], 'duplicate_payment_id')

    def test_s5_duplicate_order_create_returns_same_order(self):
        """POST /orders/ twice for the same PAYMENT_PENDING app returns same PK."""
        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())

        with patch('payments.views._recalculate_fee',
                   return_value=('BD.LATE_30', Decimal('20.00'), 'INR')):
            r1 = self.client.post('/api/payments/orders/',
                                  {'application': app.pk, 'payment_method': 'CASH'})
            r2 = self.client.post('/api/payments/orders/',
                                  {'application': app.pk, 'payment_method': 'CASH'})

        self.assertIn(r1.status_code, [200, 201])
        self.assertEqual(r2.status_code, 200, 'Second create must return existing order')
        self.assertEqual(r1.data['id'], r2.data['id'], 'Both must return same order id')
        self.assertEqual(
            PaymentOrder.objects.filter(application=app).count(), 1,
            'Only one PaymentOrder must exist',
        )

    # ──────────────────────────────────────────────────────────────────────────
    # SCENARIO 6: Unpaid PAYMENT_PENDING does NOT advance
    # ──────────────────────────────────────────────────────────────────────────

    def test_s6_payment_pending_without_paid_order_stays_pending(self):
        """
        An application in PAYMENT_PENDING with no paid order must stay
        in PAYMENT_PENDING and must not get a workflow assignment.
        """
        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING)
        self.assertIsNone(app.workflow_id)
        self.assertIsNone(app.current_step_id)

    def test_s6_confirm_payment_without_paid_order_returns_400(self):
        """confirm-payment with no PAID order must be rejected."""
        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())

        r = self.client.post(
            f'/api/bd-registration/applications/{app.pk}/confirm-payment/'
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn(r.data['code'], ['payment_order_missing', 'payment_not_confirmed'])

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING)

    def test_s6_confirm_payment_with_pending_order_returns_400(self):
        """confirm-payment with a PENDING (not PAID) order must be rejected."""
        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())
        # Create a PENDING order (not yet paid)
        PaymentOrder.objects.create(
            application=app, fee_code='BD.LATE_30', amount=Decimal('20.00'),
            currency='INR', payment_method=PaymentMethod.CASH,
            status=PaymentOrderStatus.PENDING, created_by=self.user,
        )
        r = self.client.post(
            f'/api/bd-registration/applications/{app.pk}/confirm-payment/'
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['code'], 'payment_not_confirmed')

    # ──────────────────────────────────────────────────────────────────────────
    # VIEW URL tests
    # ──────────────────────────────────────────────────────────────────────────

    def test_inbox_view_button_routes_to_review_for_payment_pending(self):
        """
        Inbox View button for PAYMENT_PENDING app must route to
        /applications/<pk>/review/ (HTTP 200).
        """
        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING)

        dc = self.client.__class__()
        dc.force_login(self.user)
        r = dc.get(reverse('application_review', args=[app.pk]))
        self.assertEqual(r.status_code, 200)

    def test_inbox_view_button_routes_to_detail_for_submitted(self):
        """
        Inbox View button for SUBMITTED app must route to
        /applications/<pk>/ (HTTP 200, no redirect to review).
        """
        app = self._submit_birth_app(dob_offset=5, delay_result=_free_delay_result())
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)

        dc = self.client.__class__()
        dc.force_login(self.user)
        r = dc.get(reverse('application_detail', args=[app.pk]))
        self.assertEqual(r.status_code, 200)

    def test_payment_pending_detail_url_redirects_to_review(self):
        """
        Accessing /applications/<pk>/ for a PAYMENT_PENDING app must
        redirect to /applications/<pk>/review/.
        """
        app = self._submit_birth_app(dob_offset=25, delay_result=_paid_delay_result())
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING)

        dc = self.client.__class__()
        dc.force_login(self.user)
        r = dc.get(reverse('application_detail', args=[app.pk]))
        # Expect redirect to review page
        self.assertIn(r.status_code, [301, 302])
        self.assertIn(f'/applications/{app.pk}/review/', r.get('Location', ''))

    def test_unauthenticated_cannot_view_detail(self):
        """Unauthenticated user must be redirected from detail page."""
        app = self._submit_birth_app(dob_offset=5, delay_result=_free_delay_result())

        dc = self.client.__class__()
        r = dc.get(reverse('application_detail', args=[app.pk]))
        self.assertIn(r.status_code, [301, 302])


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW ROUTING & INBOX ISOLATION TESTS  (Step — workflow routing)
# ─────────────────────────────────────────────────────────────────────────────

from unittest.mock import patch


class WorkflowRoutingTests(TestCase):
    """
    Tests for inbox isolation, initial workflow assignment, forwarding to
    Step 2, and same-ward / same-ULB routing.
    """

    def setUp(self):
        self.district, self.ulb, self.zone, self.ward = make_geo()
        self.rtype = make_rtype('WR_B', 'WR Birth')

        # Step 1 officer: DA, same ULB
        self.da_user = make_user('da_inbox')
        self.da_user.role    = UserRole.DA
        self.da_user.ulb_fk  = self.ulb
        self.da_user.ulb_code = self.ulb.code
        self.da_user.save()

        # Step 3 officer: HEALTH_OFFICER, same ULB
        self.ho_user = make_user('ho_inbox')
        self.ho_user.role    = UserRole.HEALTH_OFFICER
        self.ho_user.ulb_fk  = self.ulb
        self.ho_user.ulb_code = self.ulb.code
        self.ho_user.save()

        # Submitter (citizen / DA who filed the form)
        self.submitter = make_user('wr_submitter')

        # Seed workflow with 3 steps
        self.workflow = _seed_workflow_e2e(self.ulb)
        self.step1 = WorkflowStep.objects.get(
            workflow=self.workflow, step_number=1
        )
        self.step2, _ = WorkflowStep.objects.get_or_create(
            workflow=self.workflow,
            step_number=2,
            defaults={'code': 'SCRUTINY', 'name': 'Scrutiny',
                      'role_code': 'DA', 'is_active': True},
        )
        self.step3, _ = WorkflowStep.objects.get_or_create(
            workflow=self.workflow,
            step_number=3,
            defaults={'code': 'FIELD_VERIFY', 'name': 'Field Verify',
                      'role_code': 'HEALTH_OFFICER', 'is_active': True},
        )

        self.client_da = APIClient()
        self.client_da.force_authenticate(user=self.da_user)

        self.client_ho = APIClient()
        self.client_ho.force_authenticate(user=self.ho_user)

    def _submit_app(self):
        """Create a SUBMITTED application with workflow assigned at step 1."""
        app = Application.objects.create(
            service_type=ServiceType.BIRTH,
            registration_type=self.rtype,
            district=self.district,
            ulb=self.ulb,
            state_code='RJ',
            submitted_by=self.submitter,
            date_of_reporting=date.today(),
            status=ApplicationStatus.SUBMITTED,
            submitted_at=timezone.now(),
            workflow=self.workflow,
            current_step=self.step1,
        )
        BirthRegistration.objects.create(
            application=app,
            date_of_birth=date.today() - timedelta(5),
            sex='MALE',
        )
        return app

    # ── Inbox isolation ───────────────────────────────────────────────────────

    def test_da_inbox_shows_step1_application(self):
        """DA user must see the application that is at Step 1 (role: DA)."""
        from django.test import Client as DjangoClient
        app = self._submit_app()
        c = DjangoClient()
        c.force_login(self.da_user)
        r = c.get(reverse('application_inbox'))
        self.assertEqual(r.status_code, 200)
        app_numbers = [a.application_number for a in r.context['applications']]
        self.assertIn(app.application_number, app_numbers,
                      'DA must see the Step-1 application in inbox')

    def test_health_officer_inbox_excludes_step1_application(self):
        """HEALTH_OFFICER must NOT see an application still at Step 1 (role: DA)."""
        from django.test import Client as DjangoClient
        app = self._submit_app()
        c = DjangoClient()
        c.force_login(self.ho_user)
        r = c.get(reverse('application_inbox'))
        self.assertEqual(r.status_code, 200)
        app_numbers = [a.application_number for a in r.context['applications']]
        self.assertNotIn(app.application_number, app_numbers,
                         'HEALTH_OFFICER must not see Step-1 (DA) applications')

    def test_different_ulb_user_excluded_from_inbox(self):
        """A DA from a different ULB must not see this application."""
        from django.test import Client as DjangoClient
        from geography.models import District, ULB

        other_district = District.objects.create(code='OTH2', name='Other District')
        other_ulb = ULB.objects.create(
            code='OULB2', name='Other MC',
            district=other_district, ulb_type='NAGAR_NIGAM',
        )
        other_da = make_user('other_da_ulb')
        other_da.role     = UserRole.DA
        other_da.ulb_fk   = other_ulb
        other_da.ulb_code = other_ulb.code
        other_da.save()

        app = self._submit_app()  # belongs to self.ulb

        c = DjangoClient()
        c.force_login(other_da)
        r = c.get(reverse('application_inbox'))
        self.assertEqual(r.status_code, 200)
        app_numbers = [a.application_number for a in r.context['applications']]
        self.assertNotIn(app.application_number, app_numbers,
                         'DA from different ULB must not see this application')

    # ── Forwarding ────────────────────────────────────────────────────────────

    def test_forward_advances_step_to_step2(self):
        """
        When the DA forwards the application, current_step must advance
        from Step 1 to Step 2.
        """
        app = self._submit_app()
        r = self.client_da.post(
            f'/api/bd-registration/applications/{app.pk}/forward/',
            {'remarks': 'Forwarding to scrutiny'}
        )
        self.assertEqual(r.status_code, 200, r.data)
        app.refresh_from_db()
        self.assertEqual(app.current_step.step_number, 2,
                         'Step should advance to 2 after forwarding')
        self.assertEqual(app.status, ApplicationStatus.UNDER_SCRUTINY)

    def test_forward_removes_application_from_da_inbox(self):
        """
        After forwarding, the application should still appear in DA inbox
        because Step 2 is also role DA — but status is now UNDER_SCRUTINY.
        """
        from django.test import Client as DjangoClient
        app = self._submit_app()
        self.client_da.post(
            f'/api/bd-registration/applications/{app.pk}/forward/', {}
        )
        app.refresh_from_db()
        # After forward: status = UNDER_SCRUTINY, step = 2 (role: DA)
        # DA still sees it (step2 is also DA role)
        c = DjangoClient()
        c.force_login(self.da_user)
        r = c.get(reverse('application_inbox'))
        app_numbers = [a.application_number for a in r.context['applications']]
        self.assertIn(app.application_number, app_numbers)

    def test_forward_to_step3_appears_in_health_officer_inbox(self):
        """
        After two forwards (Step1→Step2→Step3), the application must
        appear in the HEALTH_OFFICER's inbox.
        """
        from django.test import Client as DjangoClient
        app = self._submit_app()

        # First forward: Step 1 → Step 2
        self.client_da.post(
            f'/api/bd-registration/applications/{app.pk}/forward/', {}
        )
        app.refresh_from_db()
        self.assertEqual(app.current_step.step_number, 2)

        # Second forward: Step 2 → Step 3
        self.client_da.post(
            f'/api/bd-registration/applications/{app.pk}/forward/', {}
        )
        app.refresh_from_db()
        self.assertEqual(app.current_step.step_number, 3,
                         'Step should advance to 3 after second forward')

        # HEALTH_OFFICER now sees it
        c_ho = DjangoClient()
        c_ho.force_login(self.ho_user)
        r = c_ho.get(reverse('application_inbox'))
        app_numbers = [a.application_number for a in r.context['applications']]
        self.assertIn(app.application_number, app_numbers,
                      'HEALTH_OFFICER must see Step-3 application in inbox')

        # DA must no longer see it (step 3 role_code = HEALTH_OFFICER ≠ DA)
        c_da = DjangoClient()
        c_da.force_login(self.da_user)
        r_da = c_da.get(reverse('application_inbox'))
        da_apps = [a.application_number for a in r_da.context['applications']]
        self.assertNotIn(app.application_number, da_apps,
                         'DA must not see Step-3 application')

    # ── No duplicate assignment ───────────────────────────────────────────────

    def test_advance_workflow_is_idempotent_at_last_step(self):
        """Calling advance_workflow at the last step must not error or change step."""
        from bd_registration.workflow_service import advance_workflow
        app = self._submit_app()
        app.current_step = self.step3
        app.save(update_fields=['current_step'])

        old_step, new_step = advance_workflow(app, self.da_user)
        self.assertEqual(old_step.pk, self.step3.pk)
        self.assertIsNone(new_step, 'No next step at final step')
        app.refresh_from_db()
        self.assertEqual(app.current_step.pk, self.step3.pk,
                         'Step must not change at last step')
