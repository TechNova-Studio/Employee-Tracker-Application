import React, { useEffect, useState } from 'react';
import { api, getStoredUser } from '../lib/api.js';
import { ErrorBox, Field, Hint, Message, PageHeader } from '../components/ui.jsx';
import { dateTime, Dialog, label, Pager, queryString, useRows } from '../components/DataView.jsx';

function futureExpiry() { const date = new Date(Date.now() + 7 * 86400000); date.setMinutes(date.getMinutes() - date.getTimezoneOffset()); return date.toISOString().slice(0, 16); }
const emptyForm = () => ({ customer_company_name: '', contact_person_name: '', mobile_number: '', email: '', trial_duration_days: 7, allowed_users: 5, allowed_devices: 5, expiry_date: futureExpiry(), lead_source: '', remarks: '', single_use: true, sales_owner: getStoredUser().id || '' });
export default function TrialCodesPage() {
  const [form, setForm] = useState(emptyForm); const [options, setOptions] = useState({ owners: [], plans: [] }); const [optionsError, setOptionsError] = useState('');
  const [page, setPage] = useState(1); const [status, setStatus] = useState(''); const [search, setSearch] = useState('');
  const [message, setMessage] = useState(''); const [error, setError] = useState(''); const [created, setCreated] = useState(null); const [cancelRow, setCancelRow] = useState(null); const [busy, setBusy] = useState(false);
  const data = useRows(`/demo-trial-codes/?${queryString({ page, status, search })}`);
  const plan = options.plans[0];
  useEffect(() => { let active = true; api('/demo-trial-codes/form-options/').then(value => { if (active) { setOptions(value); setOptionsError(''); } }).catch(e => { if (active) setOptionsError(e.message); }); return () => { active = false; }; }, []);
  const change = key => value => setForm(f => ({ ...f, [key]: value }));
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError(''); setMessage(''); setCreated(null);
    try {
      const result = await api('/demo-trial-codes/', { method: 'POST', body: JSON.stringify({ ...form, expiry_date: new Date(form.expiry_date).toISOString(), sales_owner: form.sales_owner || undefined, plan: plan.id }) });
      setCreated(result); setForm(emptyForm()); setStatus(''); setSearch(''); setPage(1); await data.refresh();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function cancel() {
    setBusy(true); setError('');
    try { await api(`/demo-trial-codes/${cancelRow.id}/cancel/`, { method: 'POST', body: '{}' }); setCancelRow(null); setMessage('Code cancelled. Existing trial companies remain available in Trial Dashboard.'); if (page > 1 && data.rows.length === 1) setPage(page - 1); else await data.refresh(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  const signupLink = code => `${window.location.origin}/trial-signup?code=${encodeURIComponent(code)}`;
  async function copy(value) { try { await navigator.clipboard.writeText(value); setMessage('Copied to clipboard.'); } catch { setError('Clipboard unavailable. Select and copy the code or signup link manually.'); } }
  return <div><PageHeader title="Demo / Trial Code Generator"><button disabled={data.loading} onClick={data.refresh}>Refresh</button></PageHeader>
    <Hint>Generate a code, share its signup link, then manage the enrolled company from Trial Dashboard. Code expiry controls signup; the trial duration starts when the customer signs up.</Hint>
    <Message text={message}/><ErrorBox text={error || data.error || optionsError}/>
    {created && <section className="created-code"><h3>Demo code ready</h3><p><code>{created.code}</code><button onClick={() => copy(created.code)}>Copy code</button></p>
      <a href={signupLink(created.code)} target="_blank" rel="noreferrer">{signupLink(created.code)}</a><button onClick={() => copy(signupLink(created.code))}>Copy signup link</button>
      <p>{created.trial_duration_days} days · {created.allowed_users} users · {created.allowed_devices} devices · Signup closes {dateTime(created.expiry_date)}</p></section>}
    <h3>Generate a code</h3>
    {!plan && <Hint>{optionsError ? 'Trial setup could not be loaded. Reload this page after checking the connection.' : 'An active TRIAL plan is required. Ask Super Admin to configure it before generating codes.'}</Hint>}
    <form className="grid-form" onSubmit={submit}>
      <Field label="Customer company" value={form.customer_company_name} onChange={change('customer_company_name')} maxLength={255} required/>
      <Field label="Contact name" value={form.contact_person_name} onChange={change('contact_person_name')} maxLength={255}/>
      <Field label="Contact email" type="email" value={form.email} onChange={change('email')} maxLength={254}/>
      <Field label="Mobile number" type="tel" value={form.mobile_number} onChange={change('mobile_number')} maxLength={30}/>
      <Field label="Trial duration (days)" type="number" value={form.trial_duration_days} onChange={change('trial_duration_days')} min={1} max={90} required/>
      <Field label={`Allowed users${plan ? ` (max ${plan.max_users})` : ''}`} type="number" value={form.allowed_users} onChange={change('allowed_users')} min={1} max={plan?.max_users} required/>
      <Field label={`Allowed devices${plan ? ` (max ${plan.max_devices})` : ''}`} type="number" value={form.allowed_devices} onChange={change('allowed_devices')} min={1} max={plan?.max_devices} required/>
      <Field label="Code expiry (your local time)" type="datetime-local" value={form.expiry_date} onChange={change('expiry_date')} required/>
      <Field label="Sales owner" value={form.sales_owner} onChange={change('sales_owner')} required
        selectOptions={[{ value: '', label: 'Select owner' }, ...options.owners.map(u => ({ value: u.id, label: u.email || u.username }))]}/>
      <Field label="Lead source" value={form.lead_source} onChange={change('lead_source')} selectOptions={[{ value: '', label: 'Select source (optional)' }, 'Sales call', 'Website', 'Referral', 'Event', 'Other']}/>
      <Field label="Notes (internal)" value={form.remarks} onChange={change('remarks')} textarea maxLength={2000}/>
      <Field label="Redemption"><span className="checkbox-field"><input type="checkbox" checked={form.single_use} onChange={e => change('single_use')(e.target.checked)}/>One company only</span><span className="small">Uncheck to allow multiple companies to use this code before expiry.</span></Field>
      <button disabled={busy || !plan}>{busy ? 'Saving…' : 'Generate code'}</button>
    </form>
    <h3>Generated codes</h3><div className="grid-form"><Field label="Search code, company or email" value={search} onChange={v => { setSearch(v); setPage(1); }}/>
      <Field label="Status" value={status} onChange={v => { setStatus(v); setPage(1); }} selectOptions={[{ value: '', label: 'All statuses' }, ...['ACTIVE', 'USED', 'EXPIRED', 'CANCELLED', 'CONVERTED'].map(v => ({ value: v, label: label(v) }))]}/></div>
    <Pager data={data} page={page} setPage={setPage}/>
    {!data.loading && !data.rows.length && !data.error && <div className="empty">No codes match these filters.</div>}
    {!!data.rows.length && <div className="table-wrap"><table><thead><tr>{['Code', 'Customer', 'Terms', 'Status', 'Code expires', 'Owner', 'Actions'].map(v => <th key={v}>{v}</th>)}</tr></thead><tbody>
      {data.rows.map(row => <tr key={row.id}><td><code>{row.code}</code><div className="small">{row.single_use ? 'Single use' : 'Multiple companies'}</div></td><td>{row.customer_company_name}<div className="small">{row.email}</div></td>
        <td>{row.trial_duration_days} days<br/>{row.allowed_users} users / {row.allowed_devices} devices</td><td><span className="badge">{label(row.effective_status)}</span></td><td>{dateTime(row.expiry_date)}</td><td>{row.sales_owner_email || row.generated_by_email || '—'}</td>
        <td><div className="action-row">{row.effective_status === 'ACTIVE' && <><button onClick={() => copy(row.code)}>Copy code</button><a className="button-link" href={signupLink(row.code)} target="_blank" rel="noreferrer">Signup</a></>}
          {['ACTIVE', 'EXPIRED'].includes(row.status) && <button className="danger" disabled={busy} onClick={() => { setError(''); setCancelRow(row); }}>Cancel code</button>}</div></td></tr>)}
    </tbody></table></div>}
    {cancelRow && <Dialog title="Cancel demo code?" onClose={() => !busy && setCancelRow(null)}><p>Stop new signups using <strong>{cancelRow.code}</strong>? Enrolled companies will retain their trial status.</p>
      <ErrorBox text={error}/><button className="danger" disabled={busy} onClick={cancel}>{busy ? 'Cancelling…' : 'Cancel code'}</button><button disabled={busy} onClick={() => setCancelRow(null)}>Keep code</button></Dialog>}
  </div>;
}
