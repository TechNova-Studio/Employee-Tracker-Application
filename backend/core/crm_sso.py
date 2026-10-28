"""CRM OAuth bridge. Only configured servers can assert employee identities."""
import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import URLError

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from .models import CRMLoginAttempt, ERPConnector, ERPEmployeeMapping, Profile
from .serializers import UserSerializer, CompanySerializer


class SSOFailure(APIException):
    status_code = 403
    default_detail = 'CRM authentication failed. Start login again.'


class LoginThrottle(AnonRateThrottle):
    rate = '20/min'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def provider_config(key):
    value = settings.CRM_SSO_PROVIDERS.get(key)
    if not isinstance(value, dict):
        raise ValidationError('Unknown CRM provider.')
    required = ('authorization_url', 'token_url', 'userinfo_url', 'client_id', 'connector_id', 'crm_company_id', 'issuer')
    if any(not value.get(field) for field in required):
        raise ValidationError('CRM login is not configured. Contact your administrator.')
    for field in ('authorization_url', 'token_url', 'userinfo_url', 'issuer'):
        url = urlsplit(value[field])
        local = settings.DEBUG and settings.CRM_SSO_ALLOW_LOOPBACK_HTTP and url.hostname in ('localhost', '127.0.0.1')
        if (url.scheme != 'https' and not (local and url.scheme == 'http')) or not url.hostname or url.username or url.password or url.fragment or url.query:
            raise ValidationError('CRM provider URLs must be HTTPS without credentials, query or fragment.')
    if not ERPConnector.objects.filter(pk=value['connector_id'], is_active=True).exists():
        raise SSOFailure('CRM connector is inactive or unavailable.')
    return value


def crm_json(url, data=None, bearer=None):
    headers = {'Accept': 'application/json'}
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    req = Request(url, data=urlencode(data).encode() if data is not None else None, headers=headers)
    try:
        with build_opener(NoRedirect).open(req, timeout=8) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError('Response too large')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError('Invalid response')
            return result
    except (URLError, OSError, ValueError):
        error = APIException('CRM could not verify this login. Start again or contact your administrator.')
        error.status_code = 502
        raise error from None


class PublicSSOView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method == 'POST' and not isinstance(request.data, dict):
            raise ValidationError('A JSON object is required.')

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        response['Pragma'] = 'no-cache'
        return response


class CRMProvidersView(PublicSSOView):
    def get(self, request):
        providers = []
        for key, value in settings.CRM_SSO_PROVIDERS.items():
            try:
                provider_config(key)
            except (ValidationError, SSOFailure):
                continue
            providers.append({'id': key, 'name': value.get('name', key)})
        return Response({'providers': providers})


class CRMStartView(PublicSSOView):
    def post(self, request):
        key = str(request.data.get('provider', ''))
        cfg = provider_config(key)
        redirect = str(request.data.get('redirect_uri', ''))
        parsed = urlsplit(redirect)
        try:
            port = parsed.port
        except ValueError:
            port = None
        if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not port
                or parsed.netloc != f'127.0.0.1:{port}' or parsed.path != '/crm/callback'
                or parsed.query or parsed.fragment):
            raise ValidationError('Use the registered 127.0.0.1 loopback callback.')
        challenge = str(request.data.get('code_challenge', ''))
        state = str(request.data.get('state', ''))
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', challenge) or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', state):
            raise ValidationError('A valid S256 challenge and random state are required.')
        secret = secrets.token_urlsafe(32)
        CRMLoginAttempt.objects.create(secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
            provider=key, challenge=challenge, redirect_uri=redirect,
            expires_at=timezone.now() + timedelta(minutes=5))
        query = dict(response_type='code', client_id=cfg['client_id'], redirect_uri=redirect,
                     scope='workpulse_identity', code_challenge=challenge, code_challenge_method='S256', state=state)
        return Response({'attempt_token': secret, 'authorization_url': cfg['authorization_url'] + '?' + urlencode(query),
                         'issuer': cfg['issuer'], 'expires_in': 300})


@method_decorator(sensitive_post_parameters("code", "code_verifier", "attempt_token"), name="dispatch")
class CRMExchangeView(PublicSSOView):
    def post(self, request):
        secret = request.data.get('attempt_token', '')
        verifier = request.data.get('code_verifier', '')
        code = request.data.get('code', '')
        if not isinstance(secret, str) or not isinstance(verifier, str) or not isinstance(code, str):
            raise ValidationError('Invalid login exchange.')
        if not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}', verifier) or not 1 <= len(code) <= 2048 or len(secret) > 128:
            raise ValidationError('Invalid code or PKCE verifier.')
        attempt = CRMLoginAttempt.objects.filter(secret_hash=hashlib.sha256(secret.encode()).hexdigest()).first()
        if not attempt or attempt.used_at or attempt.expires_at <= timezone.now():
            raise SSOFailure('Login expired or already used. Start again.')
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        if not hmac.compare_digest(challenge, attempt.challenge):
            raise SSOFailure('PKCE verification failed.')
        cfg = provider_config(attempt.provider)
        # Compare-and-set is safe across multiple web workers; never exchange a code twice.
        claimed = CRMLoginAttempt.objects.filter(pk=attempt.pk, used_at__isnull=True,
            expires_at__gt=timezone.now()).update(used_at=timezone.now())
        if not claimed:
            raise SSOFailure('Login already used. Start again.')
        token_request = dict(grant_type='authorization_code', client_id=cfg['client_id'],
                            code=code, redirect_uri=attempt.redirect_uri, code_verifier=verifier)
        if cfg.get('client_secret'):
            token_request['client_secret'] = cfg['client_secret']
        tokens = crm_json(cfg['token_url'], token_request)
        access = tokens.get('access_token')
        if str(tokens.get('token_type', '')).lower() != 'bearer' or not isinstance(access, str) or not access or len(access) > 8192 or '\n' in access or '\r' in access:
            raise SSOFailure('CRM returned an invalid access token.')
        identity = crm_json(cfg['userinfo_url'], bearer=access)
        external = identity.get('external_id')
        if (identity.get('is_active') is not True or identity.get('issuer') != cfg['issuer']
                or identity.get('audience') != cfg['client_id']
                or identity.get('company_id') != str(cfg['crm_company_id'])
                or not isinstance(external, str) or not external or len(external) > 128):
            raise SSOFailure('CRM identity is inactive or does not match this integration.')
        from .views import unsupported_agent_response, create_audit
        with transaction.atomic():
            connector = ERPConnector.objects.select_for_update().filter(pk=cfg['connector_id'], is_active=True).first()
            if not connector:
                raise SSOFailure('CRM connector is inactive.')
            # PostgreSQL cannot lock the nullable side of a reverse OneToOne join.
            # Lock the employee profile separately so missing profiles still fail closed.
            mapping = ERPEmployeeMapping.objects.select_for_update().select_related('user', 'connector__company').filter(
                connector=connector, external_id=external).first()
            if not mapping:
                return Response({'detail': 'CRM employee mapping is required. Contact your administrator.',
                                 'blocked_reason': 'MAPPING_REQUIRED'}, status=409)
            user = mapping.user
            profile = Profile.objects.select_for_update().filter(user_id=user.pk).first()
            company = mapping.connector.company
            if (not profile or profile.company_id != company.pk or profile.role == 'SUPER_ADMIN'
                    or not user.is_active or not profile.is_active_employee):
                raise SSOFailure('Mapped WorkPulse employee is inactive or belongs to another company.')
            if profile.policy_status == 'POLICY_DECLINED':
                raise SSOFailure('Monitoring policy was declined. Contact HR/Admin.')
            if company.status not in ('ACTIVE', 'INTERNAL', 'TRIAL_ACTIVE') or company.is_trial_expired():
                raise SSOFailure('Company access is suspended or the trial has expired.')
            if not request.data.get('app_version') or request.data.get('platform') not in ('windows', 'darwin', 'linux'):
                raise ValidationError('Desktop app_version and platform are required.')
            blocked = unsupported_agent_response(request, company=company, user=user)
            if blocked:
                return blocked
            token, _ = Token.objects.get_or_create(user=user)
            create_audit(request, 'CRM_LOGIN', obj=user, company=company)
            return Response({'token': token.key, 'user': UserSerializer(user).data,
                'company': CompanySerializer(company).data, 'screenshot_interval_seconds': company.screenshot_interval_seconds,
                'idle_threshold_seconds': company.idle_threshold_seconds})
