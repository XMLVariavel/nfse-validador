"""
atualizar_schemas.py — Verificador e atualizador automático de Schemas XSD
=========================================================================
Monitora a página oficial do gov.br/nfse e atualiza os schemas XSD
automaticamente quando uma nova versão é publicada.

Uso:
  python atualizar_schemas.py            # verifica e atualiza se necessário
  python atualizar_schemas.py --check    # só verifica, sem atualizar
  python atualizar_schemas.py --force    # força atualização mesmo sem mudança

Agendamento (cron — rodar toda segunda-feira às 08h):
  0 8 * * 1 cd /caminho/sistema-nfse && python atualizar_schemas.py >> logs/xsd_update.log 2>&1

Dependências: apenas stdlib Python 3.8+ (urllib, zipfile, hashlib, re, json)
"""

import re, json, sys, shutil, hashlib, zipfile, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime

# ── Configuração ────────────────────────────────────────────────────────────
BASE          = Path(__file__).parent
ESTADO_FILE   = BASE / "tabelas" / "xsd_update_state.json"
LOG_FILE      = BASE / "logs" / "xsd_update.log"
SCHEMAS_DIR   = BASE / "schemas"
BACKUP_DIR    = BASE / "schemas" / "_backup"

URL_PAGINA    = "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual"
URL_BASE      = "https://www.gov.br"

# Mapeamento: pasta de destino por padrão de nome no ZIP
# Arquivos v1.00 → v100, v1.01 → v101, TecnoNFSeNacional → tecno
DESTINO_MAP = {
    "v1.00": SCHEMAS_DIR / "v100",
    "v1.01": SCHEMAS_DIR / "v101",
    "TecnoNFSeNacional": SCHEMAS_DIR / "tecno",
}

# ── Logging ─────────────────────────────────────────────────────────────────
LOG_FILE.parent.mkdir(exist_ok=True)

def log(msg, nivel="INFO"):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    txt = f"[{ts}] [{nivel}] {msg}"
    print(txt)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(txt + "\n")

def log_ok(msg):  log(msg, "OK")
def log_err(msg): log(msg, "ERRO")
def log_av(msg):  log(msg, "AVISO")

# ── Estado persistente ───────────────────────────────────────────────────────
def carregar_estado():
    if ESTADO_FILE.exists():
        try:
            return json.loads(ESTADO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def salvar_estado(estado):
    ESTADO_FILE.parent.mkdir(exist_ok=True)
    ESTADO_FILE.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")

# ── Hash de arquivo ──────────────────────────────────────────────────────────
def hash_arquivo(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def hash_dir(pasta: Path) -> dict:
    """Retorna dict {nome_arquivo: sha256} para todos os .xsd de uma pasta."""
    resultado = {}
    if not pasta.exists():
        return resultado
    for f in sorted(pasta.glob("*.xsd")):
        resultado[f.name] = hash_arquivo(f)
    return resultado

# ── Scraping da página gov.br ────────────────────────────────────────────────
def buscar_link_xsd() -> dict | None:
    """
    Faz GET na página de documentação atual e extrai o link do ZIP de esquemas XSD.
    Retorna dict com: url, nome, versao, data  — ou None se não encontrar.
    """
    log(f"Consultando {URL_PAGINA} …")
    try:
        req = urllib.request.Request(
            URL_PAGINA,
            headers={"User-Agent": "NFS-e-Schema-Monitor/1.0 (automacao interna)"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        log_err(f"Falha ao acessar gov.br: {e}")
        return None

    # Procura pelo link do ZIP de esquemas XSD
    # Padrão atual: nfse-esquemas_xsd-v1-01-20260209.zip
    padrao = r'href="([^"]*nfse-esquemas[_-]xsd[^"]*\.zip)"'
    m = re.search(padrao, html, re.IGNORECASE)
    if not m:
        log_err("Link do ZIP de schemas XSD não encontrado na página. O layout pode ter mudado.")
        return None

    href = m.group(1)
    url  = href if href.startswith("http") else URL_BASE + href
    nome = url.split("/")[-1]

    # Extrair versão e data do nome: nfse-esquemas_xsd-v1-01-20260209.zip
    ver_m  = re.search(r"v(\d+[-_]\d+)", nome, re.IGNORECASE)
    data_m = re.search(r"(\d{8})", nome)
    versao = ver_m.group(1).replace("-", ".") if ver_m else "desconhecida"
    data   = data_m.group(1) if data_m else "desconhecida"

    # Formatar data legível: 20260209 → 2026-02-09
    if len(data) == 8:
        data_fmt = f"{data[:4]}-{data[4:6]}-{data[6:]}"
    else:
        data_fmt = data

    resultado = {"url": url, "nome": nome, "versao": versao, "data": data_fmt, "data_raw": data}
    log(f"Encontrado: {nome}  (versão {versao}, data {data_fmt})")
    return resultado

# ── Verificação de atualização ───────────────────────────────────────────────
def precisa_atualizar(info_remoto: dict, estado: dict, forcar: bool) -> bool:
    if forcar:
        log_av("Atualização forçada via --force.")
        return True

    nome_atual = estado.get("ultimo_zip")
    if not nome_atual:
        log("Nenhum estado anterior. Primeira execução — baixando schemas.")
        return True

    if info_remoto["nome"] != nome_atual:
        log_ok(f"Nova versão detectada: {nome_atual} → {info_remoto['nome']}")
        return True

    log_ok(f"Schemas já estão atualizados ({nome_atual}). Nenhuma ação necessária.")
    return False

# ── Download ─────────────────────────────────────────────────────────────────
def baixar_zip(url: str, destino: Path) -> bool:
    log(f"Baixando {url} …")
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "NFS-e-Schema-Monitor/1.0 (automacao interna)"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            dados = resp.read()
        destino.write_bytes(dados)
        log_ok(f"ZIP baixado: {destino.name} ({len(dados)//1024} KB)")
        return True
    except Exception as e:
        log_err(f"Falha no download: {e}")
        return False

# ── Backup ───────────────────────────────────────────────────────────────────
def fazer_backup():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / ts
    dest.mkdir(parents=True, exist_ok=True)
    copiados = 0
    for pasta in [SCHEMAS_DIR / "v100", SCHEMAS_DIR / "v101", SCHEMAS_DIR / "tecno"]:
        if pasta.exists():
            pasta_bak = dest / pasta.name
            shutil.copytree(pasta, pasta_bak)
            copiados += sum(1 for _ in pasta.glob("*.xsd"))
    log_ok(f"Backup criado em {dest} ({copiados} arquivos .xsd)")
    return dest

# ── Extração e instalação ────────────────────────────────────────────────────
def instalar_schemas(zip_path: Path) -> dict:
    """
    Extrai o ZIP e distribui os XSDs pelas pastas corretas.
    Retorna dict com resumo: {pasta: [arquivos instalados]}
    """
    resultado = {}
    log(f"Extraindo {zip_path.name} …")

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            nomes = zf.namelist()
            log(f"Arquivos no ZIP: {len(nomes)}")

            for nome_zip in nomes:
                if not nome_zip.lower().endswith(".xsd"):
                    continue

                # Determinar pasta de destino
                nome_arquivo = Path(nome_zip).name
                pasta_dest   = _determinar_pasta(nome_arquivo)

                if pasta_dest is None:
                    log_av(f"  Sem destino mapeado para: {nome_arquivo} — ignorado")
                    continue

                pasta_dest.mkdir(parents=True, exist_ok=True)
                destino_final = pasta_dest / nome_arquivo

                # Extrair
                dados = zf.read(nome_zip)
                destino_final.write_bytes(dados)

                pasta_key = pasta_dest.name
                resultado.setdefault(pasta_key, []).append(nome_arquivo)
                log(f"  ✔ {nome_arquivo} → schemas/{pasta_key}/")

    except zipfile.BadZipFile as e:
        log_err(f"ZIP corrompido: {e}")
        return {}
    except Exception as e:
        log_err(f"Erro ao extrair: {e}")
        return {}

    total = sum(len(v) for v in resultado.values())
    log_ok(f"Instalação concluída: {total} arquivos em {len(resultado)} pasta(s)")
    return resultado

def _determinar_pasta(nome_arquivo: str) -> Path | None:
    """
    Decide em qual subpasta instalar com base no nome do arquivo.
    Lógica:
      - Contém "v1.00" ou "_v1_00" ou similar → v100
      - Contém "v1.01" ou "_v1_01" ou similar → v101
      - Contém "TecnoNFSe" → tecno
      - Sem versão explícita mas é XSD → tenta inferir pelo conteúdo do nome
    """
    n = nome_arquivo.lower()

    if "tecno" in n:
        return SCHEMAS_DIR / "tecno"

    # Versão no nome: v1.00, v1_00, v1-00
    if re.search(r"v1[._-]0[01]", n):
        if re.search(r"v1[._-]01", n):
            return SCHEMAS_DIR / "v101"
        if re.search(r"v1[._-]00", n):
            return SCHEMAS_DIR / "v100"

    # Sem versão explícita no nome → verificar se já existe em alguma pasta
    for sub in ["v101", "v100"]:
        if (SCHEMAS_DIR / sub / nome_arquivo).exists():
            return SCHEMAS_DIR / sub

    # Fallback: colocar na v101 (versão mais recente)
    log_av(f"  Versão não identificada em '{nome_arquivo}' — instalando em v101 (fallback)")
    return SCHEMAS_DIR / "v101"

# ── Recarregar schemas no servidor (se rodando) ──────────────────────────────
def sinalizar_servidor():
    """
    Cria um arquivo sentinel que o server.py pode verificar para recarregar schemas.
    O server.py pode checar periodicamente se esse arquivo existe e recompilar.
    """
    sentinel = BASE / "tabelas" / "reload_schemas.flag"
    sentinel.write_text(datetime.now().isoformat(), encoding="utf-8")
    log("Arquivo sentinel criado: tabelas/reload_schemas.flag")
    log("O servidor irá recarregar os schemas na próxima requisição (se suporte a recarga estiver ativo).")

# ── Relatório ────────────────────────────────────────────────────────────────
def gerar_relatorio(info: dict, instalados: dict, backup_path: Path) -> str:
    linhas = [
        "=" * 60,
        f"RELATÓRIO DE ATUALIZAÇÃO DE SCHEMAS XSD",
        f"Data/hora : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        f"Versão    : {info['versao']}",
        f"Data XSD  : {info['data']}",
        f"Arquivo   : {info['nome']}",
        f"Backup    : {backup_path}",
        "=" * 60,
    ]
    for pasta, arquivos in sorted(instalados.items()):
        linhas.append(f"\nPasta schemas/{pasta}/  ({len(arquivos)} arquivo(s)):")
        for arq in sorted(arquivos):
            linhas.append(f"  ✔ {arq}")
    linhas.append("\n" + "=" * 60)
    return "\n".join(linhas)

# ── Fluxo principal ──────────────────────────────────────────────────────────
def main():
    args   = sys.argv[1:]
    check  = "--check" in args
    forcar = "--force" in args

    log("=" * 50)
    log("Iniciando verificação de schemas XSD NFS-e")
    log("=" * 50)

    # 1. Buscar link atual na página
    info = buscar_link_xsd()
    if not info:
        log_err("Não foi possível verificar a página. Abortando.")
        sys.exit(1)

    # 2. Carregar estado anterior
    estado = carregar_estado()

    # 3. Verificar se precisa atualizar
    if not precisa_atualizar(info, estado, forcar):
        if check:
            print(json.dumps({"atualizado": False, "versao": info["versao"], "nome": info["nome"]}, ensure_ascii=False, indent=2))
        sys.exit(0)

    if check:
        log_ok("Nova versão disponível. Use sem --check para atualizar.")
        print(json.dumps({"atualizado": True, "versao_nova": info["versao"], "nome": info["nome"],
                          "versao_atual": estado.get("versao","nenhuma")}, ensure_ascii=False, indent=2))
        sys.exit(0)

    # 4. Baixar ZIP
    zip_tmp = BASE / f"_download_{info['data_raw']}.zip"
    if not baixar_zip(info["url"], zip_tmp):
        log_err("Download falhou. Abortando atualização.")
        sys.exit(1)

    # 5. Backup dos schemas atuais
    backup_path = fazer_backup()

    # 6. Instalar novos schemas
    instalados = instalar_schemas(zip_tmp)

    if not instalados:
        log_err("Nenhum schema instalado — possível erro no ZIP. Restaurando backup…")
        for sub in ["v100", "v101", "tecno"]:
            bak = backup_path / sub
            dst = SCHEMAS_DIR / sub
            if bak.exists():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(bak, dst)
        log_av("Backup restaurado.")
        zip_tmp.unlink(missing_ok=True)
        sys.exit(1)

    # 7. Limpar ZIP temporário
    zip_tmp.unlink(missing_ok=True)

    # 8. Salvar novo estado
    estado.update({
        "ultimo_zip": info["nome"],
        "versao": info["versao"],
        "data_xsd": info["data"],
        "atualizado_em": datetime.now().isoformat(),
        "backup": str(backup_path),
        "schemas_instalados": instalados,
    })
    salvar_estado(estado)

    # 9. Sinalizar servidor para recarregar
    sinalizar_servidor()

    # 10. Relatório final
    relatorio = gerar_relatorio(info, instalados, backup_path)
    log(relatorio)

    print("\n✔ Schemas XSD atualizados com sucesso!")
    print(f"  Versão: {info['versao']}  |  Data: {info['data']}")
    total = sum(len(v) for v in instalados.items())

if __name__ == "__main__":
    main()
