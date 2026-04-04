"""
launcher.py — NFS-e Validador v3.1
Inicia o servidor Python e abre Chrome/Edge em modo App.
Sem janela CMD. Log em AppData\Local.
"""

import sys, os, time, threading, subprocess, webbrowser
from pathlib import Path

# ── Caminhos ──────────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    # Empacotado: exe está em DATA, libs em _MEIPASS
    BASE = Path(sys._MEIPASS)   # libs Python (lxml, etc.)
    DATA = Path(sys.executable).parent  # tabelas/, schemas/, static/
else:
    BASE = Path(__file__).parent
    DATA = BASE

PORT = 8000
URL  = f"http://localhost:{PORT}"

# ── Log em AppData\Local (sempre gravável sem admin) ─────────────────────────
try:
    _appdata = Path(os.environ.get("LOCALAPPDATA") or
                    os.environ.get("APPDATA") or str(DATA))
    _logdir  = _appdata / "NFS-e Validador" / "logs"
    _logdir.mkdir(parents=True, exist_ok=True)
    _log = open(_logdir / "launcher.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = _log
    sys.stderr = _log
except Exception:
    pass  # sem log é ok — o app abre mesmo assim

def _log_print(msg):
    try:
        print(msg, flush=True)
    except Exception:
        pass

_log_print(f"\n{'='*50}")
_log_print(f"NFS-e Validador iniciando {time.strftime('%Y-%m-%d %H:%M:%S')}")
_log_print(f"BASE={BASE}")
_log_print(f"DATA={DATA}")

# ── Configurar ambiente Python ────────────────────────────────────────────────
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(DATA))
os.chdir(str(DATA))  # server.py precisa do CWD = DATA para achar tabelas/

# ── Iniciar servidor HTTP em thread ──────────────────────────────────────────
def _iniciar_servidor():
    """Executa server.py no mesmo processo Python do exe."""
    import traceback as _tb

    # server.py está em _internal ao lado do exe
    server_path = BASE / "server.py"
    if not server_path.exists():
        server_path = DATA / "server.py"

    _log_print(f"server.py: {server_path} exists={server_path.exists()}")

    if not server_path.exists():
        _log_print("ERRO: server.py nao encontrado!")
        return

    # Executar server.py lendo e compilando o código diretamente
    # Isso garante que usa os módulos já carregados no _internal
    try:
        _log_print("Executando server.py...")
        with open(str(server_path), encoding="utf-8") as _f:
            _codigo = _f.read()

        # Namespace limpo com __file__ apontando para o server.py real
        _ns = {
            "__name__": "__main__",
            "__file__": str(server_path),
            "__spec__": None,
        }
        exec(compile(_codigo, str(server_path), "exec"), _ns)

    except SystemExit:
        pass  # server.py chamou sys.exit normalmente
    except Exception:
        _log_print(f"ERRO no server.py:\n{_tb.format_exc()}")

_srv = threading.Thread(target=_iniciar_servidor, daemon=True, name="servidor")
_srv.start()

# ── Aguardar servidor responder (máx 20s) ────────────────────────────────────
import urllib.request

def _aguardar(timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(URL + "/api/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.4)
    return False

_log_print("Aguardando servidor na porta 8000...")
if not _aguardar():
    _log_print("TIMEOUT: servidor nao respondeu em 20s")
    # Mostrar erro ao usuario (sem console, usar messagebox)
    try:
        import tkinter as tk
        from tkinter import messagebox
        _root = tk.Tk(); _root.withdraw()
        messagebox.showerror(
            "NFS-e Validador",
            "Nao foi possivel iniciar o servidor interno.\n\n"
            "Verifique se a porta 8000 nao esta sendo usada por outro programa.\n\n"
            f"Log: {_logdir / 'launcher.log'}"
        )
        _root.destroy()
    except Exception:
        pass
    sys.exit(1)

_log_print(f"Servidor OK em {URL}")

# ── Abrir Chrome/Edge em modo App ─────────────────────────────────────────────
def _configurar_taskbar_icon():
    """Define AppUserModelID para o ícone correto aparecer na barra de tarefas."""
    try:
        import ctypes
        # Setar ID único do app — Windows usa isso para agrupar na taskbar
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "NFS-e.Validador.Nacional.v3"
        )
        # Setar ícone da janela do processo
        _ico = str(DATA / "nfse.ico")
        if os.path.exists(_ico):
            # Carregar ícone via ctypes
            _ICON_BIG   = 1
            _ICON_SMALL = 0
            _WM_SETICON = 0x0080
            _hicon = ctypes.windll.user32.LoadImageW(
                None, _ico, 1,  # IMAGE_ICON
                0, 0, 0x0050    # LR_LOADFROMFILE | LR_DEFAULTSIZE
            )
            if _hicon:
                _log_print(f"Ícone carregado: {_ico}")
    except Exception as e:
        _log_print(f"taskbar icon: {e}")

_configurar_taskbar_icon()

def _abrir_browser():
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    _profile = str(DATA / ".chrome-profile")
    flags = [
        f"--app={URL}",
        "--window-size=1400,860",
        "--window-position=60,40",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-background-networking",
        f"--user-data-dir={_profile}",
        "--app-id=nfse-validador-nacional",
    ]
    _NO_WIN = 0x08000000
    _DETACH = 0x00000008

    for exe in candidates:
        if os.path.exists(exe):
            _log_print(f"Abrindo: {exe}")
            try:
                proc = subprocess.Popen(
                    [exe] + flags,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=_NO_WIN | _DETACH
                )
                return proc
            except Exception as e:
                _log_print(f"Falha em {exe}: {e}")
                continue

    # Fallback
    _log_print("Chrome/Edge nao encontrado — abrindo browser padrao")
    webbrowser.open(URL)
    return None

_browser = _abrir_browser()
_log_print("Browser aberto. Aguardando fechar...")

# ── Manter vivo até o browser fechar ──────────────────────────────────────────
if _browser:
    _browser.wait()
    _log_print("Browser fechado.")
else:
    # Sem processo rastreavel: aguardar Ctrl+C ou sinal
    try:
        while _srv.is_alive():
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass

_log_print("Encerrando.")
sys.exit(0)
