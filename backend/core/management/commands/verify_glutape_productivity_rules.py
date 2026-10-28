import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models import Company
from core.productivity_policy_checks import verify_glutape_policy


class Command(BaseCommand):
    help = 'Run read-only Glutape baseline classification examples and optionally save JSON evidence.'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int, required=True)
        parser.add_argument('--output')

    def handle(self, *args, **options):
        company = Company.objects.filter(pk=options['company_id']).first()
        if not company or company.pk != 1 or 'glutape' not in company.name.casefold():
            raise CommandError('Select Glutape WorkPulse company ID 1.')
        result = verify_glutape_policy(company)
        for case in result['cases']:
            self.stdout.write(f"{'PASS' if case['passed'] else 'FAIL'}: Department {case['department_id']} — "
                              f"{case['label']}: expected {case['expected']}, got {case['actual']}")
        if options.get('output'):
            Path(options['output']).write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        self.stdout.write(f"{result['passed']} passed, {result['failed']} failed; "
                          f"{result['pending_rule_count']} rules pending telemetry confirmation.")
        for row in result['pending_telemetry_rules']:
            self.stdout.write(f"PENDING: {row['department_name']} / {row['tool_name']} "
                              f"({'/'.join(row['pattern_types'])}) => {row['category']}; exact captured value required.")
        if result['failed']:
            raise CommandError('Review conflicting or missing rules before rollout.')
