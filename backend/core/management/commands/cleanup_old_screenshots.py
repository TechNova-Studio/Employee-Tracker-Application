from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Company, Screenshot
from pathlib import Path


class Command(BaseCommand):
    help = 'Soft-delete and remove local screenshot files older than company retention policy.'

    def handle(self, *args, **options):
        deleted = 0
        now = timezone.now()
        for company in Company.objects.all():
            cutoff = now - timezone.timedelta(days=company.screenshot_retention_days)
            qs = Screenshot.objects.filter(company=company, captured_at__lt=cutoff, deleted_at__isnull=True)
            for shot in qs:
                if shot.file:
                    try:
                        path = Path(shot.file.path)
                        if path.exists():
                            path.unlink()
                    except Exception:
                        pass
                shot.deleted_at = now
                shot.status = 'DELETED_BY_RETENTION'
                shot.save(update_fields=['deleted_at','status'])
                deleted += 1
        self.stdout.write(self.style.SUCCESS(f'Old screenshots cleaned: {deleted}'))
