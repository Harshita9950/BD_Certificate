"""
payments/urls.py
=================
Mounted at: /api/payments/

Routes
------
GET    /api/payments/orders/                          list all orders
POST   /api/payments/orders/                          create order
GET    /api/payments/orders/<pk>/                     retrieve order + transactions
POST   /api/payments/orders/<pk>/collect-cash/        record cash receipt
POST   /api/payments/orders/<pk>/verify-payment/      verify Razorpay signature
POST   /api/payments/orders/<pk>/cancel/              cancel pending order
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PaymentOrderViewSet

app_name = 'payments'

router = DefaultRouter()
router.register('orders', PaymentOrderViewSet, basename='payment-order')

urlpatterns = [
    path('', include(router.urls)),
]
