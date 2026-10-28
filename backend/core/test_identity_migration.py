from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class EmployeeIdentityMigrationTest(TransactionTestCase):
    previous = [('core', '0003_billinginvoice_billing_cycle_and_more')]
    current = [('core', '0004_company_employee_identity')]

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def setUp(self):
        self.old_apps = self.migrate(self.previous)

    def tearDown(self):
        self.migrate([('core', '0005_explicit_erp_employee_mapping')])
        super().tearDown()

    def test_legacy_mapping_is_archived_and_reversible(self):
        Company = self.old_apps.get_model('core', 'Company')
        User = self.old_apps.get_model('auth', 'User')
        Connector = self.old_apps.get_model('core', 'ERPConnector')
        Mapping = self.old_apps.get_model('core', 'ERPEmployeeMapping')
        company = Company.objects.create(name='Legacy')
        user = User.objects.create(username='legacy', email='legacy@id.test')
        connector = Connector.objects.create(company=company, api_token='legacy-token')
        mapping = Mapping.objects.create(connector=connector, user=user, external_id='old-source-123')
        apps = self.migrate(self.current)
        log = apps.get_model('core', 'AuditLog').objects.get(action_type='ARCHIVE_LEGACY_ERP_MAPPING')
        self.assertEqual(log.before_data['external_id'], 'old-source-123')
        self.assertEqual(log.before_data['user_id'], user.pk)
        self.assertNotIn('core_erpemployeemapping', connection.introspection.table_names())
        restored_apps = self.migrate(self.previous)
        restored = restored_apps.get_model('core', 'ERPEmployeeMapping').objects.get(pk=mapping.pk)
        self.assertEqual(restored.external_id, 'old-source-123')
        self.assertEqual(restored.user_id, user.pk)

    def test_duplicate_company_employee_ids_block_migration(self):
        Company = self.old_apps.get_model('core', 'Company')
        User = self.old_apps.get_model('auth', 'User')
        Profile = self.old_apps.get_model('core', 'Profile')
        company = Company.objects.create(name='Duplicates')
        first = User.objects.create(username='first')
        second = User.objects.create(username='second')
        Profile.objects.create(company=company, user=first, employee_code='GLUTAPE0001')
        duplicate = Profile.objects.create(company=company, user=second, employee_code='glutape0001')
        try:
            with self.assertRaisesRegex(RuntimeError, 'Resolve duplicate employee IDs'):
                self.migrate(self.current)
        finally:
            Profile.objects.filter(pk=duplicate.pk).update(employee_code='GLUTAPE0002')
