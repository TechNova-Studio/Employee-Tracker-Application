import React from 'react';
import Icon from './Icon.jsx';
import { ACTIVITY_TYPES, composition, dateLabel, duration, initials, percentage, seconds } from '../lib/dashboard.js';

export function Avatar({ person, size = '' }) {
  return <span className={`avatar avatar-${['brand','teal','amber','rose'][(person?.id || 0)%4]} ${size}`}>{initials(person?.name)}</span>;
}
export function StatTile({ icon, tone, label, value, caption, extra }) {
  return <article className={`stat-tile tone-${tone}`}><div className="stat-label"><span>{label}</span><span className="stat-icon"><Icon name={icon} size={19}/></span></div><div className="stat-value">{value}{extra}</div><div className="stat-caption">{caption}</div></article>;
}
export function EmptyState({ title, text, icon = 'chart', action }) {
  return <div className="dash-empty"><span className="empty-icon"><Icon name={icon} size={27}/></span><strong>{title}</strong>{text && <p>{text}</p>}{action}</div>;
}
export function Legend({ compact = false }) {
  return <div className={`activity-legend ${compact?'compact':''}`}>{ACTIVITY_TYPES.map(type=><span key={type.key}><i style={{background:type.color}}/>{type.label}</span>)}</div>;
}
export function CompositionBar({ row, className = '' }) {
  const parts = composition(row);
  return <div className={`composition-bar ${className}`} role="img" aria-label={parts.map(type=>`${type.label} ${duration(type.seconds)}`).join(', ')}>{parts.map(type=><i key={type.key} style={{width:`${type.pct}%`,background:type.color}} title={`${type.label}: ${duration(type.seconds)}`}/>)}</div>;
}
export function TimeBreakdown({ summary = {} }) {
  const parts = composition(summary);
  let offset = 0;
  const stops = parts.map(type=>{const start=offset; offset+=type.pct; return `${type.color} ${start}% ${offset}%`;});
  const total = parts.reduce((sum,type)=>sum+type.seconds,0);
  return <div className="time-breakdown"><div className="donut-wrap"><div className="time-donut" style={{background:total?`conic-gradient(${stops.join(',')})`:'var(--line)'}} role="img" aria-label={`Productive share ${percentage(summary.productive_share_pct)} of classified application time`}><div><strong>{percentage(summary.productive_share_pct)}</strong><span>Productive share</span><small>of classified time</small></div></div></div>
    <div className="breakdown-rows">{parts.map(type=><div key={type.key}><span><i style={{background:type.color}}/>{type.label}</span><strong>{duration(type.seconds)}</strong><small>{percentage(type.pct)}</small></div>)}</div>
    <div className="coverage-note"><span>Classification coverage</span><strong>{percentage(summary.classification_coverage_pct)}</strong><div><i style={{width:`${summary.classification_coverage_pct || 0}%`}}/></div></div>
  </div>;
}
export function ActivityChart({ rows = [], granularity = 'day', compact = false }) {
  const max = Math.max(0,...rows.map(row=>seconds(row.activity_seconds)));
  if (!max) return <EmptyState title="No application activity yet" text="Recorded application time will appear here after a desktop work session." icon="activity"/>;
  const width = Math.max(550,rows.length*22), height = compact?195:230, plotHeight = height-52;
  const left = 43, right = 12, plotWidth = width-left-right, step = plotWidth/rows.length;
  const barWidth = Math.min(26,step*.56);
  const stride = Math.max(1,Math.ceil(rows.length/9));
  return <div className="activity-chart"><div className="chart-scroll"><svg viewBox={`0 0 ${width} ${height}`} style={width>900?{minWidth:width}:undefined} role="img" aria-label={`Recorded application usage by ${granularity}, split into productive, neutral, unproductive and unknown time`}>
    <title>Recorded application time</title>
    {[0,1,2,3].map(index=>{const y=18+plotHeight-index*plotHeight/3;return <g key={index}><line x1={left} x2={width-right} y1={y} y2={y} className="chart-grid"/><text x={left-9} y={y+4} textAnchor="end" className="chart-tick">{duration(max*index/3)}</text></g>;})}
    {rows.map((row,index)=>{let y=18+plotHeight;const x=left+step*index+(step-barWidth)/2;return <g key={row.label || row.date}><title>{`${row.label || dateLabel(row.date)} — ${composition(row).map(type=>`${type.label}: ${duration(type.seconds)}`).join(', ')}`}</title>{composition(row).map(type=>{const h=type.seconds/max*plotHeight;y-=h;return <rect key={type.key} x={x} y={y} width={barWidth} height={h} fill={type.color} rx="2"/>;})}{index%stride===0 && <text x={x+barWidth/2} y={height-7} textAnchor="middle" className="chart-tick">{row.label || dateLabel(row.date)}</text>}</g>;})}
  </svg></div><details className="chart-data"><summary>View chart data</summary><div className="table-wrap"><table><thead><tr><th>Period</th>{ACTIVITY_TYPES.map(type=><th key={type.key}>{type.label}</th>)}</tr></thead><tbody>{rows.map(row=><tr key={row.label || row.date}><td>{row.label || dateLabel(row.date)}</td>{composition(row).map(type=><td key={type.key}>{duration(type.seconds)}</td>)}</tr>)}</tbody></table></div></details></div>;
}
export function StatusBadge({ person }) {
  const label = {active:'Working',idle:'Idle now',offline:'Offline',inactive:'Inactive'}[person.live_status] || 'Offline';
  return <span className={`status-pill status-${person.live_status || 'offline'}`}><i/>{label}</span>;
}
export function PeopleList({ rows = [], mode, onSelect }) {
  if (!rows.length) return <EmptyState title="Waiting for classified activity" text="Employees with no classified time are kept out of this comparison." icon="people"/>;
  return <div className="people-list">{rows.map((person,index)=><button key={person.id} className="person-insight" onClick={()=>onSelect(person.id)}><span className="person-rank">{String(index+1).padStart(2,'0')}</span><Avatar person={person}/><span className="person-text"><strong>{person.name}</strong><small>{person.department_name}</small></span><span className={`person-number ${mode==='productive'?'productive-text':'neutral-text'}`}><strong>{mode==='productive'?duration(person.productive_seconds):percentage(person.productive_share_pct)}</strong><small>{mode==='productive'?'productive':`${percentage(person.classification_coverage_pct)} classified`}</small></span></button>)}</div>;
}
export function DepartmentList({ rows = [], onSelect, expanded, onExpand }) {
  if (!rows.length) return <EmptyState title="No departments in this view" text="Try another department or employment filter." icon="building"/>;
  const selected = expanded?rows:rows.slice(0,5);
  return <div className="department-list">{selected.map(row=><button key={row.id || 'unassigned'} className="department-row" onClick={()=>onSelect(row.id || 'unassigned')}><div><strong>{row.name}</strong><span>{duration(row.productive_seconds)}</span></div><CompositionBar row={row}/><small>{row.employee_count} {row.employee_count===1?'employee':'employees'} · {percentage(row.productive_share_pct)} productive share</small></button>)}{rows.length>5 && <button className="text-button department-expand" onClick={onExpand}>{expanded?'Show less':`View all ${rows.length} departments`}<Icon name="down" size={13}/></button>}</div>;
}
export function TopApps({ rows = [] }) {
  const max = Math.max(1,...rows.map(row=>seconds(row.seconds)));
  if (!rows.length) return <EmptyState title="No application usage recorded" text="Apps and captured website domains appear as activity arrives." icon="screen"/>;
  return <div className="top-apps">{rows.map((row,index)=><div className="top-app" key={`${row.app_name}|${row.domain}`}><span className={`app-symbol app-symbol-${index%3}`}><Icon name={row.domain?'link':'screen'} size={16}/></span><div><strong title={row.app_name || row.domain}>{row.app_name || row.domain || 'Unnamed application'}</strong><small title={row.domain}>{row.domain || 'Desktop application'}</small><div className="app-meter"><i style={{width:`${seconds(row.seconds)/max*100}%`}}/></div></div><span>{duration(row.seconds)}</span></div>)}</div>;
}
