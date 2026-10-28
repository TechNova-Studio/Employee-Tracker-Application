from .crm_sso import CRMProvidersView, CRMStartView, CRMExchangeView
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *
from .erp_mapping_api import ERPEmployeeMappingViewSet
from .erp_employee_import_api import ERPEmployeeImportView
from .productivity_api import ProductivityRuleViewSet
from .dashboard_api import TeamDashboardView

router = DefaultRouter()
router.register('plans', CompanyPlanViewSet)
router.register('companies', CompanyViewSet)
router.register('departments', DepartmentViewSet)
router.register('users', UserViewSet)
router.register('subscriptions', SubscriptionViewSet)
router.register('devices', DeviceViewSet)
router.register('agent-versions', AgentVersionViewSet)
router.register('policies', PolicyVersionViewSet)
router.register('policy-acceptances', PolicyAcceptanceViewSet)
router.register('sessions', WorkSessionViewSet)
router.register('activities', ActivityLogViewSet)
router.register('screenshots', ScreenshotViewSet)
router.register('productivity-categories', ProductivityRuleViewSet)
router.register('alerts', AlertViewSet)
router.register('ai-summaries', DailyAISummaryViewSet)
router.register('manager-reviews', ManagerReviewViewSet)
router.register('demo-trial-codes', DemoTrialCodeViewSet)
router.register('trial-signup-logs', TrialSignupLogViewSet)
router.register('trial-conversion-logs', TrialConversionLogViewSet)
router.register('erp-connectors', ERPConnectorViewSet)
router.register('erp-events', ERPEventViewSet)
router.register('audit-logs', AuditLogViewSet)
router.register('billing-invoices', BillingInvoiceViewSet)

urlpatterns = [
    path('health/', health),
    path('auth/crm/providers/', CRMProvidersView.as_view()),
    path('auth/crm/start/', CRMStartView.as_view()),
    path('auth/crm/exchange/', CRMExchangeView.as_view()),
    path('auth/login/', LoginView.as_view()),
    path('auth/logout/', LogoutView.as_view()),
    path('auth/me/', CurrentUserView.as_view()),

    path('agent/version-check/', AgentVersionCheckView.as_view()),
    path('agent/device/register/', DeviceRegisterView.as_view()),
    path('agent/session/start/', SessionStartView.as_view()),
    path('agent/session/stop/', SessionStopView.as_view()),
    path('agent/session/status/', SessionStatusView.as_view()),
    path('agent/heartbeat/', HeartbeatUploadView.as_view()),
    path('agent/activity/batch/', ActivityBatchUploadView.as_view()),
    path('agent/screenshots/upload/', ScreenshotUploadView.as_view()),
    path('agent/screenshots/presigned-placeholder/', S3PresignedPlaceholderView.as_view()),

    path('policy/current/', CurrentPolicyView.as_view()),
    path('policy/accept/', PolicyAcceptView.as_view()),
    path('policy/decline/', PolicyDeclineView.as_view()),

    path('reports/dashboard-summary/', DashboardSummaryView.as_view()),
    path('reports/team-dashboard/', TeamDashboardView.as_view(), name='team-dashboard'),
    path('reports/attendance/', AttendanceReportView.as_view()),
    path('reports/activity/', ActivityReportView.as_view()),

    path('trial/validate-code/', TrialValidateView.as_view()),
    path('trial/signup/', TrialSignupView.as_view()),
    path('trial/extend/', TrialExtendView.as_view()),
    path('trial/convert/', TrialConvertView.as_view()),
    path('trial/cancel/', TrialCancelView.as_view()),
    path('trial/companies/', TrialCompanyListView.as_view()),
    path('trial/dashboard/', TrialDashboardView.as_view()),

    path('erp/ingest/', ERPPublicIngestView.as_view()),
    path('erp/employees/import/', ERPEmployeeImportView.as_view(), name='erp-employee-import'),
    path('erp/', include(([
        path('employee-mappings/', ERPEmployeeMappingViewSet.as_view({'get': 'list', 'post': 'create'}), name='erp-employee-mappings'),
        path('employee-mappings/bulk/', ERPEmployeeMappingViewSet.as_view({'post': 'bulk'}), name='erp-employee-mappings-bulk'),
        path('employee-mappings/form-options/', ERPEmployeeMappingViewSet.as_view({'get': 'form_options'}), name='erp-employee-mappings-options'),
        path('employee-mappings/<int:pk>/', ERPEmployeeMappingViewSet.as_view({'get': 'retrieve'}), name='erp-employee-mapping-detail'),
    ], 'erp-mapping'))),
    path('', include(router.urls)),
]
