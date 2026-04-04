# nfse_app.spec — Etapa 1: compila NFS-e Validador.exe
# Verifica automaticamente quais tabelas existem antes de incluir

import os
from pathlib import Path

block_cipher = None

# Tabelas — inclui apenas as que existem na pasta
TABELAS_DIR = Path('tabelas')
tabelas_existentes = []
for nome in ['rejeicoes.json', 'leiaute_data.json', 'cidades_ibge.json',
             'paises_iso.json', 'todas.json', 'indop_ibs_cbs.json']:
    f = TABELAS_DIR / nome
    if f.exists():
        tabelas_existentes.append((str(f), 'tabelas'))
    else:
        print(f'[aviso] tabelas/{nome} nao encontrado — ignorado')

# Schemas — inclui apenas pastas que existem
SCHEMAS_DIR = Path('schemas')
schemas_existentes = []
for pasta in ['v100', 'v101', 'tecno']:
    p = SCHEMAS_DIR / pasta
    if p.exists():
        schemas_existentes.append((str(p), f'schemas/{pasta}'))
    else:
        print(f'[aviso] schemas/{pasta} nao encontrado — ignorado')

datas_app = [
    ('static/index.html', 'static'),
] + tabelas_existentes + schemas_existentes + [
    ('atualizar_schemas.py', '.'),
    ('monitorar_docs.py',    '.'),
    ('server.py',            '.'),
    ('nfse.ico',             '.'),
    ('versao.json',          '.'),
]

a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=datas_app,
    hiddenimports=[
        'lxml','lxml.etree','lxml._elementpath',
        'urllib.request','urllib.error','urllib.parse',
        'http.server','socketserver','threading',
        'json','base64','pathlib','collections','subprocess',
        'webbrowser','signal',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter','matplotlib','numpy','pandas','PIL','cv2'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='NFS-e Validador',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    uac_admin=False,
    uac_uiaccess=False,
    icon='nfse.ico',
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True,
    name='app',
)
