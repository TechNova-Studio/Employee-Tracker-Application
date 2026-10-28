from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from datetime import timedelta
import secrets


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CompanyPlan(TimeStampedModel):
    PLAN_CODES = [
        ('INTERNAL', 'Internal'),
        ('TRIAL', 'Trial'),
        ('BASIC', 'Basic'),
        ('PRO', 'Pro'),
        ('BUSINESS', 'Business'),
        ('ENTERPRISE', 'Enterprise'),
    ]
    code = models.CharField(max_length=32, choices=PLAN_CODES, unique=True)
    name = models.CharField(max_length=100)
    price_per_user = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_users = models.PositiveIntegerField(default=10)
    max_devices = models.PositiveIntegerField(default=10)
    screenshot_retention_days = models.PositiveIntegerField(default=30)
    ai_enabled = models.BooleanField(default=True)
    erp_connector_enabled = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Company(TimeStampedModel):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('TRIAL_ACTIVE', 'Trial Active'),
        ('TRIAL_EXPIRED', 'Trial Expired'),
        ('SUSPENDED', 'Suspended'),
        ('INTERNAL', 'Internal'),
    ]
    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255, blank=True)
    employee_id_prefix = models.CharField(max_length=32, blank=True)
    next_employee_number = models.PositiveBigIntegerField(default=1)
    contact_person = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    mobile = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='ACTIVE')
    plan = models.ForeignKey(CompanyPlan, on_delete=models.PROTECT, null=True, blank=True)
    trial_start_date = models.DateTimeField(null=True, blank=True)
    trial_end_date = models.DateTimeField(null=True, blank=True)
    allowed_users = models.PositiveIntegerField(default=10)
    allowed_devices = models.PositiveIntegerField(default=10)
    screenshot_interval_seconds = models.PositiveIntegerField(default=300)
    screenshot_retention_days = models.PositiveIntegerField(default=30)
    idle_threshold_seconds = models.PositiveIntegerField(default=300)
    billing_disabled = models.BooleanField(default=False)

    def is_trial_expired(self):
        return self.status in ('TRIAL_ACTIVE', 'TRIAL_EXPIRED') and bool(
            self.trial_end_date and timezone.now() >= self.trial_end_date)

    def __str__(self):
        return self.name


class Department(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('company', 'name')]

    def __str__(self):
        return f'{self.company.name} - {self.name}'


class Profile(TimeStampedModel):
    ROLE_CHOICES = [
        ('SUPER_ADMIN', 'Super Admin'),
        ('COMPANY_ADMIN', 'Company Admin'),
        ('HR_ADMIN', 'HR/Admin'),
        ('SALES_ADMIN', 'Sales/Admin'),
        ('MANAGER', 'Manager'),
        ('EMPLOYEE', 'Employee'),
    ]
    POLICY_CHOICES = [
        ('NOT_ACCEPTED', 'Not Accepted'),
        ('ACCEPTED', 'Accepted'),
        ('POLICY_DECLINED', 'Policy Declined'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='profiles')
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default='EMPLOYEE')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='team_members')
    employee_code = models.CharField(max_length=64, blank=True)
    mobile = models.CharField(max_length=30, blank=True)
    policy_status = models.CharField(max_length=32, choices=POLICY_CHOICES, default='NOT_ACCEPTED')
    can_generate_trials = models.BooleanField(default=False)
    is_active_employee = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            Lower('employee_code'), 'company', condition=~models.Q(employee_code=''),
            name='unique_company_employee_code',
        )]

    def __str__(self):
        return f'{self.user.email} - {self.role}'


class Subscription(TimeStampedModel):
    STATUS_CHOICES = [
        ('INTERNAL_NOT_BILLABLE', 'Internal / Not Billable'),
        ('TRIAL', 'Trial'),
        ('ACTIVE', 'Active'),
        ('PAST_DUE', 'Past Due'),
        ('CANCELLED', 'Cancelled'),
        ('EXPIRED', 'Expired'),
    ]
    BILLING_CYCLE = [('MONTHLY', 'Monthly'), ('ANNUAL', 'Annual'), ('NONE', 'None')]
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(CompanyPlan, on_delete=models.PROTECT)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='TRIAL')
    active_user_count = models.PositiveIntegerField(default=0)
    price_per_user = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    billing_cycle = models.CharField(max_length=16, choices=BILLING_CYCLE, default='NONE')
    trial_start_date = models.DateTimeField(null=True, blank=True)
    trial_end_date = models.DateTimeField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)


class Device(TimeStampedModel):
    STATUS_CHOICES = [('ACTIVE', 'Active'), ('BLOCKED', 'Blocked'), ('UNKNOWN', 'Unknown'), ('OUTDATED', 'Outdated')]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='devices')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices')
    device_id = models.CharField(max_length=128)
    hostname = models.CharField(max_length=255, blank=True)
    platform = models.CharField(max_length=64, blank=True)
    local_ip = models.CharField(max_length=64, blank=True)
    public_ip = models.CharField(max_length=64, blank=True)
    app_version = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='ACTIVE')
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('company', 'device_id')]


class AgentVersion(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='agent_versions')
    platform = models.CharField(max_length=32, default='windows')
    latest_version = models.CharField(max_length=32, default='1.0.0')
    minimum_supported_version = models.CharField(max_length=32, default='1.0.0')
    download_url = models.URLField(blank=True)
    checksum = models.CharField(max_length=255, blank=True)
    release_notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)


class PolicyVersion(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='policies')
    version = models.CharField(max_length=32)
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = [('company', 'version')]


class PolicyAcceptance(TimeStampedModel):
    STATUS_CHOICES = [('ACCEPTED', 'Accepted'), ('DECLINED', 'Declined')]
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    policy = models.ForeignKey(PolicyVersion, on_delete=models.CASCADE)
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    accepted_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.CharField(max_length=64, blank=True)
    user_agent = models.TextField(blank=True)


class WorkSession(TimeStampedModel):
    STATUS_CHOICES = [('RUNNING', 'Running'), ('STOPPED', 'Stopped'), ('AUTO_STOPPED', 'Auto Stopped')]
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    stopped_at = models.DateTimeField(null=True, blank=True)
    active_seconds = models.PositiveIntegerField(default=0)
    idle_seconds = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='RUNNING')


class Heartbeat(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True)
    session = models.ForeignKey(WorkSession, on_delete=models.CASCADE, related_name='heartbeats')
    captured_at = models.DateTimeField(default=timezone.now)
    active_seconds = models.PositiveIntegerField(default=0)
    idle_seconds = models.PositiveIntegerField(default=0)
    is_idle = models.BooleanField(default=False)
    app_version = models.CharField(max_length=32, blank=True)
    public_ip = models.CharField(max_length=64, blank=True)


class ActivityLog(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True)
    session = models.ForeignKey(WorkSession, on_delete=models.CASCADE, related_name='activities')
    captured_at = models.DateTimeField(default=timezone.now)
    app_name = models.CharField(max_length=255, blank=True)
    window_title = models.TextField(blank=True)
    domain = models.CharField(max_length=255, blank=True)
    url = models.TextField(blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    mouse_count = models.PositiveIntegerField(default=0)
    keyboard_count = models.PositiveIntegerField(default=0)
    productivity = models.CharField(max_length=32, default='UNKNOWN')


class Screenshot(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True)
    session = models.ForeignKey(WorkSession, on_delete=models.CASCADE, related_name='screenshots')
    captured_at = models.DateTimeField(default=timezone.now)
    storage_mode = models.CharField(max_length=16, default='local')
    file = models.ImageField(upload_to='screenshots/%Y/%m/%d/', null=True, blank=True)
    object_key = models.CharField(max_length=500, blank=True)
    checksum = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=32, default='UPLOADED')
    deleted_at = models.DateTimeField(null=True, blank=True)


class ScreenshotAccessLog(TimeStampedModel):
    ACTION_CHOICES = [('VIEW', 'View'), ('DOWNLOAD', 'Download'), ('DELETE', 'Delete')]
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    screenshot = models.ForeignKey(Screenshot, on_delete=models.CASCADE, related_name='access_logs')
    accessed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=16, choices=ACTION_CHOICES)
    ip_address = models.CharField(max_length=64, blank=True)
    user_agent = models.TextField(blank=True)


class AppWebsiteCategory(TimeStampedModel):
    PRODUCTIVITY_CHOICES = [('PRODUCTIVE', 'Productive'), ('NEUTRAL', 'Neutral'), ('UNPRODUCTIVE', 'Unproductive'), ('UNKNOWN', 'Unknown')]
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    pattern_type = models.CharField(max_length=32, default='APP')
    pattern = models.CharField(max_length=255)
    category = models.CharField(max_length=32, choices=PRODUCTIVITY_CHOICES, default='UNKNOWN')
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)


class Alert(TimeStampedModel):
    STATUS_CHOICES = [('OPEN', 'Open'), ('ACKNOWLEDGED', 'Acknowledged'), ('CLOSED', 'Closed')]
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True)
    alert_type = models.CharField(max_length=64)
    severity = models.CharField(max_length=16, default='MEDIUM')
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='OPEN')
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_alerts')
    resolved_at = models.DateTimeField(null=True, blank=True)


class DailyAISummary(TimeStampedModel):
    REVIEW_CHOICES = [('PENDING', 'Pending'), ('REVIEWED', 'Reviewed'), ('IGNORED', 'Ignored'), ('CONFIRMED', 'Confirmed'), ('EXPLANATION_REQUESTED', 'Employee Explanation Requested')]
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    active_seconds = models.PositiveIntegerField(default=0)
    idle_seconds = models.PositiveIntegerField(default=0)
    productive_seconds = models.PositiveIntegerField(default=0)
    neutral_seconds = models.PositiveIntegerField(default=0)
    unproductive_seconds = models.PositiveIntegerField(default=0)
    top_apps = models.JSONField(default=list, blank=True)
    top_websites = models.JSONField(default=list, blank=True)
    screenshot_count = models.PositiveIntegerField(default=0)
    unusual_activity_flags = models.JSONField(default=list, blank=True)
    summary_text = models.TextField(blank=True)
    risk_flags = models.JSONField(default=list, blank=True)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    manager_review_status = models.CharField(max_length=32, choices=REVIEW_CHOICES, default='PENDING')

    class Meta:
        unique_together = [('company', 'user', 'date')]


class ManagerReview(TimeStampedModel):
    ai_summary = models.ForeignKey(DailyAISummary, on_delete=models.CASCADE, related_name='reviews')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=32)
    remarks = models.TextField(blank=True)


class DemoTrialCode(TimeStampedModel):
    STATUS_CHOICES = [('ACTIVE', 'Active'), ('USED', 'Used'), ('EXPIRED', 'Expired'), ('CANCELLED', 'Cancelled'), ('CONVERTED', 'Converted')]
    code = models.CharField(max_length=64, unique=True)
    customer_company_name = models.CharField(max_length=255)
    contact_person_name = models.CharField(max_length=255, blank=True)
    mobile_number = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    trial_duration_days = models.PositiveIntegerField(default=7)
    allowed_users = models.PositiveIntegerField(default=5)
    allowed_devices = models.PositiveIntegerField(default=5)
    plan = models.ForeignKey(CompanyPlan, on_delete=models.PROTECT, null=True, blank=True)
    expiry_date = models.DateTimeField()
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='generated_trial_codes')
    sales_owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_trial_codes')
    lead_source = models.CharField(max_length=100, blank=True)
    remarks = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='ACTIVE')
    single_use = models.BooleanField(default=True)
    used_by_company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def generate_code(prefix='BOLD'):
        return f'{prefix}-{secrets.token_urlsafe(8).upper().replace("-", "").replace("_", "")[:12]}'


class TrialSignupLog(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    demo_code = models.ForeignKey(DemoTrialCode, on_delete=models.SET_NULL, null=True, blank=True)
    admin_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    signup_email = models.EmailField(blank=True)
    ip_address = models.CharField(max_length=64, blank=True)
    user_agent = models.TextField(blank=True)
    status = models.CharField(max_length=32, default='SUCCESS')
    message = models.TextField(blank=True)


class TrialConversionLog(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    demo_code = models.ForeignKey(DemoTrialCode, on_delete=models.SET_NULL, null=True, blank=True)
    converted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    old_plan = models.ForeignKey(CompanyPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='old_conversions')
    new_plan = models.ForeignKey(CompanyPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='new_conversions')
    billing_cycle = models.CharField(max_length=16, default='MONTHLY')
    notes = models.TextField(blank=True)


class ERPConnector(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, default='Glutape ERP')
    api_token = models.CharField(max_length=128, unique=True)
    is_active = models.BooleanField(default=True)
    allowed_event_types = models.JSONField(default=list, blank=True)
    token_rotated_at = models.DateTimeField(null=True, blank=True)


class ERPEvent(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    connector = models.ForeignKey(ERPConnector, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=64)
    external_id = models.CharField(max_length=128, blank=True)
    payload = models.JSONField(default=dict)
    received_at = models.DateTimeField(default=timezone.now)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True)


class ERPEmployeeMapping(TimeStampedModel):
    """Connector-scoped stable CRM employee ID linked to a WorkPulse User."""
    connector = models.ForeignKey(ERPConnector, on_delete=models.PROTECT, related_name='employee_mappings')
    external_id = models.CharField(max_length=128)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='erp_employee_mappings')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['connector', 'external_id'], name='unique_erp_employee_identity'),
            models.UniqueConstraint(fields=['connector', 'user'], name='unique_erp_connector_employee'),
        ]


class AuditLog(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action_type = models.CharField(max_length=100)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=100, blank=True)
    ip_address = models.CharField(max_length=64, blank=True)
    user_agent = models.TextField(blank=True)
    before_data = models.JSONField(default=dict, blank=True)
    after_data = models.JSONField(default=dict, blank=True)


class BillingInvoice(TimeStampedModel):
    STATUS_CHOICES = [('DRAFT', 'Draft'), ('ISSUED', 'Issued'), ('PAID', 'Paid'), ('VOID', 'Void')]
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True)
    invoice_number = models.CharField(max_length=64, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default='INR')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='DRAFT')
    billing_period_start = models.DateField(null=True, blank=True)
    billing_period_end = models.DateField(null=True, blank=True)
    provider = models.CharField(max_length=32, default='RAZORPAY_PLACEHOLDER')
    provider_reference = models.CharField(max_length=255, blank=True)
    line_description = models.CharField(max_length=255, blank=True)
    quantity = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    billing_cycle = models.CharField(max_length=16, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    payment_recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name='recorded_billing_payments')
    notes = models.TextField(blank=True)
    void_reason = models.TextField(blank=True)


class CRMLoginAttempt(models.Model):
    """Short-lived, one-use desktop handshakes; no CRM credentials stored."""
    secret_hash = models.CharField(max_length=64, unique=True)
    provider = models.CharField(max_length=64)
    challenge = models.CharField(max_length=43)
    redirect_uri = models.CharField(max_length=200)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
