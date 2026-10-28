"""Internal billing records. No payment gateway or tax calculation is performed."""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from .models import BillingInvoice, Company, Device, Subscription


class BillingConflict(APIException):
    status_code = 409
    default_detail = 'The billing record no longer allows this action. Refresh and try again.'


def active_users(company):
    return User.objects.filter(profile__company=company, is_active=True, profile__is_active_employee=True).count()


def billing_reason(subscription):
    company = subscription.company
    if company.billing_disabled or company.status == 'INTERNAL' or subscription.plan.code == 'INTERNAL':
        return 'Internal / not billable'
    if company.status in ('TRIAL_ACTIVE', 'TRIAL_EXPIRED') or subscription.plan.code == 'TRIAL':
        return 'Trial subscriptions are not billed'
    if company.status != 'ACTIVE' or subscription.status != 'ACTIVE':
        return 'An active company and subscription are required'
    if company.plan_id != subscription.plan_id:
        return 'Company and subscription plans differ; Super Admin must configure the subscription'
    if subscription.billing_cycle not in ('MONTHLY', 'ANNUAL'):
        return 'Select a monthly or annual billing cycle'
    if subscription.price_per_user <= 0:
        return 'No billable rate is configured'
    return ''


def period_end(start, cycle):
    months = 12 if cycle == 'ANNUAL' else 1
    index = start.year * 12 + start.month - 1 + months
    year, month = divmod(index, 12)
    if year > 9999:
        raise ValidationError({'billing_period_start': 'Choose an earlier date.'})
    return date(year, month + 1, min(start.day, monthrange(year, month + 1)[1])) - timedelta(days=1)


def estimate(subscription, count):
    multiplier = 12 if subscription.billing_cycle == 'ANNUAL' else 1
    return (subscription.price_per_user * count * multiplier).quantize(Decimal('0.01'))


@transaction.atomic
def configure_subscription(company_id, plan, cycle):
    company = Company.objects.select_for_update().filter(pk=company_id).first()
    if not company:
        raise ValidationError({'company_id': 'Select an existing company.'})
    if company.status in ('TRIAL_ACTIVE', 'TRIAL_EXPIRED'):
        raise ValidationError({'company_id': 'Use Trial Dashboard to convert this trial.'})
    if company.status == 'SUSPENDED':
        raise ValidationError({'company_id': 'Reactivate the company before configuring billing.'})
    if not plan.is_active or plan.code == 'TRIAL':
        raise ValidationError({'plan_id': 'Select an active paid or internal plan.'})
    internal = plan.code == 'INTERNAL'
    if (internal and cycle != 'NONE') or (not internal and cycle not in ('MONTHLY', 'ANNUAL')):
        raise ValidationError({'billing_cycle': 'Internal uses NONE; paid plans use MONTHLY or ANNUAL.'})
    count = active_users(company)
    devices = Device.objects.filter(company=company).exclude(status='BLOCKED').count()
    if count > plan.max_users or devices > plan.max_devices:
        raise ValidationError({'plan_id': 'This plan is below the current user/device count.'})
    company.plan, company.billing_disabled = plan, internal
    company.status = 'INTERNAL' if internal else 'ACTIVE'
    company.allowed_users, company.allowed_devices = plan.max_users, plan.max_devices
    company.screenshot_retention_days = plan.screenshot_retention_days
    company.save()
    sub, _ = Subscription.objects.update_or_create(company=company, defaults={
        'plan': plan, 'status': 'INTERNAL_NOT_BILLABLE' if internal else 'ACTIVE',
        'billing_cycle': cycle, 'price_per_user': plan.price_per_user, 'active_user_count': count,
    })
    return sub


@transaction.atomic
def create_invoice(subscription_id, start, notes=''):
    sub = Subscription.objects.filter(pk=subscription_id).first()
    if not sub:
        raise ValidationError({'subscription_id': 'Select an existing subscription.'})
    # Company lock serializes invoice generation and subscription/plan changes.
    Company.objects.select_for_update().get(pk=sub.company_id)
    sub = Subscription.objects.select_related('company', 'plan').get(pk=sub.pk)
    reason = billing_reason(sub)
    if reason:
        raise ValidationError({'subscription_id': reason})
    count = active_users(sub.company)
    if count < 1:
        raise ValidationError({'subscription_id': 'No active users to bill.'})
    end = period_end(start, sub.billing_cycle)
    if BillingInvoice.objects.filter(company=sub.company, billing_period_start__lte=end,
                                     billing_period_end__gte=start).exclude(status='VOID').exists():
        raise BillingConflict('A non-void invoice already covers all or part of this period.')
    amount = estimate(sub, count)
    if amount > Decimal('9999999999.99'):
        raise ValidationError({'amount': 'Invoice total exceeds the supported amount.'})
    invoice = BillingInvoice.objects.create(company=sub.company, subscription=sub, status='DRAFT',
        amount=amount, currency='INR', billing_period_start=start, billing_period_end=end, provider='MANUAL',
        line_description=f'{sub.plan.name} subscription', quantity=count, unit_price=sub.price_per_user,
        billing_cycle=sub.billing_cycle, notes=notes)
    # The database ID makes generated numbers stable and unique without rewriting legacy numbers.
    invoice.invoice_number = f'WP-MANUAL-{timezone.localdate():%Y}-{invoice.pk:08d}'
    invoice.save(update_fields=['invoice_number'])
    sub.active_user_count = count
    sub.save(update_fields=['active_user_count', 'updated_at'])
    return invoice


@transaction.atomic
def transition_invoice(invoice_id, action, user, reference='', reason=''):
    company_id = BillingInvoice.objects.values_list('company_id', flat=True).get(pk=invoice_id)
    Company.objects.select_for_update().get(pk=company_id)
    invoice = BillingInvoice.objects.select_for_update().get(pk=invoice_id)
    if action != 'void' and (invoice.provider != 'MANUAL' or invoice.quantity < 1 or not invoice.billing_period_end):
        raise BillingConflict('Legacy placeholders cannot be issued or paid. Void an obsolete placeholder and create a new record.')
    if action == 'issue':
        if invoice.status == 'ISSUED':
            return invoice, False
        if invoice.status != 'DRAFT':
            raise BillingConflict('Only a draft invoice can be issued.')
        if invoice.company.billing_disabled or invoice.company.status != 'ACTIVE':
            raise BillingConflict('This company is not currently billable. Void the draft if it is no longer needed.')
        invoice.status, invoice.issued_at = 'ISSUED', timezone.now()
    elif action == 'record-payment':
        if invoice.status == 'PAID' and invoice.provider_reference == reference:
            return invoice, False
        if invoice.status != 'ISSUED':
            raise BillingConflict('Only an issued invoice can have a payment recorded.')
        invoice.status, invoice.paid_at = 'PAID', timezone.now()
        invoice.provider_reference, invoice.payment_recorded_by = reference, user
    elif action == 'void':
        if invoice.status == 'VOID':
            return invoice, False
        if invoice.status not in ('DRAFT', 'ISSUED'):
            raise BillingConflict('Paid invoices cannot be voided; refunds are not implemented.')
        invoice.status, invoice.voided_at, invoice.void_reason = 'VOID', timezone.now(), reason
    else:
        raise ValidationError('Unknown invoice action.')
    invoice.save()
    return invoice, True
