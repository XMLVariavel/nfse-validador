"""
wizard.py — Instalador NFS-e Validador v3.1
Wizard visual 4 telas: Boas-vindas → Pasta → Instalando → Concluído
O Setup embarca o app já compilado (NFS-e Validador.exe) dentro de si.
"""
import tkinter as tk
from tkinter import filedialog, messagebox
import threading, shutil, os, sys, subprocess, time
from pathlib import Path

APP_NAME    = "NFS-e Validador"
APP_VER     = "3.1"
PUBLISHER   = "Equipe de Suporte ERP"
# Instalar em AppData\Local por padrão (não requer admin)
# O usuário pode mudar para Program Files se quiser
DEFAULT_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA",
    os.environ.get("APPDATA",
    os.path.join(os.environ.get("USERPROFILE", r"C:\Users\Public"), "AppData", "Local"))),
    APP_NAME
)
EXE_NAME    = "NFS-e Validador.exe"

BG="#0d1117"; BG2="#161b22"; BORDER="#30363d"; ACCENT="#4ade80"
TEXT="#e6edf3"; TEXT2="#8b949e"

def res(rel):
    base = Path(sys._MEIPASS) if getattr(sys,"frozen",False) else Path(__file__).parent
    return base / rel

class InstallerWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Instalacao — {APP_NAME} v{APP_VER}")
        self.resizable(False, False)
        self.configure(bg=BG)
        W,H=560,430
        self.geometry(f"{W}x{H}+{(self.winfo_screenwidth()-W)//2}+{(self.winfo_screenheight()-H)//2}")
        try:
            ico=res("nfse.ico")
            if ico.exists(): self.iconbitmap(str(ico))
        except: pass
        self._install_start  = time.time()
        self._install_pct    = 0
        self._timer_running  = False
        self.install_dir     = tk.StringVar(value=DEFAULT_DIR)
        self.create_desktop = tk.BooleanVar(value=True)
        self.create_menu    = tk.BooleanVar(value=True)
        self.open_after     = tk.BooleanVar(value=True)
        self.frame = tk.Frame(self, bg=BG)
        self.frame.pack(fill="both", expand=True)
        self.show_welcome()

    def clear(self):
        for w in self.frame.winfo_children(): w.destroy()

    def header(self, title, sub=""):
        hf=tk.Frame(self.frame,bg=BG2,height=88); hf.pack(fill="x"); hf.pack_propagate(False)
        tk.Frame(hf,bg=ACCENT,height=3).pack(fill="x",side="bottom")
        inn=tk.Frame(hf,bg=BG2); inn.pack(fill="both",expand=True,padx=24,pady=14)
        tk.Label(inn,text=title,bg=BG2,fg=TEXT,font=("Segoe UI",13,"bold")).pack(anchor="w")
        if sub: tk.Label(inn,text=sub,bg=BG2,fg=TEXT2,font=("Segoe UI",9)).pack(anchor="w",pady=(2,0))

    def footer(self, back=None, nxt=None, nxt_txt="Proximo →", back_txt="← Voltar"):
        ff=tk.Frame(self.frame,bg=BG2,height=54); ff.pack(fill="x",side="bottom"); ff.pack_propagate(False)
        tk.Frame(ff,bg=BORDER,height=1).pack(fill="x",side="top")
        bf=tk.Frame(ff,bg=BG2); bf.pack(side="right",padx=20,pady=10)
        if back:
            tk.Button(bf,text=back_txt,command=back,bg=BG,fg=TEXT2,relief="flat",cursor="hand2",
                      font=("Segoe UI",9),padx=14,pady=5,bd=1,highlightthickness=1,
                      highlightbackground=BORDER,activebackground=BORDER,activeforeground=TEXT
                      ).pack(side="left",padx=(0,8))
        if nxt:
            tk.Button(bf,text=nxt_txt,command=nxt,bg=ACCENT,fg=BG,relief="flat",cursor="hand2",
                      font=("Segoe UI",9,"bold"),padx=18,pady=5,
                      activebackground="#22c55e",activeforeground=BG).pack(side="left")

    def body_frame(self):
        f=tk.Frame(self.frame,bg=BG); f.pack(fill="both",expand=True,padx=28,pady=20); return f

    def lbl(self,parent,text,size=9,color=TEXT,bold=False,pady=0):
        tk.Label(parent,text=text,bg=BG,fg=color,wraplength=490,justify="left",
                 font=("Segoe UI",size,"bold" if bold else "normal")).pack(anchor="w",pady=pady)

    def sep(self,parent,pady=10):
        tk.Frame(parent,bg=BORDER,height=1).pack(fill="x",pady=pady)

    def chk(self,parent,var,text):
        tk.Checkbutton(parent,variable=var,text=text,bg=BG,fg=TEXT,selectcolor=BG2,
                       activebackground=BG,activeforeground=TEXT,font=("Segoe UI",9),
                       cursor="hand2",highlightthickness=0).pack(anchor="w",pady=2)

    # TELA 1
    def show_welcome(self):
        self.clear()
        self.header(f"Bem-vindo ao {APP_NAME} {APP_VER}","Assistente de instalacao")
        body=self.body_frame()
        card=tk.Frame(body,bg=BG2,highlightthickness=1,highlightbackground=BORDER)
        card.pack(fill="x",pady=(0,16))
        inn=tk.Frame(card,bg=BG2,padx=20,pady=16); inn.pack(fill="x")
        tk.Label(inn,text="✔",bg=BG2,fg=ACCENT,font=("Segoe UI",34,"bold")).pack(side="left",padx=(0,16))
        tf=tk.Frame(inn,bg=BG2); tf.pack(side="left")
        tk.Label(tf,text=APP_NAME,bg=BG2,fg=TEXT,font=("Segoe UI",13,"bold")).pack(anchor="w")
        tk.Label(tf,text=f"Versao {APP_VER}  •  Validador de XML NFS-e Nacional",bg=BG2,fg=TEXT2,font=("Segoe UI",8)).pack(anchor="w")
        tk.Label(tf,text=PUBLISHER,bg=BG2,fg=TEXT2,font=("Segoe UI",8)).pack(anchor="w")
        self.lbl(body,
            "Este assistente instalara o NFS-e Validador no seu computador.\n\n"
            "Apos a instalacao, o aplicativo abrira como uma janela dedicada no "
            "Chrome ou Edge — sem barra de endereco, como um app nativo.",size=9,color=TEXT2)
        self.sep(body)
        self.lbl(body,"⚠  Feche outros programas antes de continuar.",size=9,color="#fbbf24")
        self.footer(nxt=self.show_location)

    # TELA 2
    def show_location(self):
        self.clear()
        self.header("Pasta de instalacao","Escolha onde o NFS-e Validador sera instalado")
        body=self.body_frame()
        self.lbl(body,"Instalar em:",color=TEXT2,pady=(0,4))
        row=tk.Frame(body,bg=BG); row.pack(fill="x",pady=(0,4))
        tk.Entry(row,textvariable=self.install_dir,bg=BG2,fg=TEXT,insertbackground=TEXT,
                 font=("Segoe UI",9),relief="flat",highlightthickness=1,
                 highlightbackground=BORDER,highlightcolor=ACCENT
                 ).pack(side="left",fill="x",expand=True,ipady=6,padx=(0,8))
        def browse():
            d=filedialog.askdirectory(title="Escolher pasta")
            if d: self.install_dir.set(d.replace("/","\\")+"\\"+APP_NAME)
        tk.Button(row,text="Procurar…",command=browse,bg=BORDER,fg=TEXT,relief="flat",
                  cursor="hand2",font=("Segoe UI",9),padx=12,pady=5,
                  activebackground=BG2,activeforeground=TEXT).pack(side="left")
        self.lbl(body,"Espaco necessario: ~90 MB",color=TEXT2,pady=(2,0))
        self.sep(body)
        self.lbl(body,"Opcoes:",color=TEXT2,pady=(0,6))
        self.chk(body,self.create_desktop,"Criar atalho na Area de Trabalho")
        self.chk(body,self.create_menu,   "Criar atalho no Menu Iniciar")
        self.chk(body,self.open_after,    "Abrir o NFS-e Validador apos a instalacao")
        self.footer(back=self.show_welcome,nxt=self.show_installing,nxt_txt="Instalar →")

    # TELA 3
    def show_installing(self):
        self.clear()
        self.header("Instalando…","Aguarde enquanto os arquivos sao copiados")
        body=self.body_frame()

        self.lbl_status=tk.Label(body,text="Preparando…",bg=BG,fg=TEXT2,
                                  font=("Segoe UI",9),anchor="w")
        self.lbl_status.pack(fill="x",pady=(0,8))

        bar_track=tk.Frame(body,bg=BORDER,height=10)
        bar_track.pack(fill="x"); bar_track.pack_propagate(False)
        self.bar=tk.Frame(bar_track,bg=ACCENT,height=10)
        self.bar.place(x=0,y=0,relheight=1,relwidth=0)

        # Linha de info: detalhe + tempo
        info_row=tk.Frame(body,bg=BG); info_row.pack(fill="x",pady=(8,0))
        self.lbl_detail=tk.Label(info_row,text="",bg=BG,fg=TEXT2,
                                  font=("Consolas",8),anchor="w")
        self.lbl_detail.pack(side="left",fill="x",expand=True)
        self.lbl_pct=tk.Label(info_row,text="0%",bg=BG,fg=ACCENT,
                               font=("Segoe UI",9,"bold"),anchor="e")
        self.lbl_pct.pack(side="right")

        # Timer e ETA
        timer_row=tk.Frame(body,bg=BG); timer_row.pack(fill="x",pady=(6,0))
        self.lbl_timer=tk.Label(timer_row,text="⏱  0s",bg=BG,fg=TEXT2,
                                 font=("Segoe UI",9),anchor="w")
        self.lbl_timer.pack(side="left")
        self.lbl_eta=tk.Label(timer_row,text="",bg=BG,fg=TEXT2,
                               font=("Segoe UI",9),anchor="e")
        self.lbl_eta.pack(side="right")

        ff=tk.Frame(self.frame,bg=BG2,height=54)
        ff.pack(fill="x",side="bottom"); ff.pack_propagate(False)
        tk.Frame(ff,bg=BORDER,height=1).pack(fill="x",side="top")

        # Iniciar timer
        self._install_start = time.time()
        self._install_pct   = 0
        self._timer_running = True
        self._tick_timer()

        threading.Thread(target=self._do_install,daemon=True).start()

    def _tick_timer(self):
        """Atualiza o cronômetro a cada segundo."""
        if not self._timer_running: return
        elapsed = int(time.time() - self._install_start)
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        if h > 0:
            t = f"⏱  {h}h {m:02d}m {s:02d}s"
        elif m > 0:
            t = f"⏱  {m}m {s:02d}s"
        else:
            t = f"⏱  {s}s"
        try:
            self.lbl_timer.config(text=t)
            # Calcular ETA
            pct = self._install_pct
            if pct > 5 and elapsed > 3:
                total_est = elapsed * 100 / pct
                restante  = int(total_est - elapsed)
                if restante > 60:
                    eta = f"~{restante//60}m {restante%60:02d}s restantes"
                elif restante > 0:
                    eta = f"~{restante}s restantes"
                else:
                    eta = "finalizando…"
                self.lbl_eta.config(text=eta)
            self.after(1000, self._tick_timer)
        except Exception:
            pass

    def _prog(self,pct,status,detail=""):
        self._install_pct = pct
        self.lbl_status.config(text=status)
        self.lbl_pct.config(text=f"{pct}%")
        self.bar.place(relwidth=pct/100)
        if detail: self.lbl_detail.config(text=detail)
        self.update_idletasks()

    def _copiar_arvore(self, src_dir, dst_dir, pct_ini, pct_fim, label):
        """Copia pasta recursivamente arquivo a arquivo com progresso visual."""
        src_dir = Path(src_dir)
        dst_dir = Path(dst_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)

        # Listar arquivos sem rglob para evitar travamento inicial
        # Usa os.walk que é incremental
        arquivos = []
        for raiz, dirs, fnames in os.walk(src_dir):
            for fname in fnames:
                arquivos.append(Path(raiz) / fname)

        total = max(1, len(arquivos))
        copiados = 0
        for arq in arquivos:
            rel  = arq.relative_to(src_dir)
            dest = dst_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(arq, dest)
            copiados += 1
            pct = int(pct_ini + (pct_fim - pct_ini) * copiados / total)
            # Mostrar arquivo e contador
            self._prog(pct, label,
                       f"  {rel.name}  ({copiados}/{total})")

    def _do_install(self):
        dest = Path(self.install_dir.get())
        src  = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
        try:
            # 1. Criar pastas
            self._prog(3, "Criando estrutura de pastas…")
            for sub in ["logs","tabelas","schemas/v100","schemas/v101",
                        "schemas/tecno","static",".chrome-profile"]:
                (dest / sub).mkdir(parents=True, exist_ok=True)

            # 2. Copiar app (exe + _internal)
            # O spec embarca a pasta dist/app/ como subpasta "app" dentro do Setup
            app_src = src / "app"
            if app_src.exists():
                self._prog(6, "Copiando NFS-e Validador.exe…")
                # Arquivos soltos (exe, ico, etc.)
                for item in app_src.iterdir():
                    if item.is_file():
                        shutil.copy2(item, dest / item.name)
                        self._prog(8, "Copiando aplicativo…", f"  → {item.name}")

                # _internal (DLLs do Python) — mais pesado
                internal = app_src / "_internal"
                if internal.exists():
                    self._copiar_arvore(internal, dest / "_internal", 8, 70,
                                        "Copiando bibliotecas Python…")
                else:
                    for item in app_src.iterdir():
                        if item.is_dir():
                            self._copiar_arvore(item, dest / item.name, 8, 60,
                                                f"Copiando {item.name}…")
            else:
                # Fallback: arquivos estão na raiz do _MEIPASS
                self._prog(6, "Copiando NFS-e Validador.exe…")
                for fname in [EXE_NAME]:
                    s = src / fname
                    if s.exists():
                        shutil.copy2(s, dest / fname)
                        self._prog(8, "Copiando aplicativo…", f"  → {fname}")
                    else:
                        # Buscar em qualquer lugar dentro de src
                        found = list(src.rglob(EXE_NAME))
                        if found:
                            shutil.copy2(found[0], dest / EXE_NAME)
                            self._prog(8, "Copiando aplicativo…", f"  → {EXE_NAME}")
                internal = src / "_internal"
                if internal.exists():
                    self._copiar_arvore(internal, dest / "_internal", 8, 70,
                                        "Copiando bibliotecas Python…")

            # 3. Schemas XSD
            self._prog(70, "Copiando schemas XSD…")
            for i, pasta in enumerate(["v100", "v101", "tecno"]):
                sp = src / "schemas" / pasta
                dp = dest / "schemas" / pasta
                if sp.exists():
                    pini = 70 + i * 3
                    pfim = pini + 3
                    self._copiar_arvore(sp, dp, pini, pfim,
                                        f"Copiando schemas/{pasta}…")

            # 4. Tabelas
            self._prog(79, "Copiando tabelas de dados…")
            tsrc = src / "tabelas"
            if tsrc.exists():
                arqs = [f for f in tsrc.iterdir()
                        if f.suffix == ".json"
                        and "state" not in f.name
                        and "notif" not in f.name]
                for i, f in enumerate(arqs):
                    shutil.copy2(f, dest / "tabelas" / f.name)
                    pct = 79 + int(3 * (i+1) / max(1, len(arqs)))
                    self._prog(pct, "Copiando tabelas…", f"  → {f.name}")

            # 5. Interface web
            self._prog(82, "Copiando interface web…")
            ssrc = src / "static"
            if ssrc.exists():
                arqs = list(ssrc.iterdir())
                for i, f in enumerate(arqs):
                    shutil.copy2(f, dest / "static" / f.name)
                    pct = 82 + int(2 * (i+1) / max(1, len(arqs)))
                    self._prog(pct, "Copiando interface web…", f"  → {f.name}")

            # 6. Ícone
            ico = src / "nfse.ico"
            if ico.exists():
                shutil.copy2(ico, dest / "nfse.ico")

            # 7. Atalhos
            self._prog(86, "Criando atalhos…")
            exe_path = dest / EXE_NAME
            if self.create_desktop.get():
                self._atalho(exe_path,
                             Path(os.environ["USERPROFILE"]) / "Desktop",
                             dest / "nfse.ico")
                self._prog(89, "Atalho na Area de Trabalho criado…", "  → Desktop")

            if self.create_menu.get():
                md = (Path(os.environ.get("APPDATA","")) /
                      "Microsoft/Windows/Start Menu/Programs" / APP_NAME)
                md.mkdir(parents=True, exist_ok=True)
                self._atalho(exe_path, md, dest / "nfse.ico")
                self._prog(92, "Atalho no Menu Iniciar criado…", "  → Menu Iniciar")

            # 8. Registro Windows
            self._prog(96, "Registrando no Windows…")
            self._registrar(dest, exe_path)

            self._prog(100, "Instalacao concluida!", "  ✔ Tudo pronto.")
            time.sleep(0.6)
            self.after(300, self.show_done)

        except Exception as e:
            self.after(0, lambda: messagebox.showerror(
                "Erro na instalacao",
                f"Ocorreu um erro:\n\n{e}\n\n"
                f"Verifique permissoes em:\n{dest}"))

    def _atalho(self,exe,pasta,ico=None):
        lnk=str(pasta/f"{APP_NAME}.lnk")
        ps=(f'$ws=New-Object -ComObject WScript.Shell;'            f'$s=$ws.CreateShortcut("{lnk}");'            f'$s.TargetPath="{exe}";'            f'$s.WorkingDirectory="{exe.parent}";'            f'$s.Description="{APP_NAME} v{APP_VER}";')
        if ico and Path(ico).exists(): ps+=f'$s.IconLocation="{ico}";' 
        ps+='$s.Save()'
        subprocess.run(["powershell","-NoProfile","-NonInteractive","-Command",ps],
                       capture_output=True,creationflags=0x08000000)

    def _registrar(self,dest,exe):
        try:
            import winreg
            kp=r"Software\Microsoft\Windows\CurrentVersion\Uninstall\NFS-eValidador"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,kp) as k:
                winreg.SetValueEx(k,"DisplayName",    0,winreg.REG_SZ, APP_NAME)
                winreg.SetValueEx(k,"DisplayVersion", 0,winreg.REG_SZ, APP_VER)
                winreg.SetValueEx(k,"Publisher",      0,winreg.REG_SZ, PUBLISHER)
                winreg.SetValueEx(k,"InstallLocation",0,winreg.REG_SZ, str(dest))
                winreg.SetValueEx(k,"DisplayIcon",    0,winreg.REG_SZ, str(exe))
                winreg.SetValueEx(k,"UninstallString",0,winreg.REG_SZ, f'"{exe}" --uninstall')
                winreg.SetValueEx(k,"NoModify",       0,winreg.REG_DWORD,1)
                winreg.SetValueEx(k,"EstimatedSize",  0,winreg.REG_DWORD,92160)
        except: pass

    # TELA 4
    def show_done(self):
        self._timer_running = False
        self.clear()
        self.header("Instalacao concluida! ✔",f"{APP_NAME} v{APP_VER} instalado com sucesso")
        body=self.body_frame()
        card=tk.Frame(body,bg=BG2,highlightthickness=1,highlightbackground=ACCENT)
        card.pack(fill="x",pady=(0,16))
        inn=tk.Frame(card,bg=BG2,padx=20,pady=16); inn.pack(fill="x")
        tk.Label(inn,text="✔",bg=BG2,fg=ACCENT,font=("Segoe UI",28,"bold")).pack(side="left",padx=(0,14))
        tf=tk.Frame(inn,bg=BG2); tf.pack(side="left")
        tk.Label(tf,text="Instalacao bem-sucedida",bg=BG2,fg=TEXT,font=("Segoe UI",12,"bold")).pack(anchor="w")
        tk.Label(tf,text=f"Local: {self.install_dir.get()}",bg=BG2,fg=TEXT2,font=("Segoe UI",8)).pack(anchor="w")
        self.lbl(body,
            "O NFS-e Validador esta pronto para uso.\n"
            "Ao abrir, o sistema inicia automaticamente e abre uma janela "
            "dedicada no Chrome/Edge — sem barra de endereco.",color=TEXT2)
        self.sep(body)
        self.chk(body,self.open_after,f"Abrir o {APP_NAME} agora")
        def concluir():
            if self.open_after.get():
                exe=Path(self.install_dir.get())/EXE_NAME
                if exe.exists():
                    subprocess.Popen(
                    [str(exe)], cwd=str(exe.parent),
                    creationflags=0x00000008 | 0x08000000)  # DETACHED + NO_WINDOW
            self.destroy()
        self.footer(nxt=concluir,nxt_txt="Concluir ✔")

if __name__=="__main__":
    InstallerWizard().mainloop()
