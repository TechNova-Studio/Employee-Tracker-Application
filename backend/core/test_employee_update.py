from django.contrib.auth.models import User
from django.test import TestCase

from .models import AuditLog, Company, Department, ERPConnector, ERPEmployeeMapping, Profile


class EmployeeUpdateAPITest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Glutape')
        self.other = Company.objects.create(name='Other')
        self.admin = self.employee('admin', role='COMPANY_ADMIN')
        self.target = self.employee('target')
        self.manager = self.employee('manager', role='MANAGER')
        self.foreign = self.employee('foreign', company=self.other, role='MANAGER')
        self.super = self.employee('super', role='SUPER_ADMIN')
        self.department = Department.objects.create(company=self.company, name='Sales')
        self.foreign_department = Department.objects.create(company=self.other, name='Foreign')
        self.connector = ERPConnector.objects.create(company=self.company, api_token='employee-update-connector',
            allowed_event_types=['erp_user_active', 'erp_user_updated'])
        self.mapping = ERPEmployeeMapping.objects.create(connector=self.connector, external_id='21', user=self.target)
        self.client.force_login(self.admin)

    def employee(self, username, role='EMPLOYEE', company=None):
        user = User.objects.create_user(username=username, email=f'{username}@update.test')
        Profile.objects.create(user=user, company=company or self.company, role=role)
        return user

    def patch(self, body, user=None):
        return self.client.patch(f'/api/users/{(user or self.target).pk}/', body, content_type='application/json')

    def test_manual_details_and_role_assignment_preserve_crm_identity(self):
        response = self.patch({'email': 'updated@update.test', 'first_name': 'Megha', 'last_name': 'Sharma',
                               'role': 'MANAGER', 'department': self.department.pk, 'manager': self.manager.pk})
        self.assertEqual(response.status_code, 200, response.content)
        self.target.refresh_from_db(); self.mapping.refresh_from_db()
        self.assertEqual(self.mapping.external_id, '21')
        self.assertEqual(self.mapping.user_id, self.target.pk)
        self.assertEqual(self.target.profile.role, 'MANAGER')
        self.assertEqual(self.target.profile.department_id, self.department.pk)
        self.assertEqual(self.target.profile.manager_id, self.manager.pk)
        self.assertEqual(response.json()['profile']['manager_name'], self.manager.email)
        self.assertTrue(AuditLog.objects.filter(action_type='UPDATE_USER').exists())
        event = self.client.post('/api/erp/ingest/', {'event_type': 'erp_user_updated', 'external_id': '21',
            'payload': {'first_name': 'Current CRM Name'}}, content_type='application/json', HTTP_X_WORKPULSE_TOKEN=self.connector.api_token)
        self.assertEqual(event.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.profile.role, 'MANAGER')
        self.assertEqual(self.target.profile.department_id, self.department.pk)
        self.assertEqual(self.target.profile.manager_id, self.manager.pk)

    def test_clear_optional_assignments_and_set_password_for_erp_created_user(self):
        self.target.profile.department = self.department
        self.target.profile.manager = self.manager
        self.target.profile.save()
        self.assertFalse(self.target.has_usable_password())
        response = self.patch({'department': None, 'manager': None, 'password': 'Setup-Password-987!'})
        self.assertEqual(response.status_code, 200, response.content)
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password('Setup-Password-987!'))
        self.assertIsNone(self.target.profile.department)
        self.assertIsNone(self.target.profile.manager)
        self.assertEqual(self.mapping.user_id, self.target.pk)

    def test_omitted_password_does_not_reset_existing_password(self):
        self.target.set_password('Original-Password-123!'); self.target.save()
        self.assertEqual(self.patch({'first_name': 'Updated'}).status_code, 200)
        self.assertEqual(self.patch({'password': ''}).status_code, 400)
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password('Original-Password-123!'))

    def test_basic_manual_creation_without_password_allows_later_setup(self):
        response = self.client.post('/api/users/', {'username': 'basic', 'email': 'basic@update.test',
            'first_name': 'Basic', 'last_name': 'Employee'}, content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        created = User.objects.get(pk=response.json()['id'])
        self.assertFalse(created.has_usable_password())
        self.assertEqual(created.profile.role, 'EMPLOYEE')
        self.assertEqual(created.profile.company_id, self.company.pk)
        self.assertIsNone(created.profile.department)
        self.assertIsNone(created.profile.manager)
        self.assertEqual(self.patch({'password': 'Set-Later-Password-987!'}, user=created).status_code, 200)
        created.refresh_from_db()
        self.assertTrue(created.check_password('Set-Later-Password-987!'))

    def test_promoted_manager_is_available_for_next_employee_creation(self):
        url = f'/api/users/form-options/?company_id={self.company.pk}'
        before = self.client.get(url)
        self.assertEqual(before.status_code, 200)
        self.assertNotIn(self.target.pk, [row['id'] for row in before.json()['managers']])

        response = self.patch({'role': 'MANAGER'})
        self.assertEqual(response.status_code, 200, response.content)
        options = self.client.get(url)
        self.assertEqual(options.status_code, 200)
        manager_ids = [row['id'] for row in options.json()['managers']]
        self.assertIn(self.target.pk, manager_ids)
        self.assertNotIn(self.foreign.pk, manager_ids)

        created = self.client.post('/api/users/', {'username': 'new-report', 'email': 'new-report@update.test',
            'manager': self.target.pk}, content_type='application/json')
        self.assertEqual(created.status_code, 201, created.content)
        employee = User.objects.get(pk=created.json()['id'])
        self.assertEqual(employee.profile.manager_id, self.target.pk)
        self.mapping.refresh_from_db()
        self.assertEqual(self.mapping.user_id, self.target.pk)

        self.assertEqual(self.patch({'role': 'EMPLOYEE'}).status_code, 200)
        options = self.client.get(url)
        self.assertNotIn(self.target.pk, [row['id'] for row in options.json()['managers']])

    def test_promoting_inactive_employee_does_not_make_them_an_assignable_manager(self):
        url = f'/api/users/form-options/?company_id={self.company.pk}'
        self.assertEqual(self.patch({'role': 'MANAGER'}).status_code, 200)
        self.target.is_active = False
        self.target.save(update_fields=['is_active'])
        self.assertNotIn(self.target.pk, [row['id'] for row in self.client.get(url).json()['managers']])
        self.target.is_active = True
        self.target.save(update_fields=['is_active'])
        self.target.profile.is_active_employee = False
        self.target.profile.save(update_fields=['is_active_employee'])
        self.assertNotIn(self.target.pk, [row['id'] for row in self.client.get(url).json()['managers']])

    def test_super_admin_cannot_assign_foreign_department_or_manager(self):
        self.client.force_login(self.super)
        for payload in ({'department': self.foreign_department.pk}, {'manager': self.foreign.pk}):
            response = self.patch({'first_name': 'Must not save', **payload})
            self.assertEqual(response.status_code, 400, response.content)
        self.target.refresh_from_db()
        self.assertEqual(self.target.first_name, '')
        self.assertFalse(AuditLog.objects.filter(action_type='UPDATE_USER').exists())

    def test_linked_employee_cannot_move_company_or_become_platform_super_admin(self):
        self.client.force_login(self.super)
        self.assertEqual(self.patch({'company': self.other.pk}).status_code, 400)
        self.assertEqual(self.patch({'role': 'SUPER_ADMIN'}).status_code, 400)
        self.mapping.refresh_from_db(); self.target.refresh_from_db()
        self.assertEqual(self.target.profile.company_id, self.company.pk)
        self.assertEqual(self.target.profile.role, 'EMPLOYEE')
        self.assertEqual(self.mapping.external_id, '21')

    def test_invalid_role_and_self_manager_are_rejected(self):
        self.assertEqual(self.patch({'role': 'not-a-role'}).status_code, 400)
        self.assertEqual(self.patch({'manager': self.target.pk}).status_code, 400)
        self.assertEqual(self.patch({'email': ''}).status_code, 400)

    def test_employee_write_and_company_admin_super_admin_edit_are_blocked(self):
        self.assertEqual(self.patch({'first_name': 'Blocked'}, user=self.super).status_code, 403)
        self.client.force_login(self.target)
        self.assertEqual(self.patch({'first_name': 'Blocked'}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.patch({'first_name': 'Blocked'}, user=self.foreign).status_code, 404)

    def test_current_inactive_assignments_are_preserved_but_new_ones_are_rejected(self):
        self.department.is_active = False; self.department.save()
        self.manager.is_active = False; self.manager.save()
        self.target.profile.department = self.department
        self.target.profile.manager = self.manager
        self.target.profile.save()
        self.assertEqual(self.patch({'first_name': 'Updated', 'department': self.department.pk, 'manager': self.manager.pk}).status_code, 200)
        second = self.employee('second')
        self.assertEqual(self.patch({'department': self.department.pk}, user=second).status_code, 400)
        self.assertEqual(self.patch({'manager': self.manager.pk}, user=second).status_code, 400)

    def test_employee_search_company_filter_and_pagination(self):
        self.target.first_name = 'Megha'; self.target.save()
        matched = self.client.get('/api/users/?search=Megha').json()
        self.assertEqual([row['id'] for row in matched['results']], [self.target.pk])
        self.assertEqual(self.client.get(f'/api/users/?company_id={self.other.pk}').status_code, 403)
        for index in range(51):
            self.employee(f'page-user-{index}')
        page = self.client.get('/api/users/?page=1').json()
        self.assertEqual(len(page['results']), 50)
        self.assertIsNotNone(page['next'])
        self.assertGreater(len(self.client.get('/api/users/?page=2').json()['results']), 0)
        self.client.force_login(self.super)
        other = self.client.get(f'/api/users/?company_id={self.other.pk}').json()
        self.assertEqual([row['id'] for row in other['results']], [self.foreign.pk])
