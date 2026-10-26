from django.urls import path
from .views import (
    CertificateSearchView,
    CertificateEditView,
    UpdationInboxView,
    UpdationSentboxView,
    UpdationRequestDetailView,
    UpdationForwardView,
    UpdationApproveView,
    UpdationRejectView,
    UpdationRegisterReportView,
    UpdationPendingReportView,
    UpdationDecisionReportView,
    UpdationFieldChangeReportView,
    UpdationSummaryReportView,
)

app_name = 'certificate_updation'

urlpatterns = [
    path('search/',                               CertificateSearchView.as_view(),          name='certificate_search'),
    path('<int:app_pk>/edit/',                    CertificateEditView.as_view(),             name='certificate_edit'),
    path('request/<int:pk>/',                     UpdationRequestDetailView.as_view(),       name='updation_request_detail'),
    path('request/<int:pk>/forward/',             UpdationForwardView.as_view(),             name='updation_forward'),
    path('request/<int:pk>/approve/',             UpdationApproveView.as_view(),             name='updation_approve'),
    path('request/<int:pk>/reject/',              UpdationRejectView.as_view(),              name='updation_reject'),
    # Reports
    path('reports/register/',                     UpdationRegisterReportView.as_view(),      name='report_updation_register'),
    path('reports/pending/',                      UpdationPendingReportView.as_view(),       name='report_updation_pending'),
    path('reports/decisions/',                    UpdationDecisionReportView.as_view(),      name='report_updation_decisions'),
    path('reports/field-changes/',                UpdationFieldChangeReportView.as_view(),   name='report_updation_field_changes'),
    path('reports/summary/',                      UpdationSummaryReportView.as_view(),       name='report_updation_summary'),
]
