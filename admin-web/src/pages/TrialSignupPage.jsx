import React, { useState } from 'react';
import { api } from '../lib/api.js';
import { ErrorBox, Field, Hint, PageHeader } from '../components/ui.jsx';
import { dateTime } from '../components/DataView.jsx';

export default function TrialSignupPage() {
  const [form, setForm] = useState({ code: new URLSearchParams(window.location.search).get('code') || '', company_name: '', employee_id_prefix: '', admin_name: '', admin_email: '', mobile: '', password: '' });
  const [terms, setTerms] = useState(null); const [result, setResult] = useState(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const change = key => value => { setForm(f => ({ ...f, [key]: value })); if (key === 'code') setTerms(null); };
  async function validate() {
    setBusy(true); setError(''); setTerms(null);
    try { const d = await api('/trial/validate-code/', { method: 'POST', body: JSON.stringify({ code: form.code }) }); setTerms(d.code); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError('');
    try { const d = await api('/trial/signup/', { method: 'POST', body: JSON.stringify(form) }); setResult(d); setForm(f => ({ ...f, password: '' })); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <div className="public-signup"><PageHeader title="Start your BOLD WorkPulse trial"/>
    {result ? <section className="created-code"><h3>{result.company.name} is ready</h3><p>Sign in with {result.admin_user.email} and the password you just created.</p><p>Your trial ends {dateTime(result.company.trial_end_date)}.</p><a className="button-link" href="/">Go to sign in</a></section> : <>
      <Hint>Validate the demo code shared by your sales contact, then create your company administrator account.</Hint><ErrorBox text={error}/>
      <form className="grid-form" onSubmit={submit}>
        <Field label="Demo code" value={form.code} onChange={change('code')} required maxLength={64} disabled={busy}/><button type="button" disabled={busy || !form.code.trim()} onClick={validate}>{busy ? 'Please wait…' : 'Validate code'}</button>
        {terms && <div className="trial-terms">{terms.trial_duration_days}-day trial · {terms.allowed_users} users · {terms.allowed_devices} devices<br/>Signup before {dateTime(terms.expiry_date)}</div>}
        <Field label="Company name" value={form.company_name} onChange={change('company_name')} required maxLength={255}/>
        <Field label="Employee ID prefix (optional)" value={form.employee_id_prefix} onChange={change('employee_id_prefix')} maxLength={32} placeholder="GLUTAPE"/>
        <p className="small">A prefix generates IDs such as GLUTAPE0001 for the administrator and subsequent users. Leave blank to use email.</p>
        <Field label="Administrator name" value={form.admin_name} onChange={change('admin_name')} required maxLength={150}/>
        <Field label="Administrator email" type="email" value={form.admin_email} onChange={change('admin_email')} required maxLength={150} autoComplete="email"/>
        <Field label="Mobile (optional)" type="tel" value={form.mobile} onChange={change('mobile')} maxLength={30} autoComplete="tel"/>
        <Field label="Password" type="password" value={form.password} onChange={change('password')} required minLength={8} maxLength={128} autoComplete="new-password"/>
        <p className="small">Use at least 8 characters. Avoid a common password, only numbers or your name/email.</p>
        <button disabled={busy || !terms}>{busy ? 'Creating…' : 'Create trial company'}</button>
      </form><p>Already registered? <a href="/">Sign in</a></p></>}
  </div>;
}
