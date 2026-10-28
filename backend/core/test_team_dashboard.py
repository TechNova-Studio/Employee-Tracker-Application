import csv
from datetime import datetime, timedelta, timezone as utc
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from .models import ActivityLog, AuditLog, Company, Department, ERPConnector, ERPEmployeeMapping, Heartbeat, Profile, WorkSession


class TeamDashboardTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 16, 7, 0, tzinfo=utc.utc)
        self.company = Company.objects.create(name='Glutape')
        self.other = Company.objects.create(name='Private other company')
        self.sales = Department.objects.create(company=self.company, name='Sales')
        self.it = Department.objects.create(company=self.company, name='IT')
        self.foreign_department = Department.objects.create(company=self.other, name='Private foreign department')
        self.admin = self.user('admin', role='COMPANY_ADMIN')
        self.manager = self.user('manager', role='MANAGER')
        self.alice = self.user('alice', department=self.sales, manager=self.manager)
        self.bob = self.user('bob', department=self.it)
        self.inactive = self.user('inactive', active=False)
        self.foreign = self.user('foreign', company=self.other, department=self.foreign_department)
        self.session = WorkSession.objects.create(company=self.company, user=self.alice, started_at=self.now-timedelta(hours=1))
        self.client = APIClient()

    def user(self, name, role='EMPLOYEE', company=None, department=None, manager=None, active=True):
        user = User.objects.create_user(username=name, email=name+'@qa.example', first_name=name.title(), is_active=active)
        Profile.objects.create(user=user, company=company or self.company, role=role, department=department,
                               manager=manager, is_active_employee=active)
        return user

    def get(self, user=None, **query):
        self.client.force_authenticate(user=user or self.admin)
        with patch('core.dashboard_api.timezone.now', return_value=self.now):
            return self.client.get('/api/reports/team-dashboard/', {'from_date':'2026-10-16','to_date':'2026-10-16', **query})

    def activity(self, user=None, **extra):
        user = user or self.alice
        values = {'company':self.company,'user':user,'session':self.session,'app_name':'Work tool',
                  'captured_at':self.now,'duration_seconds':600,'productivity':'PRODUCTIVE'}
        values.update(extra)
        return ActivityLog.objects.create(**values)

    def heartbeat(self, **extra):
        values = {'company':self.company,'user':self.alice,'session':self.session,'captured_at':self.now,
                  'active_seconds':1200,'idle_seconds':300,'is_idle':False}
        values.update(extra)
        return Heartbeat.objects.create(**values)

    def test_company_admin_sees_entire_own_roster_including_inactive(self):
        self.activity();self.activity(user=self.foreign,company=self.other)
        response = self.get()
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Cache-Control'],'private, no-store')
        body = response.json()
        self.assertEqual(body['company']['name'],'Glutape')
        self.assertEqual(body['summary']['total_employees'],5)
        self.assertEqual(body['summary']['inactive_employees'],1)
        self.assertEqual(body['summary']['productive_seconds'],600)
        self.assertNotIn('Private other',response.content.decode())
        self.assertNotIn('foreign@',response.content.decode())
        self.assertEqual(body['scope'],'OWN_COMPANY')

    def test_authentication_and_workforce_role_permissions(self):
        response=self.client.get('/api/reports/team-dashboard/')
        self.assertIn(response.status_code,(401,403))
        sales_admin=self.user('sales-admin',role='SALES_ADMIN')
        self.assertEqual(self.get(sales_admin).status_code,403)
        hr=self.user('hr',role='HR_ADMIN')
        self.assertEqual(self.get(hr).status_code,200)

    def test_company_parameter_cannot_escape_scope(self):
        self.assertEqual(self.get(company_id=self.other.pk).status_code,403)
        self.assertEqual(self.get(department_id=self.foreign_department.pk).status_code,403)
        self.assertEqual(self.get(employee_id=self.foreign.pk).status_code,403)

    def test_super_admin_selects_company_without_initial_cross_company_metrics(self):
        user=self.user('super',role='SUPER_ADMIN')
        response=self.get(user).json()
        self.assertTrue(response['requires_company'])
        self.assertNotIn('summary',response)
        self.assertEqual(len(response['options']['companies']),2)
        response=self.get(user,company_id=self.other.pk).json()
        self.assertEqual(response['company']['id'],self.other.pk)
        self.assertEqual(response['employees']['count'],1)

    def test_manager_and_employee_cannot_view_other_users(self):
        response=self.get(self.manager).json()
        self.assertEqual([row['id'] for row in response['employees']['results']],[self.alice.pk])
        self.assertEqual(self.get(self.manager,employee_id=self.bob.pk).status_code,403)
        response=self.get(self.bob).json()
        self.assertEqual([row['id'] for row in response['employees']['results']],[self.bob.pk])
        self.assertEqual(response['scope'],'OWN_USER')

    def test_heartbeat_work_and_application_usage_are_separate_with_unknown_excluded_from_share(self):
        self.heartbeat()
        self.activity(duration_seconds=600)
        self.activity(duration_seconds=300,productivity='NEUTRAL')
        self.activity(duration_seconds=300,productivity='UNPRODUCTIVE')
        self.activity(duration_seconds=600,productivity='UNKNOWN')
        body=self.get().json();summary=body['summary']
        self.assertEqual(summary['work_seconds'],1500)
        self.assertEqual(summary['activity_seconds'],1800)
        self.assertEqual(summary['productive_share_pct'],50)
        self.assertEqual(summary['classification_coverage_pct'],66.7)
        self.assertEqual(summary['unknown_seconds'],600)
        self.assertEqual(summary['unproductive_seconds'],300)

    def test_no_activity_and_unknown_only_are_not_ranked_as_low_productivity(self):
        self.activity(user=self.bob,productivity='UNKNOWN')
        body=self.get().json()
        self.assertEqual(body['leaders'],[]);self.assertEqual(body['review'],[])
        row=next(row for row in body['employees']['results'] if row['id']==self.bob.pk)
        self.assertIsNone(row['productive_share_pct'])
        self.assertEqual(row['classification_coverage_pct'],0)
        self.assertEqual(body['summary']['no_activity_employees'],4)

    def test_date_range_uses_heartbeats_even_when_session_started_before_the_range(self):
        self.session.started_at=self.now-timedelta(days=2);self.session.save()
        self.heartbeat()
        body=self.get().json()
        self.assertEqual(body['summary']['work_seconds'],1500)
        self.assertEqual(body['summary']['sessions'],0)

    def test_current_status_requires_recent_heartbeat_running_session_and_active_employee(self):
        self.heartbeat(is_idle=True)
        body=self.get().json()
        self.assertEqual(next(row for row in body['employees']['results'] if row['id']==self.alice.pk)['live_status'],'idle')
        self.assertEqual(body['summary']['online_employees'],1)
        self.session.status='STOPPED';self.session.save()
        self.assertEqual(self.get().json()['summary']['online_employees'],0)
        self.session.status='RUNNING';self.session.save()
        Heartbeat.objects.update(captured_at=self.now-timedelta(minutes=4))
        self.assertEqual(self.get().json()['summary']['online_employees'],0)

    def test_kolkata_date_boundaries_and_hourly_trend(self):
        self.activity(captured_at=datetime(2026,10,15,18,30,tzinfo=utc.utc),duration_seconds=10)
        self.activity(captured_at=datetime(2026,10,16,18,30,tzinfo=utc.utc),duration_seconds=999)
        body=self.get().json()
        self.assertEqual(body['summary']['productive_seconds'],10)
        self.assertEqual(body['trend_granularity'],'hour')
        self.assertEqual(len(body['trend']),24)
        self.assertEqual(body['trend'][0]['productive_seconds'],10)

    def test_multi_day_trend_includes_zero_days_and_rejects_invalid_ranges(self):
        self.activity()
        body=self.get(from_date='2026-10-14').json()
        self.assertEqual(body['trend_granularity'],'day')
        self.assertEqual(len(body['trend']),3)
        self.assertEqual(body['trend'][0]['activity_seconds'],0)
        for query in ({'from_date':'bad'},{'from_date':'2026-10-17'}, {'from_date':'2026-01-01'}, {'page_size':101}, {'sort':'password'}):
            self.assertEqual(self.get(**query).status_code,400)

    def test_pagination_search_and_sort_include_employees_beyond_first_50(self):
        for index in range(55):self.user(f'additional-{index:02d}',department=self.sales)
        body=self.get(page=3,page_size=20,sort='name_asc').json()
        self.assertEqual(body['summary']['total_employees'],60)
        self.assertEqual(body['employees']['count'],60)
        self.assertEqual(len(body['employees']['results']),20)
        body=self.get(search='additional-54').json()
        self.assertEqual(body['employees']['count'],1)
        self.assertEqual(body['summary']['total_employees'],60)
        self.assertEqual(self.get(employment='inactive').json()['summary']['total_employees'],1)

    def test_foreign_department_reference_is_labelled_unassigned(self):
        Profile.objects.filter(user=self.bob).update(department=self.foreign_department)
        body=self.get(department_id='unassigned').json()
        row=next(row for row in body['employees']['results'] if row['id']==self.bob.pk)
        self.assertEqual(row['department_name'],'Unassigned')
        self.assertNotIn('Private foreign department',str(body))

    def test_csv_includes_all_filtered_rows_and_escapes_formulas(self):
        self.alice.first_name='=FORMULA';self.alice.save()
        response=self.get(export='csv',page_size=1)
        self.assertEqual(response['Content-Type'],'text/csv; charset=utf-8')
        rows=list(csv.DictReader(StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows),5)
        self.assertTrue(any(row['name']=="'=FORMULA" for row in rows))
        self.assertNotIn('foreign@',response.content.decode())

    def test_stored_history_is_not_reclassified_or_changed_by_dashboard(self):
        history=self.activity(productivity='UNKNOWN')
        before=(ActivityLog.objects.count(),AuditLog.objects.count())
        self.get();self.get(export='csv')
        history.refresh_from_db();self.assertEqual(history.productivity,'UNKNOWN')
        self.assertEqual((ActivityLog.objects.count(),AuditLog.objects.count()),before)
        self.assertEqual(self.client.post('/api/reports/team-dashboard/',{}).status_code,405)

    def test_mapping_fallback_only_uses_selected_company_connectors(self):
        connector=ERPConnector.objects.create(company=self.company,name='Own connector',api_token='qa-own-not-real')
        foreign=ERPConnector.objects.create(company=self.other,name='Other connector',api_token='qa-other-not-real')
        ERPEmployeeMapping.objects.create(connector=connector,user=self.alice,external_id='GLUTAPE0079')
        ERPEmployeeMapping.objects.create(connector=foreign,user=self.bob,external_id='PRIVATE-CODE')
        body=self.get().json()
        alice=next(row for row in body['employees']['results'] if row['id']==self.alice.pk)
        bob=next(row for row in body['employees']['results'] if row['id']==self.bob.pk)
        self.assertEqual(alice['employee_code'],'GLUTAPE0079');self.assertEqual(bob['employee_code'],'')

    def test_query_count_does_not_grow_per_employee(self):
        for index in range(25):self.user(f'bulk-{index}')
        with CaptureQueriesContext(connection) as queries:
            response=self.get(page_size=100)
        self.assertEqual(response.status_code,200)
        self.assertLess(len(queries),22)
