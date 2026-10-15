"""
payments/tests.py
==================
Tests for both cash and online (Razorpay) payment flows.

Coverage
--------
Cash:
  - Successful cash collection advances application to SUBMITTED + assigns workflow
  - Duplicate collect-cash returns 409
  - Collect on wrong-status order returns 400
  - Collect on wrong-method (ONLINE) order returns 400

Online (Razorpay):
  - Create order returns razorpay_key_id in response
  - Valid signature verification advances application
  - Invalid signature records FAILED transaction, returns 400
  - Duplicate payment_id returns 409
  - Order_id mismatch returns 400

Guards:
  - Cannot create order for non-PAYMENT_PENDING application
  - Zero-fee application cannot create a payment order
  - Idempotency: POST /orders/ twice returns same PENDING order

Workflow:
  - After cash payment, application has workflow + step 1 assigned
  - PAYMENT_PENDING application has no workflow before payment
"""

import hashlib
import hmac
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from bd_master.models import RegistrationType
from bd_registration.models import Application, ApplicationStatus, BirthRegistration, ServiceType
from bd_registration.tests import make_geo, make_rtype, make_user
from geography.models import District, ULB, Zone, Ward
from workflow_master.models import Workflow, WorkflowStep
from users.models import ApplicationCode

from .models import (
    PaymentMethod, PaymentOrder, PaymentOrderStatus,
    PaymentTransaction, PaymentTransactionStatus,
)

User = get_user_model()


# ─── Test helpers ─────────────────────────────────────────────────────────────

def _seed_workflow(ulb):
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


def _make_payment_pending_app(user, district, ulb, rtype, dob_offset=25):
    """Create a DRAFT Application + BirthRegistration, then set PAYMENT_PENDING."""
    app = Application.objects.create(
        service_type=ServiceType.BIRTH,
        registration_type=rtype,
        district=district,
        ulb=ulb,
        state_code='RJ',
        submitted_by=user,
        date_of_reporting=date.today(),
    )
    BirthRegistration.objects.create(
        application=app,
        date_of_birth=date.today() - timedelta(dob_offset),
        sex='MALE',
    )
    app.status = ApplicationStatus.PAYMENT_PENDING
    app.save(update_fields=['status'])
    return app


def _make_delay_result_with_fee(fee=Decimal('20.00'), category='DELAYED_30_DAYS'):
    from bd_registration.services import DelayResult
    return DelayResult(
        delay_days=25, delay_category=category,
        is_normal=False, fee_code='BD.LATE_30',
        applicable_fee=fee, currency='INR',
        requires_authority=False, authority_code=None,
        authority_name=None, authority_notes='',
        requires_form_14=False, requires_affidavit=False,
        requires_permission_order=False,
        required_document_codes=[], required_document_names=[],
        rule_reference='', rule_code='', error='',
    )


def _sign(order_id, payment_id, secret='test_secret'):
    msg = f'{order_id}|{payment_id}'.encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


# ─── Cash Payment Tests ───────────────────────────────────────────────────────

class CashPaymentTests(TestCase):

    def setUp(self):
        self.district, self.ulb, _, _ = make_geo()
        self.rtype  = make_rtype('CP_B', 'CP Birth')
        self.user   = make_user('cp_user')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        _seed_workflow(self.ulb)

    def _pending_app(self):
        return _make_payment_pending_app(self.user, self.district, self.ulb, self.rtype)

    def _create_cash_order(self, app):
        """Create a CASH PaymentOrder directly (bypasses fee calc)."""
        return PaymentOrder.objects.create(
            application=app,
            fee_code='BD.LATE_30',
            amount=Decimal('20.00'),
            currency='INR',
            payment_method=PaymentMethod.CASH,
            status=PaymentOrderStatus.PENDING,
            created_by=self.user,
        )

    # ── success ───────────────────────────────────────────────────────────────

    def test_cash_collect_succeeds(self):
        app   = self._pending_app()
        order = self._create_cash_order(app)

        r = self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'receipt_number': 'RCP-001', 'payment_date': str(date.today())},
        )
        self.assertEqual(r.status_code, 200, r.data)
        order.refresh_from_db()
        self.assertEqual(order.status, PaymentOrderStatus.PAID)

    def test_cash_collect_creates_captured_transaction(self):
        app   = self._pending_app()
        order = self._create_cash_order(app)
        self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'receipt_number': 'RCP-002', 'payment_date': str(date.today())},
        )
        txn = PaymentTransaction.objects.get(payment_order=order)
        self.assertEqual(txn.status, PaymentTransactionStatus.CAPTURED)
        self.assertEqual(txn.receipt_number, 'RCP-002')
        self.assertEqual(txn.collected_by, self.user)
        self.assertEqual(txn.amount, Decimal('20.00'))

    def test_cash_collect_advances_application_to_submitted(self):
        app   = self._pending_app()
        order = self._create_cash_order(app)
        self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'receipt_number': 'RCP-003', 'payment_date': str(date.today())},
        )
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)
        self.assertIsNotNone(app.submitted_at)

    def test_cash_collect_assigns_workflow(self):
        app   = self._pending_app()
        order = self._create_cash_order(app)
        self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'receipt_number': 'RCP-004', 'payment_date': str(date.today())},
        )
        app.refresh_from_db()
        self.assertIsNotNone(app.workflow_id)
        self.assertEqual(app.current_step.code, 'SURVEY_MAIL')

    # ── duplicate / idempotency ────────────────────────────────────────────────

    def test_cash_collect_duplicate_returns_409(self):
        app   = self._pending_app()
        order = self._create_cash_order(app)
        self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'receipt_number': 'RCP-005', 'payment_date': str(date.today())},
        )
        r = self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'receipt_number': 'RCP-006', 'payment_date': str(date.today())},
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['code'], 'already_paid')

    # ── wrong state / method ───────────────────────────────────────────────────

    def test_collect_on_cancelled_order_returns_400(self):
        app   = self._pending_app()
        order = self._create_cash_order(app)
        order.status = PaymentOrderStatus.CANCELLED
        order.save(update_fields=['status'])
        r = self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'receipt_number': 'RCP-007', 'payment_date': str(date.today())},
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['code'], 'invalid_order_status')

    def test_collect_on_online_order_returns_400(self):
        app   = self._pending_app()
        order = PaymentOrder.objects.create(
            application=app, fee_code='BD.LATE_30', amount=Decimal('20.00'),
            currency='INR', payment_method=PaymentMethod.ONLINE,
            status=PaymentOrderStatus.PENDING, created_by=self.user,
            razorpay_order_id='order_test_123',
        )
        r = self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'receipt_number': 'RCP-008', 'payment_date': str(date.today())},
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['code'], 'wrong_payment_method')

    def test_collect_requires_receipt_number(self):
        app   = self._pending_app()
        order = self._create_cash_order(app)
        r = self.client.post(
            f'/api/payments/orders/{order.pk}/collect-cash/',
            {'payment_date': str(date.today())},
        )
        self.assertEqual(r.status_code, 400)


# ─── Online / Razorpay Payment Tests ─────────────────────────────────────────

class RazorpayPaymentTests(TestCase):

    FAKE_KEY_ID     = 'rzp_test_FAKE_KEY_ID'
    FAKE_KEY_SECRET = 'test_secret'

    def setUp(self):
        self.district, self.ulb, _, _ = make_geo()
        self.rtype  = make_rtype('RP_B', 'RP Birth')
        self.user   = make_user('rp_user')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        _seed_workflow(self.ulb)

    def _pending_app(self):
        return _make_payment_pending_app(self.user, self.district, self.ulb, self.rtype)

    def _create_online_order(self, app, rzp_order_id='order_fake_001'):
        return PaymentOrder.objects.create(
            application=app,
            fee_code='BD.LATE_30', amount=Decimal('20.00'), currency='INR',
            payment_method=PaymentMethod.ONLINE,
            status=PaymentOrderStatus.PENDING,
            razorpay_order_id=rzp_order_id,
            created_by=self.user,
        )

    # ── create order with Razorpay SDK mock ───────────────────────────────────

    @patch('payments.views.settings')
    def test_create_online_order(self, mock_settings):
        mock_settings.RAZORPAY_KEY_ID     = self.FAKE_KEY_ID
        mock_settings.RAZORPAY_KEY_SECRET = self.FAKE_KEY_SECRET
        mock_settings.RAZORPAY_CURRENCY   = 'INR'

        mock_rzp_order = {'id': 'order_mocked_001', 'amount': 2000, 'currency': 'INR'}

        with patch('builtins.__import__', side_effect=lambda name, *a, **kw:
                   __import__(name, *a, **kw)) as _:
            pass  # replaced below

        app = self._pending_app()

        # Patch razorpay at the package level — views imports it locally
        import razorpay as _rzp_module
        mock_client = MagicMock()
        mock_client.order.create.return_value = mock_rzp_order
        with patch.object(_rzp_module, 'Client', return_value=mock_client):
            with patch('payments.views.DelayCalculationService.calculate') as mock_calc:
                mock_calc.return_value = _make_delay_result_with_fee()
                r = self.client.post('/api/payments/orders/', {
                    'application': app.pk,
                    'payment_method': 'ONLINE',
                })

        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['razorpay_order_id'], 'order_mocked_001')
        self.assertIn('razorpay_key_id', r.data)

    # ── verify payment — valid signature ──────────────────────────────────────

    @patch('payments.views.settings')
    def test_verify_payment_valid_signature(self, mock_settings):
        mock_settings.RAZORPAY_KEY_SECRET = self.FAKE_KEY_SECRET

        app   = self._pending_app()
        order = self._create_online_order(app, 'order_valid_001')
        payment_id = 'pay_valid_001'
        sig = _sign('order_valid_001', payment_id, self.FAKE_KEY_SECRET)

        r = self.client.post(f'/api/payments/orders/{order.pk}/verify-payment/', {
            'razorpay_payment_id': payment_id,
            'razorpay_order_id':   'order_valid_001',
            'razorpay_signature':  sig,
        })

        self.assertEqual(r.status_code, 200, r.data)
        order.refresh_from_db()
        self.assertEqual(order.status, PaymentOrderStatus.PAID)
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)
        self.assertIsNotNone(app.workflow_id)

    # ── verify payment — invalid signature ────────────────────────────────────

    @patch('payments.views.settings')
    def test_verify_payment_invalid_signature_returns_400(self, mock_settings):
        mock_settings.RAZORPAY_KEY_SECRET = self.FAKE_KEY_SECRET

        app   = self._pending_app()
        order = self._create_online_order(app, 'order_bad_sig_001')

        r = self.client.post(f'/api/payments/orders/{order.pk}/verify-payment/', {
            'razorpay_payment_id': 'pay_bad_001',
            'razorpay_order_id':   'order_bad_sig_001',
            'razorpay_signature':  'totally_wrong_signature',
        })

        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['code'], 'signature_invalid')

        # FAILED transaction recorded
        txn = PaymentTransaction.objects.get(payment_order=order)
        self.assertEqual(txn.status, PaymentTransactionStatus.FAILED)
        self.assertEqual(txn.razorpay_error_code, 'SIGNATURE_MISMATCH')

        # Application must NOT advance
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.PAYMENT_PENDING)

    # ── duplicate payment_id ──────────────────────────────────────────────────

    @patch('payments.views.settings')
    def test_duplicate_payment_id_returns_409(self, mock_settings):
        mock_settings.RAZORPAY_KEY_SECRET = self.FAKE_KEY_SECRET

        app1  = self._pending_app()
        app2  = _make_payment_pending_app(
            self.user, self.district, self.ulb,
            make_rtype('RP_B2', 'RP Birth2'), dob_offset=26,
        )
        order1 = self._create_online_order(app1, 'order_dup_001')
        order2 = self._create_online_order(app2, 'order_dup_002')

        payment_id = 'pay_dup_001'
        sig1 = _sign('order_dup_001', payment_id, self.FAKE_KEY_SECRET)

        # First verify — succeeds
        self.client.post(f'/api/payments/orders/{order1.pk}/verify-payment/', {
            'razorpay_payment_id': payment_id,
            'razorpay_order_id':   'order_dup_001',
            'razorpay_signature':  sig1,
        })

        # Second verify with same payment_id — must be rejected
        sig2 = _sign('order_dup_002', payment_id, self.FAKE_KEY_SECRET)
        r = self.client.post(f'/api/payments/orders/{order2.pk}/verify-payment/', {
            'razorpay_payment_id': payment_id,
            'razorpay_order_id':   'order_dup_002',
            'razorpay_signature':  sig2,
        })
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['code'], 'duplicate_payment_id')

    # ── order_id mismatch ─────────────────────────────────────────────────────

    @patch('payments.views.settings')
    def test_order_id_mismatch_returns_400(self, mock_settings):
        mock_settings.RAZORPAY_KEY_SECRET = self.FAKE_KEY_SECRET

        app   = self._pending_app()
        order = self._create_online_order(app, 'order_real_001')

        r = self.client.post(f'/api/payments/orders/{order.pk}/verify-payment/', {
            'razorpay_payment_id': 'pay_mismatch_001',
            'razorpay_order_id':   'order_DIFFERENT_001',
            'razorpay_signature':  'any_sig',
        })
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['code'], 'order_id_mismatch')


# ─── Guard Tests ──────────────────────────────────────────────────────────────

class PaymentGuardTests(TestCase):

    def setUp(self):
        self.district, self.ulb, _, _ = make_geo()
        self.rtype  = make_rtype('PG_B', 'PG Birth')
        self.user   = make_user('pg_user')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _draft_app(self):
        app = Application.objects.create(
            service_type=ServiceType.BIRTH, registration_type=self.rtype,
            district=self.district, ulb=self.ulb, state_code='RJ',
            submitted_by=self.user, date_of_reporting=date.today(),
        )
        BirthRegistration.objects.create(
            application=app, date_of_birth=date.today() - timedelta(5), sex='MALE',
        )
        return app

    def test_create_order_for_non_payment_pending_app_returns_400(self):
        app = self._draft_app()  # status is DRAFT
        r = self.client.post('/api/payments/orders/', {
            'application': app.pk, 'payment_method': 'CASH',
        })
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['code'], 'invalid_application_status')

    def test_create_order_for_zero_fee_returns_400(self):
        app = self._draft_app()
        app.status = ApplicationStatus.PAYMENT_PENDING
        app.save(update_fields=['status'])

        with patch('payments.views._recalculate_fee') as mock_fee:
            mock_fee.return_value = ('', Decimal('0.00'), 'INR')
            r = self.client.post('/api/payments/orders/', {
                'application': app.pk, 'payment_method': 'CASH',
            })

        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['code'], 'zero_fee')

    def test_idempotent_create_returns_existing_pending_order(self):
        app = self._draft_app()
        app.status = ApplicationStatus.PAYMENT_PENDING
        app.save(update_fields=['status'])

        existing = PaymentOrder.objects.create(
            application=app, fee_code='BD.LATE_30', amount=Decimal('20.00'),
            currency='INR', payment_method=PaymentMethod.CASH,
            status=PaymentOrderStatus.PENDING, created_by=self.user,
        )

        with patch('payments.views._recalculate_fee') as mock_fee:
            mock_fee.return_value = ('BD.LATE_30', Decimal('20.00'), 'INR')
            r = self.client.post('/api/payments/orders/', {
                'application': app.pk, 'payment_method': 'CASH',
            })

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['id'], existing.pk)

    def test_unauthenticated_cannot_create_order(self):
        app = self._draft_app()
        r = APIClient().post('/api/payments/orders/', {
            'application': app.pk, 'payment_method': 'CASH',
        })
        self.assertEqual(r.status_code, 401)

    def test_cancel_pending_order_succeeds(self):
        app = self._draft_app()
        app.status = ApplicationStatus.PAYMENT_PENDING
        app.save(update_fields=['status'])
        order = PaymentOrder.objects.create(
            application=app, fee_code='BD.LATE_30', amount=Decimal('20.00'),
            currency='INR', payment_method=PaymentMethod.CASH,
            status=PaymentOrderStatus.PENDING, created_by=self.user,
        )
        r = self.client.post(f'/api/payments/orders/{order.pk}/cancel/')
        self.assertEqual(r.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, PaymentOrderStatus.CANCELLED)

    def test_cancel_paid_order_returns_409(self):
        app = self._draft_app()
        app.status = ApplicationStatus.SUBMITTED
        app.save(update_fields=['status'])
        order = PaymentOrder.objects.create(
            application=app, fee_code='BD.LATE_30', amount=Decimal('20.00'),
            currency='INR', payment_method=PaymentMethod.CASH,
            status=PaymentOrderStatus.PAID, created_by=self.user,
        )
        r = self.client.post(f'/api/payments/orders/{order.pk}/cancel/')
        self.assertEqual(r.status_code, 409)
