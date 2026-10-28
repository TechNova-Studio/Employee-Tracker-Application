from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token
from .models import (ActivityLog, AgentVersion, Alert, AppWebsiteCategory, Company, Department,
                     Device, ERPConnector, ERPEvent, PolicyAcceptance,
                     PolicyVersion, Profile, WorkSession)


class HealthCheckTest(TestCase):
    def test_health(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')


class AgentVersionFlowTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Tenant A')
        self.other = Company.objects.create(name='Tenant B')
        self.super_admin = User.objects.create_user(username='version-super', password='secret')
        Profile.objects.create(user=self.super_admin, role='SUPER_ADMIN')
        self.company_admin = User.objects.create_user(username='version-admin', password='secret')
        Profile.objects.create(user=self.company_admin, company=self.company, role='COMPANY_ADMIN')
        self.employee = User.objects.create_user(username='version-employee', password='secret', email='version@example.com')
        Profile.objects.create(user=self.employee, company=self.company, role='EMPLOYEE')

    def create_rule(self, **overrides):
        data = {'platform': 'windows', 'latest_version': '2.0.0',
                'minimum_supported_version': '2.0.0', 'download_url': 'https://example.com/agent.exe',
                **overrides}
        return self.client.post('/api/agent-versions/', data=data, content_type='application/json')

    def test_super_admin_scope_validation_version_validation_and_effective_rule(self):
        self.client.force_login(self.super_admin)
        self.assertEqual(self.create_rule(company=999999).status_code, 400)
        self.assertEqual(self.create_rule(company=self.company.id, minimum_supported_version='3.0.0').status_code, 400)
        self.assertEqual(self.create_rule(company=self.company.id, latest_version='v2.0').status_code, 400)
        self.assertFalse(AgentVersion.objects.exists())
        global_rule = self.create_rule()
        self.assertEqual(global_rule.status_code, 201)
        company_rule = self.create_rule(company=self.company.id, minimum_supported_version='1.0.0')
        self.assertEqual(company_rule.status_code, 201)
        options = self.client.get('/api/agent-versions/company-options/').json()['companies']
        self.assertEqual({row['id'] for row in options}, {self.company.id, self.other.id})
        self.assertEqual([row['id'] for row in self.client.get('/api/agent-versions/?scope=global').json()['results']], [global_rule.json()['id']])
        self.assertEqual([row['id'] for row in self.client.get(f'/api/agent-versions/?company_id={self.company.id}').json()['results']], [company_rule.json()['id']])
        url = '/api/agent/version-check/?platform=windows&version=1.0.0'
        self.client.logout()
        self.assertTrue(self.client.get(url).json()['force_update_required'])
        self.assertEqual(self.client.get(url + f'&company_id={self.company.id}').status_code, 403)
        self.client.force_login(self.employee)
        self.assertFalse(self.client.get(url).json()['force_update_required'])
        self.assertEqual(self.client.get(url + f'&company_id={self.other.id}').status_code, 403)
        self.client.force_login(self.super_admin)
        self.assertFalse(self.client.get(url + f'&company_id={self.company.id}').json()['force_update_required'])
        self.assertEqual(self.client.get(url + '&company_id=999999').status_code, 400)

    def test_company_admin_cannot_reassign_rule_and_old_rule_does_not_reactivate(self):
        self.client.force_login(self.super_admin)
        global_id = self.create_rule().json()['id']
        other_id = self.create_rule(company=self.other.id).json()['id']
        self.client.force_login(self.company_admin)
        self.assertEqual(self.client.patch(f'/api/agent-versions/{global_id}/',
                         data={'is_active': False}, content_type='application/json').status_code, 403)
        self.assertEqual(self.client.get(f'/api/agent-versions/{other_id}/').status_code, 404)
        first = self.create_rule(company=self.other.id)
        self.assertEqual(first.status_code, 201)
        first_id = first.json()['id']
        self.assertEqual(first.json()['company'], self.company.id)
        moved = self.client.patch(f'/api/agent-versions/{first_id}/',
                                  data={'company': self.other.id}, content_type='application/json')
        self.assertEqual(moved.status_code, 400)
        self.assertEqual(AgentVersion.objects.get(pk=first_id).company, self.company)
        second = self.create_rule(latest_version='3.0.0', minimum_supported_version='3.0.0')
        self.assertEqual(second.status_code, 201)
        self.assertFalse(AgentVersion.objects.get(pk=first_id).is_active)
        self.assertEqual(self.client.get('/api/agent/version-check/?version=1.0.0').json()['minimum_supported_version'], '3.0.0')
        self.assertEqual(self.client.patch(f'/api/agent-versions/{second.json()["id"]}/',
                         data={'is_active': False}, content_type='application/json').status_code, 200)
        self.assertEqual(self.client.get('/api/agent/version-check/?version=1.0.0').json()['minimum_supported_version'], '2.0.0')

    def test_login_checks_company_rule_before_issuing_token(self):
        self.client.force_login(self.super_admin)
        self.create_rule()
        self.create_rule(company=self.company.id, latest_version='3.0.0', minimum_supported_version='3.0.0')
        self.client.logout()
        login = {'email': self.employee.email, 'password': 'secret'}
        blocked = self.client.post('/api/auth/login/', data={**login, 'platform': 'windows', 'app_version': '1.0.0'},
                                   content_type='application/json')
        self.assertEqual(blocked.status_code, 426)
        self.assertEqual(blocked.json()['blocked_reason'], 'OUTDATED_AGENT')
        self.assertEqual(blocked.json()['version']['minimum_supported_version'], '3.0.0')
        self.assertFalse(Token.objects.filter(user=self.employee).exists())
        permitted = self.client.post('/api/auth/login/', data={**login, 'platform': 'windows', 'app_version': '3.0.0'},
                                     content_type='application/json')
        self.assertEqual(permitted.status_code, 200)
        self.assertTrue(Token.objects.filter(user=self.employee).exists())
        headers = {'HTTP_AUTHORIZATION': f'Token {permitted.json()["token"]}'}
        old_device = self.client.post('/api/agent/device/register/', data={
            'device_id': 'desk-1', 'platform': 'windows', 'app_version': '1.0.0',
        }, content_type='application/json', **headers)
        self.assertEqual(old_device.status_code, 426)
        self.assertEqual(old_device.json()['version']['download_url'], 'https://example.com/agent.exe')
        updated_device = self.client.post('/api/agent/device/register/', data={
            'device_id': 'desk-1', 'platform': 'windows', 'app_version': '3.0.0',
        }, content_type='application/json', **headers)
        self.assertEqual(updated_device.status_code, 200)
        self.assertEqual(self.client.post('/api/auth/login/', data=login, content_type='application/json').status_code, 200)

    def test_desktop_login_requires_company_without_blocking_admin_web(self):
        credentials = {'username': self.super_admin.username, 'password': 'secret'}
        desktop = self.client.post('/api/auth/login/', data={**credentials, 'app_version': '1.0.0', 'platform': 'windows'},
                                   content_type='application/json')
        self.assertEqual(desktop.status_code, 403)
        self.assertEqual(desktop.json()['blocked_reason'], 'NO_COMPANY')
        self.assertFalse(Token.objects.filter(user=self.super_admin).exists())
        self.assertEqual(self.client.post('/api/auth/login/', data=credentials,
                                          content_type='application/json').status_code, 200)

    def test_desktop_login_trims_email_before_authentication(self):
        response = self.client.post('/api/auth/login/', data={
            'email': f'  {self.employee.email}  ', 'password': 'secret',
            'app_version': '1.0.0', 'platform': 'windows',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['id'], self.employee.id)


class PolicySessionActivityFlowTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='WorkPulse Tenant')
        self.other = Company.objects.create(name='Second Tenant')
        self.super_admin = User.objects.create_user(username='policy-super', password='secret')
        Profile.objects.create(user=self.super_admin, role='SUPER_ADMIN')
        self.admin = User.objects.create_user(username='policy-admin', password='secret')
        Profile.objects.create(user=self.admin, company=self.company, role='COMPANY_ADMIN')
        self.hr = User.objects.create_user(username='policy-hr', password='secret')
        Profile.objects.create(user=self.hr, company=self.company, role='HR_ADMIN')
        self.manager = User.objects.create_user(username='policy-manager', password='secret')
        Profile.objects.create(user=self.manager, company=self.company, role='MANAGER')
        self.employee = User.objects.create_user(username='policy-employee', password='secret', email='employee@tenant.example')
        Profile.objects.create(user=self.employee, company=self.company, role='EMPLOYEE', manager=self.manager)
        self.coworker = User.objects.create_user(username='policy-coworker', password='secret')
        Profile.objects.create(user=self.coworker, company=self.company, role='EMPLOYEE')
        self.outsider = User.objects.create_user(username='policy-outsider', password='secret')
        Profile.objects.create(user=self.outsider, company=self.other, role='EMPLOYEE')

    def post(self, path, data, **kwargs):
        return self.client.post(path, data=data, content_type='application/json', **kwargs)

    def publish(self, version, company=None):
        data = {'version': version, 'title': 'Employee Monitoring', 'body': f'Consent text {version}',
                'is_active': True}
        if company is not None:
            data['company'] = company.pk
        return self.post('/api/policies/', data)

    def test_policy_scope_immutable_text_stale_acceptance_and_idempotency(self):
        self.client.force_login(self.super_admin)
        self.assertEqual(self.publish('1.0').status_code, 400)
        self.assertEqual(self.publish('1.0', self.company).status_code, 201)
        self.assertEqual(self.publish('1.0', self.other).status_code, 201)
        first = PolicyVersion.objects.get(company=self.company)
        self.assertEqual({row['id'] for row in self.client.get('/api/policies/company-options/').json()['companies']},
                         {self.company.pk, self.other.pk})
        self.client.force_login(self.hr)
        self.assertEqual(self.publish('2.0', self.other).status_code, 403)
        self.assertEqual(self.publish('1.0').status_code, 400)
        self.assertEqual(self.client.patch(f'/api/policies/{first.pk}/', data={'body': 'Changed after publication'},
                                           content_type='application/json').status_code, 400)
        self.assertEqual(self.client.delete(f'/api/policies/{first.pk}/').status_code, 405)
        self.assertEqual(PolicyVersion.objects.get(pk=first.pk).body, 'Consent text 1.0')
        second = self.publish('2.0')
        self.assertEqual(second.status_code, 201)
        self.assertFalse(PolicyVersion.objects.get(pk=first.pk).is_active)
        self.client.force_login(self.employee)
        self.assertEqual(self.post('/api/policy/accept/', {'policy_id': first.pk}).status_code, 409)
        self.assertEqual(self.post('/api/policy/accept/', {}).status_code, 400)
        acceptance = self.post('/api/policy/accept/', {'policy_id': second.json()['id']})
        self.assertEqual(acceptance.status_code, 200)
        self.assertEqual(acceptance.json()['policy_version'], '2.0')
        self.assertEqual(self.post('/api/policy/accept/', {'policy_id': second.json()['id']}).status_code, 200)
        self.assertEqual(PolicyAcceptance.objects.filter(user=self.employee, status='ACCEPTED').count(), 1)
        self.assertTrue(self.client.get('/api/policy/current/').json()['accepted'])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/policy-acceptances/').json()['count'], 1)
        self.assertEqual(self.client.get('/api/policies/?company_id=' + str(self.other.pk)).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/api/policy-acceptances/').json()['count'], 1)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get('/api/policy-acceptances/').json()['count'], 0)

    def test_accept_session_heartbeat_activity_then_new_policy_requires_reacceptance(self):
        self.client.force_login(self.admin)
        first = self.publish('1.0').json()['id']
        AppWebsiteCategory.objects.create(company=self.company, pattern_type='DOMAIN',
                                          pattern='crm.example.com', category='PRODUCTIVE')
        sales = Department.objects.create(company=self.company, name='Sales')
        self.employee.profile.department = sales
        self.employee.profile.save(update_fields=['department'])
        AppWebsiteCategory.objects.create(company=self.company, pattern_type='DOMAIN',
                                          pattern='youtube.com', category='UNPRODUCTIVE')
        AppWebsiteCategory.objects.create(company=self.company, department=sales, pattern_type='DOMAIN',
                                          pattern='youtube.com', category='NEUTRAL')
        self.client.force_login(self.employee)
        device = self.post('/api/agent/device/register/', {'device_id': 'EMPLOYEE-DEVICE', 'platform': 'windows', 'app_version': '1.0.0'})
        self.assertEqual(device.status_code, 200)
        session_payload = {'device_id': 'EMPLOYEE-DEVICE', 'platform': 'windows', 'app_version': '1.0.0'}
        denied = self.post('/api/agent/session/start/', session_payload)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()['blocked_reason'], 'POLICY_NOT_ACCEPTED')
        self.assertEqual(self.post('/api/policy/accept/', {'device_id': 'EMPLOYEE-DEVICE', 'policy_id': first}).status_code, 200)
        started = self.post('/api/agent/session/start/', session_payload)
        self.assertEqual(started.status_code, 200)
        session_id = started.json()['id']
        heartbeat = {**session_payload, 'session_id': session_id, 'active_seconds': 45, 'idle_seconds': 0}
        self.assertEqual(self.post('/api/agent/heartbeat/', {**heartbeat, 'active_seconds': -5}).status_code, 400)
        self.assertEqual(self.post('/api/agent/heartbeat/', heartbeat).status_code, 200)
        self.assertEqual(WorkSession.objects.get(pk=session_id).active_seconds, 45)
        activity = {**session_payload, 'session_id': session_id,
                    'activities': [{'app_name': 'Chrome', 'domain': 'crm.example.com',
                                    'duration_seconds': 45, 'mouse_count': 3, 'keyboard_count': 2}]}
        self.assertEqual(self.post('/api/agent/activity/batch/', {**activity, 'activities': 'bad'}).status_code, 400)
        uploaded = self.post('/api/agent/activity/batch/', activity)
        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(uploaded.json()['created'], 1)
        self.assertEqual(uploaded.json()['items'][0]['productivity'], 'PRODUCTIVE')
        team_rule = self.post('/api/agent/activity/batch/', {**activity, 'activities': [
            {'app_name': 'Chrome', 'domain': 'youtube.com', 'duration_seconds': 10}]})
        self.assertEqual(team_rule.json()['items'][0]['productivity'], 'NEUTRAL')
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/api/sessions/').json()['count'], 1)
        self.assertEqual(self.client.get('/api/activities/?productivity=PRODUCTIVE').json()['count'], 1)
        self.assertEqual(self.client.get('/api/sessions/?from_date=2026-99-99').status_code, 400)
        self.assertEqual(self.client.get('/api/sessions/?company_id=' + str(self.other.pk)).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.post('/api/sessions/', {'user': self.employee.pk}).status_code, 403)
        self.assertEqual(self.post('/api/activities/', {'user': self.employee.pk}).status_code, 403)
        second = self.publish('2.0').json()['id']
        self.assertEqual(WorkSession.objects.get(pk=session_id).status, 'AUTO_STOPPED')
        self.client.force_login(self.employee)
        rejected = self.post('/api/agent/heartbeat/', heartbeat)
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(rejected.json()['blocked_reason'], 'POLICY_NOT_ACCEPTED')
        self.assertFalse(self.client.get('/api/policy/current/').json()['accepted'])
        self.assertEqual(self.post('/api/policy/accept/', {'policy_id': first}).status_code, 409)
        self.assertEqual(self.post('/api/policy/accept/', {'policy_id': second}).status_code, 200)
        next_session = self.post('/api/agent/session/start/', session_payload)
        self.assertEqual(next_session.status_code, 200)
        self.assertEqual(self.post('/api/agent/session/stop/', {'session_id': next_session.json()['id']}).status_code, 200)
        self.assertEqual(self.client.get('/api/sessions/?status=STOPPED').json()['count'], 1)
        self.assertEqual(self.client.get('/api/activities/?user_id=' + str(self.outsider.pk)).json()['count'], 0)

    def test_decline_stops_session_and_reactivation_requires_new_consent(self):
        self.client.force_login(self.admin)
        policy_id = self.publish('1.0').json()['id']
        self.client.force_login(self.employee)
        self.post('/api/agent/device/register/', {'device_id': 'DECLINE-DEVICE', 'app_version': '1.0.0'})
        self.post('/api/policy/accept/', {'policy_id': policy_id})
        session = self.post('/api/agent/session/start/', {'device_id': 'DECLINE-DEVICE', 'app_version': '1.0.0'}).json()['id']
        declined = self.post('/api/policy/decline/', {'policy_id': policy_id})
        self.assertEqual(declined.status_code, 200)
        self.assertEqual(WorkSession.objects.get(pk=session).status, 'AUTO_STOPPED')
        self.assertEqual(self.client.get('/api/policy/current/').json()['blocked_reason'], 'POLICY_DECLINED')
        self.assertEqual(self.post('/api/policy/accept/', {'policy_id': policy_id}).status_code, 403)
        self.assertEqual(self.post('/api/auth/login/', {'email': self.employee.email, 'password': 'secret'}).status_code, 403)
        self.client.force_login(self.hr)
        self.assertEqual(self.client.post(f'/api/users/{self.employee.pk}/reactivate-policy/').status_code, 200)
        self.client.force_login(self.employee)
        self.assertFalse(self.client.get('/api/policy/current/').json()['accepted'])
        self.assertEqual(self.post('/api/policy/accept/', {'policy_id': policy_id}).status_code, 200)
        self.assertEqual(PolicyAcceptance.objects.filter(user=self.employee, status='ACCEPTED').count(), 2)
        self.assertEqual(Alert.objects.filter(user=self.employee, alert_type='POLICY_DECLINED').count(), 1)

    def test_timeline_filters_pagination_and_role_scopes(self):
        sessions = []
        for user, company in ((self.employee, self.company), (self.coworker, self.company),
                              (self.outsider, self.other)):
            device = Device.objects.create(company=company, user=user, device_id=f'device-{user.pk}')
            sessions.append(WorkSession.objects.create(company=company, user=user, device=device,
                                                       status='STOPPED', stopped_at=timezone.now()))
        ActivityLog.objects.bulk_create([
            ActivityLog(company=self.company, user=self.employee, device=sessions[0].device,
                        session=sessions[0], app_name=f'App-{i}', duration_seconds=20)
            for i in range(51)
        ])
        ActivityLog.objects.create(company=self.company, user=self.coworker, device=sessions[1].device,
                                   session=sessions[1], app_name='Other app')
        ActivityLog.objects.create(company=self.other, user=self.outsider, device=sessions[2].device,
                                   session=sessions[2], app_name='Another tenant')
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/api/sessions/').json()['count'], 1)
        self.assertEqual(self.client.get('/api/activities/').json()['count'], 51)
        self.assertEqual([row['id'] for row in self.client.get('/api/sessions/filter-options/').json()['users']],
                         [self.employee.pk])
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get('/api/sessions/').json()['count'], 1)
        self.assertEqual(self.client.get('/api/activities/?user_id=' + str(self.coworker.pk)).json()['count'], 0)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/sessions/').json()['count'], 2)
        self.assertEqual(self.client.get('/api/activities/').json()['count'], 52)
        self.assertEqual(self.client.get('/api/sessions/?from_date=2026-09-26&to_date=2026-09-25').status_code, 400)
        self.assertEqual(self.client.get('/api/activities/?productivity=INVALID').status_code, 400)
        self.assertEqual(self.client.patch(f'/api/sessions/{sessions[0].pk}/',
                                           data={'status': 'RUNNING'}, content_type='application/json').status_code, 403)
        self.client.force_login(self.super_admin)
        self.assertEqual(self.client.get('/api/sessions/').json()['count'], 3)
        self.assertEqual(self.client.get('/api/activities/').json()['count'], 53)
        self.assertEqual(len(self.client.get('/api/activities/?page=2').json()['results']), 3)
        self.assertEqual(self.client.get('/api/sessions/filter-options/').json()['users'], [])
        scoped = self.client.get(f'/api/sessions/filter-options/?company_id={self.company.pk}').json()['users']
        self.assertEqual({row['id'] for row in scoped}, {self.employee.pk, self.coworker.pk})
        self.assertEqual(self.client.get('/api/sessions/?company_id=' + str(self.other.pk)).json()['count'], 1)


class ERPEmployeeLifecycleTest(TestCase):
    def test_policy_reactivation_does_not_change_mapped_employment_status(self):
        from .models import ERPEmployeeMapping
        company = Company.objects.create(name='Glutape')
        connector = ERPConnector.objects.create(company=company, api_token='policy-erp-token', allowed_event_types=['erp_user_inactive'])
        user = User.objects.create_user(username='employee-policy', email='employee@policy.test')
        Profile.objects.create(user=user, company=company, policy_status='POLICY_DECLINED')
        ERPEmployeeMapping.objects.create(connector=connector, user=user, external_id='21')
        response = self.client.post('/api/erp/ingest/', {'event_type': 'erp_user_inactive', 'external_id': '21', 'payload': {}},
            content_type='application/json', HTTP_X_WORKPULSE_TOKEN=connector.api_token)
        self.assertEqual(response.status_code, 200)
        admin = User.objects.create_user(username='hr-policy')
        Profile.objects.create(user=admin, company=company, role='HR_ADMIN')
        self.client.force_login(admin)
        response = self.client.post(f'/api/users/{user.pk}/reactivate-policy/')
        self.assertEqual(response.status_code, 200)
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.is_active_employee)
        self.assertEqual(user.profile.policy_status, 'NOT_ACCEPTED')


class CompanyAndERPConnectorTest(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_user(username='sa', password='secret')
        Profile.objects.create(user=self.super_admin, role='SUPER_ADMIN')
        self.company_admin = User.objects.create_user(username='companyadmin', password='secret')
        self.existing_company = Company.objects.create(name='Existing Company')
        Profile.objects.create(user=self.company_admin, company=self.existing_company, role='COMPANY_ADMIN')

    def test_super_admin_can_create_company_then_connector_and_employee(self):
        self.client.force_login(self.super_admin)
        response = self.client.post('/api/companies/', data={
            'name': 'New SaaS Company', 'status': 'ACTIVE', 'allowed_users': 20,
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        company_id = response.json()['id']
        self.assertTrue(Company.objects.filter(pk=company_id).exists())
        connector_response = self.client.post('/api/erp-connectors/', data={
            'name': 'New Company CRM', 'company': company_id,
            'allowed_event_types': ['erp_user_created', 'erp_user_updated', 'erp_user_active', 'erp_user_inactive'],
        }, content_type='application/json')
        self.assertEqual(connector_response.status_code, 201)
        connector = ERPConnector.objects.get(pk=connector_response.json()['id'])
        self.assertEqual(connector.company_id, company_id)
        self.client.logout()
        employee_response = self.client.post('/api/erp/ingest/', data={
            'event_type': 'erp_user_created', 'external_id': 'source-1',
            'payload': {'email': 'new@saas.example'},
        }, content_type='application/json', HTTP_X_WORKPULSE_TOKEN=connector.api_token)
        self.assertEqual(employee_response.status_code, 200)
        self.assertEqual(User.objects.get(email='new@saas.example').profile.company_id, company_id)

    def test_company_admin_cannot_create_company_but_can_create_own_connector(self):
        self.client.force_login(self.company_admin)
        denied = self.client.post('/api/companies/', data={'name': 'Forbidden'}, content_type='application/json')
        self.assertEqual(denied.status_code, 403)
        response = self.client.post('/api/erp-connectors/', data={
            'name': 'Existing CRM', 'allowed_event_types': ['erp_user_created'],
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ERPConnector.objects.get(pk=response.json()['id']).company_id, self.existing_company.pk)

    def test_super_admin_connector_requires_existing_company(self):
        self.client.force_login(self.super_admin)
        response = self.client.post('/api/erp-connectors/', data={
            'name': 'No company', 'company': 999999,
        }, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ERPConnector.objects.exists())


class UserFormOptionsTest(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name='Glutape')
        self.company_b = Company.objects.create(name='Other Company')
        self.dept_a = Department.objects.create(company=self.company_a, name='IT')
        self.dept_b = Department.objects.create(company=self.company_b, name='Finance')
        self.admin_a = User.objects.create_user(username='admin-a', password='secret')
        Profile.objects.create(user=self.admin_a, company=self.company_a, role='COMPANY_ADMIN')
        self.admin_b = User.objects.create_user(username='admin-b', password='secret')
        Profile.objects.create(user=self.admin_b, company=self.company_b, role='COMPANY_ADMIN')
        self.manager_a = User.objects.create_user(username='manager-a', password='secret')
        Profile.objects.create(user=self.manager_a, company=self.company_a, role='MANAGER')
        self.super_admin = User.objects.create_user(username='super-a', password='secret')
        Profile.objects.create(user=self.super_admin, role='SUPER_ADMIN')

    def test_company_admin_sees_only_own_form_options(self):
        self.client.force_login(self.admin_a)
        response = self.client.get('/api/users/form-options/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['companies'], [{'id': self.company_a.id, 'name': self.company_a.name, 'employee_id_prefix': ''}])
        self.assertEqual([row['id'] for row in data['departments']], [self.dept_a.id])
        self.assertIn(self.manager_a.pk, [row['id'] for row in data['managers']])
        self.assertNotIn(self.admin_b.pk, [row['id'] for row in data['managers']])
        self.assertEqual(self.client.get(f'/api/users/form-options/?company_id={self.company_b.pk}').status_code, 403)

    def test_super_admin_can_change_company_options(self):
        self.client.force_login(self.super_admin)
        response = self.client.get('/api/users/form-options/')
        self.assertEqual(len(response.json()['companies']), 2)
        self.assertEqual(response.json()['departments'], [])
        selected = self.client.get(f'/api/users/form-options/?company_id={self.company_b.pk}').json()
        self.assertEqual([row['id'] for row in selected['departments']], [self.dept_b.pk])
        self.assertEqual([row['id'] for row in selected['managers']], [self.admin_b.pk])

    def test_employee_create_rejects_department_or_manager_from_other_company(self):
        self.client.force_login(self.super_admin)
        payload = {'email': 'new@example.com', 'username': 'new@example.com',
                   'password': 'StrongPass123!', 'company': self.company_a.pk, 'role': 'EMPLOYEE'}
        wrong_department = self.client.post('/api/users/', data={**payload, 'department': self.dept_b.pk},
                                            content_type='application/json')
        self.assertEqual(wrong_department.status_code, 400)
        wrong_manager = self.client.post('/api/users/', data={**payload, 'manager': self.admin_b.pk},
                                         content_type='application/json')
        self.assertEqual(wrong_manager.status_code, 400)
        valid = self.client.post('/api/users/', data={**payload, 'department': self.dept_a.pk,
                                                    'manager': self.manager_a.pk}, content_type='application/json')
        self.assertEqual(valid.status_code, 201)
        employee = User.objects.get(email='new@example.com')
        self.assertEqual(employee.profile.company, self.company_a)
        self.assertEqual(employee.profile.department, self.dept_a)
        self.assertEqual(employee.profile.manager, self.manager_a)


class SalesScopeTest(TestCase):
    def test_sales_admin_has_trial_scope_without_employee_activity_access(self):
        company = Company.objects.create(name='Sales Tenant')
        sales = User.objects.create_user(username='sales', password='secret')
        Profile.objects.create(user=sales, company=company, role='SALES_ADMIN', can_generate_trials=True)
        self.client.force_login(sales)
        self.assertEqual(self.client.get('/api/reports/dashboard-summary/').status_code, 200)
        self.assertEqual(self.client.get('/api/demo-trial-codes/').status_code, 200)
        self.assertEqual(self.client.get('/api/trial/dashboard/').status_code, 200)
        for url in ('/api/users/', '/api/devices/', '/api/alerts/', '/api/sessions/',
                    '/api/activities/', '/api/reports/attendance/', '/api/reports/activity/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)


class DepartmentFlowTest(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name='Glutape')
        self.company_b = Company.objects.create(name='Other')
        self.super_admin = User.objects.create_user(username='super-dept', password='secret')
        Profile.objects.create(user=self.super_admin, role='SUPER_ADMIN')
        self.company_admin = User.objects.create_user(username='company-dept', password='secret')
        Profile.objects.create(user=self.company_admin, company=self.company_a, role='COMPANY_ADMIN')
        self.hr = User.objects.create_user(username='hr-dept', password='secret')
        Profile.objects.create(user=self.hr, company=self.company_a, role='HR_ADMIN')
        self.employee = User.objects.create_user(username='employee-dept', password='secret')
        Profile.objects.create(user=self.employee, company=self.company_a, role='EMPLOYEE')

    def post_department(self, data):
        return self.client.post('/api/departments/', data=data, content_type='application/json')

    def test_super_admin_company_selection_and_department_lifecycle(self):
        self.client.force_login(self.super_admin)
        self.assertEqual(self.post_department({'name': 'IT'}).status_code, 400)
        self.assertEqual(self.post_department({'name': 'IT', 'company': 999999}).status_code, 400)
        options = self.client.get('/api/departments/company-options/').json()
        self.assertEqual(len(options['companies']), 2)
        created = self.post_department({'name': ' IT ', 'company': self.company_a.pk})
        self.assertEqual(created.status_code, 201)
        department = Department.objects.get(pk=created.json()['id'])
        self.assertEqual((department.company, department.name), (self.company_a, 'IT'))
        self.assertEqual(self.post_department({'name': 'it', 'company': self.company_a.pk}).status_code, 400)
        self.assertEqual(self.post_department({'name': 'IT', 'company': self.company_b.pk}).status_code, 201)
        listing = self.client.get(f'/api/departments/?company_id={self.company_a.pk}').json()
        self.assertEqual(listing['count'], 1)
        renamed = self.client.patch(f'/api/departments/{department.pk}/',
                                    data={'name': 'Operations'}, content_type='application/json')
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(self.client.patch(f'/api/departments/{department.pk}/',
                                           data={'company': self.company_b.pk}, content_type='application/json').status_code, 400)
        inactive = self.client.patch(f'/api/departments/{department.pk}/',
                                     data={'is_active': False}, content_type='application/json')
        self.assertEqual(inactive.status_code, 200)
        self.assertEqual(self.client.delete(f'/api/departments/{department.pk}/').status_code, 405)
        department.refresh_from_db()
        self.assertEqual(department.name, 'Operations')
        self.assertFalse(department.is_active)

    def test_company_admin_and_hr_are_scoped_and_inactive_not_in_user_options(self):
        self.client.force_login(self.company_admin)
        options = self.client.get('/api/departments/company-options/').json()
        self.assertEqual(options['companies'], [{'id': self.company_a.pk, 'name': 'Glutape'}])
        self.assertEqual(self.post_department({'name': 'Finance', 'company': self.company_b.pk}).status_code, 403)
        created = self.post_department({'name': 'Finance'})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()['company'], self.company_a.pk)
        self.assertEqual(self.client.get(f'/api/departments/?company_id={self.company_b.pk}').status_code, 403)
        self.client.force_login(self.hr)
        self.assertEqual(self.post_department({'name': 'HR'}).status_code, 201)
        self.assertEqual(self.client.patch(f'/api/departments/{created.json()["id"]}/',
                                           data={'is_active': False}, content_type='application/json').status_code, 200)
        user_options = self.client.get('/api/users/form-options/').json()
        self.assertNotIn('Finance', [row['name'] for row in user_options['departments']])
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get('/api/departments/company-options/').status_code, 403)


# Regression coverage for the Screenshot / Summary / Trial UI flows.
from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from .models import (CompanyPlan, DailyAISummary, DemoTrialCode, ManagerReview,
                     Screenshot, ScreenshotAccessLog, Subscription, TrialConversionLog, TrialSignupLog)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class WorkflowFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name='Operations company')
        cls.other = Company.objects.create(name='Other company')
        for attr, role, company in [('super_admin', 'SUPER_ADMIN', None), ('admin', 'COMPANY_ADMIN', cls.company),
                                   ('manager', 'MANAGER', cls.company), ('employee', 'EMPLOYEE', cls.company),
                                   ('coworker', 'EMPLOYEE', cls.company), ('outsider', 'EMPLOYEE', cls.other),
                                   ('sales', 'SALES_ADMIN', cls.company), ('other_sales', 'SALES_ADMIN', cls.other)]:
            user = User.objects.create_user(username=attr, email=f'{attr}@flow.example', password='FlowStrong#987')
            Profile.objects.create(user=user, role=role, company=company, can_generate_trials=role in ['SALES_ADMIN', 'COMPANY_ADMIN'],
                                   manager=cls.manager if attr == 'employee' else None)
            setattr(cls, attr, user)

    def post(self, path, data):
        return self.client.post(path, data=data, content_type='application/json')

    def session(self, user=None, company=None):
        user, company = user or self.employee, company or self.company
        device, _ = Device.objects.get_or_create(company=company, user=user, device_id=f'flow-{user.pk}', defaults={'hostname': 'Desktop', 'app_version': '1.0.0'})
        return WorkSession.objects.create(company=company, user=user, device=device)


class ScreenshotFlowTest(WorkflowFixture):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = override_settings(MEDIA_ROOT=directory.name, SCREENSHOT_STORAGE_MODE='local')
        settings.enable(); self.addCleanup(settings.disable)
        self.work = self.session()
        policy = PolicyVersion.objects.create(company=self.company, version='1', title='Policy', body='Monitoring', is_active=True)
        self.employee.profile.policy_status = 'ACCEPTED'; self.employee.profile.save()
        PolicyAcceptance.objects.create(company=self.company, user=self.employee, policy=policy, status='ACCEPTED')
        self.client.force_login(self.employee)

    def upload(self, file=None, **extra):
        data = {'session_id': self.work.pk, 'device_id': self.work.device.device_id, 'app_version': '1.0.0', **extra}
        if file is not None:
            data['file'] = file
        return self.client.post('/api/agent/screenshots/upload/', data=data)

    def image_file(self, image_format='PNG'):
        content = BytesIO(); Image.new('RGB', (12, 12), 'blue').save(content, format=image_format)
        return SimpleUploadedFile('desktop.png', content.getvalue(), content_type='image/png')

    def test_validated_upload_protected_preview_download_and_soft_delete(self):
        self.assertEqual(self.upload().status_code, 400)
        self.assertEqual(self.upload(SimpleUploadedFile('bad.png', b'not an image')).status_code, 400)
        self.assertEqual(self.upload(self.image_file(), checksum='wrong').status_code, 400)
        self.assertFalse(Screenshot.objects.exists())
        uploaded = self.upload(self.image_file('JPEG'))
        self.assertEqual(uploaded.status_code, 200, uploaded.content)
        row = uploaded.json(); shot_id = row['id']
        self.assertEqual(row['company_name'], self.company.name)
        self.assertNotIn('file', row); self.assertNotIn('object_key', row)
        self.assertEqual(len(row['checksum']), 64)
        for action in ('view', 'download'):
            response = self.client.get(f'/api/screenshots/{shot_id}/{action}/')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'image/jpeg')
            self.assertEqual(response['Cache-Control'], 'private, no-store')
            self.assertTrue(b''.join(response.streaming_content))
        self.assertEqual(ScreenshotAccessLog.objects.filter(screenshot_id=shot_id).count(), 2)
        self.assertEqual(self.post(f'/api/screenshots/{shot_id}/soft-delete/', {}).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.post(f'/api/screenshots/{shot_id}/soft-delete/', {}).status_code, 200)
        self.assertTrue(Screenshot.objects.get(pk=shot_id).deleted_at)
        self.assertEqual(ScreenshotAccessLog.objects.filter(screenshot_id=shot_id, action='DELETE').count(), 1)
        self.assertEqual(self.client.get(f'/api/screenshots/{shot_id}/view/').status_code, 404)
        self.assertEqual(self.client.get('/api/screenshots/').json()['count'], 0)

    def test_scope_filters_pagination_and_no_metadata_mutation(self):
        own = self.upload(self.image_file()).json()['id']
        other_session = self.session(self.outsider, self.other)
        external = Screenshot.objects.create(company=self.other, user=self.outsider, session=other_session)
        Screenshot.objects.bulk_create([Screenshot(company=self.company, user=self.employee, session=self.work) for _ in range(50)])
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/api/screenshots/').json()['count'], 51)
        self.assertEqual(len(self.client.get('/api/screenshots/?page=2').json()['results']), 1)
        self.assertEqual(self.client.get(f'/api/screenshots/{external.pk}/view/').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/screenshots/{external.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/screenshots/?company_id={self.other.pk}').status_code, 403)
        self.assertEqual(self.client.get('/api/screenshots/?from_date=bad').status_code, 400)
        options = self.client.get('/api/screenshots/filter-options/').json()
        self.assertEqual([u['id'] for u in options['users']], [self.employee.pk])
        self.assertEqual(self.post('/api/screenshots/', {}).status_code, 405)
        self.assertEqual(self.client.patch(f'/api/screenshots/{own}/', data={'status': 'DELETED'}, content_type='application/json').status_code, 405)
        self.client.force_login(self.coworker)
        self.assertEqual(self.client.get(f'/api/screenshots/{own}/view/').status_code, 404)
        self.client.force_login(self.sales)
        self.assertEqual(self.client.get('/api/screenshots/').status_code, 403)


class SummaryFlowTest(WorkflowFixture):
    def setUp(self):
        self.work = self.session()
        self.work.active_seconds = 3600; self.work.idle_seconds = 60; self.work.save()
        ActivityLog.objects.create(company=self.company, user=self.employee, device=self.work.device, session=self.work,
                                   app_name='Editor', duration_seconds=600, productivity='PRODUCTIVE')
        self.date = str(timezone.localdate())
        self.client.force_login(self.manager)

    def generate(self, **extra):
        return self.post('/api/ai-summaries/generate/', {'date': self.date, **extra})

    def test_generate_first_review_repeat_generation_and_changed_data(self):
        self.assertEqual(self.generate().json()['created'], 1)
        summary = DailyAISummary.objects.get(user=self.employee)
        self.assertEqual(summary.active_seconds, 3600)
        response = self.post('/api/manager-reviews/', {'ai_summary': summary.pk, 'status': 'REVIEWED', 'remarks': 'Checked time', 'reviewed_by': self.super_admin.pk})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(ManagerReview.objects.get().reviewed_by, self.manager)
        self.assertEqual(self.generate().json()['unchanged'], 1)
        summary.refresh_from_db(); self.assertEqual(summary.manager_review_status, 'REVIEWED')
        self.work.active_seconds += 60; self.work.save()
        self.assertEqual(self.generate().json()['updated'], 1)
        summary.refresh_from_db(); self.assertEqual(summary.manager_review_status, 'PENDING')
        self.assertEqual(ManagerReview.objects.count(), 1)
        self.assertEqual(Alert.objects.filter(alert_type='AI_RISK_FLAG').count(), 1)
        self.assertEqual(self.client.get(f'/api/manager-reviews/?ai_summary={summary.pk}').json()['count'], 1)
        self.assertEqual(self.client.delete(f'/api/manager-reviews/{response.json()["id"]}/').status_code, 405)
        self.assertEqual(self.post('/api/manager-reviews/', {'ai_summary': summary.pk, 'status': 'INVALID'}).status_code, 400)
        self.assertEqual(self.post('/api/manager-reviews/', {'ai_summary': summary.pk, 'status': 'EXPLANATION_REQUESTED'}).status_code, 400)

    def test_overnight_heartbeat_totals_and_stale_review(self):
        from .models import Heartbeat
        from .ai_summaries import generate_summaries
        from datetime import datetime, time
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        self.work.started_at = timezone.make_aware(datetime.combine(yesterday, time(23, 50)))
        self.work.active_seconds = 9999; self.work.save()
        for day, active in [(yesterday, 600), (today, 120)]:
            Heartbeat.objects.create(company=self.company, user=self.employee, session=self.work, device=self.work.device,
                captured_at=timezone.make_aware(datetime.combine(day, time(23, 55) if day == yesterday else time(0, 5))), active_seconds=active)
        generate_summaries(User.objects.filter(pk=self.employee.pk), yesterday)
        generate_summaries(User.objects.filter(pk=self.employee.pk), today)
        self.assertEqual(DailyAISummary.objects.get(user=self.employee, date=yesterday).active_seconds, 600)
        current = DailyAISummary.objects.get(user=self.employee, date=today)
        self.assertEqual(current.active_seconds, 120)
        response = self.post('/api/manager-reviews/', {'ai_summary': current.pk, 'status': 'REVIEWED',
                             'summary_updated_at': (current.updated_at - timedelta(seconds=1)).isoformat()})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ManagerReview.objects.exists())

    def test_generation_review_and_read_scopes(self):
        other = DailyAISummary.objects.create(company=self.other, user=self.outsider, date=self.date)
        self.assertEqual(self.generate(user_id=self.coworker.pk).status_code, 403)
        self.assertEqual(self.generate(company_id=self.other.pk).status_code, 403)
        self.assertEqual(self.generate(date='bad').status_code, 400)
        self.assertEqual(self.generate(date=str(timezone.localdate() + timedelta(days=1))).status_code, 400)
        self.assertEqual(self.post('/api/manager-reviews/', {'ai_summary': other.pk, 'status': 'CONFIRMED'}).status_code, 403)
        self.generate()
        self.assertEqual(self.client.get('/api/ai-summaries/').json()['count'], 1)
        self.assertEqual(self.client.get('/api/ai-summaries/?review_status=INVALID').status_code, 400)
        self.assertEqual(self.client.get('/api/ai-summaries/?from_date=2000-01-01&to_date=2000-01-02').json()['count'], 0)
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get('/api/ai-summaries/').json()['count'], 1)
        self.assertEqual(self.generate().status_code, 403)
        self.assertEqual(self.post('/api/manager-reviews/', {'ai_summary': other.pk, 'status': 'REVIEWED'}).status_code, 403)
        self.client.force_login(self.super_admin)
        self.assertEqual(self.generate().status_code, 400)
        self.assertEqual(self.generate(company_id=self.company.pk).status_code, 200)
        self.client.force_login(self.sales)
        self.assertEqual(self.client.get('/api/ai-summaries/').status_code, 403)


class TrialFlowTest(WorkflowFixture):
    def setUp(self):
        self.trial = CompanyPlan.objects.create(code='TRIAL', name='Trial', max_users=10, max_devices=10)
        self.paid = CompanyPlan.objects.create(code='BASIC', name='Basic', max_users=25, max_devices=30, price_per_user=100)
        self.internal = CompanyPlan.objects.create(code='INTERNAL', name='Internal', max_users=500, max_devices=500)
        self.client.force_login(self.sales)

    def code(self, **extra):
        result = self.post('/api/demo-trial-codes/', {'customer_company_name': 'Customer', 'trial_duration_days': 7,
            'allowed_users': 5, 'allowed_devices': 5, 'expiry_date': (timezone.now() + timedelta(days=1)).isoformat(), **extra})
        self.assertEqual(result.status_code, 201, result.content)
        return result.json()

    def signup(self, code, email='new.customer@example.com', **extra):
        return self.post('/api/trial/signup/', {'code': code, 'company_name': 'Trial customer', 'admin_name': 'Customer Admin',
            'admin_email': email, 'password': 'TrialStrong#987', **extra})

    def test_optional_prefix_generates_trial_administrator_id(self):
        row = self.code()
        result = self.signup(row['code'], employee_id_prefix='glutape')
        self.assertEqual(result.status_code, 201, result.content)
        company = Company.objects.get(pk=result.json()['company']['id'])
        self.assertEqual(company.employee_id_prefix, 'GLUTAPE')
        self.assertEqual(company.profiles.get().employee_code, 'GLUTAPE0001')

    def test_code_validation_owner_and_immutable_audit_fields(self):
        for data in ({'trial_duration_days': 0}, {'allowed_users': 0}, {'allowed_devices': 999},
                     {'expiry_date': 'bad'}, {'expiry_date': (timezone.now() - timedelta(days=1)).isoformat()},
                     {'plan': self.paid.pk}, {'sales_owner': self.other_sales.pk}):
            response = self.post('/api/demo-trial-codes/', {'customer_company_name': 'Test', 'expiry_date': (timezone.now() + timedelta(days=1)).isoformat(), **data})
            self.assertEqual(response.status_code, 400, response.content)
        row = self.code(status='CONVERTED', generated_by=self.super_admin.pk)
        self.assertEqual(row['status'], 'ACTIVE'); self.assertEqual(row['generated_by'], self.sales.pk)
        self.assertEqual(self.client.patch(f'/api/demo-trial-codes/{row["id"]}/', data={'generated_by': self.other_sales.pk}, content_type='application/json').status_code, 405)
        self.assertEqual(self.client.delete(f'/api/demo-trial-codes/{row["id"]}/').status_code, 405)
        self.assertEqual(self.client.get('/api/demo-trial-codes/form-options/').json()['owners'][0]['id'], self.sales.pk)
        self.client.force_login(self.other_sales)
        self.assertEqual(self.client.get('/api/demo-trial-codes/').json()['count'], 0)
        self.assertEqual(self.post(f'/api/demo-trial-codes/{row["id"]}/cancel/', {}).status_code, 404)

    def test_signup_validation_single_use_and_no_orphan_company(self):
        row = self.code(remarks='Private sales note', email='private.contact@example.com')
        valid = self.post('/api/trial/validate-code/', {'code': row['code'].lower()})
        self.assertEqual(valid.status_code, 200)
        self.assertNotIn('remarks', valid.json()['code']); self.assertNotIn('email', valid.json()['code'])
        before = Company.objects.count()
        self.assertEqual(self.signup(row['code'], email='bad').status_code, 400)
        self.assertEqual(self.signup(row['code'], password='1234').status_code, 400)
        self.assertEqual(self.signup(row['code'], email=self.sales.email).status_code, 400)
        self.assertEqual(Company.objects.count(), before)
        result = self.signup(row['code'])
        self.assertEqual(result.status_code, 201, result.content)
        company = Company.objects.get(pk=result.json()['company']['id'])
        self.assertEqual(company.subscription.status, 'TRIAL')
        self.assertEqual(company.profiles.get().role, 'COMPANY_ADMIN')
        self.assertEqual(company.profiles.get().employee_code, '')
        self.assertTrue(PolicyVersion.objects.filter(company=company, is_active=True).exists())
        self.assertEqual(TrialSignupLog.objects.filter(company=company, status='SUCCESS').count(), 1)
        self.assertEqual(self.signup(row['code'], email='second@example.com').status_code, 400)
        self.assertEqual(Company.objects.count(), before + 1)
        second_code = self.code()
        with patch('core.views.PolicyVersion.objects.create', side_effect=RuntimeError('Simulated write failure')):
            with self.assertRaises(RuntimeError):
                self.signup(second_code['code'], email='rollback@example.com')
        self.assertFalse(User.objects.filter(email='rollback@example.com').exists())
        self.assertEqual(Company.objects.count(), before + 1)
        self.assertEqual(DemoTrialCode.objects.get(pk=second_code['id']).status, 'ACTIVE')

    def test_reusable_codes_keep_all_companies_scoped_and_count_conversions(self):
        row = self.code(single_use=False)
        first = self.signup(row['code']).json()['company']['id']
        second = self.signup(row['code'], email='second@example.com').json()['company']['id']
        self.assertEqual(DemoTrialCode.objects.get(pk=row['id']).status, 'ACTIVE')
        companies = self.client.get('/api/trial/companies/').json()
        self.assertEqual({r['id'] for r in companies['results']}, {first, second})
        convert = self.post('/api/trial/convert/', {'company_id': first, 'plan_code': 'BASIC', 'billing_cycle': 'MONTHLY'})
        self.assertEqual(convert.status_code, 200, convert.content)
        metrics = self.client.get('/api/trial/dashboard/').json()
        self.assertEqual(metrics['codes_used'], 1); self.assertEqual(metrics['active_trials'], 1)
        self.assertEqual(metrics['converted_trials'], 1); self.assertEqual(metrics['conversion_percent'], 50)
        self.assertEqual(self.post(f'/api/demo-trial-codes/{row["id"]}/cancel/', {}).status_code, 200)
        self.assertEqual(Company.objects.get(pk=second).status, 'TRIAL_ACTIVE')
        self.assertEqual(self.signup(row['code'], email='third@example.com').status_code, 400)
        self.client.force_login(self.other_sales)
        self.assertEqual(self.client.get('/api/trial/companies/').json()['count'], 0)
        self.assertEqual(self.post('/api/trial/extend/', {'company_id': second, 'days': 5}).status_code, 404)

    def test_expired_trial_extend_convert_and_paid_session_start(self):
        row = self.code()
        company_id = self.signup(row['code']).json()['company']['id']
        company = Company.objects.get(pk=company_id)
        company.trial_end_date = timezone.now() - timedelta(days=10); company.save()
        self.assertEqual(self.client.get('/api/trial/dashboard/').json()['expired_trials'], 1)
        company.refresh_from_db(); self.assertEqual(company.status, 'TRIAL_EXPIRED')
        self.assertEqual(company.subscription.status, 'EXPIRED')
        for days in (-1, 0, 91, 'bad', 1.5):
            self.assertEqual(self.post('/api/trial/extend/', {'company_id': company.pk, 'days': days}).status_code, 400)
        extended = self.post('/api/trial/extend/', {'company_id': company.pk, 'days': 5})
        self.assertEqual(extended.status_code, 200)
        company.refresh_from_db(); self.assertGreater(company.trial_end_date, timezone.now() + timedelta(days=4))
        for code, cycle, expected in [('TRIAL', 'MONTHLY', 400), ('BAD', 'MONTHLY', 400), ('BASIC', 'NONE', 400), ('INTERNAL', 'NONE', 403)]:
            self.assertEqual(self.post('/api/trial/convert/', {'company_id': company.pk, 'plan_code': code, 'billing_cycle': cycle}).status_code, expected)
        company.trial_end_date = timezone.now() - timedelta(days=1); company.status = 'TRIAL_EXPIRED'; company.save()
        self.assertEqual(self.post('/api/trial/convert/', {'company_id': company.pk, 'plan_code': 'BASIC', 'billing_cycle': 'ANNUAL'}).status_code, 200)
        company.refresh_from_db(); self.assertFalse(company.is_trial_expired())
        self.assertEqual(company.allowed_users, 25); self.assertEqual(company.allowed_devices, 30)
        self.assertEqual(company.subscription.status, 'ACTIVE')
        self.assertEqual(self.post('/api/trial/convert/', {'company_id': company.pk, 'plan_code': 'BASIC', 'billing_cycle': 'MONTHLY'}).status_code, 400)
        self.assertEqual(TrialConversionLog.objects.filter(company=company).count(), 1)
        user = company.profiles.get().user
        self.client.force_login(user)
        policy = PolicyVersion.objects.get(company=company)
        self.post('/api/policy/accept/', {'policy_id': policy.pk})
        self.post('/api/agent/device/register/', {'device_id': 'paid-desktop', 'app_version': '1.0.0'})
        started = self.post('/api/agent/session/start/', {'device_id': 'paid-desktop', 'app_version': '1.0.0'})
        self.assertEqual(started.status_code, 200, started.content)

    def test_trial_cancel_stops_tracking_and_super_scope_excludes_unrelated_companies(self):
        row = self.code()
        company = Company.objects.get(pk=self.signup(row['code']).json()['company']['id'])
        user = company.profiles.get().user
        session = self.session(user, company)
        self.assertEqual(self.post('/api/trial/cancel/', {'company_id': 'bad'}).status_code, 400)
        self.assertEqual(self.post('/api/trial/cancel/', {'company_id': company.pk}).status_code, 200)
        session.refresh_from_db(); self.assertEqual(session.status, 'AUTO_STOPPED')
        self.assertEqual(Subscription.objects.get(company=company).status, 'CANCELLED')
        self.assertEqual(self.post('/api/trial/extend/', {'company_id': company.pk, 'days': 5}).status_code, 400)
        self.client.force_login(user)
        blocked = self.post('/api/agent/session/start/', {'device_id': session.device.device_id, 'app_version': '1.0.0'})
        self.assertEqual(blocked.status_code, 403); self.assertEqual(blocked.json()['blocked_reason'], 'SUSPENDED')
        blocked = self.post('/api/agent/heartbeat/', {'session_id': session.pk, 'device_id': session.device.device_id, 'app_version': '1.0.0'})
        self.assertEqual(blocked.status_code, 403); self.assertEqual(blocked.json()['blocked_reason'], 'SUSPENDED')
        self.client.force_login(self.super_admin)
        self.assertEqual(self.client.get('/api/trial/companies/').json()['count'], 1)
        self.assertEqual(self.post('/api/trial/cancel/', {'company_id': self.company.pk}).status_code, 404)


class BillingWorkflowTest(WorkflowFixture):
    def setUp(self):
        from .models import BillingInvoice
        self.plan = CompanyPlan.objects.create(code='BASIC', name='Basic', price_per_user='199.50', max_users=30, max_devices=30)
        self.internal = CompanyPlan.objects.create(code='INTERNAL', name='Internal', max_users=500, max_devices=500)
        self.trial_plan = CompanyPlan.objects.create(code='TRIAL', name='Trial', max_users=10, max_devices=10)
        self.client.force_login(self.super_admin)

    def configure(self, company=None, plan=None, cycle='MONTHLY'):
        return self.post('/api/subscriptions/configure/', {'company_id': (company or self.company).pk,
                         'plan_id': (plan or self.plan).pk, 'billing_cycle': cycle})

    def draft(self, sub_id, start='2026-09-01', **extra):
        return self.post('/api/billing-invoices/', {'subscription_id': sub_id, 'billing_period_start': start, **extra})

    def test_subscription_configuration_and_read_only_tenant_access(self):
        configured = self.configure()
        self.assertEqual(configured.status_code, 200, configured.content)
        self.company.refresh_from_db()
        self.assertEqual(self.company.plan, self.plan)
        self.assertEqual(self.company.allowed_users, 30)
        self.assertEqual(configured.json()['live_user_count'], 5)
        self.assertEqual(configured.json()['estimated_amount'], '997.50')
        self.configure(self.other)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/subscriptions/').json()['count'], 1)
        self.assertEqual(self.client.get('/api/subscriptions/overview/').json()['subscriptions'], 1)
        self.assertFalse(self.client.get('/api/subscriptions/form-options/').json()['can_manage'])
        self.assertEqual(self.client.get(f'/api/subscriptions/?company_id={self.other.pk}').status_code, 403)
        self.assertEqual(self.configure().status_code, 403)
        self.assertEqual(self.draft(configured.json()['id']).status_code, 403)
        for user in (self.employee, self.manager, self.sales):
            self.client.force_login(user)
            for endpoint in ('subscriptions', 'billing-invoices'):
                self.assertEqual(self.client.get(f'/api/{endpoint}/').status_code, 403)
        self.client.force_login(self.super_admin)
        self.assertEqual(self.client.patch(f'/api/subscriptions/{configured.json()["id"]}/',
                         data={'company': self.other.pk}, content_type='application/json').status_code, 405)

    def test_exact_amount_snapshot_overlap_and_manual_payment_transitions(self):
        from .models import AuditLog, BillingInvoice
        sub = self.configure().json()
        self.employee.is_active = False; self.employee.save()
        result = self.draft(sub['id'], amount='1.00', status='PAID', company=self.other.pk, currency='USD')
        self.assertEqual(result.status_code, 201, result.content)
        row = result.json(); invoice_id = row['id']
        self.assertEqual(row['quantity'], 4)
        self.assertEqual(row['unit_price'], '199.50'); self.assertEqual(row['amount'], '798.00')
        self.assertEqual(row['currency'], 'INR'); self.assertEqual(row['status'], 'DRAFT')
        self.assertEqual(row['company'], self.company.pk); self.assertEqual(row['billing_period_end'], '2026-09-30')
        self.assertTrue(row['invoice_number'].startswith('WP-MANUAL-'))
        self.assertEqual(self.draft(sub['id']).status_code, 409)
        self.assertEqual(self.draft(sub['id'], start='2026-09-15').status_code, 409)
        self.assertEqual(self.post(f'/api/billing-invoices/{invoice_id}/record-payment/', {'reference': 'Bank-1'}).status_code, 409)
        self.assertEqual(self.post(f'/api/billing-invoices/{invoice_id}/issue/', {}).status_code, 200)
        self.assertEqual(self.post(f'/api/billing-invoices/{invoice_id}/issue/', {}).status_code, 200)
        self.assertEqual(self.post(f'/api/billing-invoices/{invoice_id}/record-payment/', {'reference': '  '}).status_code, 400)
        paid = self.post(f'/api/billing-invoices/{invoice_id}/record-payment/', {'reference': 'Bank-1'})
        self.assertEqual(paid.status_code, 200)
        self.assertIsNotNone(paid.json()['paid_at']); self.assertEqual(paid.json()['payment_recorded_by'], self.super_admin.pk)
        self.assertEqual(self.post(f'/api/billing-invoices/{invoice_id}/record-payment/', {'reference': 'Bank-1'}).status_code, 200)
        self.assertEqual(AuditLog.objects.filter(action_type='BILLING_RECORD_PAYMENT', object_id=str(invoice_id)).count(), 1)
        self.assertEqual(self.post(f'/api/billing-invoices/{invoice_id}/record-payment/', {'reference': 'Bank-2'}).status_code, 409)
        self.assertEqual(self.post(f'/api/billing-invoices/{invoice_id}/void/', {'reason': 'No longer needed'}).status_code, 409)
        self.assertEqual(self.client.patch(f'/api/billing-invoices/{invoice_id}/', data={'amount': '0'}, content_type='application/json').status_code, 405)
        self.assertEqual(self.client.delete(f'/api/billing-invoices/{invoice_id}/').status_code, 405)
        self.plan.price_per_user = '500'; self.plan.save()
        self.configure()
        self.assertEqual(str(BillingInvoice.objects.get(pk=invoice_id).amount), '798.00')
        self.client.force_login(self.admin)
        self.assertEqual(self.post(f'/api/billing-invoices/{invoice_id}/void/', {'reason': 'Attempt'}).status_code, 403)
        self.assertEqual(self.client.get(f'/api/billing-invoices/{invoice_id}/').status_code, 200)
        self.client.force_login(self.other_sales)
        self.other_sales.profile.role = 'COMPANY_ADMIN'; self.other_sales.profile.save()
        self.assertEqual(self.client.get(f'/api/billing-invoices/{invoice_id}/').status_code, 404)

    def test_nonbillable_guard_annual_periods_void_and_currency_totals(self):
        from .models import BillingInvoice
        sub = self.configure(plan=self.internal, cycle='NONE').json()
        self.assertFalse(sub['is_billable'])
        self.assertEqual(self.draft(sub['id']).status_code, 400)
        self.company.status = 'TRIAL_ACTIVE'; self.company.plan = self.trial_plan; self.company.save()
        self.assertEqual(self.configure().status_code, 400)
        self.company.status = 'ACTIVE'; self.company.save()
        sub = self.configure(cycle='ANNUAL').json()
        row = self.draft(sub['id'], start='2024-02-29').json()
        self.assertEqual(row['amount'], '11970.00')
        self.assertEqual(row['billing_period_end'], '2025-02-27')
        self.assertEqual(self.post(f'/api/billing-invoices/{row["id"]}/void/', {'reason': ''}).status_code, 400)
        voided = self.post(f'/api/billing-invoices/{row["id"]}/void/', {'reason': 'Incorrect billing period'})
        self.assertEqual(voided.status_code, 200)
        self.assertEqual(voided.json()['status'], 'VOID'); self.assertIsNotNone(voided.json()['voided_at'])
        self.assertEqual(self.draft(sub['id'], start='2024-02-29').status_code, 201)
        legacy = BillingInvoice.objects.create(company=self.company, amount=10, currency='USD', status='DRAFT')
        self.assertEqual(self.post(f'/api/billing-invoices/{legacy.pk}/issue/', {}).status_code, 409)
        totals = self.client.get('/api/subscriptions/overview/').json()['invoice_totals']
        self.assertEqual({row['currency'] for row in totals}, {'INR', 'USD'})
        self.assertEqual(self.post(f'/api/billing-invoices/{legacy.pk}/void/', {'reason': 'Retire placeholder'}).status_code, 200)
        self.configure(plan=self.internal, cycle='NONE')
        draft = BillingInvoice.objects.filter(provider='MANUAL', status='DRAFT').get()
        self.assertEqual(self.post(f'/api/billing-invoices/{draft.pk}/issue/', {}).status_code, 409)

    def test_plan_validation_and_subscription_validation(self):
        self.assertEqual(self.configure(cycle='NONE').status_code, 400)
        self.assertEqual(self.configure(plan=self.internal).status_code, 400)
        self.assertEqual(self.configure(plan=self.trial_plan).status_code, 400)
        self.plan.max_users = 1; self.plan.save()
        self.assertEqual(self.configure().status_code, 400)
        self.assertFalse(Subscription.objects.exists())
        for payload in ({'price_per_user': '-1'}, {'max_users': 0}, {'max_devices': 0}, {'screenshot_retention_days': 0}, {'code': 'PRO'}):
            response = self.client.patch(f'/api/plans/{self.plan.pk}/', data=payload, content_type='application/json')
            self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.client.patch(f'/api/plans/{self.internal.pk}/', data={'price_per_user': '1'}, content_type='application/json').status_code, 400)
        self.assertEqual(self.client.delete(f'/api/plans/{self.plan.pk}/').status_code, 405)
        self.assertEqual(self.client.patch(f'/api/plans/{self.plan.pk}/', data={'is_active': False}, content_type='application/json').status_code, 200)
        self.assertEqual(self.configure().status_code, 400)
        self.assertEqual(self.draft(999999).status_code, 400)
        self.assertEqual(self.post('/api/subscriptions/configure/', {'company_id': 'bad', 'plan_id': self.plan.pk, 'billing_cycle': 'MONTHLY'}).status_code, 400)

    def test_invoice_pagination_and_own_company_totals(self):
        from .models import BillingInvoice
        BillingInvoice.objects.bulk_create([BillingInvoice(company=self.company, amount=1) for _ in range(51)])
        BillingInvoice.objects.create(company=self.other, amount=999)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/billing-invoices/').json()['count'], 51)
        self.assertEqual(len(self.client.get('/api/billing-invoices/?page=2').json()['results']), 1)
        self.assertEqual(self.client.get('/api/billing-invoices/?status=invalid').status_code, 400)
        self.assertEqual(self.client.get('/api/subscriptions/overview/').json()['invoice_totals'][0]['amount'], 51.0)


class ERPConnectorSettingsTest(WorkflowFixture):
    def setUp(self):
        self.client.force_login(self.admin)

    def connector(self, **extra):
        result = self.post('/api/erp-connectors/', {'name': 'CRM source', 'allowed_event_types': ['erp_user_created', 'erp_user_updated', 'erp_user_inactive', 'pi_created'], **extra})
        self.assertEqual(result.status_code, 201, result.content)
        return result.json()

    def ingest(self, token, event='pi_created', external_id='ERP-101', payload=None):
        return self.client.post('/api/erp/ingest/', data={'event_type': event, 'external_id': external_id, 'payload': payload or {}},
            content_type='application/json', HTTP_X_WORKPULSE_TOKEN=token, HTTP_AUTHORIZATION='Token irrelevant-user-token')

    def test_tokens_are_masked_audited_rotated_and_disabling_blocks_ingest(self):
        from .models import AuditLog
        row = self.connector()
        token = row['api_token']
        self.assertGreaterEqual(len(token), 32)
        self.assertIsNotNone(row['token_rotated_at'])
        self.assertNotIn('api_token', self.client.get('/api/erp-connectors/').json()['results'][0])
        self.assertNotIn('api_token', self.client.get(f'/api/erp-connectors/{row["id"]}/').json())
        self.assertEqual(self.ingest(token).status_code, 202)
        reveal = self.post(f'/api/erp-connectors/{row["id"]}/reveal-token/', {})
        self.assertEqual(reveal.json()['api_token'], token); self.assertEqual(reveal['Cache-Control'], 'private, no-store')
        rotated = self.post(f'/api/erp-connectors/{row["id"]}/rotate-token/', {})
        new_token = rotated.json()['api_token']; self.assertNotEqual(new_token, token)
        self.assertEqual(self.ingest(token).status_code, 403)
        self.assertEqual(self.ingest(new_token).status_code, 202)
        disabled = self.client.patch(f'/api/erp-connectors/{row["id"]}/', data={'is_active': False}, content_type='application/json')
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(disabled.json()['event_count'], 2)
        self.assertEqual(self.ingest(new_token).status_code, 403)
        self.assertEqual(self.client.get('/api/erp-connectors/?status=INACTIVE').json()['count'], 1)
        self.assertEqual(self.client.delete(f'/api/erp-connectors/{row["id"]}/').status_code, 405)
        for log in AuditLog.objects.all():
            self.assertNotIn(token, str(log.before_data) + str(log.after_data))
            self.assertNotIn(new_token, str(log.before_data) + str(log.after_data))
        self.assertTrue(AuditLog.objects.filter(action_type='ROTATE_ERP_TOKEN').exists())
        AuditLog.objects.create(company=self.company, action_type='LEGACY', before_data={'api_token': token}, after_data={'nested': {'token': token}})
        self.assertNotIn(token, self.client.get('/api/audit-logs/').content.decode())

    def test_read_only_hr_and_cross_tenant_write_protection(self):
        row = self.connector()
        hr = User.objects.create_user(username='erp-hr', password='secret')
        Profile.objects.create(user=hr, company=self.company, role='HR_ADMIN')
        self.client.force_login(hr)
        self.assertEqual(self.client.get('/api/erp-connectors/').status_code, 200)
        self.assertFalse(self.client.get('/api/erp-connectors/form-options/').json()['can_manage'])
        self.assertEqual(self.post(f'/api/erp-connectors/{row["id"]}/reveal-token/', {}).status_code, 403)
        self.assertEqual(self.post(f'/api/erp-connectors/{row["id"]}/rotate-token/', {}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.patch(f'/api/erp-connectors/{row["id"]}/', data={'company': self.other.pk}, content_type='application/json').status_code, 400)
        self.assertEqual(self.post('/api/erp-connectors/', {'company': self.other.pk, 'name': 'Forbidden', 'allowed_event_types': ['pi_created']}).status_code, 403)
        self.assertEqual(self.client.get(f'/api/erp-connectors/?company_id={self.other.pk}').status_code, 403)
        self.other_sales.profile.role = 'COMPANY_ADMIN'; self.other_sales.profile.save(); self.client.force_login(self.other_sales)
        self.assertEqual(self.client.get(f'/api/erp-connectors/{row["id"]}/').status_code, 404)
        self.assertEqual(self.post(f'/api/erp-connectors/{row["id"]}/rotate-token/', {}).status_code, 404)
        for user in (self.employee, self.sales):
            self.client.force_login(user)
            self.assertEqual(self.client.get('/api/erp-connectors/').status_code, 403)
            self.assertEqual(self.client.get('/api/erp-events/').status_code, 403)

    def test_event_selection_validation_duplicate_names_and_history(self):
        for bad in ('pi_created', {'pi_created': True}, ['bad event!'], [12], [], ['UPPER_CASE']):
            response = self.post('/api/erp-connectors/', {'name': 'Bad', 'allowed_event_types': bad})
            self.assertEqual(response.status_code, 400, response.content)
        row = self.connector(allowed_event_types=['pi_created', 'pi_created', 'erp_user_created', 'erp_user_updated'])
        self.assertEqual(len(row['allowed_event_types']), 3)
        self.assertEqual(self.post('/api/erp-connectors/', {'name': ' crm SOURCE ', 'allowed_event_types': ['pi_created']}).status_code, 400)
        self.assertEqual(self.client.patch(f'/api/erp-connectors/{row["id"]}/', data={'api_token': 'insecure'}, content_type='application/json').status_code, 400)
        token = row['api_token']
        self.assertEqual(self.ingest(token, event='erp_user_inactive').status_code, 400)
        processed = self.ingest(token, event='erp_user_created', payload={'email': 'erp.created@flow.example'})
        self.assertEqual(processed.status_code, 200, processed.content)
        failed = self.ingest(token, event='erp_user_updated', external_id='unknown', payload={'email': 'missing@example.com'})
        self.assertEqual(failed.status_code, 409)
        received = self.ingest(token)
        self.assertEqual(received.status_code, 202)
        for status in ('PROCESSED', 'FAILED', 'RECEIVED'):
            response = self.client.get(f'/api/erp-events/?status={status}&connector_id={row["id"]}')
            self.assertEqual(response.json()['count'], 1)
            self.assertEqual(response.json()['results'][0]['processing_status'], status)
            self.assertNotIn('payload', response.json()['results'][0])
        detail = self.client.get(f'/api/erp-events/{processed.json()["event"]["id"]}/').json()
        self.assertEqual(detail['payload']['email'], 'erp.created@flow.example')
        self.assertEqual(self.client.get('/api/erp-events/?status=bad').status_code, 400)
        self.assertEqual(self.client.get('/api/erp-events/?from_date=2026-09-26&to_date=2026-09-25').status_code, 400)
        stats = self.client.get('/api/erp-connectors/').json()['results'][0]
        self.assertEqual(stats['event_count'], 3); self.assertIsNotNone(stats['last_received_at'])
        self.assertEqual(self.client.get(f'/api/erp-events/?company_id={self.other.pk}').status_code, 403)
        self.client.force_login(self.other_sales); self.other_sales.profile.role = 'COMPANY_ADMIN'; self.other_sales.profile.save()
        self.assertEqual(self.client.get(f'/api/erp-events/{detail["id"]}/').status_code, 404)

    def test_super_admin_options_include_all_companies_and_events_paginate(self):
        row = self.connector()
        ERPEvent.objects.bulk_create([ERPEvent(company=self.company, connector_id=row['id'], event_type='pi_created') for _ in range(51)])
        self.assertEqual(len(self.client.get('/api/erp-events/?page=2').json()['results']), 1)
        self.client.force_login(self.super_admin)
        data = self.client.get('/api/erp-connectors/form-options/').json()
        self.assertEqual({c['id'] for c in data['companies']}, {self.company.pk, self.other.pk})
        self.assertEqual(data['connectors'], [])
        scoped = self.client.get(f'/api/erp-connectors/form-options/?company_id={self.company.pk}').json()
        self.assertEqual(scoped['connectors'][0]['id'], row['id'])
        self.assertEqual(len(scoped['companies']), 2)
        self.assertEqual(self.post('/api/erp-connectors/', {'name': 'Invalid', 'company': 'bad', 'allowed_event_types': ['pi_created']}).status_code, 400)
