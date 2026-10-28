import React, { useEffect, useState } from 'react';
import { api, getStoredUser } from '../lib/api.js';
import { ErrorBox, Field, Hint, Message, PageHeader } from '../components/ui.jsx';
import { dateTime, Dialog, label, Pager, queryString, useRows } from '../components/DataView.jsx';

const employeeEvents = ['erp_user_created', 'erp_user_updated', 'erp_user_active', 'erp_user_inactive'];

export default function ERPConnectorPage() {
  const role = getStoredUser()?.profile?.role; const isSuper = role === 'SUPER_ADMIN'; const canManage = ['SUPER_ADMIN', 'COMPANY_ADMIN'].includes(role);
  const [companyId, setCompanyId] = useState(isSuper ? '' : String(getStoredUser()?.profile?.company || ''));
  const [options, setOptions] = useState({ companies: [], events: [], connectors: [], ingest_url: '' }); const [optionsError, setOptionsError] = useState(''); const [reload, setReload] = useState(0);
  const [connectorPage, setConnectorPage] = useState(1); const [connectorStatus, setConnectorStatus] = useState(''); const [eventPage, setEventPage] = useState(1);
  const [filters, setFilters] = useState({ connector_id: '', status: '', event_type: '', search: '', from_date: '', to_date: '' });
  const [modal, setModal] = useState(null); const [form, setForm] = useState({}); const [secret, setSecret] = useState(null); const [showSecret, setShowSecret] = useState(false);
  const [eventDetail, setEventDetail] = useState(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [message, setMessage] = useState('');
  const connectors = useRows(`/erp-connectors/?${queryString({ company_id: companyId, page: connectorPage, status: connectorStatus })}`);
  const events = useRows(`/erp-events/?${queryString({ company_id: companyId, page: eventPage, ...filters })}`);
  useEffect(() => {
    let active = true; setOptionsError('');
    api(`/erp-connectors/form-options/?${queryString({ company_id: companyId })}`).then(result => { if (active) setOptions(result); }).catch(e => { if (active) setOptionsError(e.message); });
    return () => { active = false; };
  }, [companyId, reload]);
  useEffect(() => {
    if (modal?.type !== 'event') return;
    let active = true; setEventDetail(null);
    api(`/erp-events/${modal.row.id}/`).then(result => { if (active) setEventDetail(result); }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [modal]);
  const refresh = () => { connectors.refresh(); events.refresh(); setReload(v => v + 1); };
  const changeCompany = value => { setCompanyId(value); setConnectorPage(1); setEventPage(1); setFilters(f => ({ ...f, connector_id: '' })); setSecret(null); };
  const filter = key => value => { setFilters(f => ({ ...f, [key]: value })); setEventPage(1); };
  function edit(row = null) {
    setError(''); setModal({ type: 'edit', row });
    setForm(row ? { name: row.name, company: String(row.company), is_active: row.is_active, allowed_event_types: Array.isArray(row.allowed_event_types) ? row.allowed_event_types : [] }
      : { name: '', company: companyId, is_active: true, allowed_event_types: [...employeeEvents] });
  }
  async function copy(text) { try { await navigator.clipboard.writeText(text); setMessage('Copied to clipboard.'); } catch { setError('Clipboard unavailable. Select and copy the value manually.'); } }
  function displaySecret(row, data) { setShowSecret(false); setSecret({ name: row.name, company_name: row.company_name, value: data.api_token }); setModal(null); }
  async function reveal(row) {
    setBusy(true); setError('');
    try { displaySecret(row, await api(`/erp-connectors/${row.id}/reveal-token/`, { method: 'POST', body: '{}' })); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError(''); setMessage('');
    try {
      if (modal.type === 'edit') {
        const payload = { ...form }; if (!isSuper || modal.row) delete payload.company;
        const result = await api(modal.row ? `/erp-connectors/${modal.row.id}/` : '/erp-connectors/', { method: modal.row ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
        if (!modal.row) displaySecret(result, result); else setModal(null);
        setMessage(modal.row ? 'Connector settings saved.' : 'Connector created. Copy the token into your ERP backend configuration.');
      } else if (modal.type === 'toggle') {
        await api(`/erp-connectors/${modal.row.id}/`, { method: 'PATCH', body: JSON.stringify({ is_active: !modal.row.is_active }) });
        setMessage(modal.row.is_active ? 'Connector disabled. Its token cannot receive new events.' : 'Connector enabled.'); setModal(null);
      } else if (modal.type === 'rotate') {
        const result = await api(`/erp-connectors/${modal.row.id}/rotate-token/`, { method: 'POST', body: '{}' });
        displaySecret(modal.row, result); setMessage('Token rotated. Update the ERP backend before sending more events.');
      }
      if (connectorPage > 1 && connectors.rows.length === 1) setConnectorPage(connectorPage - 1); refresh();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  const availableEvents = [...options.events, ...(form.allowed_event_types || []).filter(value => !options.events.some(e => e.value === value)).map(value => ({ value, label: `${value} (custom)`, processing: 'RECEIVED_ONLY' }))];
  const title = modal?.type === 'edit' ? (modal.row ? 'Edit connector' : 'Create ERP connector') : modal?.type === 'rotate' ? 'Rotate connector token?' : modal?.type === 'toggle' ? `${modal.row.is_active ? 'Disable' : 'Enable'} connector?` : 'ERP event details';
  return <div><PageHeader title="ERP Connector Settings"><button disabled={busy || connectors.loading || events.loading} onClick={refresh}>Refresh</button>{canManage && <button onClick={() => edit()}>Create connector</button>}</PageHeader>
    <Hint>ERP sends events to WorkPulse. Employee lifecycle events sync users; business events are stored as Received for review. A received event does not mean its business workflow was processed.</Hint>
    <Message text={message}/><ErrorBox text={error || optionsError || connectors.error || events.error}/>
    <div className="grid-form">{isSuper && <Field label="Company" value={companyId} onChange={changeCompany} selectOptions={[{ value: '', label: 'All companies' }, ...options.companies.map(c => ({ value: c.id, label: c.name }))]}/>}
      <Field label="Connector status" value={connectorStatus} onChange={v => { setConnectorStatus(v); setConnectorPage(1); }} selectOptions={[{ value: '', label: 'All statuses' }, { value: 'ACTIVE', label: 'Active' }, { value: 'INACTIVE', label: 'Inactive' }]}/></div>
    <h3>Connectors</h3><Pager data={connectors} page={connectorPage} setPage={setConnectorPage}/>
    {!connectors.loading && !connectors.rows.length && !connectors.error && <div className="empty">No connectors match these filters.{canManage ? ' Create a connector for your ERP source.' : 'Ask a company administrator to configure the connection.'}</div>}
    {!!connectors.rows.length && <div className="table-wrap"><table><thead><tr>{['Connector', 'Company', 'Status', 'Events', 'Token', 'Last received', 'Actions'].map(v => <th key={v}>{v}</th>)}</tr></thead><tbody>
      {connectors.rows.map(row => <tr key={row.id}><td>{row.name}</td><td>{row.company_name}</td><td><span className="badge">{row.is_active ? 'Active' : 'Inactive'}</span></td><td>{row.allowed_event_types.length} allowed / {row.event_count} received</td><td><code>{row.token_hint}</code><div className="small">Rotated: {dateTime(row.token_rotated_at)}</div></td><td>{row.last_received_at ? dateTime(row.last_received_at) : 'Waiting for first event'}</td><td><div className="action-row">
        <button onClick={() => { setError(''); setModal({ type: 'setup', row }); }}>Setup details</button>
        {canManage && <><button onClick={() => edit(row)}>Edit events</button><button disabled={busy} onClick={() => reveal(row)}>View token</button><button disabled={busy} onClick={() => { setError(''); setModal({ type: 'rotate', row }); }}>Rotate token</button><button disabled={busy} className={row.is_active ? 'danger' : ''} onClick={() => { setError(''); setModal({ type: 'toggle', row }); }}>{row.is_active ? 'Disable' : 'Enable'}</button></>}
      </div></td></tr>)}
    </tbody></table></div>}
    <h3>ERP events</h3><div className="grid-form">
      <Field label="Source connector" value={filters.connector_id} onChange={filter('connector_id')} disabled={isSuper && !companyId} selectOptions={[{ value: '', label: isSuper && !companyId ? 'Select company to choose a connector' : 'All connectors' }, ...options.connectors.map(c => ({ value: c.id, label: c.name }))]}/>
      <Field label="Processing status" value={filters.status} onChange={filter('status')} selectOptions={[{ value: '', label: 'All statuses' }, ...['PROCESSED', 'FAILED', 'RECEIVED', 'PENDING'].map(v => ({ value: v, label: label(v) }))]}/>
      <Field label="Event type" value={filters.event_type} onChange={filter('event_type')} selectOptions={[{ value: '', label: 'All event types' }, ...options.events.map(e => ({ value: e.value, label: e.label }))]}/>
      <Field label="Search CRM ID / email / event type" value={filters.search} onChange={filter('search')}/><Field label="From date" type="date" value={filters.from_date} onChange={filter('from_date')}/><Field label="To date" type="date" value={filters.to_date} onChange={filter('to_date')} min={filters.from_date || undefined}/>
    </div><Pager data={events} page={eventPage} setPage={setEventPage}/>
    {!events.loading && !events.rows.length && !events.error && <div className="empty">No events match these filters. Use Setup details to configure your ERP sender.</div>}
    {!!events.rows.length && <div className="table-wrap"><table><thead><tr>{['Received', 'Company / connector', 'Event type', 'CRM employee ID / reference', 'Result', ''].map((v, i) => <th key={i}>{v}</th>)}</tr></thead><tbody>
      {events.rows.map(row => <tr key={row.id}><td>{dateTime(row.received_at)}</td><td>{row.company_name}<div className="small">{row.connector_name}</div></td><td>{row.event_type}</td><td>{row.external_id || row.employee_id || row.employee_email || '—'}{(row.external_id || row.employee_id) && row.employee_email && <div className="small">{row.employee_email}</div>}</td><td><span className="badge">{label(row.processing_status)}</span>{row.processing_error && <div className="small">{row.processing_error}</div>}</td><td><button onClick={() => { setError(''); setModal({ type: 'event', row }); }}>View details</button></td></tr>)}
    </tbody></table></div>}
    {secret && <Dialog title={`Connector token · ${secret.name}`} onClose={() => { setSecret(null); setShowSecret(false); }}>
      <p>{secret.company_name}</p><Hint>Store this token in your ERP backend configuration. Token views and rotations are logged.</Hint>
      <Field label="API token"><input className="token-input" type={showSecret ? 'text' : 'password'} value={secret.value} readOnly autoComplete="off" onFocus={e => e.target.select()}/></Field>
      <div className="action-row"><button onClick={() => setShowSecret(v => !v)}>{showSecret ? 'Hide' : 'Show'}</button><button onClick={() => copy(secret.value)}>Copy token</button></div><ErrorBox text={error}/><Message text={message}/>
    </Dialog>}
    {modal?.type === 'setup' && <Dialog title={`ERP setup · ${modal.row.name}`} onClose={() => setModal(null)}>
      <p>{modal.row.company_name} · {modal.row.is_active ? 'Active' : 'Disabled'}</p><p>POST events to:</p><pre className="code-block">{options.ingest_url}</pre><button onClick={() => copy(options.ingest_url)}>Copy endpoint</button>
      <pre className="code-block">{'Content-Type: application/json\nX-WORKPULSE-TOKEN: <your connector token>'}</pre>
      <h4>Allowed events</h4><ul>{modal.row.allowed_event_types.map(event => <li key={event}>{event} · {employeeEvents.includes(event) ? 'Employee sync' : 'Received only'}</li>)}</ul>
      <p className="small">Successful delivery is confirmed by an event appearing in the list. Enabling a connector alone does not prove the ERP sender is connected.</p>
      <p>Every employee event requires a top-level external_id: the same stable CRM employee ID used in the import file's employee_id column, with the same case. Use the same connector token for import and future events. Employee creation also requires email:</p><pre className="code-block">{JSON.stringify({ event_type: 'erp_user_created', external_id: 'GLUTAPE0001', payload: { email: '<employee email>', first_name: '<name>', is_active: true } }, null, 2)}</pre>
      <p>After a CRM employee is made inactive, the CRM backend must send this event using that employee's mapped external_id:</p><pre className="code-block">{JSON.stringify({ event_type: 'erp_user_inactive', external_id: 'GLUTAPE0001', payload: { is_active: false } }, null, 2)}</pre>
      <p className="small">Replace the sample ID with the actual imported CRM ID. A successful status update returns status: processed. Department, designation and manager are optional. The Employee ID shown in the employee list is a separate, optional WorkPulse display code.</p>
      <ErrorBox text={error}/><Message text={message}/>
    </Dialog>}
    {modal?.type === 'event' && <Dialog title={`ERP event #${modal.row.id}`} onClose={() => setModal(null)} wide>
      <ErrorBox text={error}/>{eventDetail ? <><p>{eventDetail.company_name} · {eventDetail.connector_name} · <span className="badge">{label(eventDetail.processing_status)}</span></p>
        <dl className="detail-list"><dt>Event type</dt><dd>{eventDetail.event_type}</dd><dt>CRM employee ID / reference</dt><dd>{eventDetail.external_id || '—'}</dd><dt>WorkPulse display code in payload</dt><dd>{eventDetail.employee_id || '—'}</dd><dt>Employee email</dt><dd>{eventDetail.employee_email || '—'}</dd><dt>Received</dt><dd>{dateTime(eventDetail.received_at)}</dd><dt>Processed</dt><dd>{dateTime(eventDetail.processed_at)}</dd></dl>
        {eventDetail.processing_error && <ErrorBox text={eventDetail.processing_error}/>}{eventDetail.processing_status === 'RECEIVED' && <Hint>Stored successfully. This business event has no workflow processor yet.</Hint>}
        <h4>Payload</h4><pre className="code-block">{JSON.stringify(eventDetail.payload, null, 2)}</pre></> : !error && <p>Loading event…</p>}
    </Dialog>}
    {modal && ['edit', 'rotate', 'toggle'].includes(modal.type) && <Dialog title={title} onClose={() => !busy && setModal(null)} wide={modal.type === 'edit'}>
      <form className="grid-form" onSubmit={submit}>
        {modal.type === 'edit' && <><Field label="Connector name" value={form.name} onChange={v => setForm(f => ({ ...f, name: v }))} required maxLength={100}/>
          {isSuper && <Field label="Company" value={form.company} disabled={!!modal.row} required onChange={v => setForm(f => ({ ...f, company: v }))} selectOptions={[{ value: '', label: 'Select company' }, ...options.companies.map(c => ({ value: c.id, label: c.name }))]}/>}
          <Field label="Connection status" value={form.is_active ? 'ACTIVE' : 'INACTIVE'} onChange={v => setForm(f => ({ ...f, is_active: v === 'ACTIVE' }))} selectOptions={[{ value: 'ACTIVE', label: 'Active' }, { value: 'INACTIVE', label: 'Inactive' }]}/>
          <fieldset className="event-picker"><legend>Allowed events</legend><p className="small">Employee events update users. Business events are stored for review.</p><button type="button" onClick={() => setForm(f => ({ ...f, allowed_event_types: [...new Set([...f.allowed_event_types, ...employeeEvents])] }))}>Select employee lifecycle events</button>
            <div className="event-grid">{availableEvents.map(event => <label className="event-option" key={event.value}><input type="checkbox" checked={form.allowed_event_types.includes(event.value)} onChange={e => setForm(f => ({ ...f, allowed_event_types: e.target.checked ? [...f.allowed_event_types, event.value] : f.allowed_event_types.filter(v => v !== event.value) }))}/><span>{event.label}<small>{event.processing === 'PROCESSED' ? 'Employee sync' : 'Received only'}</small></span></label>)}</div>
          </fieldset></>}
        {modal.type === 'rotate' && <p>Replace the token for <strong>{modal.row.name}</strong>? The current token stops working immediately. Update your ERP backend with the new token after rotation.</p>}
        {modal.type === 'toggle' && <p>{modal.row.is_active ? 'Stop accepting new events from' : 'Allow configured events from'} <strong>{modal.row.name}</strong>? Existing events and employee mappings are retained.</p>}
        <ErrorBox text={error}/><div><button disabled={busy || (modal.type === 'edit' && form.is_active && !form.allowed_event_types.length)}>{busy ? 'Saving…' : modal.type === 'rotate' ? 'Rotate token' : modal.type === 'toggle' ? 'Confirm' : 'Save connector'}</button><button type="button" disabled={busy} onClick={() => setModal(null)}>Back</button></div>
      </form>
    </Dialog>}
  </div>;
}
