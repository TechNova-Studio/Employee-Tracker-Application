import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import APIException

from core.erp_employee_mapping import save_mapping_rows
from core.erp_mapping_api import MappingRowSerializer
from core.models import ERPConnector


class Command(BaseCommand):
    help = 'Validate/import reviewed CRM ID -> existing WorkPulse User ID mappings.'

    def add_arguments(self, parser):
        parser.add_argument('--connector-id', type=int, required=True)
        parser.add_argument('--file', required=True)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        connector = ERPConnector.objects.filter(pk=options['connector_id']).first()
        if connector is None:
            raise CommandError('Connector does not exist.')
        try:
            path = Path(options['file'])
            if path.stat().st_size > 5 * 1024 * 1024:
                raise CommandError('CSV must be at most 5 MiB.')
            with path.open(newline='', encoding='utf-8-sig') as source:
                reader = csv.DictReader(source)
                if reader.fieldnames != ['crm_employee_id', 'workpulse_employee_id']:
                    raise CommandError('CSV header must be crm_employee_id,workpulse_employee_id.')
                rows = [{'external_id': row['crm_employee_id'],
                         'workpulse_employee_id': row['workpulse_employee_id']} for row in reader]
        except (OSError, csv.Error, KeyError) as exc:
            raise CommandError(f'Cannot read mapping CSV: {exc}') from exc
        if not rows or len(rows) > 10000:
            raise CommandError('Provide 1–10000 reviewed mapping rows.')
        serializer = MappingRowSerializer(data=rows, many=True)
        try:
            serializer.is_valid(raise_exception=True)
            result = save_mapping_rows(connector, serializer.validated_data, dry_run=options['dry_run'])
        except APIException as exc:
            raise CommandError(str(exc.detail)) from exc
        prefix = 'Validated (no changes saved)' if options['dry_run'] else 'Saved'
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}: {result['created']} new, {result['unchanged']} unchanged."))
