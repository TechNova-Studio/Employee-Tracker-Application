import React, { useEffect, useState } from 'react';
import Icon from './Icon.jsx';
import ThemeToggle from './ThemeToggle.jsx';

const icons = { dashboard:'dashboard', companies:'building', users:'people', departments:'building', devices:'screen',
  'agent-versions':'screen', policies:'shield', attendance:'clock', activity:'activity', screenshots:'image',
  'productivity-categories':'rules', alerts:'bell', 'ai-summaries':'sparkle', 'trial-codes':'card',
  'trial-dashboard':'chart', billing:'card', 'erp-connectors':'link', 'audit-logs':'document', settings:'settings' };
const groups = [
  ['WORKSPACE', ['dashboard','users','departments','companies']],
  ['WORK INSIGHTS', ['attendance','activity','screenshots','productivity-categories','ai-summaries','alerts']],
  ['ADMINISTRATION', ['devices','agent-versions','policies','trial-codes','trial-dashboard','billing','erp-connectors','audit-logs','settings']],
];
export function Brand() {
  return <div className="brand"><span className="brand-mark"><i/><i/><i/><i/></span><div><strong>WorkPulse</strong><small>by BOLD</small></div></div>;
}
export default function AppShell({ user, menu, page, onNavigate, onLogout, theme, setTheme, children }) {
  const [open, setOpen] = useState(false);
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.email || 'Workspace admin';
  const company = user.profile?.company_name || (user.profile?.role === 'SUPER_ADMIN' ? 'All workspaces' : 'Your workspace');
  const label = menu.find(([key]) => key === page)?.[1] || 'Overview';
  useEffect(() => {
    const handler = event => { if (event.key === 'Escape') setOpen(false); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, []);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement;
    const sidebar = document.getElementById('workspace-navigation');
    sidebar?.querySelector('.nav-item')?.focus();
    const trap = event => {
      if (event.key !== 'Tab') return;
      const controls = [...sidebar.querySelectorAll('button:not([disabled])')].filter(element=>element.getClientRects().length);
      const first = controls[0], last = controls[controls.length-1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', trap);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const media = window.matchMedia?.('(max-width: 980px)');
    const resize = event => { if (!event.matches) setOpen(false); };
    media?.addEventListener?.('change',resize);
    return () => { document.removeEventListener('keydown',trap); media?.removeEventListener?.('change',resize); document.body.style.overflow=overflow; previous?.focus?.(); };
  }, [open]);
  function navigate(key) { onNavigate(key); setOpen(false); }
  return <div className="app">
    <a href="#main-content" className="skip-link">Skip to content</a>
    {open && <button className="nav-backdrop" aria-label="Close navigation" onClick={() => setOpen(false)}/>}
    <aside className={`sidebar ${open ? 'is-open' : ''}`} id="workspace-navigation" aria-label="Workspace navigation">
      <div className="sidebar-brand"><Brand/><button className="icon-button mobile-nav-close" aria-label="Close navigation" onClick={() => setOpen(false)}><Icon name="close"/></button></div>
      <div className="workspace-card"><span className="workspace-avatar">{company.charAt(0).toUpperCase()}</span><div><strong title={company}>{company}</strong><small>WorkPulse workspace</small></div><Icon name="down" size={14}/></div>
      <nav>{groups.map(([group, keys]) => {
        const items = menu.filter(([key]) => keys.includes(key));
        return items.length ? <div className="nav-group" key={group}><span className="nav-label">{group}</span>{items.map(([key, text]) =>
          <button key={key} onClick={() => navigate(key)} className={`nav-item ${key === page ? 'active' : ''}`} aria-current={key === page ? 'page' : undefined}>
            <Icon name={icons[key]}/><span>{key === 'dashboard' ? 'Overview' : text}</span>{key === page && <i className="nav-active-dot"/>}
          </button>)}</div> : null;
      })}</nav>
      <div className="sidebar-footer"><span className="avatar avatar-brand">{name.charAt(0).toUpperCase()}</span><div><strong title={name}>{name}</strong><small>{(user.profile?.role || '').replaceAll('_',' ').toLowerCase()}</small></div><button className="icon-button" onClick={onLogout} title="Sign out" aria-label="Sign out"><Icon name="logout" size={18}/></button></div>
    </aside>
    <main className="app-main" id="main-content">
      <header className="topbar"><div className="topbar-location"><button className="icon-button mobile-nav-toggle" aria-label="Open navigation" aria-controls="workspace-navigation" aria-expanded={open} onClick={() => setOpen(true)}><Icon name="menu"/></button><span className="topbar-company">{company}</span><Icon name="chevron" size={13}/><strong>{page === 'dashboard' ? 'Overview' : label}</strong></div><div className="topbar-actions"><span className="private-workspace"><Icon name="shield" size={14}/>Private workspace</span><ThemeToggle theme={theme} onChange={setTheme}/><span className="topbar-divider"/><span className="avatar avatar-brand topbar-avatar" title={name}>{name.charAt(0).toUpperCase()}</span></div></header>
      <div className="page-content">{children}</div>
      <footer className="app-footer"><span>BOLD WorkPulse</span><span>Work activity, with clarity.</span></footer>
    </main>
  </div>;
}
