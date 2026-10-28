const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("workpulse", {
  versionCheck: () => ipcRenderer.invoke("agent:versionCheck"),
  verifySession: () => ipcRenderer.invoke("agent:verifySession"),
  setApiBase: (url) => ipcRenderer.invoke("agent:setApiBase", url),
  testConnection: () => ipcRenderer.invoke("agent:testConnection"),
  onAuthExpired: (callback) => {
    const handler = () => callback();
    ipcRenderer.on("agent:authExpired", handler);
    return () => ipcRenderer.removeListener("agent:authExpired", handler);
  },
  onUpdateRequired: (callback) => {
    const handler = (_, version) => callback(version);
    ipcRenderer.on("agent:updateRequired", handler);
    return () => ipcRenderer.removeListener("agent:updateRequired", handler);
  },
  onPolicyRequired: (callback) => {
    const handler = (_, reason) => callback(reason);
    ipcRenderer.on("agent:policyRequired", handler);
    return () => ipcRenderer.removeListener("agent:policyRequired", handler);
  },
  onSessionEnded: (callback) => {
    const handler = (_, message) => callback(message);
    ipcRenderer.on("agent:sessionEnded", handler);
    return () => ipcRenderer.removeListener("agent:sessionEnded", handler);
  },
  openDownload: (url) => ipcRenderer.invoke("agent:openDownload", url),
  crmProviders: () => ipcRenderer.invoke("agent:crmProviders"),
  crmLogin: (provider) => ipcRenderer.invoke("agent:crmLogin", provider),
  cancelCRMLogin: () => ipcRenderer.invoke("agent:cancelCRMLogin"),
  login: (payload) => ipcRenderer.invoke("agent:login", payload),
  logout: () => ipcRenderer.invoke("agent:logout"),
  getPolicy: () => ipcRenderer.invoke("agent:getPolicy"),
  acceptPolicy: (policyId) => ipcRenderer.invoke("agent:acceptPolicy", policyId),
  declinePolicy: (policyId) => ipcRenderer.invoke("agent:declinePolicy", policyId),
  registerDevice: () => ipcRenderer.invoke("agent:registerDevice"),
  startSession: () => ipcRenderer.invoke("agent:startSession"),
  stopSession: (flush = true) => ipcRenderer.invoke("agent:stopSession", flush),
  status: () => ipcRenderer.invoke("agent:status"),
  inputDiagnostics: () => ipcRenderer.invoke("agent:inputDiagnostics"),
  screenshotDiagnostics: () => ipcRenderer.invoke("agent:screenshotDiagnostics"),
  syncNow: () => ipcRenderer.invoke("agent:syncNow"),
  getConfig: () => ipcRenderer.invoke("agent:getConfig"),
});
