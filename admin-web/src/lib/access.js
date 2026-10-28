// Match the server's role permissions when deciding which Admin Web pages to show.
const ALL = ['SUPER_ADMIN', 'COMPANY_ADMIN', 'HR_ADMIN', 'SALES_ADMIN', 'MANAGER', 'EMPLOYEE'];
const ADMINS = ['SUPER_ADMIN', 'COMPANY_ADMIN', 'HR_ADMIN'];
const OPERATIONS = [...ADMINS, 'MANAGER', 'EMPLOYEE'];

const pageRoles = {
  dashboard: ALL,
  companies: ['SUPER_ADMIN', 'COMPANY_ADMIN'],
  users: [...ADMINS, 'MANAGER'],
  departments: ADMINS,
  devices: OPERATIONS,
  'agent-versions': OPERATIONS,
  policies: ADMINS,
  attendance: OPERATIONS,
  activity: OPERATIONS,
  screenshots: OPERATIONS,
  'productivity-categories': ADMINS,
  alerts: OPERATIONS,
  'ai-summaries': OPERATIONS,
  billing: ['SUPER_ADMIN', 'COMPANY_ADMIN'],
  'erp-connectors': ADMINS,
  'audit-logs': ADMINS,
  settings: ['SUPER_ADMIN', 'COMPANY_ADMIN'],
};

export function canViewPage(user, page) {
  const role = user?.profile?.role;
  if (!role) return false;
  if (page === 'trial-codes' || page === 'trial-dashboard') {
    return role === 'SUPER_ADMIN' ||
      (['COMPANY_ADMIN', 'SALES_ADMIN'].includes(role) && !!user.profile.can_generate_trials);
  }
  return (pageRoles[page] || []).includes(role);
}

export function canManageAgentVersions(user) {
  return ['SUPER_ADMIN', 'COMPANY_ADMIN'].includes(user?.profile?.role);
}

export function canCloseAlerts(user) {
  return ADMINS.includes(user?.profile?.role);
}

export function canDeleteScreenshots(user) {
  return [...ADMINS, 'MANAGER'].includes(user?.profile?.role);
}
