from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Process pending AI jobs. In v1 staging this calls the rule-based summary generator.'

    def handle(self, *args, **options):
        call_command('generate_daily_ai_summaries')
        self.stdout.write(self.style.SUCCESS('Pending AI jobs processed using staging fallback.'))
