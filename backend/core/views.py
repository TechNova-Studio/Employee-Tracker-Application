from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Sum, Count, Max
from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils.dateparse import parse_date
from datetime import timedelta
from rest_framework import mixins, serializers, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import *
from .serializers import *
from .permissions import *
from .erp_employee_sync import EMPLOYEE_EVENTS, EmployeeSyncError, validate_employee_event, ingest_employee_event
from .employee_identity import assign_employee_id
from .ai_summaries import generate_summaries
from .billing import configure_subscription, create_invoice, transition_invoice
from .erp_catalog import event_options
from .activity_context import normalize_web_context, url_rule_matches
import secrets
import logging
import hashlib
import mimetypes

logger = logging.getLogger(__name__)


def client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def version_tuple(version):
    try:
        parts = [int(part) for part in str(version or '0.0.0').split('.')[:3]]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts)
    except Exception:
        return (0, 0, 0)


def is_super_admin(user):
    return is_super_admin_user(user)


def user_company(user):
    if user and user.is_authenticated and hasattr(user, 'profile'):
        return user.profile.company
    return None


def admin_company_scope(request, qs, company_field='company_id'):
    company = user_company(request.user)
    if not is_super_admin(request.user):
        if not company:
            return qs.none()
        qs = qs.filter(**{company_field: company.pk})
    selected = request.query_params.get('company_id')
    if selected:
        company_id = serializers.IntegerField(min_value=1).run_validation(selected)
        if not is_super_admin(request.user) and company_id != getattr(company, 'pk', None):
            raise PermissionDenied('Cannot access another company.')
        qs = qs.filter(**{company_field: company_id})
    return qs


def can_manage_trials(user):
    if is_super_admin(user):
        return True
    return bool(hasattr(user, 'profile') and user.profile.role in ['COMPANY_ADMIN', 'SALES_ADMIN'] and user.profile.can_generate_trials)


def create_audit(request, action_type, obj=None, before=None, after=None, company=None):
    try:
        AuditLog.objects.create(
            company=company or user_company(request.user),
            actor=request.user if request.user.is_authenticated else None,
            action_type=action_type,
            object_type=obj.__class__.__name__ if obj else '',
            object_id=str(getattr(obj, 'id', '')) if obj else '',
            ip_address=client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            before_data=before or {},
            after_data=after or {},
        )
    except Exception:
        pass


def latest_agent_version(platform='windows', company=None):
    qs = AgentVersion.objects.filter(platform=platform or 'windows', is_active=True)
    if company:
        version = qs.filter(company=company).order_by('-id').first()
        if version:
            return version
    return qs.filter(company__isnull=True).order_by('-id').first()


def agent_version_payload(platform, installed_version, company=None):
    version = latest_agent_version(platform, company)
    latest = version.latest_version if version else settings.DEFAULT_AGENT_LATEST_VERSION
    minimum = version.minimum_supported_version if version else settings.DEFAULT_AGENT_MINIMUM_SUPPORTED_VERSION
    return {
        'latest_version': latest,
        'minimum_supported_version': minimum,
        'force_update_required': version_tuple(installed_version) < version_tuple(minimum),
        'download_url': version.download_url if version and version.download_url else settings.DESKTOP_AGENT_DOWNLOAD_URL,
        'checksum': version.checksum if version else '',
        'release_notes': version.release_notes if version else 'Initial staging release',
        'platform': platform or 'windows',
    }


def create_outdated_agent_alert(company, user, device=None, payload=None):
    if not company or not user or not user.is_authenticated:
        return
    Alert.objects.get_or_create(
        company=company,
        user=user,
        device=device,
        alert_type='OUTDATED_AGENT',
        status='OPEN',
        defaults={
            'severity': 'HIGH',
            'title': 'Outdated desktop agent',
            'message': f"Installed agent is below minimum supported version {payload.get('minimum_supported_version') if payload else ''}. Update required.",
        }
    )


def unsupported_agent_response(request, company=None, user=None, device=None):
    platform = request.data.get('platform') or request.query_params.get('platform') or getattr(device, 'platform', '') or 'windows'
    installed_version = request.data.get('app_version') or request.query_params.get('version') or getattr(device, 'app_version', '') or '0.0.0'
    payload = agent_version_payload(platform, installed_version, company=company)
    if payload['force_update_required']:
        create_outdated_agent_alert(company, user or request.user, device, payload)
        return Response({'detail': 'Desktop agent version is not supported. Update required.', 'blocked': True, 'blocked_reason': 'OUTDATED_AGENT', 'version': payload}, status=426)
    return None


def latest_active_policy(company):
    if not company:
        return None
    return PolicyVersion.objects.filter(company=company, is_active=True).order_by('-id').first()


def has_accepted_latest_policy(user, company):
    policy = latest_active_policy(company)
    if not policy:
        return False, None
    profile = getattr(user, 'profile', None)
    accepted = bool(profile and profile.is_active_employee and profile.policy_status == 'ACCEPTED'
                    and PolicyAcceptance.objects.filter(company=company, user=user, policy=policy, status='ACCEPTED').exists())
    return accepted, policy


def policy_upload_gate(request, company):
    blocked = company_tracking_gate(company)
    if blocked:
        return blocked
    profile = getattr(request.user, 'profile', None)
    accepted, policy = has_accepted_latest_policy(request.user, company)
    if accepted:
        return None
    WorkSession.objects.filter(company=company, user=request.user, status='RUNNING').update(
        status='AUTO_STOPPED', stopped_at=timezone.now())
    reason = ('EMPLOYEE_INACTIVE' if profile and not profile.is_active_employee else
              'POLICY_DECLINED' if profile and profile.policy_status == 'POLICY_DECLINED' else
              'POLICY_NOT_ACCEPTED' if policy else 'POLICY_NOT_CONFIGURED')
    return Response({'detail': 'The current monitoring policy must be accepted before tracking.',
                     'blocked': True, 'blocked_reason': reason,
                     'policy_id': getattr(policy, 'pk', None)}, status=403)


def role_scoped_user_filter(request, qs):
    if is_super_admin(request.user):
        return qs
    company = user_company(request.user)
    if not company:
        return qs.none()
    qs = qs.filter(company=company)
    role = get_role(request.user)
    if role == 'MANAGER':
        return qs.filter(user__profile__manager=request.user)
    if role == 'EMPLOYEE':
        return qs.filter(user=request.user)
    return qs


def filter_operations(request, qs, date_field, statuses=None):
    qs = role_scoped_user_filter(request, qs)
    company_id = request.query_params.get('company_id')
    if company_id:
        if not company_id.isdigit():
            raise ValidationError({'company_id': 'Select a valid company.'})
        if not is_super_admin(request.user) and str(getattr(user_company(request.user), 'pk', '')) != company_id:
            raise PermissionDenied('Cannot view another company.')
        qs = qs.filter(company_id=company_id)
    user_id = request.query_params.get('user_id')
    if user_id:
        if not user_id.isdigit():
            raise ValidationError({'user_id': 'Select a valid employee.'})
        qs = qs.filter(user_id=user_id)
    dates = {}
    for param, lookup in (('from_date', 'gte'), ('to_date', 'lte')):
        value = request.query_params.get(param)
        if value:
            try:
                parsed = parse_date(value)
            except ValueError:
                parsed = None
            if parsed is None:
                raise ValidationError({param: 'Use YYYY-MM-DD.'})
            dates[param] = parsed
            date_lookup = date_field if date_field == 'date' else f'{date_field}__date'
            qs = qs.filter(**{f'{date_lookup}__{lookup}': parsed})
    if 'from_date' in dates and 'to_date' in dates and dates['from_date'] > dates['to_date']:
        raise ValidationError({'to_date': 'End date must not precede start date.'})
    if statuses:
        status = request.query_params.get('status' if date_field == 'started_at' else 'productivity')
        if status:
            if status not in statuses:
                raise ValidationError({'status': 'Select a valid status/category.'})
            qs = qs.filter(**{'status' if date_field == 'started_at' else 'productivity': status})
    return qs


def operations_users(user):
    qs = User.objects.filter(profile__company__isnull=False).select_related('profile')
    if is_super_admin(user):
        return qs
    qs = qs.filter(profile__company=user_company(user))
    if get_role(user) == 'MANAGER':
        qs = qs.filter(profile__manager=user)
    elif get_role(user) == 'EMPLOYEE':
        qs = qs.filter(pk=user.pk)
    return qs


def operations_options(request):
    companies = Company.objects.all() if is_super_admin(request.user) else Company.objects.filter(
        pk=getattr(user_company(request.user), 'pk', None))
    users = operations_users(request.user)
    company_id = request.query_params.get('company_id')
    if company_id:
        if not company_id.isdigit() or not companies.filter(pk=company_id).exists():
            raise ValidationError({'company_id': 'Select a company in your scope.'})
        users = users.filter(profile__company_id=company_id)
    elif is_super_admin(request.user):
        users = users.none()
    return Response({'companies': list(companies.order_by('name').values('id', 'name')),
                     'users': list(users.order_by('email', 'id').values('id', 'email', 'first_name', 'username'))})


def expire_trial_companies(qs):
    with transaction.atomic():
        eligible = qs.filter(status='TRIAL_ACTIVE', trial_end_date__lte=timezone.now()).values('pk')
        ids = list(Company.objects.select_for_update().filter(pk__in=eligible, status='TRIAL_ACTIVE',
                   trial_end_date__lte=timezone.now())
                   .values_list('id', flat=True))
        Company.objects.filter(pk__in=ids, status='TRIAL_ACTIVE').update(status='TRIAL_EXPIRED')
        Subscription.objects.filter(company_id__in=ids, status='TRIAL').update(status='EXPIRED')
        WorkSession.objects.filter(company_id__in=ids, status='RUNNING').update(
            status='AUTO_STOPPED', stopped_at=timezone.now())


def company_tracking_gate(company):
    if not company:
        return Response({'detail': 'No company assigned.'}, status=403)
    if company.status == 'TRIAL_ACTIVE' and company.is_trial_expired():
        expire_trial_companies(Company.objects.filter(pk=company.pk))
        company.status = 'TRIAL_EXPIRED'
    if company.status in ('SUSPENDED', 'TRIAL_EXPIRED'):
        WorkSession.objects.filter(company=company, status='RUNNING').update(
            status='AUTO_STOPPED', stopped_at=timezone.now())
        return Response({'detail': 'Company is suspended or its trial has expired. Contact your administrator.',
                         'blocked': True, 'blocked_reason': company.status}, status=403)
    return None


def allowed_trial_code_queryset(user):
    qs = DemoTrialCode.objects.select_related('generated_by', 'sales_owner', 'used_by_company', 'plan').all()
    if is_super_admin(user):
        return qs
    company = user_company(user)
    if not company or not can_manage_trials(user):
        return DemoTrialCode.objects.none()
    role = get_role(user)
    if role == 'SALES_ADMIN':
        # Sales/Admin is limited to trials personally generated by them or assigned to them.
        # They cannot extend/convert/cancel a random trial company merely by guessing company_id.
        return qs.filter(models.Q(generated_by=user) | models.Q(sales_owner=user))
    if role == 'COMPANY_ADMIN':
        # Company Admin may manage trial codes owned by users of their own company.
        return qs.filter(models.Q(generated_by__profile__company=company) | models.Q(sales_owner__profile__company=company))
    return DemoTrialCode.objects.none()


def allowed_trial_company_queryset(user):
    codes = allowed_trial_code_queryset(user)
    company_ids = codes.exclude(used_by_company__isnull=True).values_list('used_by_company_id', flat=True)
    signup_ids = TrialSignupLog.objects.filter(demo_code__in=codes, status='SUCCESS').values_list('company_id', flat=True)
    scope = models.Q(id__in=company_ids) | models.Q(id__in=signup_ids)
    if is_super_admin(user):
        scope |= models.Q(trial_start_date__isnull=False) | models.Q(status__in=['TRIAL_ACTIVE', 'TRIAL_EXPIRED'])
    return Company.objects.filter(scope).select_related('plan').distinct()


def get_scoped_trial_company(user, company_id):
    return allowed_trial_company_queryset(user).filter(id=company_id).first()


def screenshot_queryset_for_user(user):
    qs = Screenshot.objects.select_related('company', 'user', 'device', 'session').filter(deleted_at__isnull=True)
    if is_super_admin(user):
        return qs
    company = user_company(user)
    if not company:
        return qs.none()
    qs = qs.filter(company=company)
    role = get_role(user)
    if role == 'MANAGER':
        return qs.filter(user__profile__manager=user)
    if role == 'EMPLOYEE':
        return qs.filter(user=user)
    return qs


class TenantModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrReadOnlyScoped]
    company_field = 'company'

    def get_queryset(self):
        qs = super().get_queryset()
        if is_super_admin(self.request.user):
            return qs
        company = user_company(self.request.user)
        if not company:
            return qs.none()
        return qs.filter(**{self.company_field: company})

    def perform_create(self, serializer):
        company = user_company(self.request.user)
        if is_super_admin(self.request.user) and self.request.data.get('company'):
            company = Company.objects.filter(id=self.request.data.get('company')).first()
        obj = serializer.save(company=company)
        create_audit(self.request, 'CREATE', obj=obj, after=serializer.data, company=company)

    def perform_update(self, serializer):
        before = {}
        try:
            before = self.get_serializer(self.get_object()).data
        except Exception:
            pass
        obj = serializer.save()
        create_audit(self.request, 'UPDATE', obj=obj, before=dict(before), after=serializer.data, company=getattr(obj, 'company', user_company(self.request.user)))


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    return Response({'status': 'ok', 'product': 'BOLD WorkPulse', 'timestamp': timezone.now()})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = str(request.data.get('email') or request.data.get('username') or '').strip()
        password = request.data.get('password')
        user = authenticate(username=username, password=password)
        if user is None:
            user = User.objects.filter(email__iexact=username).first()
            if user and not user.check_password(password):
                user = None
        if not user or not user.is_active:
            return Response({'detail': 'Invalid login or inactive user.'}, status=400)
        profile = getattr(user, 'profile', None)
        company = profile.company if profile else None
        if request.data.get('app_version') and not company:
            return Response({'blocked': True, 'blocked_reason': 'NO_COMPANY',
                             'detail': 'Desktop login requires a user assigned to a company.'}, status=403)
        if profile and profile.policy_status == 'POLICY_DECLINED':
            create_audit(request, 'LOGIN_BLOCKED_POLICY_DECLINED', obj=user, company=company)
            return Response({'blocked': True, 'blocked_reason': 'POLICY_DECLINED', 'detail': 'Monitoring policy was declined. HR/Admin must reactivate this employee before login.'}, status=403)
        if profile and not profile.is_active_employee:
            create_audit(request, 'LOGIN_BLOCKED_INACTIVE_EMPLOYEE', obj=user, company=company)
            return Response({'blocked': True, 'blocked_reason': 'EMPLOYEE_INACTIVE', 'detail': 'Employee profile is inactive.'}, status=403)
        if request.data.get('app_version'):
            blocked = unsupported_agent_response(request, company=company, user=user)
            if blocked:
                return blocked
        if company and company.status == 'TRIAL_ACTIVE' and company.is_trial_expired():
            expire_trial_companies(Company.objects.filter(pk=company.pk))
            company.refresh_from_db()
        token, _ = Token.objects.get_or_create(user=user)
        create_audit(request, 'LOGIN', obj=user, company=company)
        return Response({
            'token': token.key,
            'user': UserSerializer(user).data,
            'company': CompanySerializer(company).data if company else None,
            'screenshot_interval_seconds': company.screenshot_interval_seconds if company else settings.DEFAULT_SCREENSHOT_INTERVAL_SECONDS,
            'idle_threshold_seconds': company.idle_threshold_seconds if company else settings.DEFAULT_IDLE_THRESHOLD_SECONDS,
        })


class LogoutView(APIView):
    def post(self, request):
        create_audit(request, 'LOGOUT')
        return Response({'status': 'logged_out'})


class CurrentUserView(APIView):
    def get(self, request):
        company = user_company(request.user)
        return Response({'user': UserSerializer(request.user).data, 'company': CompanySerializer(company).data if company else None})


class CompanyPlanViewSet(viewsets.ModelViewSet):
    queryset = CompanyPlan.objects.all().order_by('id')
    serializer_class = CompanyPlanSerializer
    permission_classes = [IsCompanyPlanPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_super_admin(self.request.user):
            return qs
        # Company Admin / HR/Admin / Sales/Admin may read only active plans for display/trial conversion.
        return qs.filter(is_active=True)

    def perform_create(self, serializer):
        obj = serializer.save()
        create_audit(self.request, 'CREATE_COMPANY_PLAN', obj=obj, after=serializer.data)

    def perform_update(self, serializer):
        before = CompanyPlanSerializer(self.get_object()).data
        obj = serializer.save()
        create_audit(self.request, 'UPDATE_COMPANY_PLAN', obj=obj, before=dict(before), after=serializer.data)

    def destroy(self, request, *args, **kwargs):
        return Response({'detail': 'Deactivate a plan to preserve subscription and invoice history.'}, status=405)


class CompanyViewSet(TenantModelViewSet):
    queryset = Company.objects.all().order_by('-id')
    serializer_class = CompanySerializer
    company_field = 'id'
    permission_classes = [IsCompanyPermission]
    company_admin_basic_fields = {
        'name', 'legal_name', 'contact_person', 'email', 'mobile',
        'employee_id_prefix',
        'screenshot_interval_seconds', 'screenshot_retention_days', 'idle_threshold_seconds'
    }

    def get_queryset(self):
        if is_super_admin(self.request.user):
            return Company.objects.all().order_by('-id')
        company = user_company(self.request.user)
        if get_role(self.request.user) == 'COMPANY_ADMIN' and company:
            return Company.objects.filter(id=company.id)
        return Company.objects.none()

    def perform_create(self, serializer):
        obj = serializer.save()
        create_audit(self.request, 'CREATE_COMPANY', obj=obj, after=serializer.data, company=obj)

    def update(self, request, *args, **kwargs):
        if not is_super_admin(request.user):
            instance = self.get_object()
            if instance.id != getattr(user_company(request.user), 'id', None):
                return Response({'detail': 'Company Admin can update own company only.'}, status=403)
            supplied = set(request.data.keys())
            disallowed = supplied - self.company_admin_basic_fields
            if disallowed:
                return Response({'detail': 'Company Admin may update only basic company settings.', 'blocked_fields': sorted(disallowed)}, status=403)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def perform_update(self, serializer):
        before = CompanySerializer(self.get_object()).data
        obj = serializer.save()
        create_audit(self.request, 'UPDATE_COMPANY', obj=obj, before=dict(before), after=serializer.data, company=obj)

    def perform_destroy(self, instance):
        before = CompanySerializer(instance).data
        create_audit(self.request, 'DELETE_COMPANY', obj=instance, before=dict(before), company=instance)
        instance.delete()


class DepartmentViewSet(TenantModelViewSet):
    queryset = Department.objects.all().order_by('name')
    serializer_class = DepartmentSerializer
    permission_classes = [IsCompanyAdminOrHR]

    def get_queryset(self):
        qs = super().get_queryset()
        company_id = self.request.query_params.get('company_id')
        if company_id:
            try:
                company_id = int(company_id)
            except (ValueError, TypeError):
                raise ValidationError({'company_id': 'Select a valid company.'})
            if not is_super_admin(self.request.user) and company_id != getattr(user_company(self.request.user), 'id', None):
                raise PermissionDenied('Company outside your access.')
            return qs.filter(company_id=company_id)
        return qs

    @action(detail=False, methods=['get'], url_path='company-options')
    def company_options(self, request):
        if is_super_admin(request.user):
            companies = Company.objects.order_by('name').values('id', 'name')
            return Response({'companies': list(companies), 'selected_company_id': None})
        company = user_company(request.user)
        if not company:
            return Response({'detail': 'No company assigned.'}, status=400)
        return Response({'companies': [{'id': company.pk, 'name': company.name}],
                         'selected_company_id': company.pk})

    def perform_create(self, serializer):
        company = user_company(self.request.user)
        if is_super_admin(self.request.user):
            company_id = self.request.data.get('company')
            try:
                company = Company.objects.filter(pk=int(company_id)).first()
            except (ValueError, TypeError):
                company = None
            if not company:
                raise ValidationError({'company': 'Select an existing company.'})
        elif not company:
            raise ValidationError({'company': 'No company assigned.'})
        elif self.request.data.get('company') and str(self.request.data['company']) != str(company.pk):
            raise PermissionDenied('Cannot create departments in another company.')

        name = serializer.validated_data['name'].strip()
        if Department.objects.filter(company=company, name__iexact=name).exists():
            raise ValidationError({'name': 'This department already exists in the selected company.'})
        obj = serializer.save(company=company, name=name)
        create_audit(self.request, 'CREATE_DEPARTMENT', obj=obj, company=company)

    def perform_update(self, serializer):
        department = self.get_object()
        supplied_company = self.request.data.get('company')
        if supplied_company and str(supplied_company) != str(department.company_id):
            raise ValidationError({'company': 'Department company cannot be changed.'})
        name = serializer.validated_data.get('name', department.name).strip()
        if Department.objects.filter(company=department.company, name__iexact=name).exclude(pk=department.pk).exists():
            raise ValidationError({'name': 'This department already exists in the selected company.'})
        before = DepartmentSerializer(department).data
        obj = serializer.save(name=name)
        create_audit(self.request, 'UPDATE_DEPARTMENT', obj=obj, before=dict(before),
                     after=DepartmentSerializer(obj).data, company=obj.company)

    def destroy(self, request, *args, **kwargs):
        return Response({'detail': 'Deactivate the department instead of deleting it.'}, status=405)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related('profile', 'profile__company', 'profile__department', 'profile__manager').all().order_by('-id')
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrReadOnlyScoped]

    def get_queryset(self):
        qs = super().get_queryset()
        if not is_super_admin(self.request.user):
            company = user_company(self.request.user)
            if not company:
                return qs.none()
            qs = qs.filter(profile__company=company)
            role = get_role(self.request.user)
            if role == 'MANAGER':
                qs = qs.filter(models.Q(profile__manager=self.request.user) | models.Q(id=self.request.user.id))
            elif role == 'EMPLOYEE':
                qs = qs.filter(id=self.request.user.id)
        qs = admin_company_scope(self.request, qs, 'profile__company_id')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(models.Q(email__icontains=search) | models.Q(first_name__icontains=search) |
                           models.Q(last_name__icontains=search) | models.Q(username__icontains=search))
        return qs

    @action(detail=False, methods=['get'], url_path='form-options')
    def form_options(self, request):
        role = get_role(request.user)
        if role not in ['SUPER_ADMIN', 'COMPANY_ADMIN', 'HR_ADMIN']:
            return Response({'detail': 'Only admins can add employees.'}, status=403)

        if role == 'SUPER_ADMIN':
            companies = list(Company.objects.order_by('name').values('id', 'name', 'employee_id_prefix'))
            company_id = request.query_params.get('company_id')
            if company_id:
                try:
                    company = Company.objects.filter(pk=int(company_id)).first()
                except (ValueError, TypeError):
                    company = None
                if not company:
                    return Response({'detail': 'Select a valid company.'}, status=400)
            else:
                company = None
        else:
            company = user_company(request.user)
            if not company:
                return Response({'detail': 'No company assigned.'}, status=400)
            if request.query_params.get('company_id') and str(company.pk) != request.query_params['company_id']:
                return Response({'detail': 'Company outside your access.'}, status=403)
            companies = [{'id': company.pk, 'name': company.name, 'employee_id_prefix': company.employee_id_prefix}]

        departments = []
        managers = []
        if company:
            departments = list(Department.objects.filter(company=company, is_active=True)
                               .order_by('name').values('id', 'name'))
            managers = list(User.objects.filter(
                profile__company=company,
                profile__role__in=['MANAGER', 'COMPANY_ADMIN', 'HR_ADMIN', 'SALES_ADMIN'],
                profile__is_active_employee=True, is_active=True,
            ).order_by('first_name', 'id').values('id', 'first_name', 'last_name', 'email'))
        return Response({'companies': companies, 'selected_company_id': company.pk if company else None,
                         'departments': departments, 'managers': managers})

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        if not is_super_admin(request.user):
            company = user_company(request.user)
            if not company:
                return Response({'detail': 'No company assigned'}, status=400)
            data['company'] = company.id
            if data.get('role') == 'SUPER_ADMIN':
                return Response({'detail': 'Only Super Admin can create another Super Admin.'}, status=403)
            if data.get('department') and not Department.objects.filter(id=data.get('department'), company=company).exists():
                return Response({'detail': 'Department outside your company is not allowed.'}, status=403)
            if data.get('manager') and not User.objects.filter(id=data.get('manager'), profile__company=company).exists():
                return Response({'detail': 'Manager outside your company is not allowed.'}, status=403)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        company_id = validated.get('company')
        if validated.get('role', 'EMPLOYEE') != 'SUPER_ADMIN' and not Company.objects.filter(pk=company_id).exists():
            return Response({'detail': 'Select an existing company for this employee.'}, status=400)
        if validated.get('department') and not Department.objects.filter(
            pk=validated['department'], company_id=company_id).exists():
            return Response({'detail': 'Department must belong to the selected company.'}, status=400)
        if validated.get('manager') and not User.objects.filter(
            pk=validated['manager'], profile__company_id=company_id).exists():
            return Response({'detail': 'Manager must belong to the selected company.'}, status=400)
        self.perform_create(serializer)
        return Response(serializer.data, status=201)

    def update(self, request, *args, **kwargs):
        data = request.data.copy()
        if not is_super_admin(request.user):
            company = user_company(request.user)
            data.pop('company', None)
            if data.get('role') == 'SUPER_ADMIN':
                return Response({'detail': 'Only Super Admin can assign Super Admin role.'}, status=403)
            if data.get('department') and not Department.objects.filter(id=data.get('department'), company=company).exists():
                return Response({'detail': 'Department outside your company is not allowed.'}, status=403)
            if data.get('manager') and not User.objects.filter(id=data.get('manager'), profile__company=company).exists():
                return Response({'detail': 'Manager outside your company is not allowed.'}, status=403)
            obj = self.get_object()
            if getattr(obj.profile, 'role', None) == 'SUPER_ADMIN':
                return Response({'detail': 'Only Super Admin can update a Super Admin account.'}, status=403)
            if getattr(obj.profile, 'company_id', None) != getattr(company, 'id', None):
                return Response({'detail': 'Cannot update user outside your company.'}, status=403)
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def perform_create(self, serializer):
        user = serializer.save()
        create_audit(self.request, 'CREATE_USER', obj=user, after=serializer.data, company=user_company(user) or user_company(self.request.user))

    def perform_update(self, serializer):
        before = UserSerializer(self.get_object()).data
        user = serializer.save()
        create_audit(self.request, 'UPDATE_USER', obj=user, before=dict(before), after=serializer.data, company=user_company(user) or user_company(self.request.user))

    @action(detail=True, methods=['post'], url_path='reactivate-policy')
    def reactivate_policy(self, request, pk=None):
        if get_role(request.user) not in ['SUPER_ADMIN', 'COMPANY_ADMIN', 'HR_ADMIN']:
            return Response({'detail': 'Only Super Admin, Company Admin, or HR/Admin can reactivate policy-declined users.'}, status=403)
        user = self.get_object()
        if hasattr(user, 'profile'):
            user.profile.policy_status = 'NOT_ACCEPTED'
            user.profile.save(update_fields=['policy_status'])
        create_audit(request, 'POLICY_USER_REACTIVATED', obj=user, company=user_company(user) or user_company(request.user))
        return Response(UserSerializer(user).data)


class SubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Subscription.objects.select_related('company', 'plan').annotate(live_user_count=Count(
        'company__profiles', filter=models.Q(company__profiles__user__is_active=True,
                                            company__profiles__is_active_employee=True))).order_by('-id')
    serializer_class = SubscriptionSerializer
    permission_classes = [IsBillingAdmin]

    def get_queryset(self):
        return admin_company_scope(self.request, super().get_queryset())

    @action(detail=False, methods=['get'], url_path='form-options')
    def form_options(self, request):
        companies = admin_company_scope(request, Company.objects.order_by('name'), 'pk')
        plans = CompanyPlan.objects.filter(is_active=True).exclude(code='TRIAL').order_by('id')
        return Response({'companies': list(companies.values('id', 'name', 'status')),
                         'plans': CompanyPlanSerializer(plans, many=True).data,
                         'can_manage': is_super_admin(request.user), 'payment_mode': 'MANUAL'})

    @action(detail=False, methods=['post'])
    def configure(self, request):
        serializer = SubscriptionConfigureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        before_obj = Subscription.objects.filter(company_id=data['company_id']).first()
        before = SubscriptionSerializer(before_obj).data if before_obj else {}
        sub = configure_subscription(data['company_id'], data['plan'], data['billing_cycle'])
        result = SubscriptionSerializer(sub).data
        create_audit(request, 'CONFIGURE_SUBSCRIPTION', obj=sub, before=dict(before), after=dict(result), company=sub.company)
        return Response(result)

    @action(detail=False, methods=['get'])
    def overview(self, request):
        subscriptions = self.get_queryset()
        invoices = admin_company_scope(request, BillingInvoice.objects.all())
        totals = list(invoices.values('currency', 'status').annotate(amount=Sum('amount'), count=Count('id'))
                      .order_by('currency', 'status'))
        return Response({'subscriptions': subscriptions.count(),
                         'active_subscriptions': subscriptions.filter(status='ACTIVE').count(),
                         'internal_subscriptions': subscriptions.filter(status='INTERNAL_NOT_BILLABLE').count(),
                         'trial_subscriptions': subscriptions.filter(status='TRIAL').count(),
                         'invoice_totals': totals, 'payment_mode': 'MANUAL', 'online_checkout_available': False})


class DeviceViewSet(TenantModelViewSet):
    queryset = Device.objects.select_related('company', 'user').all().order_by('-last_seen_at')
    serializer_class = DeviceSerializer
    permission_classes = [IsAdminOrReadOnlyScoped]

    def get_queryset(self):
        qs = super().get_queryset()
        role = get_role(self.request.user)
        if role == 'MANAGER':
            return qs.filter(user__profile__manager=self.request.user)
        if role == 'EMPLOYEE':
            return qs.filter(user=self.request.user)
        return qs


class AgentVersionViewSet(viewsets.ModelViewSet):
    queryset = AgentVersion.objects.select_related('company').all().order_by('-id')
    serializer_class = AgentVersionSerializer
    permission_classes = [IsAgentVersionPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_super_admin(self.request.user):
            if self.request.query_params.get('scope') == 'global':
                return qs.filter(company__isnull=True)
            company_id = self.request.query_params.get('company_id')
            if company_id:
                if not company_id.isdigit() or not Company.objects.filter(pk=company_id).exists():
                    raise ValidationError({'company_id': 'Select an existing company.'})
                return qs.filter(company_id=company_id)
            return qs
        company = user_company(self.request.user)
        return qs.filter(models.Q(company=company) | models.Q(company__isnull=True)) if company else qs.none()

    @action(detail=False, methods=['get'], url_path='company-options')
    def company_options(self, request):
        if is_super_admin(request.user):
            return Response({'companies': list(Company.objects.order_by('name').values('id', 'name'))})
        company = user_company(request.user)
        return Response({'companies': [{'id': company.pk, 'name': company.name}] if company else []})

    def perform_create(self, serializer):
        company = user_company(self.request.user)
        if is_super_admin(self.request.user):
            company_id = self.request.data.get('company')
            if company_id not in (None, ''):
                if not str(company_id).isdigit():
                    raise ValidationError({'company': 'Select a valid company.'})
                company = Company.objects.filter(pk=company_id).first()
                if not company:
                    raise ValidationError({'company': 'Company not found.'})
            else:
                company = None
        if not is_super_admin(self.request.user) and not company:
            raise ValidationError({'company': 'No company assigned.'})
        with transaction.atomic():
            obj = serializer.save(company=company)
            if obj.is_active:
                AgentVersion.objects.filter(company=company, platform=obj.platform, is_active=True).exclude(pk=obj.pk).update(is_active=False)
        create_audit(self.request, 'AGENT_VERSION_CREATED', obj=obj, company=company)

    def perform_update(self, serializer):
        obj_before = self.get_object()
        if not is_super_admin(self.request.user) and obj_before.company_id != getattr(user_company(self.request.user), 'id', None):
            raise PermissionDenied('Company Admin cannot update global or other-company agent versions.')
        if 'company' in self.request.data and str(self.request.data.get('company') or '') != str(obj_before.company_id or ''):
            raise ValidationError({'company': 'Rule scope cannot be changed. Create a new rule for another company.'})
        before = AgentVersionSerializer(obj_before).data
        with transaction.atomic():
            obj = serializer.save()
            if obj.is_active or (before['is_active'] and not obj.is_active):
                AgentVersion.objects.filter(company=obj.company, platform=obj.platform, is_active=True).exclude(pk=obj.pk).update(is_active=False)
        create_audit(self.request, 'AGENT_VERSION_UPDATED', obj=obj, before=dict(before), after=serializer.data, company=obj.company)

    def perform_destroy(self, instance):
        if not is_super_admin(self.request.user) and instance.company_id != getattr(user_company(self.request.user), 'id', None):
            raise PermissionDenied('Company Admin cannot delete global or other-company agent versions.')
        before = AgentVersionSerializer(instance).data
        create_audit(self.request, 'AGENT_VERSION_DELETED', obj=instance, before=dict(before), company=instance.company)
        if instance.is_active:
            AgentVersion.objects.filter(company=instance.company, platform=instance.platform, is_active=True).exclude(pk=instance.pk).update(is_active=False)
        instance.delete()


class PolicyVersionViewSet(TenantModelViewSet):
    queryset = PolicyVersion.objects.all().order_by('-id')
    serializer_class = PolicyVersionSerializer
    permission_classes = [IsCompanyAdminOrHR]

    def get_queryset(self):
        qs = super().get_queryset()
        company_id = self.request.query_params.get('company_id')
        if is_super_admin(self.request.user) and company_id:
            if not company_id.isdigit() or not Company.objects.filter(pk=company_id).exists():
                raise ValidationError({'company_id': 'Select an existing company.'})
            return qs.filter(company_id=company_id)
        if company_id and str(getattr(user_company(self.request.user), 'pk', '')) != company_id:
            raise PermissionDenied('Cannot view another company policy.')
        return qs

    @action(detail=False, methods=['get'], url_path='company-options')
    def company_options(self, request):
        if is_super_admin(request.user):
            companies = Company.objects.order_by('name').values('id', 'name')
        else:
            companies = Company.objects.filter(pk=getattr(user_company(request.user), 'pk', None)).values('id', 'name')
        return Response({'companies': list(companies)})

    def perform_create(self, serializer):
        company = user_company(self.request.user)
        if is_super_admin(self.request.user):
            company_id = self.request.data.get('company')
            if not str(company_id or '').isdigit():
                raise ValidationError({'company': 'Select a company.'})
            company = Company.objects.filter(pk=company_id).first()
            if not company:
                raise ValidationError({'company': 'Company not found.'})
        elif not company:
            raise ValidationError({'company': 'No company assigned.'})
        elif self.request.data.get('company') and str(self.request.data['company']) != str(company.pk):
            raise PermissionDenied('Cannot create a policy for another company.')
        if PolicyVersion.objects.filter(company=company, version__iexact=serializer.validated_data['version']).exists():
            raise ValidationError({'version': 'This policy version already exists for the company.'})
        with transaction.atomic():
            obj = serializer.save(company=company, created_by=self.request.user)
            if obj.is_active:
                PolicyVersion.objects.filter(company=company, is_active=True).exclude(pk=obj.pk).update(is_active=False)
                WorkSession.objects.filter(company=company, status='RUNNING').update(status='AUTO_STOPPED', stopped_at=timezone.now())
        create_audit(self.request, 'POLICY_VERSION_CREATED', obj=obj, company=company)

    def perform_update(self, serializer):
        obj = self.get_object()
        for field in ('company', 'created_by', 'version', 'title', 'body'):
            if field in self.request.data and str(self.request.data[field]) != str(getattr(obj, field + '_id' if field in ('company', 'created_by') else field) or ''):
                raise ValidationError({field: 'Policy content and scope cannot change. Publish a new version.'})
        before = PolicyVersionSerializer(obj).data
        with transaction.atomic():
            obj = serializer.save()
            if obj.is_active:
                other_active = PolicyVersion.objects.filter(company=obj.company, is_active=True).exclude(pk=obj.pk).update(is_active=False)
            elif before['is_active']:
                other_active = PolicyVersion.objects.filter(company=obj.company, is_active=True).exclude(pk=obj.pk).update(is_active=False)
            else:
                other_active = 0
            if before['is_active'] != obj.is_active or other_active:
                WorkSession.objects.filter(company=obj.company, status='RUNNING').update(status='AUTO_STOPPED', stopped_at=timezone.now())
        create_audit(self.request, 'POLICY_VERSION_UPDATED', obj=obj, before=before,
                     after=PolicyVersionSerializer(obj).data, company=obj.company)

    def destroy(self, request, *args, **kwargs):
        return Response({'detail': 'Deactivate a policy instead of deleting consent history.'}, status=405)

class PolicyAcceptanceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PolicyAcceptance.objects.select_related('company', 'user', 'policy').all().order_by('-id')
    serializer_class = PolicyAcceptanceSerializer
    permission_classes = [IsPolicyAcceptanceReader]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_super_admin(self.request.user):
            company_id = self.request.query_params.get('company_id')
            if company_id:
                if not company_id.isdigit() or not Company.objects.filter(pk=company_id).exists():
                    raise ValidationError({'company_id': 'Select an existing company.'})
                qs = qs.filter(company_id=company_id)
            return qs
        company = user_company(self.request.user)
        if not company:
            return qs.none()
        qs = qs.filter(company=company)
        role = get_role(self.request.user)
        if role == 'MANAGER':
            return qs.filter(user__profile__manager=self.request.user)
        if role == 'EMPLOYEE':
            return qs.filter(user=self.request.user)
        return qs


class WorkSessionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WorkSession.objects.select_related('company', 'user', 'device').all().order_by('-started_at')
    serializer_class = WorkSessionSerializer
    permission_classes = [IsOperationsReader]

    def get_queryset(self):
        return filter_operations(self.request, super().get_queryset(), 'started_at',
                                 {'RUNNING', 'STOPPED', 'AUTO_STOPPED'})

    @action(detail=False, methods=['get'], url_path='filter-options')
    def filter_options(self, request):
        if is_super_admin(request.user):
            companies = Company.objects.order_by('name').values('id', 'name')
        else:
            companies = Company.objects.filter(pk=getattr(user_company(request.user), 'pk', None)).values('id', 'name')
        users = (self.get_queryset().order_by('user__email').values('user_id', 'user__email').distinct()
                 if not is_super_admin(request.user) or request.query_params.get('company_id') else [])
        return Response({'companies': list(companies),
                         'users': [{'id': row['user_id'], 'email': row['user__email']} for row in users]})


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ActivityLog.objects.select_related('company', 'user', 'device', 'session').all().order_by('-captured_at')
    serializer_class = ActivityLogSerializer
    permission_classes = [IsOperationsReader]

    def get_queryset(self):
        return filter_operations(self.request, super().get_queryset(), 'captured_at',
                                 {'PRODUCTIVE', 'NEUTRAL', 'UNPRODUCTIVE', 'UNKNOWN'})


class ScreenshotViewSet(mixins.DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Screenshot.objects.select_related('company', 'user', 'device', 'session').all().order_by('-captured_at')
    serializer_class = ScreenshotSerializer
    permission_classes = [IsScreenshotUser]

    def get_queryset(self):
        return filter_operations(self.request, screenshot_queryset_for_user(self.request.user), 'captured_at').exclude(
            status='DELETED').order_by('-captured_at', '-id')

    @action(detail=False, methods=['get'], url_path='filter-options')
    def filter_options(self, request):
        return operations_options(request)

    def _serve_local_file(self, request, screenshot, action):
        if not screenshot.file:
            return Response({'detail': 'Screenshot file not available in local storage.'}, status=404)
        if not screenshot.file.storage.exists(screenshot.file.name):
            return Response({'detail': 'Screenshot file missing from storage.'}, status=404)
        ScreenshotAccessLog.objects.create(company=screenshot.company, screenshot=screenshot, accessed_by=request.user, action=action, ip_address=client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', ''))
        create_audit(request, f'SCREENSHOT_{action}', obj=screenshot, company=screenshot.company)
        content_type = mimetypes.guess_type(screenshot.file.name)[0]
        content_type = content_type if content_type in ('image/png', 'image/jpeg', 'image/webp') else 'application/octet-stream'
        extension = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}.get(content_type, 'bin')
        filename = f'workpulse-screenshot-{screenshot.id}.{extension}'
        file_handle = screenshot.file.storage.open(screenshot.file.name, 'rb')
        response = FileResponse(file_handle, as_attachment=(action == 'DOWNLOAD'), filename=filename, content_type=content_type)
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response

    @action(detail=True, methods=['get'], url_path='view')
    def view_file(self, request, pk=None):
        screenshot = self.get_object()
        if screenshot.storage_mode != 'local':
            ScreenshotAccessLog.objects.create(company=screenshot.company, screenshot=screenshot, accessed_by=request.user, action='VIEW', ip_address=client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', ''))
            return Response({'detail': 'S3 protected view requires production S3 configuration.', 'external_configuration_required': True}, status=501)
        return self._serve_local_file(request, screenshot, 'VIEW')

    @action(detail=True, methods=['get'], url_path='download')
    def download_file(self, request, pk=None):
        screenshot = self.get_object()
        if screenshot.storage_mode != 'local':
            ScreenshotAccessLog.objects.create(company=screenshot.company, screenshot=screenshot, accessed_by=request.user, action='DOWNLOAD', ip_address=client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', ''))
            return Response({'detail': 'S3 protected download requires production S3 configuration.', 'external_configuration_required': True}, status=501)
        return self._serve_local_file(request, screenshot, 'DOWNLOAD')

    @action(detail=True, methods=['post'], url_path='log-access')
    def log_access(self, request, pk=None):
        screenshot = self.get_object()
        if request.data.get('action', 'VIEW') not in ('VIEW', 'DOWNLOAD'):
            raise ValidationError({'action': 'Use VIEW or DOWNLOAD. Deletion requires the delete action.'})
        ScreenshotAccessLog.objects.create(company=screenshot.company, screenshot=screenshot, accessed_by=request.user, action=request.data.get('action', 'VIEW'), ip_address=client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', ''))
        return Response({'status': 'logged'})

    @action(detail=True, methods=['post'], url_path='soft-delete')
    def soft_delete(self, request, pk=None):
        if get_role(request.user) not in ['SUPER_ADMIN', 'COMPANY_ADMIN', 'HR_ADMIN', 'MANAGER']:
            return Response({'detail': 'Not allowed to delete screenshots.'}, status=403)
        screenshot = self.get_object()
        screenshot.deleted_at = timezone.now()
        screenshot.status = 'DELETED'
        screenshot.save(update_fields=['deleted_at', 'status'])
        ScreenshotAccessLog.objects.create(company=screenshot.company, screenshot=screenshot, accessed_by=request.user, action='DELETE', ip_address=client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', ''))
        create_audit(request, 'DELETE_SCREENSHOT', obj=screenshot, company=screenshot.company)
        return Response({'status': 'deleted'})

    def destroy(self, request, *args, **kwargs):
        # Do not hard-delete screenshot rows from the API. Standard DELETE also becomes a logged soft delete.
        if get_role(request.user) not in ['SUPER_ADMIN', 'COMPANY_ADMIN', 'HR_ADMIN', 'MANAGER']:
            return Response({'detail': 'Not allowed to delete screenshots.'}, status=403)
        screenshot = self.get_object()
        if not screenshot.deleted_at:
            screenshot.deleted_at = timezone.now()
            screenshot.status = 'DELETED'
            screenshot.save(update_fields=['deleted_at', 'status'])
        ScreenshotAccessLog.objects.create(company=screenshot.company, screenshot=screenshot, accessed_by=request.user, action='DELETE', ip_address=client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', ''))
        create_audit(request, 'DELETE_SCREENSHOT', obj=screenshot, company=screenshot.company)
        return Response({'status': 'deleted'})


class AppWebsiteCategoryViewSet(TenantModelViewSet):
    queryset = AppWebsiteCategory.objects.all().order_by('pattern')
    serializer_class = AppWebsiteCategorySerializer
    permission_classes = [IsCompanyAdminOrHR]


class AlertViewSet(TenantModelViewSet):
    queryset = Alert.objects.select_related('company', 'user', 'device').all().order_by('-id')
    serializer_class = AlertSerializer
    permission_classes = [IsAdminOrReadOnlyScoped]

    def get_queryset(self):
        qs = super().get_queryset()
        role = get_role(self.request.user)
        if role == 'MANAGER':
            return qs.filter(user__profile__manager=self.request.user)
        if role == 'EMPLOYEE':
            return qs.filter(user=self.request.user)
        return qs

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        alert = self.get_object()
        if get_role(request.user) == 'EMPLOYEE':
            return Response({'detail': 'Employees cannot close alerts.'}, status=403)
        alert.status = request.data.get('status', 'CLOSED')
        alert.resolved_by = request.user
        alert.resolved_at = timezone.now()
        alert.save()
        create_audit(request, 'CLOSE_ALERT', obj=alert, company=alert.company)
        return Response(AlertSerializer(alert).data)


class DailyAISummaryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DailyAISummary.objects.select_related('company', 'user').all().order_by('-date', '-id')
    serializer_class = DailyAISummarySerializer
    permission_classes = [IsAISummaryReader]

    def get_queryset(self):
        qs = filter_operations(self.request, super().get_queryset(), 'date')
        status = self.request.query_params.get('review_status')
        if status:
            if status not in dict(DailyAISummary.REVIEW_CHOICES):
                raise ValidationError({'review_status': 'Select a valid review status.'})
            qs = qs.filter(manager_review_status=status)
        return qs

    @action(detail=False, methods=['get'], url_path='filter-options')
    def filter_options(self, request):
        return operations_options(request)

    @action(detail=False, methods=['post'])
    def generate(self, request):
        target_date = serializers.DateField().run_validation(request.data.get('date'))
        if target_date > timezone.localdate():
            raise ValidationError({'date': 'Choose today or a past date.'})
        company = user_company(request.user)
        if is_super_admin(request.user):
            company_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('company_id'))
            company = Company.objects.filter(pk=company_id).first()
        elif request.data.get('company_id') and str(request.data['company_id']) != str(getattr(company, 'pk', None)):
            raise PermissionDenied('Cannot generate summaries for another company.')
        if not company:
            raise ValidationError({'company_id': 'Select a valid company.'})
        users = operations_users(request.user).filter(profile__company=company)
        if request.data.get('user_id'):
            user_id = serializers.IntegerField(min_value=1).run_validation(request.data['user_id'])
            users = users.filter(pk=user_id)
            if not users.exists():
                raise PermissionDenied('Employee is outside your scope.')
        result = generate_summaries(users, target_date)
        create_audit(request, 'GENERATE_AI_SUMMARIES', after={'date': str(target_date), **result}, company=company)
        return Response({'date': target_date, 'analysis_mode': 'RULE_BASED', **result})


class ManagerReviewViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ManagerReview.objects.select_related('ai_summary', 'ai_summary__company', 'ai_summary__user', 'reviewed_by').all().order_by('-id')
    serializer_class = ManagerReviewSerializer
    permission_classes = [IsManagerOrAdminReview]

    def get_queryset(self):
        summaries = role_scoped_user_filter(self.request, DailyAISummary.objects.all())
        qs = super().get_queryset().filter(ai_summary__in=summaries)
        if self.request.query_params.get('ai_summary'):
            summary_id = serializers.IntegerField(min_value=1).run_validation(self.request.query_params['ai_summary'])
            qs = qs.filter(ai_summary_id=summary_id)
        return qs

    def perform_create(self, serializer):
        ai_summary = serializer.validated_data.get('ai_summary')
        if not role_scoped_user_filter(self.request, DailyAISummary.objects.all()).filter(pk=ai_summary.pk).exists():
            raise PermissionDenied('AI summary outside allowed scope.')
        with transaction.atomic():
            summary = DailyAISummary.objects.select_for_update().get(pk=ai_summary.pk)
            expected_update = serializer.validated_data.pop('summary_updated_at', None)
            if expected_update and expected_update != summary.updated_at:
                raise ValidationError({'detail': 'This summary has changed. Close it, refresh, and review the latest version.'})
            obj = serializer.save(reviewed_by=self.request.user)
            summary.manager_review_status = obj.status
            summary.save(update_fields=['manager_review_status', 'updated_at'])
        create_audit(self.request, 'MANAGER_REVIEW_CREATED', obj=obj, company=obj.ai_summary.company if obj.ai_summary else user_company(self.request.user))


class DemoTrialCodeViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    queryset = DemoTrialCode.objects.select_related('generated_by', 'sales_owner', 'plan', 'used_by_company').all().order_by('-id')
    serializer_class = DemoTrialCodeSerializer
    permission_classes = [IsTrialAdmin]

    def get_queryset(self):
        qs = allowed_trial_code_queryset(self.request.user).order_by('-id')
        status = self.request.query_params.get('status')
        if status:
            if status not in dict(DemoTrialCode.STATUS_CHOICES):
                raise ValidationError({'status': 'Select a valid status.'})
            if status == 'EXPIRED':
                qs = qs.filter(models.Q(status='EXPIRED') | models.Q(status='ACTIVE', expiry_date__lte=timezone.now()))
            elif status == 'ACTIVE':
                qs = qs.filter(status='ACTIVE', expiry_date__gt=timezone.now())
            else:
                qs = qs.filter(status=status)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(models.Q(code__icontains=search) | models.Q(customer_company_name__icontains=search)
                           | models.Q(email__icontains=search))
        return qs

    def eligible_owners(self):
        qs = User.objects.filter(is_active=True, profile__is_active_employee=True).filter(
            models.Q(profile__role='SUPER_ADMIN') |
            models.Q(profile__role__in=['COMPANY_ADMIN', 'SALES_ADMIN'], profile__can_generate_trials=True))
        if get_role(self.request.user) == 'SALES_ADMIN':
            return qs.filter(pk=self.request.user.pk)
        if not is_super_admin(self.request.user):
            return qs.filter(profile__company=user_company(self.request.user))
        return qs

    @action(detail=False, methods=['get'], url_path='form-options')
    def form_options(self, request):
        return Response({'owners': list(self.eligible_owners().order_by('email').values('id', 'email', 'username')),
                         'plans': CompanyPlanSerializer(CompanyPlan.objects.filter(code='TRIAL', is_active=True), many=True).data})

    def perform_create(self, serializer):
        sales_owner = serializer.validated_data.get('sales_owner') or self.request.user
        if not self.eligible_owners().filter(pk=sales_owner.pk).exists():
            raise ValidationError({'sales_owner': 'Select an eligible sales owner in your scope.'})
        code = DemoTrialCode.generate_code('BOLD')
        while DemoTrialCode.objects.filter(code=code).exists():
            code = DemoTrialCode.generate_code('BOLD')
        obj = serializer.save(code=code, status='ACTIVE', generated_by=self.request.user, sales_owner=sales_owner)
        create_audit(self.request, 'CREATE_DEMO_TRIAL_CODE', obj=obj, after=serializer.data, company=user_company(self.request.user))

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def cancel(self, request, pk=None):
        candidate = self.get_object()
        obj = DemoTrialCode.objects.select_for_update().get(pk=candidate.pk)
        if obj.status not in ('ACTIVE', 'EXPIRED'):
            return Response({'detail': 'Only available or expired codes can be cancelled. Manage enrolled companies in Trial Dashboard.'}, status=409)
        before = DemoTrialCodeSerializer(obj).data
        obj.status = 'CANCELLED'
        obj.save(update_fields=['status'])
        create_audit(request, 'CANCEL_DEMO_TRIAL_CODE', obj=obj, before=dict(before), after={'status': 'CANCELLED'}, company=user_company(request.user))
        return Response(DemoTrialCodeSerializer(obj).data)


class TrialSignupLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TrialSignupLog.objects.select_related('company', 'demo_code', 'admin_user').all().order_by('-id')
    serializer_class = TrialSignupLogSerializer
    permission_classes = [IsTrialAdmin]

    def get_queryset(self):
        if is_super_admin(self.request.user):
            return super().get_queryset()
        return super().get_queryset().filter(demo_code__in=allowed_trial_code_queryset(self.request.user))


class TrialConversionLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TrialConversionLog.objects.select_related('company', 'demo_code', 'converted_by', 'old_plan', 'new_plan').all().order_by('-id')
    serializer_class = TrialConversionLogSerializer
    permission_classes = [IsTrialAdmin]

    def get_queryset(self):
        if is_super_admin(self.request.user):
            return super().get_queryset()
        return super().get_queryset().filter(company__in=allowed_trial_company_queryset(self.request.user))


class ERPConnectorViewSet(viewsets.ModelViewSet):
    queryset = ERPConnector.objects.select_related('company').annotate(
        event_count=Count('erpevent'), last_received_at=Max('erpevent__received_at')).order_by('-id')
    serializer_class = ERPConnectorSerializer
    permission_classes = [IsERPConnectorPermission]

    def get_queryset(self):
        qs = admin_company_scope(self.request, super().get_queryset())
        status = self.request.query_params.get('status')
        if status:
            if status not in ('ACTIVE', 'INACTIVE'):
                raise ValidationError({'status': 'Use ACTIVE or INACTIVE.'})
            qs = qs.filter(is_active=status == 'ACTIVE')
        return qs

    @action(detail=False, methods=['get'], url_path='form-options')
    def form_options(self, request):
        companies = Company.objects.order_by('name') if is_super_admin(request.user) else Company.objects.filter(
            pk=getattr(user_company(request.user), 'pk', None))
        connectors = admin_company_scope(request, ERPConnector.objects.order_by('name'))
        if is_super_admin(request.user) and not request.query_params.get('company_id'):
            connectors = connectors.none()
        return Response({'companies': list(companies.values('id', 'name')), 'events': event_options(),
                         'connectors': list(connectors.values('id', 'name')),
                         'can_manage': get_role(request.user) in ('SUPER_ADMIN', 'COMPANY_ADMIN'),
                         'ingest_url': request.build_absolute_uri('/api/erp/ingest/')})

    @staticmethod
    def secret_response(obj, data=None, status=200):
        response = Response({**(data or {}), 'id': obj.pk, 'api_token': obj.api_token,
                             'token_rotated_at': obj.token_rotated_at}, status=status)
        response['Cache-Control'] = 'private, no-store'
        return response

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = user_company(request.user)
        if is_super_admin(request.user):
            company_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('company'))
            company = Company.objects.filter(pk=company_id).first()
        elif request.data.get('company') is not None and str(request.data['company']) != str(getattr(company, 'pk', None)):
            raise PermissionDenied('Cannot create a connector for another company.')
        if not company:
            raise ValidationError({'company': 'Select an existing company.'})
        Company.objects.select_for_update().get(pk=company.pk)
        name = serializer.validated_data.get('name', 'Glutape ERP').strip()
        if ERPConnector.objects.filter(company=company, name__iexact=name).exists():
            raise ValidationError({'name': 'This company already has a connector with this name.'})
        obj = serializer.save(company=company, name=name, api_token=secrets.token_urlsafe(32), token_rotated_at=timezone.now())
        result = self.get_serializer(obj).data
        create_audit(request, 'CREATE_ERP_CONNECTOR', obj=obj, after=dict(result), company=company)
        return self.secret_response(obj, result, status=201)

    @transaction.atomic
    def perform_update(self, serializer):
        company = serializer.instance.company
        Company.objects.select_for_update().get(pk=company.pk)
        obj = ERPConnector.objects.select_for_update().get(pk=serializer.instance.pk)
        before = self.get_serializer(obj).data
        name = serializer.validated_data.get('name', obj.name).strip()
        if ERPConnector.objects.filter(company=company, name__iexact=name).exclude(pk=obj.pk).exists():
            raise ValidationError({'name': 'This company already has a connector with this name.'})
        active = serializer.validated_data.get('is_active', obj.is_active)
        events = serializer.validated_data.get('allowed_event_types', obj.allowed_event_types)
        if active and not events:
            raise ValidationError({'allowed_event_types': 'Select events before enabling this connector.'})
        serializer.instance = obj
        obj = serializer.save(name=name)
        serializer.instance = self.queryset.get(pk=obj.pk)
        create_audit(self.request, 'UPDATE_ERP_CONNECTOR', obj=obj, before=dict(before),
                     after=dict(self.get_serializer(serializer.instance).data), company=company)

    def destroy(self, request, *args, **kwargs):
        self.get_object()
        return Response({'detail': 'Deactivate the connector to preserve event and employee mapping history.'}, status=405)

    @action(detail=True, methods=['post'], url_path='reveal-token')
    def reveal_token(self, request, pk=None):
        obj = self.get_object()
        create_audit(request, 'REVEAL_ERP_TOKEN', obj=obj, company=obj.company)
        return self.secret_response(obj)

    @action(detail=True, methods=['post'], url_path='rotate-token')
    @transaction.atomic
    def rotate_token(self, request, pk=None):
        candidate = self.get_object()
        obj = ERPConnector.objects.select_for_update().get(pk=candidate.pk)
        obj.api_token, obj.token_rotated_at = secrets.token_urlsafe(32), timezone.now()
        obj.save(update_fields=['api_token', 'token_rotated_at', 'updated_at'])
        create_audit(request, 'ROTATE_ERP_TOKEN', obj=obj, company=obj.company)
        return self.secret_response(obj)


class ERPEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ERPEvent.objects.select_related('company', 'connector').all().order_by('-received_at', '-id')
    serializer_class = ERPEventSerializer
    permission_classes = [IsERPEventReader]

    def get_queryset(self):
        qs = admin_company_scope(self.request, super().get_queryset())
        connector = self.request.query_params.get('connector_id')
        if connector:
            qs = qs.filter(connector_id=serializers.IntegerField(min_value=1).run_validation(connector))
        status = self.request.query_params.get('status')
        if status == 'PROCESSED':
            qs = qs.filter(processed=True)
        elif status == 'FAILED':
            qs = qs.filter(processed=False).exclude(processing_error='')
        elif status in ('RECEIVED', 'PENDING'):
            qs = qs.filter(processed=False, processing_error='')
            qs = qs.filter(event_type__in=EMPLOYEE_EVENTS) if status == 'PENDING' else qs.exclude(event_type__in=EMPLOYEE_EVENTS)
        elif status:
            raise ValidationError({'status': 'Select a valid processing status.'})
        event_type = self.request.query_params.get('event_type')
        if event_type:
            qs = qs.filter(event_type=event_type)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(models.Q(external_id__icontains=search) | models.Q(event_type__icontains=search) |
                           models.Q(payload__employee_id__icontains=search) |
                           models.Q(payload__employee_code__icontains=search) | models.Q(payload__email__icontains=search))
        dates = {}
        for key in ('from_date', 'to_date'):
            value = self.request.query_params.get(key)
            if value:
                dates[key] = serializers.DateField().run_validation(value)
                qs = qs.filter(**{'received_at__date__' + ('gte' if key == 'from_date' else 'lte'): dates[key]})
        if len(dates) == 2 and dates['from_date'] > dates['to_date']:
            raise ValidationError({'to_date': 'End date must not precede start date.'})
        return qs


class AuditLogViewSet(TenantModelViewSet):
    queryset = AuditLog.objects.select_related('company', 'actor').all().order_by('-id')
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuditReader]


class BillingInvoiceViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    queryset = BillingInvoice.objects.select_related('company', 'subscription', 'payment_recorded_by').all().order_by('-id')
    serializer_class = BillingInvoiceSerializer
    permission_classes = [IsBillingAdmin]

    def get_queryset(self):
        qs = admin_company_scope(self.request, super().get_queryset())
        status = self.request.query_params.get('status')
        if status:
            if status not in dict(BillingInvoice.STATUS_CHOICES):
                raise ValidationError({'status': 'Select a valid invoice status.'})
            qs = qs.filter(status=status)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = InvoiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        invoice = create_invoice(data['subscription_id'], data['billing_period_start'], data['notes'])
        result = self.get_serializer(invoice).data
        create_audit(request, 'CREATE_BILLING_DRAFT', obj=invoice, after=dict(result), company=invoice.company)
        return Response(result, status=201)

    def change_status(self, request, name, data=None):
        candidate = self.get_object()
        invoice, changed = transition_invoice(candidate.pk, name, request.user, **(data or {}))
        result = self.get_serializer(invoice).data
        if changed:
            create_audit(request, 'BILLING_' + name.upper().replace('-', '_'), obj=invoice,
                         after=dict(result), company=invoice.company)
        return Response(result)

    @action(detail=True, methods=['post'])
    def issue(self, request, pk=None):
        return self.change_status(request, 'issue')

    @action(detail=True, methods=['post'], url_path='record-payment')
    def record_payment(self, request, pk=None):
        serializer = PaymentRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.change_status(request, 'record-payment', serializer.validated_data)

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        serializer = InvoiceVoidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.change_status(request, 'void', serializer.validated_data)


class AgentVersionCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        platform = request.query_params.get('platform', 'windows')
        installed_version = request.query_params.get('version', '0.0.0')
        company = user_company(request.user)
        company_id = request.query_params.get('company_id')
        if company_id:
            if not request.user.is_authenticated:
                raise PermissionDenied('Sign in to check a company rule.')
            if not str(company_id).isdigit():
                raise ValidationError({'company_id': 'Select a valid company.'})
            if not is_super_admin(request.user) and str(getattr(company, 'pk', '')) != str(company_id):
                raise PermissionDenied('Cannot check another company rule.')
            company = Company.objects.filter(pk=company_id).first()
            if not company:
                raise ValidationError({'company_id': 'Company not found.'})
        return Response(agent_version_payload(platform, installed_version, company=company))


class CurrentPolicyView(APIView):
    def get(self, request):
        company = user_company(request.user)
        if not company:
            return Response({'detail': 'No company assigned'}, status=400)
        policy = latest_active_policy(company)
        if not policy:
            return Response({'detail': 'No policy configured'}, status=404)
        accepted, _ = has_accepted_latest_policy(request.user, company)
        profile = getattr(request.user, 'profile', None)
        blocked_reason = ('EMPLOYEE_INACTIVE' if profile and not profile.is_active_employee else
                          'POLICY_DECLINED' if profile and profile.policy_status == 'POLICY_DECLINED' else None)
        return Response({'policy': PolicyVersionSerializer(policy).data, 'accepted': accepted,
                         'blocked_reason': blocked_reason})


class PolicyAcceptView(APIView):
    def post(self, request):
        company = user_company(request.user)
        if not company:
            return Response({'detail': 'No company assigned'}, status=400)
        profile = getattr(request.user, 'profile', None)
        if profile and (profile.policy_status == 'POLICY_DECLINED' or not profile.is_active_employee):
            return Response({
                'blocked': True,
                'blocked_reason': 'EMPLOYEE_INACTIVE' if not profile.is_active_employee else 'POLICY_DECLINED',
                'detail': 'Employee is inactive or the monitoring policy was declined.'
            }, status=403)
        policy = latest_active_policy(company)
        if not policy:
            return Response({'detail': 'No policy configured'}, status=404)
        if not request.data.get('policy_id'):
            raise ValidationError({'policy_id': 'Confirm the policy version shown to the employee.'})
        if str(request.data['policy_id']) != str(policy.pk):
            return Response({'detail': 'Policy changed. Read and accept the current version.',
                             'blocked_reason': 'POLICY_CHANGED', 'policy': PolicyVersionSerializer(policy).data}, status=409)
        device = Device.objects.filter(company=company, user=request.user, device_id=request.data.get('device_id')).first()
        with transaction.atomic():
            acceptance = (PolicyAcceptance.objects.filter(
                company=company, user=request.user, policy=policy, status='ACCEPTED').order_by('-id').first()
                if request.user.profile.policy_status == 'ACCEPTED' else None)
            created = acceptance is None
            if created:
                acceptance = PolicyAcceptance.objects.create(
                    company=company, user=request.user, policy=policy, device=device, status='ACCEPTED',
                    accepted_at=timezone.now(), ip_address=client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''))
            request.user.profile.policy_status = 'ACCEPTED'
            request.user.profile.save(update_fields=['policy_status'])
        if created:
            create_audit(request, 'POLICY_ACCEPTED', obj=acceptance, company=company)
        return Response(PolicyAcceptanceSerializer(acceptance).data)


class PolicyDeclineView(APIView):
    def post(self, request):
        company = user_company(request.user)
        if not company:
            return Response({'detail': 'No company assigned'}, status=400)
        if getattr(request.user.profile, 'policy_status', '') == 'POLICY_DECLINED':
            return Response({'blocked': True, 'blocked_reason': 'POLICY_DECLINED',
                             'detail': 'HR/Admin must reactivate the employee.'}, status=403)
        policy = latest_active_policy(company)
        if not policy:
            return Response({'detail': 'No policy configured'}, status=404)
        if not request.data.get('policy_id'):
            raise ValidationError({'policy_id': 'Confirm the policy version shown to the employee.'})
        if str(request.data['policy_id']) != str(policy.pk):
            return Response({'detail': 'Policy changed. Read the current version before deciding.',
                             'blocked_reason': 'POLICY_CHANGED', 'policy': PolicyVersionSerializer(policy).data}, status=409)
        device = Device.objects.filter(company=company, user=request.user, device_id=request.data.get('device_id')).first()
        with transaction.atomic():
            acceptance = PolicyAcceptance.objects.create(company=company, user=request.user, policy=policy, device=device, status='DECLINED', declined_at=timezone.now(), ip_address=client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', ''))
            request.user.profile.policy_status = 'POLICY_DECLINED'
            request.user.profile.save(update_fields=['policy_status'])
            WorkSession.objects.filter(company=company, user=request.user, status='RUNNING').update(status='AUTO_STOPPED', stopped_at=timezone.now())
            Alert.objects.get_or_create(company=company, user=request.user, device=device, alert_type='POLICY_DECLINED',
                                        status='OPEN', defaults={'severity': 'HIGH', 'title': 'Policy declined',
                                                                 'message': 'Employee declined the monitoring policy.'})
        create_audit(request, 'POLICY_DECLINED', obj=acceptance, company=company)
        return Response({'status': 'blocked', 'blocked': True, 'blocked_reason': 'POLICY_DECLINED', 'acceptance': PolicyAcceptanceSerializer(acceptance).data})


class DeviceRegisterView(APIView):
    def post(self, request):
        company = user_company(request.user)
        if not company:
            return Response({'detail': 'No company assigned'}, status=400)
        device_id = request.data.get('device_id')
        if not device_id:
            return Response({'detail': 'device_id required'}, status=400)
        app_version = request.data.get('app_version', '')
        platform = request.data.get('platform', 'windows')
        payload = agent_version_payload(platform, app_version, company=company)
        status_value = 'OUTDATED' if payload['force_update_required'] else 'ACTIVE'
        device, _ = Device.objects.update_or_create(
            company=company,
            device_id=device_id,
            defaults={
                'user': request.user,
                'hostname': request.data.get('hostname', ''),
                'platform': platform,
                'local_ip': request.data.get('local_ip', ''),
                'public_ip': client_ip(request),
                'app_version': app_version,
                'status': status_value,
                'last_seen_at': timezone.now(),
            }
        )
        create_audit(request, 'DEVICE_REGISTERED', obj=device, company=company)
        if payload['force_update_required']:
            create_outdated_agent_alert(company, request.user, device, payload)
            return Response({'detail': 'Desktop agent version is not supported. Update required.', 'blocked': True, 'blocked_reason': 'OUTDATED_AGENT', 'version': payload, 'device': DeviceSerializer(device).data}, status=426)
        return Response(DeviceSerializer(device).data)


class SessionStartView(APIView):
    def post(self, request):
        company = user_company(request.user)
        if not company:
            return Response({'detail': 'No company assigned'}, status=400)
        blocked = company_tracking_gate(company)
        if blocked:
            return blocked
        device = Device.objects.filter(company=company, user=request.user, device_id=request.data.get('device_id')).first()
        if not device:
            return Response({'detail': 'Register this device before starting a work session.'}, status=400)
        blocked = unsupported_agent_response(request, company=company, user=request.user, device=device)
        if blocked:
            if device:
                device.status = 'OUTDATED'
                device.save(update_fields=['status'])
            return blocked
        profile = getattr(request.user, 'profile', None)
        if profile and (profile.policy_status == 'POLICY_DECLINED' or not profile.is_active_employee):
            return Response({'blocked': True, 'blocked_reason': 'POLICY_DECLINED' if profile.policy_status == 'POLICY_DECLINED' else 'EMPLOYEE_INACTIVE',
                             'detail': 'Employee must be reactivated before monitoring.'}, status=403)
        accepted, policy = has_accepted_latest_policy(request.user, company)
        if not accepted:
            return Response({'blocked': True, 'blocked_reason': 'POLICY_NOT_ACCEPTED' if policy else 'POLICY_NOT_CONFIGURED',
                             'detail': 'Latest active monitoring policy must be accepted before starting a work session.',
                             'policy_id': getattr(policy, 'id', None)}, status=403)
        WorkSession.objects.filter(company=company, user=request.user, status='RUNNING').update(status='AUTO_STOPPED', stopped_at=timezone.now())
        session = WorkSession.objects.create(company=company, user=request.user, device=device, started_at=timezone.now(), status='RUNNING')
        create_audit(request, 'SESSION_STARTED', obj=session, company=company)
        return Response(WorkSessionSerializer(session).data)


class SessionStopView(APIView):
    def post(self, request):
        company = user_company(request.user)
        session = WorkSession.objects.filter(company=company, user=request.user, id=request.data.get('session_id'), status='RUNNING').first()
        if not session:
            return Response({'detail': 'Running session not found'}, status=404)
        session.status = 'STOPPED'
        session.stopped_at = timezone.now()
        session.save()
        create_audit(request, 'SESSION_STOPPED', obj=session, company=company)
        return Response(WorkSessionSerializer(session).data)


class SessionStatusView(APIView):
    def get(self, request):
        company = user_company(request.user)
        session = WorkSession.objects.filter(company=company, user=request.user, status='RUNNING').order_by('-id').first()
        return Response(WorkSessionSerializer(session).data if session else {'status': 'NO_RUNNING_SESSION'})


class HeartbeatUploadView(APIView):
    def post(self, request):
        company = user_company(request.user)
        device = Device.objects.filter(company=company, user=request.user, device_id=request.data.get('device_id')).first()
        blocked = unsupported_agent_response(request, company=company, user=request.user, device=device)
        if blocked:
            if device:
                device.status = 'OUTDATED'
                device.save(update_fields=['status'])
            return blocked
        blocked = policy_upload_gate(request, company)
        if blocked:
            return blocked
        session = WorkSession.objects.filter(company=company, user=request.user, id=request.data.get('session_id'), status='RUNNING').first()
        if not session:
            return Response({'detail': 'Running session not found'}, status=404)
        if not device or session.device_id != device.pk:
            return Response({'detail': 'Session device does not match the registered device.'}, status=400)
        try:
            active_seconds = int(request.data.get('active_seconds', 0))
            idle_seconds = int(request.data.get('idle_seconds', 0))
        except (ValueError, TypeError):
            raise ValidationError({'seconds': 'Use nonnegative whole seconds.'})
        if not 0 <= active_seconds <= 3600 or not 0 <= idle_seconds <= 3600:
            raise ValidationError({'seconds': 'Use nonnegative whole seconds (maximum 3600).'} )
        if device:
            device.last_seen_at = timezone.now()
            device.public_ip = client_ip(request)
            device.app_version = request.data.get('app_version', device.app_version)
            device.save(update_fields=['last_seen_at', 'public_ip', 'app_version'])
        hb = Heartbeat.objects.create(company=company, user=request.user, device=device, session=session, active_seconds=active_seconds, idle_seconds=idle_seconds, is_idle=request.data.get('is_idle', False), app_version=request.data.get('app_version', ''), public_ip=client_ip(request))
        session.active_seconds += active_seconds
        session.idle_seconds += idle_seconds
        session.save(update_fields=['active_seconds', 'idle_seconds', 'updated_at'])
        if hb.idle_seconds >= company.idle_threshold_seconds:
            Alert.objects.get_or_create(company=company, user=request.user, device=device, alert_type='LONG_IDLE_TIME', title='Long idle time detected', defaults={'severity': 'MEDIUM', 'message': f'Idle seconds reported: {hb.idle_seconds}'})
        return Response(HeartbeatSerializer(hb).data)


class ActivityBatchUploadView(APIView):
    def post(self, request):
        company = user_company(request.user)
        device = Device.objects.filter(company=company, user=request.user, device_id=request.data.get('device_id')).first()
        blocked = unsupported_agent_response(request, company=company, user=request.user, device=device)
        if blocked:
            if device:
                device.status = 'OUTDATED'
                device.save(update_fields=['status'])
            return blocked
        blocked = policy_upload_gate(request, company)
        if blocked:
            return blocked
        session = WorkSession.objects.filter(company=company, user=request.user, id=request.data.get('session_id'), status='RUNNING').first()
        if not session:
            return Response({'detail': 'Running session not found'}, status=404)
        if not device or session.device_id != device.pk:
            return Response({'detail': 'Session device does not match the registered device.'}, status=400)
        activities = request.data.get('activities')
        if not isinstance(activities, list) or not 1 <= len(activities) <= 500:
            raise ValidationError({'activities': 'Provide between 1 and 500 activity records.'})
        for row in activities:
            if not isinstance(row, dict):
                raise ValidationError({'activities': 'Each activity must be an object.'})
            for field, limit in (('app_name', 255), ('domain', 255), ('window_title', 16384), ('url', 16384)):
                value = row.get(field, '')
                if value is None:
                    value = ''
                if not isinstance(value, str) or len(value) > limit:
                    raise ValidationError({field: f'Use text with at most {limit} characters.'})
                row[field] = value.strip()
            row['domain'], row['url'] = normalize_web_context(row['domain'], row['url'])
            for field in ('duration_seconds', 'mouse_count', 'keyboard_count'):
                try:
                    count = int(row.get(field, 0))
                except (ValueError, TypeError):
                    raise ValidationError({field: 'Use a nonnegative whole number.'})
                if count < 0 or count > 86400:
                    raise ValidationError({field: 'Use a value between 0 and 86400.'})
                row[field] = count
        created = []
        for row in activities:
            category = classify_activity(company, request.user, row.get('app_name', ''), row.get('domain', ''),
                                         row.get('window_title', ''), row.get('url', ''))
            obj = ActivityLog.objects.create(company=company, user=request.user, device=device, session=session, app_name=row.get('app_name', ''), window_title=row.get('window_title', ''), domain=row.get('domain', ''), url=row.get('url', ''), duration_seconds=row.get('duration_seconds', 0), mouse_count=row.get('mouse_count', 0), keyboard_count=row.get('keyboard_count', 0), productivity=category)
            created.append(obj)
        return Response({'created': len(created), 'items': ActivityLogSerializer(created, many=True).data})


def classify_activity(company, user, app_name, domain, title, url=''):
    domain, url = normalize_web_context(domain, url)
    dept = getattr(user.profile, 'department', None) if hasattr(user, 'profile') else None
    candidates = AppWebsiteCategory.objects.filter(company=company, is_active=True).filter(models.Q(department=dept) | models.Q(department__isnull=True))
    # Department rules and longer patterns take precedence over company defaults.
    rules = sorted(candidates, key=lambda rule: (rule.department_id is not None, len(rule.pattern), rule.pk), reverse=True)
    for rule in rules:
        pattern = rule.pattern.strip().lower()
        kind = rule.pattern_type.upper()
        if not pattern:
            continue
        if kind == 'DOMAIN':
            host = domain
            matches = host == pattern or host.endswith('.' + pattern)
        elif kind == 'APP':
            matches = pattern in (app_name or '').lower()
        elif kind in ('WINDOW', 'WINDOW_TITLE', 'TITLE'):
            matches = pattern in (title or '').lower()
        elif kind == 'URL':
            matches = url_rule_matches(pattern, url)
        else:
            matches = pattern in f'{app_name} {domain} {title} {url}'.lower()
        if matches:
            return rule.category
    return 'UNKNOWN'


class ScreenshotUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        company = user_company(request.user)
        device = Device.objects.filter(company=company, user=request.user, device_id=request.data.get('device_id')).first()
        blocked = unsupported_agent_response(request, company=company, user=request.user, device=device)
        if blocked:
            if device:
                device.status = 'OUTDATED'
                device.save(update_fields=['status'])
            return blocked
        blocked = policy_upload_gate(request, company)
        if blocked:
            return blocked
        session_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('session_id'))
        session = WorkSession.objects.filter(company=company, user=request.user, id=session_id, status='RUNNING').first()
        if not session:
            return Response({'detail': 'Running session not found'}, status=404)
        if not device or session.device_id != device.pk:
            return Response({'detail': 'Session device does not match the registered device.'}, status=400)
        uploaded_file = request.FILES.get('file')
        if settings.SCREENSHOT_STORAGE_MODE != 'local':
            return Response({'detail': 'Screenshot storage is not configured for uploads. Configure local storage for staging.'}, status=501)
        if not uploaded_file:
            raise ValidationError({'file': 'Attach a PNG, JPEG or WebP screenshot.'})
        if uploaded_file.size > 20 * 1024 * 1024:
            raise ValidationError({'file': 'Screenshot must be no larger than 20 MB.'})
        try:
            uploaded_file = serializers.ImageField().run_validation(uploaded_file)
        except (DjangoValidationError, ValidationError) as exc:
            raise ValidationError({'file': 'Upload a valid PNG, JPEG or WebP image.'}) from exc
        if uploaded_file.image.format not in ('PNG', 'JPEG', 'WEBP'):
            raise ValidationError({'file': 'Use PNG, JPEG or WebP.'})
        digest = hashlib.sha256()
        for chunk in uploaded_file.chunks():
            digest.update(chunk)
        checksum = digest.hexdigest()
        if request.data.get('checksum') and request.data['checksum'].lower() != checksum:
            raise ValidationError({'checksum': 'Screenshot checksum does not match the uploaded file.'})
        uploaded_file.seek(0)
        extension = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp'}[uploaded_file.image.format]
        uploaded_file.name = f'{secrets.token_hex(16)}.{extension}'
        screenshot = Screenshot.objects.create(company=company, user=request.user, device=device, session=session,
            captured_at=timezone.now(), storage_mode='local', file=uploaded_file, checksum=checksum, status='UPLOADED')
        return Response(ScreenshotSerializer(screenshot, context={'request': request}).data)


class DashboardSummaryView(APIView):
    def get(self, request):
        company = user_company(request.user)
        role = get_role(request.user)
        today = timezone.localdate()

        if is_super_admin(request.user):
            return Response({
                'scope': 'ALL_COMPANIES',
                'companies': Company.objects.count(),
                'users': User.objects.count(),
                'sessions_today': WorkSession.objects.filter(started_at__date=today).count(),
                'open_alerts': Alert.objects.filter(status='OPEN').count(),
                'trial_codes_generated': DemoTrialCode.objects.count(),
                'active_trials': Company.objects.filter(status='TRIAL_ACTIVE').count(),
            })

        if not company:
            return Response({'scope': 'NO_COMPANY', 'companies': 0, 'users': 0, 'sessions_today': 0, 'open_alerts': 0})

        if role in ['COMPANY_ADMIN', 'HR_ADMIN']:
            return Response({
                'scope': 'OWN_COMPANY',
                'company_id': company.id,
                'companies': 1,
                'users': User.objects.filter(profile__company=company).count(),
                'sessions_today': WorkSession.objects.filter(company=company, started_at__date=today).count(),
                'open_alerts': Alert.objects.filter(company=company, status='OPEN').count(),
                'policy_declined_users': User.objects.filter(profile__company=company, profile__policy_status='POLICY_DECLINED').count(),
            })

        if role == 'SALES_ADMIN':
            stats = trial_dashboard_stats(request.user)
            return Response({'scope': 'OWN_SALES_TRIALS', 'company_id': company.id,
                             'trial_codes_generated': stats['codes_generated'], **stats})

        if role == 'MANAGER':
            team_user_ids = list(User.objects.filter(profile__company=company, profile__manager=request.user).values_list('id', flat=True))
            return Response({
                'scope': 'ASSIGNED_TEAM',
                'company_id': company.id,
                'team_users': len(team_user_ids),
                'sessions_today': WorkSession.objects.filter(company=company, user_id__in=team_user_ids, started_at__date=today).count(),
                'open_alerts': Alert.objects.filter(company=company, user_id__in=team_user_ids, status='OPEN').count(),
            })

        if role == 'EMPLOYEE':
            return Response({
                'scope': 'OWN_USER',
                'company_id': company.id,
                'sessions_today': WorkSession.objects.filter(company=company, user=request.user, started_at__date=today).count(),
                'open_alerts': Alert.objects.filter(company=company, user=request.user, status='OPEN').count(),
                'latest_policy_status': getattr(request.user.profile, 'policy_status', ''),
            })

        return Response({'detail': 'Role not allowed for dashboard summary.'}, status=403)


class AttendanceReportView(APIView):
    def get(self, request):
        if get_role(request.user) == 'SALES_ADMIN':
            return Response({'detail': 'Sales/Admin can access trial-sales data only.'}, status=403)
        qs = WorkSession.objects.all() if is_super_admin(request.user) else WorkSession.objects.filter(company=user_company(request.user))
        if get_role(request.user) == 'MANAGER':
            qs = qs.filter(user__profile__manager=request.user)
        elif get_role(request.user) == 'EMPLOYEE':
            qs = qs.filter(user=request.user)
        qs = qs.values('user__email').annotate(active_seconds=Sum('active_seconds'), idle_seconds=Sum('idle_seconds'), sessions=Count('id')).order_by('user__email')
        return Response(list(qs))


class ActivityReportView(APIView):
    def get(self, request):
        if get_role(request.user) == 'SALES_ADMIN':
            return Response({'detail': 'Sales/Admin can access trial-sales data only.'}, status=403)
        qs = ActivityLog.objects.all() if is_super_admin(request.user) else ActivityLog.objects.filter(company=user_company(request.user))
        if get_role(request.user) == 'MANAGER':
            qs = qs.filter(user__profile__manager=request.user)
        elif get_role(request.user) == 'EMPLOYEE':
            qs = qs.filter(user=request.user)
        qs = qs.values('app_name', 'productivity').annotate(seconds=Sum('duration_seconds')).order_by('-seconds')[:100]
        return Response(list(qs))


def trial_code_error(code):
    if not code or code.status != 'ACTIVE' or code.expiry_date <= timezone.now():
        return 'Invalid, expired or unavailable demo code.'
    if code.single_use and (code.used_by_company_id or code.used_at):
        return 'Demo code already used.'
    if not code.plan or code.plan.code != 'TRIAL' or not code.plan.is_active:
        return 'The trial plan is unavailable. Contact the person who provided this code.'
    return None


class TrialValidateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        data = TrialCodeInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        code = DemoTrialCode.objects.select_related('plan').filter(code=data.validated_data['code']).first()
        error = trial_code_error(code)
        if error:
            return Response({'valid': False, 'reason': error}, status=400)
        # Public validation exposes only the terms needed for signup, never contacts or internal remarks.
        return Response({'valid': True, 'code': {
            'code': code.code, 'trial_duration_days': code.trial_duration_days,
            'allowed_users': code.allowed_users, 'allowed_devices': code.allowed_devices,
            'expiry_date': code.expiry_date, 'plan_name': code.plan.name,
        }})


class TrialSignupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = TrialSignupInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                # Serialize redemptions of a code so a single-use code cannot create two tenants.
                code = DemoTrialCode.objects.select_for_update().filter(code=data['code']).first()
                error = trial_code_error(code)
                if error:
                    TrialSignupLog.objects.create(demo_code=code, signup_email=data['admin_email'],
                        ip_address=client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        status='FAILED', message=error)
                    return Response({'detail': error}, status=400)
                plan = code.plan
                start = timezone.now()
                end = start + timedelta(days=code.trial_duration_days)
                user = User.objects.create_user(username=data['admin_email'], email=data['admin_email'],
                                                first_name=data['admin_name'], password=data['password'])
                company = Company.objects.create(name=data['company_name'], legal_name=data['company_name'],
                    employee_id_prefix=data['employee_id_prefix'],
                    contact_person=data['admin_name'], email=data['admin_email'], mobile=data['mobile'],
                    status='TRIAL_ACTIVE', plan=plan, trial_start_date=start, trial_end_date=end,
                    allowed_users=code.allowed_users, allowed_devices=code.allowed_devices,
                    screenshot_retention_days=plan.screenshot_retention_days)
                Subscription.objects.create(company=company, plan=plan, status='TRIAL', active_user_count=1,
                    price_per_user=plan.price_per_user, billing_cycle='NONE', trial_start_date=start, trial_end_date=end)
                Profile.objects.create(user=user, company=company, role='COMPANY_ADMIN', can_generate_trials=False,
                                       employee_code=assign_employee_id(company))
                PolicyVersion.objects.create(company=company, version='1.0', title='Employee Monitoring Policy',
                    body='This company uses BOLD WorkPulse for attendance, activity and screenshot monitoring during work sessions. '
                         'Employees must accept this policy before starting a session. Company administrators should publish '
                         'their organization-specific monitoring policy before inviting employees.', is_active=True)
                code.used_by_company, code.used_at = company, start
                if code.single_use:
                    code.status = 'USED'
                code.save(update_fields=['used_by_company', 'used_at', 'status', 'updated_at'])
                TrialSignupLog.objects.create(company=company, demo_code=code, admin_user=user, signup_email=user.email,
                    ip_address=client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    status='SUCCESS', message='Trial company created')
                create_audit(request, 'TRIAL_SIGNUP', obj=company, company=company,
                             after={'demo_code_id': code.pk, 'admin_user_id': user.pk})
        except IntegrityError:
            return Response({'detail': 'The email or code was just used. Refresh and try another email or code.'}, status=409)
        return Response({'company': CompanySerializer(company).data,
                         'admin_user': {'id': user.pk, 'email': user.email}}, status=201)


def locked_trial_company(request, company_id):
    # Lock only the company row (plan is nullable and must not be part of FOR UPDATE).
    allowed = allowed_trial_company_queryset(request.user).filter(pk=company_id).values('pk')
    company = Company.objects.select_for_update().filter(pk__in=allowed).first()
    if not company:
        raise Http404('Trial company not found in your allowed scope.')
    if company.status not in ('TRIAL_ACTIVE', 'TRIAL_EXPIRED'):
        raise ValidationError({'company_id': 'Only active or expired trials allow this action.'})
    return company


class TrialExtendView(APIView):
    permission_classes = [IsTrialAdmin]

    @transaction.atomic
    def post(self, request):
        serializer = TrialExtendInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        company = locked_trial_company(request, data['company_id'])
        before = CompanySerializer(company).data
        base = max(company.trial_end_date or timezone.now(), timezone.now())
        company.trial_end_date = base + timedelta(days=data['days'])
        company.status = 'TRIAL_ACTIVE'
        company.save(update_fields=['trial_end_date', 'status', 'updated_at'])
        if company.plan:
            Subscription.objects.update_or_create(company=company, defaults={
                'plan': company.plan, 'trial_end_date': company.trial_end_date, 'status': 'TRIAL'})
        create_audit(request, 'TRIAL_EXTENDED', obj=company, before=dict(before),
                     after={'days': data['days'], 'trial_end_date': str(company.trial_end_date)}, company=company)
        return Response(CompanySerializer(company).data)


class TrialConvertView(APIView):
    permission_classes = [IsTrialAdmin]

    @transaction.atomic
    def post(self, request):
        serializer = TrialConvertInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        company = locked_trial_company(request, data['company_id'])
        new_plan = CompanyPlan.objects.filter(code=data['plan_code'], is_active=True).first()
        if not new_plan:
            raise ValidationError({'plan_code': 'Select an active plan.'})
        internal = new_plan.code == 'INTERNAL'
        if internal and not is_super_admin(request.user):
            raise PermissionDenied('Only Super Admin can convert a trial to Internal / Not Billable.')
        if data['billing_cycle'] != 'NONE' and internal or data['billing_cycle'] == 'NONE' and not internal:
            raise ValidationError({'billing_cycle': 'Use NONE for Internal; MONTHLY or ANNUAL for paid plans.'})
        active_users = User.objects.filter(is_active=True, profile__company=company, profile__is_active_employee=True).count()
        active_devices = Device.objects.filter(company=company).exclude(status='BLOCKED').count()
        if active_users > new_plan.max_users or active_devices > new_plan.max_devices:
            raise ValidationError({'plan_code': 'Plan capacity is below the current user/device count. Choose a larger plan.'})
        before = CompanySerializer(company).data
        old_plan = company.plan
        company.plan, company.status, company.billing_disabled = new_plan, 'INTERNAL' if internal else 'ACTIVE', internal
        company.allowed_users, company.allowed_devices = new_plan.max_users, new_plan.max_devices
        company.screenshot_retention_days = new_plan.screenshot_retention_days
        company.save()
        sub, _ = Subscription.objects.get_or_create(company=company, defaults={'plan': new_plan})
        sub.plan, sub.status = new_plan, 'INTERNAL_NOT_BILLABLE' if internal else 'ACTIVE'
        sub.billing_cycle, sub.converted_at, sub.price_per_user = data['billing_cycle'], timezone.now(), new_plan.price_per_user
        sub.active_user_count = active_users
        sub.save()
        signup = TrialSignupLog.objects.filter(company=company, status='SUCCESS').select_related('demo_code').first()
        code = signup.demo_code if signup else DemoTrialCode.objects.filter(used_by_company=company).first()
        if code and code.single_use:
            code.status = 'CONVERTED'
            code.save(update_fields=['status', 'updated_at'])
        log = TrialConversionLog.objects.create(company=company, demo_code=code, converted_by=request.user,
            old_plan=old_plan, new_plan=new_plan, billing_cycle=sub.billing_cycle, notes=data['notes'])
        create_audit(request, 'TRIAL_CONVERTED', obj=company, before=dict(before),
                     after={'new_plan': new_plan.code, 'billing_cycle': sub.billing_cycle}, company=company)
        return Response(TrialConversionLogSerializer(log).data)


class TrialCancelView(APIView):
    permission_classes = [IsTrialAdmin]

    @transaction.atomic
    def post(self, request):
        serializer = TrialCompanyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = locked_trial_company(request, serializer.validated_data['company_id'])
        before = CompanySerializer(company).data
        company.status = 'SUSPENDED'
        company.save(update_fields=['status', 'updated_at'])
        Subscription.objects.filter(company=company).update(status='CANCELLED')
        WorkSession.objects.filter(company=company, status='RUNNING').update(status='AUTO_STOPPED', stopped_at=timezone.now())
        DemoTrialCode.objects.filter(used_by_company=company, single_use=True).update(status='CANCELLED')
        create_audit(request, 'TRIAL_CANCELLED', obj=company, before=dict(before), after={'status': 'SUSPENDED'}, company=company)
        return Response({'status': 'cancelled', 'company': CompanySerializer(company).data})


class TrialCompanyListView(APIView):
    permission_classes = [IsTrialAdmin]

    def get(self, request):
        qs = allowed_trial_company_queryset(request.user)
        expire_trial_companies(qs)
        status = request.query_params.get('status')
        if status:
            if status not in dict(Company.STATUS_CHOICES):
                raise ValidationError({'status': 'Select a valid company status.'})
            qs = qs.filter(status=status)
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(models.Q(name__icontains=search) | models.Q(email__icontains=search))
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs.order_by('-id'), request, view=self)
        return paginator.get_paginated_response(CompanySerializer(page, many=True).data)


def trial_dashboard_stats(user):
    codes = allowed_trial_code_queryset(user)
    companies = allowed_trial_company_queryset(user)
    expire_trial_companies(companies)
    used = codes.filter(models.Q(used_at__isnull=False) | models.Q(trialsignuplog__status='SUCCESS')).distinct().count()
    converted = companies.filter(models.Q(trialconversionlog__isnull=False) |
                                 models.Q(demotrialcode__status='CONVERTED')).distinct().count()
    activated = companies.count()
    return {'codes_generated': codes.count(), 'codes_used': used,
        'active_trials': companies.filter(status='TRIAL_ACTIVE').count(),
        'expired_trials': companies.filter(status='TRIAL_EXPIRED').count(),
        'cancelled_trials': companies.filter(status='SUSPENDED').count(), 'activated_trials': activated,
        'converted_trials': converted, 'conversion_percent': round(converted / activated * 100, 2) if activated else 0}


class TrialDashboardView(APIView):
    permission_classes = [IsTrialAdmin]

    def get(self, request):
        return Response(trial_dashboard_stats(request.user))


class ERPPublicIngestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @transaction.atomic
    def post(self, request):
        if not isinstance(request.data, dict):
            return Response({'detail': 'Request body must be a JSON object.'}, status=400)
        token = request.META.get('HTTP_X_WORKPULSE_TOKEN')
        connector = ERPConnector.objects.filter(api_token=token, is_active=True).first()
        if not connector:
            return Response({'detail': 'Invalid connector token'}, status=403)
        Company.objects.select_for_update().get(pk=connector.company_id)
        connector = ERPConnector.objects.select_for_update().filter(pk=connector.pk, api_token=token, is_active=True).first()
        if not connector:
            return Response({'detail': 'Invalid connector token'}, status=403)
        if not isinstance(connector.allowed_event_types, list):
            return Response({'detail': 'Connector event settings are invalid. Ask an administrator to save the allowed events.'}, status=400)
        event_type = request.data.get('event_type')
        if not isinstance(event_type, str) or event_type not in connector.allowed_event_types:
            return Response({'detail': 'Event type is not allowed for this connector.'}, status=400)
        payload = request.data.get('payload', {})
        if not isinstance(payload, dict):
            return Response({'detail': 'payload must be a JSON object.'}, status=400)
        external_id = request.data.get('external_id', '')
        if event_type in EMPLOYEE_EVENTS:
            for company_id in (request.data.get('company_id'), payload.get('company_id')):
                if company_id is not None and str(company_id) != str(connector.company_id):
                    return Response({'detail': 'company_id must match the connector company.'}, status=400)
        elif not isinstance(external_id, str) or len(external_id) > 128:
            return Response({'detail': 'external_id must be a string of at most 128 characters.'}, status=400)
        try:
            validate_employee_event(event_type, payload, external_id)
            if event_type in EMPLOYEE_EVENTS:
                external_id = external_id.strip()
        except EmployeeSyncError as exc:
            return Response({'detail': str(exc)}, status=400)
        event = ERPEvent.objects.create(company=connector.company, connector=connector,
                                        event_type=event_type, external_id=external_id, payload=payload)
        if event_type not in EMPLOYEE_EVENTS:
            return Response({'status': 'received', 'event': ERPEventSerializer(event).data}, status=202)
        try:
            result = ingest_employee_event(event)
        except EmployeeSyncError as exc:
            event.processing_error = str(exc)
            event.save(update_fields=['processing_error'])
            return Response({'status': 'failed', 'detail': str(exc), 'code': exc.code, 'event_id': event.pk}, status=409)
        except Exception:
            logger.exception('Employee ERP event %s failed', event.pk)
            event.processing_error = 'Unexpected processing error; see server logs.'
            event.save(update_fields=['processing_error'])
            return Response({'status': 'failed', 'detail': event.processing_error,
                             'event_id': event.pk}, status=500)
        return Response({'status': 'processed', **result, 'event': ERPEventSerializer(event).data})


class S3PresignedPlaceholderView(APIView):
    def post(self, request):
        blocked = unsupported_agent_response(request, company=user_company(request.user), user=request.user)
        if blocked:
            return blocked
        return Response({
            'storage_mode': settings.SCREENSHOT_STORAGE_MODE,
            'external_configuration_required': settings.SCREENSHOT_STORAGE_MODE != 'local',
            'local_upload_url': f'{settings.BACKEND_BASE_URL}/api/agent/screenshots/upload/',
            'message': 'S3 presigned upload/download is structurally ready. Configure S3 fields in .env for production.'
        })
