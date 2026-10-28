import React, { useEffect, useRef, useState } from 'react';
import { api, getStoredUser, normalizeRows } from '../lib/api.js';
import { ErrorBox, Field, Hint, PageHeader } from '../components/ui.jsx';

const time = value => value ? new Date(value).toLocaleString() : '—';
const duration = value => {
  const seconds = Number(value) || 0;
  return `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m ${seconds % 60}s`;
};

export default function OperationsPage({ kind }) {
  const sessions = kind === 'sessions';
  const isSuperAdmin = getStoredUser()?.profile?.role === 'SUPER_ADMIN';
  const [companyId, setCompanyId] = useState('');
  const [userId, setUserId] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [companies, setCompanies] = useState([]);
  const [users, setUsers] = useState([]);
  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [error, setError] = useState('');
  const sequence = useRef(0);

  async function load() {
    const current = ++sequence.current;
    if (fromDate && toDate && fromDate > toDate) {
      setRows([]); setCount(0); setHasNext(false);
      setError('End date must not precede start date.'); return;
    }
    const query = new URLSearchParams({ page: String(page) });
    if (companyId) query.set('company_id', companyId);
    if (userId) query.set('user_id', userId);
    if (fromDate) query.set('from_date', fromDate);
    if (toDate) query.set('to_date', toDate);
    if (status) query.set(sessions ? 'status' : 'productivity', status);
    try {
      const response = await api(`/${kind}/?${query}`);
      if (current !== sequence.current) return;
      setRows(normalizeRows(response));
      setCount(response.count ?? normalizeRows(response).length);
      setHasNext(!!response.next);
      setError('');
    } catch (err) { if (current === sequence.current) setError(err.message); }
  }

  useEffect(() => { load(); }, [kind, companyId, userId, fromDate, toDate, status, page]);
  useEffect(() => {
    let cancelled = false;
    const query = companyId ? `?company_id=${encodeURIComponent(companyId)}` : '';
    api(`/sessions/filter-options/${query}`).then(result => {
      if (!cancelled) { setCompanies(result.companies); setUsers(result.users); }
    }).catch(err => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [companyId]);

  const changeCompany = value => { setCompanyId(value); setUserId(''); setRows([]); setPage(1); };
  const change = setter => value => { setter(value); setPage(1); };
  const title = sessions ? 'Attendance Sessions' : 'Activity Timeline';
  return <div>
    <PageHeader title={title}><button type="button" onClick={load}>Refresh</button></PageHeader>
    <Hint>{sessions
      ? 'Work sessions come from the desktop agent. Active and idle time is recorded by heartbeats during a running session.'
      : 'App and website activity is recorded only during a running desktop session. Mouse and keyboard counts do not include typed content.'}</Hint>
    <ErrorBox text={error} />
    <div className="grid-form">
      {isSuperAdmin && <Field label="Company" value={companyId} onChange={changeCompany}
        selectOptions={[{ value: '', label: 'All companies' }, ...companies.map(c => ({ value: String(c.id), label: c.name }))]} />}
      <Field label="Employee" value={userId} onChange={change(setUserId)}
        selectOptions={[{ value: '', label: 'All visible employees' }, ...users.map(u => ({ value: String(u.id), label: u.email || `User #${u.id}` }))]} />
      <Field label="From date" type="date" value={fromDate} onChange={change(setFromDate)} />
      <Field label="To date" type="date" value={toDate} onChange={change(setToDate)} />
      <Field label={sessions ? 'Session status' : 'Productivity'} value={status} onChange={change(setStatus)}
        selectOptions={[{ value: '', label: 'All' }, ...(sessions ? [
          { value: 'RUNNING', label: 'Running' }, { value: 'STOPPED', label: 'Stopped' },
          { value: 'AUTO_STOPPED', label: 'Auto stopped' },
        ] : [
          { value: 'PRODUCTIVE', label: 'Productive' }, { value: 'NEUTRAL', label: 'Neutral' },
          { value: 'UNPRODUCTIVE', label: 'Unproductive' }, { value: 'UNKNOWN', label: 'Unknown' },
        ])]} />
    </div>
    <p>{count} {sessions ? 'sessions' : 'activity records'} • page {page}</p>
    {rows.length === 0 ? <div className="empty">No records match these filters.</div> : <div className="table-wrap"><table>
      <thead><tr>{(sessions
        ? ['Employee', 'Company', 'Started', 'Stopped', 'Status', 'Active', 'Idle', 'Device']
        : ['Captured', 'Employee', 'Company', 'App', 'Domain', 'Window', 'Category', 'Duration', 'Mouse', 'Keyboard']
      ).map(label => <th key={label}>{label}</th>)}</tr></thead>
      <tbody>{rows.map(row => <tr key={row.id}>
        {sessions ? <>
          <td>{row.user_email}</td><td>{row.company_name}</td><td>{time(row.started_at)}</td>
          <td>{time(row.stopped_at)}</td><td>{row.status}</td>
          <td>{duration(row.active_seconds)}</td><td>{duration(row.idle_seconds)}</td>
          <td>{row.device_name || '—'}</td>
        </> : <>
          <td>{time(row.captured_at)}</td><td>{row.user_email}</td><td>{row.company_name}</td>
          <td>{row.app_name || '—'}</td><td>{row.domain || '—'}</td><td>{row.window_title || '—'}</td>
          <td>{row.productivity}</td><td>{duration(row.duration_seconds)}</td>
          <td>{row.mouse_count}</td><td>{row.keyboard_count}</td>
        </>}</tr>)}</tbody>
    </table></div>}
    <div className="action-row">
      <button type="button" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</button>
      <button type="button" disabled={!hasNext} onClick={() => setPage(p => p + 1)}>Next</button>
    </div>
  </div>;
}
