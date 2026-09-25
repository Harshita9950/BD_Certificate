
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils import timezone

from rest_framework import viewsets, mixins
from rest_framework.permissions import IsAuthenticated

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter

from .models import (
    TradeCategory,
    Trade,
    SubTrade,
    ULBTradeConfig,
    Application,
    CoOwner,
    ApplicationDocument,
)

from .serializers import (
    TradeCategorySerializer,
    TradeSerializer,
    SubTradeSerializer,
    ULBTradeConfigSerializer,
    ApplicationSerializer,
)

from geography.models import District, ULB, Ward


# =========================================================
# TRADE LICENCE APPLICATION FORM
# =========================================================

@login_required
def new_application(request):

    context = {
        "trade_categories": TradeCategory.objects.filter(
            is_active=True
        ).order_by("name"),

        "districts": District.objects.filter(
            is_active=True
        ).order_by("name"),
    }

    if request.method == "POST":

        try:
            with transaction.atomic():

                # -----------------------------------------
                # 1. Validate geography and category
                # -----------------------------------------

                ulb = ULB.objects.get(
                    pk=request.POST.get("ulb"),
                    is_active=True,
                )

                ward = Ward.objects.get(
                    pk=request.POST.get("ward"),
                    is_active=True,
                    zone__ulb=ulb,
                    zone__is_active=True,
                )

                category = TradeCategory.objects.get(
                    pk=request.POST.get("category"),
                    is_active=True,
                )

                # -----------------------------------------
                # 2. Read business details
                # -----------------------------------------

                firm_name = request.POST.get(
                    "firm_name", ""
                ).strip()

                building_address = request.POST.get(
                    "building_address", ""
                ).strip()

                business_name = (
                    request.POST.get("business_name", "").strip()
                    or firm_name
                )

                business_address = (
                    request.POST.get("business_address", "").strip()
                    or building_address
                )

                if not business_name or not business_address:
                    raise ValueError(
                        "Business name and business address are required."
                    )

                # -----------------------------------------
                # 3. Create application
                # -----------------------------------------

                application = Application.objects.create(
                    applicant=request.user,
                    ulb=ulb,
                    ward=ward,
                    category=category,

                    # Applicant details
                    applicant_name=request.POST.get(
                        "applicant_name", ""
                    ).strip(),

                    father_or_spouse_name=request.POST.get(
                        "father_spouse_name", ""
                    ).strip(),

                    date_of_birth=(
                        date.fromisoformat(
                            request.POST["date_of_birth"]
                        )
                        if request.POST.get("date_of_birth")
                        else None
                    ),

                    gender=request.POST.get("gender", ""),

                    aadhaar_number=request.POST.get(
                        "aadhaar_number", ""
                    ).strip(),

                    applicant_mobile=request.POST.get(
                        "applicant_mobile", ""
                    ).strip(),

                    applicant_email=request.POST.get(
                        "applicant_email", ""
                    ).strip(),

                    nationality=request.POST.get(
                        "nationality", "Indian"
                    ).strip(),

                    correspondence_address=request.POST.get(
                        "correspondence_address", ""
                    ).strip(),

                    # Ownership details
                    constitution_type=request.POST.get(
                        "business_constitution", ""
                    ),

                    firm_name=firm_name,

                    owner_name=request.POST.get(
                        "owner_name", ""
                    ).strip(),

                    owner_mobile=request.POST.get(
                        "owner_mobile", ""
                    ).strip(),

                    owner_email=request.POST.get(
                        "owner_email", ""
                    ).strip(),

                    # Business details
                    business_name=business_name,
                    business_address=business_address,

                    business_mobile=request.POST.get(
                        "business_mobile", ""
                    ).strip(),

                    # Premises details
                    premises_ownership=request.POST.get(
                        "premises_ownership", ""
                    ),

                    premises_owner_name=request.POST.get(
                        "premises_owner_name", ""
                    ).strip(),

                    building_address=building_address,

                    floor=request.POST.get(
                        "floor_numbers", ""
                    ).strip(),

                    total_area=(
                        Decimal(request.POST["total_premises_area"])
                        if request.POST.get("total_premises_area")
                        else None
                    ),

                    business_area=(
                        Decimal(request.POST["business_area"])
                        if request.POST.get("business_area")
                        else None
                    ),

                    nature_of_business=request.POST.get(
                        "nature_of_business", ""
                    ).strip(),

                    business_description=request.POST.get(
                        "business_description", ""
                    ).strip(),

                    employee_count=(
                        int(request.POST["employee_count"])
                        if request.POST.get("employee_count")
                        else None
                    ),

                    # Submission details
                    status=Application.Status.SUBMITTED,
                    submitted_at=timezone.now(),
                )

                # -----------------------------------------
                # 4. Save co-owner details
                # -----------------------------------------

                co_owner_names = request.POST.getlist(
                    "co_owner_name[]"
                )

                co_owner_relationships = request.POST.getlist(
                    "co_owner_relationship[]"
                )

                co_owner_mobiles = request.POST.getlist(
                    "co_owner_mobile[]"
                )

                co_owner_emails = request.POST.getlist(
                    "co_owner_email[]"
                )

                for i, name in enumerate(co_owner_names):

                    name = name.strip()

                    if not name:
                        continue

                    CoOwner.objects.create(
                        application=application,
                        name=name,

                        relationship=(
                            co_owner_relationships[i].strip()
                            if i < len(co_owner_relationships)
                            else ""
                        ),

                        mobile=(
                            co_owner_mobiles[i].strip()
                            if i < len(co_owner_mobiles)
                            else ""
                        ),

                        email=(
                            co_owner_emails[i].strip()
                            if i < len(co_owner_emails)
                            else ""
                        ),
                    )

                # -----------------------------------------
                # 5. Save uploaded document (if provided)
                # -----------------------------------------

                uploaded_document = request.FILES.get("document")
                document_remark = request.POST.get(
                    "document_remark", ""
                ).strip()

                if uploaded_document:
                    ApplicationDocument.objects.create(
                        application=application,
                        document=uploaded_document,
                        remark=document_remark,
                    )

            # -----------------------------------------
            # 6. Success message
            # -----------------------------------------

            messages.success(
                request,
                f"Application submitted successfully. "
                f"Application No: {application.application_no}",
            )

            return redirect("new_application")

        except (
            ULB.DoesNotExist,
            Ward.DoesNotExist,
            TradeCategory.DoesNotExist,
        ):
            messages.error(
                request,
                "Please select a valid ULB, ward, and trade category.",
            )

        except (ValueError, InvalidOperation, TypeError):
            messages.error(
                request,
                "Please check the form values and try again.",
            )

    return render(
        request,
        "Authority/new_application_form.html",
        context,
    )


# =========================================================
# TRADE CATEGORY API
# =========================================================

class TradeCategoryViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
):

    queryset = TradeCategory.objects.all()
    serializer_class = TradeCategorySerializer

    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["is_active"]
    search_fields = ["code", "name"]


# =========================================================
# TRADE API
# =========================================================

class TradeViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = (
        Trade.objects.filter(is_active=True)
        .select_related("category")
    )

    serializer_class = TradeSerializer

    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["category", "is_active"]
    search_fields = ["code", "name"]


# =========================================================
# SUB-TRADE API
# =========================================================

class SubTradeViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = (
        SubTrade.objects.filter(is_active=True)
        .select_related("trade__category")
    )

    serializer_class = SubTradeSerializer

    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["trade", "is_active"]
    search_fields = ["code", "name"]


# =========================================================
# ULB TRADE CONFIG API
# =========================================================

class ULBTradeConfigViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = (
        ULBTradeConfig.objects
        .select_related("ulb", "trade__category")
        .order_by("ulb", "trade")
    )

    serializer_class = ULBTradeConfigSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["ulb", "trade", "is_enabled"]


# =========================================================
# APPLICATION API
# =========================================================

class ApplicationViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
):

    serializer_class = ApplicationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Application.objects.filter(
                applicant=self.request.user
            )
            .select_related(
                "category",
                "ulb",
                "ward",
                "workflow",
                "current_step",
            )
            .prefetch_related("co_owners")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        serializer.save(applicant=self.request.user)