"""
monitorar_docs.py — Monitor de Documentação Oficial NFS-e
=========================================================
Monitora as páginas do gov.br/nfse e:
  1. Detecta novas Notas Técnicas / documentos publicados
  2. Atualiza o arquivo tabelas/docs_state.json com os novos links
  3. Gera o trecho HTML para o menu Documentação do index.html (patch automático)
  4. Cria sentinel para o server.py recarregar

Uso:
  python monitorar_docs.py            # verifica e atualiza se houver mudança
  python monitorar_docs.py --check    # só verifica, imprime JSON com resultado
  python monitorar_docs.py --force    # força atualização mesmo sem mudança

Agendamento sugerido (Task Scheduler Windows):
  Frequência: toda segunda-feira às 08h00
  Comando: python monitorar_docs.py
  Diretório: pasta raiz do sistema-nfse

Dependências: apenas stdlib Python 3.8+
"""

import re, json, sys, os, logging
from pathlib import Path
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError

# ── Config ──────────────────────────────────────────────────────────────────
BASE         = Path(__file__).parent
STATE_FILE   = BASE / "tabelas" / "docs_state.json"
LOG_FILE     = BASE / "logs" / "docs_monitor.log"
HTML_FILE    = BASE / "static" / "index.html"
SENTINEL     = BASE / "tabelas" / "reload_docs.flag"

PAGES = [
    {
        "id":    "rtc",
        "nome":  "RTC — Reforma Tributária do Consumo",
        "url":   "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc",
    },
    {
        "id":    "atual",
        "nome":  "Documentação Atual (Produção)",
        "url":   "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual",
    },
    {
        "id":    "restrita",
        "nome":  "Produção Restrita (Piloto RTC)",
        "url":   "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita",
    },
]

HEADERS = {"User-Agent": "NFS-e-Doc-Monitor/1.0 (automacao interna)"}

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_FILE.parent.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]
)
log = logging.getLogger("docs_monitor")


# ── Estado ───────────────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"paginas": {}, "ultima_verificacao": None}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Scraping ─────────────────────────────────────────────────────────────────
def fetch_page(url: str) -> str | None:
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except URLError as e:
        log.error(f"Erro ao acessar {url}: {e}")
        return None


def extrair_links(html: str, base_url: str) -> list[dict]:
    """
    Extrai links de documentos (.pdf, .xlsx, .zip) e Notas Técnicas da página.
    Retorna lista de dicts: {texto, url, tipo, data}
    """
    links = []
    # PDFs, XLSXs, ZIPs de documentos oficiais
    padrao_arquivo = re.compile(
        r'href="([^"]*(?:nt-\d+|nota-tecnica|anexo[ivx\d\-]+|nfse-esquemas)[^"]*\.(pdf|xlsx|zip))"[^>]*>([^<]{1,200})',
        re.IGNORECASE
    )
    for m in padrao_arquivo.finditer(html):
        href, ext, texto = m.group(1), m.group(2), m.group(3).strip()
        url = href if href.startswith("http") else "https://www.gov.br" + href
        nome = url.split("/")[-1]
        # Extrair data do nome se houver (ex: 20260209)
        data_m = re.search(r"(\d{8})", nome)
        data = data_m.group(1) if data_m else ""
        if len(data) == 8:
            data = f"{data[:4]}-{data[4:6]}-{data[6:]}"
        # Extrair número da NT
        nt_m = re.search(r"nt-?(\d{3})", nome, re.IGNORECASE)
        nt_num = nt_m.group(1) if nt_m else ""

        links.append({
            "texto": texto[:120],
            "url":   url,
            "nome":  nome,
            "tipo":  ext.lower(),
            "data":  data,
            "nt":    nt_num,
        })

    # Também capturar links de páginas de NTs (texto rico)
    padrao_nt = re.compile(
        r'href="([^"]*nota-tecnica[^"]*)"[^>]*>([^<]{5,200})',
        re.IGNORECASE
    )
    for m in padrao_nt.finditer(html):
        href, texto = m.group(1), m.group(2).strip()
        if any(l["url"] == href for l in links):
            continue
        url = href if href.startswith("http") else "https://www.gov.br" + href
        links.append({
            "texto": texto[:120],
            "url":   url,
            "nome":  url.split("/")[-1],
            "tipo":  "web",
            "data":  "",
            "nt":    "",
        })

    # Deduplicar por URL
    seen = set()
    result = []
    for l in links:
        if l["url"] not in seen:
            seen.add(l["url"])
            result.append(l)
    return result


# ── Comparação de estados ─────────────────────────────────────────────────────
def comparar(antigo: list[dict], novo: list[dict]) -> list[dict]:
    """Retorna links que estão em novo mas não em antigo (por URL)."""
    urls_antigas = {l["url"] for l in antigo}
    return [l for l in novo if l["url"] not in urls_antigas]


# ── Geração do HTML do menu Documentação ────────────────────────────────────
def gerar_html_docs(state: dict) -> str:
    """Gera o bloco HTML completo do painel de documentação."""
    ts = state.get("ultima_verificacao", "—")
    linhas = [
        f'  <p class="doc-panel-title">Documentação Técnica Oficial — NFS-e Nacional</p>',
        f'  <p class="doc-panel-sub">Monitoramento automático · Última verificação: {ts} '
        f'· <a href="https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica" '
        f'target="_blank" style="color:var(--blue)">gov.br/nfse</a></p>',
    ]

    for page in PAGES:
        pid = page["id"]
        docs = state["paginas"].get(pid, {}).get("links", [])
        if not docs:
            continue

        linhas.append(f'\n  <div class="doc-section">')
        linhas.append(f'    <div class="doc-section-title">{page["nome"]}</div>')

        # Agrupar por NT
        grupos_nt: dict[str, list] = {}
        sem_nt = []
        for l in docs:
            nt = l.get("nt", "")
            if nt:
                grupos_nt.setdefault(nt, []).append(l)
            else:
                sem_nt.append(l)

        # NTs em ordem decrescente
        for nt_num in sorted(grupos_nt.keys(), reverse=True):
            arqs = grupos_nt[nt_num]
            is_new = any(l.get("novo") for l in arqs)
            new_badge = '<span class="doc-nt-badge badge-prod">Novo</span>' if is_new else ''
            linhas.append(f'    <div class="doc-nt-card nt-new">')
            linhas.append(f'      <div class="doc-nt-title">Nota Técnica nº {nt_num} {new_badge}</div>')
            linhas.append(f'      <div class="doc-links">')
            for l in arqs:
                tipo_class = {"pdf":"pdf","xlsx":"xls","zip":"zip"}.get(l["tipo"],"web")
                linhas.append(
                    f'        <a class="doc-link {tipo_class}" href="{l["url"]}" '
                    f'target="_blank" rel="noopener">'
                    f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
                    f'<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>'
                    f'<polyline points="14 2 14 8 20 8"/></svg>'
                    f'{l["texto"]} ({l["tipo"].upper()})'
                    f'</a>'
                )
            linhas.append(f'      </div>')
            linhas.append(f'    </div>')

        # Docs sem NT identificada
        if sem_nt:
            linhas.append(f'    <div class="doc-nt-card">')
            linhas.append(f'      <div class="doc-links">')
            for l in sem_nt:
                tipo_class = {"pdf":"pdf","xlsx":"xls","zip":"zip"}.get(l["tipo"],"web")
                linhas.append(
                    f'        <a class="doc-link {tipo_class}" href="{l["url"]}" '
                    f'target="_blank" rel="noopener">'
                    f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
                    f'<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>'
                    f'<polyline points="14 2 14 8 20 8"/></svg>'
                    f'{l["texto"]}'
                    f'</a>'
                )
            linhas.append(f'      </div>')
            linhas.append(f'    </div>')

        linhas.append(f'  </div>')

    return "\n".join(linhas)


def patch_html(html_path: Path, novo_conteudo: str) -> bool:
    """
    Substitui o conteúdo entre os marcadores no index.html.
    Marcadores: <!-- DOC_PANEL_START --> e <!-- DOC_PANEL_END -->
    """
    if not html_path.exists():
        log.warning(f"index.html não encontrado em {html_path}")
        return False

    content = html_path.read_text(encoding="utf-8")
    start_tag = "<!-- DOC_PANEL_START -->"
    end_tag   = "<!-- DOC_PANEL_END -->"

    if start_tag not in content or end_tag not in content:
        log.warning("Marcadores DOC_PANEL_START/END não encontrados no index.html. "
                    "Adicione-os manualmente para ativar o patch automático.")
        return False

    novo = content[:content.index(start_tag) + len(start_tag)]
    novo += "\n" + novo_conteudo + "\n"
    novo += content[content.index(end_tag):]
    html_path.write_text(novo, encoding="utf-8")
    log.info("index.html atualizado com novos documentos.")
    return True


# ── Fluxo principal ───────────────────────────────────────────────────────────
def main():
    args   = sys.argv[1:]
    check  = "--check"  in args
    forcar = "--force"  in args

    log.info("=" * 50)
    log.info("Monitor de Documentação NFS-e gov.br")
    log.info("=" * 50)

    state = load_state()
    houve_mudanca = False
    novos_total   = []

    for page in PAGES:
        pid  = page["id"]
        nome = page["nome"]
        url  = page["url"]
        log.info(f"\nVerificando: {nome}")
        log.info(f"  URL: {url}")

        html = fetch_page(url)
        if not html:
            log.warning(f"  Falha — pulando.")
            continue

        links_novos = extrair_links(html, url)
        links_antigos = state["paginas"].get(pid, {}).get("links", [])

        novos = comparar(links_antigos, links_novos) if not forcar else links_novos
        if novos:
            log.info(f"  {len(novos)} novo(s) documento(s) encontrado(s):")
            for l in novos:
                log.info(f"    + {l['texto']} → {l['nome']}")
                l["novo"] = True
            houve_mudanca = True
            novos_total.extend(novos)

            # Marcar novos e mesclar com lista existente
            urls_novas = {l["url"] for l in novos}
            merged = [l for l in links_antigos if l["url"] not in urls_novas]
            for l in links_novos:
                if l["url"] in urls_novas:
                    l["novo"] = True
                merged.append(l)

            state["paginas"][pid] = {
                "ultima_verificacao": datetime.now().isoformat(),
                "links": merged,
            }
        else:
            log.info(f"  Sem novidades.")
            if pid not in state["paginas"]:
                state["paginas"][pid] = {
                    "ultima_verificacao": datetime.now().isoformat(),
                    "links": links_novos,
                }

    state["ultima_verificacao"] = datetime.now().strftime("%d/%m/%Y %H:%M")

    if check:
        resultado = {
            "houve_mudanca": houve_mudanca,
            "novos": len(novos_total),
            "docs": [{"texto":l["texto"],"url":l["url"]} for l in novos_total],
        }
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        return

    if houve_mudanca or forcar:
        save_state(state)
        log.info("\nSalvando estado atualizado…")

        # Tentar patch automático no HTML
        novo_html = gerar_html_docs(state)
        patched = patch_html(HTML_FILE, novo_html)
        if not patched:
            # Salvar como arquivo separado para referência
            out = BASE / "tabelas" / "docs_menu.html"
            out.write_text(novo_html, encoding="utf-8")
            log.info(f"HTML do menu salvo em: {out}")

        # Criar sentinel
        SENTINEL.parent.mkdir(exist_ok=True)
        SENTINEL.write_text(datetime.now().isoformat(), encoding="utf-8")
        log.info("Sentinel criado para recarregar o servidor.")

        log.info(f"\n{'='*50}")
        log.info(f"✔ {len(novos_total)} novo(s) documento(s) adicionado(s) ao menu.")
    else:
        save_state(state)
        log.info("\nNenhuma mudança detectada. Estado salvo.")

    log.info("Monitor encerrado.\n")


if __name__ == "__main__":
    main()
