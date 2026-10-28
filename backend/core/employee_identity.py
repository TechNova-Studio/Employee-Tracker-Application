"""Company employee IDs shared by admin creation and ERP synchronization."""
import re

from .models import Profile


class EmployeeIdentityError(ValueError):
    pass


def normalize_employee_id(value):
    if not isinstance(value, str):
        raise EmployeeIdentityError('employee_id must be a string of at most 64 characters.')
    value = value.strip()
    if len(value) > 64 or any(char.isspace() or not char.isprintable() for char in value):
        raise EmployeeIdentityError('employee_id must have at most 64 characters without spaces.')
    return value


def normalize_prefix(value):
    if not isinstance(value, str):
        raise EmployeeIdentityError('Employee ID prefix must be text.')
    value = value.strip().upper()
    if len(value) > 32 or (value and not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]*', value)):
        raise EmployeeIdentityError('Use at most 32 letters, numbers, hyphens or underscores for the prefix.')
    return value


def assign_employee_id(company, requested='', *, user_id=None):
    """Caller must hold this company's row lock until the profile is saved."""
    code = normalize_employee_id(requested)
    profiles = Profile.objects.filter(company=company)
    if user_id is not None:
        profiles = profiles.exclude(user_id=user_id)
    if code:
        if profiles.filter(employee_code__iexact=code).exists():
            raise EmployeeIdentityError('Employee ID already belongs to another user in this company.')
        if company.employee_id_prefix:
            suffix = re.fullmatch(re.escape(company.employee_id_prefix) + r'(\d+)', code, re.IGNORECASE)
            if suffix:
                number = int(suffix.group(1))
                if company.next_employee_number <= number < 9223372036854775806:
                    company.next_employee_number = number + 1
                    company.save(update_fields=['next_employee_number'])
        return code
    if not company.employee_id_prefix:
        return ''
    number = company.next_employee_number
    while True:
        if number >= 9223372036854775806:
            raise EmployeeIdentityError('Employee ID sequence is exhausted.')
        code = f'{company.employee_id_prefix}{number:04d}'
        number += 1
        if not profiles.filter(employee_code__iexact=code).exists():
            break
    company.next_employee_number = number
    company.save(update_fields=['next_employee_number'])
    return code
