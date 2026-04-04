# nfse_setup.spec — Etapa 2: compila Setup.exe (wizard instalador)
# console=False + onefile=True

import os
from pathlib import Path

block_cipher = None
APP_DIR = str(Path('dist') / 'app')

if not os.path.exists(APP_DIR):
    raise FileNotFoundError(
        f"Pasta \'{APP_DIR}\' nao encontrada!\n"
        "Execute primeiro: pyinstaller nfse_app.spec"
    )

datas_setup = [
    (APP_DIR, 'app'),
    ('nfse.ico', '.'),
]

a = Analysis(
    ['wizard.py'],
    pathex=['.'],
    binaries=[],
    datas=datas_setup,
    hiddenimports=[
        'tkinter','tkinter.ttk','tkinter.filedialog','tkinter.messagebox',
        'winreg','threading','shutil','subprocess','pathlib','time',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['lxml','matplotlib','numpy','pandas'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NFS-e_Validador_Setup',
    debug=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,          # ← SEM janela CMD
    uac_admin=False,        # ← SEM pedido de admin
    uac_uiaccess=False,
    icon='nfse.ico',
    onefile=True,
)
