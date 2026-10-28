"""Shared mapping validation for HTTP APIs, lifecycle events and CSV import."""
from django.db import transaction
from rest_framework.exceptions import APIException, ValidationError

from .models import AuditLog, Company, ERPConnector, ERPEmployeeMapping, Profile


class MappingConflict(APIException):
    status_code = 409
    default_code = 'mapping_conflict'


def normalize_external_id(value):
    if not isinstance(value, str):
        raise ValueError('external_id must be the stable CRM employee ID as a string.')
    value = value.strip()
    if not value or len(value) > 128 or any(c.isspace() or not c.isprintable() for c in value):
        raise ValueError('external_id must contain 1–128 characters without spaces or control characters.')
    return value


def mapping_data(mapping):
    return {'id': mapping.pk, 'connector_id': mapping.connector_id,
            'external_id': mapping.external_id, 'workpulse_employee_id': mapping.user_id}


@transaction.atomic
def save_employee_mapping(connector, external_id, user_id, *, actor=None):
    try:
        external_id = normalize_external_id(external_id)
    except ValueError as exc:
        raise ValidationError({'external_id': str(exc)})
    # All identity writes use company -> connector lock order, including ingestion.
    Company.objects.select_for_update().get(pk=connector.company_id)
    connector = ERPConnector.objects.select_for_update().get(pk=connector.pk)
    profile = Profile.objects.select_for_update().filter(user_id=user_id, company_id=connector.company_id).first()
    if profile is None or profile.role == 'SUPER_ADMIN':
        raise ValidationError({'workpulse_employee_id': 'Select an existing company employee. Super Admin cannot be mapped.'})
    existing = ERPEmployeeMapping.objects.filter(connector=connector, external_id=external_id).first()
    if existing:
        if existing.user_id != user_id:
            raise MappingConflict('This CRM employee ID is already linked to another WorkPulse employee.')
        return existing, False
    if ERPEmployeeMapping.objects.filter(connector=connector, user_id=user_id).exists():
        raise MappingConflict('This WorkPulse employee already has a different CRM ID in this connector.')
    mapping = ERPEmployeeMapping.objects.create(connector=connector, external_id=external_id, user_id=user_id)
    AuditLog.objects.create(company_id=connector.company_id, actor=actor,
        action_type='CREATE_ERP_EMPLOYEE_MAPPING', object_type='ERPEmployeeMapping',
        object_id=str(mapping.pk), after_data=mapping_data(mapping))
    return mapping, True


@transaction.atomic
def save_mapping_rows(connector, rows, *, dry_run=False, actor=None):
    """Validate the entire batch; any error rolls back every mapping and audit row."""
    results, errors, seen_external, seen_users = [], [], set(), set()
    for number, row in enumerate(rows, start=1):
        identity, user_id = row['external_id'], row['workpulse_employee_id']
        if identity in seen_external or user_id in seen_users:
            errors.append({'row': number, 'detail': 'Duplicate CRM or WorkPulse employee ID in this file.'})
            continue
        seen_external.add(identity)
        seen_users.add(user_id)
        try:
            mapping, created = save_employee_mapping(connector, identity, user_id, actor=actor)
        except (ValidationError, MappingConflict) as exc:
            errors.append({'row': number, 'detail': exc.detail})
        else:
            result = mapping_data(mapping)
            result['created'] = created
            if dry_run:
                result.pop('id')
            results.append(result)
    if errors:
        raise ValidationError({'rows': errors})
    if dry_run:
        transaction.set_rollback(True)
    return {'dry_run': dry_run, 'created': sum(r['created'] for r in results),
            'unchanged': sum(not r['created'] for r in results), 'mappings': results}
