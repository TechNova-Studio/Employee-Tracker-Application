"""Multipart employee onboarding scoped by the existing ERP connector token."""
import logging

from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .erp_employee_import import EmployeeImportError, boolean_value, import_employee_rows, read_employee_file
from .models import ERPConnector


logger = logging.getLogger(__name__)


class ERPEmployeeImportView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser]

    def post(self, request):
        token = request.META.get('HTTP_X_WORKPULSE_TOKEN')
        connector = ERPConnector.objects.filter(api_token=token, is_active=True).first() if token else None
        if connector is None:
            return Response({'detail': 'Invalid connector token.'}, status=403)
        if not isinstance(connector.allowed_event_types, list) or 'erp_user_created' not in connector.allowed_event_types:
            return Response({'detail': 'Enable erp_user_created in this connector before importing.'}, status=403)
        if set(request.data) - {'file', 'dry_run', 'company_id'}:
            return Response({'detail': 'Supported form fields: file, dry_run and optional company_id.'}, status=400)
        if len(request.FILES) != 1 or len(request.FILES.getlist('file')) != 1:
            return Response({'detail': 'Select exactly one file under the form-data key file.'}, status=400)
        if any(len(request.data.getlist(key)) != 1 for key in request.data):
            return Response({'detail': 'Do not repeat form-data keys.'}, status=400)
        company_id = request.data.get('company_id')
        if company_id is not None and str(company_id) != str(connector.company_id):
            return Response({'detail': 'company_id must match the connector company.'}, status=400)
        try:
            dry_run = boolean_value(request.data.get('dry_run', 'false'), 'dry_run')
            rows = read_employee_file(request.FILES['file'])
            return Response(import_employee_rows(connector, token, rows, dry_run=dry_run))
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        except EmployeeImportError as exc:
            return Response({'status': 'failed', 'detail': str(exc), 'errors': exc.errors}, status=exc.status)
        except Exception:
            logger.exception('Employee file import failed for connector %s', connector.pk)
            return Response({'status': 'failed', 'detail': 'Unexpected import error. No employees or mappings were saved.'}, status=500)
