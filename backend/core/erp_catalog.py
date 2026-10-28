from .erp_employee_sync import EMPLOYEE_EVENTS

BUSINESS_EVENTS = (
    'lead_created', 'followup_added', 'pi_created', 'pi_updated', 'invoice_created',
    'dispatch_updated', 'transporter_assigned', 'capa_created', 'price_engine_task_updated',
    'inventory_entry_created', 'erp_user_login',
)


def event_options():
    return [{'value': name, 'label': name.replace('_', ' ').capitalize(),
             'processing': 'PROCESSED' if name in EMPLOYEE_EVENTS else 'RECEIVED_ONLY'}
            for name in sorted(EMPLOYEE_EVENTS) + list(BUSINESS_EVENTS)]
