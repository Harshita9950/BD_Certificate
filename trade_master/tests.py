from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from .models import TradeCategory, Trade, SubTrade, ULBTradeConfig
from users.models import User, UserRole
from geography.models import District, ULB, ULBType


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_category(code='CAT01', name='Manufacturing'):
    return TradeCategory.objects.create(code=code, name=name)


def make_trade(category, code='T01', name='Bakery'):
    return Trade.objects.create(category=category, code=code, name=name)


def make_subtrade(trade, code='ST01', name='Bread'):
    return SubTrade.objects.create(trade=trade, code=code, name=name)


def make_ulb():
    d = District.objects.create(code='D01', name='District 1')
    return ULB.objects.create(district=d, code='U01', name='ULB 1', ulb_type=ULBType.NAGAR_NIGAM)


def make_user(email='user@test.com'):
    return User.objects.create_user(
        email=email, password='Pass123!',
        first_name='Test', last_name='User',
        role=UserRole.OFFICER,
    )


# ── TradeCategory ─────────────────────────────────────────────────────────────

class TradeCategoryTest(TestCase):

    def test_create(self):
        c = make_category()
        self.assertEqual(c.code, 'CAT01')
        self.assertTrue(c.is_active)
        self.assertIsNotNone(c.created_at)

    def test_str(self):
        c = make_category()
        self.assertIn('CAT01', str(c))

    def test_code_unique(self):
        make_category('CAT01')
        with self.assertRaises(IntegrityError):
            make_category('CAT01', name='Duplicate')

    def test_inactive(self):
        c = TradeCategory.objects.create(code='CAT02', name='Old', is_active=False)
        self.assertFalse(c.is_active)

    def test_protect_on_delete_when_trade_exists(self):
        c = make_category()
        make_trade(c)
        with self.assertRaises(ProtectedError):
            c.delete()


# ── Trade ─────────────────────────────────────────────────────────────────────

class TradeTest(TestCase):

    def setUp(self):
        self.category = make_category()

    def test_create(self):
        t = make_trade(self.category)
        self.assertEqual(t.category, self.category)
        self.assertTrue(t.is_active)

    def test_str(self):
        t = make_trade(self.category)
        self.assertIn('T01', str(t))

    def test_code_unique(self):
        make_trade(self.category, 'T01')
        with self.assertRaises(IntegrityError):
            make_trade(self.category, 'T01', name='Dup')

    def test_same_code_different_category_not_allowed(self):
        c2 = make_category('CAT02', 'Services')
        make_trade(self.category, 'T01')
        # Trade.code is globally unique (not scoped to category)
        with self.assertRaises(IntegrityError):
            make_trade(c2, 'T01', name='Another')

    def test_multiple_trades_per_category(self):
        make_trade(self.category, 'T01', 'Bakery')
        make_trade(self.category, 'T02', 'Dairy')
        self.assertEqual(self.category.trades.count(), 2)

    def test_inactive(self):
        t = Trade.objects.create(category=self.category, code='T99', name='Old', is_active=False)
        self.assertFalse(t.is_active)

    def test_protect_on_delete_when_subtrade_exists(self):
        t = make_trade(self.category)
        make_subtrade(t)
        with self.assertRaises(ProtectedError):
            t.delete()

    def test_category_relation(self):
        t = make_trade(self.category)
        self.assertEqual(t.category.code, 'CAT01')


# ── SubTrade ──────────────────────────────────────────────────────────────────

class SubTradeTest(TestCase):

    def setUp(self):
        self.category = make_category()
        self.trade    = make_trade(self.category)

    def test_create(self):
        s = make_subtrade(self.trade)
        self.assertEqual(s.trade, self.trade)
        self.assertTrue(s.is_active)

    def test_str(self):
        s = make_subtrade(self.trade)
        self.assertIn('ST01', str(s))
        self.assertIn(self.trade.code, str(s))

    def test_code_unique_within_trade(self):
        make_subtrade(self.trade, 'ST01')
        with self.assertRaises(IntegrityError):
            make_subtrade(self.trade, 'ST01', name='Dup')

    def test_same_code_different_trade_allowed(self):
        t2 = make_trade(self.category, 'T02', 'Dairy')
        make_subtrade(self.trade, 'ST01')
        s2 = make_subtrade(t2, 'ST01', name='Sub in T02')
        self.assertEqual(s2.code, 'ST01')
        self.assertEqual(s2.trade, t2)

    def test_multiple_subtrades_per_trade(self):
        make_subtrade(self.trade, 'ST01', 'Bread')
        make_subtrade(self.trade, 'ST02', 'Cake')
        self.assertEqual(self.trade.sub_trades.count(), 2)

    def test_inactive(self):
        s = SubTrade.objects.create(trade=self.trade, code='ST99', name='Old', is_active=False)
        self.assertFalse(s.is_active)

    def test_chain_to_category(self):
        s = make_subtrade(self.trade)
        self.assertEqual(s.trade.category, self.category)


# ── ULBTradeConfig ────────────────────────────────────────────────────────────

class ULBTradeConfigTest(TestCase):

    def setUp(self):
        self.ulb      = make_ulb()
        self.category = make_category()
        self.trade    = make_trade(self.category)

    def test_create(self):
        cfg = ULBTradeConfig.objects.create(ulb=self.ulb, trade=self.trade)
        self.assertTrue(cfg.is_enabled)

    def test_str(self):
        cfg = ULBTradeConfig.objects.create(ulb=self.ulb, trade=self.trade)
        self.assertIn(self.ulb.code, str(cfg))
        self.assertIn(self.trade.code, str(cfg))

    def test_unique_per_ulb_trade(self):
        ULBTradeConfig.objects.create(ulb=self.ulb, trade=self.trade)
        with self.assertRaises(IntegrityError):
            ULBTradeConfig.objects.create(ulb=self.ulb, trade=self.trade)

    def test_disabled_config(self):
        cfg = ULBTradeConfig.objects.create(ulb=self.ulb, trade=self.trade, is_enabled=False)
        self.assertFalse(cfg.is_enabled)

    def test_different_ulbs_can_have_same_trade(self):
        d2   = District.objects.create(code='D02', name='District 2')
        ulb2 = ULB.objects.create(district=d2, code='U02', name='ULB 2', ulb_type=ULBType.NAGAR_PARISHAD)
        ULBTradeConfig.objects.create(ulb=self.ulb,  trade=self.trade)
        ULBTradeConfig.objects.create(ulb=ulb2, trade=self.trade)
        self.assertEqual(ULBTradeConfig.objects.filter(trade=self.trade).count(), 2)

    def test_ulb_isolation_via_filter(self):
        d2   = District.objects.create(code='D02', name='District 2')
        ulb2 = ULB.objects.create(district=d2, code='U02', name='ULB 2', ulb_type=ULBType.NAGAR_PARISHAD)
        t2   = make_trade(self.category, 'T02', 'Dairy')
        ULBTradeConfig.objects.create(ulb=self.ulb,  trade=self.trade)
        ULBTradeConfig.objects.create(ulb=ulb2, trade=t2)
        self.assertEqual(ULBTradeConfig.objects.filter(ulb=self.ulb).count(), 1)
        self.assertEqual(ULBTradeConfig.objects.filter(ulb=ulb2).count(), 1)

    def test_protect_trade_on_delete_when_config_exists(self):
        ULBTradeConfig.objects.create(ulb=self.ulb, trade=self.trade)
        with self.assertRaises(ProtectedError):
            self.trade.delete()

    def test_protect_ulb_on_delete_when_config_exists(self):
        ULBTradeConfig.objects.create(ulb=self.ulb, trade=self.trade)
        with self.assertRaises(ProtectedError):
            self.ulb.delete()


# ── API ───────────────────────────────────────────────────────────────────────

class TradeMasterAPITest(TestCase):

    def setUp(self):
        self.client   = APIClient()
        self.user     = make_user()
        self.category = make_category('CAT01', 'Manufacturing')
        self.trade    = make_trade(self.category, 'T01', 'Bakery')
        self.subtrade = make_subtrade(self.trade, 'ST01', 'Bread')
        TradeCategory.objects.create(code='CAT99', name='Inactive Cat', is_active=False)
        Trade.objects.create(category=self.category, code='T99', name='Inactive Trade', is_active=False)

    def test_category_list_requires_auth(self):
        r = self.client.get('/api/trade-master/categories/')
        self.assertIn(r.status_code, [401, 403])

    def test_category_list(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get('/api/trade-master/categories/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        codes = [i['code'] for i in r.data['results']]
        self.assertIn('CAT01', codes)
        self.assertNotIn('CAT99', codes)

    def test_category_retrieve(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get(f'/api/trade-master/categories/{self.category.pk}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['code'], 'CAT01')

    def test_category_read_only(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.post('/api/trade-master/categories/', {'code': 'X', 'name': 'X'})
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_trade_list_requires_auth(self):
        r = self.client.get('/api/trade-master/trades/')
        self.assertIn(r.status_code, [401, 403])

    def test_trade_list(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get('/api/trade-master/trades/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        codes = [i['code'] for i in r.data['results']]
        self.assertIn('T01', codes)
        self.assertNotIn('T99', codes)

    def test_trade_filter_by_category(self):
        c2 = make_category('CAT02', 'Services')
        make_trade(c2, 'T02', 'Consulting')
        self.client.force_authenticate(user=self.user)
        r = self.client.get(f'/api/trade-master/trades/?category={self.category.pk}')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        codes = [i['code'] for i in r.data['results']]
        self.assertIn('T01', codes)
        self.assertNotIn('T02', codes)

    def test_trade_retrieve(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get(f'/api/trade-master/trades/{self.trade.pk}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['category_name'], 'Manufacturing')

    def test_subtrade_list_requires_auth(self):
        r = self.client.get('/api/trade-master/sub-trades/')
        self.assertIn(r.status_code, [401, 403])

    def test_subtrade_list(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get('/api/trade-master/sub-trades/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        codes = [i['code'] for i in r.data['results']]
        self.assertIn('ST01', codes)

    def test_subtrade_filter_by_trade(self):
        t2  = make_trade(self.category, 'T02', 'Dairy')
        st2 = make_subtrade(t2, 'ST02', 'Milk')
        self.client.force_authenticate(user=self.user)
        r = self.client.get(f'/api/trade-master/sub-trades/?trade={self.trade.pk}')
        codes = [i['code'] for i in r.data['results']]
        self.assertIn('ST01', codes)
        self.assertNotIn('ST02', codes)

    def test_subtrade_retrieve(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get(f'/api/trade-master/sub-trades/{self.subtrade.pk}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['trade_name'], 'Bakery')
        self.assertEqual(r.data['category_name'], 'Manufacturing')

    def test_subtrade_read_only(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.post('/api/trade-master/sub-trades/', {'code': 'X', 'name': 'X'})
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_search_trade_by_name(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get('/api/trade-master/trades/?search=Bakery')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreater(len(r.data['results']), 0)
        self.assertEqual(r.data['results'][0]['code'], 'T01')

    def test_ulb_config_list_requires_auth(self):
        r = self.client.get('/api/trade-master/ulb-configs/')
        self.assertIn(r.status_code, [401, 403])

    def test_ulb_config_filter_by_ulb(self):
        ulb = make_ulb()
        ULBTradeConfig.objects.create(ulb=ulb, trade=self.trade)
        self.client.force_authenticate(user=self.user)
        r = self.client.get(f'/api/trade-master/ulb-configs/?ulb={ulb.pk}')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data['results']), 1)
