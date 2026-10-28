import React, { useEffect, useState } from 'react';
import { api, getStoredUser, normalizeRows } from '../lib/api.js';
import { canCloseAlerts } from '../lib/access.js';
import { ErrorBox, Message, PageHeader, SimpleTable } from '../components/ui.jsx';

export default function AlertsPage() {
  const canClose = canCloseAlerts(getStoredUser());
  const [rows, setRows] = useState([]); const [message, setMessage] = useState(''); const [error, setError] = useState('');
  async function load(){ try { setRows(normalizeRows(await api('/alerts/'))); } catch(e){ setError(e.message); } }
  useEffect(()=>{load();}, []);
  async function close(id){ try { await api(`/alerts/${id}/close/`, { method:'POST', body: JSON.stringify({ status:'CLOSED' }) }); setMessage('Alert closed.'); load(); } catch(e){ setError(e.message); } }
  return <div><PageHeader title="Alerts"><button onClick={load}>Refresh</button></PageHeader><Message text={message}/><ErrorBox text={error}/><SimpleTable rows={rows} actions={canClose ? r => <button onClick={() => close(r.id)}>Close</button> : undefined} /></div>;
}
