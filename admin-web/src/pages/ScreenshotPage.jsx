import React, { useEffect, useState } from 'react';
import { downloadBlob, screenshotBlob, api, getStoredUser } from '../lib/api.js';
import { canDeleteScreenshots } from '../lib/access.js';
import { ErrorBox, Hint, Message, PageHeader } from '../components/ui.jsx';
import { dateTime, Dialog, Pager, queryString, ScopeFilters, useRows } from '../components/DataView.jsx';

function Preview({ row, onClose, previous, next, onDownload, downloading }) {
  const [url, setUrl] = useState(''); const [error, setError] = useState(''); const [actualSize, setActualSize] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); let href = ''; let active = true;
    setUrl(''); setError(''); setActualSize(false);
    screenshotBlob(row.id, 'view', controller.signal).then(blob => {
      if (active) { href = URL.createObjectURL(blob); setUrl(href); }
    }).catch(e => { if (active && e.name !== 'AbortError') setError(e.message); });
    return () => { active = false; controller.abort(); if (href) URL.revokeObjectURL(href); };
  }, [row.id]);
  return <Dialog title={`Screenshot · ${row.user_email}`} onClose={onClose} wide>
    <p className="small">{row.company_name} · {dateTime(row.captured_at)} · {row.device_name || 'Device not named'} · Session #{row.session}</p>
    <ErrorBox text={error}/>
    {!url && !error && <p role="status">Loading screenshot…</p>}
    {url && <div className={`screenshot-stage ${actualSize ? 'actual-size' : ''}`}><img src={url} alt={`Desktop captured for ${row.user_email} at ${dateTime(row.captured_at)}`}
      onError={() => setError('This image could not be displayed.')}/></div>}
    <div className="action-row">
      <button type="button" disabled={!previous} onClick={previous}>Previous image</button>
      <button type="button" disabled={!next} onClick={next}>Next image</button>
      <button type="button" disabled={!url} onClick={() => setActualSize(v => !v)}>{actualSize ? 'Fit to screen' : 'Actual size'}</button>
      <button type="button" disabled={downloading} onClick={() => onDownload(row)}>{downloading ? 'Downloading…' : 'Download'}</button>
    </div>
  </Dialog>;
}

export default function ScreenshotPage() {
  const canDelete = canDeleteScreenshots(getStoredUser());
  const [filters, setFilters] = useState({ company_id: '', user_id: '', from_date: '', to_date: '' });
  const [page, setPage] = useState(1); const [selected, setSelected] = useState(null); const [deleteRow, setDeleteRow] = useState(null);
  const [message, setMessage] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [downloading, setDownloading] = useState(false);
  const data = useRows(`/screenshots/?${queryString({ ...filters, page })}`);
  const index = data.rows.findIndex(r => r.id === selected?.id);
  async function download(row) {
    setError(''); setDownloading(true);
    try { const blob = await screenshotBlob(row.id, 'download'); const ext = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp' }[blob.type]; downloadBlob(blob, `workpulse-screenshot-${row.id}.${ext}`); }
    catch (e) { setError(e.message); } finally { setDownloading(false); }
  }
  async function remove() {
    setBusy(true); setError('');
    try { await api(`/screenshots/${deleteRow.id}/soft-delete/`, { method: 'POST', body: '{}' }); setDeleteRow(null); setMessage('Screenshot deleted. The deletion is recorded in the access log.');
      if (data.rows.length === 1 && page > 1) setPage(p => p - 1); else await data.refresh();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <div>
    <PageHeader title="Screenshot Viewer"><button disabled={data.loading} onClick={data.refresh}>Refresh</button></PageHeader>
    <Hint>View screenshots by employee and date. Views, downloads and deletions are logged.</Hint>
    <Message text={message}/><ErrorBox text={error || data.error}/>
    <ScopeFilters endpoint="screenshots" filters={filters} onChange={patch => { setFilters(f => ({ ...f, ...patch })); setPage(1); setSelected(null); }}/>
    <Pager data={data} page={page} setPage={setPage}/>
    {!data.loading && !data.rows.length && !data.error && <div className="empty">No screenshots match these filters. Start an accepted-policy desktop session and wait for the capture interval.</div>}
    {!!data.rows.length && <div className="table-wrap"><table><thead><tr>{['Captured', 'Employee', 'Company', 'Device', 'Session', 'Actions'].map(x => <th key={x}>{x}</th>)}</tr></thead>
      <tbody>{data.rows.map(row => <tr key={row.id}><td>{dateTime(row.captured_at)}</td><td>{row.user_email}</td><td>{row.company_name}</td><td>{row.device_name || '—'}</td><td>#{row.session}</td>
        <td><div className="action-row"><button onClick={() => setSelected(row)}>View screenshot</button><button disabled={downloading} onClick={() => download(row)}>Download</button>
          {canDelete && <button className="danger" onClick={() => { setError(''); setDeleteRow(row); }}>Delete</button>}</div></td></tr>)}</tbody></table></div>}
    {selected && <Preview row={selected} onClose={() => setSelected(null)} onDownload={download} downloading={downloading}
      previous={index > 0 ? () => setSelected(data.rows[index - 1]) : null}
      next={index >= 0 && index < data.rows.length - 1 ? () => setSelected(data.rows[index + 1]) : null}/>}
    {deleteRow && <Dialog title="Delete screenshot?" onClose={() => !busy && setDeleteRow(null)}><p>Remove the screenshot for {deleteRow.user_email}, captured {dateTime(deleteRow.captured_at)}, from the viewer?</p>
      <ErrorBox text={error}/><button className="danger" disabled={busy} onClick={remove}>{busy ? 'Deleting…' : 'Delete screenshot'}</button><button disabled={busy} onClick={() => setDeleteRow(null)}>Keep screenshot</button></Dialog>}
  </div>;
}
