"""Read-only examples for the approved Glutape policy, using the real classifier."""
import json
from pathlib import Path

from django.contrib.auth.models import User

from .models import Department, Profile
from .views import classify_activity


def verify_glutape_policy(company):
    departments = {department.pk: department for department in Department.objects.filter(company=company)}
    cases = []

    def check(department_id, label, expected, app='Google Chrome', domain='', url='', title=''):
        department = departments.get(department_id)
        if not department:
            cases.append({'department_id': department_id, 'label': label, 'expected': expected,
                          'actual': 'MISSING_DEPARTMENT', 'passed': False})
            return
        # Unsaved stand-ins exercise classification without creating employees or activity.
        user = User(username='policy-check')
        Profile(user=user, company=company, department=department, role='EMPLOYEE')
        actual = classify_activity(company, user, app, domain, title, url)
        cases.append({'department_id': department_id, 'department_name': department.name,
                      'label': label, 'expected': expected, 'actual': actual, 'passed': actual == expected})

    for department_id in range(1, 10):
        check(department_id, 'Live CRM SPA route', 'PRODUCTIVE', domain='boldsoftmations.github.io',
              url='https://boldsoftmations.github.io/crm-frontend/invoice/example')
        check(department_id, 'Other GitHub Pages project', 'UNKNOWN', domain='boldsoftmations.github.io',
              url='https://boldsoftmations.github.io/unclassified-project/')
        check(department_id, 'Google search', 'NEUTRAL', domain='google.com')
        check(department_id, 'Gmail overrides broad Google neutral rule', 'PRODUCTIVE', domain='mail.google.com')
        check(department_id, 'YouTube initially neutral', 'NEUTRAL', domain='youtube.com')
        for domain in ('calendar.google.com', 'meet.google.com'):
            check(department_id, domain + ' inherits Google neutral default', 'NEUTRAL', domain=domain)
        for domain in ('netflix.com', 'jiohotstar.com', 'primevideo.com', 'steampowered.com'):
            check(department_id, domain + ' not confirmed in final baseline', 'UNKNOWN', domain=domain)
        for app in ('Google Chrome', 'Microsoft Edge'):
            check(department_id, app + ' with unclassified website', 'UNKNOWN', app=app,
                  domain='unclassified.example', url='https://unclassified.example/')
    for department_id, expected in ((4, 'NEUTRAL'), (5, 'PRODUCTIVE'), (3, 'NEUTRAL')):
        check(department_id, 'LinkedIn department override', expected, domain='linkedin.com')
    for department_id, expected in ((6, 'PRODUCTIVE'), (4, 'NEUTRAL')):
        check(department_id, 'ChatGPT department override', expected, domain='chatgpt.com')
    for department_id in (1, 2, 4, 5, 9):
        check(department_id, 'Operational WhatsApp Web', 'PRODUCTIVE', domain='web.whatsapp.com')
    check(3, 'Accounts WhatsApp Web initially neutral', 'NEUTRAL', domain='web.whatsapp.com')
    check(6, 'IT repository work', 'PRODUCTIVE', domain='github.com')
    for domain in ('naukri.com', 'indeed.com', 'ncs.gov.in'):
        check(5, 'Confirmed HR recruitment portal', 'PRODUCTIVE', domain=domain)
    for department_id, domains in (
        (2, ('alibaba.com', 'made-in-china.com', 'globalsources.com', 'icegate.gov.in')),
        (3, ('gst.gov.in', 'ewaybillgst.gov.in', 'incometax.gov.in', 'icegate.gov.in')),
        (4, ('indiamart.com', 'tradeindia.com', 'justdial.com')),
        (6, ('stackoverflow.com', 'platform.openai.com', 'developer.mozilla.org',
             'docs.python.org', 'heroku.com', 'console.aws.amazon.com')),
    ):
        for domain in domains:
            check(department_id, domain + ' awaits actual Glutape usage confirmation', 'UNKNOWN', domain=domain)
    check(3, 'Unclassified application', 'UNKNOWN', app='UnclassifiedApp', title='Unclassified work')
    data_path = Path(__file__).resolve().parent / 'data' / 'glutape_productivity_v1.json'
    pending = json.loads(data_path.read_text(encoding='utf-8'))['pending_telemetry_rules']
    return {'company_id': company.pk, 'passed': sum(case['passed'] for case in cases),
            'failed': sum(not case['passed'] for case in cases), 'cases': cases,
            'pending_rule_count': len(pending), 'pending_telemetry_rules': pending,
            'verification_basis': 'Synthetic activity inputs against saved rules; does not prove desktop URL capture.',
            'pending_examples': ['Excel/Word/PowerPoint exact APP names', 'Accounts Tally APP classification',
                                 'HR SmartOffice APP/domain classification', 'Store/Factory OS-BOOKS APP classification',
                                 'IT native tool APP classifications']}
