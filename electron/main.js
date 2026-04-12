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

// Update via fetch direto — sem electron-updater (ver função verificarAtualizacao abaixo)

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

// Ícone NFS-e embutido em base64 (não depende de arquivo externo)
const ICON_B64 = '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'
const ICON_PATH = null  // não usado — ícone vem do base64

// Também tentar arquivo se existir (para desenvolvimento)
const ICON_CANDIDATES = [
  path.join(process.resourcesPath, 'app', 'nfse.ico'),
  path.join(__dirname, 'build', 'nfse.ico'),
  path.join(RESOURCES, 'nfse.ico'),
]
const ICON_FILE = ICON_CANDIDATES.find(p => fs.existsSync(p)) || null

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
let icon         = undefined  // ícone global — usado no updater e na janela

// ── Forçar instância única ────────────────────────────────────────────────────
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
      mainWindow.focus()
    } else {
      criarJanela()
    }
  })
}

// ── Iniciar servidor Python ───────────────────────────────────────────────────
async function iniciarServidor() {
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
    // 1. Verificar python embarcado (incluído no pacote)
    const pythonEmbed = path.join(RESOURCES, 'python', 'python.exe')
    let pythonCmd = 'python'

    if (fs.existsSync(pythonEmbed)) {
      pythonCmd = pythonEmbed
      log(`Usando Python embarcado: ${pythonEmbed}`)
    } else {
      // 2. Tentar python do sistema
      const pythonCmds = ['python', 'python3', 'py']
      let encontrado = false
      for (const cmd of pythonCmds) {
        try {
          const test = require('child_process').spawnSync(cmd, ['--version'],
            { timeout: 3000 })
          if (test.status === 0) {
            pythonCmd = cmd
            encontrado = true
            log(`Usando Python do sistema: ${cmd}`)
            break
          }
        } catch {}
      }

      if (!encontrado) {
        // 3. Python não encontrado — baixar python-embed automaticamente
        log('Python não encontrado — baixando Python Embarcado...')
        if (splashWindow && !splashWindow.isDestroyed()) {
          splashWindow.webContents.executeJavaScript(
            "document.querySelector('p') && (document.querySelector('p').textContent = 'Instalando Python...')"
          ).catch(() => {})
        }

        const pythonDir  = path.join(RESOURCES, 'python')
        const pythonExe  = path.join(pythonDir, 'python.exe')
        const pythonUrl  = 'https://www.python.org/ftp/python/3.13.0/python-3.13.0-embed-amd64.zip'
        const zipPath    = path.join(app.getPath('temp'), 'python-embed.zip')

        try {
          // Baixar zip
          const https = require('https')
          await new Promise((resolve, reject) => {
            const file = require('fs').createWriteStream(zipPath)
            https.get(pythonUrl, res => {
              res.pipe(file)
              file.on('finish', () => { file.close(); resolve() })
            }).on('error', reject)
          })

          // Extrair zip
          fs.mkdirSync(pythonDir, { recursive: true })
          const { execSync } = require('child_process')
          execSync(`powershell -command "Expand-Archive -Path '${zipPath}' -DestinationPath '${pythonDir}' -Force"`,
            { windowsHide: true })
          fs.unlinkSync(zipPath)

          // Instalar pip
          const getPip = path.join(app.getPath('temp'), 'get-pip.py')
          await new Promise((resolve, reject) => {
            https.get('https://bootstrap.pypa.io/get-pip.py', res => {
              const file = require('fs').createWriteStream(getPip)
              res.pipe(file)
              file.on('finish', () => { file.close(); resolve() })
            }).on('error', reject)
          })
          require('child_process').spawnSync(pythonExe, [getPip],
            { windowsHide: true, timeout: 60000 })
          fs.unlinkSync(getPip)

          pythonCmd = pythonExe
          log(`Python embarcado instalado em: ${pythonDir}`)
        } catch (e) {
          log(`Erro ao baixar Python: ${e.message}`)
          // Mostrar erro e sair
          dialog.showErrorBox('Python não encontrado',
            'O Python não está instalado e não foi possível baixá-lo automaticamente.\n\n' +
            'Instale o Python em: https://www.python.org/downloads/\n' +
            'Marque "Add Python to PATH" durante a instalação.\n\n' +
            'Após instalar, reinicie o NFS-e Validador.'
          )
          app.quit()
          return
        }
      }
    }
    log(`Python: ${pythonCmd}`)

    const pythonEnv = {
      ...process.env,
      PYTHONUTF8:       '1',
      PYTHONIOENCODING: 'utf-8',
      PYTHONUNBUFFERED: '1',
    }

    // Python já verificado acima

    // Instalar dependências se necessário (lxml)
    try {
      log('Verificando dependencias Python...')
      const check = require('child_process').spawnSync(
        pythonCmd, ['-c', 'import lxml'],
        { env: pythonEnv, timeout: 10000 }
      )
      if (check.status !== 0) {
        log('lxml nao encontrado — instalando...')
        // Atualizar splash com mensagem
        if (splashWindow && !splashWindow.isDestroyed()) {
          splashWindow.webContents.executeJavaScript(
            "document.querySelector('p') && (document.querySelector('p').textContent = 'Instalando dependências...')"
          ).catch(() => {})
        }
        require('child_process').spawnSync(
          pythonCmd, ['-m', 'pip', 'install', 'lxml', '--quiet'],
          { env: pythonEnv, timeout: 120000, windowsHide: true }
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
  // Atualizar mensagem na splash
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.executeJavaScript(
      "document.querySelector('p') && (document.querySelector('p').textContent = 'Servidor pronto!')"
    ).catch(() => {})
  }
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


// ── Tela de Splash ────────────────────────────────────────────────────────────
let splashWindow = null

function criarSplash() {
  splashWindow = new BrowserWindow({
    width:           380,
    height:          240,
    frame:           false,       // sem barra de título
    transparent:     false,
    resizable:       false,
    center:          true,
    alwaysOnTop:     true,
    skipTaskbar:     true,
    icon:            icon || undefined,
    backgroundColor: '#0F0A1E',
    webPreferences:  { nodeIntegration: false }
  })

  const html = `<!DOCTYPE html><html>
  <head><meta charset="UTF-8"><style>
    * { margin:0; padding:0; box-sizing:border-box }
    body {
      background:#0F0A1E; color:#F5F0FF;
      font-family:'Segoe UI',sans-serif;
      display:flex; flex-direction:column;
      align-items:center; justify-content:center;
      height:100vh; gap:16px;
      user-select:none;
    }
    .logo {
      width:64px; height:64px; border-radius:16px;
      background:linear-gradient(135deg,#B57BFF,#4D9FFF);
      display:flex; align-items:center; justify-content:center;
      font-size:32px;
    }
    h1 { font-size:18px; font-weight:600; color:#F5F0FF; letter-spacing:.3px }
    p  { font-size:12px; color:#8B70D0; }
    .dots { display:flex; gap:6px; margin-top:8px }
    .dot {
      width:7px; height:7px; border-radius:50%; background:#B57BFF;
      animation: bounce 1.2s infinite ease-in-out;
    }
    .dot:nth-child(2) { animation-delay:.2s; background:#4D9FFF }
    .dot:nth-child(3) { animation-delay:.4s; background:#FF6B35 }
    @keyframes bounce {
      0%,80%,100% { transform:scale(.6); opacity:.4 }
      40%          { transform:scale(1);  opacity:1  }
    }
  </style></head>
  <body>
    <div class="logo">✓</div>
    <div>
      <h1>NFS-e Validador</h1>
      <p style="text-align:center;margin-top:4px">Iniciando servidor...</p>
    </div>
    <div class="dots">
      <div class="dot"></div>
      <div class="dot"></div>
      <div class="dot"></div>
    </div>
  </body></html>`

  splashWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html))
  log('Splash exibido.')
}

function fecharSplash() {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.close()
    splashWindow = null
    log('Splash fechado.')
  }
}

// ── Criar janela principal ────────────────────────────────────────────────────
function criarJanela() {
  // Criar ícone — Windows prefere .ico para taskbar
  // Tentar arquivo .ico primeiro, depois base64 como fallback
  // icon é global — declarado acima
  try {
    if (ICON_FILE && fs.existsSync(ICON_FILE)) {
      // .ico nativo funciona melhor no Windows para taskbar
      icon = nativeImage.createFromPath(ICON_FILE)
      if (!icon.isEmpty()) {
        log(`Icone carregado via arquivo ICO: ${ICON_FILE}`)
      } else {
        throw new Error('ico vazio')
      }
    } else {
      throw new Error('arquivo ico nao encontrado')
    }
  } catch (e) {
    // Fallback: base64 embutido
    try {
      log(`Fallback base64: ${e.message}`)
      const buf = Buffer.from(ICON_B64, 'base64')
      icon = nativeImage.createFromBuffer(buf)
      if (!icon.isEmpty()) {
        log(`Icone carregado via base64 (${icon.getSize().width}x${icon.getSize().height})`)
      }
    } catch (e2) {
      log(`Erro icone: ${e2.message}`)
    }
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

  // Se há tray, minimizar para background em vez de fechar
  mainWindow.on('close', (e) => {
    if (!app.isQuitting && tray) {
      e.preventDefault()
      mainWindow.hide()
      log('Janela ocultada — app no tray')
    }
  })

  mainWindow.on('closed', () => { mainWindow = null })

  // Carregar app
  mainWindow.loadURL(URL)
  log(`Carregando: ${URL}`)
}

// ── Tray (ícone na bandeja do sistema) ───────────────────────────────────────
function criarTray() {
  try {
    // Usar o mesmo ícone já carregado pela janela principal (nunca é nulo)
    const trayIcon = icon || nativeImage.createFromPath(
      ICON_CANDIDATES.find(p => fs.existsSync(p)) || ''
    )
    if (!trayIcon || trayIcon.isEmpty()) {
      log('Tray: ícone não disponível — usando tray sem ícone')
    }
    tray = new Tray(trayIcon && !trayIcon.isEmpty() ? trayIcon : nativeImage.createEmpty())
    tray.setToolTip(APP_NAME)

    const menu = Menu.buildFromTemplate([
      { label: 'Abrir NFS-e Validador', click: () => {
        if (mainWindow) { mainWindow.show(); mainWindow.focus() }
        else criarJanela()
      }},
      { type: 'separator' },
      { label: 'Verificar documentos agora', click: () => {
        _trayVerificarDocs()
      }},
      { label: 'Verificar schemas agora', click: () => {
        _trayVerificarSchemas()
      }},
      { type: 'separator' },
      { label: 'Encerrar completamente', click: () => {
        app.isQuitting = true
        app.quit()
      }}
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


// ════════════════════════════════════════════════════════
// CONTROLE DE INSTALAÇÕES — Google Sheets
// Credenciais lidas do arquivo sheets_config.json (não vai pro git)
// ════════════════════════════════════════════════════════
let _SHEET_ID     = ''
let _CLIENT_EMAIL = ''
let _PRIVATE_KEY  = ''

// Carregar credenciais do arquivo de config (fora do código)
function _carregarCredenciaisSheets() {
  try {
    const configPath = path.join(RESOURCES, 'sheets_config.json')
    if (fs.existsSync(configPath)) {
      const cfg = JSON.parse(fs.readFileSync(configPath, 'utf8'))
      _SHEET_ID     = cfg.sheet_id     || ''
      _CLIENT_EMAIL = cfg.client_email || ''
      _PRIVATE_KEY  = cfg.private_key  || ''
      log('Sheets: credenciais carregadas de sheets_config.json')
      return true
    } else {
      log('Sheets: sheets_config.json não encontrado — monitoramento desativado')
      return false
    }
  } catch (e) {
    log(`Sheets: erro ao carregar credenciais: ${e.message}`)
    return false
  }
}


// Gerar JWT para autenticação Google
async function _gerarJWT() {
  const now   = Math.floor(Date.now() / 1000)
  const claim = {
    iss: _CLIENT_EMAIL,
    scope: 'https://www.googleapis.com/auth/spreadsheets',
    aud: 'https://oauth2.googleapis.com/token',
    exp: now + 3600,
    iat: now,
  }

  // Encode base64url
  const b64 = s => Buffer.from(JSON.stringify(s))
    .toString('base64')
    .replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'')

  const header  = b64({ alg:'RS256', typ:'JWT' })
  const payload = b64(claim)
  const signing = `${header}.${payload}`

  // Assinar com chave privada RSA
  const crypto = require('crypto')
  const sign   = crypto.createSign('RSA-SHA256')
  sign.update(signing)
  const sig = sign.sign(_PRIVATE_KEY, 'base64')
    .replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'')

  const jwt = `${signing}.${sig}`

  // Trocar JWT por access token
  const resp = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=${jwt}`
  })
  const data = await resp.json()
  return data.access_token
}

// Formatar data BR
function _dataBR(d = new Date()) {
  return d.toLocaleString('pt-BR', { timeZone:'America/Sao_Paulo',
    day:'2-digit', month:'2-digit', year:'numeric',
    hour:'2-digit', minute:'2-digit' })
}

// Registrar/atualizar máquina na planilha
async function _registrarMaquina() {
  // Verificar se credenciais estão carregadas
  if (!_SHEET_ID || !_CLIENT_EMAIL || !_PRIVATE_KEY) {
    log('Sheets: credenciais não configuradas — pulando registro')
    return
  }
  try {
    const os      = require('os')
    const maquina = os.hostname()
    const usuario = os.userInfo().username
    const versao  = 'v' + app.getVersion()
    const sistema = `${os.platform()} ${os.release()}`
    const agora   = _dataBR()
    const token   = await _gerarJWT()
    if (!token) { log('Sheets: falha ao obter token'); return }

    const base = `https://sheets.googleapis.com/v4/spreadsheets/${_SHEET_ID}`
    const auth = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }

    // Ler planilha atual
    const leitura = await fetch(`${base}/values/A:G`, { headers: auth })
    const dados   = await leitura.json()
    const linhas  = dados.values || []

    // Criar cabeçalho se planilha vazia
    if (linhas.length === 0) {
      await fetch(`${base}/values/A1:G1?valueInputOption=RAW`, {
        method: 'PUT', headers: auth,
        body: JSON.stringify({ values: [['Máquina','Usuário','Versão','Atualizado','Último acesso','Sistema','Observação']] })
      })
      linhas.push(['Máquina','Usuário','Versão','Atualizado','Último acesso','Sistema','Observação'])
    }

    // Verificar se máquina já existe (coluna A)
    let linhaExistente = -1
    for (let i = 1; i < linhas.length; i++) {
      if ((linhas[i][0] || '').toLowerCase() === maquina.toLowerCase()) {
        linhaExistente = i + 1  // linha 1-indexed
        break
      }
    }

    const atualizado = versao === ('v' + app.getVersion()) ? '✅ Sim' : '⚠️ Não'
    const novaLinha  = [maquina, usuario, versao, atualizado, agora, sistema, '']

    if (linhaExistente > 0) {
      // Atualizar linha existente
      await fetch(`${base}/values/A${linhaExistente}:G${linhaExistente}?valueInputOption=RAW`, {
        method: 'PUT', headers: auth,
        body: JSON.stringify({ values: [novaLinha] })
      })
      log(`Sheets: máquina ${maquina} atualizada (linha ${linhaExistente})`)
    } else {
      // Adicionar nova linha
      await fetch(`${base}/values/A:G:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`, {
        method: 'POST', headers: auth,
        body: JSON.stringify({ values: [novaLinha] })
      })
      log(`Sheets: nova máquina registrada: ${maquina}`)
    }
  } catch (ex) {
    log(`Sheets erro: ${ex.message}`)
  }
}


// ── Verificação em background + Notificações Windows ─────────────────────────
let _notifConfig = { docs: true, schemas: true, forum: false }

// IDs de notificações já enviadas — evita repetir na mesma sessão
const _notifEnviadas = new Set()

function _enviarNotificacaoWindows(titulo, corpo, onClick, dedupeKey) {
  try {
    // Deduplicação: não enviar a mesma notificação duas vezes na sessão
    if (dedupeKey && _notifEnviadas.has(dedupeKey)) {
      log(`Notificação ignorada (já enviada): ${dedupeKey}`)
      return
    }

    // Notificações do Windows funcionam sem tray a partir do Electron 13+
    // mas exigem que o app tenha AppUserModelId definido
    const { Notification } = require('electron')
    if (!Notification.isSupported()) {
      log('Notificações não suportadas neste sistema')
      return
    }

    const notif = new Notification({
      title:       titulo,
      body:        corpo,
      icon:        icon || undefined,
      silent:      false,
      timeoutType: 'default',
      appName:     APP_NAME,
    })

    if (onClick) notif.on('click', onClick)

    notif.on('failed', (e, err) => log(`Notificação falhou: ${err}`))
    notif.show()

    if (dedupeKey) _notifEnviadas.add(dedupeKey)
    log(`Notificação enviada: ${titulo}`)

    // Atualizar tooltip do tray para refletir novidade
    if (tray) tray.setToolTip(`${APP_NAME} — ${titulo}`)

  } catch (e) {
    log(`Notificação erro: ${e.message}`)
  }
}

// ── Feedback visual no tray ao verificar manualmente ─────────────────────────
function _trayFeedback(msg, resetMs) {
  if (!tray) return
  tray.setToolTip(`${APP_NAME}\n${msg}`)
  if (resetMs) setTimeout(() => { if (tray) tray.setToolTip(APP_NAME) }, resetMs)
}

function _trayNotificar(titulo, corpo, onClick) {
  // Notificação balloon nativa do Windows via tray
  if (tray && process.platform === 'win32') {
    tray.displayBalloon({
      iconType: 'info',
      title:    titulo,
      content:  corpo,
    })
    if (onClick) tray.once('balloon-click', onClick)
  }
  // Também envia notificação normal
  _enviarNotificacaoWindows(titulo, corpo, onClick, `tray-${titulo}`)
}

async function _trayVerificarDocs() {
  if (!serverReady) {
    dialog.showMessageBox({ type: 'info', title: 'NFS-e Validador',
      message: 'Servidor ainda inicializando.', detail: 'Aguarde alguns segundos e tente novamente.', buttons: ['OK'] })
    return
  }
  log('Tray: verificação manual de documentos iniciada')

  // Mostrar janela com progresso imediatamente
  if (mainWindow) { mainWindow.show(); mainWindow.focus() }
  else criarJanela()

  _trayFeedback('🔍 Verificando documentos gov.br...')
  _updateBanner('🔍 Verificando documentos gov.br...', 10)

  try {
    const r = await fetch(`http://localhost:${PORT}/api/monitorar-docs`)
    const d = await r.json()
    if (!d.ok) {
      _updateBanner('❌ Erro ao verificar documentos', 0)
      _trayFeedback('❌ Erro ao verificar documentos', 8000)
      dialog.showMessageBox({ type: 'error', title: 'Erro', message: 'Não foi possível verificar documentos.', buttons: ['OK'] })
      return
    }

    // Progresso visual no banner + tooltip
    let seg = 45
    _updateBanner(`⏳ Verificando documentos... ${seg}s`, 20)
    const intervalo = setInterval(() => {
      seg--
      const pct = Math.round((45 - seg) / 45 * 80) + 10
      if (tray) tray.setToolTip(`${APP_NAME}\n⏳ Verificando documentos... ${seg}s`)
      _updateBanner(`⏳ Verificando documentos... ${seg}s`, pct)
      if (seg <= 0) clearInterval(intervalo)
    }, 1000)

    await new Promise(resolve => setTimeout(resolve, 45000))
    clearInterval(intervalo)

    const r2 = await fetch(`http://localhost:${PORT}/api/docs`)
    const d2 = await r2.json()
    const novas = d2.novas?.length || 0

    if (novas > 0) {
      const titulos = d2.novas.map(n => n.titulo || n.id).slice(0, 2).join(', ')
      _updateBanner(`✅ ${novas} novo(s) documento(s) encontrado(s)!`, 100)
      _trayFeedback(`✅ ${novas} novo(s) documento(s)!`, 15000)
      _trayNotificar(`📄 ${novas} novo(s) documento(s) no gov.br!`,
        titulos + (novas > 2 ? ` e mais ${novas - 2}...` : ''),
        () => { if (mainWindow) { mainWindow.show(); mainWindow.focus() } else criarJanela() })
      setTimeout(() => _removerBanner(), 8000)
    } else {
      _updateBanner('✅ Documentos: nenhuma novidade encontrada', 100)
      _trayFeedback('✅ Documentos: nenhuma novidade', 8000)
      _trayNotificar('Documentos gov.br', 'Verificação concluída — nenhuma novidade encontrada.')
      setTimeout(() => _removerBanner(), 5000)
    }

  } catch (e) {
    log(`Tray docs erro: ${e.message}`)
    _updateBanner(`❌ Erro: ${e.message}`, 0)
    _trayFeedback('❌ Erro na verificação', 8000)
    setTimeout(() => _removerBanner(), 8000)
  }
}

async function _trayVerificarSchemas() {
  if (!serverReady) {
    dialog.showMessageBox({ type: 'info', title: 'NFS-e Validador',
      message: 'Servidor ainda inicializando.', detail: 'Aguarde alguns segundos e tente novamente.', buttons: ['OK'] })
    return
  }
  log('Tray: verificação manual de schemas iniciada')

  // Abrir janela e mostrar progresso imediatamente
  if (mainWindow) { mainWindow.show(); mainWindow.focus() }
  else criarJanela()

  _trayFeedback('🔄 Verificando schemas XSD...')
  _updateBanner('🔄 Verificando schemas XSD...', 10)

  try {
    const rAntes = await fetch(`http://localhost:${PORT}/api/notificacoes`)
    const dAntes = await rAntes.json()
    const zipAntes = dAntes.schemas?.[0]?.arquivo || ''

    const r = await fetch(`http://localhost:${PORT}/api/atualizar-schemas`)
    const d = await r.json()
    if (!d.ok) {
      _updateBanner('❌ Erro ao verificar schemas', 0)
      _trayFeedback('❌ Erro ao verificar schemas', 8000)
      dialog.showMessageBox({ type: 'error', title: 'Erro', message: 'Não foi possível verificar schemas XSD.', buttons: ['OK'] })
      setTimeout(() => _removerBanner(), 5000)
      return
    }

    // Progresso visual no banner + tooltip
    let seg = 30
    _updateBanner(`⏳ Verificando schemas XSD... ${seg}s`, 15)
    const intervalo = setInterval(() => {
      seg--
      const pct = Math.round((30 - seg) / 30 * 80) + 10
      if (tray) tray.setToolTip(`${APP_NAME}\n⏳ Verificando schemas XSD... ${seg}s`)
      _updateBanner(`⏳ Verificando schemas XSD... ${seg}s`, pct)
      if (seg <= 0) clearInterval(intervalo)
    }, 1000)

    await new Promise(resolve => setTimeout(resolve, 30000))
    clearInterval(intervalo)

    const rDepois = await fetch(`http://localhost:${PORT}/api/notificacoes`)
    const dDepois = await rDepois.json()
    const zipDepois = dDepois.schemas?.[0]?.arquivo || ''

    if (zipDepois && zipDepois !== zipAntes) {
      const schema = dDepois.schemas[0]
      _updateBanner('✅ Schemas XSD atualizados!', 100)
      _trayFeedback('✅ Schemas atualizados!', 15000)
      _trayNotificar('🔄 Schemas XSD atualizados!', schema?.titulo || 'Nova versão instalada.',
        () => { if (mainWindow) { mainWindow.show(); mainWindow.focus() } else criarJanela() })
      setTimeout(() => _removerBanner(), 8000)
    } else {
      _updateBanner('✅ Schemas já estão atualizados', 100)
      _trayFeedback('✅ Schemas: já atualizados', 8000)
      _trayNotificar('Schemas XSD', 'Verificação concluída — schemas já estão atualizados.')
      setTimeout(() => _removerBanner(), 5000)
    }

  } catch (e) {
    log(`Tray schemas erro: ${e.message}`)
    _updateBanner(`❌ Erro: ${e.message}`, 0)
    _trayFeedback('❌ Erro na verificação', 8000)
    setTimeout(() => _removerBanner(), 8000)
  }
}

async function _verificarDocsBackground() {
  if (!_notifConfig.docs) return
  if (!serverReady) return
  log('Background: verificando documentos...')
  try {
    // 1. Disparar monitoramento
    const r = await fetch(`http://localhost:${PORT}/api/monitorar-docs`)
    const d = await r.json()
    if (!d.ok) { log('Background docs: monitorar-docs retornou erro'); return }

    // 2. Aguardar 45s para o monitorar_docs.py terminar de scraping
    //    (era 30s mas o site do gov.br pode ser lento)
    log('Background docs: aguardando 45s para resultado...')
    await new Promise(resolve => setTimeout(resolve, 45000))

    // 3. Buscar resultado
    const r2 = await fetch(`http://localhost:${PORT}/api/docs`)
    const d2 = await r2.json()
    const novas = d2.novas?.length || 0

    log(`Background docs: ${novas} documento(s) novo(s) encontrado(s)`)

    if (novas > 0) {
      const titulos = d2.novas.map(n => n.titulo || n.id).slice(0, 3).join(', ')
      const dedupeKey = `docs-${d2.novas.map(n => n.id).sort().join('-')}`

      _enviarNotificacaoWindows(
        `📄 ${novas} novo(s) documento(s) no gov.br!`,
        titulos + (novas > 3 ? ` e mais ${novas - 3}...` : ''),
        () => {
          if (mainWindow) { mainWindow.show(); mainWindow.focus() }
          else criarJanela()
        },
        dedupeKey
      )
    } else {
      // Sem novas NTs — resetar tooltip do tray
      if (tray) tray.setToolTip(APP_NAME)
    }

  } catch (e) {
    log(`Background docs erro: ${e.message}`)
  }
}

async function _verificarSchemasBackground() {
  if (!_notifConfig.schemas) return
  if (!serverReady) return
  log('Background: verificando schemas XSD...')
  try {
    // 1. Capturar estado ANTES da verificação
    const rAntes = await fetch(`http://localhost:${PORT}/api/notificacoes`)
    const dAntes = await rAntes.json()
    const zipAntes = dAntes.schemas?.[0]?.arquivo || ''

    // 2. Disparar atualização de schemas
    const r = await fetch(`http://localhost:${PORT}/api/atualizar-schemas`)
    const d = await r.json()
    if (!d.ok) { log(`Background schemas: erro na API`); return }

    log('Background schemas: aguardando 30s para conclusão...')
    await new Promise(resolve => setTimeout(resolve, 30000))

    // 3. Verificar estado DEPOIS — se mudou, houve atualização
    const rDepois = await fetch(`http://localhost:${PORT}/api/notificacoes`)
    const dDepois = await rDepois.json()
    const zipDepois = dDepois.schemas?.[0]?.arquivo || ''

    if (zipDepois && zipDepois !== zipAntes) {
      // Schema novo detectado pela comparação
      const schema = dDepois.schemas[0]
      const dedupeKey = `schemas-${zipDepois}`
      _enviarNotificacaoWindows(
        '🔄 Schemas XSD atualizados!',
        `${schema.titulo} — ${schema.subtitulo || ''}`,
        () => {
          if (mainWindow) { mainWindow.show(); mainWindow.focus() }
          else criarJanela()
        },
        dedupeKey
      )
      log(`Schemas atualizados: ${zipAntes} → ${zipDepois}`)
    } else {
      log(`Background schemas: sem novidades (${zipDepois || 'nenhum zip'})`)
    }
  } catch (e) {
    log(`Background schemas erro: ${e.message}`)
  }
}

// Verificações automáticas em background (a cada 4h)
function _iniciarVerificacoesBackground() {
  const INTERVALO = 4 * 60 * 60 * 1000  // 4 horas

  // Primeira verificação após 3 minutos (servidor precisa estar estável)
  setTimeout(() => {
    _verificarDocsBackground()
    // Schemas com delay extra para não sobrecarregar no boot
    setTimeout(() => _verificarSchemasBackground(), 60000)
  }, 3 * 60 * 1000)

  // Repetir a cada 4h com offset de 10min entre docs e schemas
  setInterval(() => {
    _verificarDocsBackground()
    setTimeout(() => _verificarSchemasBackground(), 10 * 60 * 1000)
  }, INTERVALO)

  log('Verificações em background ativadas (a cada 4h, primeira em 3min)')
}

// IPC para configurações de notificação
ipcMain.handle('get-notif-config', () => _notifConfig)
ipcMain.handle('set-notif-config', (_, config) => {
  _notifConfig = { ..._notifConfig, ...config }
  log(`Config notificações: ${JSON.stringify(_notifConfig)}`)
  return _notifConfig
})

// IPC: fórum detectou novos tópicos — disparar notificação Windows
ipcMain.handle('notificar-forum', (_, titulo, quantidade) => {
  if (!_notifConfig.forum) return { ok: false, motivo: 'forum desativado' }
  const corpo = quantidade === 1
    ? titulo
    : `${quantidade} novos tópicos — veja na aba Fórum`
  _enviarNotificacaoWindows(
    '💬 Fórum NFS-e Brasil',
    corpo,
    () => {
      if (mainWindow) { mainWindow.show(); mainWindow.focus() }
      else criarJanela()
    },
    `forum-${titulo}`
  )
  return { ok: true }
})

// IPC: disparar monitoramento de documentos manualmente pelo frontend
ipcMain.handle('monitorar-docs-agora', async () => {
  log('Monitoramento manual solicitado pelo usuário')
  await _verificarDocsBackground()
  return { ok: true }
})

// ── App ready ─────────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  log('='.repeat(50))
  log(`${APP_NAME} iniciando — v${app.getVersion()}`)
  log(`RESOURCES: ${RESOURCES}`)
  log(`userData:  ${app.getPath('userData')}`)
  log(`Icone: base64 embutido (${ICON_B64.length} chars) + arquivo: ${ICON_FILE || "nao encontrado"}`)
  log('='.repeat(50))

  // CRÍTICO: definir AppUserModelId para ícone correto na taskbar do Windows
  if (process.platform === 'win32') {
    app.setAppUserModelId('br.gov.nfse.validador')
  }

  // Mostrar splash enquanto inicia
  const _splashInicio = Date.now()
  criarSplash()

  // Iniciar servidor Python
  await iniciarServidor()

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

  // Garantir tempo mínimo de 2.5s para splash ser visível
  const _tempoSplash = Date.now() - _splashInicio
  const _espera = Math.max(0, 2500 - _tempoSplash)

  setTimeout(() => {
    fecharSplash()
    criarJanela()
    criarTray()
  }, _espera)

  // Iniciar verificações em background
  _iniciarVerificacoesBackground()

  // Registrar máquina no Google Sheets (controle de instalações)
  _carregarCredenciaisSheets()
  setTimeout(() => _registrarMaquina(), 5000)
  // Atualizar a cada 4 horas
  setInterval(() => _registrarMaquina(), 4 * 60 * 60 * 1000)

  // Verificar atualizações após 10s (não bloquear abertura)
  if (app.isPackaged) {
    setTimeout(() => verificarAtualizacao(), 10000)
    // Verificar a cada 30min
    setInterval(() => verificarAtualizacao(), 30 * 60 * 1000)
  }
})

// ════════════════════════════════════════════════════════
// AUTO-UPDATE VIA FETCH DIRETO — sem electron-updater
// Fluxo: versao.json → compara → baixa .exe → fecha app → instala
// ════════════════════════════════════════════════════════

const GITHUB_OWNER = 'XMLVariavel'
const GITHUB_REPO  = 'nfse-validador'
const VERSAO_URL   = `https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/main/versao.json`
const RELEASE_BASE = `https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/releases/download`

let _updateDisponivel    = null
let _downloadEmAndamento = false

// ── Normalizar versão para comparação — "3.8" == "3.8.0", "3.10" > "3.9" ────
const _normalizar = v => v.replace(/^v/, '').split('.').map(n => parseInt(n) || 0)
const _comparar   = (a, b) => {
  const na = _normalizar(a), nb = _normalizar(b)
  const len = Math.max(na.length, nb.length)
  for (let i = 0; i < len; i++) {
    const diff = (na[i] || 0) - (nb[i] || 0)
    if (diff !== 0) return diff
  }
  return 0
}

// ── Verificar nova versão ────────────────────────────────────────────────────
async function verificarAtualizacao() {
  log('Verificando atualizacoes via versao.json...')
  try {
    const resp = await fetch(VERSAO_URL, {
      headers: { 'Cache-Control': 'no-cache', 'User-Agent': `NFS-e-Validador/${app.getVersion()}` }
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const remote = await resp.json()

    const versaoRemota = (remote.versao || '').trim()
    const versaoLocal  = app.getVersion().trim()

    log(`Versao local: ${versaoLocal} | Remota: ${versaoRemota}`)

    if (!versaoRemota || _comparar(versaoRemota, versaoLocal) <= 0) {
      log('Sem atualizacoes disponíveis.')
      return
    }

    // Montar informações do update — delta ZIP ou instalador completo
    const zipName  = `update-${versaoRemota}.zip`
    const zipUrl   = `${RELEASE_BASE}/v${versaoRemota}/${zipName}`
    const exeName  = `NFS-e-Validador-Setup-${versaoRemota}.exe`
    const exeUrl   = `${RELEASE_BASE}/v${versaoRemota}/${exeName}`

    // Preferir update_zip do versao.json se informado, senão montar URL padrão
    const updateZipUrl = remote.update_zip || zipUrl

    _updateDisponivel = {
      versao:       versaoRemota,
      data:         remote.data || '',
      zipUrl:       updateZipUrl,
      zipName,
      exeUrl,
      exeName,
      tipoUpdate:   'delta'  // começa tentando delta
    }
    log(`Atualizacao disponivel: v${versaoRemota} | ZIP: ${updateZipUrl}`)

    _perguntarUpdate(_updateDisponivel)

  } catch (err) {
    log(`Erro ao verificar atualizacao: ${err.message}`)
  }
}

// ── Dialog de confirmação ────────────────────────────────────────────────────
function _perguntarUpdate({ versao, data }) {
  const dataFmt = data ? ` · ${data}` : ''
  if (mainWindow) {
    mainWindow.webContents.executeJavaScript(
      `typeof _mostrarUpdateNaAjuda === 'function' && _mostrarUpdateNaAjuda('${versao}', '${data}')`
    ).catch(() => {})
  }
  dialog.showMessageBox(mainWindow || BrowserWindow.getFocusedWindow(), {
    type:      'info',
    title:     'Atualizacao disponivel',
    message:   `NFS-e Validador v${versao}${dataFmt}`,
    detail:    'Uma nova versao esta disponivel.\n\n' +
               '✅ Atualizacao rapida — baixa apenas os arquivos alterados (~3MB)\n' +
               '   O app reinicia automaticamente sem precisar reinstalar.',
    buttons:   ['Atualizar agora', 'Depois'],
    defaultId: 0,
    cancelId:  1,
    icon:      icon || undefined,
  }).then(result => {
    if (result.response === 0) _baixarEAplicarDelta(_updateDisponivel)
    else log('Usuario adiou o update.')
  })
}

// ── Download do ZIP delta e aplicação ────────────────────────────────────────
async function _baixarEAplicarDelta({ versao, zipUrl, zipName, exeUrl, exeName }) {
  if (_downloadEmAndamento) return
  _downloadEmAndamento = true

  const fs_   = require('fs')
  const path_ = require('path')
  const zipPath = path_.join(app.getPath('temp'), zipName)

  log(`Baixando delta ZIP: ${zipUrl} -> ${zipPath}`)
  _updateBanner('Iniciando download da atualizacao...', 0)

  try {
    // 1. Baixar o ZIP delta
    await _baixarArquivo(zipUrl, zipPath, (pct, mbB, mbT) => {
      _updateBanner(`${pct}% — ${mbB} MB de ${mbT} MB`, pct)
    })

    log('ZIP delta baixado: ' + zipPath)
    _updateBanner('Preparando instalacao...', 100)

    // 2. Confirmar com usuário
    const { response } = await dialog.showMessageBox(
      mainWindow || BrowserWindow.getFocusedWindow(), {
      type:      'info',
      title:     'Pronto para atualizar',
      message:   `v${versao} baixada com sucesso!`,
      detail:    'O NFS-e Validador sera fechado, atualizado e reaberto automaticamente.\n\nIsso leva apenas alguns segundos.',
      buttons:   ['Atualizar agora', 'Atualizar depois'],
      defaultId: 0,
      cancelId:  1,
      icon:      icon || undefined,
    })

    if (response !== 0) {
      _updateDisponivel.zipPath = zipPath
      log('Atualizacao adiada. ZIP salvo em: ' + zipPath)
      _downloadEmAndamento = false
      return
    }

    // 3. Criar script .bat que aplica o ZIP e reinicia o app
    await _aplicarDeltaViaScript(zipPath, versao)

  } catch (err) {
    log(`Erro no download delta: ${err.message}`)
    _downloadEmAndamento = false

    // Fallback: oferecer instalador completo
    const { response } = await dialog.showMessageBox(
      mainWindow || BrowserWindow.getFocusedWindow(), {
      type:    'warning',
      title:   'Erro na atualizacao rapida',
      message: `Nao foi possivel baixar a atualizacao delta:\n${err.message}`,
      detail:  'Deseja baixar o instalador completo como alternativa?',
      buttons: ['Baixar instalador completo', 'Cancelar'],
      defaultId: 0,
      cancelId:  1,
    })

    if (response === 0) {
      _downloadEmAndamento = false
      _baixarEInstalarCompleto({ versao, url: exeUrl, exeName })
    }
  }
}

// ── Aplicar ZIP delta via script .bat externo ────────────────────────────────
async function _aplicarDeltaViaScript(zipPath, versao) {
  const fs_   = require('fs')
  const path_ = require('path')

  // Pasta de instalação atual
  const installDir = path_.dirname(process.execPath)

  // Caminho do script updater
  const batPath = path_.join(app.getPath('temp'), 'nfse_updater.bat')

  // Caminho do app para reiniciar
  const appExe  = process.execPath

  // Script .bat que:
  // 1. Espera o app fechar (3s)
  // 2. Extrai o ZIP sobre a pasta de instalação usando PowerShell
  // 3. Reabre o app
  const batScript = `@echo off
echo NFS-e Validador - Aplicando atualizacao v${versao}...
ping 127.0.0.1 -n 4 >nul

echo Extraindo arquivos...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '${zipPath.replace(/\\/g, '\\\\')}' -DestinationPath '${installDir.replace(/\\/g, '\\\\')}' -Force"

if errorlevel 1 (
    echo ERRO ao extrair ZIP
    pause
    exit /b 1
)

echo Atualizacao aplicada com sucesso!
echo Reiniciando NFS-e Validador...
ping 127.0.0.1 -n 2 >nul
start "" "${appExe.replace(/\\/g, '\\\\')}"
exit
`

  fs_.writeFileSync(batPath, batScript, { encoding: 'utf8' })
  log(`Script updater criado: ${batPath}`)
  log(`Diretorio de instalacao: ${installDir}`)

  // Executar o script e fechar o app
  const { spawn: _sp } = require('child_process')
  _sp('cmd.exe', ['/c', batPath], {
    detached:    true,
    windowsHide: false,
    stdio:       'ignore',
  }).unref()

  log('Updater iniciado — fechando app...')
  setTimeout(() => {
    app.isQuitting = true
    app.quit()
  }, 500)
}

// ── Fallback: instalar completo ───────────────────────────────────────────────
async function _baixarEInstalarCompleto({ versao, url, exeName }) {
  if (_downloadEmAndamento) return
  _downloadEmAndamento = true

  const destPath = path.join(app.getPath('temp'), exeName)
  log(`Baixando instalador completo: ${url} -> ${destPath}`)
  _updateBanner('Baixando instalador completo...', 0)

  try {
    await _baixarArquivo(url, destPath, (pct, mbB, mbT) => {
      _updateBanner(`${pct}% — ${mbB} MB de ${mbT} MB`, pct)
    })
    log('Instalador baixado: ' + destPath)
    _updateBanner('Download concluido! Aguarde...', 100)

    const { response } = await dialog.showMessageBox(
      mainWindow || BrowserWindow.getFocusedWindow(), {
      type:      'info',
      title:     'Pronto para instalar',
      message:   `v${versao} baixada com sucesso!`,
      detail:    'O NFS-e Validador sera fechado e o instalador executado silenciosamente.',
      buttons:   ['Instalar agora', 'Instalar depois'],
      defaultId: 0,
      cancelId:  1,
      icon:      icon || undefined,
    })

    if (response === 0) _executarInstalador(destPath)
    else {
      _updateDisponivel.exePath = destPath
      _downloadEmAndamento = false
    }
  } catch (err) {
    log(`Erro no instalador completo: ${err.message}`)
    _downloadEmAndamento = false
    dialog.showErrorBox('Erro no download',
      `Nao foi possivel baixar a atualizacao:\n\n${err.message}\n\nTente novamente mais tarde.`)
  }
}

// ── Download com progresso e redirect ─────────────────────────────────────────
function _baixarArquivo(url, destPath, onProgress) {
  return new Promise((resolve, reject) => {
    const https_ = require('https')
    const http_  = require('http')
    const fs_    = require('fs')
    const _fazer = (urlAtual) => {
      const client = urlAtual.startsWith('https') ? https_ : http_
      client.get(urlAtual, { headers: { 'User-Agent': `NFS-e-Validador/${app.getVersion()}` } }, res => {
        if ([301, 302, 307, 308].includes(res.statusCode)) {
          log(`Redirect -> ${res.headers.location}`)
          _fazer(res.headers.location); return
        }
        if (res.statusCode !== 200) { reject(new Error(`HTTP ${res.statusCode}`)); return }
        const total = parseInt(res.headers['content-length'] || '0')
        let baixado = 0
        const file = fs_.createWriteStream(destPath)
        res.on('data', chunk => {
          baixado += chunk.length
          if (total > 0 && onProgress) {
            onProgress(
              Math.round(baixado * 100 / total),
              (baixado / 1048576).toFixed(1),
              (total   / 1048576).toFixed(1)
            )
          }
        })
        res.pipe(file)
        file.on('finish', () => { file.close(); resolve() })
        file.on('error',  e => { fs_.unlink(destPath, () => {}); reject(e) })
        res.on('error',   e => { fs_.unlink(destPath, () => {}); reject(e) })
      }).on('error', reject)
    }
    _fazer(url)
  })
}

// ── Instalador completo (fallback) ─────────────────────────────────────────────
function _executarInstalador(exePath) {
  log('Executando instalador: ' + exePath)
  _updateBanner('Aguardando verificacao de seguranca...', 99)
  setTimeout(() => {
    try {
      const { spawn: _sp } = require('child_process')
      _sp(exePath, ['/SILENT', '/CLOSEAPPLICATIONS', '/CURRENTUSER'], {
        detached: true, windowsHide: false, stdio: 'ignore'
      }).unref()
      setTimeout(() => { app.isQuitting = true; app.quit() }, 1000)
    } catch (err) {
      log('Erro ao executar instalador: ' + err.message)
      const { shell: _sh } = require('electron')
      _sh.showItemInFolder(exePath)
      dialog.showMessageBox({ type: 'info', title: 'Instalar manualmente',
        message: 'Nao foi possivel executar o instalador automaticamente.',
        detail: `O arquivo foi baixado em:\n${exePath}\n\nExecute-o manualmente.`
      })
    }
  }, 5000)
}

// ── Banner de progresso no app ─────────────────────────────────────────────────
function _updateBanner(texto, pct) {
  if (!mainWindow) return
  mainWindow.webContents.executeJavaScript(`
    (function(){
      let b = document.getElementById('electron-update-banner')
      if (!b) {
        b = document.createElement('div'); b.id = 'electron-update-banner'
        b.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:9999;background:#161b22;border:1px solid #4ade80;border-radius:10px;padding:14px 18px;min-width:280px;max-width:340px;box-shadow:0 8px 32px rgba(0,0,0,.4)'
        document.body.appendChild(b)
      }
      b.innerHTML =
        '<div style="display:flex;gap:10px;align-items:center;margin-bottom:8px">' +
          '<div style="font-size:18px">⬇️</div>' +
          '<div><div style="font-size:11px;font-weight:600;color:#4ade80">Atualizando NFS-e Validador...</div>' +
          '<div style="font-size:10px;color:#8b949e;margin-top:2px">${texto.replace(/\'/g, "\\'")}</div></div></div>' +
        '<div style="height:4px;background:#21262d;border-radius:2px;overflow:hidden">' +
          '<div style="height:100%;width:${pct}%;background:#4ade80;transition:width .3s;border-radius:2px"></div></div>'
    })()
  `).catch(() => {})
}

// ── IPC handlers ───────────────────────────────────────────────────────────────
ipcMain.handle('check-update-now', () => {
  log('Verificacao manual solicitada...')
  verificarAtualizacao()
  return { ok: true }
})
ipcMain.handle('download-update', () => {
  if (_updateDisponivel) _baixarEAplicarDelta(_updateDisponivel)
  else verificarAtualizacao()
})
ipcMain.handle('install-update', () => {
  if (_updateDisponivel?.zipPath) _aplicarDeltaViaScript(_updateDisponivel.zipPath, _updateDisponivel.versao)
  else if (_updateDisponivel?.exePath) _executarInstalador(_updateDisponivel.exePath)
})

// Recarregar// Recarregar janela após update dos arquivos Python/HTML
ipcMain.handle('reload-app', () => {
  log('Recarregando app apos update...')
  if (mainWindow) {
    setTimeout(() => mainWindow.loadURL(URL), 1500)
  }
})

// Abrir pasta de recursos (para debug)
ipcMain.handle('open-resources', () => {
  shell.openPath(RESOURCES)
})

// ── Encerrar servidor ao fechar ───────────────────────────────────────────────
// Ao fechar janela: minimizar para tray se tray existir, senão encerrar
app.on('window-all-closed', () => {
  if (process.platform === 'darwin') return
  if (tray) {
    // Tray ativo — manter rodando em background
    log('Janela fechada — app continua em background no tray')
  } else {
    // Sem tray — encerrar completamente para não ficar processo zumbi
    log('Janela fechada — sem tray, encerrando app')
    app.isQuitting = true
    app.quit()
  }
})

app.on('before-quit', () => {
  log('Encerrando servidor Python...')
  app.isQuitting = true
  if (serverProc && !serverProc.killed) {
    try { serverProc.kill('SIGTERM') } catch {}
    // Forçar SIGKILL após 2s se ainda não morreu
    setTimeout(() => {
      try {
        if (serverProc && !serverProc.killed) serverProc.kill('SIGKILL')
      } catch {}
    }, 2000)
  }
  if (tray) { try { tray.destroy() } catch {} tray = null }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) criarJanela()
})
