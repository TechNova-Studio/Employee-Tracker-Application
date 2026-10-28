import React, { useEffect, useRef, useState } from 'react';
import { api, getStoredUser, normalizeRows } from '../lib/api.js';
import { Field, PageHeader } from '../components/ui.jsx';
import './ProductivityRulesPage.css';

const EMPTY = { department: '', pattern_type: 'DOMAIN', pattern: '', category: 'PRODUCTIVE', notes: '', is_active: true };
const TYPES = [{ value: 'DOMAIN', label: 'Website domain' }, { value: 'APP', label: 'Application' },
  { value: 'WINDOW', label: 'Window title' }, { value: 'URL', label: 'URL contains' }];
const CATEGORIES = [{ value: 'PRODUCTIVE', label: 'Productive' }, { value: 'NEUTRAL', label: 'Neutral' },
  { value: 'UNPRODUCTIVE', label: 'Unproductive' }, { value: 'UNKNOWN', label: 'Unknown' }];
const HELP = {
  DOMAIN: 'Enter a hostname, such as github.com. Its subdomains also match.',
  APP: 'Enter part of the reported app name, such as Code.exe. Matching ignores letter case.',
  WINDOW: 'Enter text from the window title, such as BOLD ERP. Matching ignores letter case.',
  URL: 'Enter part of the reported URL, such as /crm-frontend/. Matching ignores letter case.',
};
const EXAMPLES = { DOMAIN: 'e.g. github.com', APP: 'e.g. Code.exe', WINDOW: 'e.g. BOLD ERP', URL: 'e.g. /crm-frontend/' };
const canonicalType = value => ['TITLE', 'WINDOW_TITLE'].includes(value?.toUpperCase()) ? 'WINDOW' : value?.toUpperCase();

export default function ProductivityRulesPage() {
  const user = getStoredUser();
  const isSuperAdmin = user?.profile?.role === 'SUPER_ADMIN';
  const allowed = ['SUPER_ADMIN', 'COMPANY_ADMIN', 'HR_ADMIN'].includes(user?.profile?.role);
  const [companyId, setCompanyId] = useState('');
  const [companies, setCompanies] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [optionsFor, setOptionsFor] = useState(null);
  const [optionsError, setOptionsError] = useState('');
  const [optionsVersion, setOptionsVersion] = useState(0);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState(null);
  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [category, setCategory] = useState('');
  const [patternType, setPatternType] = useState('');
  const [departmentId, setDepartmentId] = useState('');
  const [active, setActive] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [listError, setListError] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const mutationPending = useRef(false);
  const editor = useRef(null);

  useEffect(() => {
    if (!allowed) return;
    const controller = new AbortController();
    setOptionsFor(null); setOptionsError(''); setDepartments([]);
    const query = companyId ? `?company_id=${encodeURIComponent(companyId)}` : '';
    api(`/productivity-categories/form-options/${query}`, { signal: controller.signal }).then(data => {
      if (controller.signal.aborted) return;
      setCompanies(data.companies || []); setDepartments(data.departments || []);
      setOptionsFor(companyId);
      if (!isSuperAdmin && data.selected_company_id) setCompanyId(String(data.selected_company_id));
    }).catch(err => { if (!controller.signal.aborted) setOptionsError(err.message); });
    return () => controller.abort();
  }, [companyId, optionsVersion, allowed, isSuperAdmin]);

  useEffect(() => {
    if (!allowed || !companyId) { setRows([]); setCount(0); setLoading(false); return; }
    const controller = new AbortController();
    const query = new URLSearchParams({ company_id: companyId, page: String(page), page_size: String(pageSize) });
    for (const [key, value] of Object.entries({ search: appliedSearch, category, pattern_type: patternType,
      department_id: departmentId, is_active: active })) if (value) query.set(key, value);
    setLoading(true); setListError('');
    api(`/productivity-categories/?${query}`, { signal: controller.signal }).then(data => {
      if (controller.signal.aborted) return;
      setRows(normalizeRows(data)); setCount(Number(data.count ?? normalizeRows(data).length));
    }).catch(err => {
      if (!controller.signal.aborted) { setRows([]); setCount(0); setListError(err.message); }
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [companyId, page, pageSize, appliedSearch, category, patternType, departmentId, active, refresh, allowed]);

  function clearFilters() {
    setSearch(''); setAppliedSearch(''); setCategory(''); setPatternType(''); setDepartmentId(''); setActive(''); setPage(1);
  }
  function cancelEdit() { setEditing(null); setForm({ ...EMPTY }); setError(''); }
  function changeCompany(value) {
    setCompanyId(value); setRows([]); setCount(0); cancelEdit(); clearFilters(); setMessage(''); setListError('');
  }
  function change(field, value) { setForm(current => ({ ...current, [field]: value })); setError(''); }
  function filter(setter, value) { setter(value); setPage(1); }
  function reload() { setRefresh(value => value + 1); }

  async function save(event) {
    event.preventDefault();
    if (mutationPending.current || !companyId || optionsFor !== companyId) return;
    const pattern = form.pattern.trim();
    if (!pattern) { setError('Enter a pattern for this rule.'); return; }
    mutationPending.current = true; setBusy(true); setError(''); setMessage('');
    const payload = { ...form, pattern, department: form.department ? Number(form.department) : null };
    if (!editing) payload.company = Number(companyId);
    try {
      await api(editing ? `/productivity-categories/${editing}/` : '/productivity-categories/', {
        method: editing ? 'PATCH' : 'POST', body: JSON.stringify(payload),
      });
      setMessage(editing ? 'Rule updated. New activity will use the saved rules.' : 'Rule created. New activity will use the saved rules.');
      cancelEdit(); setPage(1); reload();
    } catch (err) { setError(err.message); }
    finally { mutationPending.current = false; setBusy(false); }
  }

  async function toggle(rule) {
    if (mutationPending.current) return;
    mutationPending.current = true; setBusy(true); setError(''); setMessage('');
    try {
      await api(`/productivity-categories/${rule.id}/`, { method: 'PATCH', body: JSON.stringify({ is_active: !rule.is_active }) });
      if (editing === rule.id) cancelEdit();
      setMessage(`Rule ${rule.is_active ? 'deactivated' : 'activated'}. New activity will use the saved rules.`);
      setPage(1); reload();
    } catch (err) { setError(err.message); }
    finally { mutationPending.current = false; setBusy(false); }
  }

  function edit(rule) {
    setEditing(rule.id);
    setForm({ department: rule.department == null ? '' : String(rule.department),
      pattern_type: canonicalType(rule.pattern_type), pattern: rule.pattern,
      category: rule.category, notes: rule.notes || '', is_active: rule.is_active });
    setMessage(''); setError('');
    editor.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    requestAnimationFrame(() => editor.current?.querySelector('input[name="pattern"]')?.focus({ preventScroll: true }));
  }

  if (!allowed) return <div className="error" role="alert">You do not have permission to manage productivity rules.</div>;
  const ready = Boolean(companyId) && optionsFor === companyId && !optionsError;
  const companyName = companies.find(item => String(item.id) === companyId)?.name || 'your company';
  const scopedDepartments = departments.filter(item => item.is_active || String(item.id) === form.department);
  const filtersApplied = Boolean(appliedSearch || category || patternType || departmentId || active);
  const pages = Math.max(1, Math.ceil(count / pageSize));

  return <div className="productivity-page">
    <PageHeader title="Productivity Rules"><button type="button" className="pr-secondary" disabled={busy || loading}
      onClick={() => { reload(); setOptionsVersion(value => value + 1); }}>Refresh</button></PageHeader>
    <p className="pr-intro">Decide which apps and websites count as productive time for your team.</p>
    {message && <div className="pr-notice" role="status">{message}</div>}
    {optionsError && <div className="error" role="alert">{optionsError} <button type="button" onClick={() => setOptionsVersion(value => value + 1)}>Retry options</button></div>}
    {error && <div className="error" role="alert">{error}</div>}

    <section className="pr-context" aria-label="Rule company">
      <Field label="Company" aria-label="Company" value={companyId} disabled={busy || !isSuperAdmin} onChange={changeCompany}
        selectOptions={[{ value: '', label: 'Select a company' }, ...companies.map(item => ({ value: String(item.id), label: item.name }))]} />
      <div className="pr-context-copy"><strong>{companyId ? `Rules for ${companyName}` : 'Choose a company to get started'}</strong>
        <p>A company-wide rule applies to every department. Department rules take priority when they match.</p></div>
    </section>

    <section className="pr-panel" ref={editor} aria-labelledby="pr-editor-title">
      <div className="pr-section-heading"><div><h3 id="pr-editor-title">{editing ? `Edit rule #${editing}` : 'Add a rule'}</h3>
        <p>{editing ? 'Update this rule in its existing company.' : 'Choose a scope, a pattern and its classification.'}</p></div>
        {editing && <button type="button" className="pr-secondary" disabled={busy} onClick={cancelEdit}>Cancel edit</button>}</div>
      <form onSubmit={save}>
        <fieldset disabled={!ready || busy} className="pr-form-grid">
          <legend className="pr-sr-only">Rule details</legend>
          <Field label="Rule scope" aria-label="Rule scope" value={form.department} onChange={value => change('department', value)}
            selectOptions={[{ value: '', label: 'Company-wide' }, ...scopedDepartments.map(item => ({ value: String(item.id), label: `${item.name}${item.is_active ? '' : ' (inactive)'}` }))]} />
          <Field label="Pattern type" aria-label="Pattern type" value={form.pattern_type} onChange={value => change('pattern_type', value)} selectOptions={TYPES} />
          <Field label="Classification" aria-label="Classification" value={form.category} onChange={value => change('category', value)} selectOptions={CATEGORIES} />
          <div className="pr-pattern"><Field label="Pattern" aria-label="Pattern" name="pattern" value={form.pattern} required maxLength={255}
            placeholder={EXAMPLES[form.pattern_type]} aria-describedby="pr-pattern-help" onChange={value => change('pattern', value)} />
            <small id="pr-pattern-help">{HELP[form.pattern_type]}</small></div>
          <label className="pr-checkbox"><input type="checkbox" checked={form.is_active} onChange={event => change('is_active', event.target.checked)} />Active rule</label>
          <div className="pr-notes"><Field label="Notes (optional)" aria-label="Notes (optional)" textarea value={form.notes} maxLength={4000}
            placeholder="Explain why this rule is useful for the team." onChange={value => change('notes', value)} /></div>
          <div className="pr-form-actions"><span>Changes apply to new activity. Existing activity records keep their saved classification.</span>
            <button type="submit" className="pr-primary">{busy ? 'Saving…' : editing ? 'Save changes' : 'Create rule'}</button></div>
        </fieldset>
      </form>
    </section>

    <section className="pr-panel" aria-labelledby="pr-rules-title" aria-busy={loading}>
      <div className="pr-section-heading"><div><h3 id="pr-rules-title">Saved rules</h3><p>Most recently updated first. Unmatched activity is classified as Unknown.</p></div>
        {companyId && <span className="pr-count">{count} {count === 1 ? 'rule' : 'rules'} in this view</span>}</div>
      <form className="pr-filters" onSubmit={event => { event.preventDefault(); setPage(1); setAppliedSearch(search.trim()); }}>
        <fieldset disabled={!companyId || busy}>
          <div className="pr-search"><Field label="Search rules" aria-label="Search rules" type="search" value={search} onChange={setSearch} placeholder="Pattern, notes or department" />
            <button type="submit" className="pr-secondary">Search</button></div>
          <Field label="Filter classification" aria-label="Filter classification" value={category} onChange={value => filter(setCategory, value)} selectOptions={[{ value: '', label: 'All classifications' }, ...CATEGORIES]} />
          <Field label="Filter type" aria-label="Filter type" value={patternType} onChange={value => filter(setPatternType, value)} selectOptions={[{ value: '', label: 'All pattern types' }, ...TYPES]} />
          <Field label="Filter scope" aria-label="Filter scope" value={departmentId} onChange={value => filter(setDepartmentId, value)} selectOptions={[
            { value: '', label: 'All scopes' }, { value: 'company', label: 'Company-wide only' },
            ...departments.map(item => ({ value: String(item.id), label: `${item.name}${item.is_active ? '' : ' (inactive)'}` })),
          ]} />
          <Field label="Filter status" aria-label="Filter status" value={active} onChange={value => filter(setActive, value)} selectOptions={[
            { value: '', label: 'Active and inactive' }, { value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' },
          ]} />
        </fieldset>
      </form>
      {filtersApplied && <button type="button" className="pr-text-button" disabled={busy} onClick={clearFilters}>Clear filters</button>}
      {listError && <div className="error" role="alert">{listError} <button type="button" onClick={reload}>Retry rules</button></div>}
      {!companyId ? <div className="pr-empty">Select a company to view its rules.</div> : loading ? <div className="pr-empty" role="status">Loading rules…</div> : rows.length === 0 ?
        <div className="pr-empty"><strong>{filtersApplied ? 'No matching rules' : 'No rules yet'}</strong><p>{filtersApplied ? 'Try another search or clear the filters.' : 'Add a rule above to start classifying activity.'}</p></div> :
        <div className="pr-table-wrap"><table><thead><tr><th>Pattern</th><th>Type</th><th>Scope</th><th>Classification</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>{rows.map(rule => <tr key={rule.id}>
            <td><strong className="pr-rule-pattern">{rule.pattern}</strong>{rule.notes && <small className="pr-rule-notes">{rule.notes}</small>}</td>
            <td>{TYPES.find(item => item.value === canonicalType(rule.pattern_type))?.label || rule.pattern_type}</td>
            <td>{rule.department ? rule.department_name || departments.find(item => item.id === rule.department)?.name || `Department #${rule.department}` : 'Company-wide'}</td>
            <td><span className={`pr-badge pr-category-${rule.category?.toLowerCase()}`}>{CATEGORIES.find(item => item.value === rule.category)?.label || rule.category}</span></td>
            <td><span className={`pr-badge ${rule.is_active ? 'pr-active' : 'pr-inactive'}`}>{rule.is_active ? 'Active' : 'Inactive'}</span></td>
            <td><div className="pr-row-actions"><button type="button" className="pr-secondary" disabled={busy || !ready} aria-label={`Edit ${rule.pattern}`} onClick={() => edit(rule)}>Edit</button>
              <button type="button" className="pr-text-button" disabled={busy || !ready} aria-label={`${rule.is_active ? 'Deactivate' : 'Activate'} ${rule.pattern}`} onClick={() => toggle(rule)}>{rule.is_active ? 'Deactivate' : 'Activate'}</button></div></td>
          </tr>)}</tbody></table></div>}
      {companyId && <nav className="pr-pager" aria-label="Rules pagination">
        <span aria-live="polite">{count ? `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, count)} of ${count}` : '0 rules'}</span>
        <Field label="Rules per page" aria-label="Rules per page" value={pageSize} disabled={busy || loading} onChange={value => { setPageSize(Number(value)); setPage(1); }}
          selectOptions={[10, 20, 50].map(value => ({ value, label: value }))} />
        <button type="button" className="pr-secondary" disabled={busy || loading || page <= 1} onClick={() => setPage(value => value - 1)}>Previous</button>
        <span>Page {page} of {pages}</span>
        <button type="button" className="pr-secondary" disabled={busy || loading || page >= pages} onClick={() => setPage(value => value + 1)}>Next</button>
      </nav>}
    </section>
    <p className="pr-footnote">Matching ignores letter case. Within the same scope, longer matching patterns take priority.</p>
  </div>;
}
