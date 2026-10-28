import React, { useEffect, useState } from 'react';
import { api, getStoredUser, normalizeRows } from '../lib/api.js';
import { Card, ErrorBox, Field, Hint, Message, PageHeader } from '../components/ui.jsx';
import { dateTime, Dialog, label, Pager, queryString, useRows } from '../components/DataView.jsx';

export default function TrialDashboardPage() {
  const isSuper = getStoredUser()?.profile?.role === 'SUPER_ADMIN';
  const [summary, setSummary] = useState(null); const [plans, setPlans] = useState([]); const [refreshKey, setRefreshKey] = useState(0);
  const [page, setPage] = useState(1); const [status, setStatus] = useState(''); const [search, setSearch] = useState('');
  const [action, setAction] = useState(''); const [target, setTarget] = useState(null); const [days, setDays] = useState(5); const [planCode, setPlanCode] = useState(''); const [cycle, setCycle] = useState('MONTHLY'); const [notes, setNotes] = useState('');
  const [message, setMessage] = useState(''); const [error, setError] = useState(''); const [overviewError, setOverviewError] = useState(''); const [busy, setBusy] = useState(false);
  const data = useRows(`/trial/companies/?${queryString({ page, status, search })}`);
  useEffect(() => {
    let active = true; setOverviewError('');
    Promise.all([api('/trial/dashboard/'), api('/plans/')]).then(([stats, available]) => {
      if (active) { setSummary(stats); setPlans(normalizeRows(available).filter(p => p.is_active && p.code !== 'TRIAL' && (isSuper || p.code !== 'INTERNAL'))); }
    }).catch(e => { if (active) setOverviewError(e.message); });
    return () => { active = false; };
  }, [refreshKey, isSuper]);
  const refresh = () => { data.refresh(); setRefreshKey(k => k + 1); };
  const eligible = data.rows.filter(r => ['TRIAL_ACTIVE', 'TRIAL_EXPIRED'].includes(r.status));
  const open = (name, row) => { setAction(name); setTarget(row); setDays(5); setPlanCode(''); setCycle('MONTHLY'); setNotes(''); setError(''); };
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError(''); setMessage('');
    try {
      await api(`/trial/${action}/`, { method: 'POST', body: JSON.stringify({ company_id: target.id, ...(action === 'extend' ? { days } : action === 'convert' ? { plan_code: planCode, billing_cycle: cycle, notes } : {}) }) });
      setMessage(action === 'convert' ? `${target.name} converted. Subscription and plan limits updated; payment is not collected by this action.` : action === 'extend' ? `${target.name} trial extended by ${days} days.` : `${target.name} trial cancelled. Running sessions have stopped.`);
      setTarget(null); if (page > 1 && data.rows.length === 1) setPage(page - 1); else data.refresh(); setRefreshKey(k => k + 1);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <div><PageHeader title="Trial Dashboard"><button disabled={data.loading || busy} onClick={refresh}>Refresh</button><a className="button-link" href="/trial-signup" target="_blank" rel="noreferrer">Open signup</a></PageHeader>
    <Hint>Manage trial companies assigned to you. Conversion updates the subscription and plan limits. Payment collection must be handled separately.</Hint>
    <Message text={message}/><ErrorBox text={error || overviewError || data.error}/>
    {summary ? <div className="cards">{[['Codes generated', 'codes_generated'], ['Codes redeemed', 'codes_used'], ['Active trials', 'active_trials'], ['Expired trials', 'expired_trials'], ['Cancelled trials', 'cancelled_trials'], ['Converted companies', 'converted_trials']].map(([title, key]) => <Card key={key} title={title} value={summary[key]}/>)}<Card title="Conversion rate" value={`${summary.conversion_percent}%`}/></div> : <p>Loading trial overview…</p>}
    <p className="small">Conversion rate = converted companies ÷ activated trial companies. Redeemed codes include codes whose trials were converted or cancelled.</p>
    <div className="grid-form"><Field label="Search company or admin email" value={search} onChange={v => { setSearch(v); setPage(1); }}/>
      <Field label="Company status" value={status} onChange={v => { setStatus(v); setPage(1); }} selectOptions={[{ value: '', label: 'All trial companies' }, ...['TRIAL_ACTIVE', 'TRIAL_EXPIRED', 'ACTIVE', 'INTERNAL', 'SUSPENDED'].map(v => ({ value: v, label: v === 'ACTIVE' ? 'Converted to paid' : v === 'INTERNAL' ? 'Converted to internal' : label(v) }))]}/></div>
    <Pager data={data} page={page} setPage={setPage}/>
    {!data.loading && !data.rows.length && !data.error && <div className="empty">No trial companies match these filters. A customer must redeem a demo code before their company appears here.</div>}
    {!!data.rows.length && <div className="table-wrap"><table><thead><tr>{['Company', 'Plan', 'Status', 'Trial started', 'Trial ends', 'Limits', 'Actions'].map(v => <th key={v}>{v}</th>)}</tr></thead><tbody>
      {data.rows.map(row => <tr key={row.id}><td>{row.name}<div className="small">{row.email}</div></td><td>{row.plan_name || '—'}</td><td><span className="badge">{label(row.status)}</span></td><td>{dateTime(row.trial_start_date)}</td><td>{dateTime(row.trial_end_date)}</td><td>{row.allowed_users} users / {row.allowed_devices} devices</td><td>
        {['TRIAL_ACTIVE', 'TRIAL_EXPIRED'].includes(row.status) ? <div className="action-row"><button onClick={() => open('extend', row)}>Extend</button><button onClick={() => open('convert', row)}>Convert</button><button className="danger" onClick={() => open('cancel', row)}>Cancel trial</button></div> : <span className="small">{row.status === 'SUSPENDED' ? 'Cancelled' : 'Converted'}</span>}
      </td></tr>)}
    </tbody></table></div>}
    {target && <Dialog title={`${action === 'extend' ? 'Extend' : action === 'convert' ? 'Convert' : 'Cancel'} trial`} onClose={() => !busy && setTarget(null)}>
      <form className="grid-form" onSubmit={submit}>
        <Field label="Trial company" value={target.id} onChange={id => setTarget(eligible.find(c => c.id === Number(id)) || target)} required disabled={busy}
          selectOptions={eligible.map(c => ({ value: c.id, label: `${c.name} — ${label(c.status)}` }))}/>
        {action === 'extend' && <><Field label="Additional days" type="number" value={days} onChange={setDays} min={1} max={90} required/><p className="small">Expired trials extend from now; active trials extend from their current end date.</p></>}
        {action === 'convert' && <><Field label="Target plan" value={planCode} onChange={v => { setPlanCode(v); setCycle(v === 'INTERNAL' ? 'NONE' : 'MONTHLY'); }} required
          selectOptions={[{ value: '', label: 'Select an active plan' }, ...plans.map(p => ({ value: p.code, label: `${p.name} · ${p.max_users} users / ${p.max_devices} devices` }))]}/>
          <Field label="Billing cycle" value={cycle} onChange={setCycle} selectOptions={planCode === 'INTERNAL' ? [{ value: 'NONE', label: 'Not billable' }] : [{ value: 'MONTHLY', label: 'Monthly' }, { value: 'ANNUAL', label: 'Annual' }]}/>
          <Field label="Conversion notes" value={notes} onChange={setNotes} textarea maxLength={2000}/>{!plans.length && <ErrorBox text="No eligible active plans are configured."/>}</>}
        {action === 'cancel' && <p>Cancel this trial and stop its running work sessions? Existing records are retained.</p>}
        <ErrorBox text={error}/><div><button className={action === 'cancel' ? 'danger' : ''} disabled={busy || (action === 'convert' && !planCode)}>{busy ? 'Saving…' : action === 'extend' ? 'Extend trial' : action === 'convert' ? 'Confirm conversion' : 'Cancel trial'}</button><button type="button" disabled={busy} onClick={() => setTarget(null)}>Back</button></div>
      </form></Dialog>}
  </div>;
}
