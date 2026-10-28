import React from 'react';

export function Message({ text }) { return text ? <div className="notice">{text}</div> : null; }
export function ErrorBox({ text }) { return text ? <div className="error">{text}</div> : null; }
export function Hint({ children }) { return <div className="hint">{children}</div>; }
export function Card({ title, value }) { return <div className="card"><div>{title}</div><strong>{value ?? 0}</strong></div>; }

export function Field({ label, value, onChange, type = 'text', textarea = false, selectOptions = null, children, ...props }) {
  if (children) return <label>{label}{children}</label>;
  if (selectOptions) {
    return <label>{label}<select {...props} value={value ?? ''} onChange={e => onChange(e.target.value)}>{selectOptions.map(opt => <option key={opt.value ?? opt} value={opt.value ?? opt}>{opt.label ?? opt}</option>)}</select></label>;
  }
  if (textarea) return <label>{label}<textarea {...props} value={value ?? ''} onChange={e => onChange(e.target.value)} /></label>;
  return <label>{label}<input {...props} type={type} value={value ?? ''} onChange={e => onChange(type === 'number' ? (e.target.value === '' ? '' : Number(e.target.value)) : e.target.value)} /></label>;
}

export function renderCell(v) {
  if (v === null || v === undefined) return '';
  if (typeof v === 'object') return JSON.stringify(v).slice(0, 180);
  return String(v).slice(0, 180);
}

export function SimpleTable({ rows, actions }) {
  if (!rows || rows.length === 0) return <div className="empty">No records.</div>;
  const cols = Object.keys(rows[0]).filter(c => !['file', 'object_key'].includes(c));
  return <div className="table-wrap"><table><thead><tr>{cols.map(c => <th key={c}>{c}</th>)}{actions && <th>Actions</th>}</tr></thead><tbody>{rows.map((r, i) => <tr key={r.id || i}>{cols.map(c => <td key={c}>{renderCell(r[c])}</td>)}{actions && <td>{actions(r)}</td>}</tr>)}</tbody></table></div>;
}

export function PageHeader({ title, children }) { return <div className="page-header"><h2>{title}</h2>{children}</div>; }
