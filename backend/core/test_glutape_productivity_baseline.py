import csv
from datetime import datetime, timezone as dt_timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .management.commands.load_glutape_productivity_rules import read_baseline, snapshot
from .models import ActivityLog, AppWebsiteCategory, AuditLog, Company, Department, Profile, WorkSession
from .productivity_policy_checks import verify_glutape_policy


class GlutapeProductivityBaselineTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(pk=1, name='Glutape')
        self.other = Company.objects.create(pk=2, name='Other company')
        self.baseline = read_baseline()
        for raw_id, name in self.baseline['expected_departments'].items():
            Department.objects.create(pk=int(raw_id), name=name, company=self.company)
        self.admin = User.objects.create_user(username='baseline-admin', email='admin@qa.example')
        Profile.objects.create(user=self.admin, role='COMPANY_ADMIN', company=self.company, department_id=6)
        self.session = WorkSession.objects.create(company=self.company, user=self.admin)

    def load(self, **extra):
        output = StringIO()
        call_command('load_glutape_productivity_rules', company_id=1, actor_email=self.admin.email,
                     stdout=output, **extra)
        return output.getvalue()

    def activity(self, **extra):
        values = {'company':self.company, 'user':self.admin, 'session':self.session,
                  'captured_at':datetime(2026,10,16,5,tzinfo=dt_timezone.utc),
                  'productivity':'UNKNOWN','duration_seconds':120,'app_name':'UnknownTool'}
        values.update(extra)
        return ActivityLog.objects.create(**values)

    def seed_previous_baseline(self):
        for row in self.baseline['rules'] + self.baseline['superseded_rules']:
            rule = AppWebsiteCategory.objects.create(company=self.company, department_id=row['department'],
                pattern_type=row['pattern_type'], pattern=row['pattern'], category=row['category'],
                notes=row['notes'], is_active=True)
            AuditLog.objects.create(company=self.company, actor=self.admin,
                object_type='AppWebsiteCategory', object_id=str(rule.pk),
                action_type='PRODUCTIVITY_BASELINE_CREATE',
                after_data={**snapshot(rule), **self.baseline['supersedes']})

    def test_final_policy_has_20_confirmed_rules_and_12_held_confirmations(self):
        self.assertEqual(len(self.baseline['rules']),20)
        self.assertEqual(len(self.baseline['pending_telemetry_rules']),12)
        self.assertEqual({row['pattern_type'] for row in self.baseline['rules']},{'DOMAIN','URL'})
        self.assertFalse(any('*' in row['pattern'] for row in self.baseline['rules']))
        self.assertEqual(sum(row['department'] is None for row in self.baseline['rules']),9)
        self.assertEqual([row['pattern'] for row in self.baseline['rules'] if row['pattern_type']=='URL'],
                         ['boldsoftmations.github.io/crm-frontend/'])
        self.assertEqual(len(self.baseline['superseded_rules']),24)
        pending = {row['tool_name']:row for row in self.baseline['pending_telemetry_rules']}
        self.assertEqual(pending['Microsoft Excel']['category'],'PRODUCTIVE')
        self.assertEqual(pending['Microsoft Word']['category'],'NEUTRAL')
        self.assertEqual(pending['Microsoft PowerPoint']['category'],'NEUTRAL')
        self.assertEqual(pending['SmartOffice']['pattern_types'],['APP','DOMAIN'])
        self.assertEqual(pending['SmartOffice']['department'],5)
        self.assertFalse(any(row['category']=='UNPRODUCTIVE' for row in self.baseline['rules']))

    def test_upgrading_previous_44_rules_deactivates_24_with_audits_and_keeps_history(self):
        self.seed_previous_baseline()
        history=self.activity(productivity='PRODUCTIVE',domain='alibaba.com')
        self.assertIn('20 unchanged, 24 deactivated',self.load(dry_run=True))
        self.assertEqual(AppWebsiteCategory.objects.filter(is_active=True).count(),44)
        self.assertEqual(AuditLog.objects.count(),44)
        self.assertIn('20 unchanged, 24 deactivated',self.load())
        self.assertEqual(AppWebsiteCategory.objects.filter(is_active=True).count(),20)
        self.assertEqual(AppWebsiteCategory.objects.filter(is_active=False).count(),24)
        retired=AuditLog.objects.filter(action_type='PRODUCTIVITY_BASELINE_DEACTIVATE')
        self.assertEqual(retired.count(),24)
        for audit in retired:
            self.assertTrue(audit.before_data['is_active'])
            self.assertFalse(audit.after_data['is_active'])
            self.assertEqual(audit.before_data['category'],audit.after_data['category'])
            self.assertEqual(audit.after_data['baseline_id'],self.baseline['baseline_id'])
        history.refresh_from_db();self.assertEqual(history.productivity,'PRODUCTIVE')
        self.assertIn('20 unchanged, 0 deactivated',self.load())
        self.assertEqual(AuditLog.objects.count(),68)

    def test_manually_changed_previous_rule_requires_review_before_retirement(self):
        self.seed_previous_baseline()
        rule=AppWebsiteCategory.objects.get(company=self.company,department_id=2,pattern='alibaba.com')
        rule.notes='New manual confirmation';rule.save()
        with self.assertRaisesMessage(CommandError,'not an unchanged rule'):
            self.load()
        self.assertEqual(AppWebsiteCategory.objects.filter(is_active=True).count(),44)
        self.assertEqual(AuditLog.objects.count(),44)
        self.load(update_existing=True)
        rule.refresh_from_db();self.assertFalse(rule.is_active)

    def test_later_manual_reactivation_is_not_silently_undone(self):
        self.seed_previous_baseline();self.load()
        rule=AppWebsiteCategory.objects.get(company=self.company,department_id=2,pattern='alibaba.com')
        rule.is_active=True;rule.save()
        AuditLog.objects.create(company=self.company,actor=self.admin,object_type='AppWebsiteCategory',
            object_id=str(rule.pk),action_type='UPDATE',after_data=snapshot(rule))
        before=AuditLog.objects.count()
        with self.assertRaisesMessage(CommandError,'--update-existing'):
            self.load()
        rule.refresh_from_db();self.assertTrue(rule.is_active)
        self.assertEqual(AuditLog.objects.count(),before)

    def test_unowned_retired_pattern_requires_review_and_other_rules_remain_untouched(self):
        row=self.baseline['superseded_rules'][0]
        own=AppWebsiteCategory.objects.create(company=self.company,department_id=row['department'],
            pattern_type=row['pattern_type'],pattern=row['pattern'],category=row['category'])
        foreign=AppWebsiteCategory.objects.create(company=self.other,pattern_type=row['pattern_type'],
            pattern=row['pattern'],category=row['category'])
        custom=AppWebsiteCategory.objects.create(company=self.company,pattern_type='DOMAIN',
            pattern='confirmed-internal.example',category='PRODUCTIVE')
        with self.assertRaisesMessage(CommandError,'--update-existing'):
            self.load()
        own.refresh_from_db();self.assertTrue(own.is_active)
        self.assertIn('1 deactivated',self.load(update_existing=True))
        own.refresh_from_db();self.assertFalse(own.is_active)
        foreign.refresh_from_db();custom.refresh_from_db()
        self.assertTrue(foreign.is_active);self.assertTrue(custom.is_active)

    def test_failed_upgrade_rolls_back_all_retirements_and_audits(self):
        self.seed_previous_baseline()
        AppWebsiteCategory.objects.create(company=self.company,department_id=6,
            pattern_type='DOMAIN',pattern='youtube.com',category='PRODUCTIVE')
        with self.assertRaisesMessage(CommandError,'Policy verification failed'):
            self.load()
        self.assertEqual(AppWebsiteCategory.objects.filter(is_active=True).count(),45)
        self.assertEqual(AuditLog.objects.count(),44)

    def test_dry_run_then_apply_is_audited_and_repeat_safe_without_changing_history(self):
        history=self.activity()
        self.assertIn('20 new',self.load(dry_run=True))
        self.assertFalse(AppWebsiteCategory.objects.exists());self.assertFalse(AuditLog.objects.exists())
        self.assertIn('20 new',self.load())
        self.assertEqual(AppWebsiteCategory.objects.count(),20)
        self.assertFalse(AppWebsiteCategory.objects.filter(pattern_type='APP').exists())
        self.assertEqual(AuditLog.objects.filter(actor=self.admin,company=self.company,
            action_type='PRODUCTIVITY_BASELINE_CREATE').count(),20)
        self.assertIn('20 unchanged',self.load())
        self.assertEqual(AppWebsiteCategory.objects.count(),20);self.assertEqual(AuditLog.objects.count(),20)
        history.refresh_from_db();self.assertEqual(history.productivity,'UNKNOWN')

    def test_conflicting_rule_aborts_until_explicitly_reviewed(self):
        rule=AppWebsiteCategory.objects.create(company=self.company,pattern_type='DOMAIN',
            pattern='linkedin.com',category='UNPRODUCTIVE',notes='Old setting')
        with self.assertRaisesMessage(CommandError,'--update-existing'):self.load()
        self.assertEqual(AppWebsiteCategory.objects.count(),1);self.assertFalse(AuditLog.objects.exists())
        self.assertIn('1 updated',self.load(dry_run=True,update_existing=True))
        rule.refresh_from_db();self.assertEqual(rule.category,'UNPRODUCTIVE')
        self.load(update_existing=True)
        rule.refresh_from_db();self.assertEqual(rule.category,'NEUTRAL')
        audit=AuditLog.objects.get(object_id=str(rule.pk),action_type='PRODUCTIVITY_BASELINE_UPDATE')
        self.assertEqual(audit.before_data['category'],'UNPRODUCTIVE')
        self.assertEqual(audit.after_data['category'],'NEUTRAL')

    def test_matching_existing_rule_preserves_its_custom_notes(self):
        rule=AppWebsiteCategory.objects.create(company=self.company,pattern_type='DOMAIN',
            pattern='mail.google.com',category='PRODUCTIVE',notes='Locally reviewed note')
        self.assertIn('1 unchanged',self.load())
        rule.refresh_from_db();self.assertEqual(rule.notes,'Locally reviewed note')
        self.assertEqual(AuditLog.objects.count(),19)

    def test_wrong_company_actor_department_and_duplicates_are_rejected(self):
        with self.assertRaises(CommandError):
            call_command('load_glutape_productivity_rules',company_id=2,actor_email=self.admin.email,stdout=StringIO())
        for role in ('EMPLOYEE','MANAGER','SALES_ADMIN'):
            self.admin.profile.role=role;self.admin.profile.save()
            with self.assertRaises(CommandError):self.load()
        self.admin.profile.role='COMPANY_ADMIN';self.admin.profile.save()
        Department.objects.filter(pk=9).update(is_active=False)
        with self.assertRaisesMessage(CommandError,'Department 9'):self.load()
        Department.objects.filter(pk=9).update(is_active=True)
        Department.objects.filter(pk=5).update(name='HR')
        for _ in range(2):
            AppWebsiteCategory.objects.create(company=self.company,pattern_type='DOMAIN',pattern='mail.google.com',category='PRODUCTIVE')
        with self.assertRaisesMessage(CommandError,'Duplicate existing'):self.load()
        self.assertEqual(AppWebsiteCategory.objects.count(),2);self.assertFalse(AuditLog.objects.exists())

    def test_broad_productive_browser_and_github_pages_rules_are_flagged(self):
        for kind,pattern in (('APP','chrome.exe'),('APP','edge'),('DOMAIN','boldsoftmations.github.io')):
            rule=AppWebsiteCategory.objects.create(company=self.company,pattern_type=kind,pattern=pattern,category='PRODUCTIVE')
            with self.assertRaisesMessage(CommandError,'broad productive'):self.load()
            rule.delete()
        self.assertFalse(AuditLog.objects.exists())

    def test_audit_write_failure_rolls_back_rules(self):
        with patch('core.management.commands.load_glutape_productivity_rules.AuditLog.objects.create',side_effect=RuntimeError('Audit unavailable')):
            with self.assertRaises(RuntimeError):self.load()
        self.assertFalse(AppWebsiteCategory.objects.exists());self.assertFalse(AuditLog.objects.exists())

    def test_actual_classifier_policy_examples_pass_and_app_cases_remain_pending(self):
        self.load()
        result=verify_glutape_policy(self.company)
        self.assertEqual(result['failed'],0,result['cases']);self.assertEqual(result['passed'],150)
        self.assertEqual(result['pending_rule_count'],12)
        output=StringIO()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'verification.json'
            call_command('verify_glutape_productivity_rules',company_id=1,output=str(path),stdout=output)
            self.assertEqual(json.loads(path.read_text())['failed'],0)
        self.assertIn('150 passed, 0 failed',output.getvalue())

    def test_extra_rule_causing_sample_failure_rolls_back_import(self):
        AppWebsiteCategory.objects.create(company=self.company,department_id=6,
            pattern_type='DOMAIN',pattern='youtube.com',category='PRODUCTIVE')
        with self.assertRaisesMessage(CommandError,'Policy verification failed'):self.load()
        self.assertEqual(AppWebsiteCategory.objects.count(),1);self.assertFalse(AuditLog.objects.exists())

    def test_unknown_exports_use_inclusive_local_dates_and_do_not_write_activity(self):
        self.activity(captured_at=datetime(2026,10,15,18,30,tzinfo=dt_timezone.utc),duration_seconds=60,
            app_name='Tool',domain='unknown.example',url='https://unknown.example/',window_title='=unsafe-title')
        self.activity(app_name='Tool',duration_seconds=120,window_title='Other title')
        self.activity(captured_at=datetime(2026,10,16,18,30,tzinfo=dt_timezone.utc),duration_seconds=999)
        self.activity(productivity='PRODUCTIVE',duration_seconds=300)
        other_user=User.objects.create_user(username='other')
        Profile.objects.create(user=other_user,company=self.other,role='EMPLOYEE')
        other_session=WorkSession.objects.create(user=other_user,company=self.other)
        self.activity(company=self.other,user=other_user,session=other_session,duration_seconds=900)
        before=ActivityLog.objects.count()
        with tempfile.TemporaryDirectory() as directory:
            call_command('export_unknown_productivity',company_id=1,from_date='2026-10-16',to_date='2026-10-16',
                timezone='Asia/Kolkata',output_dir=directory,stdout=StringIO())
            summary=json.loads((Path(directory)/'summary.json').read_text())
            self.assertEqual(summary['unknown_activity_count'],2)
            self.assertEqual(summary['unknown_duration_seconds'],180)
            self.assertEqual(summary['activities_with_url'],1)
            with (Path(directory)/'applications.csv').open(encoding='utf-8-sig',newline='') as file:rows=list(csv.DictReader(file))
            self.assertEqual(rows[0]['app_name'],'Tool');self.assertEqual(rows[0]['total_duration_seconds'],'180')
            self.assertEqual(rows[0]['department_name'],'IT')
            with (Path(directory)/'window_titles.csv').open(encoding='utf-8-sig',newline='') as file:
                titles=[row['window_title'] for row in csv.DictReader(file)]
            self.assertIn("'=unsafe-title",titles)
        self.assertEqual(ActivityLog.objects.count(),before);self.assertFalse(AuditLog.objects.exists())

    def test_unknown_export_invalid_dates_and_foreign_department_labels(self):
        self.activity()
        foreign=Department.objects.create(company=self.other,name='Private other department')
        Profile.objects.filter(user=self.admin).update(department=foreign)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(CommandError):
                call_command('export_unknown_productivity',company_id=1,from_date='2026-10-17',to_date='2026-10-16',output_dir=directory,stdout=StringIO())
            call_command('export_unknown_productivity',company_id=1,from_date='2026-10-16',to_date='2026-10-16',output_dir=directory,stdout=StringIO())
            with (Path(directory)/'applications.csv').open(encoding='utf-8-sig',newline='') as file:rows=list(csv.DictReader(file))
            self.assertEqual(rows[0]['department_name'],'Unassigned')
