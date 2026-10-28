from rest_framework.permissions import BasePermission, SAFE_METHODS

ROLE_SUPER_ADMIN = 'SUPER_ADMIN'
ROLE_COMPANY_ADMIN = 'COMPANY_ADMIN'
ROLE_HR_ADMIN = 'HR_ADMIN'
ROLE_SALES_ADMIN = 'SALES_ADMIN'
ROLE_MANAGER = 'MANAGER'
ROLE_EMPLOYEE = 'EMPLOYEE'

ADMIN_ROLES = {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN}
TRIAL_ROLES = {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_SALES_ADMIN}
MANAGEMENT_READ_ROLES = {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN, ROLE_SALES_ADMIN, ROLE_MANAGER}


def get_role(user):
    if not user or not user.is_authenticated or not hasattr(user, 'profile'):
        return None
    return user.profile.role


def is_role(user, *roles):
    return get_role(user) in roles


def is_super_admin_user(user):
    return is_role(user, ROLE_SUPER_ADMIN)


def is_company_admin_user(user):
    return is_role(user, ROLE_COMPANY_ADMIN)


def is_hr_admin_user(user):
    return is_role(user, ROLE_HR_ADMIN)


def is_sales_admin_user(user):
    return is_role(user, ROLE_SALES_ADMIN)


def is_manager_user(user):
    return is_role(user, ROLE_MANAGER)


def is_employee_user(user):
    return is_role(user, ROLE_EMPLOYEE)


class IsAuthenticatedRole(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and hasattr(request.user, 'profile'))


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_super_admin_user(request.user)


class IsSuperOrCompanyAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_role(request.user, ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN)


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return get_role(request.user) in ADMIN_ROLES


class IsAdminOrReadOnlyScoped(BasePermission):
    def has_permission(self, request, view):
        role = get_role(request.user)
        if request.method in SAFE_METHODS:
            return role in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE}
        return role in ADMIN_ROLES


class IsCompanyAdminOrHR(BasePermission):
    def has_permission(self, request, view):
        return is_role(request.user, ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN)


class IsTrialAdmin(BasePermission):
    def has_permission(self, request, view):
        if not is_role(request.user, ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_SALES_ADMIN):
            return False
        if is_super_admin_user(request.user):
            return True
        return bool(getattr(request.user.profile, 'can_generate_trials', False))


class IsManagerOrAdminReview(BasePermission):
    def has_permission(self, request, view):
        role = get_role(request.user)
        if request.method in SAFE_METHODS:
            return role in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE}
        return role in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN, ROLE_MANAGER}


class IsScreenshotUser(BasePermission):
    def has_permission(self, request, view):
        role = get_role(request.user)
        if request.method in SAFE_METHODS:
            return role in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE}
        return role in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN, ROLE_MANAGER}


class IsAuditReader(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS and is_role(request.user, ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN)


class IsBillingAdmin(BasePermission):
    def has_permission(self, request, view):
        role = get_role(request.user)
        if request.method in SAFE_METHODS:
            return role in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN}
        return role == ROLE_SUPER_ADMIN


class IsCompanyPlanPermission(BasePermission):
    """Plans are centrally controlled. Only Super Admin may create/update/delete."""
    def has_permission(self, request, view):
        role = get_role(request.user)
        if request.method in SAFE_METHODS:
            return role in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN, ROLE_SALES_ADMIN}
        return role == ROLE_SUPER_ADMIN


class IsCompanyPermission(BasePermission):
    """Company creation/deletion is Super Admin only; Company Admin may read/update own basic settings."""
    def has_permission(self, request, view):
        role = get_role(request.user)
        if request.method in SAFE_METHODS:
            return role in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN}
        if request.method in {'POST', 'DELETE'}:
            return role == ROLE_SUPER_ADMIN
        if request.method in {'PUT', 'PATCH'}:
            return role in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN}
        return False


class IsPolicyAcceptanceReader(BasePermission):
    """Policy acceptance records are system logs and must not be modified from the list API."""
    def has_permission(self, request, view):
        if request.method not in SAFE_METHODS:
            return False
        return get_role(request.user) in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE}


class IsOperationsReader(BasePermission):
    """Attendance and activity records are written only by the desktop agent endpoints."""
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS and get_role(request.user) in {
            ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE}


class IsERPEventReader(BasePermission):
    """ERP event payloads are sensitive. No employee access. Public ingestion uses a separate token endpoint."""
    def has_permission(self, request, view):
        if request.method not in SAFE_METHODS:
            return False
        return get_role(request.user) in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN, ROLE_MANAGER}


class IsAgentVersionPermission(BasePermission):
    """Super Admin can manage global/company agent versions; Company Admin can manage own company versions only."""
    def has_permission(self, request, view):
        role = get_role(request.user)
        if request.method in SAFE_METHODS:
            return role in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE}
        return role in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN}

class IsERPConnectorPermission(BasePermission):
    """ERP connector settings are company-sensitive. Super/Company Admin can manage; HR/Admin may read own company only through queryset scoping."""
    def has_permission(self, request, view):
        role = get_role(request.user)
        if request.method in SAFE_METHODS:
            return role in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN}
        return role in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN}

class IsAISummaryReader(BasePermission):
    """Scoped reads; only admins/managers can request rule-based generation."""
    def has_permission(self, request, view):
        if getattr(view, 'action', None) == 'generate':
            return get_role(request.user) in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN, ROLE_MANAGER}
        if request.method not in SAFE_METHODS:
            return False
        return get_role(request.user) in {ROLE_SUPER_ADMIN, ROLE_COMPANY_ADMIN, ROLE_HR_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE}
