from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ExplicitERPMappingMigrationTest(TransactionTestCase):
    old = [('core', '0003_billinginvoice_billing_cycle_and_more')]
    latest = [('core', '0005_explicit_erp_employee_mapping')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        self.migrate(self.latest)
        super().tearDown()

    def test_existing_mapping_and_timestamps_survive_upgrade_from_old_backend(self):
        apps = self.migrate(self.old)
        company = apps.get_model('core', 'Company').objects.create(name='Legacy CRM')
        user = apps.get_model('auth', 'User').objects.create(username='legacy-mapping')
        apps.get_model('core', 'Profile').objects.create(user_id=user.pk, company_id=company.pk)
        connector = apps.get_model('core', 'ERPConnector').objects.create(company_id=company.pk, api_token='legacy-mapping-token')
        mapping = apps.get_model('core', 'ERPEmployeeMapping').objects.create(connector_id=connector.pk, user_id=user.pk, external_id='21')
        latest = self.migrate(self.latest)
        restored = latest.get_model('core', 'ERPEmployeeMapping').objects.get(pk=mapping.pk)
        self.assertEqual(restored.external_id, '21')
        self.assertEqual(restored.user_id, user.pk)
        self.assertEqual(restored.connector_id, connector.pk)
        self.assertEqual(restored.created_at, mapping.created_at)
        self.assertTrue(latest.get_model('core', 'AuditLog').objects.filter(action_type='ARCHIVE_LEGACY_ERP_MAPPING').exists())
        second = latest.get_model('auth', 'User').objects.create(username='new-mapping')
        added = latest.get_model('core', 'ERPEmployeeMapping').objects.create(connector_id=connector.pk, user_id=second.pk, external_id='34')
        self.assertGreater(added.pk, restored.pk)

    def test_restore_when_identity_migration_was_already_applied(self):
        apps = self.migrate(self.old)
        company = apps.get_model('core', 'Company').objects.create(name='Already upgraded')
        user = apps.get_model('auth', 'User').objects.create(username='archived-mapping')
        connector = apps.get_model('core', 'ERPConnector').objects.create(company_id=company.pk, api_token='archived-mapping-token')
        row = apps.get_model('core', 'ERPEmployeeMapping').objects.create(connector_id=connector.pk, user_id=user.pk, external_id='21')
        self.migrate([('core', '0004_company_employee_identity')])
        self.assertNotIn('core_erpemployeemapping', connection.introspection.table_names())
        latest = self.migrate(self.latest)
        self.assertEqual(latest.get_model('core', 'ERPEmployeeMapping').objects.get(pk=row.pk).user_id, user.pk)
