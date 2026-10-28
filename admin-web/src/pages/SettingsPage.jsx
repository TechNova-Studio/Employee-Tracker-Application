import React from 'react';
import { Hint, PageHeader } from '../components/ui.jsx';

export default function SettingsPage(){
  return <div><PageHeader title="Settings"/><Hint>Staging must remain simple: SCREENSHOT_STORAGE_MODE=local and AI_PROVIDER=mock. Production S3, AI, billing, email, SSL and signing certificates are external configuration.</Hint><h3>Do not change without management approval</h3><ul><li>No Docker, Redis, Celery, Kubernetes, microservices or complex DevOps in v1 staging.</li><li>Do not expose direct screenshot media URLs.</li><li>Do not allow employee access to company-wide logs, ERP events, billing data or screenshots of others.</li><li>Do not add keylogger, clipboard, webcam or microphone access.</li></ul></div>;
}
