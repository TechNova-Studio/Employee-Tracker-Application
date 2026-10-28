import React, { useEffect, useRef, useState } from 'react';
import { api, getStoredUser } from '../lib/api.js';
import { ErrorBox, Field, Hint, Message, PageHeader, SimpleTable } from '../components/ui.jsx';
import { Pager, queryString, useRows } from '../components/DataView.jsx';

const emptyForm = {
  email: '', username: '', first_name: '', last_name: '', password: '',
  role: 'EMPLOYEE', company: '', department: '', manager: '', employee_id: '',
};

export default function UsersPage() {
  const currentRole = getStoredUser()?.profile?.role;
  const isSuperAdmin = currentRole === 'SUPER_ADMIN';
  const canManage = ['SUPER_ADMIN', 'COMPANY_ADMIN', 'HR_ADMIN'].includes(currentRole);
  const [form, setForm] = useState(emptyForm);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [optionsBusy, setOptionsBusy] = useState(false);
  const [optionsRevision, setOptionsRevision] = useState(0);
  const [companies, setCompanies] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [managers, setManagers] = useState([]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [companyFilter, setCompanyFilter] = useState('');
  const formRef = useRef(null);
  const data = useRows(`/users/?${queryString({ page, search, company_id: companyFilter })}`);

  useEffect(() => {
    let cancelled = false;
    if (canManage) {
      api('/users/form-options/').then(options => {
        if (cancelled) return;
        setCompanies(options.companies);
        if (!isSuperAdmin && options.selected_company_id) {
          setForm(previous => ({ ...previous, company: String(options.selected_company_id) }));
        }
      }).catch(err => { if (!cancelled) setError(err.message); });
    }
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setDepartments([]); setManagers([]); setOptionsBusy(false);
    if (canManage && form.company) {
      setOptionsBusy(true);
      api(`/users/form-options/?company_id=${encodeURIComponent(form.company)}`, { cache: 'no-store' })
        .then(options => {
          if (!cancelled) { setDepartments(options.departments); setManagers(options.managers); }
        })
        .catch(err => { if (!cancelled) setError(err.message); })
        .finally(() => { if (!cancelled) setOptionsBusy(false); });
    }
    return () => { cancelled = true; };
  }, [form.company, editing?.id, optionsRevision]);

  async function refreshEmployees() {
    setOptionsRevision(previous => previous + 1);
    await data.refresh();
  }

  function resetForm() {
    setEditing(null);
    setForm(previous => ({ ...emptyForm, company: previous.company }));
  }

  function beginEdit(user) {
    setMessage(''); setError(''); setEditing(user);
    setForm({
      ...emptyForm,
      email: user.email || '', username: user.username || '',
      first_name: user.first_name || '', last_name: user.last_name || '',
      role: user.profile.role,
      company: user.profile.company == null ? '' : String(user.profile.company),
      department: user.profile.department == null ? '' : String(user.profile.department),
      manager: user.profile.manager == null ? '' : String(user.profile.manager),
      employee_id: user.profile.employee_id || '',
    });
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function submit(e) {
    e.preventDefault(); setMessage(''); setError('');
    try {
      if (form.role !== 'SUPER_ADMIN' && !form.company) throw new Error('Select a company for this employee.');
      if (!form.email.trim()) throw new Error('Email is required.');
      setBusy(true);
      const payload = editing ? {
        email: form.email.trim(), first_name: form.first_name.trim(), last_name: form.last_name.trim(),
        role: form.role, department: form.department ? Number(form.department) : null,
        manager: form.manager ? Number(form.manager) : null,
        ...(form.password ? { password: form.password } : {}),
      } : Object.fromEntries(Object.entries({ ...form, email: form.email.trim() }).filter(([, value]) => value !== ''));
      if (!editing) {
        payload.username = payload.username || payload.email;
        if (!isSuperAdmin) delete payload.company;
      }
      const saved = await api(editing ? `/users/${editing.id}/` : '/users/', {
        method: editing ? 'PATCH' : 'POST', body: JSON.stringify(payload),
      });
      const signedIn = getStoredUser();
      if (editing && saved.id === signedIn?.id && saved.profile?.role !== signedIn.profile?.role) {
        localStorage.setItem('workpulse_user', JSON.stringify(saved));
        window.location.reload();
        return;
      }
      setMessage(editing ? 'Employee updated.' : `User created${saved.profile?.employee_id ? ` · Employee code: ${saved.profile.employee_id}` : ''}. ${form.password ? 'Employee must accept the latest policy before a work session.' : 'Use Edit to set a password when the employee is ready to sign in.'}`);
      setOptionsRevision(previous => previous + 1);
      resetForm();
      await data.refresh();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function reactivate(id) {
    setMessage(''); setError(''); setBusy(true);
    try {
      await api(`/users/${id}/reactivate-policy/`, { method: 'POST', body: JSON.stringify({}) });
      setMessage('Policy reset. Employment status was not changed.');
      await data.refresh();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  const roleOptions = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SALES_ADMIN', 'COMPANY_ADMIN'];
  if (isSuperAdmin) roleOptions.push('SUPER_ADMIN');
  const prefix = companies.find(company => String(company.id) === String(form.company))?.employee_id_prefix;
  const departmentOptions = [...departments];
  if (editing?.profile.department && !departmentOptions.some(row => row.id === editing.profile.department)) {
    departmentOptions.push({ id: editing.profile.department, name: `${editing.profile.department_name || 'Department'} (current)` });
  }
  const managerOptions = managers.filter(manager => manager.id !== editing?.id);
  if (editing?.profile.manager && !managerOptions.some(row => row.id === editing.profile.manager)) {
    managerOptions.push({ id: editing.profile.manager, displayName: `${editing.profile.manager_name || `Manager #${editing.profile.manager}`} (current)` });
  }
  const tableRows = data.rows.map(user => {
    const mappings = Array.isArray(user.erp_mappings) ? user.erp_mappings : null;
    const crmIds = [...new Set((mappings || []).map(mapping => mapping.external_id))];
    const employeeCode = user.profile?.employee_id || user.profile?.employee_code ||
      (crmIds.length === 1 ? crmIds[0] : crmIds.length > 1 ? 'Multiple CRM IDs' : '—');
    return {
    id: user.id, name: [user.first_name, user.last_name].filter(Boolean).join(' ') || '—',
    email: user.email, company: user.profile?.company_name || '—',
    employee_code: employeeCode,
    ...(canManage ? { crm_mapping: !mappings ? 'Unavailable' : mappings.length
      ? mappings.map(mapping => `${mapping.connector_name || `Connector #${mapping.connector_id}`}: ${mapping.external_id}${mapping.connector_active === false ? ' (disabled)' : ''}`).join('; ')
      : user.profile?.role === 'SUPER_ADMIN' ? 'Not applicable' : 'Not mapped' } : {}),
    role: user.profile?.role || '—',
    department: user.profile?.department_name || '—', manager: user.profile?.manager_name || '—',
    status: user.is_active && user.profile?.is_active_employee ? 'Active' : 'Inactive',
    };
  });

  return (
    <div>
      <PageHeader title="Users / Employees"><button disabled={data.loading || busy || optionsBusy} onClick={refreshEmployees}>Refresh</button></PageHeader>
      <Hint>{canManage ? 'Create users with their name and email, then use Edit to assign a role, department and manager. A password can be set now or later.' : 'Your visible employee details.'}</Hint>
      {canManage && <Hint>CRM mapping shows the saved source employee ID and connector. When no WorkPulse display code is assigned, employee_code shows the mapped CRM ID. Multiple different source IDs are listed under crm_mapping.</Hint>}
      <Message text={message} /><ErrorBox text={error || data.error} />
      {canManage && <section ref={formRef}>
        <h3>{editing ? `Edit Employee · ${editing.email}` : 'Create User'}</h3>
        <form className="grid-form" onSubmit={submit}>
          <Field label="Email" type="email" required disabled={busy} value={form.email} onChange={value => setForm({ ...form, email: value })} />
          {!editing && <Field label="Username (optional)" disabled={busy} value={form.username} onChange={value => setForm({ ...form, username: value })} />}
          <Field label="First name" disabled={busy} value={form.first_name} onChange={value => setForm({ ...form, first_name: value })} />
          <Field label="Last name" disabled={busy} value={form.last_name} onChange={value => setForm({ ...form, last_name: value })} />
          <Field label={editing ? 'New password (optional)' : 'Password (optional)'} type="password" autoComplete="new-password" disabled={busy}
            value={form.password} onChange={value => setForm({ ...form, password: value })} />
          <Field label="Role" disabled={busy} value={form.role} selectOptions={roleOptions} onChange={value => setForm({ ...form, role: value })} />
          <Field label="Company" disabled={busy || !!editing || !isSuperAdmin} value={form.company}
            selectOptions={[{ value: '', label: 'Select company' }, ...companies.map(company => ({ value: company.id, label: company.name }))]}
            onChange={value => setForm({ ...form, company: value, department: '', manager: '' })} />
          <Field label="Employee code (optional)" disabled={busy || !!editing} value={form.employee_id} maxLength={64} placeholder={prefix ? `${prefix}0001` : 'Optional employee code'}
            onChange={value => setForm({ ...form, employee_id: value })} />
          {!editing && <p className="small">{prefix ? `Leave blank to generate an employee code using ${prefix}.` : 'Leave blank if an employee display code is not needed.'}</p>}
          <Field label="Department (optional)" disabled={busy || optionsBusy || !form.company} value={form.department}
            selectOptions={[{ value: '', label: 'No department' }, ...departmentOptions.map(department => ({ value: department.id, label: department.name }))]}
            onChange={value => setForm({ ...form, department: value })} />
          <Field label="Manager (optional)" disabled={busy || optionsBusy || !form.company} value={form.manager}
            selectOptions={[{ value: '', label: 'No manager' }, ...managerOptions.map(manager => ({
              value: manager.id, label: manager.displayName || `${[manager.first_name, manager.last_name].filter(Boolean).join(' ') || manager.email} (${manager.email})`,
            }))]} onChange={value => setForm({ ...form, manager: value })} />
          <button type="submit" disabled={busy || optionsBusy}>{busy ? 'Saving…' : editing ? 'Save Changes' : 'Create User'}</button>
          {editing && <button type="button" disabled={busy} onClick={() => { resetForm(); setError(''); }}>Cancel Edit</button>}
        </form>
      </section>}
      <div className="inline-form">
        <Field label="Search employees" type="search" value={search} onChange={value => { setSearch(value); setPage(1); }} />
        {isSuperAdmin && <Field label="Company filter" value={companyFilter}
          selectOptions={[{ value: '', label: 'All companies' }, ...companies.map(company => ({ value: company.id, label: company.name }))]}
          onChange={value => { setCompanyFilter(value); setPage(1); }} />}
      </div>
      <Pager data={data} page={page} setPage={setPage} />
      <SimpleTable rows={tableRows} actions={canManage ? row => {
        const user = data.rows.find(candidate => candidate.id === row.id);
        if (!user.profile || (!isSuperAdmin && user.profile.role === 'SUPER_ADMIN')) return null;
        return <div className="action-row">
          <button disabled={busy} onClick={() => beginEdit(user)}>Edit</button>
          <button disabled={busy} onClick={() => reactivate(user.id)}>Reactivate Policy</button>
        </div>;
      } : undefined} />
    </div>
  );
}
