"""Admin mapping APIs. ERP connector secrets authenticate ingestion only."""
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied

from .erp_employee_mapping import normalize_external_id, save_employee_mapping, save_mapping_rows
from .models import ERPConnector, ERPEmployeeMapping
from .permissions import IsERPConnectorPermission, get_role, is_super_admin_user


def scope_company(request, queryset, field):
    if not is_super_admin_user(request.user):
        company_id = getattr(getattr(request.user, 'profile', None), 'company_id', None)
        if not company_id:
            return queryset.none()
        queryset = queryset.filter(**{field: company_id})
    selected = request.query_params.get('company_id')
    if selected is not None:
        selected = serializers.IntegerField(min_value=1).run_validation(selected)
        if not is_super_admin_user(request.user) and selected != company_id:
            raise PermissionDenied('Cannot access another company.')
        queryset = queryset.filter(**{field: selected})
    return queryset


class MappingRowSerializer(serializers.Serializer):
    external_id = serializers.CharField(max_length=128)
    workpulse_employee_id = serializers.IntegerField(min_value=1)

    def to_internal_value(self, data):
        if isinstance(data, dict) and 'external_id' in data and not isinstance(data['external_id'], str):
            raise serializers.ValidationError({'external_id': 'Send the stable CRM employee ID as a string.'})
        return super().to_internal_value(data)

    def validate_external_id(self, value):
        try:
            return normalize_external_id(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))


class MappingCreateSerializer(MappingRowSerializer):
    connector_id = serializers.IntegerField(min_value=1)


class MappingBulkSerializer(serializers.Serializer):
    connector_id = serializers.IntegerField(min_value=1)
    dry_run = serializers.BooleanField(default=False)
    rows = MappingRowSerializer(many=True, min_length=1, max_length=1000)


class ERPEmployeeMappingSerializer(serializers.ModelSerializer):
    connector_id = serializers.IntegerField(read_only=True)
    connector_name = serializers.CharField(source='connector.name', read_only=True)
    company_id = serializers.IntegerField(source='connector.company_id', read_only=True)
    workpulse_employee_id = serializers.IntegerField(source='user_id', read_only=True)
    workpulse_profile_id = serializers.IntegerField(source='user.profile.id', read_only=True)
    employee_name = serializers.SerializerMethodField()
    employee_email = serializers.EmailField(source='user.email', read_only=True)
    workpulse_employee_code = serializers.CharField(source='user.profile.employee_code', read_only=True)

    class Meta:
        model = ERPEmployeeMapping
        fields = ['id', 'connector_id', 'connector_name', 'company_id', 'external_id',
                  'workpulse_employee_id', 'workpulse_profile_id', 'employee_name',
                  'employee_email', 'workpulse_employee_code', 'created_at', 'updated_at']
        read_only_fields = fields

    def get_employee_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


class ERPEmployeeMappingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ERPEmployeeMapping.objects.select_related('connector', 'user', 'user__profile').order_by('id')
    serializer_class = ERPEmployeeMappingSerializer
    permission_classes = [IsERPConnectorPermission]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = scope_company(self.request, super().get_queryset(), 'connector__company_id')
        connector_id = self.request.query_params.get('connector_id')
        if connector_id is not None:
            connector_id = serializers.IntegerField(min_value=1).run_validation(connector_id)
            qs = qs.filter(connector_id=connector_id)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(external_id__icontains=search) | Q(user__email__icontains=search) |
                           Q(user__first_name__icontains=search) | Q(user__last_name__icontains=search))
        return qs

    def connector(self, connector_id):
        qs = scope_company(self.request, ERPConnector.objects.all(), 'company_id')
        return get_object_or_404(qs, pk=connector_id)

    def create(self, request, *args, **kwargs):
        serializer = MappingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        mapping, created = save_employee_mapping(self.connector(values['connector_id']),
            values['external_id'], values['workpulse_employee_id'], actor=request.user)
        return Response(self.get_serializer(mapping).data, status=201 if created else 200)

    @action(detail=False, methods=['post'], url_path='bulk')
    def bulk(self, request):
        serializer = MappingBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = save_mapping_rows(self.connector(data['connector_id']), data['rows'],
            dry_run=data['dry_run'], actor=request.user)
        return Response(result)

    @action(detail=False, methods=['get'], url_path='form-options')
    def form_options(self, request):
        connector_id = serializers.IntegerField(min_value=1).run_validation(request.query_params.get('connector_id'))
        connector = self.connector(connector_id)
        users = User.objects.select_related('profile').filter(profile__company_id=connector.company_id).exclude(
            profile__role='SUPER_ADMIN').order_by('id')
        search = request.query_params.get('search', '').strip()
        if search:
            users = users.filter(Q(email__icontains=search) | Q(first_name__icontains=search) |
                                 Q(last_name__icontains=search) | Q(profile__employee_code__icontains=search))
        pager = PageNumberPagination()
        page = pager.paginate_queryset(users, request, view=self)
        links = {row.user_id: row.external_id for row in ERPEmployeeMapping.objects.filter(
            connector=connector, user_id__in=[user.pk for user in page])}
        results = [{'workpulse_employee_id': user.pk, 'workpulse_profile_id': user.profile.pk,
                    'name': user.get_full_name() or user.username, 'email': user.email,
                    'employee_code': user.profile.employee_code, 'is_active': user.is_active,
                    'external_id': links.get(user.pk)} for user in page]
        response = pager.get_paginated_response(results)
        response.data.update({'connector_id': connector.pk, 'company_id': connector.company_id,
                              'can_manage': get_role(request.user) in ('SUPER_ADMIN', 'COMPANY_ADMIN')})
        return response
