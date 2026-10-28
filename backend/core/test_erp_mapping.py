import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.test import TestCase
from rest_framework.authtoken.models import Token

from .models import AuditLog, Company, ERPConnector, ERPEmployeeMapping, ERPEvent, Profile, WorkSession


class ERPEmployeeMappingAPITest(TestCase):
    url = '/api/erp/employee-mappings/'

    def setUp(self):
        self.company = Company.objects.create(name='Glutape')
        self.other = Company.objects.create(name='Other')
        self.admin = self.employee('admin', self.company, role='COMPANY_ADMIN')
        self.hr = self.employee('hr', self.company, role='HR_ADMIN')
        self.target = self.employee('target', self.company)
        self.second = self.employee('second', self.company)
        self.foreign = self.employee('foreign', self.other)
        self.super = self.employee('super', self.company, role='SUPER_ADMIN')
        self.connector = ERPConnector.objects.create(company=self.company, api_token='mapping-token',
            allowed_event_types=['erp_user_created', 'erp_user_updated', 'erp_user_active', 'erp_user_inactive'])
        self.other_connector = ERPConnector.objects.create(company=self.other, api_token='other-mapping-token',
            allowed_event_types=self.connector.allowed_event_types)
        self.client.force_login(self.admin)

    def employee(self, name, company, role='EMPLOYEE'):
        user = User.objects.create_user(username=name, email=f'{name}@mapping.test')
        Profile.objects.create(user=user, company=company, role=role)
        return user

    def post(self, body, suffix=''):
        return self.client.post(self.url + suffix, body, content_type='application/json')

    def link(self, identity='21', user=None, connector=None):
        return self.post({'connector_id': (connector or self.connector).pk, 'external_id': identity,
                          'workpulse_employee_id': (user or self.target).pk})

    def event(self, kind, identity='21', payload=None, token=None):
        return self.client.post('/api/erp/ingest/', {'event_type': kind, 'external_id': identity, 'payload': payload or {}},
            content_type='application/json', HTTP_X_WORKPULSE_TOKEN=token or self.connector.api_token)

    def test_save_different_ids_and_replay_is_idempotent(self):
        self.assertNotEqual(self.target.pk, 21)
        saved = self.link()
        self.assertEqual(saved.status_code, 201, saved.content)
        self.assertEqual(saved.json()['workpulse_employee_id'], self.target.pk)
        self.assertEqual(saved.json()['external_id'], '21')
        self.assertEqual(self.link().status_code, 200)
        self.assertEqual(ERPEmployeeMapping.objects.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action_type='CREATE_ERP_EMPLOYEE_MAPPING').count(), 1)

    def test_conflicting_source_or_target_cannot_replace_mapping(self):
        self.link()
        self.assertEqual(self.link(user=self.second).status_code, 409)
        self.assertEqual(self.link(identity='22').status_code, 409)
        self.assertEqual(ERPEmployeeMapping.objects.get().user_id, self.target.pk)

    def test_company_scope_and_protected_user(self):
        self.assertEqual(self.link(user=self.foreign).status_code, 400)
        self.assertEqual(self.link(user=self.super).status_code, 400)
        self.assertEqual(self.link(connector=self.other_connector).status_code, 404)
        self.assertEqual(self.client.get(self.url + f'?company_id={self.other.pk}').status_code, 403)
        self.assertEqual(ERPEmployeeMapping.objects.count(), 0)

    def test_admin_only_writes_and_hr_reads(self):
        self.link()
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.link(identity='22', user=self.second).status_code, 403)
        self.assertEqual(self.post({'connector_id': self.connector.pk, 'rows': []}, 'bulk/').status_code, 403)
        self.client.force_login(self.target)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout()
        response = self.client.post(self.url, {'connector_id': self.connector.pk, 'external_id': '22',
            'workpulse_employee_id': self.second.pk}, content_type='application/json', HTTP_X_WORKPULSE_TOKEN=self.connector.api_token)
        self.assertIn(response.status_code, (401, 403))

    def test_invalid_fields_do_not_save(self):
        for identity in ('', 'bad id', 'bad\nvalue', 'x' * 129, 21, {'id': 21}):
            self.assertEqual(self.link(identity=identity).status_code, 400)
        self.assertEqual(self.post({'connector_id': self.connector.pk, 'external_id': '21',
                                   'workpulse_employee_id': 999999}).status_code, 400)
        self.assertEqual(ERPEmployeeMapping.objects.count(), 0)

    def test_options_list_existing_active_and_inactive_users_and_mapping(self):
        self.link()
        self.second.is_active = False
        self.second.save()
        response = self.client.get(self.url + f'form-options/?connector_id={self.connector.pk}')
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()['results']
        self.assertNotIn(self.foreign.pk, {r['workpulse_employee_id'] for r in rows})
        self.assertNotIn(self.super.pk, {r['workpulse_employee_id'] for r in rows})
        mapped = next(r for r in rows if r['workpulse_employee_id'] == self.target.pk)
        self.assertEqual(mapped['external_id'], '21')
        self.assertEqual(mapped['workpulse_profile_id'], self.target.profile.pk)
        self.assertFalse(next(r for r in rows if r['workpulse_employee_id'] == self.second.pk)['is_active'])
        self.assertEqual(self.client.get(self.url + f'form-options/?connector_id={self.other_connector.pk}').status_code, 404)

    def test_bulk_dry_run_then_save_and_reimport(self):
        body = {'connector_id': self.connector.pk, 'dry_run': True, 'rows': [
            {'external_id': '21', 'workpulse_employee_id': self.target.pk},
            {'external_id': '34', 'workpulse_employee_id': self.second.pk}]}
        response = self.post(body, 'bulk/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['created'], 2)
        self.assertEqual(ERPEmployeeMapping.objects.count(), 0)
        self.assertFalse(AuditLog.objects.exists())
        body['dry_run'] = False
        self.assertEqual(self.post(body, 'bulk/').json()['created'], 2)
        self.assertEqual(self.post(body, 'bulk/').json()['unchanged'], 2)
        self.assertEqual(ERPEmployeeMapping.objects.count(), 2)

    def test_bulk_invalid_row_rolls_back_entire_batch(self):
        body = {'connector_id': self.connector.pk, 'rows': [
            {'external_id': '21', 'workpulse_employee_id': self.target.pk},
            {'external_id': '34', 'workpulse_employee_id': self.foreign.pk},
            {'external_id': '35', 'workpulse_employee_id': 999999}]}
        response = self.post(body, 'bulk/')
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(len(response.json()['rows']), 2)
        self.assertFalse(ERPEmployeeMapping.objects.exists())
        self.assertFalse(AuditLog.objects.exists())

    def test_bulk_duplicate_rows_are_rejected(self):
        row = {'external_id': '21', 'workpulse_employee_id': self.target.pk}
        response = self.post({'connector_id': self.connector.pk, 'rows': [row, row]}, 'bulk/')
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(ERPEmployeeMapping.objects.exists())

    def test_csv_dry_run_save_and_unchanged_import(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'mappings.csv'
            path.write_text(f'crm_employee_id,workpulse_employee_id\n21,{self.target.pk}\n', encoding='utf-8')
            output = StringIO()
            call_command('import_erp_mappings', connector_id=self.connector.pk, file=str(path), dry_run=True, stdout=output)
            self.assertFalse(ERPEmployeeMapping.objects.exists())
            call_command('import_erp_mappings', connector_id=self.connector.pk, file=str(path), stdout=output)
            call_command('import_erp_mappings', connector_id=self.connector.pk, file=str(path), stdout=output)
            self.assertEqual(ERPEmployeeMapping.objects.count(), 1)
            path.write_text(f'crm_employee_id,workpulse_employee_id\n22,{self.second.pk}\n23,{self.foreign.pk}\n', encoding='utf-8')
            with self.assertRaises(CommandError):
                call_command('import_erp_mappings', connector_id=self.connector.pk, file=str(path), stdout=output)
            self.assertEqual(ERPEmployeeMapping.objects.count(), 1)

    def test_lifecycle_uses_mapping_not_email_and_revokes_tokens(self):
        self.link()
        token = Token.objects.create(user=self.target)
        session = WorkSession.objects.create(company=self.company, user=self.target)
        response = self.event('erp_user_inactive', payload={'email': self.second.email})
        self.assertEqual(response.status_code, 200, response.content)
        self.target.refresh_from_db(); self.second.refresh_from_db(); session.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertTrue(self.second.is_active)
        self.assertFalse(self.target.profile.is_active_employee)
        self.assertEqual(session.status, 'AUTO_STOPPED')
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())
        self.assertEqual(self.event('erp_user_active').status_code, 200)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_missing_map_cannot_auto_match_existing_email(self):
        response = self.event('erp_user_inactive', payload={'email': self.target.email})
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['code'], 'mapping_required')
        self.assertEqual(self.event('erp_user_created', payload={'email': self.target.email}).status_code, 409)
        self.assertEqual(User.objects.count(), 6)
        self.assertFalse(ERPEmployeeMapping.objects.exists())
        self.assertEqual(ERPEvent.objects.filter(processed=False, processing_error__gt='').count(), 2)

    def test_create_employee_and_map_is_atomic_and_replay_safe(self):
        response = self.event('erp_user_created', identity='new-42', payload={'email': 'new@mapping.test', 'first_name': 'New'})
        self.assertEqual(response.status_code, 200, response.content)
        user_id = response.json()['workpulse_employee_id']
        self.assertEqual(ERPEmployeeMapping.objects.get(external_id='new-42').user_id, user_id)
        self.assertFalse(User.objects.get(pk=user_id).has_usable_password())
        again = self.event('erp_user_created', identity='new-42', payload={'email': 'new@mapping.test'})
        self.assertEqual(again.json()['user_id'], user_id)
        update = self.event('erp_user_updated', identity='new-42', payload={'email': 'changed@mapping.test', 'mobile': '123'})
        self.assertEqual(update.status_code, 200)
        self.assertEqual(User.objects.get(pk=user_id).email, 'changed@mapping.test')
        self.assertEqual(ERPEmployeeMapping.objects.count(), 1)
        self.assertEqual(User.objects.count(), 7)

    def test_update_email_conflict_rolls_back_other_profile_fields(self):
        self.link()
        response = self.event('erp_user_updated', payload={'email': self.second.email, 'first_name': 'Changed', 'mobile': '123'})
        self.assertEqual(response.status_code, 409)
        self.target.refresh_from_db()
        self.assertEqual(self.target.first_name, '')
        self.assertEqual(self.target.profile.mobile, '')

    def test_same_crm_id_is_isolated_between_companies_and_connectors(self):
        self.link()
        self.client.force_login(self.super)
        self.assertEqual(self.link(user=self.foreign, connector=self.other_connector).status_code, 201)
        response = self.event('erp_user_inactive', token=self.other_connector.api_token)
        self.assertEqual(response.json()['user_id'], self.foreign.pk)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_stale_company_or_protected_mapping_cannot_be_used(self):
        self.link()
        Profile.objects.filter(user=self.target).update(company=self.other)
        self.assertEqual(self.event('erp_user_inactive').status_code, 409)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_external_id_required_and_token_company_cannot_be_overridden(self):
        response = self.client.post('/api/erp/ingest/', {'event_type': 'erp_user_active', 'payload': {'email': self.target.email}},
            content_type='application/json', HTTP_X_WORKPULSE_TOKEN=self.connector.api_token)
        self.assertEqual(response.status_code, 400)
        for identity in ('', 21, {'id': 21}, 'bad id'):
            self.assertEqual(self.event('erp_user_active', identity=identity).status_code, 400)
        response = self.client.post('/api/erp/ingest/', {'event_type': 'erp_user_active', 'external_id': '21',
            'company_id': self.other.pk, 'payload': {}}, content_type='application/json', HTTP_X_WORKPULSE_TOKEN=self.connector.api_token)
        self.assertEqual(response.status_code, 400)

    def test_search_detail_and_pagination_are_scoped(self):
        saved = self.link().json()
        response = self.client.get(self.url + '?search=21')
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(self.client.get(self.url + f'{saved["id"]}/').status_code, 200)
        self.client.force_login(self.foreign)
        self.foreign.profile.role = 'COMPANY_ADMIN'; self.foreign.profile.save()
        self.assertEqual(self.client.get(self.url).json()['count'], 0)
        self.assertEqual(self.client.get(self.url + f'{saved["id"]}/').status_code, 404)

    def test_user_primary_key_is_distinct_from_profile_primary_key(self):
        User.objects.create(username='no-profile')
        employee = self.employee('different-user-id', self.company)
        self.assertNotEqual(employee.pk, employee.profile.pk)
        response = self.link(identity='77', user=employee)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['workpulse_employee_id'], employee.pk)
        response = self.event('erp_user_inactive', identity='77')
        self.assertEqual(response.json()['user_id'], employee.pk)
        employee.refresh_from_db()
        self.assertFalse(employee.is_active)

    def test_failed_create_rolls_back_employee_mapping_and_audit(self):
        self.target.profile.employee_code = 'EXISTING-CODE'
        self.target.profile.save()
        response = self.event('erp_user_created', identity='new-failed',
            payload={'email': 'must-not-exist@mapping.test', 'employee_id': 'EXISTING-CODE'})
        self.assertEqual(response.status_code, 409, response.content)
        self.assertFalse(User.objects.filter(email='must-not-exist@mapping.test').exists())
        self.assertFalse(ERPEmployeeMapping.objects.exists())
        self.assertFalse(AuditLog.objects.exists())

    def test_mapped_company_admin_role_is_preserved(self):
        self.link(user=self.admin)
        response = self.event('erp_user_updated', payload={'role': 'SUPER_ADMIN', 'first_name': 'Admin'})
        self.assertEqual(response.status_code, 200)
        self.admin.profile.refresh_from_db()
        self.assertEqual(self.admin.profile.role, 'COMPANY_ADMIN')

    def test_admin_login_token_authenticates_mapping_api(self):
        token = Token.objects.create(user=self.admin)
        self.client.logout()
        response = self.client.post(self.url, {'connector_id': self.connector.pk, 'external_id': '21',
            'workpulse_employee_id': self.target.pk}, content_type='application/json', HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(response.status_code, 201, response.content)
