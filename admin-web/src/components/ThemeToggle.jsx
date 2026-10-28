import React, { useEffect, useState } from 'react';
import Icon from './Icon.jsx';

export function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      const stored = localStorage.getItem('workpulse_theme');
      if (stored === 'light' || stored === 'dark') return stored;
    } catch { /* Theme still works if browser storage is unavailable. */ }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('workpulse_theme', theme); } catch { /* Keep the session preference. */ }
  }, [theme]);
  return [theme, setTheme];
}

export default function ThemeToggle({ theme, onChange }) {
  return <div className="theme-switch" role="group" aria-label="Color theme">
    {['light', 'dark'].map(value => <button key={value} className={theme === value ? 'selected' : ''}
      title={`${value === 'light' ? 'Light' : 'Dark'} mode`} aria-label={`${value === 'light' ? 'Light' : 'Dark'} mode`}
      aria-pressed={theme === value} onClick={() => onChange(value)}><Icon name={value === 'light' ? 'sun' : 'moon'} size={17}/></button>)}
  </div>;
}
