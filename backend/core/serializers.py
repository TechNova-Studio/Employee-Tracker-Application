from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from decimal import Decimal
import re
from rest_framework import serializers
from .models import *
from .billing import active_users, billing_reason, estimate
from .employee_identity import (EmployeeIdentityError, assign_employee_id,
                                normalize_employee_id, normalize_prefix)


class ProfileSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    employee_id = serializers.CharField(source='employee_code', read_only=True)
    manager_name = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ['id', 'company', 'company_name', 'role', 'department', 'department_name', 'manager', 'manager_name', 'employee_id', 'employee_code', 'mobile', 'policy_status', 'can_generate_trials', 'is_active_employee']

    def get_manager_name(self, obj):
        return (obj.manager.get_full_name() or obj.manager.email or obj.manager.username) if obj.manager else ''


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    erp_mappings = serializers.SerializerMethodField()
    email = serializers.EmailField(required=True, allow_blank=False)
    password = serializers.CharField(write_only=True, required=False)
    role = serializers.ChoiceField(choices=Profile.ROLE_CHOICES, write_only=True, required=False)
    company = serializers.IntegerField(write_only=True, required=False)
    department = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    manager = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    employee_id = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=64)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'date_joined', 'password', 'role', 'company', 'department', 'manager', 'employee_id', 'profile', 'erp_mappings']
        read_only_fields = ['date_joined']

    def get_erp_mappings(self, obj):
        request = self.context.get('request')
        actor_profile = getattr(getattr(request, 'user', None), 'profile', None)
        role = getattr(actor_profile, 'role', None)
        if role not in ('SUPER_ADMIN', 'COMPANY_ADMIN', 'HR_ADMIN'):
            return []
        profile = getattr(obj, 'profile', None)
        company_id = getattr(profile, 'company_id', None)
        if not company_id or profile.role == 'SUPER_ADMIN':
            return []
        if role != 'SUPER_ADMIN' and actor_profile.company_id != company_id:
            return []
        return [{'connector_id': mapping.connector_id, 'connector_name': mapping.connector.name,
                 'connector_active': mapping.connector.is_active, 'external_id': mapping.external_id}
                for mapping in obj.erp_employee_mappings.all()
                if mapping.connector.company_id == company_id]

    def validate_employee_id(self, value):
        try:
            return normalize_employee_id(value)
        except EmployeeIdentityError as exc:
            raise serializers.ValidationError(str(exc))

    def validate(self, attrs):
        profile = getattr(self.instance, 'profile', None)
        company_id = attrs.get('company', getattr(profile, 'company_id', None))
        role = attrs.get('role', getattr(profile, 'role', 'EMPLOYEE'))
        if role != 'SUPER_ADMIN' and not Company.objects.filter(pk=company_id).exists():
            raise serializers.ValidationError({'company': 'Select an existing company for this employee.'})
        if self.instance and ERPEmployeeMapping.objects.filter(user=self.instance).exists():
            if company_id != getattr(profile, 'company_id', None):
                raise serializers.ValidationError({'company': 'A CRM-linked employee cannot be moved to another company.'})
            if role == 'SUPER_ADMIN':
                raise serializers.ValidationError({'role': 'A CRM-linked employee must use a company role.'})
        if attrs.get('department') is not None:
            department = Department.objects.filter(pk=attrs['department'], company_id=company_id).first()
            if not department:
                raise serializers.ValidationError({'department': 'Department must belong to this employee company.'})
            if not department.is_active and attrs['department'] != getattr(profile, 'department_id', None):
                raise serializers.ValidationError({'department': 'Select an active department.'})
        if attrs.get('manager') is not None:
            manager = User.objects.select_related('profile').filter(pk=attrs['manager'], profile__company_id=company_id).first()
            if not manager:
                raise serializers.ValidationError({'manager': 'Manager must belong to this employee company.'})
            if self.instance and manager.pk == self.instance.pk:
                raise serializers.ValidationError({'manager': 'An employee cannot be their own manager.'})
            if manager.pk != getattr(profile, 'manager_id', None) and (
                    not manager.is_active or not manager.profile.is_active_employee or
                    manager.profile.role not in ('MANAGER', 'COMPANY_ADMIN', 'HR_ADMIN', 'SALES_ADMIN')):
                raise serializers.ValidationError({'manager': 'Select an active manager from this company.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop('password', None)
        role = validated_data.pop('role', 'EMPLOYEE')
        company_id = validated_data.pop('company', None)
        department_id = validated_data.pop('department', None)
        manager_id = validated_data.pop('manager', None)
        employee_id = validated_data.pop('employee_id', '')
        company = Company.objects.select_for_update().filter(id=company_id).first() if company_id else None
        if company and User.objects.filter(profile__company=company, email__iexact=validated_data.get('email', '')).exists():
            raise serializers.ValidationError({'email': 'An employee already uses this email in the company.'})
        try:
            employee_id = assign_employee_id(company, employee_id) if company and role != 'SUPER_ADMIN' else ''
        except EmployeeIdentityError as exc:
            raise serializers.ValidationError({'employee_id': str(exc)})
        if not validated_data.get('username'):
            validated_data['username'] = validated_data.get('email')
        user = User.objects.create_user(password=password, **validated_data)
        department = Department.objects.filter(id=department_id).first() if department_id else None
        manager = User.objects.filter(id=manager_id).first() if manager_id else None
        Profile.objects.create(user=user, company=company, department=department, manager=manager, role=role, employee_code=employee_id, can_generate_trials=role in ['SUPER_ADMIN','COMPANY_ADMIN','SALES_ADMIN'])
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        profile_fields = {k: validated_data.pop(k) for k in ['role', 'company', 'department', 'manager'] if k in validated_data}
        employee_id = validated_data.pop('employee_id', None)
        profile = getattr(instance, 'profile', None)
        company_id = profile_fields.get('company', getattr(profile, 'company_id', None))
        company = Company.objects.select_for_update().filter(pk=company_id).first() if company_id else None
        if company and 'email' in validated_data and User.objects.filter(
            profile__company=company, email__iexact=validated_data['email']).exclude(pk=instance.pk).exists():
            raise serializers.ValidationError({'email': 'An employee already uses this email in the company.'})
        if profile and company and (employee_id is not None or 'company' in profile_fields):
            requested = employee_id if employee_id is not None else profile.employee_code
            if employee_id == '' and profile.employee_code:
                raise serializers.ValidationError({'employee_id': 'An assigned employee ID cannot be cleared.'})
            try:
                profile.employee_code = assign_employee_id(company, requested, user_id=instance.pk)
            except EmployeeIdentityError as exc:
                raise serializers.ValidationError({'employee_id': str(exc)})
        password = validated_data.pop('password', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)
        instance.save()
        if hasattr(instance, 'profile'):
            profile = instance.profile
            if 'role' in profile_fields:
                profile.role = profile_fields['role']
                profile.can_generate_trials = profile.role in ['SUPER_ADMIN','COMPANY_ADMIN','SALES_ADMIN']
            if 'company' in profile_fields:
                profile.company = Company.objects.filter(id=profile_fields['company']).first()
            if 'department' in profile_fields:
                profile.department = Department.objects.filter(id=profile_fields['department']).first()
            if 'manager' in profile_fields:
                profile.manager = User.objects.filter(id=profile_fields['manager']).first()
            profile.save()
        return instance


class CompanyPlanSerializer(serializers.ModelSerializer):
    price_per_user = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.00'))
    max_users = serializers.IntegerField(min_value=1, max_value=100000, default=10)
    max_devices = serializers.IntegerField(min_value=1, max_value=100000, default=10)
    screenshot_retention_days = serializers.IntegerField(min_value=1, max_value=3650, default=30)

    class Meta:
        model = CompanyPlan
        fields = '__all__'

    def validate(self, attrs):
        code = attrs.get('code', getattr(self.instance, 'code', None))
        if self.instance and code != self.instance.code:
            raise serializers.ValidationError({'code': 'Plan codes cannot be changed after creation.'})
        price = attrs.get('price_per_user', getattr(self.instance, 'price_per_user', Decimal('0')))
        if code in ('INTERNAL', 'TRIAL') and price != 0:
            raise serializers.ValidationError({'price_per_user': 'Internal and Trial plans must have a zero rate.'})
        return attrs


class CompanySerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    is_trial_expired = serializers.SerializerMethodField()

    class Meta:
        model = Company
        exclude = ['next_employee_number']

    def validate_employee_id_prefix(self, value):
        try:
            return normalize_prefix(value)
        except EmployeeIdentityError as exc:
            raise serializers.ValidationError(str(exc))

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = Company.objects.select_for_update().get(pk=instance.pk)
        return super().update(instance, validated_data)

    def get_is_trial_expired(self, obj):
        return obj.is_trial_expired()


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = '__all__'
        read_only_fields = ['company']
        # Company is assigned by the view; duplicate names are validated there.
        validators = []


class SubscriptionSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    company_status = serializers.CharField(source='company.status', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    plan_code = serializers.CharField(source='plan.code', read_only=True)
    live_user_count = serializers.SerializerMethodField()
    is_billable = serializers.SerializerMethodField()
    billing_reason = serializers.SerializerMethodField()
    estimated_amount = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = '__all__'

    def get_live_user_count(self, obj):
        return obj.live_user_count if hasattr(obj, 'live_user_count') else active_users(obj.company)

    def get_billing_reason(self, obj):
        return billing_reason(obj) or ('No active users to bill' if not self.get_live_user_count(obj) else '')

    def get_is_billable(self, obj):
        return not self.get_billing_reason(obj)

    def get_estimated_amount(self, obj):
        return str(estimate(obj, self.get_live_user_count(obj))) if self.get_is_billable(obj) else None

    def get_currency(self, obj):
        return 'INR'


class SubscriptionConfigureSerializer(serializers.Serializer):
    company_id = serializers.IntegerField(min_value=1)
    plan_id = serializers.PrimaryKeyRelatedField(source='plan', queryset=CompanyPlan.objects.filter(is_active=True))
    billing_cycle = serializers.ChoiceField(choices=['MONTHLY', 'ANNUAL', 'NONE'])


class InvoiceCreateSerializer(serializers.Serializer):
    subscription_id = serializers.IntegerField(min_value=1)
    billing_period_start = serializers.DateField()
    notes = serializers.CharField(max_length=2000, allow_blank=True, default='')


class PaymentRecordSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=255)


class InvoiceVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000)


class DeviceSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = Device
        fields = '__all__'


class AgentVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentVersion
        fields = '__all__'
        read_only_fields = ['company']

    def validate(self, attrs):
        import re

        latest = attrs.get('latest_version', getattr(self.instance, 'latest_version', ''))
        minimum = attrs.get('minimum_supported_version', getattr(self.instance, 'minimum_supported_version', ''))
        for field, value in [('latest_version', latest), ('minimum_supported_version', minimum)]:
            if not re.fullmatch(r'\d+(?:\.\d+){0,2}', value):
                raise serializers.ValidationError({field: 'Use a numeric version such as 1.2.3.'})
        def parts(value):
            return tuple(int(part) for part in (value.split('.') + ['0', '0'])[:3])
        if parts(minimum) > parts(latest):
            raise serializers.ValidationError({'minimum_supported_version': 'Minimum supported version cannot exceed latest version.'})
        platform = attrs.get('platform', getattr(self.instance, 'platform', ''))
        if not platform or not platform.strip():
            raise serializers.ValidationError({'platform': 'Platform is required.'})
        attrs['platform'] = platform.strip().lower()
        return attrs


class PolicyVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyVersion
        fields = '__all__'
        read_only_fields = ['company', 'created_by']
        validators = []

    def validate(self, attrs):
        for field in ('version', 'title', 'body'):
            value = attrs.get(field)
            if value is not None:
                if not isinstance(value, str) or not value.strip():
                    raise serializers.ValidationError({field: 'This field cannot be empty.'})
                attrs[field] = value.strip()
        return attrs


class PolicyAcceptanceSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    policy_title = serializers.CharField(source='policy.title', read_only=True)
    policy_version = serializers.CharField(source='policy.version', read_only=True)

    class Meta:
        model = PolicyAcceptance
        fields = '__all__'


class WorkSessionSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    device_name = serializers.CharField(source='device.hostname', read_only=True)

    class Meta:
        model = WorkSession
        fields = '__all__'


class HeartbeatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Heartbeat
        fields = '__all__'


class ActivityLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = ActivityLog
        fields = '__all__'


class ScreenshotSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    device_name = serializers.CharField(source='device.hostname', read_only=True, default='')
    protected_view_url = serializers.SerializerMethodField()
    protected_download_url = serializers.SerializerMethodField()

    class Meta:
        model = Screenshot
        fields = ['id', 'company', 'company_name', 'user', 'user_email', 'device', 'device_name', 'session', 'captured_at', 'storage_mode', 'checksum', 'status', 'deleted_at', 'created_at', 'updated_at', 'protected_view_url', 'protected_download_url']
        read_only_fields = fields

    def get_protected_view_url(self, obj):
        request = self.context.get('request')
        path = f'/api/screenshots/{obj.id}/view/'
        return request.build_absolute_uri(path) if request else path

    def get_protected_download_url(self, obj):
        request = self.context.get('request')
        path = f'/api/screenshots/{obj.id}/download/'
        return request.build_absolute_uri(path) if request else path


class ScreenshotAccessLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScreenshotAccessLog
        fields = '__all__'


class AppWebsiteCategorySerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = AppWebsiteCategory
        fields = '__all__'


class AlertSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = Alert
        fields = '__all__'


class DailyAISummarySerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    analysis_mode = serializers.SerializerMethodField()

    class Meta:
        model = DailyAISummary
        fields = '__all__'

    def get_analysis_mode(self, obj):
        return 'RULE_BASED'


class ManagerReviewSerializer(serializers.ModelSerializer):
    reviewed_by_email = serializers.CharField(source='reviewed_by.email', read_only=True)
    summary_updated_at = serializers.DateTimeField(write_only=True, required=False)
    status = serializers.ChoiceField(choices=[item for item in DailyAISummary.REVIEW_CHOICES if item[0] != 'PENDING'])

    class Meta:
        model = ManagerReview
        fields = '__all__'
        read_only_fields = ['reviewed_by', 'created_at', 'updated_at']
        extra_kwargs = {'remarks': {'max_length': 4000}}

    def validate(self, attrs):
        if attrs.get('status') == 'EXPLANATION_REQUESTED' and not attrs.get('remarks', '').strip():
            raise serializers.ValidationError({'remarks': 'Describe the clarification requested.'})
        return attrs


class DemoTrialCodeSerializer(serializers.ModelSerializer):
    generated_by_email = serializers.CharField(source='generated_by.email', read_only=True)
    sales_owner_email = serializers.CharField(source='sales_owner.email', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    effective_status = serializers.SerializerMethodField()
    trial_duration_days = serializers.IntegerField(min_value=1, max_value=90, default=7)
    allowed_users = serializers.IntegerField(min_value=1, max_value=100000, default=5)
    allowed_devices = serializers.IntegerField(min_value=1, max_value=100000, default=5)

    class Meta:
        model = DemoTrialCode
        fields = '__all__'
        read_only_fields = ['code', 'generated_by', 'status', 'used_by_company', 'used_at']

    def get_effective_status(self, obj):
        return 'EXPIRED' if obj.status == 'ACTIVE' and obj.expiry_date <= timezone.now() else obj.status

    def validate_expiry_date(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError('Choose a future expiry date.')
        return value

    def validate(self, attrs):
        plan = attrs.get('plan') or CompanyPlan.objects.filter(code='TRIAL', is_active=True).first()
        if not plan or plan.code != 'TRIAL' or not plan.is_active:
            raise serializers.ValidationError({'plan': 'An active TRIAL plan must be configured.'})
        for field, maximum in [('allowed_users', plan.max_users), ('allowed_devices', plan.max_devices)]:
            if attrs.get(field, 5) > maximum:
                raise serializers.ValidationError({field: f'Trial plan limit is {maximum}.'})
        attrs['plan'] = plan
        return attrs


class TrialCodeInputSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)

    def validate_code(self, value):
        return value.strip().upper()


class TrialSignupInputSerializer(TrialCodeInputSerializer):
    company_name = serializers.CharField(max_length=255)
    admin_name = serializers.CharField(max_length=150)
    admin_email = serializers.EmailField(max_length=150)
    mobile = serializers.CharField(max_length=30, required=False, allow_blank=True, default='')
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    employee_id_prefix = serializers.CharField(max_length=32, required=False, allow_blank=True, default='')

    def validate_employee_id_prefix(self, value):
        return CompanySerializer().validate_employee_id_prefix(value)

    def validate_admin_email(self, value):
        value = value.lower()
        if User.objects.filter(models.Q(email__iexact=value) | models.Q(username__iexact=value)).exists():
            raise serializers.ValidationError('An account already uses this email. Sign in or use a different email.')
        return value

    def validate(self, attrs):
        user = User(username=attrs['admin_email'], email=attrs['admin_email'], first_name=attrs['admin_name'])
        try:
            validate_password(attrs['password'], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages})
        return attrs


class TrialExtendInputSerializer(serializers.Serializer):
    company_id = serializers.IntegerField(min_value=1)
    days = serializers.IntegerField(min_value=1, max_value=90)


class TrialConvertInputSerializer(serializers.Serializer):
    company_id = serializers.IntegerField(min_value=1)
    plan_code = serializers.ChoiceField(choices=['BASIC', 'PRO', 'BUSINESS', 'ENTERPRISE', 'INTERNAL'])
    billing_cycle = serializers.ChoiceField(choices=['MONTHLY', 'ANNUAL', 'NONE'])
    notes = serializers.CharField(max_length=2000, allow_blank=True, default='')


class TrialCompanyInputSerializer(serializers.Serializer):
    company_id = serializers.IntegerField(min_value=1)


class TrialSignupLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrialSignupLog
        fields = '__all__'


class TrialConversionLogSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = TrialConversionLog
        fields = '__all__'


class ERPConnectorSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    token_hint = serializers.SerializerMethodField()
    event_count = serializers.IntegerField(read_only=True, default=0)
    last_received_at = serializers.DateTimeField(read_only=True, allow_null=True, default=None)
    allowed_event_types = serializers.ListField(child=serializers.CharField(max_length=64), min_length=0, max_length=50)

    class Meta:
        model = ERPConnector
        fields = ['id', 'company', 'company_name', 'name', 'is_active', 'allowed_event_types', 'token_hint',
                  'token_rotated_at', 'event_count', 'last_received_at', 'created_at', 'updated_at']
        read_only_fields = ['company', 'token_rotated_at', 'created_at', 'updated_at']

    def get_token_hint(self, obj):
        return '••••••••' + obj.api_token[-4:] if obj.api_token else 'Not configured'

    def validate_allowed_event_types(self, values):
        if any(not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', value) for value in values):
            raise serializers.ValidationError('Event names must use lowercase letters, digits and underscores.')
        return list(dict.fromkeys(values))

    def validate(self, attrs):
        if 'api_token' in self.initial_data:
            raise serializers.ValidationError({'api_token': 'Tokens are generated by the server. Use Rotate token to change one.'})
        if self.instance and 'company' in self.initial_data and str(self.initial_data['company']) != str(self.instance.company_id):
            raise serializers.ValidationError({'company': 'A connector cannot be moved to another company.'})
        active = attrs.get('is_active', getattr(self.instance, 'is_active', True))
        events = attrs.get('allowed_event_types', getattr(self.instance, 'allowed_event_types', []))
        if active and not events:
            raise serializers.ValidationError({'allowed_event_types': 'Select at least one event before enabling this connector.'})
        return attrs


class ERPEventSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    connector_name = serializers.CharField(source='connector.name', read_only=True, default='Deleted connector')
    employee_email = serializers.SerializerMethodField()
    employee_id = serializers.SerializerMethodField()
    processing_status = serializers.SerializerMethodField()
    class Meta:
        model = ERPEvent
        fields = '__all__'

    def get_processing_status(self, obj):
        from .erp_employee_sync import EMPLOYEE_EVENTS
        return ('PROCESSED' if obj.processed else 'FAILED' if obj.processing_error else
                'PENDING' if obj.event_type in EMPLOYEE_EVENTS else 'RECEIVED')

    def get_employee_email(self, obj):
        return obj.payload.get('email', '') if isinstance(obj.payload, dict) and obj.event_type.startswith('erp_user_') else ''

    def get_employee_id(self, obj):
        return obj.payload.get('employee_id', obj.payload.get('employee_code', '')) if isinstance(obj.payload, dict) and obj.event_type.startswith('erp_user_') else ''

    def get_fields(self):
        fields = super().get_fields()
        if getattr(self.context.get('view'), 'action', '') == 'list':
            fields.pop('payload', None)
        return fields


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.CharField(source='actor.email', read_only=True)
    before_data = serializers.SerializerMethodField()
    after_data = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = '__all__'

    @staticmethod
    def redact(value):
        if isinstance(value, dict):
            return {key: '[redacted]' if key.lower() in {'api_token', 'token', 'password', 'secret'} else AuditLogSerializer.redact(item)
                    for key, item in value.items()}
        if isinstance(value, list):
            return [AuditLogSerializer.redact(item) for item in value]
        return value

    def get_before_data(self, obj):
        return self.redact(obj.before_data)

    def get_after_data(self, obj):
        return self.redact(obj.after_data)


class BillingInvoiceSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    payment_recorded_by_email = serializers.CharField(source='payment_recorded_by.email', read_only=True, default='')

    class Meta:
        model = BillingInvoice
        fields = '__all__'  
