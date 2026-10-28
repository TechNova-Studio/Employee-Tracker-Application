"""Read-only, tenant-scoped employee usage dashboard. No performance scoring."""
import csv
from datetime import date, datetime, time, timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.db.models import Count, Max, Sum
from django.db.models.functions import TruncDate, TruncHour
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ActivityLog, Alert, Company, Department, ERPEmployeeMapping, Heartbeat, WorkSession
from .permissions import IsAdminOrReadOnlyScoped, get_role


CATEGORIES = ('PRODUCTIVE', 'NEUTRAL', 'UNPRODUCTIVE', 'UNKNOWN')
SORTS = ('productive_desc', 'share_desc', 'share_asc', 'work_desc', 'idle_desc', 'name_asc')
STATES = ('all', 'active', 'idle', 'offline', 'inactive', 'no_activity')


def integer(query, key, default=None, maximum=None):
    value = query.get(key)
    if value in (None, ''):
        return default
    return serializers.IntegerField(min_value=1, max_value=maximum).run_validation(value)


def period(query):
    today = timezone.localdate()
    try:
        first = date.fromisoformat(query.get('from_date') or today.isoformat())
        last = date.fromisoformat(query.get('to_date') or today.isoformat())
    except (TypeError, ValueError) as exc:
        raise serializers.ValidationError({'date': 'Use dates in YYYY-MM-DD format.'}) from exc
    if last < first or (last - first).days > 92:
        raise serializers.ValidationError({'date': 'Choose an ordered date range of at most 93 days.'})
    zone = timezone.get_default_timezone()
    return (first, last, datetime.combine(first, time.min, tzinfo=zone),
            datetime.combine(last + timedelta(days=1), time.min, tzinfo=zone))


def metrics(values):
    result = {key: int(values.get(key) or 0) for key in
              ('active_seconds', 'idle_seconds', 'heartbeat_count', 'sessions',
               'productive_seconds', 'neutral_seconds', 'unproductive_seconds', 'unknown_seconds')}
    result['work_seconds'] = result['active_seconds'] + result['idle_seconds']
    result['activity_seconds'] = sum(result[category.lower() + '_seconds'] for category in CATEGORIES)
    known = result['activity_seconds'] - result['unknown_seconds']
    result['classified_seconds'] = known
    result['productive_share_pct'] = round(result['productive_seconds'] * 100 / known, 1) if known else None
    result['classification_coverage_pct'] = round(known * 100 / result['activity_seconds'], 1) if result['activity_seconds'] else None
    result['has_activity'] = result['activity_seconds'] > 0
    result['has_work_telemetry'] = result['heartbeat_count'] > 0
    return result


def sum_metrics(rows):
    return metrics({key: sum(row.get(key, 0) for row in rows) for key in
                    ('active_seconds', 'idle_seconds', 'heartbeat_count', 'sessions',
                     'productive_seconds', 'neutral_seconds', 'unproductive_seconds', 'unknown_seconds')})


def safe_csv(value):
    text = str(value if value is not None else '')
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


class TeamDashboardView(APIView):
    permission_classes = [IsAdminOrReadOnlyScoped]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    def get(self, request):
        query = request.query_params
        role = get_role(request.user)
        super_admin = role == 'SUPER_ADMIN'
        own_company = getattr(request.user.profile, 'company_id', None)
        company_id = integer(query, 'company_id', own_company if not super_admin else None)
        if not super_admin and company_id != own_company:
            raise PermissionDenied('Cannot access another company.')
        choices = Company.objects.all() if super_admin else Company.objects.filter(pk=own_company)
        companies = list(choices.order_by('name', 'id').values('id', 'name'))
        if company_id is None:
            return Response({'requires_company': True, 'company': None,
                             'scope': 'SELECT_COMPANY' if super_admin else 'NO_COMPANY',
                             'options': {'companies': companies, 'departments': []}})
        company = choices.filter(pk=company_id).first()
        if not company:
            raise serializers.ValidationError({'company_id': 'Select an available company.'})
        first, last, start, end = period(query)
        employment = query.get('employment', 'all')
        if employment not in ('all', 'active', 'inactive'):
            raise serializers.ValidationError({'employment': 'Choose all, active or inactive.'})
        sort = query.get('sort', 'productive_desc')
        state = query.get('state', 'all')
        if sort not in SORTS or state not in STATES:
            raise serializers.ValidationError({'filters': 'Choose a supported employee sort and status.'})
        page = integer(query, 'page', 1)
        page_size = integer(query, 'page_size', 20, 100)
        roster = User.objects.filter(profile__company=company).select_related('profile__department')
        scope = 'OWN_COMPANY'
        if role == 'MANAGER':
            roster = roster.filter(profile__manager=request.user)
            scope = 'ASSIGNED_TEAM'
        elif role == 'EMPLOYEE':
            roster = roster.filter(pk=request.user.pk)
            scope = 'OWN_USER'
        elif super_admin:
            scope = 'SELECTED_COMPANY'
        departments = Department.objects.filter(company=company)
        if role in ('MANAGER', 'EMPLOYEE'):
            departments = departments.filter(pk__in=roster.values('profile__department_id'))
        options = {'companies': companies, 'departments': list(departments.order_by('name', 'id').values('id', 'name'))}
        department_id = query.get('department_id', '')
        if department_id == 'unassigned':
            roster = roster.exclude(profile__department__company=company)
        elif department_id:
            selected = integer(query, 'department_id')
            if not departments.filter(pk=selected).exists():
                raise PermissionDenied('Select a department in your visible company/team.')
            roster = roster.filter(profile__department_id=selected)
        employee_id = integer(query, 'employee_id')
        if employee_id:
            if not roster.filter(pk=employee_id).exists():
                raise PermissionDenied('Employee is outside your visible scope.')
            roster = roster.filter(pk=employee_id)
        if employment == 'active':
            roster = roster.filter(is_active=True, profile__is_active_employee=True)
        elif employment == 'inactive':
            roster = roster.exclude(is_active=True, profile__is_active_employee=True)
        users = list(roster.order_by('id'))
        ids = [user.pk for user in users]
        activities = ActivityLog.objects.filter(company=company, user_id__in=ids,
                                                captured_at__gte=start, captured_at__lt=end)
        heartbeats = Heartbeat.objects.filter(company=company, user_id__in=ids,
                                              captured_at__gte=start, captured_at__lt=end)
        work = {row['user_id']: row for row in heartbeats.values('user_id').annotate(
            active_seconds=Sum('active_seconds'), idle_seconds=Sum('idle_seconds'), heartbeat_count=Count('id'))}
        usage = {}
        for row in activities.values('user_id', 'productivity').annotate(seconds=Sum('duration_seconds')):
            category = row['productivity'] if row['productivity'] in CATEGORIES else 'UNKNOWN'
            values = usage.setdefault(row['user_id'], {})
            key = category.lower() + '_seconds'
            values[key] = values.get(key, 0) + row['seconds']
        sessions = dict(WorkSession.objects.filter(company=company, user_id__in=ids,
            started_at__gte=start, started_at__lt=end).values('user_id').annotate(total=Count('id')).values_list('user_id', 'total'))
        last_seen = dict(Heartbeat.objects.filter(company=company, user_id__in=ids).values('user_id')
                         .annotate(last=Max('captured_at')).values_list('user_id', 'last'))
        now = timezone.now()
        recent = {}
        for row in (Heartbeat.objects.filter(company=company, user_id__in=ids,
                captured_at__gte=now-timedelta(seconds=180), captured_at__lte=now).order_by('-captured_at', '-id')
                .values('user_id', 'is_idle', 'session__status')):
            recent.setdefault(row['user_id'], row)
        mapping_codes = {}
        for row in ERPEmployeeMapping.objects.filter(connector__company=company, user_id__in=ids).values('user_id', 'external_id'):
            mapping_codes.setdefault(row['user_id'], set()).add(row['external_id'])
        rows = []
        for user in users:
            profile = user.profile
            department = profile.department if profile.department and profile.department.company_id == company.pk else None
            active = user.is_active and profile.is_active_employee
            current = recent.get(user.pk)
            live = ('idle' if current['is_idle'] else 'active') if active and current and current['session__status'] == 'RUNNING' else 'offline'
            source_ids = mapping_codes.get(user.pk, set())
            values = metrics({**work.get(user.pk, {}), **usage.get(user.pk, {}), 'sessions': sessions.get(user.pk, 0)})
            rows.append({'id': user.pk, 'name': user.get_full_name().strip() or user.email or user.username,
                'email': user.email, 'employee_code': profile.employee_code or (next(iter(source_ids)) if len(source_ids) == 1 else ''),
                'department_id': department.pk if department else None,
                'department_name': department.name if department else 'Unassigned',
                'employment_active': active, 'live_status': live if active else 'inactive',
                'last_seen_at': last_seen.get(user.pk), **values})
        summary = {**sum_metrics(rows), 'total_employees': len(rows),
            'active_employees': sum(row['employment_active'] for row in rows),
            'inactive_employees': sum(not row['employment_active'] for row in rows),
            'online_employees': sum(row['live_status'] in ('active', 'idle') for row in rows),
            'reporting_employees': sum(row['has_activity'] or row['has_work_telemetry'] for row in rows),
            'no_activity_employees': sum(not row['has_activity'] and not row['has_work_telemetry'] for row in rows),
            'open_alerts': Alert.objects.filter(company=company, user_id__in=ids, status='OPEN').count()}
        eligible = [row for row in rows if row['classified_seconds'] > 0]
        leaders = sorted([row for row in eligible if row['productive_seconds'] > 0],
                         key=lambda row: (-row['productive_seconds'], row['name'].casefold(), row['id']))[:3]
        review = sorted(eligible, key=lambda row: (row['productive_share_pct'], -row['classified_seconds'], row['id']))[:3]
        department_groups = {}
        for row in rows:
            department_groups.setdefault((row['department_id'], row['department_name']), []).append(row)
        department_rows = [{'id': key[0], 'name': key[1], 'employee_count': len(group), **sum_metrics(group)}
                           for key, group in department_groups.items()]
        department_rows.sort(key=lambda row: (-row['productive_seconds'], row['name'].casefold()))
        hourly = first == last
        days = ({f'{hour:02d}:00': {'date': first.isoformat(), 'label': f'{hour:02d}:00'} for hour in range(24)}
                if hourly else {(first+timedelta(days=i)).isoformat(): {'date': (first+timedelta(days=i)).isoformat()}
                                 for i in range((last-first).days+1)})
        truncation = TruncHour if hourly else TruncDate
        for row in (activities.annotate(day=truncation('captured_at', tzinfo=timezone.get_default_timezone()))
                .values('day', 'productivity').annotate(seconds=Sum('duration_seconds'))):
            category = row['productivity'] if row['productivity'] in CATEGORIES else 'UNKNOWN'
            bucket = days[row['day'].strftime('%H:00') if hourly else row['day'].isoformat()]
            key = category.lower() + '_seconds'
            bucket[key] = bucket.get(key, 0) + row['seconds']
        trend = [{**metrics(row), 'date': row['date'], **({'label': row['label']} if hourly else {})} for row in days.values()]
        apps = list(activities.values('app_name', 'domain').annotate(seconds=Sum('duration_seconds')).order_by('-seconds', 'app_name', 'domain')[:5])
        table = rows
        search = query.get('search', '').strip().casefold()[:200]
        if search:
            table = [row for row in table if search in ' '.join(str(row[key]) for key in
                     ('name', 'email', 'employee_code', 'department_name')).casefold()]
        if state == 'no_activity':
            table = [row for row in table if not row['has_activity'] and not row['has_work_telemetry']]
        elif state != 'all':
            table = [row for row in table if row['live_status'] == state]
        if sort == 'name_asc':
            table = sorted(table, key=lambda row: (row['name'].casefold(), row['id']))
        elif sort in ('share_asc', 'share_desc'):
            direction = 1 if sort == 'share_asc' else -1
            table = sorted(table, key=lambda row: (row['productive_share_pct'] is None,
                direction * (row['productive_share_pct'] or 0), row['name'].casefold(), row['id']))
        else:
            field = {'productive_desc': 'productive_seconds', 'work_desc': 'work_seconds', 'idle_desc': 'idle_seconds'}[sort]
            table = sorted(table, key=lambda row: (-row[field], row['name'].casefold(), row['id']))
        if query.get('export') == 'csv':
            output = StringIO()
            columns = ['name', 'email', 'employee_code', 'department_name', 'employment_active', 'work_seconds',
                       'active_seconds', 'idle_seconds', 'has_work_telemetry', 'activity_seconds', 'productive_seconds', 'neutral_seconds',
                       'unproductive_seconds', 'unknown_seconds', 'productive_share_pct', 'classification_coverage_pct']
            writer = csv.writer(output)
            writer.writerow(columns)
            for row in table:
                writer.writerow([safe_csv(row[key]) for key in columns])
            response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="workpulse-team-{first}-{last}.csv"'
            response['Cache-Control'] = 'private, no-store'
            return response
        pages = max(1, (len(table)+page_size-1)//page_size)
        page = min(page, pages)
        response = Response({'schema_version': 1, 'requires_company': False, 'scope': scope,
            'company': {'id': company.pk, 'name': company.name},
            'range': {'from_date': first.isoformat(), 'to_date': last.isoformat(),
                      'timezone': str(timezone.get_default_timezone()), 'days': (last-first).days+1},
            'generated_at': now, 'options': options, 'summary': summary,
            'employees': {'count': len(table), 'page': page, 'page_size': page_size, 'pages': pages,
                          'results': table[(page-1)*page_size:page*page_size]},
            'leaders': leaders, 'review': review, 'departments': department_rows, 'trend': trend,
            'trend_granularity': 'hour' if hourly else 'day', 'top_apps': apps,
            'definitions': {'work_time': 'Active + idle seconds from heartbeats captured within the date range.',
                'productive_share': 'Productive / (productive + neutral + unproductive). UNKNOWN excluded.',
                'coverage': 'Classified app time / all recorded app time.',
                'live_status': 'Latest heartbeat within 180 seconds and its session is still running.',
                'department': 'Current assignment; historical department is not snapshotted.',
                'sessions': 'Sessions started in the date range.',
                'time': 'Telemetry is attributed to its captured timestamp; separate devices can overlap.'}})
        response['Cache-Control'] = 'private, no-store'
        return response
