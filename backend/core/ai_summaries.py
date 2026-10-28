"""Deterministic daily summaries shared by the API and scheduled command."""
from django.db import transaction
from django.db.models import Sum
from .models import ActivityLog, Alert, DailyAISummary, Heartbeat, Screenshot, WorkSession


def generate_summaries(users, target_date):
    result = {'created': 0, 'updated': 0, 'unchanged': 0, 'skipped': 0}
    for user in users.select_related('profile__company').order_by('id'):
        company = user.profile.company
        sessions = WorkSession.objects.filter(company=company, user=user, started_at__date=target_date)
        heartbeats = Heartbeat.objects.filter(company=company, user=user, captured_at__date=target_date)
        activities = ActivityLog.objects.filter(company=company, user=user, captured_at__date=target_date)
        if not sessions.exists() and not activities.exists() and not heartbeats.exists():
            result['skipped'] += 1
            continue
        totals = heartbeats.aggregate(active=Sum('active_seconds'), idle=Sum('idle_seconds'))
        # Legacy/sample sessions without heartbeats use their stored counters.
        # Real overnight sessions are attributed to each heartbeat's local date.
        legacy = sessions.filter(heartbeats__isnull=True).aggregate(active=Sum('active_seconds'), idle=Sum('idle_seconds'))
        active = (totals['active'] or 0) + (legacy['active'] or 0)
        idle = (totals['idle'] or 0) + (legacy['idle'] or 0)
        categories = {row['productivity']: row['seconds'] or 0 for row in
                      activities.values('productivity').annotate(seconds=Sum('duration_seconds'))}
        productive, neutral, unproductive = [categories.get(k, 0) for k in ('PRODUCTIVE', 'NEUTRAL', 'UNPRODUCTIVE')]
        top_apps = list(activities.exclude(app_name='').values('app_name').annotate(seconds=Sum('duration_seconds'))
                        .order_by('-seconds', 'app_name').values_list('app_name', flat=True)[:5])
        top_sites = list(activities.exclude(domain='').values('domain').annotate(seconds=Sum('duration_seconds'))
                         .order_by('-seconds', 'domain').values_list('domain', flat=True)[:5])
        count = Screenshot.objects.filter(company=company, user=user, captured_at__date=target_date,
                                          deleted_at__isnull=True).exclude(status='DELETED').count()
        flags, risks = [], []
        if idle > active:
            flags.append('Recorded idle time exceeds active time.'); risks.append('HIGH_IDLE')
        if unproductive > productive and unproductive:
            flags.append('Usage classified as unproductive exceeds productive usage.'); risks.append('HIGH_UNPRODUCTIVE')
        if not count:
            flags.append('No screenshots are available for this date.'); risks.append('NO_SCREENSHOTS')
        text = (f'{user.email or user.username}: {active / 3600:.2f} recorded active hours and '
                f'{idle / 3600:.2f} idle hours. Top apps: {", ".join(top_apps) or "None recorded"}. '
                f'Top websites: {", ".join(top_sites) or "None recorded"}. Screenshots: {count}. '
                'Rule-based summary of recorded telemetry; it does not establish work quality or misconduct. '
                'Manager/admin review is required before any action.')
        values = dict(active_seconds=active, idle_seconds=idle, productive_seconds=productive,
                      neutral_seconds=neutral, unproductive_seconds=unproductive, top_apps=top_apps,
                      top_websites=top_sites, screenshot_count=count, unusual_activity_flags=flags,
                      summary_text=text, risk_flags=risks, confidence_score=0)
        with transaction.atomic():
            obj, created = DailyAISummary.objects.get_or_create(company=company, user=user, date=target_date,
                                                               defaults=values)
            obj = DailyAISummary.objects.select_for_update().get(pk=obj.pk)
            changed = not created and any(getattr(obj, key) != value for key, value in values.items())
            if changed:
                for key, value in values.items():
                    setattr(obj, key, value)
                obj.manager_review_status = 'PENDING'
                obj.save()
            result['created' if created else 'updated' if changed else 'unchanged'] += 1
            title = f'Daily activity observations — {target_date}'
            if risks:
                Alert.objects.get_or_create(company=company, user=user, alert_type='AI_RISK_FLAG', title=title,
                                            defaults={'severity': 'MEDIUM', 'message': ', '.join(flags)})
    return result
