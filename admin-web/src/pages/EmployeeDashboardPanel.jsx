import React, { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api.js';
import { dashboardQuery, duration, percentage, rangeLabel } from '../lib/dashboard.js';
import Icon from '../components/Icon.jsx';
import { ActivityChart, Avatar, CompositionBar, EmptyState, Legend, StatusBadge, TopApps } from '../components/DashboardWidgets.jsx';

export default function EmployeeDashboardPanel({ employeeId, filters, onClose }) {
  const dialog = useRef(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const query = dashboardQuery(filters,{employee_id:employeeId, employment:'all',search:'',state:'all',page:1,page_size:1});
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement;
    if (element?.showModal) element.showModal(); else element?.setAttribute('open','');
    return () => { element?.close?.(); previous?.focus?.(); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(()=>{controller.abort();setError('This is taking longer than expected. Please try again.');},30000);
    setData(null); setError('');
    api(`/reports/team-dashboard/?${query}`,{signal:controller.signal,cache:'no-store'})
      .then(result=>{if (!controller.signal.aborted) setData(result);})
      .catch(err=>{if (!controller.signal.aborted) setError(err.message);})
      .finally(()=>clearTimeout(timer));
    return () => {clearTimeout(timer);controller.abort();};
  }, [query,revision]);
  const person = data?.employees?.results?.find(row=>row.id===employeeId);
  const stats = person ? [
    ['Recorded work time',person.has_work_telemetry?duration(person.work_seconds):'—'],
    ['Active time',person.has_work_telemetry?duration(person.active_seconds):'—'],
    ['Idle time',person.has_work_telemetry?duration(person.idle_seconds):'—'],
    ['Productive',duration(person.productive_seconds)],['Neutral',duration(person.neutral_seconds)],
    ['Unproductive',duration(person.unproductive_seconds)],['Unknown',duration(person.unknown_seconds)],
    ['Productive share',percentage(person.productive_share_pct)],
  ] : [];
  return <dialog className="employee-drawer" ref={dialog} aria-labelledby="employee-panel-title"
    onCancel={event=>{event.preventDefault();onClose();}} onClick={event=>{if(event.target===event.currentTarget) onClose();}}>
    <div className="drawer-heading"><div><span className="section-eyebrow">EMPLOYEE INSIGHT</span><h2 id="employee-panel-title">Activity detail</h2></div><button className="icon-button" aria-label="Close employee detail" onClick={onClose} autoFocus><Icon name="close"/></button></div>
    {error ? <EmptyState title="Employee detail unavailable" text={error} action={<button onClick={()=>setRevision(value=>value+1)}>Try again</button>}/> : !person ? <div className="drawer-loading" role="status"><span className="loading-dot"/>Loading employee activity…</div> : <div className="drawer-content">
      <div className="drawer-person"><Avatar person={person} size="avatar-large"/><div><h3>{person.name}</h3><p>{person.department_name} {person.employee_code && `· ${person.employee_code}`}</p><small>{person.email}</small></div><StatusBadge person={person}/></div>
      <div className="drawer-period"><Icon name="calendar" size={15}/>{rangeLabel(data.range)}<span>{data.range.timezone}</span></div>
      <div className="drawer-metrics">{stats.map(([label,value])=><div key={label}><small>{label}</small><strong>{value}</strong></div>)}</div>
      <section className="drawer-section"><div className="panel-heading"><h3>Application time mix</h3><small>{duration(person.activity_seconds)} recorded</small></div><CompositionBar row={person} className="drawer-composition"/><Legend/><p className="chart-note">{percentage(person.classification_coverage_pct)} classified. UNKNOWN time is excluded from productive share.</p></section>
      <section className="drawer-section"><div className="panel-heading"><h3>Activity over time</h3><small>{data.trend_granularity==='hour'?'Hourly':'Daily'}</small></div><ActivityChart rows={data.trend} granularity={data.trend_granularity} compact/></section>
      <section className="drawer-section"><div className="panel-heading"><h3>Most-used applications</h3><Icon name="screen" size={17}/></div><TopApps rows={data.top_apps}/></section>
      <p className="dashboard-footnote">Work time and application usage are separate telemetry streams. These categories describe usage, not completed tasks or employee performance.</p>
    </div>}
  </dialog>;
}
