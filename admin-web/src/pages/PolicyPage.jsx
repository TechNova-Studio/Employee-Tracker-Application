import React, { useEffect, useRef, useState } from 'react';
import { api, getStoredUser, normalizeRows } from '../lib/api.js';
import { ErrorBox, Field, Hint, Message, PageHeader } from '../components/ui.jsx';

const initialPolicy = {
  version: '', title: '', body: '',
  is_active: true,
};
const time = value => value ? new Date(value).toLocaleString() : '—';

export default function PolicyPage() {
  const isSuperAdmin = getStoredUser()?.profile?.role === 'SUPER_ADMIN';
  const [companies, setCompanies] = useState([]);
  const [companyId, setCompanyId] = useState('');
  const [form, setForm] = useState(initialPolicy);
  const [policies, setPolicies] = useState([]);
  const [acceptances, setAcceptances] = useState([]);
  const [policyPage, setPolicyPage] = useState(1);
  const [acceptancePage, setAcceptancePage] = useState(1);
  const [policyCount, setPolicyCount] = useState(0);
  const [acceptanceCount, setAcceptanceCount] = useState(0);
  const [morePolicies, setMorePolicies] = useState(false);
  const [moreAcceptances, setMoreAcceptances] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const sequence = useRef(0);

  useEffect(() => {
    api('/policies/company-options/').then(result => {
      setCompanies(result.companies);
      if (!isSuperAdmin && result.companies.length) setCompanyId(String(result.companies[0].id));
    }).catch(err => setError(err.message));
  }, []);

  async function load(selectedCompany = companyId) {
    const current = ++sequence.current;
    if (!selectedCompany) { setPolicies([]); setAcceptances([]); setPolicyCount(0); setAcceptanceCount(0); return; }
    try {
      const [policyResponse, acceptanceResponse] = await Promise.all([
        api(`/policies/?company_id=${encodeURIComponent(selectedCompany)}&page=${policyPage}`),
        api(`/policy-acceptances/?company_id=${encodeURIComponent(selectedCompany)}&page=${acceptancePage}`),
      ]);
      if (current !== sequence.current) return;
      setPolicies(normalizeRows(policyResponse));
      setAcceptances(normalizeRows(acceptanceResponse));
      setPolicyCount(policyResponse.count ?? normalizeRows(policyResponse).length);
      setAcceptanceCount(acceptanceResponse.count ?? normalizeRows(acceptanceResponse).length);
      setMorePolicies(!!policyResponse.next); setMoreAcceptances(!!acceptanceResponse.next);
      setError('');
    } catch (err) { if (current === sequence.current) setError(err.message); }
  }

  useEffect(() => { load(); }, [companyId, policyPage, acceptancePage]);

  async function submit(event) {
    event.preventDefault(); setError(''); setMessage('');
    if (!companyId) { setError('Select a company.'); return; }
    if (!form.version.trim() || !form.title.trim() || !form.body.trim()) {
      setError('Version, title and policy text are required.'); return;
    }
    setBusy(true);
    try {
      await api('/policies/', { method: 'POST', body: JSON.stringify({
        ...form, ...(isSuperAdmin ? { company: companyId } : {}),
      }) });
      setForm(current => ({ ...current, version: '' }));
      setPolicyPage(1);
      setMessage('Policy published. Employees must accept this version before tracking continues.');
      await load();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function toggle(policy) {
    setMessage(''); setError(''); setBusy(true);
    try {
      await api(`/policies/${policy.id}/`, {
        method: 'PATCH', body: JSON.stringify({ is_active: !policy.is_active }),
      });
      setMessage(policy.is_active ? 'Policy deactivated. Work sessions need an active policy.' : 'Policy activated. Employees must accept it before tracking.');
      await load();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return <div>
    <PageHeader title="Monitoring Policy & Acceptances"><button type="button" onClick={() => load()}>Refresh</button></PageHeader>
    <Hint>Publish a new version to change policy text. Accepted versions stay unchanged as consent records. An active policy is required before the desktop agent can start or continue tracking.</Hint>
    <Message text={message} /><ErrorBox text={error} />
    {isSuperAdmin ? <Field label="Company" value={companyId} onChange={value => {
      setCompanyId(value); setPolicyPage(1); setAcceptancePage(1); setPolicies([]); setAcceptances([]);
      setPolicyCount(0); setAcceptanceCount(0); setMessage('');
    }} selectOptions={[{ value: '', label: 'Select company' }, ...companies.map(c => ({ value: String(c.id), label: c.name }))]} />
      : <p>Company: {companies[0]?.name || 'No company assigned'}</p>}
    <h3>Publish policy version</h3>
    <form className="grid-form" onSubmit={submit}>
      <Field label="Version" value={form.version} onChange={v => setForm({ ...form, version: v })} />
      <Field label="Title" value={form.title} onChange={v => setForm({ ...form, title: v })} />
      <Field label="Policy text" textarea value={form.body} onChange={v => setForm({ ...form, body: v })} />
      <Field label="Activate on publish"><input type="checkbox" checked={form.is_active} onChange={e => setForm({ ...form, is_active: e.target.checked })} /></Field>
      <button type="submit" disabled={busy || !companyId}>Publish version</button>
    </form>

    <h3>Policy versions ({policyCount})</h3>
    {policies.length === 0 ? <div className="empty">No policies for this company.</div> : <div className="table-wrap"><table>
      <thead><tr><th>Version</th><th>Title</th><th>Published</th><th>Status</th><th>Policy text</th><th>Action</th></tr></thead>
      <tbody>{policies.map(row => <tr key={row.id}>
        <td>{row.version}</td><td>{row.title}</td><td>{time(row.created_at)}</td><td>{row.is_active ? 'Active' : 'Inactive'}</td>
        <td><details><summary>View text</summary><pre className="policy-text">{row.body}</pre></details></td>
        <td><button type="button" disabled={busy} onClick={() => toggle(row)}>{row.is_active ? 'Deactivate' : 'Activate'}</button></td>
      </tr>)}</tbody></table></div>}
    <div className="action-row"><button disabled={policyPage === 1} onClick={() => setPolicyPage(p => p - 1)}>Previous</button><button disabled={!morePolicies} onClick={() => setPolicyPage(p => p + 1)}>Next</button></div>

    <h3>Acceptance history ({acceptanceCount})</h3>
    {acceptances.length === 0 ? <div className="empty">No employee responses for this company.</div> : <div className="table-wrap"><table>
      <thead><tr><th>Employee</th><th>Version</th><th>Policy</th><th>Response</th><th>Time</th></tr></thead>
      <tbody>{acceptances.map(row => <tr key={row.id}>
        <td>{row.user_email}</td><td>{row.policy_version}</td><td>{row.policy_title}</td>
        <td>{row.status}</td><td>{time(row.status === 'ACCEPTED' ? row.accepted_at : row.declined_at)}</td>
      </tr>)}</tbody></table></div>}
    <div className="action-row"><button disabled={acceptancePage === 1} onClick={() => setAcceptancePage(p => p - 1)}>Previous</button><button disabled={!moreAcceptances} onClick={() => setAcceptancePage(p => p + 1)}>Next</button></div>
  </div>;
}
