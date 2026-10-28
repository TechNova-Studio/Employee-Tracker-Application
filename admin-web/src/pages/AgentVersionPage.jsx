import React, { useEffect, useRef, useState } from 'react';
import { api, getStoredUser, normalizeRows } from '../lib/api.js';
import { canManageAgentVersions } from '../lib/access.js';
import { ErrorBox, Field, Hint, Message, PageHeader } from '../components/ui.jsx';

const emptyRule = {
  company: '', platform: 'windows', latest_version: '1.0.0', minimum_supported_version: '1.0.0',
  download_url: '', checksum: '', release_notes: '', is_active: true,
};
const platforms = [
  { value: 'windows', label: 'Windows' },
  { value: 'linux', label: 'Linux' },
  { value: 'darwin', label: 'macOS' },
];

export default function AgentVersionPage() {
  const user = getStoredUser();
  const canManage = canManageAgentVersions(user);
  const isSuperAdmin = user?.profile?.role === 'SUPER_ADMIN';
  const [form, setForm] = useState(emptyRule);
  const [editing, setEditing] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [rows, setRows] = useState([]);
  const [installedVersion, setInstalledVersion] = useState('1.0.0');
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const loadSequence = useRef(0);

  async function load(selectedCompany = form.company) {
    const sequence = ++loadSequence.current;
    try {
      const scope = isSuperAdmin ? (selectedCompany ? `?company_id=${encodeURIComponent(selectedCompany)}` : '?scope=global') : '';
      const result = normalizeRows(await api(`/agent-versions/${scope}`));
      if (sequence === loadSequence.current) { setRows(result); setError(''); }
    } catch (err) { if (sequence === loadSequence.current) setError(err.message); }
  }

  useEffect(() => {
    if (isSuperAdmin) {
      api('/agent-versions/company-options/').then(data => setCompanies(data.companies))
        .catch(err => setError(err.message));
    }
  }, []);

  useEffect(() => {
    setRows([]);
    load();
  }, [form.company]);

  function change(field, value) {
    setForm(current => ({ ...current, [field]: value }));
    setPreview(null);
  }

  function cancelEdit() {
    setEditing(null);
    setForm(current => ({ ...emptyRule, company: current.company }));
  }

  async function submit(event) {
    event.preventDefault(); setMessage(''); setError('');
    if (!/^\d+(\.\d+){0,2}$/.test(form.latest_version) || !/^\d+(\.\d+){0,2}$/.test(form.minimum_supported_version)) {
      setError('Use numeric versions such as 1.2.3.'); return;
    }
    const payload = { ...form };
    if (!isSuperAdmin || !payload.company || editing) delete payload.company;
    setBusy(true);
    try {
      await api(editing ? `/agent-versions/${editing}/` : '/agent-versions/', {
        method: editing ? 'PATCH' : 'POST', body: JSON.stringify(payload),
      });
      setMessage(editing ? 'Version rule updated.' : 'Version rule created.');
      cancelEdit(); setPreview(null);
      await load();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function toggle(rule) {
    setMessage(''); setError(''); setBusy(true);
    try {
      await api(`/agent-versions/${rule.id}/`, {
        method: 'PATCH', body: JSON.stringify({ is_active: !rule.is_active }),
      });
      setMessage(`Rule ${rule.is_active ? 'deactivated' : 'activated'}.`);
      setPreview(null);
      await load();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function checkVersion(event) {
    event.preventDefault(); setError(''); setPreview(null);
    try {
      const query = new URLSearchParams({ platform: form.platform, version: installedVersion.trim() });
      if (isSuperAdmin && form.company) query.set('company_id', form.company);
      setPreview(await api(`/agent/version-check/?${query}`));
    } catch (err) { setError(err.message); }
  }

  const visibleRows = isSuperAdmin
    ? rows.filter(rule => String(rule.company ?? '') === form.company)
    : rows;
  const companyName = id => companies.find(item => String(item.id) === String(id))?.name || `Company #${id}`;

  return (
    <div>
      <PageHeader title="Agent Version Management"><button type="button" onClick={() => load()}>Refresh</button></PageHeader>
      <Hint>Choose a scope and platform. An active company rule overrides the global rule for that company. Deactivate a company rule to use the global rule again. Set the minimum version to require an update; provide a working installer URL so employees can download it.</Hint>
      <Message text={message} /><ErrorBox text={error} />

      {isSuperAdmin && <Field label="Rule scope" value={form.company} onChange={value => {
        setEditing(null); setForm({ ...emptyRule, company: value }); setPreview(null);
      }} selectOptions={[
        { value: '', label: 'Global (all companies without their own rule)' },
        ...companies.map(company => ({ value: String(company.id), label: company.name })),
      ]} />}

      {canManage && <form className="grid-form" onSubmit={submit}>
        <Field label="Platform" value={form.platform} onChange={value => change('platform', value)} selectOptions={platforms} />
        <Field label="Latest version" value={form.latest_version} onChange={value => change('latest_version', value)} />
        <Field label="Minimum supported version" value={form.minimum_supported_version} onChange={value => change('minimum_supported_version', value)} />
        <Field label="Installer download URL" type="url" value={form.download_url} onChange={value => change('download_url', value)} />
        <Field label="SHA-256 checksum (optional)" value={form.checksum} onChange={value => change('checksum', value)} />
        <Field label="Release notes" textarea value={form.release_notes} onChange={value => change('release_notes', value)} />
        <Field label="Active"><input type="checkbox" checked={form.is_active} onChange={event => change('is_active', event.target.checked)} /></Field>
        <div className="action-row">
          <button type="submit" disabled={busy}>{editing ? 'Save changes' : 'Create rule'}</button>
          {editing && <button type="button" onClick={cancelEdit}>Cancel edit</button>}
        </div>
      </form>}

      <form className="inline-form" onSubmit={checkVersion}>
        <Field label="Test installed version" value={installedVersion} onChange={setInstalledVersion} />
        {!canManage && <Field label="Platform" value={form.platform} onChange={value => change('platform', value)} selectOptions={platforms} />}
        <button type="submit">Check effective rule</button>
      </form>
      {preview && <div className="notice" role="status">
        {preview.force_update_required ? 'Update required' : 'Version supported'}: latest {preview.latest_version}, minimum {preview.minimum_supported_version}.
        {preview.download_url && <> <a href={preview.download_url} target="_blank" rel="noreferrer">Installer download</a>.</>}
      </div>}

      <h3>{isSuperAdmin ? (form.company ? `${companyName(form.company)} rules` : 'Global rules') : 'Company and global rules'}</h3>
      {visibleRows.length === 0 ? <div className="empty">No rules for this scope. The server defaults apply if there is no active global rule.</div> : <div className="table-wrap">
        <table><thead><tr><th>Scope</th><th>Platform</th><th>Latest</th><th>Minimum</th><th>Status</th><th>Installer</th><th>Release notes</th>{canManage && <th>Actions</th>}</tr></thead>
          <tbody>{visibleRows.map(rule => {
            const canEdit = canManage && (isSuperAdmin || rule.company !== null);
            return <tr key={rule.id}>
              <td>{rule.company === null ? 'Global' : isSuperAdmin ? companyName(rule.company) : 'My company'}</td>
              <td>{rule.platform}</td><td>{rule.latest_version}</td><td>{rule.minimum_supported_version}</td>
              <td>{rule.is_active ? 'Active' : 'Inactive'}</td>
              <td>{rule.download_url ? <a href={rule.download_url} target="_blank" rel="noreferrer">Download</a> : 'Server default'}</td>
              <td>{rule.release_notes || '—'}</td>
              {canManage && <td>{canEdit && <div className="action-row">
                <button type="button" disabled={busy} onClick={() => {
                  setEditing(rule.id); setForm({ ...rule, company: rule.company == null ? '' : String(rule.company) });
                  setPreview(null); setMessage(''); setError('');
                }}>Edit</button>
                <button type="button" disabled={busy} onClick={() => toggle(rule)}>{rule.is_active ? 'Deactivate' : 'Activate'}</button>
              </div>}</td>}
            </tr>;
          })}</tbody>
        </table>
      </div>}
    </div>
  );
}
