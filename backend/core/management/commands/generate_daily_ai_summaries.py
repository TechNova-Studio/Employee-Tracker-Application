from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.dateparse import parse_date
from core.ai_summaries import generate_summaries


class Command(BaseCommand):
    help = 'Generate rule-based daily summaries; unchanged summaries retain their review status.'

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, default=None, help='YYYY-MM-DD. Defaults to today.')

    def handle(self, *args, **options):
        try:
            target_date = parse_date(options['date']) if options['date'] else timezone.localdate()
        except ValueError:
            target_date = None
        if target_date is None or target_date > timezone.localdate():
            raise CommandError('Use a valid date no later than today (YYYY-MM-DD).')
        result = generate_summaries(User.objects.filter(profile__company__isnull=False), target_date)
        self.stdout.write(self.style.SUCCESS(f'Rule-based summaries for {target_date}: {result}'))
