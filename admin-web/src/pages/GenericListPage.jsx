import React, { useEffect, useState } from 'react';
import { api, normalizeRows } from '../lib/api.js';
import { ErrorBox, Hint, PageHeader, SimpleTable } from '../components/ui.jsx';

export default function GenericListPage({ endpoint, title, hint }) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');
  async function load() { setError(''); try { setRows(normalizeRows(await api(`/${endpoint}/`))); } catch (e) { setError(e.message); } }
  useEffect(() => { load(); }, [endpoint]);
  return <div><PageHeader title={title}><button onClick={load}>Refresh</button></PageHeader>{hint && <Hint>{hint}</Hint>}<ErrorBox text={error}/><SimpleTable rows={rows}/></div>;
}
