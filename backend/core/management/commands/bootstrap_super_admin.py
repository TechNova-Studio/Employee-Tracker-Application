import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from core.models import Profile


class Command(BaseCommand):
    help = 'Create the first Super Admin from WORKPULSE_SUPERADMIN_EMAIL / WORKPULSE_SUPERADMIN_PASSWORD.'

    def add_arguments(self, parser):
        parser.add_argument('--noinput', action='store_true')

    def handle(self, *args, **options):
        email = os.environ.get('WORKPULSE_SUPERADMIN_EMAIL', '').strip().lower()
        password = os.environ.get('WORKPULSE_SUPERADMIN_PASSWORD', '')
        if not email or not password:
            raise CommandError('Set both WORKPULSE_SUPERADMIN_EMAIL and WORKPULSE_SUPERADMIN_PASSWORD.')
        if len(password) < 10:
            raise CommandError('Use a password of at least 10 characters.')
        if Profile.objects.filter(role='SUPER_ADMIN').exists():
            self.stdout.write('A Super Admin already exists. Nothing changed.')
            return
        user, _ = User.objects.get_or_create(username=email, defaults={'email': email})
        user.email = email
        user.is_active = True
        user.set_password(password)
        user.save()
        Profile.objects.update_or_create(user=user, defaults={
            'company': None, 'role': 'SUPER_ADMIN', 'policy_status': 'ACCEPTED',
            'can_generate_trials': True, 'is_active_employee': True})
        self.stdout.write(self.style.SUCCESS(f'Super Admin created: {email}'))