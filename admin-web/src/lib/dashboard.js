export const ACTIVITY_TYPES = [
  { key:'productive', label:'Productive', color:'var(--productive)' },
  { key:'neutral', label:'Neutral', color:'var(--neutral)' },
  { key:'unproductive', label:'Unproductive', color:'var(--unproductive)' },
  { key:'unknown', label:'Unknown', color:'var(--unknown)' },
];
export function seconds(value) { const number = Number(value); return Number.isFinite(number) ? Math.max(0, number) : 0; }
export function duration(value) {
  const number = seconds(value);
  if (!number) return '0m';
  if (number < 60) return '<1m';
  const minutes = Math.floor(number / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2,'0')}m` : `${minutes}m`;
}
export function percentage(value) { return value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : `${Math.max(0, Math.min(100, Number(value))).toFixed(1).replace('.0','')}%`; }
export function initials(name = '') { return String(name).trim().split(/\s+/).filter(Boolean).slice(0,2).map(word=>word[0].toUpperCase()).join('') || '?'; }
export function localDate(value = new Date()) { return `${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}-${String(value.getDate()).padStart(2,'0')}`; }
export function presetRange(preset, now = new Date()) {
  const start = new Date(now.getFullYear(),now.getMonth(),now.getDate());
  if (preset === 'week') start.setDate(start.getDate()-6);
  if (preset === 'month') start.setDate(start.getDate()-29);
  return { from_date:localDate(start), to_date:localDate(now) };
}
export function validRange(from, to) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(from || '') || !/^\d{4}-\d{2}-\d{2}$/.test(to || '')) return false;
  const start = Date.parse(`${from}T00:00:00Z`), end = Date.parse(`${to}T00:00:00Z`);
  return Number.isFinite(start) && Number.isFinite(end) && new Date(start).toISOString().slice(0,10) === from && new Date(end).toISOString().slice(0,10) === to && end >= start && end-start <= 92*86400000;
}
export function dateLabel(value, options = {month:'short',day:'numeric'}) {
  const parsed = new Date(`${value}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleDateString('en-IN',options);
}
export function rangeLabel(range) { return range?.from_date === range?.to_date ? dateLabel(range?.from_date,{weekday:'short',day:'numeric',month:'long',year:'numeric'}) : `${dateLabel(range?.from_date)} – ${dateLabel(range?.to_date,{day:'numeric',month:'short',year:'numeric'})}`; }
export function composition(row = {}) {
  const values = ACTIVITY_TYPES.map(type => ({...type, seconds:seconds(row[`${type.key}_seconds`])}));
  const total = values.reduce((sum,type)=>sum+type.seconds,0);
  return values.map(type=>({...type, pct:total ? type.seconds/total*100 : 0}));
}
export function dashboardQuery(filters = {}, extra = {}) {
  const query = new URLSearchParams();
  Object.entries({...filters,...extra}).forEach(([key,value])=> {
    if (value !== '' && value !== undefined && value !== null && key !== 'preset') query.set(key,String(value));
  });
  return query.toString();
}
export function numberedPages(page, pages) {
  const values = [...new Set([1,page-1,page,page+1,pages].filter(value=>value>=1 && value<=pages))].sort((a,b)=>a-b);
  return values.flatMap((value,index)=>index && value-values[index-1]>1 ? [`gap-${value}`,value] : [value]);
}
