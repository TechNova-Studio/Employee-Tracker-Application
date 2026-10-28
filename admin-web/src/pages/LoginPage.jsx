import React, { useState } from 'react';
import { api, saveLogin } from '../lib/api.js';
import { ErrorBox } from '../components/ui.jsx';
import { Brand } from '../components/AppShell.jsx';
import ThemeToggle from '../components/ThemeToggle.jsx';
import Icon from '../components/Icon.jsx';

export default function LoginPage({ onLogin, theme, setTheme }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(e) {
    e.preventDefault();
    setError(''); setBusy(true);
    try {
      const data = await api('/auth/login/', { method: 'POST', body: JSON.stringify({ email: email.trim(), password }) });
      saveLogin(data);
      onLogin(data.user);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <div className="login-shell"><div className="login-theme"><ThemeToggle theme={theme} onChange={setTheme}/></div>
    <div className="login-layout"><section className="login-story"><Brand/><div><h2>Your team's work.<br/>A clearer picture.</h2><p>Understand work time, discover activity patterns and keep your whole workspace in view.</p><div className="login-mini-chart" aria-hidden="true">{[32,54,42,80,62,98,84,70].map((height,i)=><i key={i} style={{height:`${height}%`}}/>)}</div></div><small>A connected workspace. A considered view.</small></section>
      <form className="login-card" onSubmit={submit}><h1>Welcome back</h1><p>Sign in to your WorkPulse workspace.</p><ErrorBox text={error}/>
        <label>Email or username<input required autoComplete="username" autoFocus placeholder="Enter your work email" value={email} onChange={e=>setEmail(e.target.value)} disabled={busy}/></label>
        <label>Password<div className="login-password"><input required autoComplete="current-password" type={visible?'text':'password'} placeholder="Enter your password" value={password} onChange={e=>setPassword(e.target.value)} disabled={busy}/><button type="button" aria-label={visible?'Hide password':'Show password'} onClick={()=>setVisible(!visible)}>{visible?'Hide':'Show'}</button></div></label>
        <button type="submit" disabled={busy}>{busy?'Signing in…':'Sign in to workspace'}<Icon name="arrow" size={17}/></button><small className="login-note">Your access follows your company and assigned role.</small>
      </form></div>
  </div>;
}
