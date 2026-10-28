from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Company, ERPConnector, ERPEvent, Profile


class EmployeeIdentityTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Glutape', employee_id_prefix='GLUTAPE')
        self.other = Company.objects.create(name='Other', employee_id_prefix='OTHER')
        self.connector = ERPConnector.objects.create(company=self.company, api_token='identity-test-token',
            allowed_event_types=['erp_user_created', 'erp_user_updated', 'erp_user_active', 'erp_user_inactive'])
        self.admin = User.objects.create_user(username='super', password='secret')
        Profile.objects.create(user=self.admin, role='SUPER_ADMIN')

    def ingest(self, kind, payload, **extra):
        self.client.logout()
        return self.client.post('/api/erp/ingest/', {'event_type': kind, 'payload': payload, **extra},
            content_type='application/json', HTTP_X_WORKPULSE_TOKEN=self.connector.api_token)

    def create_user(self, email, **extra):
        self.client.force_login(self.admin)
        return self.client.post('/api/users/', {'company': self.company.pk, 'role': 'EMPLOYEE',
            'email': email, 'username': email, 'password': 'secret', **extra}, content_type='application/json')

    def test_company_prefix_optional_and_normalized(self):
        self.client.force_login(self.admin)
        prefixed = self.client.post('/api/companies/', {'name': 'New', 'employee_id_prefix': ' glutape '},
            content_type='application/json')
        self.assertEqual(prefixed.status_code, 201, prefixed.content)
        self.assertEqual(prefixed.json()['employee_id_prefix'], 'GLUTAPE')
        plain = self.client.post('/api/companies/', {'name': 'Plain'}, content_type='application/json')
        self.assertEqual(plain.json()['employee_id_prefix'], '')
        invalid = self.client.post('/api/companies/', {'name': 'Bad', 'employee_id_prefix': 'bad prefix'},
            content_type='application/json')
        self.assertEqual(invalid.status_code, 400)

    def test_admin_is_first_id_then_employee_and_crm_id_is_preserved(self):
        admin = self.create_user('admin@id.test', role='COMPANY_ADMIN')
        self.assertEqual(admin.status_code, 201, admin.content)
        self.assertEqual(admin.json()['profile']['employee_id'], 'GLUTAPE0001')
        employee = self.create_user('employee@id.test')
        self.assertEqual(employee.json()['profile']['employee_id'], 'GLUTAPE0002')
        imported = self.create_user('imported@id.test', employee_id='GLUTAPE0101')
        self.assertEqual(imported.json()['profile']['employee_id'], 'GLUTAPE0101')
        following = self.create_user('following@id.test')
        self.assertEqual(following.json()['profile']['employee_id'], 'GLUTAPE0102')

    def test_no_prefix_uses_email_and_manual_id_is_optional(self):
        # A separate tenant with no prefix creates email-only profiles.
        self.other.employee_id_prefix = ''
        self.other.save(update_fields=['employee_id_prefix'])
        result = self.create_user('email-only@id.test', company=self.other.pk)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json()['profile']['employee_id'], '')

    def test_manual_duplicate_id_is_rejected_without_creating_user(self):
        self.create_user('first@id.test', employee_id='GLUTAPE0001')
        rejected = self.create_user('second@id.test', employee_id='glutape0001')
        self.assertEqual(rejected.status_code, 400, rejected.content)
        self.assertFalse(User.objects.filter(email='second@id.test').exists())
        with self.assertRaises(IntegrityError), transaction.atomic():
            user = User.objects.create_user(username='duplicate-db', email='duplicate@id.test')
            Profile.objects.create(user=user, company=self.company, employee_code='glutape0001')

    def test_prefix_edit_does_not_rewrite_existing_ids(self):
        result = self.create_user('listing@id.test')
        self.client.force_login(self.admin)
        changed = self.client.patch(f'/api/companies/{self.company.pk}/', {'employee_id_prefix': 'NEW'}, content_type='application/json')
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(User.objects.get(pk=result.json()['id']).profile.employee_code, 'GLUTAPE0001')
