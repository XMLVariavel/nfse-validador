"""
verificar.py — Checa se o ambiente do Validador NFS-e está pronto.
Execute antes de subir o servidor:  python verificar.py
"""
import sys
from pathlib import Path

BASE = Path(__file__).parent
OK   = "\033[92m✔\033[0m"
ERR  = "\033[91m✘\033[0m"
WARN = "\033[93m⚠\033[0m"

erros = 0

def ok(msg):   print(f"  {OK}  {msg}")
def err(msg):  global erros; erros += 1; print(f"  {ERR}  {msg}")
def warn(msg): print(f"  {WARN}  {msg}")

print("\n── Python ──────────────────────────────────")
v = sys.version_info
if v >= (3, 8):
    ok(f"Python {v.major}.{v.minor}.{v.micro}")
else:
    err(f"Python {v.major}.{v.minor} — requer 3.8+")

print("\n── Dependências ────────────────────────────")
try:
    import lxml; ok(f"lxml {lxml.__version__}")
except ImportError:
    err("lxml não instalado — execute: pip install lxml")

print("\n── Schemas XSD ─────────────────────────────")
schemas = [
    ("schemas/v100/DPS_v1.00.xsd",            "DPS v1.00"),
    ("schemas/v100/NFSe_v1.00.xsd",           "NFSe v1.00"),
    ("schemas/v101/DPS_v1.01.xsd",            "DPS v1.01"),
    ("schemas/v101/NFSe_v1.01.xsd",           "NFSe v1.01"),
    ("schemas/v101/CNC_v1.00.xsd",            "CNC v1.00"),
    ("schemas/tecno/TecnoNFSeNacional_v1.xsd", "TecnoNFSeNacional"),
]
for path, label in schemas:
    p = BASE / path
    if p.exists():
        ok(f"{label} ({p.stat().st_size // 1024} KB)")
    else:
        err(f"{label} não encontrado → {path}")

print("\n── Schemas — compilação XSD ─────────────────")
try:
    from lxml import etree
    for path, label in schemas:
        p = BASE / path
        if p.exists():
            try:
                etree.XMLSchema(etree.parse(str(p)))
                ok(f"{label} compila sem erros")
            except Exception as e:
                err(f"{label} erro de compilação: {e}")
except ImportError:
    warn("lxml não disponível — pulando compilação")

print("\n── Tabelas JSON ────────────────────────────")
tabelas = [
    ("tabelas/rejeicoes.json",       "Rejeições (Anexo VI)"),
    ("tabelas/cidades_ibge.json",    "Municípios IBGE"),
    ("tabelas/paises_iso.json",      "Países ISO"),
    ("tabelas/todas.json",           "Tabela consolidada"),
]
for path, label in tabelas:
    p = BASE / path
    if p.exists():
        import json
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            ok(f"{label} — {len(data)} registros")
        except Exception as e:
            err(f"{label} JSON inválido: {e}")
    else:
        warn(f"{label} não encontrado → {path} (opcional)")

print("\n── Arquivos estáticos ──────────────────────")
static = [
    ("static/index.html",                              "Interface principal"),
    ("static/validador-nfse-standalone.html",          "Standalone offline"),
]
for path, label in static:
    p = BASE / path
    if p.exists():
        ok(f"{label}")
    else:
        warn(f"{label} não encontrado → {path}")

print("\n" + "─" * 44)
if erros == 0:
    print("\033[92m  Tudo certo! Rode: python server.py\033[0m\n")
else:
    print(f"\033[91m  {erros} problema(s) encontrado(s). Corrija antes de iniciar.\033[0m\n")
