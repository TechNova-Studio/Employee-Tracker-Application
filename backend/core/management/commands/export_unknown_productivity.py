"""Read-only UNKNOWN activity summaries; each telemetry dimension has its own CSV."""
import csv
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Case, Count, F, IntegerField, Q, Sum, Value, When, CharField

from core.models import ActivityLog, Company


DIMENSIONS = {'applications': 'app_name', 'domains': 'domain', 'urls': 'url', 'window_titles': 'window_title'}


def csv_value(value):
    # Telemetry titles/URLs are untrusted text; do not let them become spreadsheet formulas.
    value = str(value or '')
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


class Command(BaseCommand):
    help = 'Export highest-duration UNKNOWN activity by department for an explicit date range.'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int, required=True)
        parser.add_argument('--from-date', required=True, help='Inclusive YYYY-MM-DD')
        parser.add_argument('--to-date', required=True, help='Inclusive YYYY-MM-DD')
        parser.add_argument('--timezone', default=settings.TIME_ZONE)
        parser.add_argument('--output-dir', required=True)
        parser.add_argument('--limit', type=int, default=100, help='Top rows per telemetry dimension')

    def handle(self, *args, **options):
        company = Company.objects.filter(pk=options['company_id']).first()
        if not company:
            raise CommandError('Company does not exist.')
        try:
            start_date, end_date = date.fromisoformat(options['from_date']), date.fromisoformat(options['to_date'])
            zone = ZoneInfo(options['timezone'])
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise CommandError('Use valid ISO dates and an IANA timezone, such as Asia/Kolkata.') from exc
        if end_date < start_date or options['limit'] < 1 or options['limit'] > 10000:
            raise CommandError('Choose an ordered date range and a limit between 1 and 10000.')
        start = datetime.combine(start_date, time.min, tzinfo=zone)
        end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=zone)
        activities = ActivityLog.objects.filter(company=company, captured_at__gte=start, captured_at__lt=end)
        unknown = activities.filter(productivity='UNKNOWN')
        same_company = Q(user__profile__department__company_id=company.pk)
        grouped = unknown.annotate(
            report_department_id=Case(When(same_company, then=F('user__profile__department_id')),
                default=Value(None), output_field=IntegerField()),
            report_department_name=Case(When(same_company, then=F('user__profile__department__name')),
                default=Value('Unassigned'), output_field=CharField()),
        )
        totals = unknown.aggregate(duration_seconds=Sum('duration_seconds'), activity_count=Count('id'))
        summary = {'company_id': company.pk, 'company_name': company.name, 'from_date': start_date.isoformat(),
            'to_date': end_date.isoformat(), 'timezone': str(zone), 'unknown_activity_count': totals['activity_count'],
            'unknown_duration_seconds': totals['duration_seconds'] or 0,
            'all_activity_count': activities.count(),
            'activities_with_url': activities.exclude(url='').count(),
            'activities_with_domain': activities.exclude(domain='').count(),
            'department_basis': 'Current employee department; foreign/unassigned departments are grouped as Unassigned.',
            'dimension_totals_overlap': True,
            'rule_changes_reclassify_history': False, 'files': {}}
        output = Path(options['output_dir'])
        output.mkdir(parents=True, exist_ok=True)
        for label, field in DIMENSIONS.items():
            rows = (grouped.exclude(**{field: ''}).values('report_department_id', 'report_department_name', field)
                    .annotate(total_seconds=Sum('duration_seconds'), activity_count=Count('id'))
                    .order_by('-total_seconds', 'report_department_id', field)[:options['limit']])
            filename = label + '.csv'
            with (output / filename).open('w', encoding='utf-8-sig', newline='') as target:
                writer = csv.writer(target)
                writer.writerow(['department_id', 'department_name', field, 'total_duration_seconds', 'total_duration_hours', 'activity_count'])
                for row in rows:
                    writer.writerow([row['report_department_id'] or '', csv_value(row['report_department_name']),
                        csv_value(row[field]), row['total_seconds'], round(row['total_seconds'] / 3600, 4), row['activity_count']])
            summary['files'][label] = filename
        (output / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f"Exported {totals['activity_count']} UNKNOWN activity records to {output}."))
        self.stdout.write('Each CSV is a separate view of the same activity; do not sum durations across the four files.')
