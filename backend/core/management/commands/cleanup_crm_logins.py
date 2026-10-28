from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import CRMLoginAttempt


class Command(BaseCommand):
    help = 'Delete expired CRM login attempts older than 24 hours (no employees or sessions affected).'

    def handle(self, *args, **options):
        count, _ = CRMLoginAttempt.objects.filter(expires_at__lt=timezone.now()-timedelta(days=1)).delete()
        self.stdout.write(f'Deleted {count} expired CRM login attempts.')
