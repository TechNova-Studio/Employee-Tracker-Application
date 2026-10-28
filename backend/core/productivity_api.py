"""Company-scoped administration for the existing activity classification rules."""
import re

from django.db.models import Q
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import AppWebsiteCategory, Company, Department
from .permissions import IsCompanyAdminOrHR
from .views import TenantModelViewSet, admin_company_scope, is_super_admin, user_company


PATTERN_TYPES = [('APP', 'Application'), ('DOMAIN', 'Website domain'),
                 ('WINDOW', 'Window title'), ('URL', 'URL contains')]


class ProductivityRuleSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all(), required=False)
    company_name = serializers.CharField(source='company.name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    pattern_type = serializers.CharField(max_length=32, required=False, default='APP')
    notes = serializers.CharField(required=False, allow_blank=True, max_length=4000)

    class Meta:
        model = AppWebsiteCategory
        fields = ['id', 'company', 'company_name', 'department', 'department_name',
                  'pattern_type', 'pattern', 'category', 'notes', 'is_active',
                  'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def validate_pattern_type(self, value):
        kind = value.strip().upper()
        kind = {'TITLE': 'WINDOW', 'WINDOW_TITLE': 'WINDOW'}.get(kind, kind)
        if kind not in dict(PATTERN_TYPES):
            raise serializers.ValidationError('Choose Application, Website domain, Window title or URL contains.')
        return kind

    def validate(self, attrs):
        request = self.context['request']
        own_company = user_company(request.user)
        supplied = attrs.get('company')
        if self.instance:
            company = self.instance.company
            if supplied and supplied.pk != company.pk:
                raise serializers.ValidationError({'company': 'A rule cannot be moved to another company.'})
        elif is_super_admin(request.user):
            company = supplied
            if not company:
                raise serializers.ValidationError({'company': 'Select a company.'})
        else:
            company = own_company
        if not company:
            raise serializers.ValidationError({'company': 'No company assigned.'})
        if not is_super_admin(request.user) and (company != own_company or (supplied and supplied != own_company)):
            raise PermissionDenied('Cannot manage rules for another company.')
        attrs['company'] = company

        department = attrs.get('department', getattr(self.instance, 'department', None))
        if department:
            if department.company_id != company.pk:
                raise serializers.ValidationError({'department': 'Department must belong to the selected company.'})
            if not department.is_active and department.pk != getattr(self.instance, 'department_id', None):
                raise serializers.ValidationError({'department': 'Select an active department.'})

        pattern = attrs.get('pattern', getattr(self.instance, 'pattern', '')).strip()
        if not pattern:
            raise serializers.ValidationError({'pattern': 'Enter an application, domain, window title or URL pattern.'})
        kind = attrs.get('pattern_type', getattr(self.instance, 'pattern_type', 'APP')).upper()
        if kind == 'DOMAIN':
            pattern = pattern.lower()
            label = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
            if len(pattern) > 253 or not re.fullmatch(rf'{label}(?:\.{label})*', pattern):
                raise serializers.ValidationError({'pattern': 'Enter only a hostname, such as youtube.com, without https://, a path or wildcards.'})
        attrs['pattern'] = pattern

        duplicates = AppWebsiteCategory.objects.filter(company=company, department=department,
            pattern_type__iexact=kind, pattern__iexact=pattern)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({'pattern': 'A rule already exists for this pattern and scope. Edit the existing rule.'})
        return attrs


class ProductivityRulePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class ProductivityRuleViewSet(TenantModelViewSet):
    queryset = AppWebsiteCategory.objects.select_related('company', 'department').order_by('-updated_at', '-id')
    serializer_class = ProductivityRuleSerializer
    permission_classes = [IsCompanyAdminOrHR]
    pagination_class = ProductivityRulePagination

    def get_queryset(self):
        qs = admin_company_scope(self.request, super().get_queryset())
        # List filters never change object lookup for updates.
        if self.action != 'list':
            return qs
        query = self.request.query_params
        search = query.get('search', '').strip()
        if search:
            qs = qs.filter(Q(pattern__icontains=search) | Q(notes__icontains=search)
                           | Q(department__name__icontains=search))
        for field, choices in (('category', dict(AppWebsiteCategory.PRODUCTIVITY_CHOICES)),
                               ('pattern_type', dict(PATTERN_TYPES))):
            value = query.get(field)
            if value:
                if value not in choices:
                    raise serializers.ValidationError({field: 'Select a valid filter.'})
                if field == 'pattern_type' and value == 'WINDOW':
                    qs = qs.filter(pattern_type__in=['WINDOW', 'WINDOW_TITLE', 'TITLE'])
                else:
                    qs = qs.filter(**{field: value})
        active = query.get('is_active')
        if active is not None:
            if active not in ('true', 'false'):
                raise serializers.ValidationError({'is_active': 'Use true or false.'})
            qs = qs.filter(is_active=active == 'true')
        department = query.get('department_id')
        if department == 'company':
            qs = qs.filter(department__isnull=True)
        elif department:
            department_id = serializers.IntegerField(min_value=1).run_validation(department)
            qs = qs.filter(department_id=department_id)
        return qs

    @action(detail=False, methods=['get'], url_path='form-options')
    def form_options(self, request):
        own_company = user_company(request.user)
        if is_super_admin(request.user):
            companies = Company.objects.order_by('name', 'id')
            selected = request.query_params.get('company_id')
            company = None
            if selected:
                company_id = serializers.IntegerField(min_value=1).run_validation(selected)
                company = companies.filter(pk=company_id).first()
                if not company:
                    raise serializers.ValidationError({'company_id': 'Select an existing company.'})
        else:
            if not own_company:
                raise serializers.ValidationError({'company': 'No company assigned.'})
            selected = request.query_params.get('company_id')
            if selected and serializers.IntegerField(min_value=1).run_validation(selected) != own_company.pk:
                raise PermissionDenied('Cannot access another company.')
            companies = Company.objects.filter(pk=own_company.pk)
            company = own_company
        departments = Department.objects.filter(company=company).order_by('name', 'id') if company else Department.objects.none()
        return Response({
            'companies': list(companies.values('id', 'name')),
            'selected_company_id': company.pk if company else None,
            'departments': list(departments.values('id', 'name', 'is_active')),
        })
