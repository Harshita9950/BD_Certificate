"""
certificate_updation/views.py
================================
Views for the Certificate Updation module.
"""

import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from bd_registration.models import Application, ApplicationStatus, BirthRegistration, DeathRegistration

from .models import CertificateUpdationRequest, UpdationStatus, UpdationStatusHistory, UpdationRemark
from .workflow_service import (
    advance_updation_workflow,
    assign_updation_workflow,
    is_last_updation_step,
)

logger = logging.getLogger(__name__)


def _record_upd_transition(req, old_status, new_status, action_code, user, remarks=''):
    """Write an immutable audit record for an updation status transition."""
    UpdationStatusHistory.objects.create(
        request=req,
        old_status=old_status,
        new_status=new_status,
        action=action_code,
        changed_by=user,
        changed_at=timezone.now(),
        remarks=remarks,
    )


def _save_upd_remark(req, action_code, user, remark):
    """Save a per-action remark with step/role context to UpdationRemark."""
    if not remark:
        return
    step_name = ''
    step_role = ''
    try:
        if req.current_step_id:
            step_name = req.current_step.name
            step_role = req.current_step.role_code
    except Exception:
        pass
    UpdationRemark.objects.create(
        request=req,
        action=action_code,
        step_name=step_name,
        step_role=step_role,
        officer=user,
        remark=remark,
    )


def _get_master_context():
    """Shared context for updation forms (registration types etc.)."""
    from bd_master.models import RegistrationType
    return {
        'registration_types': RegistrationType.objects.filter(is_active=True).order_by('name'),
    }


# ─── 1. Search Page ───────────────────────────────────────────────────────────

class CertificateSearchView(LoginRequiredMixin, View):
    """
    GET/POST /certificate-updation/search/

    Search for a registered application by Application Number or
    Certificate (Registration) Number. Only REGISTERED applications qualify.
    """
    login_url = '/login/'

    def get(self, request):
        return render(request, 'Authority/updation/certificate_search.html', {
            'results': None,
            'query': '',
            'error': '',
        })

    def post(self, request):
        query = request.POST.get('query', '').strip()
        error = ''
        results = []

        if not query:
            error = 'Please enter an Application Number or Certificate Number.'
        else:
            # Search by application_number OR registration_number on child records
            apps = Application.objects.filter(
                status=ApplicationStatus.REGISTERED,
            ).select_related(
                'registration_type', 'district', 'ulb',
                'birth_registration', 'death_registration',
            ).filter(
                application_number__icontains=query
            )

            # Also search by registration_number on child records
            birth_matches = Application.objects.filter(
                status=ApplicationStatus.REGISTERED,
                birth_registration__registration_number__icontains=query,
            ).select_related('registration_type', 'district', 'ulb', 'birth_registration')

            death_matches = Application.objects.filter(
                status=ApplicationStatus.REGISTERED,
                death_registration__registration_number__icontains=query,
            ).select_related('registration_type', 'district', 'ulb', 'death_registration')

            # Union and deduplicate by pk
            all_pks = set()
            combined = []
            for qs in [apps, birth_matches, death_matches]:
                for app in qs:
                    if app.pk not in all_pks:
                        all_pks.add(app.pk)
                        combined.append(app)

            results = combined
            if not results:
                error = f'No registered certificate found for "{query}".'

        return render(request, 'Authority/updation/certificate_search.html', {
            'results': results,
            'query': query,
            'error': error,
        })


# ─── 2. Edit / Request Form ───────────────────────────────────────────────────

class CertificateEditView(LoginRequiredMixin, View):
    """
    GET  /certificate-updation/<app_pk>/edit/  — pre-filled editable form
    POST /certificate-updation/<app_pk>/edit/  — submit updation request
    """
    login_url = '/login/'

    def get(self, request, app_pk):
        app = get_object_or_404(
            Application.objects.select_related(
                'registration_type', 'district', 'ulb',
                'birth_registration__ward',
                'death_registration__ward',
            ),
            pk=app_pk,
            status=ApplicationStatus.REGISTERED,
        )
        ctx = _get_master_context()
        ctx['app'] = app
        ctx['birth'] = getattr(app, 'birth_registration', None)
        ctx['death'] = getattr(app, 'death_registration', None)
        # Check for pending updation requests
        pending = CertificateUpdationRequest.objects.filter(
            original_application=app,
            status__in=(UpdationStatus.SUBMITTED, UpdationStatus.UNDER_SCRUTINY, UpdationStatus.UNDER_PROCESS),
        ).first()
        ctx['pending_request'] = pending
        return render(request, 'Authority/updation/certificate_edit.html', ctx)

    def post(self, request, app_pk):
        app = get_object_or_404(
            Application.objects.select_related(
                'registration_type', 'birth_registration', 'death_registration',
            ),
            pk=app_pk,
            status=ApplicationStatus.REGISTERED,
        )

        update_reason = request.POST.get('update_reason', '').strip()
        if not update_reason:
            ctx = _get_master_context()
            ctx['app'] = app
            ctx['birth'] = getattr(app, 'birth_registration', None)
            ctx['death'] = getattr(app, 'death_registration', None)
            ctx['error'] = 'Update reason is required.'
            return render(request, 'Authority/updation/certificate_edit.html', ctx)

        # Build proposed_changes dict from POST vs current child record
        if app.service_type == 'BIRTH_REGISTRATION':
            cr = getattr(app, 'birth_registration', None)
            cert_no = cr.registration_number if cr else ''
            fields = [
                'child_first_name', 'child_middle_name', 'child_last_name',
                'date_of_birth', 'time_of_birth', 'sex',
                'event_location_type', 'institution_name', 'place_of_birth_address',
                'mother_name', 'mother_age_at_birth', 'mother_nationality',
                'mother_education', 'mother_occupation', 'mother_mobile', 'mother_aadhaar',
                'father_name', 'father_age_at_birth', 'father_nationality',
                'father_education', 'father_occupation', 'father_mobile', 'father_aadhaar',
                'permanent_address',
                'informant_name', 'informant_relation', 'informant_address', 'informant_mobile',
            ]
        else:
            cr = getattr(app, 'death_registration', None)
            cert_no = cr.registration_number if cr else ''
            fields = [
                'deceased_first_name', 'deceased_middle_name', 'deceased_last_name',
                'sex', 'date_of_birth_of_deceased',
                'age_at_death_years', 'age_at_death_months', 'age_at_death_days',
                'nationality', 'date_of_death', 'time_of_death',
                'event_location_type', 'institution_name', 'place_of_death_address',
                'last_residence_address', 'father_name', 'mother_name', 'spouse_name',
                'informant_name', 'informant_relation', 'informant_address', 'informant_mobile',
            ]

        proposed_changes = {}
        if cr:
            for field in fields:
                old_val = getattr(cr, field, None)
                new_val = request.POST.get(field, '').strip() or None
                # Normalize both to string for comparison
                old_str = str(old_val) if old_val is not None else ''
                new_str = str(new_val) if new_val is not None else ''
                if old_str != new_str and new_str:
                    proposed_changes[field] = {'old': old_str, 'new': new_str}

        if not proposed_changes:
            ctx = _get_master_context()
            ctx['app'] = app
            ctx['birth'] = getattr(app, 'birth_registration', None)
            ctx['death'] = getattr(app, 'death_registration', None)
            ctx['error'] = 'No changes detected. Please modify at least one field.'
            return render(request, 'Authority/updation/certificate_edit.html', ctx)

        with transaction.atomic():
            req = CertificateUpdationRequest.objects.create(
                original_application=app,
                certificate_number=cert_no,
                service_type=app.service_type,
                update_reason=update_reason,
                proposed_changes=proposed_changes,
                status=UpdationStatus.SUBMITTED,
                submitted_by=request.user,
                submitted_at=timezone.now(),
            )
            _record_upd_transition(req, '', UpdationStatus.SUBMITTED, 'UPD_SUBMITTED', request.user, update_reason)
            assign_updation_workflow(req)

        return redirect('updation_inbox')


# ─── 3. Updation Inbox ────────────────────────────────────────────────────────

class UpdationInboxView(LoginRequiredMixin, View):
    """
    GET /mailbox/updation-inbox/

    Shows updation requests assigned to the current user's role/ULB step.
    """
    login_url = '/login/'

    def get(self, request):
        from users.models import UserRole
        user = request.user

        base_qs = CertificateUpdationRequest.objects.select_related(
            'original_application__registration_type',
            'original_application__district',
            'original_application__ulb',
            'current_step',
            'submitted_by',
        ).exclude(
            status__in=(UpdationStatus.DRAFT, UpdationStatus.APPROVED,
                        UpdationStatus.REJECTED, UpdationStatus.CANCELLED)
        )

        if user.is_superuser or getattr(user, 'role', None) == UserRole.ADMIN:
            qs = base_qs.order_by('-created_at')
        else:
            qs = base_qs.filter(workflow__isnull=False)
            if getattr(user, 'role', None):
                qs = qs.filter(current_step__role_code=user.role)
            if getattr(user, 'ulb_fk_id', None):
                qs = qs.filter(original_application__ulb=user.ulb_fk)
            qs = qs.order_by('-created_at')

        return render(request, 'Authority/updation/updation_inbox.html', {
            'requests': qs,
            'inbox_title': 'Certificate Updation Inbox',
            'from_param': 'upd_inbox',
        })


# ─── 4. Updation Sentbox ─────────────────────────────────────────────────────

class UpdationSentboxView(LoginRequiredMixin, View):
    """
    GET /mailbox/updation-sentbox/

    Shows all updation requests the current user has forwarded or approved.
    """
    login_url = '/login/'

    def get(self, request):
        user = request.user

        processed_ids = UpdationStatusHistory.objects.filter(
            changed_by=user,
            action__in=('UPD_FORWARDED', 'UPD_APPROVED'),
        ).values_list('request_id', flat=True).distinct()

        qs = CertificateUpdationRequest.objects.filter(
            pk__in=processed_ids
        ).select_related(
            'original_application__registration_type',
            'original_application__district',
            'original_application__ulb',
            'current_step',
            'submitted_by',
        ).order_by('-updated_at')

        return render(request, 'Authority/updation/updation_inbox.html', {
            'requests': qs,
            'inbox_title': 'Certificate Updation Sentbox',
            'from_param': 'upd_sentbox',
        })


# ─── 5. Updation Request Detail ───────────────────────────────────────────────

class UpdationRequestDetailView(LoginRequiredMixin, View):
    """
    GET /certificate-updation/request/<pk>/

    Read-only view of an updation request with proposed changes diff,
    action history, and action buttons (Forward / Approve / Reject).
    """
    login_url = '/login/'

    def get(self, request, pk):
        from_param = request.GET.get('from', '')
        req = get_object_or_404(
            CertificateUpdationRequest.objects.select_related(
                'original_application__registration_type',
                'original_application__district',
                'original_application__ulb',
                'original_application__birth_registration',
                'original_application__death_registration',
                'current_step',
                'submitted_by',
                'workflow',
            ).prefetch_related('status_history__changed_by'),
            pk=pk,
        )

        app = req.original_application
        birth = getattr(app, 'birth_registration', None)
        death = getattr(app, 'death_registration', None)

        # Determine if this is the last step (for Approve vs Forward button)
        last_step = is_last_updation_step(req)

        # Format proposed_changes for display
        changes_display = []
        for field, diff in req.proposed_changes.items():
            changes_display.append({
                'field': field.replace('_', ' ').title(),
                'old': diff.get('old', ''),
                'new': diff.get('new', ''),
            })

        # Determine if user can act (inbox view)
        can_act = from_param == 'upd_inbox'

        return render(request, 'Authority/updation/updation_request_detail.html', {
            'req': req,
            'app': app,
            'birth': birth,
            'death': death,
            'changes_display': changes_display,
            'is_last_step': last_step,
            'can_act': can_act,
            'remarks_log': req.remarks.select_related('officer').order_by('created_at'),
            'from_param': from_param,
        })


# ─── 6. Forward Updation Request ─────────────────────────────────────────────

class UpdationForwardView(LoginRequiredMixin, View):
    """
    POST /certificate-updation/request/<pk>/forward/
    """
    login_url = '/login/'

    def post(self, request, pk):
        req = get_object_or_404(CertificateUpdationRequest, pk=pk)
        remark = request.POST.get('remark', '').strip()

        FORWARDABLE = {UpdationStatus.SUBMITTED, UpdationStatus.UNDER_SCRUTINY, UpdationStatus.UNDER_PROCESS}
        if req.status not in FORWARDABLE:
            return redirect('updation_inbox')

        STATUS_MAP = {
            UpdationStatus.SUBMITTED:      UpdationStatus.UNDER_SCRUTINY,
            UpdationStatus.UNDER_SCRUTINY: UpdationStatus.UNDER_PROCESS,
            UpdationStatus.UNDER_PROCESS:  UpdationStatus.UNDER_PROCESS,
        }

        old_status = req.status
        target_status = STATUS_MAP[req.status]
        req.status = target_status
        req.save(update_fields=['status', 'updated_at'])

        _record_upd_transition(req, old_status, target_status, 'UPD_FORWARDED', request.user, remark)
        _save_upd_remark(req, 'UPD_FORWARDED', request.user, remark)
        advance_updation_workflow(req, request.user)

        return redirect('updation_inbox')


# ─── 7. Approve Updation Request ─────────────────────────────────────────────

class UpdationApproveView(LoginRequiredMixin, View):
    """
    POST /certificate-updation/request/<pk>/approve/

    Final approval — applies proposed_changes to the original child record.
    """
    login_url = '/login/'

    def post(self, request, pk):
        req = get_object_or_404(
            CertificateUpdationRequest.objects.select_related(
                'original_application__birth_registration',
                'original_application__death_registration',
            ),
            pk=pk,
        )
        remark = request.POST.get('remark', '').strip()

        if req.status not in (UpdationStatus.SUBMITTED, UpdationStatus.UNDER_SCRUTINY, UpdationStatus.UNDER_PROCESS):
            return redirect('updation_inbox')

        app = req.original_application
        old_status = req.status

        with transaction.atomic():
            # Apply proposed changes to the original child record
            if app.service_type == 'BIRTH_REGISTRATION':
                cr = getattr(app, 'birth_registration', None)
            else:
                cr = getattr(app, 'death_registration', None)

            if cr and req.proposed_changes:
                update_fields = []
                for field, diff in req.proposed_changes.items():
                    if hasattr(cr, field):
                        setattr(cr, field, diff.get('new', ''))
                        update_fields.append(field)
                if update_fields:
                    cr.save(update_fields=update_fields)

            req.status = UpdationStatus.APPROVED
            req.save(update_fields=['status', 'updated_at'])
            _record_upd_transition(req, old_status, UpdationStatus.APPROVED, 'UPD_APPROVED', request.user, remark)
            _save_upd_remark(req, 'UPD_APPROVED', request.user, remark)

        # Redirect to the updated certificate
        if app.service_type == 'BIRTH_REGISTRATION':
            return redirect('birth_certificate', pk=app.pk)
        else:
            return redirect('death_certificate', pk=app.pk)


# ─── 8. Reject Updation Request ──────────────────────────────────────────────

class UpdationRejectView(LoginRequiredMixin, View):
    """
    POST /certificate-updation/request/<pk>/reject/

    Rejects the updation request. Original record is unchanged.
    """
    login_url = '/login/'

    def post(self, request, pk):
        req = get_object_or_404(CertificateUpdationRequest, pk=pk)
        remark = request.POST.get('remark', '').strip()

        if not remark:
            return redirect('updation_request_detail', pk=pk)

        old_status = req.status
        req.status = UpdationStatus.REJECTED
        req.save(update_fields=['status', 'updated_at'])
        _record_upd_transition(req, old_status, UpdationStatus.REJECTED, 'UPD_REJECTED', request.user, remark)
        _save_upd_remark(req, 'UPD_REJECTED', request.user, remark)

        return redirect('updation_inbox')


# ─────────────────────────────────────────────────────────────────────────────
# UPDATION REPORTS
# ─────────────────────────────────────────────────────────────────────────────

import csv
from datetime import datetime
from django.http import StreamingHttpResponse


def _upd_base_qs(request):
    """Base queryset for all updation reports — scoped to user's ULB."""
    from users.models import UserRole
    user = request.user
    qs = CertificateUpdationRequest.objects.select_related(
        'original_application__district',
        'original_application__ulb',
        'original_application__registration_type',
        'current_step',
        'submitted_by',
        'workflow',
    ).prefetch_related('status_history__changed_by')
    if not (user.is_superuser or getattr(user, 'role', None) == UserRole.ADMIN):
        if getattr(user, 'ulb_fk_id', None):
            qs = qs.filter(original_application__ulb=user.ulb_fk)
    return qs


def _apply_upd_filters(qs, params):
    date_from     = params.get('date_from', '').strip()
    date_to       = params.get('date_to', '').strip()
    service_type  = params.get('service_type', '').strip()
    status        = params.get('status', '').strip()
    if date_from:
        try:
            qs = qs.filter(submitted_at__date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            qs = qs.filter(submitted_at__date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass
    if service_type:
        qs = qs.filter(service_type=service_type)
    if status:
        qs = qs.filter(status=status)
    return qs


def _upd_paginate(qs, page, per_page=25):
    total       = qs.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    page        = max(1, min(page, total_pages))
    start       = (page - 1) * per_page
    return list(qs[start:start + per_page]), total, total_pages, page


def _csv_line(row):
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(row)
    return buf.getvalue()


class UpdationRegisterReportView(LoginRequiredMixin, View):
    """GET /certificate-updation/reports/register/"""
    login_url = '/login/'

    def get(self, request):
        qs = _apply_upd_filters(_upd_base_qs(request), request.GET).order_by('-submitted_at')
        if request.GET.get('export') == 'csv':
            return self._csv(qs)
        is_print = request.GET.get('print') == '1'
        rows, total, total_pages, page = (
            (list(qs), qs.count(), 1, 1) if is_print
            else _upd_paginate(qs, int(request.GET.get('page', 1)))
        )
        return render(request, 'Authority/updation/reports/updation_register.html', {
            'rows': rows, 'total': total, 'total_pages': total_pages,
            'current_page': page, 'is_print': is_print,
            'filter_params': request.GET,
            'service_types': [('BIRTH_REGISTRATION','Birth Registration'),('DEATH_REGISTRATION','Death Registration')],
            'status_choices': UpdationStatus.choices,
            'report_title': 'Updation Register',
        })

    def _csv(self, qs):
        def rows():
            yield ['#','Request No.','Application No.','Certificate No.','Service Type','Reason','Submitted By','Submitted On','Status']
            for i, r in enumerate(qs, 1):
                yield [
                    i, f'#{r.pk}', r.original_application.application_number,
                    r.certificate_number,
                    'Birth' if r.service_type == 'BIRTH_REGISTRATION' else 'Death',
                    r.update_reason,
                    r.submitted_by.get_full_name() if r.submitted_by else '',
                    r.submitted_at.strftime('%d-%m-%Y %H:%M') if r.submitted_at else '',
                    r.get_status_display(),
                ]
        resp = StreamingHttpResponse((_csv_line(r) for r in rows()), content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="updation_register.csv"'
        return resp


class UpdationPendingReportView(LoginRequiredMixin, View):
    """GET /certificate-updation/reports/pending/"""
    login_url = '/login/'

    def get(self, request):
        qs = _apply_upd_filters(_upd_base_qs(request), request.GET).filter(
            status__in=(UpdationStatus.SUBMITTED, UpdationStatus.UNDER_SCRUTINY, UpdationStatus.UNDER_PROCESS)
        ).order_by('-submitted_at')
        if request.GET.get('export') == 'csv':
            return self._csv(qs)
        rows, total, total_pages, page = _upd_paginate(qs, int(request.GET.get('page', 1)))
        today = timezone.localdate()
        rows_with_days = []
        for r in rows:
            pd = (today - r.submitted_at.date()).days if r.submitted_at else 0
            rows_with_days.append({'req': r, 'pending_days': pd})
        return render(request, 'Authority/updation/reports/updation_pending.html', {
            'rows': rows_with_days, 'total': total, 'total_pages': total_pages,
            'current_page': page, 'is_print': False,
            'filter_params': request.GET,
            'service_types': [('BIRTH_REGISTRATION','Birth Registration'),('DEATH_REGISTRATION','Death Registration')],
            'report_title': 'Pending & Workflow Report',
        })

    def _csv(self, qs):
        today = timezone.localdate()
        def rows():
            yield ['#','Request No.','Application No.','Service Type','Current Step','Assigned Role','Pending Days','Status']
            for i, r in enumerate(qs, 1):
                pd = (today - r.submitted_at.date()).days if r.submitted_at else 0
                yield [
                    i, f'#{r.pk}', r.original_application.application_number,
                    'Birth' if r.service_type == 'BIRTH_REGISTRATION' else 'Death',
                    r.current_step.name if r.current_step else '',
                    r.current_step.role_code if r.current_step else '',
                    pd, r.get_status_display(),
                ]
        resp = StreamingHttpResponse((_csv_line(r) for r in rows()), content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="updation_pending.csv"'
        return resp


class UpdationDecisionReportView(LoginRequiredMixin, View):
    """GET /certificate-updation/reports/decisions/"""
    login_url = '/login/'

    def get(self, request):
        qs = _apply_upd_filters(_upd_base_qs(request), request.GET).filter(
            status__in=(UpdationStatus.APPROVED, UpdationStatus.REJECTED)
        ).order_by('-updated_at')
        if request.GET.get('export') == 'csv':
            return self._csv(qs)
        rows, total, total_pages, page = _upd_paginate(qs, int(request.GET.get('page', 1)))
        return render(request, 'Authority/updation/reports/updation_decisions.html', {
            'rows': rows, 'total': total, 'total_pages': total_pages,
            'current_page': page, 'is_print': False,
            'filter_params': request.GET,
            'service_types': [('BIRTH_REGISTRATION','Birth Registration'),('DEATH_REGISTRATION','Death Registration')],
            'report_title': 'Approved & Rejected Report',
        })

    def _csv(self, qs):
        def rows():
            yield ['#','Request No.','Application No.','Service Type','Status','Decision By','Decision At','Remarks']
            for i, r in enumerate(qs, 1):
                final_h = r.status_history.filter(action__in=('UPD_APPROVED','UPD_REJECTED')).last()
                yield [
                    i, f'#{r.pk}', r.original_application.application_number,
                    'Birth' if r.service_type == 'BIRTH_REGISTRATION' else 'Death',
                    r.get_status_display(),
                    final_h.changed_by.get_full_name() if (final_h and final_h.changed_by) else '',
                    final_h.changed_at.strftime('%d-%m-%Y %H:%M') if final_h else '',
                    final_h.remarks if final_h else '',
                ]
        resp = StreamingHttpResponse((_csv_line(r) for r in rows()), content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="updation_decisions.csv"'
        return resp


class UpdationFieldChangeReportView(LoginRequiredMixin, View):
    """GET /certificate-updation/reports/field-changes/"""
    login_url = '/login/'

    def get(self, request):
        qs = _apply_upd_filters(_upd_base_qs(request), request.GET).filter(
            status=UpdationStatus.APPROVED
        ).order_by('-updated_at')
        if request.GET.get('export') == 'csv':
            return self._csv(qs)
        rows, total, total_pages, page = _upd_paginate(qs, int(request.GET.get('page', 1)))
        return render(request, 'Authority/updation/reports/updation_field_changes.html', {
            'rows': rows, 'total': total, 'total_pages': total_pages,
            'current_page': page, 'is_print': False,
            'filter_params': request.GET,
            'service_types': [('BIRTH_REGISTRATION','Birth Registration'),('DEATH_REGISTRATION','Death Registration')],
            'report_title': 'Field Change History',
        })

    def _csv(self, qs):
        def rows():
            yield ['Request No.','Application No.','Field','Old Value','New Value','Approved By','Approved At']
            for r in qs:
                final_h = r.status_history.filter(action='UPD_APPROVED').last()
                approver = final_h.changed_by.get_full_name() if (final_h and final_h.changed_by) else ''
                approved_at = final_h.changed_at.strftime('%d-%m-%Y %H:%M') if final_h else ''
                for field, diff in r.proposed_changes.items():
                    yield [
                        f'#{r.pk}', r.original_application.application_number,
                        field.replace('_', ' ').title(),
                        diff.get('old', ''), diff.get('new', ''),
                        approver, approved_at,
                    ]
        resp = StreamingHttpResponse((_csv_line(r) for r in rows()), content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="updation_field_changes.csv"'
        return resp


class UpdationSummaryReportView(LoginRequiredMixin, View):
    """GET /certificate-updation/reports/summary/"""
    login_url = '/login/'

    def get(self, request):
        from django.db.models import Count, Q
        qs = _apply_upd_filters(_upd_base_qs(request), request.GET)
        total       = qs.count()
        pending     = qs.filter(status__in=(UpdationStatus.SUBMITTED, UpdationStatus.UNDER_SCRUTINY, UpdationStatus.UNDER_PROCESS)).count()
        approved    = qs.filter(status=UpdationStatus.APPROVED).count()
        rejected    = qs.filter(status=UpdationStatus.REJECTED).count()
        cancelled   = qs.filter(status=UpdationStatus.CANCELLED).count()
        by_service  = qs.values('service_type').annotate(count=Count('id')).order_by('service_type')
        by_status   = qs.values('status').annotate(count=Count('id')).order_by('status')
        return render(request, 'Authority/updation/reports/updation_summary.html', {
            'total': total, 'pending': pending, 'approved': approved,
            'rejected': rejected, 'cancelled': cancelled,
            'by_service': by_service, 'by_status': by_status,
            'filter_params': request.GET,
            'service_types': [('BIRTH_REGISTRATION','Birth Registration'),('DEATH_REGISTRATION','Death Registration')],
            'status_choices': UpdationStatus.choices,
            'report_title': 'Updation Summary',
        })
