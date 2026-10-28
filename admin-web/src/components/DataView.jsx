import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api, getStoredUser, normalizeRows } from '../lib/api.js';
import { ErrorBox, Field } from './ui.jsx';

export const dateTime = value => value ? new Date(value).toLocaleString() : '—';
export const duration = value => `${Math.floor((Number(value) || 0) / 3600)}h ${Math.floor((Number(value) || 0) % 3600 / 60)}m`;
export const localDate = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
export const queryString = values => new URLSearchParams(Object.entries(values).filter(([, value]) => value !== '' && value != null)).toString();
export const label = value => String(value || '—').replaceAll('_', ' ').toLowerCase();

export function useRows(path) {
  const [data, setData] = useState({ rows: [], count: 0, next: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const sequence = useRef(0);
  const load = useCallback(async () => {
    const seq = ++sequence.current;
    setLoading(true); setError(''); setData({ rows: [], count: 0, next: false });
    try {
      const result = await api(path);
      if (seq === sequence.current) setData({ rows: normalizeRows(result), count: result.count ?? normalizeRows(result).length, next: !!result.next });
    } catch (e) { if (seq === sequence.current) setError(e.message); }
    finally { if (seq === sequence.current) setLoading(false); }
  }, [path]);
  useEffect(() => { load(); return () => { sequence.current++; }; }, [load]);
  return { ...data, loading, error, refresh: load };
}

export function Pager({ data, page, setPage }) {
  return <div className="pager"><span>{data.loading ? 'Loading…' : `${data.count} records · Page ${page}`}</span>
    <button type="button" disabled={data.loading || page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
    <button type="button" disabled={data.loading || !data.next} onClick={() => setPage(page + 1)}>Next</button></div>;
}

export function ScopeFilters({ endpoint, filters, onChange, children }) {
  const [options, setOptions] = useState({ companies: [], users: [] });
  const [error, setError] = useState('');
  const isSuper = getStoredUser()?.profile?.role === 'SUPER_ADMIN';
  useEffect(() => {
    let active = true;
    setOptions(old => ({ ...old, users: [] })); setError('');
    api(`/${endpoint}/filter-options/?${queryString({ company_id: filters.company_id })}`).then(value => {
      if (active) setOptions(value);
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [endpoint, filters.company_id]);
  return <><ErrorBox text={error}/><div className="grid-form">
    {isSuper && <Field label="Company" value={filters.company_id} onChange={v => onChange({ company_id: v, user_id: '' })}
      selectOptions={[{ value: '', label: 'All companies' }, ...options.companies.map(c => ({ value: c.id, label: c.name }))]}/>}
    <Field label="Employee" value={filters.user_id} onChange={v => onChange({ user_id: v })}
      disabled={isSuper && !filters.company_id}
      selectOptions={[{ value: '', label: isSuper && !filters.company_id ? 'Choose a company first' : 'All visible employees' }, ...options.users.map(u => ({ value: u.id, label: u.email || u.username }))]}/>
    <Field label="From date" type="date" value={filters.from_date} onChange={v => onChange({ from_date: v })}/>
    <Field label="To date" type="date" value={filters.to_date} min={filters.from_date || undefined} onChange={v => onChange({ to_date: v })}/>
    {children}
  </div></>;
}

export function Dialog({ title, onClose, children, wide = false }) {
  const ref = useRef(null);
  useEffect(() => { const dialog = ref.current; dialog.showModal(); return () => dialog.close(); }, []);
  return <dialog ref={ref} aria-label={title} className={wide ? 'detail-dialog wide-dialog' : 'detail-dialog'} onCancel={e => { e.preventDefault(); onClose(); }}
    onClick={e => { if (e.target === ref.current) onClose(); }}>
    <div className="dialog-heading"><h3>{title}</h3><button type="button" onClick={onClose} aria-label="Close dialog">Close</button></div>
    {children}
  </dialog>;
}
