from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta, date
from core.models import *
import secrets

PASSWORD = 'Demo@12345'


class Command(BaseCommand):
    help = 'Seed BOLD WorkPulse staging data.'

    def handle(self, *args, **options):
        plans = {}
        plan_specs = [
            ('INTERNAL', 'Internal', 0, 500, 500, 365, True, True),
            ('TRIAL', 'Trial', 0, 10, 10, 7, True, False),
            ('BASIC', 'Basic', 199, 25, 25, 15, False, False),
            ('PRO', 'Pro', 299, 75, 75, 30, True, False),
            ('BUSINESS', 'Business', 399, 250, 250, 60, True, True),
            ('ENTERPRISE', 'Enterprise', 0, 1000, 1000, 90, True, True),
        ]
        for code, name, price, max_users, max_devices, retention, ai, erp in plan_specs:
            plans[code], _ = CompanyPlan.objects.update_or_create(
                code=code,
                defaults={'name': name, 'price_per_user': price, 'max_users': max_users, 'max_devices': max_devices, 'screenshot_retention_days': retention, 'ai_enabled': ai, 'erp_connector_enabled': erp, 'is_active': True}
            )

        glutape, _ = Company.objects.update_or_create(
            name='Glutape India Pvt. Ltd.',
            defaults={'legal_name':'Glutape India Pvt. Ltd.', 'contact_person':'Management', 'email':'admin@glutape.local', 'mobile':'', 'status':'INTERNAL', 'plan': plans['INTERNAL'], 'allowed_users':500, 'allowed_devices':500, 'screenshot_interval_seconds':300, 'screenshot_retention_days':365, 'idle_threshold_seconds':300, 'billing_disabled': True}
        )
        Subscription.objects.update_or_create(company=glutape, defaults={'plan': plans['INTERNAL'], 'status':'INTERNAL_NOT_BILLABLE', 'active_user_count':6, 'price_per_user':0, 'billing_cycle':'NONE', 'notes':'Internal Glutape tenant; billing disabled.'})

        depts = {}
        for name in ['Sales', 'Accounts', 'Dispatch', 'IT', 'Management']:
            depts[name], _ = Department.objects.update_or_create(company=glutape, name=name)

        def create_user(email, first, last, role, dept=None, manager=None, can_trials=False):
            user, created = User.objects.update_or_create(username=email, defaults={'email': email, 'first_name': first, 'last_name': last, 'is_active': True})
            user.set_password(PASSWORD)
            user.save()
            Profile.objects.update_or_create(user=user, defaults={'company': glutape if role != 'SUPER_ADMIN' else None, 'role': role, 'department': depts.get(dept) if dept else None, 'manager': manager, 'employee_code': email.split('@')[0].upper(), 'policy_status':'ACCEPTED' if role != 'EMPLOYEE' else 'NOT_ACCEPTED', 'can_generate_trials': can_trials or role in ['SUPER_ADMIN','COMPANY_ADMIN','SALES_ADMIN'], 'is_active_employee': True})
            return user

        super_admin = create_user('superadmin@boldworkpulse.local', 'Super', 'Admin', 'SUPER_ADMIN', can_trials=True)
        admin = create_user('admin@glutape.local', 'Glutape', 'Admin', 'COMPANY_ADMIN', 'Management', can_trials=True)
        sales_admin = create_user('salesadmin@glutape.local', 'Sales', 'Admin', 'SALES_ADMIN', 'Sales', can_trials=True)
        hr_admin = create_user('hr@glutape.local', 'HR', 'Admin', 'HR_ADMIN', 'Management')
        manager = create_user('manager@glutape.local', 'Team', 'Manager', 'MANAGER', 'Sales')
        employee = create_user('employee@glutape.local', 'Demo', 'Employee', 'EMPLOYEE', 'Sales', manager=manager)

        AgentVersion.objects.update_or_create(company=None, platform='windows', defaults={'latest_version':'1.0.0','minimum_supported_version':'1.0.0','download_url':'','checksum':'','release_notes':'Initial staging release','is_active':True})
        policy, _ = PolicyVersion.objects.update_or_create(company=glutape, version='1.0', defaults={'title':'Glutape Employee Monitoring Policy', 'body':'BOLD WorkPulse transparently records work session start/stop time, app/window titles, domain names where technically available, idle/active status and periodic screenshots only during active work sessions. It does not record keystroke content, clipboard, webcam or microphone. Employee must accept this policy before starting monitored work.', 'is_active':True, 'created_by':admin})
        for u in [admin, sales_admin, hr_admin, manager]:
            PolicyAcceptance.objects.get_or_create(company=glutape, user=u, policy=policy, status='ACCEPTED', defaults={'accepted_at':timezone.now(), 'ip_address':'127.0.0.1'})

        device, _ = Device.objects.update_or_create(company=glutape, device_id='DEMO-DEVICE-001', defaults={'user':employee,'hostname':'DEMO-LAPTOP','platform':'windows','local_ip':'192.168.1.10','public_ip':'127.0.0.1','app_version':'1.0.0','status':'ACTIVE','last_seen_at':timezone.now()})
        session, _ = WorkSession.objects.get_or_create(company=glutape, user=employee, device=device, started_at=timezone.now()-timedelta(hours=2), defaults={'active_seconds':5400,'idle_seconds':900,'status':'STOPPED','stopped_at':timezone.now()-timedelta(minutes=5)})
        ActivityLog.objects.get_or_create(company=glutape, user=employee, device=device, session=session, app_name='Chrome', window_title='CRM Follow-up Dashboard', domain='erp.glutape.local', duration_seconds=2400, productivity='PRODUCTIVE')
        ActivityLog.objects.get_or_create(company=glutape, user=employee, device=device, session=session, app_name='WhatsApp', window_title='Customer follow-up', domain='web.whatsapp.com', duration_seconds=1200, productivity='PRODUCTIVE')
        Screenshot.objects.get_or_create(company=glutape, user=employee, device=device, session=session, object_key='sample/screenshots/demo.png', storage_mode='local', status='UPLOADED')
        Alert.objects.get_or_create(company=glutape, user=employee, device=device, alert_type='LONG_IDLE_TIME', title='Long idle time detected', defaults={'severity':'MEDIUM','message':'Demo alert for staging.'})
        DailyAISummary.objects.update_or_create(company=glutape, user=employee, date=timezone.localdate(), defaults={'active_seconds':5400,'idle_seconds':900,'productive_seconds':3600,'neutral_seconds':900,'unproductive_seconds':0,'top_apps':['Chrome','WhatsApp'],'top_websites':['erp.glutape.local','web.whatsapp.com'],'screenshot_count':1,'unusual_activity_flags':[],'summary_text':'Demo employee spent most time on CRM follow-up and customer communication. No major risk flags in sample data.','risk_flags':[],'confidence_score':80,'manager_review_status':'PENDING'})

        for pattern, cat, dept in [('erp.glutape.local','PRODUCTIVE',None), ('web.whatsapp.com','PRODUCTIVE',depts['Sales']), ('youtube.com','UNPRODUCTIVE',depts['Accounts']), ('youtube.com','NEUTRAL',depts['Sales'])]:
            AppWebsiteCategory.objects.get_or_create(company=glutape, department=dept, pattern_type='DOMAIN', pattern=pattern, defaults={'category':cat, 'notes':'Seeded productivity rule'})

        for code, days, users, devices in [('GLU-TRIAL-5DAY',5,5,5),('GLU-TRIAL-7DAY',7,10,10),('GLU-TRIAL-10DAY',10,10,10)]:
            DemoTrialCode.objects.update_or_create(code=code, defaults={'customer_company_name':f'Sample Customer {days} Day','contact_person_name':'Trial Contact','mobile_number':'9999999999','email':f'trial{days}@example.com','trial_duration_days':days,'allowed_users':users,'allowed_devices':devices,'plan':plans['TRIAL'],'expiry_date':timezone.now()+timedelta(days=30),'generated_by':sales_admin,'sales_owner':sales_admin,'lead_source':'Seed Data','remarks':'Seeded trial code','status':'ACTIVE','single_use':False})

        active_trial = self.make_trial_company('Sample Active Trial Company', plans['TRIAL'], offset_days=7, status='TRIAL_ACTIVE')
        expired_trial = self.make_trial_company('Sample Expired Trial Company', plans['TRIAL'], offset_days=-1, status='TRIAL_EXPIRED')
        converted = self.make_trial_company('Sample Converted Company', plans['BASIC'], offset_days=0, status='ACTIVE')
        for sample_code, sample_company, sample_status in [('SAMPLE-ACTIVE-TRIAL', active_trial, 'USED'), ('SAMPLE-EXPIRED-TRIAL', expired_trial, 'USED'), ('SAMPLE-CONVERTED-TRIAL', converted, 'CONVERTED')]:
            DemoTrialCode.objects.update_or_create(code=sample_code, defaults={'customer_company_name': sample_company.name, 'contact_person_name':'Trial Admin', 'mobile_number':'9999999999', 'email':sample_company.email, 'trial_duration_days':7, 'allowed_users':10, 'allowed_devices':10, 'plan':plans['TRIAL'], 'expiry_date':timezone.now()+timedelta(days=30), 'generated_by':sales_admin, 'sales_owner':sales_admin, 'lead_source':'Seed Data', 'remarks':'Linked sample trial company', 'status':sample_status, 'single_use':True, 'used_by_company':sample_company, 'used_at':timezone.now()})
        TrialConversionLog.objects.get_or_create(company=converted, converted_by=super_admin, old_plan=plans['TRIAL'], new_plan=plans['BASIC'], billing_cycle='MONTHLY', notes='Seeded converted trial.')

        connector, created = ERPConnector.objects.get_or_create(
            company=glutape, name='Glutape ERP Staging Connector',
            defaults={'api_token': secrets.token_urlsafe(32), 'is_active': True, 'allowed_event_types': []},
        )
        connector.allowed_event_types = list(set(connector.allowed_event_types or []) | {
            'lead_created', 'pi_created', 'invoice_created', 'dispatch_updated',
            'capa_created', 'inventory_entry_created', 'erp_user_created',
            'erp_user_updated', 'erp_user_active', 'erp_user_inactive',
        })
        connector.save(update_fields=['allowed_event_types'])
        self.stdout.write(self.style.SUCCESS('BOLD WorkPulse seed data created.'))
        self.stdout.write(self.style.SUCCESS(f'Demo password for all users: {PASSWORD}'))

    def make_trial_company(self, name, plan, offset_days, status):
        now = timezone.now()
        end = now + timedelta(days=offset_days)
        company, _ = Company.objects.update_or_create(name=name, defaults={'legal_name':name,'contact_person':'Trial Admin','email':name.lower().replace(' ','')+'@example.com','status':status,'plan':plan,'trial_start_date':now-timedelta(days=3),'trial_end_date':end,'allowed_users':10,'allowed_devices':10,'screenshot_interval_seconds':300,'screenshot_retention_days':plan.screenshot_retention_days})
        Subscription.objects.update_or_create(company=company, defaults={'plan':plan,'status':'ACTIVE' if status=='ACTIVE' else ('EXPIRED' if status=='TRIAL_EXPIRED' else 'TRIAL'),'active_user_count':1,'price_per_user':plan.price_per_user,'billing_cycle':'MONTHLY' if status=='ACTIVE' else 'NONE','trial_start_date':company.trial_start_date,'trial_end_date':company.trial_end_date})
        username = 'admin@' + name.lower().replace(' ','').replace('.','') + '.local'
        user, _ = User.objects.update_or_create(username=username, defaults={'email':username,'first_name':'Trial','last_name':'Admin','is_active':True})
        user.set_password(PASSWORD)
        user.save()
        Profile.objects.update_or_create(user=user, defaults={'company':company,'role':'COMPANY_ADMIN','policy_status':'NOT_ACCEPTED'})
        PolicyVersion.objects.get_or_create(company=company, version='1.0', defaults={'title':'Employee Monitoring Policy','body':'Trial monitoring policy.','is_active':True})
        return company
