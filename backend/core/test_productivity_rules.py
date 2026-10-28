from django.contrib.auth.models import User
from django.test import TestCase

from .models import AppWebsiteCategory, Company, Department, Profile
from .views import classify_activity


class ProductivityRuleManagementTests(TestCase):
    endpoint = '/api/productivity-categories/'

    def setUp(self):
        self.company = Company.objects.create(name='Glutape')
        self.other = Company.objects.create(name='Other company')
        self.department = Department.objects.create(company=self.company, name='Engineering')
        self.inactive_department = Department.objects.create(company=self.company, name='Archived', is_active=False)
        self.other_department = Department.objects.create(company=self.other, name='Other department')
        self.admin = self.user('admin', 'COMPANY_ADMIN', self.company, self.department)
        self.super_admin = self.user('super', 'SUPER_ADMIN', None)
        self.client.force_login(self.admin)

    def user(self, name, role, company, department=None):
        user = User.objects.create_user(username=name)
        Profile.objects.create(user=user, company=company, department=department, role=role)
        return user

    def post(self, **extra):
        return self.client.post(self.endpoint, {'pattern_type': 'DOMAIN', 'pattern': 'github.com',
            'category': 'PRODUCTIVE', **extra}, content_type='application/json')

    def patch(self, pk, **extra):
        return self.client.patch(f'{self.endpoint}{pk}/', extra, content_type='application/json')

    def rule(self, **extra):
        return AppWebsiteCategory.objects.create(company=self.company, pattern_type='DOMAIN',
            pattern='github.com', category='PRODUCTIVE', **extra)

    def test_company_options_are_scoped_and_foreign_company_filters_are_denied(self):
        response = self.client.get(self.endpoint + 'form-options/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['companies'], [{'id': self.company.pk, 'name': 'Glutape'}])
        self.assertEqual(data['selected_company_id'], self.company.pk)
        self.assertEqual({item['id'] for item in data['departments']}, {self.department.pk, self.inactive_department.pk})
        for path in (self.endpoint, self.endpoint + 'form-options/'):
            self.assertEqual(self.client.get(path, {'company_id': self.other.pk}).status_code, 403)

    def test_super_admin_explicit_company_and_department_options(self):
        self.client.force_login(self.super_admin)
        data = self.client.get(self.endpoint + 'form-options/').json()
        self.assertEqual(len(data['companies']), 2)
        self.assertIsNone(data['selected_company_id'])
        self.assertEqual(data['departments'], [])
        data = self.client.get(self.endpoint + 'form-options/', {'company_id': self.other.pk}).json()
        self.assertEqual([item['id'] for item in data['departments']], [self.other_department.pk])
        self.assertEqual(self.post().status_code, 400)
        response = self.post(company=self.other.pk, department=self.other_department.pk)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['company'], self.other.pk)
        for company_id in ('bad', '-1', '999999'):
            self.assertEqual(self.client.get(self.endpoint + 'form-options/', {'company_id': company_id}).status_code, 400)

    def test_create_update_and_deactivate_keep_the_company(self):
        response = self.post(pattern='  GitHub.COM  ', notes='Development tools')
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data['company'], self.company.pk)
        self.assertEqual(data['pattern'], 'github.com')
        self.assertEqual(data['company_name'], 'Glutape')
        self.assertIsNone(data['department'])
        response = self.patch(data['id'], department=self.department.pk, category='NEUTRAL', notes='Review', is_active=False)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['department_name'], 'Engineering')
        self.assertFalse(response.json()['is_active'])
        self.assertEqual(response.json()['category'], 'NEUTRAL')
        self.assertEqual(self.patch(data['id'], is_active=True).status_code, 200)

    def test_existing_api_default_application_type_is_preserved(self):
        response = self.client.post(self.endpoint, {'pattern': 'Code.exe', 'category': 'PRODUCTIVE'}, content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['pattern_type'], 'APP')

    def test_cross_company_creates_moves_and_departments_are_rejected(self):
        self.assertEqual(self.post(company=self.other.pk).status_code, 403)
        self.assertEqual(self.post(department=self.other_department.pk).status_code, 400)
        rule = self.rule()
        self.assertEqual(self.patch(rule.pk, company=self.other.pk).status_code, 400)
        self.assertEqual(self.patch(rule.pk, department=self.other_department.pk).status_code, 400)
        rule.refresh_from_db()
        self.assertEqual(rule.company_id, self.company.pk)
        self.assertIsNone(rule.department_id)
        foreign = AppWebsiteCategory.objects.create(company=self.other, pattern='secret', category='NEUTRAL')
        self.assertEqual(self.patch(foreign.pk, category='PRODUCTIVE').status_code, 404)
        self.assertEqual(self.client.get(f'{self.endpoint}{foreign.pk}/').status_code, 404)
        self.client.force_login(self.super_admin)
        self.assertEqual(self.patch(rule.pk, company=self.other.pk).status_code, 400)

    def test_inactive_departments_cannot_be_newly_assigned_but_existing_rules_can_be_edited(self):
        self.assertEqual(self.post(department=self.inactive_department.pk).status_code, 400)
        rule = self.rule(department=self.inactive_department)
        self.assertEqual(self.patch(rule.pk, is_active=False).status_code, 200)
        self.assertEqual(self.patch(rule.pk, department=None).status_code, 200)
        self.assertEqual(self.patch(rule.pk, department=self.inactive_department.pk).status_code, 400)

    def test_invalid_patterns_types_and_duplicates_are_rejected(self):
        for extra in ({'pattern': '  '}, {'pattern_type': 'OTHER'}, {'category': 'OTHER'},
                      {'pattern': 'https://github.com/path'}, {'pattern': '*.github.com'},
                      {'pattern': 'github.com:443'}, {'pattern': 'bad..host'}):
            self.assertEqual(self.post(**extra).status_code, 400, extra)
        response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.post(pattern='GITHUB.COM').status_code, 400)
        self.assertEqual(self.patch(response.json()['id'], notes='Same identity').status_code, 200)
        self.assertEqual(self.post(department=self.department.pk).status_code, 201)
        self.assertEqual(self.post(pattern_type='URL', pattern='https://github.com/path').status_code, 201)

    def test_saved_rules_drive_department_precedence_and_deactivation(self):
        self.assertEqual(self.post().status_code, 201)
        response = self.post(department=self.department.pk, category='UNPRODUCTIVE')
        self.assertEqual(response.status_code, 201)
        def classify(domain):
            return classify_activity(self.company, self.admin, 'Browser', domain, '')
        self.assertEqual(classify('docs.github.com'), 'UNPRODUCTIVE')
        self.assertEqual(self.patch(response.json()['id'], is_active=False).status_code, 200)
        self.assertEqual(classify('docs.github.com'), 'PRODUCTIVE')
        self.assertEqual(classify('github.com.evil.example'), 'UNKNOWN')
        self.assertEqual(classify_activity(self.other, self.admin, 'Browser', 'github.com', ''), 'UNKNOWN')

    def test_window_alias_normalization_and_longer_pattern_precedence(self):
        result = self.post(pattern_type='window_title', pattern='BOLD ERP', category='NEUTRAL')
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json()['pattern_type'], 'WINDOW')
        self.assertEqual(self.post(pattern_type='WINDOW', pattern='BOLD ERP — Sales', category='PRODUCTIVE').status_code, 201)
        self.assertEqual(classify_activity(self.company, self.admin, '', '', 'BOLD ERP — Sales order'), 'PRODUCTIVE')

    def test_rules_are_paginated_and_list_filters_are_applied_before_pagination(self):
        AppWebsiteCategory.objects.bulk_create([AppWebsiteCategory(company=self.company, pattern=f'app-{index:02d}',
            pattern_type='APP', category='PRODUCTIVE', notes='Development') for index in range(25)])
        self.rule(department=self.department, is_active=False)
        response = self.client.get(self.endpoint, {'page_size': 10, 'page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 26)
        self.assertEqual(len(response.json()['results']), 10)
        response = self.client.get(self.endpoint, {'search': 'Development', 'category': 'PRODUCTIVE',
            'pattern_type': 'APP', 'is_active': 'true', 'department_id': 'company', 'page_size': 50})
        self.assertEqual(response.json()['count'], 25)
        response = self.client.get(self.endpoint, {'department_id': self.department.pk, 'is_active': 'false'})
        self.assertEqual(response.json()['count'], 1)
        for extra in ({'category': 'BAD'}, {'pattern_type': 'BAD'}, {'is_active': 'yes'}, {'department_id': '-2'}, {'company_id': 'bad'}):
            self.assertEqual(self.client.get(self.endpoint, extra).status_code, 400, extra)

    def test_only_authorized_admin_roles_can_manage_rules(self):
        for role in ('HR_ADMIN', 'COMPANY_ADMIN'):
            actor = self.user(role, role, self.company)
            self.client.force_login(actor)
            self.assertEqual(self.client.get(self.endpoint + 'form-options/').status_code, 200)
        for role in ('MANAGER', 'EMPLOYEE', 'SALES_ADMIN'):
            actor = self.user(role, role, self.company)
            self.client.force_login(actor)
            self.assertEqual(self.client.get(self.endpoint).status_code, 403)
            self.assertEqual(self.client.get(self.endpoint + 'form-options/').status_code, 403)
            self.assertEqual(self.post().status_code, 403)
        self.client.logout()
        self.assertIn(self.client.get(self.endpoint).status_code, (401, 403))
