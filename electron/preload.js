/**
 * preload.js — Bridge segura Electron
 */
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  getVersion:        () => ipcRenderer.invoke('app-version'),
  getAppPath:        () => ipcRenderer.invoke('app-path'),
  downloadUpdate:    () => ipcRenderer.invoke('download-update'),
  installUpdate:     () => ipcRenderer.invoke('install-update'),
  checkUpdateNow:    () => ipcRenderer.invoke('check-update-now'),
  isElectron:        true,

  // Notificações
  getNotifConfig:    ()       => ipcRenderer.invoke('get-notif-config'),
  setNotifConfig:    (config) => ipcRenderer.invoke('set-notif-config', config),

  // Forum: notificar Windows quando há tópicos novos
  notificarForum:    (titulo, qtd) => ipcRenderer.invoke('notificar-forum', titulo, qtd),

  // Documentos: disparar monitoramento manual
  monitorarDocsAgora: () => ipcRenderer.invoke('monitorar-docs-agora'),
})

// Funções globais para os botões do banner de update
window.__electronDownloadUpdate = () => {
  const btn = document.getElementById('btn-download-update')
  if (btn) {
    btn.textContent = 'Baixando...'
    btn.disabled = true
  }
  ipcRenderer.invoke('download-update')
}

window.__electronInstallNow = () => {
  ipcRenderer.invoke('install-update')
}
