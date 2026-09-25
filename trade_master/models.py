
import uuid

from django.db import models
from django.utils import timezone


# =========================================================
# TRADE CATEGORY
# =========================================================

class TradeCategory(models.Model):
    code = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Trade Categories"

    def __str__(self):
        return f"{self.name} ({self.code})"


# =========================================================
# TRADE
# =========================================================

class Trade(models.Model):
    category = models.ForeignKey(
        TradeCategory,
        on_delete=models.PROTECT,
        related_name="trades",
    )
    code = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]
        indexes = [
            models.Index(fields=["category", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


# =========================================================
# SUB-TRADE
# =========================================================

class SubTrade(models.Model):
    trade = models.ForeignKey(
        Trade,
        on_delete=models.PROTECT,
        related_name="sub_trades",
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["trade", "name"]
        unique_together = [("trade", "code")]
        indexes = [
            models.Index(fields=["trade", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code}) — {self.trade.code}"


# =========================================================
# ULB TRADE CONFIG
# =========================================================

class ULBTradeConfig(models.Model):
    """
    Controls which trades are enabled for a specific ULB.
    """

    ulb = models.ForeignKey(
        "geography.ULB",
        on_delete=models.PROTECT,
        related_name="trade_configs",
    )
    trade = models.ForeignKey(
        Trade,
        on_delete=models.PROTECT,
        related_name="ulb_configs",
    )
    is_enabled = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("ulb", "trade")]
        ordering = ["ulb", "trade"]
        indexes = [
            models.Index(fields=["ulb", "is_enabled"]),
        ]

    def __str__(self):
        status = "enabled" if self.is_enabled else "disabled"
        return f"{self.ulb.code} — {self.trade.code} [{status}]"


# =========================================================
# APPLICATION
# =========================================================

class Application(models.Model):

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_PROCESS = "UNDER_PROCESS", "Under Process"
        DEFICIENCY = "DEFICIENCY", "Deficiency"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        LICENSE_GENERATED = "LICENSE_GENERATED", "Licence Generated"

    # -----------------------------------------------------
    # Application Details
    # -----------------------------------------------------

    application_no = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
    )

    applicant = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="trade_license_applications",
    )

    ulb = models.ForeignKey(
        "geography.ULB",
        on_delete=models.PROTECT,
        related_name="trade_license_applications",
    )

    ward = models.ForeignKey(
        "geography.Ward",
        on_delete=models.PROTECT,
        related_name="trade_license_applications",
    )

    category = models.ForeignKey(
        TradeCategory,
        on_delete=models.PROTECT,
        related_name="applications",
    )

    # -----------------------------------------------------
    # Applicant Snapshot Details
    # -----------------------------------------------------

    applicant_name = models.CharField(max_length=150, blank=True)
    father_or_spouse_name = models.CharField(max_length=150, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    GENDER_CHOICES = [
        ("MALE", "Male"),
        ("FEMALE", "Female"),
        ("OTHER", "Other"),
        ("PREFER_NOT_TO_SAY", "Prefer not to say"),
    ]

    gender = models.CharField(
        max_length=20,
        choices=GENDER_CHOICES,
        blank=True,
    )

    aadhaar_number = models.CharField(max_length=12, blank=True)
    applicant_mobile = models.CharField(max_length=15, blank=True)
    applicant_email = models.EmailField(blank=True)
    nationality = models.CharField(max_length=100, default="Indian")
    correspondence_address = models.TextField(blank=True)

    # -----------------------------------------------------
    # Ownership Details
    # -----------------------------------------------------

    CONSTITUTION_CHOICES = [
        ("INDIVIDUAL", "Individual"),
        ("PROPRIETORSHIP", "Sole Proprietorship"),
        ("PARTNERSHIP", "Partnership"),
        ("LLP", "Limited Liability Partnership"),
        ("PRIVATE_LIMITED", "Private Limited Company"),
        ("PUBLIC_LIMITED", "Public Limited Company"),
        ("HUF", "HUF"),
        ("TRUST", "Trust"),
        ("SOCIETY", "Society"),
        ("COMPANY", "Company"),
        ("OTHER", "Other"),
    ]

    constitution_type = models.CharField(
        max_length=30,
        choices=CONSTITUTION_CHOICES,
        blank=True,
    )

    firm_name = models.CharField(max_length=200, blank=True)
    owner_name = models.CharField(max_length=150, blank=True)
    owner_mobile = models.CharField(max_length=15, blank=True)
    owner_email = models.EmailField(blank=True)

    # -----------------------------------------------------
    # Business Details
    # -----------------------------------------------------

    business_name = models.CharField(max_length=200)
    business_address = models.TextField()
    business_mobile = models.CharField(max_length=15, blank=True)

    # -----------------------------------------------------
    # Premises Details
    # -----------------------------------------------------

    OWNERSHIP_CHOICES = [
        ("OWNED", "Owned"),
        ("RENTED", "Rented"),
        ("LEASED", "Leased"),
    ]

    premises_ownership = models.CharField(
        max_length=10,
        choices=OWNERSHIP_CHOICES,
        blank=True,
    )

    premises_owner_name = models.CharField(max_length=150, blank=True)
    building_address = models.TextField(blank=True)
    floor = models.CharField(max_length=100, blank=True)

    total_area = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    business_area = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    nature_of_business = models.CharField(max_length=200, blank=True)
    business_description = models.TextField(blank=True)
    employee_count = models.PositiveIntegerField(null=True, blank=True)

    # -----------------------------------------------------
    # Workflow Details
    # -----------------------------------------------------

    workflow = models.ForeignKey(
        "workflow_master.Workflow",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="applications",
    )

    current_step = models.ForeignKey(
        "workflow_master.WorkflowStep",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="applications",
    )

    assigned_to = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assigned_trade_license_applications",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["ulb", "ward", "status"]),
            models.Index(fields=["assigned_to", "status"]),
        ]

    def save(self, *args, **kwargs):
        # Generate a temporary unique value for new applications.
        if not self.application_no:
            self.application_no = f"TEMP-{uuid.uuid4().hex}"
            super().save(*args, **kwargs)

            # Generate the final application number using the primary key.
            self.application_no = (
                f"TL-{timezone.localdate().year}-{self.pk:06d}"
            )
            super().save(update_fields=["application_no"])
            return

        super().save(*args, **kwargs)

    def __str__(self):
        return self.application_no


# =========================================================
# CO-OWNER
# =========================================================

class CoOwner(models.Model):
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="co_owners",
    )

    name = models.CharField(max_length=150)
    relationship = models.CharField(max_length=100, blank=True)
    mobile = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} - {self.application.application_no}"


# =========================================================
# APPLICATION DOCUMENT
# =========================================================

class ApplicationDocument(models.Model):
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    document = models.FileField(
        upload_to="trade_license/documents/%Y/%m/",
    )

    remark = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Document - {self.application.application_no}"