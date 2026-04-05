/**
 * main.js — NFS-e Validador Nacional
 * Processo principal do Electron.
 *
 * Fluxo:
 *  1. Inicia server.py (Python) como processo filho
 *  2. Aguarda servidor responder na porta 8000
 *  3. Abre janela nativa com ícone NFS-e personalizado
 *  4. Ao fechar a janela, encerra o servidor Python
 */

const { app, BrowserWindow, shell, ipcMain, dialog, Tray, Menu, nativeImage } = require('electron')
const path   = require('path')
const fs     = require('fs')
const http   = require('http')
const { spawn } = require('child_process')

// Auto-updater
let autoUpdater
try {
  autoUpdater = require('electron-updater').autoUpdater
  autoUpdater.autoDownload    = false  // perguntar antes de baixar
  autoUpdater.autoInstallOnAppQuit = true
} catch (e) {
  // electron-updater não disponível em dev
}

// ── Constantes ───────────────────────────────────────────────────────────────
const PORT     = 8000
const URL      = `http://localhost:${PORT}`
const IS_DEV   = process.env.NODE_ENV === 'development'
const APP_NAME = 'NFS-e Validador'

// ── Caminhos ──────────────────────────────────────────────────────────────────
// Em produção: recursos ficam em process.resourcesPath/app/
// Em dev: ficam na pasta pai (sistema-nfse/)
const RESOURCES = app.isPackaged
  ? path.join(process.resourcesPath, 'app')
  : path.join(__dirname, '..')

// Tentar vários caminhos possíveis para o ícone
const ICON_CANDIDATES = [
  path.join(process.resourcesPath, 'app', 'nfse.ico'),
  path.join(process.resourcesPath, 'app', 'build', 'nfse.ico'),
  path.join(__dirname, 'build', 'nfse.ico'),
  path.join(__dirname, '..', 'nfse.ico'),
  path.join(RESOURCES, 'nfse.ico'),
]
const ICON_PATH = ICON_CANDIDATES.find(p => fs.existsSync(p)) || ICON_CANDIDATES[0]

// Log em AppData\Local
const LOG_DIR  = path.join(app.getPath('userData'), 'logs')
const LOG_FILE = path.join(LOG_DIR, 'electron.log')

// ── Logger ────────────────────────────────────────────────────────────────────
function log(msg) {
  const line = `${new Date().toISOString()} ${msg}`
  console.log(line)
  try {
    fs.mkdirSync(LOG_DIR, { recursive: true })
    fs.appendFileSync(LOG_FILE, line + '\n', 'utf8')
  } catch {}
}

// ── Variáveis globais ─────────────────────────────────────────────────────────
let mainWindow   = null
let serverProc   = null
let tray         = null
let serverReady  = false

// ── Forçar instância única ────────────────────────────────────────────────────
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.focus()
    }
  })
}

// ── Iniciar servidor Python ───────────────────────────────────────────────────
function iniciarServidor() {
  // Encontrar Python
  const pythonCandidates = [
    path.join(RESOURCES, '_internal', 'python.exe'), // empacotado com PyInstaller
    'python',
    'python3',
    'py',
  ]

  // Verificar se há exe Python empacotado
  const serverScript = path.join(RESOURCES, 'server.py')
  log(`server.py: ${serverScript} (existe: ${fs.existsSync(serverScript)})`)

  // Tentar usar o exe do NFS-e (que embarca Python + server.py)
  const nfseExe = path.join(RESOURCES, 'NFS-e Validador.exe')
  if (fs.existsSync(nfseExe)) {
    log(`Iniciando via NFS-e Validador.exe: ${nfseExe}`)
    serverProc = spawn(nfseExe, ['--server-only'], {
      cwd:      RESOURCES,
      detached: false,
      windowsHide: true,
      env: { ...process.env, NFSE_SERVER_ONLY: '1' }
    })
  } else {
    // Dev: usar Python diretamente
    log(`Iniciando via Python: ${serverScript}`)
    // Tentar python, python3, ou py
    const pythonCmds = ['python', 'python3', 'py']
    let pythonCmd = 'python'
    for (const cmd of pythonCmds) {
      try {
        const test = require('child_process').spawnSync(cmd, ['--version'])
        if (test.status === 0) { pythonCmd = cmd; break }
      } catch {}
    }
    log(`Usando Python: ${pythonCmd}`)

    const pythonEnv = {
      ...process.env,
      PYTHONUTF8:       '1',
      PYTHONIOENCODING: 'utf-8',
      PYTHONUNBUFFERED: '1',
    }

    // Instalar dependências se necessário (lxml, etc.)
    try {
      log('Verificando dependencias Python...')
      const check = require('child_process').spawnSync(
        pythonCmd, ['-c', 'import lxml'],
        { env: pythonEnv, timeout: 10000 }
      )
      if (check.status !== 0) {
        log('lxml nao encontrado — instalando...')
        require('child_process').spawnSync(
          pythonCmd, ['-m', 'pip', 'install', 'lxml', '--quiet'],
          { env: pythonEnv, timeout: 60000, windowsHide: true }
        )
        log('lxml instalado.')
      } else {
        log('lxml OK.')
      }
    } catch (e) {
      log(`Aviso pip: ${e.message}`)
    }

    serverProc = spawn(pythonCmd, [serverScript], {
      cwd:         RESOURCES,
      detached:    false,
      windowsHide: true,
      env:         pythonEnv,
    })
  }

  serverProc.stdout?.on('data', d => log(`[server] ${d.toString().trim()}`))
  serverProc.stderr?.on('data', d => log(`[server:err] ${d.toString().trim()}`))
  serverProc.on('exit', code => log(`[server] encerrado (código ${code})`))

  log('Servidor Python iniciado.')
}

// ── Aguardar servidor responder ───────────────────────────────────────────────
function aguardarServidor(tentativas = 0) {
  return new Promise((resolve, reject) => {
    const MAX = 40  // 20 segundos

    function tentar() {
      http.get(`${URL}/api/health`, res => {
        if (res.statusCode === 200) {
          log('Servidor OK.')
          resolve()
        } else {
          retry()
        }
      }).on('error', () => retry())
    }

    function retry() {
      tentativas++
      if (tentativas >= MAX) {
        reject(new Error('Servidor não respondeu em 20s'))
        return
      }
      setTimeout(tentar, 500)
    }

    tentar()
  })
}

// ── Criar janela principal ────────────────────────────────────────────────────
function criarJanela() {
  // Criar ícone — Electron no Windows funciona melhor com PNG 256x256
  // mas também aceita ICO
  let icon = undefined
  if (fs.existsSync(ICON_PATH)) {
    try {
      icon = nativeImage.createFromPath(ICON_PATH)
      if (icon.isEmpty()) {
        log('AVISO: ícone carregado está vazio!')
        icon = undefined
      } else {
        log(`Icone carregado: ${ICON_PATH} (${icon.getSize().width}x${icon.getSize().height})`)
      }
    } catch (e) {
      log(`Erro ao carregar icone: ${e.message}`)
    }
  } else {
    log(`AVISO: icone nao encontrado em: ${ICON_PATH}`)
    log(`Candidatos verificados: ${ICON_CANDIDATES.join(', ')}`)
  }

  mainWindow = new BrowserWindow({
    width:           1440,
    height:          900,
    minWidth:        900,
    minHeight:       600,
    title:           APP_NAME,
    icon:            icon,                    // ← ícone NFS-e na taskbar!
    backgroundColor: '#0d1117',
    show:            false,                   // mostrar só quando carregado
    autoHideMenuBar: true,                    // sem barra de menu
    webPreferences: {
      preload:             path.join(__dirname, 'preload.js'),
      nodeIntegration:     false,
      contextIsolation:    true,
      webSecurity:         true,
    }
  })

  // Mostrar quando pronto (evita flash branco)
  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
    log('Janela exibida.')
  })

  // Abrir links externos no browser do sistema
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith('http://localhost')) {
      shell.openExternal(url)
      return { action: 'deny' }
    }
    return { action: 'allow' }
  })

  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost')) {
      event.preventDefault()
      shell.openExternal(url)
    }
  })

  mainWindow.on('closed', () => { mainWindow = null })

  // Carregar app
  mainWindow.loadURL(URL)
  log(`Carregando: ${URL}`)
}

// ── Tray (ícone na bandeja do sistema) ───────────────────────────────────────
function criarTray() {
  if (!fs.existsSync(ICON_PATH)) return

  try {
    tray = new Tray(ICON_PATH)
    tray.setToolTip(APP_NAME)

    const menu = Menu.buildFromTemplate([
      { label: 'Abrir NFS-e Validador', click: () => {
        if (mainWindow) mainWindow.focus()
        else criarJanela()
      }},
      { type: 'separator' },
      { label: 'Encerrar', click: () => app.quit() }
    ])

    tray.setContextMenu(menu)
    tray.on('double-click', () => {
      if (mainWindow) mainWindow.focus()
      else criarJanela()
    })

    log('Tray criado.')
  } catch (e) {
    log(`Tray erro: ${e.message}`)
  }
}

// ── IPC — comunicação renderer ↔ main ────────────────────────────────────────
ipcMain.handle('app-version', () => app.getVersion())
ipcMain.handle('app-path',    () => RESOURCES)

// ── App ready ─────────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  log('='.repeat(50))
  log(`${APP_NAME} iniciando — v${app.getVersion()}`)
  log(`RESOURCES: ${RESOURCES}`)
  log(`userData:  ${app.getPath('userData')}`)
  log(`ICON_PATH: ${ICON_PATH} (existe: ${fs.existsSync(ICON_PATH)})`)
  log('='.repeat(50))

  // CRÍTICO: definir AppUserModelId para ícone correto na taskbar do Windows
  if (process.platform === 'win32') {
    app.setAppUserModelId('br.gov.nfse.validador')
  }

  // Iniciar servidor Python
  iniciarServidor()

  // Aguardar servidor
  try {
    await aguardarServidor()
    serverReady = true
  } catch (err) {
    log(`ERRO: ${err.message}`)
    dialog.showErrorBox(APP_NAME,
      `Não foi possível iniciar o servidor interno.\n\n${err.message}\n\nLog: ${LOG_FILE}`)
    app.quit()
    return
  }

  // Criar janela e tray
  criarJanela()
  criarTray()

  // Verificar atualizações após 10s (não bloquear abertura)
  if (autoUpdater && app.isPackaged) {
    setTimeout(() => verificarAtualizacao(), 10000)
    // Verificar a cada 30min
    setInterval(() => verificarAtualizacao(), 30 * 60 * 1000)
  }
})

// ── Auto-updater ──────────────────────────────────────────────────────────────
function verificarAtualizacao() {
  if (!autoUpdater) return
  log('Verificando atualizacoes...')
  autoUpdater.checkForUpdates().catch(err => log(`updater: ${err.message}`))
}

// Nova versão encontrada — perguntar ao usuário
autoUpdater?.on('update-available', (info) => {
  log(`Atualizacao disponivel: v${info.version}`)
  if (!mainWindow) return

  mainWindow.webContents.executeJavaScript(`
    (function() {
      // Remover banner anterior
      document.getElementById('electron-update-banner')?.remove()
      const b = document.createElement('div')
      b.id = 'electron-update-banner'
      b.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:9999;' +
        'background:var(--bg2,#161b22);border:1px solid #4ade80;border-radius:10px;' +
        'padding:14px 18px;max-width:340px;box-shadow:0 8px 32px rgba(0,0,0,.4);' +
        'animation:slideInRight .3s ease'
      b.innerHTML = \`
        <div style="display:flex;align-items:flex-start;gap:12px">
          <div style="font-size:22px">🔄</div>
          <div style="flex:1">
            <div style="font-size:12px;font-weight:600;color:#4ade80;margin-bottom:3px">
              Nova versao disponivel!
            </div>
            <div style="font-size:11px;color:#8b949e;margin-bottom:10px">
              v${info.version} esta pronto para baixar
            </div>
            <div style="display:flex;gap:8px">
              <button onclick="window.__electronDownloadUpdate()" id="btn-download-update"
                style="flex:1;padding:5px 12px;border-radius:6px;border:none;cursor:pointer;
                  background:#4ade80;color:#000;font-size:11px;font-weight:600">
                Baixar e instalar
              </button>
              <button onclick="document.getElementById('electron-update-banner').remove()"
                style="padding:5px 10px;border-radius:6px;border:1px solid #30363d;
                  cursor:pointer;background:transparent;color:#8b949e;font-size:11px">
                Depois
              </button>
            </div>
          </div>
        </div>
      \`
      document.body.appendChild(b)
    })()
  `).catch(() => {})
})

// Download concluído — notificar e instalar
autoUpdater?.on('update-downloaded', (info) => {
  log(`Download concluido: v${info.version}`)
  if (mainWindow) {
    mainWindow.webContents.executeJavaScript(`
      (function() {
        document.getElementById('electron-update-banner')?.remove()
        const b = document.createElement('div')
        b.id = 'electron-update-banner'
        b.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:9999;' +
          'background:var(--bg2,#161b22);border:1px solid #4ade80;border-radius:10px;' +
          'padding:14px 18px;max-width:340px;box-shadow:0 8px 32px rgba(0,0,0,.4)'
        b.innerHTML = \`
          <div style="display:flex;align-items:flex-start;gap:12px">
            <div style="font-size:22px">✅</div>
            <div style="flex:1">
              <div style="font-size:12px;font-weight:600;color:#4ade80;margin-bottom:3px">
                Pronto para instalar!
              </div>
              <div style="font-size:11px;color:#8b949e;margin-bottom:10px">
                A atualizacao sera instalada ao fechar o app
              </div>
              <button onclick="window.__electronInstallNow()"
                style="width:100%;padding:5px 12px;border-radius:6px;border:none;
                  cursor:pointer;background:#4ade80;color:#000;font-size:11px;font-weight:600">
                Reiniciar e instalar agora
              </button>
            </div>
          </div>
        \`
        document.body.appendChild(b)
      })()
    `).catch(() => {})
  }
})

autoUpdater?.on('error', (err) => log(`Updater erro: ${err.message}`))

// IPC para botões de update no renderer
ipcMain.handle('check-update-now', () => {
  log('Verificacao manual solicitada...')
  verificarAtualizacao()
  return { ok: true }
})

ipcMain.handle('download-update', () => {
  log('Iniciando download da atualizacao...')
  autoUpdater?.downloadUpdate()
})
ipcMain.handle('install-update', () => {
  log('Instalando atualizacao...')
  autoUpdater?.quitAndInstall()
})

// ── Encerrar servidor ao fechar ───────────────────────────────────────────────
app.on('window-all-closed', () => {
  // No macOS manter rodando; no Windows/Linux encerrar
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  log('Encerrando servidor Python...')
  if (serverProc && !serverProc.killed) {
    try { serverProc.kill('SIGTERM') } catch {}
  }
  if (tray) { tray.destroy() }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) criarJanela()
})
