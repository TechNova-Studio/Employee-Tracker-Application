import json
from pathlib import Path

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from .activity_context import normalize_web_context
from .models import (ActivityLog, AppWebsiteCategory, Company, Department, Device,
                     PolicyAcceptance, PolicyVersion, Profile, WorkSession)
from .views import classify_activity


class WebContextNormalizationTests(SimpleTestCase):
    def test_actual_url_supplies_a_missing_domain_and_strips_sensitive_parts(self):
        self.assertEqual(normalize_web_context('', 'HTTPS://WEB.WHATSAPP.COM/?token=PRIVATE#PRIVATE'),
                         ('web.whatsapp.com', 'https://web.whatsapp.com/'))

    def test_actual_url_wins_over_a_conflicting_domain(self):
        self.assertEqual(normalize_web_context('web.whatsapp.com', 'https://unclassified.example/path'),
                         ('unclassified.example', 'https://unclassified.example/path'))

    def test_legacy_host_only_values_support_case_port_and_trailing_dot(self):
        self.assertEqual(normalize_web_context(' WEB.WHATSAPP.COM.:443 '), ('web.whatsapp.com', ''))

    def test_invalid_or_non_web_urls_cannot_fall_back_to_a_productive_domain(self):
        for url in ('file:///private.pdf', 'chrome://settings', 'https://user:password@example.com/',
                    'https://bad host/', 'https://example.com:BAD/', 'javascript:PRIVATE', 'https:\\example.com'):
            self.assertEqual(normalize_web_context('web.whatsapp.com', url), ('', ''), url)


class GlutapeTelemetryMatchingTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(pk=1, name='Glutape India Pvt Ltd')
        self.other = Company.objects.create(name='Other company')
        baseline = json.loads((Path(__file__).parent / 'data/glutape_productivity_v1.json').read_text())
        for pk, name in baseline['expected_departments'].items():
            Department.objects.create(pk=int(pk), company=self.company, name=name)
        for row in baseline['rules']:
            AppWebsiteCategory.objects.create(company=self.company, department_id=row['department'],
                pattern_type=row['pattern_type'], pattern=row['pattern'], category=row['category'], notes=row['notes'])
        self.user = User.objects.create_user(username='sales-employee', email='sales@qa.example')
        Profile.objects.create(user=self.user, company=self.company, department_id=4,
                               role='EMPLOYEE', policy_status='ACCEPTED')
        self.device = Device.objects.create(company=self.company, user=self.user, device_id='EMPLOYEE-PC',
                                             platform='windows', app_version='1.0.5')
        policy = PolicyVersion.objects.create(company=self.company, version='1', title='Monitoring', body='Policy')
        PolicyAcceptance.objects.create(company=self.company, user=self.user, device=self.device,
                                         policy=policy, status='ACCEPTED')
        self.session = WorkSession.objects.create(company=self.company, user=self.user, device=self.device)
        self.client = APIClient(); self.client.force_authenticate(user=self.user)

    def classify(self, department=4, **extra):
        self.user.profile.department_id = department
        values = {'app_name': 'Google Chrome', 'domain': '', 'title': '(159) WhatsApp Business - Google Chrome', 'url': ''}
        values.update(extra)
        return classify_activity(self.company, self.user, **values)

    def upload(self, rows):
        return self.client.post('/api/agent/activity/batch/', {'session_id': self.session.pk,
            'device_id': self.device.device_id, 'app_version': '1.0.5', 'platform': 'windows',
            'activities': rows}, format='json')

    def test_actual_whatsapp_url_resolves_every_approved_department_override(self):
        for department in range(1, 10):
            expected = 'PRODUCTIVE' if department in (1, 2, 4, 5, 9) else 'NEUTRAL'
            self.assertEqual(self.classify(department, url='https://web.whatsapp.com/'), expected)

    def test_title_without_actual_browser_address_is_not_used_to_fabricate_a_domain(self):
        for title in ('WhatsApp - Google Chrome', '(102) WhatsApp - Google Chrome',
                      '(4) WhatsApp Business - Google Chrome', 'web.whatsapp.com - Google Chrome'):
            self.assertEqual(self.classify(title=title), 'UNKNOWN')
        self.assertEqual(self.classify(app_name='LockApp.exe', title='Windows Default Lock Screen'), 'UNKNOWN')

    def test_gmail_and_crm_match_even_when_old_client_omits_the_domain(self):
        for url in ('https://mail.google.com/mail/u/0/#inbox',
                    'https://boldsoftmations.github.io/crm-frontend/',
                    'https://boldsoftmations.github.io/crm-frontend/#/sales'):
            self.assertEqual(self.classify(url=url), 'PRODUCTIVE')

    def test_shared_pages_and_similar_domains_do_not_inherit_crm_productivity(self):
        for url in ('https://boldsoftmations.github.io/other-project/',
                    'https://evil.example/boldsoftmations.github.io/crm-frontend/',
                    'https://evil.example/?next=https://boldsoftmations.github.io/crm-frontend/',
                    'https://boldsoftmations.github.io.evil.example/crm-frontend/',
                    'https://web.whatsapp.com.evil.example/'):
            self.assertEqual(self.classify(domain='web.whatsapp.com', url=url), 'UNKNOWN', url)

    def test_company_defaults_missing_department_and_other_overrides_remain_correct(self):
        self.assertEqual(self.classify(None, url='https://web.whatsapp.com/'), 'NEUTRAL')
        self.assertEqual(self.classify(5, url='https://www.linkedin.com/feed/'), 'PRODUCTIVE')
        self.assertEqual(self.classify(3, url='https://www.linkedin.com/feed/'), 'NEUTRAL')
        self.assertEqual(self.classify(6, url='https://chatgpt.com/'), 'PRODUCTIVE')
        self.assertEqual(self.classify(4, url='https://chatgpt.com/'), 'NEUTRAL')
        self.assertEqual(classify_activity(self.other, self.user, 'Chrome', '', '', 'https://web.whatsapp.com/'), 'UNKNOWN')

    def test_query_specific_url_rule_cannot_match_when_its_private_input_is_not_retained(self):
        AppWebsiteCategory.objects.create(company=self.company, pattern_type='URL',
            pattern='https://unclassified.example/?secret=yes', category='PRODUCTIVE')
        self.assertEqual(self.classify(url='https://unclassified.example/?secret=no'), 'UNKNOWN')

    def test_ingestion_stores_and_classifies_the_same_normalized_url_and_keeps_counts(self):
        response = self.upload([{'app_name': 'Google Chrome', 'domain': '',
            'window_title': '(4) WhatsApp Business - Google Chrome', 'url': 'https://WEB.WHATSAPP.COM/?token=PRIVATE#PRIVATE',
            'duration_seconds': 60, 'keyboard_count': 42, 'mouse_count': 12}])
        self.assertEqual(response.status_code, 200, response.content)
        row = response.json()['items'][0]
        self.assertEqual((row['domain'], row['url'], row['productivity']),
                         ('web.whatsapp.com', 'https://web.whatsapp.com/', 'PRODUCTIVE'))
        self.assertEqual((row['keyboard_count'], row['mouse_count']), (42, 12))
        self.assertNotIn('PRIVATE', response.content.decode())
        saved = ActivityLog.objects.get(pk=row['id'])
        self.assertEqual(saved.domain, 'web.whatsapp.com'); self.assertNotIn('PRIVATE', saved.url)

    def test_title_only_old_agents_are_accepted_and_history_is_not_reclassified(self):
        old = self.upload([{'app_name': 'Google Chrome', 'window_title': 'WhatsApp - Google Chrome',
                            'duration_seconds': 60}]).json()['items'][0]
        self.assertEqual(old['productivity'], 'UNKNOWN')
        new = self.upload([{'app_name': 'Google Chrome', 'url': 'https://web.whatsapp.com/',
                            'duration_seconds': 60}]).json()['items'][0]
        self.assertEqual(new['productivity'], 'PRODUCTIVE')
        self.assertEqual(ActivityLog.objects.get(pk=old['id']).productivity, 'UNKNOWN')

    def test_batch_text_validation_occurs_before_any_activity_is_saved(self):
        for invalid in ({'domain': ['web.whatsapp.com']}, {'url': {'private': 'value'}}, {'app_name': 'x' * 256}):
            response = self.upload([{'url': 'https://web.whatsapp.com/'}, invalid])
            self.assertEqual(response.status_code, 400, response.content)
            self.assertEqual(ActivityLog.objects.count(), 0)

    def test_rules_and_exact_app_confirmations_are_not_silently_added(self):
        self.assertEqual(AppWebsiteCategory.objects.count(), 20)
        for name in ('EXCEL.EXE', 'Microsoft Excel', 'Code.exe', 'Visual Studio Code', 'Tally.exe'):
            self.assertEqual(self.classify(app_name=name, title='Work'), 'UNKNOWN')
        self.assertFalse(AppWebsiteCategory.objects.filter(pattern_type='APP').exists())
