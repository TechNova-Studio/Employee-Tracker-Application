import React, { useEffect, useState } from 'react';
import { api, getStoredUser, normalizeRows } from '../lib/api.js';
import { ErrorBox, Field, Hint, Message, PageHeader, SimpleTable } from '../components/ui.jsx';

export default function DepartmentsPage() {
  const isSuperAdmin = getStoredUser()?.profile?.role === 'SUPER_ADMIN';
  const [companies, setCompanies] = useState([]);
  const [companyId, setCompanyId] = useState('');
  const [name, setName] = useState('');
  const [rows, setRows] = useState([]);
  const [editing, setEditing] = useState(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    api('/departments/company-options/').then(options => {
      setCompanies(options.companies);
      if (options.selected_company_id) setCompanyId(String(options.selected_company_id));
    }).catch(err => setError(err.message));
  }, []);

  async function load(selectedCompany = companyId) {
    if (!selectedCompany) { setRows([]); return; }
    try {
      setRows(normalizeRows(await api(`/departments/?company_id=${encodeURIComponent(selectedCompany)}`)));
    } catch (err) { setError(err.message); }
  }

  useEffect(() => {
    let cancelled = false;
    setRows([]);
    setEditing(null);
    if (companyId) {
      api(`/departments/?company_id=${encodeURIComponent(companyId)}`)
        .then(response => { if (!cancelled) setRows(normalizeRows(response)); })
        .catch(err => { if (!cancelled) setError(err.message); });
    }
    return () => { cancelled = true; };
  }, [companyId]);

  async function create(e) {
    e.preventDefault(); setMessage(''); setError('');
    try {
      if (!companyId) throw new Error('Select a company first.');
      const trimmedName = name.trim();
      if (!trimmedName) throw new Error('Department name is required.');
      const payload = { name: trimmedName, is_active: true };
      if (isSuperAdmin) payload.company = companyId;
      await api('/departments/', { method: 'POST', body: JSON.stringify(payload) });
      setName('');
      setMessage('Department created. It is now available in the employee form.');
      await load();
    } catch (err) { setError(err.message); }
  }

  async function update(e) {
    e.preventDefault(); setMessage(''); setError('');
    try {
      const trimmedName = editing.name.trim();
      if (!trimmedName) throw new Error('Department name is required.');
      await api(`/departments/${editing.id}/`, {
        method: 'PATCH', body: JSON.stringify({ name: trimmedName }),
      });
      setEditing(null);
      setMessage('Department renamed.');
      await load();
    } catch (err) { setError(err.message); }
  }

  async function toggle(department) {
    setMessage(''); setError('');
    try {
      await api(`/departments/${department.id}/`, {
        method: 'PATCH', body: JSON.stringify({ is_active: !department.is_active }),
      });
      setMessage(`Department ${department.is_active ? 'deactivated' : 'activated'}.`);
      await load();
    } catch (err) { setError(err.message); }
  }

  return (
    <div>
      <PageHeader title="Departments"><button onClick={() => load()}>Refresh</button></PageHeader>
      <Hint>Select a company to create and manage its departments. Deactivated departments are hidden from the employee add form; existing employee assignments remain.</Hint>
      <Message text={message} /><ErrorBox text={error} />
      <Field label="Company" value={companyId}
        selectOptions={[{ value: '', label: 'Select company' }, ...companies.map(company => ({ value: company.id, label: company.name }))]}
        onChange={value => setCompanyId(value)} />
      <form className="inline-form" onSubmit={create}>
        <Field label="Department name" value={name} onChange={setName} />
        <button type="submit" disabled={!companyId}>Create Department</button>
      </form>
      {editing && <form className="inline-form" onSubmit={update}>
        <Field label="Rename department" value={editing.name}
          onChange={value => setEditing({ ...editing, name: value })} />
        <button type="submit">Save</button>
        <button type="button" onClick={() => setEditing(null)}>Cancel</button>
      </form>}
      <SimpleTable rows={rows} actions={department => <div className="action-row">
        <button onClick={() => setEditing({ id: department.id, name: department.name })}>Rename</button>
        <button onClick={() => toggle(department)}>{department.is_active ? 'Deactivate' : 'Activate'}</button>
      </div>} />
    </div>
  );
}
