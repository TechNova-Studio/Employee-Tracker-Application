import React, { useEffect, useState } from 'react';
import { api, getStoredUser, normalizeRows } from '../lib/api.js';
import { Card, ErrorBox, Field, Hint, Message, PageHeader } from '../components/ui.jsx';
import { dateTime, Dialog, label, localDate, Pager, queryString, useRows } from '../components/DataView.jsx';

const codes = ['INTERNAL', 'TRIAL', 'BASIC', 'PRO', 'BUSINESS', 'ENTERPRISE'];
const money = (value, currency = 'INR') => {
  if (value === null || value === undefined) return '—';
  try { return new Intl.NumberFormat('en-IN', { style: 'currency', currency }).format(Number(value)); }
  catch { return `${currency} ${Number(value).toFixed(2)}`; }
};
const defaultPlan = () => ({ code: '', name: '', price_per_user: 0, max_users: 10, max_devices: 10, screenshot_retention_days: 30, ai_enabled: true, erp_connector_enabled: false, is_active: true });

function InvoiceDetail({ row, close }) {
  return <Dialog title={row.invoice_number || `Billing record #${row.id}`} onClose={close}>
    <p><strong>{row.company_name}</strong> · <span className="badge">{label(row.status)}</span></p>
    <Hint>Internal billing record. Taxes and online payment collection are not included.</Hint>
    <dl className="detail-list"><dt>Description</dt><dd>{row.line_description || 'Legacy placeholder'}</dd>
      <dt>Billing period</dt><dd>{row.billing_period_start || '—'} to {row.billing_period_end || '—'}</dd>
      <dt>Calculation</dt><dd>{row.quantity} users × {money(row.unit_price, row.currency)} / month × {row.billing_cycle === 'ANNUAL' ? 12 : 1} month(s)</dd>
      <dt>Total</dt><dd><strong>{money(row.amount, row.currency)}</strong></dd><dt>Created</dt><dd>{dateTime(row.created_at)}</dd>
      <dt>Issued</dt><dd>{dateTime(row.issued_at)}</dd><dt>Payment recorded</dt><dd>{dateTime(row.paid_at)}</dd>
      <dt>Payment reference</dt><dd>{row.provider_reference || '—'}</dd><dt>Recorded by</dt><dd>{row.payment_recorded_by_email || '—'}</dd>
      <dt>Voided</dt><dd>{dateTime(row.voided_at)}</dd><dt>Void reason</dt><dd>{row.void_reason || '—'}</dd><dt>Notes</dt><dd>{row.notes || '—'}</dd></dl>
  </Dialog>;
}

export default function BillingPage() {
  const user = getStoredUser(); const canManage = user?.profile?.role === 'SUPER_ADMIN';
  const [companyId, setCompanyId] = useState(canManage ? '' : String(user?.profile?.company || ''));
  const [options, setOptions] = useState({ companies: [], plans: [] }); const [plans, setPlans] = useState([]); const [overview, setOverview] = useState(null);
  const [reload, setReload] = useState(0); const [overviewError, setOverviewError] = useState('');
  const [subPage, setSubPage] = useState(1); const [invoicePage, setInvoicePage] = useState(1); const [invoiceStatus, setInvoiceStatus] = useState('');
  const [modal, setModal] = useState(null); const [form, setForm] = useState({}); const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(''); const [error, setError] = useState('');
  const subs = useRows(`/subscriptions/?${queryString({ company_id: companyId, page: subPage })}`);
  const invoices = useRows(`/billing-invoices/?${queryString({ company_id: companyId, page: invoicePage, status: invoiceStatus })}`);
  useEffect(() => {
    let active = true; setOverviewError(''); setOverview(null);
    Promise.all([api('/subscriptions/form-options/'), api(`/subscriptions/overview/?${queryString({ company_id: companyId })}`), api('/plans/')]).then(([choices, totals, available]) => {
      if (active) { setOptions(choices); setOverview(totals); setPlans(normalizeRows(available)); }
    }).catch(e => { if (active) setOverviewError(e.message); });
    return () => { active = false; };
  }, [companyId, reload]);
  const refresh = () => { subs.refresh(); invoices.refresh(); setReload(v => v + 1); };
  const patch = key => value => setForm(f => ({ ...f, [key]: value }));
  function open(type, row = null) {
    setError(''); setModal({ type, row });
    if (type === 'plan') setForm(row ? { ...row } : defaultPlan());
    if (type === 'subscription') setForm({ company_id: row?.company || companyId, plan_id: row?.plan || '', billing_cycle: row?.billing_cycle || 'MONTHLY' });
    if (type === 'draft') setForm({ subscription_id: row.id, billing_period_start: localDate().slice(0, 7) + '-01', notes: '' });
    if (['issue', 'record-payment', 'void'].includes(type)) setForm({ reference: '', reason: '' });
  }
  async function save(e) {
    e.preventDefault(); setBusy(true); setError(''); setMessage('');
    try {
      if (modal.type === 'plan') {
        const fields = ['code', 'name', 'price_per_user', 'max_users', 'max_devices', 'screenshot_retention_days', 'is_active'];
        await api(modal.row ? `/plans/${modal.row.id}/` : '/plans/', { method: modal.row ? 'PATCH' : 'POST', body: JSON.stringify(Object.fromEntries(fields.map(key => [key, form[key]]))) });
        setMessage('Plan saved. Existing subscriptions keep their rate until reconfigured.');
      } else if (modal.type === 'subscription') {
        await api('/subscriptions/configure/', { method: 'POST', body: JSON.stringify(form) }); setMessage('Subscription and company plan limits updated.');
      } else if (modal.type === 'draft') {
        const invoice = await api('/billing-invoices/', { method: 'POST', body: JSON.stringify(form) }); setMessage(`Draft ${invoice.invoice_number} created for ${money(invoice.amount, invoice.currency)}.`);
      } else {
        await api(`/billing-invoices/${modal.row.id}/${modal.type}/`, { method: 'POST', body: JSON.stringify(modal.type === 'record-payment' ? { reference: form.reference } : modal.type === 'void' ? { reason: form.reason } : {}) });
        setMessage(modal.type === 'record-payment' ? 'Full payment recorded manually. No money was collected by this action.' : modal.type === 'issue' ? 'Invoice issued. No email or payment request has been sent.' : 'Invoice voided. Its history is retained.');
      }
      setModal(null); if (invoicePage > 1 && invoices.rows.length === 1) setInvoicePage(invoicePage - 1); refresh();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  const eligibleCompanies = options.companies.filter(c => ['ACTIVE', 'INTERNAL'].includes(c.status));
  const selectedPlan = options.plans.find(p => String(p.id) === String(form.plan_id));
  return <div><PageHeader title="Billing & Subscriptions"><button disabled={busy || subs.loading || invoices.loading} onClick={refresh}>Refresh</button></PageHeader>
    <Hint>Manage subscriptions and internal billing records. Payments are recorded manually; online checkout and tax invoices are not available.</Hint>
    <Message text={message}/><ErrorBox text={error || overviewError || subs.error || invoices.error}/>
    {canManage && <div className="grid-form"><Field label="Company" value={companyId} onChange={v => { setCompanyId(v); setSubPage(1); setInvoicePage(1); }}
      selectOptions={[{ value: '', label: 'All companies' }, ...options.companies.map(c => ({ value: c.id, label: c.name }))]}/></div>}
    {overview && <><div className="cards"><Card title="Subscriptions" value={overview.subscriptions}/><Card title="Active paid" value={overview.active_subscriptions}/><Card title="Trial" value={overview.trial_subscriptions}/><Card title="Internal / not billable" value={overview.internal_subscriptions}/></div>
      {!!overview.invoice_totals.length && <div className="cards">{overview.invoice_totals.map(item => <Card key={`${item.currency}-${item.status}`} title={`${label(item.status)} · ${item.count} records`} value={money(item.amount, item.currency)}/>)}</div>}</>}
    <div className="section-heading"><h3>Subscriptions</h3>{canManage && <button onClick={() => open('subscription')}>Configure subscription</button>}</div>
    <p className="small">The estimate uses current active users. Annual billing uses 12 monthly rates. Convert trial companies from Trial Dashboard.</p>
    <Pager data={subs} page={subPage} setPage={setSubPage}/>
    {!subs.loading && !subs.rows.length && !subs.error && <div className="empty">No subscriptions found.{canManage ? ' Configure an active company or convert its trial.' : 'Contact your administrator to configure billing.'}</div>}
    {!!subs.rows.length && <div className="table-wrap"><table><thead><tr>{['Company', 'Plan / status', 'Cycle', 'Monthly rate / user', 'Active users', 'Estimate', 'Actions'].map(v => <th key={v}>{v}</th>)}</tr></thead><tbody>
      {subs.rows.map(row => <tr key={row.id}><td>{row.company_name}</td><td>{row.plan_name}<div className="small">{label(row.status)}</div></td><td>{label(row.billing_cycle)}</td><td>{money(row.price_per_user)}</td><td>{row.live_user_count}</td>
        <td>{row.is_billable ? money(row.estimated_amount) : <span className="small">{row.billing_reason}</span>}</td><td>{canManage && <div className="action-row">{['ACTIVE', 'INTERNAL'].includes(row.company_status) && <button onClick={() => open('subscription', row)}>Configure</button>}{row.is_billable && <button onClick={() => open('draft', row)}>Create draft</button>}</div>}</td></tr>)}
    </tbody></table></div>}
    <h3>Billing records</h3><div className="grid-form"><Field label="Invoice status" value={invoiceStatus} onChange={v => { setInvoiceStatus(v); setInvoicePage(1); }} selectOptions={[{ value: '', label: 'All statuses' }, ...['DRAFT', 'ISSUED', 'PAID', 'VOID'].map(v => ({ value: v, label: label(v) }))]}/></div>
    <Pager data={invoices} page={invoicePage} setPage={setInvoicePage}/>
    {!invoices.loading && !invoices.rows.length && !invoices.error && <div className="empty">No billing records match these filters.</div>}
    {!!invoices.rows.length && <div className="table-wrap"><table><thead><tr>{['Number', 'Company', 'Period', 'Amount', 'Status', 'Actions'].map(v => <th key={v}>{v}</th>)}</tr></thead><tbody>
      {invoices.rows.map(row => <tr key={row.id}><td>{row.invoice_number || `Record #${row.id}`}</td><td>{row.company_name}</td><td>{row.billing_period_start || '—'} → {row.billing_period_end || '—'}</td><td>{money(row.amount, row.currency)}</td><td><span className="badge">{label(row.status)}</span></td><td><div className="action-row">
        <button onClick={() => open('detail', row)}>View</button>{canManage && row.provider === 'MANUAL' && row.quantity > 0 && <>{row.status === 'DRAFT' && <button onClick={() => open('issue', row)}>Issue</button>}{row.status === 'ISSUED' && <button onClick={() => open('record-payment', row)}>Record payment</button>}</>}{canManage && ['DRAFT', 'ISSUED'].includes(row.status) && <button className="danger" onClick={() => open('void', row)}>Void</button>}
      </div></td></tr>)}
    </tbody></table></div>}
    <div className="section-heading"><h3>Plan catalogue</h3>{canManage && <button disabled={plans.length >= codes.length} onClick={() => open('plan')}>Add plan</button>}</div>
    <div className="cards">{plans.map(plan => <section key={plan.id} className="card"><h4>{plan.name} <span className="small">({plan.code})</span></h4><strong>{money(plan.price_per_user)}</strong><p className="small">per user / month · {plan.is_active ? 'Available' : 'Inactive'}</p><p>{plan.max_users} users · {plan.max_devices} devices</p><p className="small">{plan.screenshot_retention_days}-day screenshot retention</p>{canManage && <button onClick={() => open('plan', plan)}>Edit plan</button>}</section>)}</div>
    {modal?.type === 'detail' && <InvoiceDetail row={modal.row} close={() => setModal(null)}/>}
    {modal && modal.type !== 'detail' && <Dialog title={({ plan: modal.row ? 'Edit plan' : 'Add plan', subscription: 'Configure subscription', draft: 'Create billing draft', issue: 'Issue billing record', 'record-payment': 'Record a received payment', void: 'Void billing record' })[modal.type]} onClose={() => !busy && setModal(null)}>
      <form className="grid-form" onSubmit={save}>
        {modal.type === 'plan' && <><Field label="Plan code" value={form.code} disabled={!!modal.row} required onChange={v => setForm(f => ({ ...f, code: v, price_per_user: ['INTERNAL', 'TRIAL'].includes(v) ? 0 : f.price_per_user }))}
          selectOptions={[{ value: '', label: 'Select plan code' }, ...codes.filter(c => c === modal.row?.code || !plans.some(p => p.code === c))]}/>
          <Field label="Plan name" value={form.name} onChange={patch('name')} required maxLength={100}/><Field label="Monthly rate per user (INR)" type="number" value={form.price_per_user} onChange={patch('price_per_user')} min={0} step="0.01" required disabled={['INTERNAL', 'TRIAL'].includes(form.code)}/>
          <Field label="Maximum users" type="number" value={form.max_users} onChange={patch('max_users')} min={1} max={100000} required/><Field label="Maximum devices" type="number" value={form.max_devices} onChange={patch('max_devices')} min={1} max={100000} required/>
          <Field label="Screenshot retention (days)" type="number" value={form.screenshot_retention_days} onChange={patch('screenshot_retention_days')} min={1} max={3650} required/>
          <Field label="Availability"><span className="checkbox-field"><input type="checkbox" checked={!!form.is_active} onChange={e => patch('is_active')(e.target.checked)}/>Available for new subscriptions</span></Field></>}
        {modal.type === 'subscription' && <><Field label="Company" value={form.company_id} onChange={patch('company_id')} required selectOptions={[{ value: '', label: 'Select an active company' }, ...eligibleCompanies.map(c => ({ value: c.id, label: c.name }))]}/>
          <Field label="Plan" value={form.plan_id} required onChange={v => { const plan = options.plans.find(p => String(p.id) === v); setForm(f => ({ ...f, plan_id: v, billing_cycle: plan?.code === 'INTERNAL' ? 'NONE' : 'MONTHLY' })); }} selectOptions={[{ value: '', label: 'Select plan' }, ...options.plans.map(p => ({ value: p.id, label: `${p.name} · ${money(p.price_per_user)} / user / month` }))]}/>
          <Field label="Billing cycle" value={form.billing_cycle} onChange={patch('billing_cycle')} selectOptions={selectedPlan?.code === 'INTERNAL' ? [{ value: 'NONE', label: 'Not billable' }] : [{ value: 'MONTHLY', label: 'Monthly' }, { value: 'ANNUAL', label: 'Annual (12 months)' }]}/>
          <p className="small">Saving applies the selected plan's rate, user/device limits and retention period. Existing invoice amounts remain unchanged.</p></>}
        {modal.type === 'draft' && <><p>{modal.row.company_name} · {modal.row.plan_name}<br/>Current estimate: <strong>{money(modal.row.estimated_amount)}</strong></p><Field label="Billing period starts" type="date" value={form.billing_period_start} onChange={patch('billing_period_start')} required/>
          <Field label="Notes" textarea value={form.notes} onChange={patch('notes')} maxLength={2000}/><p className="small">The end date and amount are calculated from the current subscription and active users. Overlapping periods are blocked.</p></>}
        {['issue', 'record-payment', 'void'].includes(modal.type) && <p><strong>{modal.row.invoice_number}</strong><br/>{modal.row.company_name} · {money(modal.row.amount, modal.row.currency)}</p>}
        {modal.type === 'issue' && <p>Issue this draft with its recorded amount and period?</p>}
        {modal.type === 'record-payment' && <><p>Record the full amount as already received outside WorkPulse. This action does not collect money.</p><Field label="Bank / payment receipt reference" value={form.reference} onChange={patch('reference')} required maxLength={255}/></>}
        {modal.type === 'void' && <Field label="Reason for voiding" textarea value={form.reason} onChange={patch('reason')} required maxLength={2000}/>}
        <ErrorBox text={error}/><div><button disabled={busy} className={modal.type === 'void' ? 'danger' : ''}>{busy ? 'Saving…' : ({ plan: 'Save plan', subscription: 'Save subscription', draft: 'Create draft', issue: 'Issue', 'record-payment': 'Confirm payment received', void: 'Void record' })[modal.type]}</button><button type="button" disabled={busy} onClick={() => setModal(null)}>Back</button></div>
      </form>
    </Dialog>}
  </div>;
}
