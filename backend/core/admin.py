from django.contrib import admin
from .models import *

for model in [
    CompanyPlan, Company, Department, Profile, Subscription, Device, AgentVersion, PolicyVersion,
    PolicyAcceptance, WorkSession, Heartbeat, ActivityLog, Screenshot, ScreenshotAccessLog,
    AppWebsiteCategory, Alert, DailyAISummary, ManagerReview, DemoTrialCode, TrialSignupLog,
    TrialConversionLog, ERPConnector, ERPEvent, AuditLog, BillingInvoice
]:
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass
