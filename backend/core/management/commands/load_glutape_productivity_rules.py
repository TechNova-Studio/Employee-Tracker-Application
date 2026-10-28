"""Load the final Glutape policy and retire rules from the superseded baseline."""
import hashlib
import json
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import AppWebsiteCategory, AuditLog, Company, Department
from core.productivity_policy_checks import verify_glutape_policy


BASELINE_PATH = Path(__file__).resolve().parents[2] / 'data' / 'glutape_productivity_v1.json'


def read_baseline():
    with BASELINE_PATH.open(encoding='utf-8') as source:
        baseline = json.load(source)
    rows = baseline['rules']
    identities = set()
    for row in rows:
        identity = (row['department'], row['pattern_type'], row['pattern'].casefold())
        if (row['company'] != baseline['company_id'] or row['pattern_type'] not in ('DOMAIN', 'URL')
                or row['category'] not in dict(AppWebsiteCategory.PRODUCTIVITY_CHOICES)
                or not row['pattern'].strip() or '*' in row['pattern'] or identity in identities):
            raise CommandError('The approved baseline contains an invalid or duplicate rule.')
        identities.add(identity)
    for row in baseline['superseded_rules']:
        identity = (row['department'], row['pattern_type'], row['pattern'].casefold())
        if row['company'] != baseline['company_id'] or identity in identities:
            raise CommandError('The final and superseded rule identities must be distinct.')
        identities.add(identity)
    if (len(rows) != 20 or len(baseline['pending_telemetry_rules']) != 12
            or len(baseline['superseded_rules']) != 24):
        raise CommandError('The final policy must contain 20 confirmed rules, 12 pending confirmations and 24 superseded rules.')
    fingerprint = {key: baseline[key] for key in
                   ('baseline_id', 'rules', 'pending_telemetry_rules', 'superseded_rules')}
    actual_hash = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, ensure_ascii=False,
                                           separators=(',', ':')).encode()).hexdigest()
    if actual_hash != baseline['policy_sha256']:
        raise CommandError('The bundled policy fingerprint does not match its contents.')
    return baseline


def snapshot(rule):
    return {field: getattr(rule, field) for field in ('company_id', 'department_id',
        'pattern_type', 'pattern', 'category', 'notes', 'is_active')}


def validate_target(baseline, company, actor):
    if baseline['company_name_contains'] not in company.name.casefold():
        raise CommandError('Company ID 1 is not named Glutape in this database. Check the target environment.')
    profile = getattr(actor, 'profile', None)
    if not actor.is_active or not profile or not profile.is_active_employee or profile.role not in ('SUPER_ADMIN', 'COMPANY_ADMIN', 'HR_ADMIN'):
        raise CommandError('The audit actor must be an active WorkPulse Super Admin, Company Admin or HR Admin.')
    if profile.role != 'SUPER_ADMIN' and profile.company_id != company.pk:
        raise CommandError('The audit actor does not belong to the target company.')
    actual = {department.pk: department for department in Department.objects.filter(company=company)}
    errors = []
    for raw_id, expected in baseline['expected_departments'].items():
        department = actual.get(int(raw_id))
        if not department or department.name.strip().casefold() != expected.casefold() or not department.is_active:
            errors.append(f'Department {raw_id} must be active, belong to Glutape and be named {expected}.')
    if errors:
        raise CommandError('\n'.join(errors))


def unchanged_previous_baseline_rule(baseline, company, rule):
    """Only automatically retire an unchanged rule owned by the previous import."""
    latest = AuditLog.objects.filter(company=company, object_type='AppWebsiteCategory',
                                    object_id=str(rule.pk)).order_by('-id').first()
    if not latest or latest.action_type not in ('PRODUCTIVITY_BASELINE_CREATE', 'PRODUCTIVITY_BASELINE_UPDATE'):
        return False
    after = latest.after_data
    previous = baseline['supersedes']
    return (isinstance(after, dict) and after.get('baseline_id') == previous['baseline_id']
            and after.get('source_sha256') == previous['source_sha256']
            and all(after.get(field) == value for field, value in snapshot(rule).items()))


def import_plan(baseline, company, update_existing, lock=False):
    plan = []
    errors = []
    for row in baseline['rules']:
        matching = AppWebsiteCategory.objects.filter(company=company, department_id=row['department'],
            pattern_type__iexact=row['pattern_type'], pattern__iexact=row['pattern'])
        matches = list(matching.select_for_update() if lock else matching)
        if len(matches) > 1:
            errors.append(f"Duplicate existing rules for {row['pattern']} / department {row['department']}.")
            continue
        existing = matches[0] if matches else None
        action = 'create'
        if existing:
            if existing.category == row['category'] and existing.is_active:
                action = 'unchanged'
            elif update_existing:
                action = 'update'
            else:
                errors.append(f"Rule #{existing.pk} ({row['pattern']}) differs from the approved category/status. "
                              'Review it and use --update-existing to apply the approved values.')
                continue
        plan.append((action, row, existing))
    for row in baseline['superseded_rules']:
        matching = AppWebsiteCategory.objects.filter(company=company, department_id=row['department'],
            pattern_type__iexact=row['pattern_type'], pattern__iexact=row['pattern'])
        matches = list(matching.select_for_update() if lock else matching)
        if len(matches) > 1:
            errors.append(f"Duplicate superseded rules for {row['pattern']} / department {row['department']}.")
            continue
        if not matches or not matches[0].is_active:
            continue
        rule = matches[0]
        if not update_existing and not unchanged_previous_baseline_rule(baseline, company, rule):
            errors.append(f'Rule #{rule.pk} ({rule.pattern}) is superseded by the final policy, but it is not '
                          'an unchanged rule from the previous import. Review it and use --update-existing '
                          'if it should be deactivated.')
            continue
        plan.append(('deactivate', row, rule))
    # Browser APP rules could otherwise label an unclassified website as productive.
    browser_names = ('chrome', 'chrome.exe', 'google chrome', 'msedge', 'msedge.exe', 'microsoft edge',
                     'firefox', 'firefox.exe', 'mozilla firefox', 'brave', 'brave.exe', 'opera', 'opera.exe', 'safari')
    broad = AppWebsiteCategory.objects.filter(company=company, is_active=True, category='PRODUCTIVE')
    for rule in broad:
        kind = rule.pattern_type.upper()
        pattern = rule.pattern.strip().casefold()
        if (kind == 'APP' and pattern and any(pattern in name for name in browser_names)
                or kind == 'DOMAIN' and (pattern == 'boldsoftmations.github.io'
                    or 'boldsoftmations.github.io'.endswith('.' + pattern))):
            errors.append(f'Existing rule #{rule.pk} is a broad productive browser/GitHub Pages rule. '
                          'Review and deactivate it before loading this baseline.')
    if errors:
        raise CommandError('No rules were saved:\n' + '\n'.join(errors))
    return plan


class Command(BaseCommand):
    help = 'Validate/load the final Glutape V1 policy and audit retirement of superseded rules.'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int, required=True)
        parser.add_argument('--actor-email', required=True)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--update-existing', action='store_true')

    def handle(self, *args, **options):
        baseline = read_baseline()
        if options['company_id'] != baseline['company_id']:
            raise CommandError('This approved baseline is for WorkPulse company ID 1 only.')
        actors = list(User.objects.select_related('profile').filter(email__iexact=options['actor_email'].strip())[:2])
        if len(actors) != 1:
            raise CommandError('Provide the email of exactly one existing WorkPulse admin as the audit actor.')
        actor = actors[0]
        with transaction.atomic():
            companies = Company.objects.filter(pk=options['company_id'])
            if not options['dry_run']:
                companies = companies.select_for_update()
            company = companies.first()
            if not company:
                raise CommandError('Target company does not exist in this database.')
            validate_target(baseline, company, actor)
            plan = import_plan(baseline, company, options['update_existing'], lock=not options['dry_run'])
            counts = {key: sum(action == key for action, _, _ in plan)
                      for key in ('create', 'update', 'unchanged', 'deactivate')}
            if not options['dry_run']:
                for action, row, existing in plan:
                    if action == 'unchanged':
                        continue
                    before = snapshot(existing) if existing else {}
                    if action == 'create':
                        rule = AppWebsiteCategory.objects.create(company=company, department_id=row['department'],
                            pattern_type=row['pattern_type'], pattern=row['pattern'], category=row['category'],
                            notes=row['notes'], is_active=True)
                    elif action == 'update':
                        rule = existing
                        rule.category, rule.is_active, rule.notes = row['category'], True, row['notes']
                        rule.save(update_fields=['category', 'is_active', 'notes', 'updated_at'])
                    else:
                        rule = existing
                        rule.is_active = False
                        rule.save(update_fields=['is_active', 'updated_at'])
                    AuditLog.objects.create(company=company, actor=actor,
                        action_type='PRODUCTIVITY_BASELINE_' + action.upper(), object_type='AppWebsiteCategory',
                        object_id=str(rule.pk), before_data=before,
                        after_data={**snapshot(rule), 'baseline_id': baseline['baseline_id'],
                                    'policy_sha256': baseline['policy_sha256'],
                                    **({'reason': 'Removed by the final Glutape V1 approval; await telemetry confirmation.'}
                                       if action == 'deactivate' else {})})
                verification = verify_glutape_policy(company)
                if verification['failed']:
                    failures = '\n'.join(f"{case['label']}: expected {case['expected']}, got {case['actual']}"
                                         for case in verification['cases'] if not case['passed'])
                    raise CommandError('Policy verification failed; the import was rolled back:\n' + failures)
        prefix = 'Validated; no changes saved' if options['dry_run'] else 'Saved'
        self.stdout.write(self.style.SUCCESS(f"{prefix}: {counts['create']} new, {counts['update']} updated, "
                                            f"{counts['unchanged']} unchanged, {counts['deactivate']} deactivated. "
                                            '12 APP/DOMAIN rules remain pending telemetry confirmation.'))
        for action, row, existing in plan:
            if action == 'deactivate':
                self.stdout.write(f"DEACTIVATE #{existing.pk}: department={row['department'] or 'Company-wide'} "
                                  f"{row['pattern_type']} {row['pattern']}")
        if not options['dry_run']:
            self.stdout.write(f"Policy checks passed: {verification['passed']}. "
                              'Unverified APP/SmartOffice examples remain pending confirmation.')
        self.stdout.write('Historical activity was not reclassified. No productivity/performance score or attendance action was created.')
