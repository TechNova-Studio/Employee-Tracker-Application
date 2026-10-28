"""Lifecycle events resolve connector + CRM external_id through an explicit map."""
import hashlib

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token

from .employee_identity import EmployeeIdentityError, assign_employee_id, normalize_employee_id
from .erp_employee_mapping import normalize_external_id, save_employee_mapping
from .models import Company, ERPEmployeeMapping, Profile, WorkSession


EMPLOYEE_EVENTS = frozenset({
    'erp_user_created', 'erp_user_updated', 'erp_user_active', 'erp_user_inactive',
})


class EmployeeSyncError(Exception):
    def __init__(self, detail, code='employee_sync_error'):
        super().__init__(detail)
        self.code = code


def validate_employee_event(event_type, payload, external_id=''):
    if event_type not in EMPLOYEE_EVENTS:
        return
    try:
        normalize_external_id(external_id)
    except ValueError as exc:
        raise EmployeeSyncError(str(exc))
    if not isinstance(payload, dict):
        raise EmployeeSyncError('payload must be a JSON object.')
    # Optional WorkPulse display code; never used to locate the employee.
    try:
        code = normalize_employee_id(payload.get('employee_id', payload.get('employee_code', '')))
        if 'employee_id' in payload and 'employee_code' in payload:
            if code.casefold() != normalize_employee_id(payload['employee_code']).casefold():
                raise EmployeeIdentityError('employee_id and employee_code must contain the same display code.')
    except EmployeeIdentityError as exc:
        raise EmployeeSyncError(str(exc))
    if code:
        payload['employee_id'] = code
    email = payload.get('email')
    if email is not None:
        try:
            if not isinstance(email, str) or len(email) > 254:
                raise ValidationError('Invalid email.')
            email = email.strip()
            validate_email(email)
        except ValidationError:
            raise EmployeeSyncError('A valid email is required when email is supplied.')
        payload['email'] = email
    if event_type == 'erp_user_created' and not email:
        raise EmployeeSyncError('A valid email is required to create an employee.')
    for field, limit in (('first_name', 150), ('last_name', 150), ('mobile', 30)):
        if field in payload and (not isinstance(payload[field], str) or len(payload[field]) > limit):
            raise EmployeeSyncError(f'{field} must be a string of at most {limit} characters.')
    if 'is_active' in payload and not isinstance(payload['is_active'], bool):
        raise EmployeeSyncError('is_active must be a boolean.')
    if event_type in ('erp_user_active', 'erp_user_inactive') and 'is_active' in payload:
        if payload['is_active'] != (event_type == 'erp_user_active'):
            raise EmployeeSyncError('is_active conflicts with event_type.')


def _set_status(user, profile, active):
    user.is_active = active
    user.save(update_fields=['is_active'])
    profile.is_active_employee = active
    profile.save(update_fields=['is_active_employee'])
    if not active:
        Token.objects.filter(user=user).delete()
        WorkSession.objects.filter(user=user, company=profile.company, status='RUNNING').update(
            status='AUTO_STOPPED', stopped_at=timezone.now())


def process_employee_event(event, company):
    payload = event.payload
    email = payload.get('email', '')
    mapping = ERPEmployeeMapping.objects.filter(connector_id=event.connector_id, external_id=event.external_id).first()
    if mapping is None:
        if event.event_type != 'erp_user_created':
            raise EmployeeSyncError('No mapping for this CRM employee ID. Link the existing employee first.', 'mapping_required')
        # Collision detection prevents duplicates; this is not an email-based link.
        if User.objects.filter(email__iexact=email).exists():
            raise EmployeeSyncError('An account already uses this email. Review and explicitly map the existing employee.', 'mapping_required')
        digest = hashlib.sha256(f'{event.connector_id}:{event.external_id}'.encode()).hexdigest()
        username = f'erp_{company.pk}_{digest}'
        if User.objects.filter(username=username).exists():
            raise EmployeeSyncError('Generated employee username already exists; review the mapping.', 'mapping_required')
        user = User(username=username, email=email)
        user.set_unusable_password()
        user.save()
        profile = Profile.objects.create(user=user, company=company, role='EMPLOYEE')
        save_employee_mapping(event.connector, event.external_id, user.pk)
        action = 'created'
    else:
        user = User.objects.get(pk=mapping.user_id)
        profile = Profile.objects.filter(user=user).first()
        if profile is None or profile.company_id != company.pk or profile.role == 'SUPER_ADMIN':
            raise EmployeeSyncError('The mapped employee is outside the connector company or is a protected Super Admin.', 'invalid_mapping')
        action = 'updated'
    if event.event_type in ('erp_user_created', 'erp_user_updated'):
        code = payload.get('employee_id', '')
        try:
            if code:
                profile.employee_code = assign_employee_id(company, code, user_id=user.pk)
            elif not profile.employee_code:
                profile.employee_code = assign_employee_id(company, user_id=user.pk)
        except EmployeeIdentityError as exc:
            raise EmployeeSyncError(str(exc))
        if email:
            if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                raise EmployeeSyncError('Email already belongs to another account.')
            user.email = email
        for field in ('first_name', 'last_name'):
            if field in payload:
                setattr(user, field, payload[field])
        user.save(update_fields=['email', 'first_name', 'last_name'])
        if 'mobile' in payload:
            profile.mobile = payload['mobile']
        profile.save(update_fields=['employee_code', 'mobile'])
        if 'is_active' in payload:
            _set_status(user, profile, payload['is_active'])
    else:
        active = event.event_type == 'erp_user_active'
        _set_status(user, profile, active)
        action = 'activated' if active else 'deactivated'
    return {'action': action, 'user_id': user.pk, 'workpulse_employee_id': user.pk,
            'external_id': event.external_id, 'employee_id': profile.employee_code,
            'is_active': profile.is_active_employee}


def ingest_employee_event(event):
    with transaction.atomic():
        company = Company.objects.select_for_update().get(pk=event.company_id)
        result = process_employee_event(event, company)
        event.processed = True
        event.processed_at = timezone.now()
        event.processing_error = ''
        event.save(update_fields=['processed', 'processed_at', 'processing_error'])
    return result
