import React, { useEffect, useMemo, useState } from "react";
import { api, getStoredUser, getToken } from "./lib/api.js";
import { canViewPage } from "./lib/access.js";
import LoginPage from "./pages/LoginPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import CompanyPage from "./pages/CompanyPage.jsx";
import UsersPage from "./pages/UsersPage.jsx";
import DepartmentsPage from "./pages/DepartmentsPage.jsx";
import DevicesPage from "./pages/DevicesPage.jsx";
import PolicyPage from "./pages/PolicyPage.jsx";
import AgentVersionPage from "./pages/AgentVersionPage.jsx";
import AttendancePage from "./pages/AttendancePage.jsx";
import ActivityPage from "./pages/ActivityPage.jsx";
import ScreenshotPage from "./pages/ScreenshotPage.jsx";
import AISummaryPage from "./pages/AISummaryPage.jsx";
import AlertsPage from "./pages/AlertsPage.jsx";
import TrialCodesPage from "./pages/TrialCodesPage.jsx";
import TrialDashboardPage from "./pages/TrialDashboardPage.jsx";
import TrialSignupPage from "./pages/TrialSignupPage.jsx";
import BillingPage from "./pages/BillingPage.jsx";
import ERPConnectorPage from "./pages/ERPConnectorPage.jsx";
import AuditLogPage from "./pages/AuditLogPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import GenericListPage from "./pages/GenericListPage.jsx";
import AppShell from "./components/AppShell.jsx";
import { useTheme } from "./components/ThemeToggle.jsx";

const menu = [
  ["dashboard", "Dashboard"],
  ["companies", "Companies"],
  ["users", "Users / Employees"],
  ["departments", "Departments"],
  ["devices", "Devices"],
  ["agent-versions", "Agent Versions"],
  ["policies", "Policy + Acceptances"],
  ["attendance", "Attendance Sessions"],
  ["activity", "Activity Timeline"],
  ["screenshots", "Screenshot Viewer"],
  ["productivity-categories", "Productivity Rules"],
  ["alerts", "Alerts"],
  ["ai-summaries", "AI Daily Summaries"],
  ["trial-codes", "Demo Code Generator"],
  ["trial-dashboard", "Trial Dashboard"],
  ["billing", "Billing & Subscriptions"],
  ["erp-connectors", "ERP Connector Settings"],
  ["audit-logs", "Audit Logs"],
  ["settings", "Settings"],
];

export default function App() {
  const [theme, setTheme] = useTheme();
  const [user, setUser] = useState(() => (getToken() ? getStoredUser() : null));
  const [page, setPage] = useState("dashboard");
  const [authChecked, setAuthChecked] = useState(!getToken());
  useEffect(() => {
    if (!getToken()) return;
    let mounted = true;
    api('/auth/me/').then(data => {
      if (!mounted) return;
      localStorage.setItem('workpulse_user', JSON.stringify(data.user));
      setUser(data.user);
    }).catch(() => {
      if (!mounted) return;
      localStorage.removeItem('workpulse_token');
      localStorage.removeItem('workpulse_user');
      setUser(null);
    }).finally(() => { if (mounted) setAuthChecked(true); });
    return () => { mounted = false; };
  }, []);
  const availableMenu = useMemo(() => menu.filter(([key]) => canViewPage(user, key)), [user]);
  const activePage = availableMenu.some(([key]) => key === page) ? page : availableMenu[0]?.[0];
  if (window.location.pathname.includes('trial-signup')) return <TrialSignupPage />;
  if (!authChecked) return <div className="login-shell">Checking access...</div>;
  if (!user) return <LoginPage onLogin={setUser} theme={theme} setTheme={setTheme} />;
  if (!activePage) return <div className="login-shell"><div>No Admin Web pages are available for this account.
    <button onClick={() => {
      localStorage.removeItem('workpulse_token');
      localStorage.removeItem('workpulse_user');
      setUser(null);
    }}>Logout</button></div></div>;
  let content;
  if (activePage === "dashboard") content = <DashboardPage user={user} onNavigate={setPage} />;
  else if (activePage === "companies") content = <CompanyPage />;
  else if (activePage === "users") content = <UsersPage />;
  else if (activePage === "departments") content = <DepartmentsPage />;
  else if (activePage === "devices") content = <DevicesPage />;
  else if (activePage === "policies") content = <PolicyPage />;
  else if (activePage === "agent-versions") content = <AgentVersionPage />;
  else if (activePage === "attendance") content = <AttendancePage />;
  else if (activePage === "activity") content = <ActivityPage />;
  else if (activePage === "screenshots") content = <ScreenshotPage />;
  else if (activePage === "ai-summaries") content = <AISummaryPage />;
  else if (activePage === "alerts") content = <AlertsPage />;
  else if (activePage === "trial-codes") content = <TrialCodesPage />;
  else if (activePage === "trial-dashboard") content = <TrialDashboardPage />;
  else if (activePage === "billing") content = <BillingPage />;
  else if (activePage === "erp-connectors") content = <ERPConnectorPage />;
  else if (activePage === "audit-logs") content = <AuditLogPage />;
  else if (activePage === "productivity-categories")
    content = (
      <GenericListPage
        endpoint="productivity-categories"
        title="Productivity Rules"
        hint="Company-level and department-wise app/domain/window classification rules."
      />
    );
  else if (activePage === "settings") content = <SettingsPage />;
  else content = <div>Page unavailable.</div>;
  return (
    <AppShell user={user} menu={availableMenu} page={activePage} onNavigate={setPage} theme={theme} setTheme={setTheme}
      onLogout={() => {
            localStorage.removeItem('workpulse_token');
            localStorage.removeItem('workpulse_user');
            setUser(null);
            setPage("dashboard");
      }}>{content}</AppShell>
  );
}
