"""
monitorar_docs.py — Monitor de Documentação Oficial NFS-e
=========================================================
Monitora o portal gov.br/nfse e automaticamente:
  1. Detecta novas Notas Técnicas publicadas
  2. Atualiza a aba Documentação no index.html (entre marcadores DOC_PANEL)
  3. Adiciona a NT nova ao _CHANGELOG_NTS do JavaScript
  4. Cria notificação que aparece no sino do sistema
  5. Cria sentinel para o server.py recarregar se necessário

Uso:
  python monitorar_docs.py            # verifica e atualiza se houver mudança
  python monitorar_docs.py --check    # só verifica, não altera nada
  python monitorar_docs.py --force    # força atualização mesmo sem mudança

Agendamento Windows (configurado automaticamente pelo instalar_agendador.bat):
  Toda segunda-feira às 08h00 e toda quinta-feira às 08h00
"""

import re, json, sys, os, logging
from pathlib import Path
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError

# ── Configuração ─────────────────────────────────────────────────────────────
# Quando rodado dentro do exe (_internal), DATA é a pasta pai (_internal/..)
# Quando rodado como script normal, BASE é a pasta do script
import sys as _sys, os as _os
_frozen = getattr(_sys, "frozen", False)
if _frozen:
    # Dentro do exe: __file__ = _internal/monitorar_docs.py
    # Dados ficam em AppData/Local/NFS-e Validador/
    _appdata = Path(_os.environ.get("LOCALAPPDATA") or
                    _os.environ.get("APPDATA") or
                    Path(__file__).parent.parent)
    BASE = Path(_appdata) / "NFS-e Validador"
else:
    BASE = Path(__file__).parent

STATE_FILE = BASE / "tabelas" / "docs_state.json"
NOTIF_FILE = BASE / "tabelas" / "notificacoes_lidas.json"
LOG_FILE   = BASE / "logs"    / "docs_monitor.log"
HTML_FILE  = BASE / "static"  / "index.html"
SENTINEL   = BASE / "tabelas" / "reload_docs.flag"
DYNAMIC_FILE = BASE / "tabelas" / "docs_dynamic.json"

PAGES = [
    {
        "id":   "rtc",
        "nome": "RTC — Reforma Tributária do Consumo",
        "url":  "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc",
    },
    {
        "id":   "atual",
        "nome": "Documentação Atual (Produção)",
        "url":  "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual",
    },
    {
        "id":   "restrita",
        "nome": "Produção Restrita (Piloto RTC)",
        "url":  "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita",
    },
]

HEADERS = {"User-Agent": "NFS-e-Doc-Monitor/1.0 (automacao interna)"}

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]
)
log = logging.getLogger("docs_monitor")


# ── Estado ────────────────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"paginas": {}, "nts_conhecidas": [], "ultima_verificacao": None}

def save_state(state: dict):
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Scraping ──────────────────────────────────────────────────────────────────
def fetch_page(url: str) -> str | None:
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except URLError as e:
        log.error(f"Erro ao acessar {url}: {e}")
        return None


def extrair_nts(html: str) -> list[dict]:
    """
    Extrai TODOS os grupos de documentos da página gov.br.
    Captura nome correto da célula de texto, não do nome do arquivo.
    Agrupa: NT principal + seus anexos.
    """
    grupos = []
    vistos = set()

    # Extrair todas as células de tabela com links de documentos
    # A página usa tabelas <table><tr><td> com links
    # Padrão: texto do parágrafo antes dos links = título do grupo
    linhas_celula = re.findall(
        r'<td[^>]*>(.*?)</td>',
        html, re.DOTALL | re.IGNORECASE
    )

    for celula in linhas_celula:
        # Extrair links de arquivos nesta célula
        links_cel = re.findall(
            r'href="([^"]+\.(pdf|xlsx|zip))"[^>]*>([^<]{2,150})',
            celula, re.IGNORECASE
        )
        links_pagina = re.findall(
            r'href="([^"]+nota-tecnica[^"]*)"[^>]*>([^<]{5,150})',
            celula, re.IGNORECASE
        )

        if not links_cel and not links_pagina:
            continue

        # Extrair título da célula (primeiro parágrafo com texto significativo)
        textos = re.findall(r'>([^<]{10,200})<', celula)
        titulo = ""
        for t in textos:
            t = re.sub(r'\s+', ' ', t).strip()
            if len(t) > 15 and not t.startswith("http") and not t.startswith("/"):
                titulo = t[:150]
                break

        if not titulo:
            continue

        # Determinar ID e status
        nt_m = re.search(r'n[oº°]?\s*(\d{3})', titulo, re.IGNORECASE)
        anexo_m = re.search(r'[Aa]nexo\s+([IVXivx]+|\w+)', titulo)

        if nt_m:
            num = nt_m.group(1).zfill(3)
            gid = f"NT-{num}"
        elif anexo_m:
            gid = f"ANEXO-{anexo_m.group(1).upper()}"
        else:
            gid = re.sub(r'[^a-zA-Z0-9]', '-', titulo[:30]).strip('-')

        if gid in vistos:
            continue
        vistos.add(gid)

        # Inferir status pelo conteúdo da célula
        cel_lower = celula.lower()
        if "em desenvolvimento" in cel_lower or "trabalho inicial" in cel_lower:
            status = "Em desenvolvimento"
        elif "produção restrita" in cel_lower or "piloto" in cel_lower:
            status = "Produção Restrita"
        elif "não estará disponível" in cel_lower or "não disponível" in cel_lower:
            status = "Não disponível em produção"
        elif nt_m:
            status = "Produção"
        else:
            status = "Documento"

        # Montar lista de arquivos do grupo
        docs = []
        for href, ext, label in links_cel:
            url = href if href.startswith("http") else "https://www.gov.br" + href
            label_limpo = re.sub(r'\s+', ' ', label).strip()[:100]
            # Se label não é informativo, usar nome do arquivo formatado
            nome_arq = url.split("/")[-1]
            if len(label_limpo) < 5:
                label_limpo = nome_arq
            docs.append({
                "nome": label_limpo,
                "url":  url,
                "tipo": ext.lower(),
            })
        for href, label in links_pagina:
            url = href if href.startswith("http") else "https://www.gov.br" + href
            label_limpo = re.sub(r'\s+', ' ', label).strip()[:100]
            docs.append({
                "nome": label_limpo or "Ver documento",
                "url":  url,
                "tipo": "web",
            })

        if not docs:
            continue

        grupo = {
            "id":      gid,
            "num":     nt_m.group(1).zfill(3) if nt_m else "",
            "titulo":  titulo,
            "status":  status,
            "docs":    docs,
            "novo":    False,
        }
        grupos.append(grupo)

    # Se nada foi encontrado pela tabela, fallback para extração simples de links
    if not grupos:
        log.warning("Nenhum grupo encontrado via tabela — usando extração simples de links")
        for href, ext in re.findall(r'href="([^"]+\.(pdf|xlsx|zip))"', html, re.IGNORECASE):
            url = href if href.startswith("http") else "https://www.gov.br" + href
            nome = url.split("/")[-1]
            if url not in vistos:
                vistos.add(url)
                grupos.append({
                    "id": nome, "num": "", "titulo": nome,
                    "status": "Documento", "docs": [{"nome": nome, "url": url, "tipo": ext.lower()}],
                    "novo": False,
                })

    return grupos


def comparar(antigo: list, novo: list) -> list:
    """Retorna grupos que estão em novo mas não em antigo (por id ou URLs dos docs)."""
    ids_antigos = {g.get("id","") for g in antigo}
    urls_antigas = set()
    for g in antigo:
        for d in g.get("docs", []):
            urls_antigas.add(d.get("url",""))
    novos = []
    for g in novo:
        docs_novos = [d for d in g.get("docs",[]) if d.get("url","") not in urls_antigas]
        if g.get("id","") not in ids_antigos or docs_novos:
            novos.append(g)
    return novos

def inferir_dados_nt(nt: dict) -> dict:
    """Infere título, descrição e status a partir dos dados disponíveis."""
    num  = int(nt["num"])
    ntid = nt["id"]
    url  = nt["url"]
    txt  = nt["texto"]

    # Título baseado no texto extraído ou genérico
    titulo = f"{ntid} — {txt}" if txt and txt.lower() not in ("pdf", "zip", ntid.lower()) else f"{ntid} — Nota Técnica NFS-e Nacional"
    if len(titulo) > 80:
        titulo = titulo[:77] + "..."

    # Status inferido pela URL
    if "restrita" in url:
        status  = "Produção Restrita"
        impacto = "medio"
    elif "producao" in url or "atual" in url:
        status  = "Produção"
        impacto = "medio"
    else:
        status  = "Produção"
        impacto = "medio"

    # Data atual como aproximação
    data = datetime.now().strftime("%Y-%m")

    # Versão
    versao = "v1.01" if num >= 5 else "v1.00"

    return {
        "id":      ntid,
        "titulo":  titulo,
        "data":    data,
        "versao":  versao,
        "status":  status,
        "descricao": f"Nota Técnica {ntid} publicada no portal gov.br/nfse. Verifique o documento oficial para detalhes.",
        "url":     url,
        "impacto": impacto,
    }


# ── Atualizar aba Documentação no index.html ──────────────────────────────────
def gerar_bloco_doc(state: dict) -> str:
    """Gera HTML para o bloco da aba Documentação."""
    ts  = state.get("ultima_verificacao", "—")
    out = [f'  <p class="doc-panel-title">Documentação Técnica Oficial — NFS-e Nacional</p>']
    out.append(
        f'  <p class="doc-panel-sub" id="docPanelSub">'
        f'Fonte: <a href="https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc" '
        f'target="_blank" style="color:var(--blue)">gov.br/nfse — Biblioteca / Documentação Técnica / RTC</a>'
        f' · <span id="docDataVerif">Última verificação: {ts}</span></p>'
    )

    for page in PAGES:
        pid  = page["id"]
        docs = state["paginas"].get(pid, {}).get("nts", [])
        if not docs:
            continue

        out.append(f'\n  <div class="doc-section">')
        out.append(f'    <div class="doc-section-title">{page["nome"]}</div>')

        for nt in sorted(docs, key=lambda x: x.get("num","000"), reverse=True):
            is_new  = nt.get("novo", False)
            new_bdg = '<span class="doc-nt-badge badge-prod" style="font-size:9px;padding:1px 6px;border-radius:8px;background:rgba(74,222,128,.15);color:var(--accent);font-weight:700;margin-left:6px">Novo</span>' if is_new else ""
            out.append(f'    <div class="doc-nt-card{" nt-new" if is_new else ""}">')
            out.append(f'      <div class="doc-nt-title">Nota Técnica {nt["id"]} {new_bdg}</div>')
            out.append(f'      <div class="doc-links">')
            ext = nt.get("ext", "web")
            cls = {"pdf":"pdf","xlsx":"xls","zip":"zip"}.get(ext, "web")
            label = nt.get("texto", nt["id"])
            out.append(
                f'        <a class="doc-link {cls}" href="{nt["url"]}" target="_blank" rel="noopener">'
                f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
                f'<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>'
                f'<polyline points="14 2 14 8 20 8"/></svg>'
                f'{label} ({ext.upper()})</a>'
            )
            # Botão Resumir com IA se for PDF
            if ext == "pdf":
                out.append(
                    f'        <button class="btn" onclick="ntResumir(\'{nt["id"]}\',\'{nt["url"]}\',this)" '
                    f'style="font-size:10px;padding:3px 10px;color:var(--purple);border-color:rgba(167,139,250,.3);background:rgba(167,139,250,.06)">'
                    f'<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
                    f'<circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg> Resumir com IA</button>'
                )
            out.append(f'      </div>')
            out.append(f'    </div>')

        out.append(f'  </div>')

    return "\n".join(out)


def patch_doc_panel(html_path: Path, novo_conteudo: str) -> bool:
    """Substitui conteúdo entre <!-- DOC_PANEL_START --> e <!-- DOC_PANEL_END -->."""
    if not html_path.exists():
        log.warning(f"index.html não encontrado: {html_path}")
        return False
    content = html_path.read_text(encoding="utf-8")
    s, e = "<!-- DOC_PANEL_START -->", "<!-- DOC_PANEL_END -->"
    if s not in content or e not in content:
        log.warning("Marcadores DOC_PANEL_START/END não encontrados no index.html.")
        return False
    novo = content[:content.index(s) + len(s)]
    novo += "\n" + novo_conteudo + "\n"
    novo += content[content.index(e):]
    html_path.write_text(novo, encoding="utf-8")
    log.info("✔ Aba Documentação atualizada no index.html")
    return True


# ── Atualizar _CHANGELOG_NTS no JavaScript ────────────────────────────────────
def patch_changelog(html_path: Path, nts_novas: list[dict]) -> bool:
    """Injeta NTs novas no array _CHANGELOG_NTS do JavaScript."""
    if not html_path.exists() or not nts_novas:
        return False

    content = html_path.read_text(encoding="utf-8")

    # Localizar o array _CHANGELOG_NTS
    m = re.search(r'(const _CHANGELOG_NTS = )(\[.*?\]);', content, re.DOTALL)
    if not m:
        log.warning("_CHANGELOG_NTS não encontrado no index.html.")
        return False

    try:
        changelog_atual = json.loads(m.group(2))
    except json.JSONDecodeError as ex:
        log.error(f"Erro ao parsear _CHANGELOG_NTS: {ex}")
        return False

    ids_atuais = {nt["id"] for nt in changelog_atual}
    adicionadas = 0

    for nt_nova in nts_novas:
        if nt_nova["id"] in ids_atuais:
            continue
        dados = inferir_dados_nt(nt_nova)
        # Inserir no início (NT mais recente primeiro)
        changelog_atual.insert(0, dados)
        ids_atuais.add(nt_nova["id"])
        adicionadas += 1
        log.info(f"✔ {nt_nova['id']} adicionada ao Changelog")

    if adicionadas == 0:
        return False

    # Serializar e substituir no HTML
    novo_json = json.dumps(changelog_atual, ensure_ascii=False)
    novo_content = content[:m.start()] + f"const _CHANGELOG_NTS = {novo_json};" + content[m.end():]
    html_path.write_text(novo_content, encoding="utf-8")
    log.info(f"✔ Changelog atualizado: {adicionadas} NT(s) adicionada(s)")
    return True


# ── Criar notificação no sistema ──────────────────────────────────────────────
def criar_notificacao(nts_novas: list):
    """Cria notificações para o sino — suporta formato grupo (docs[]) e antigo (url)."""
    try:
        notifs = []
        if NOTIF_FILE.exists():
            notifs = json.loads(NOTIF_FILE.read_text(encoding="utf-8"))
        if not isinstance(notifs, list):
            notifs = []
    except Exception:
        notifs = []

    ts = datetime.now().isoformat()
    for g in nts_novas:
        gid = g.get("id", "DOC")
        # Suportar formato novo (grupos com docs[]) e antigo (url direto)
        if "docs" in g:
            docs = g.get("docs", [])
            url  = docs[0].get("url", "") if docs else ""
            msg  = f"{len(docs)} arquivo(s) — disponível na aba Documentação"
        else:
            url  = g.get("url", g.get("texto",""))
            msg  = f"{g.get('texto','Documento')} — disponível na aba Documentação"

        notif = {
            "id":       f"nt-nova-{gid}-{ts[:10]}",
            "tipo":     "nt_nova",
            "titulo":   f"Novo: {g.get('titulo', gid)[:60]}",
            "mensagem": msg,
            "url":      url,
            "ts":       ts,
            "lida":     False,
        }
        if not any(n.get("id") == notif["id"] for n in notifs):
            notifs.append(notif)
            log.info(f"✔ Notificação criada: {notif['titulo']}")

    NOTIF_FILE.parent.mkdir(exist_ok=True)
    NOTIF_FILE.write_text(json.dumps(notifs, ensure_ascii=False, indent=2), encoding="utf-8")



def _gerar_docs_dynamic(state: dict, nts_novas: list) -> dict:
    """
    Gera o JSON dinâmico com todos os grupos de documentos para /api/docs.
    """
    todos_grupos = []
    ids_vistos = set()

    for page in PAGES:
        pid = page["id"]
        pdata = state.get("paginas", {}).get(pid, {})
        # Tentar "grupos" primeiro, depois "nts" para compatibilidade
        grupos = pdata.get("grupos") or pdata.get("nts") or []
        log.info(f"  [{pid}] {len(grupos)} grupo(s) no state")
        for g in grupos:
            gid = g.get("id","") or g.get("nome","") or str(id(g))
            if gid not in ids_vistos:
                ids_vistos.add(gid)
                g2 = dict(g)  # cópia para não alterar state
                g2["pagina_nome"] = page["nome"]
                todos_grupos.append(g2)

    # Ordenar: grupos com número de NT primeiro (desc), depois outros
    def _sort_key(g):
        num = g.get("num","")
        return (0 if num else 1, num)
    todos_grupos.sort(key=_sort_key, reverse=False)
    todos_grupos.sort(key=lambda g: g.get("num","999"), reverse=True)

    ids_novos = {g.get("id","") for g in nts_novas}

    return {
        "ultima_verificacao": state.get("ultima_verificacao","—"),
        "grupos": todos_grupos,
        "total": len(todos_grupos),
        "novas": list(ids_novos),
        "gerado_em": datetime.now().isoformat(),
    }

# ── Fluxo principal ───────────────────────────────────────────────────────────
def main():
    args   = sys.argv[1:]
    check  = "--check" in args
    forcar = "--force" in args

    log.info("=" * 55)
    log.info("Monitor NFS-e — Documentação gov.br")
    log.info(f"Início: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    log.info(f"BASE   : {BASE}")
    log.info(f"LOG    : {LOG_FILE}")
    log.info(f"STATE  : {STATE_FILE}")
    log.info("=" * 55)

    state         = load_state()
    nts_novas     = []
    houve_mudanca = False

    # ── Varrer todas as páginas ───────────────────────────────────────────────
    for page in PAGES:
        pid  = page["id"]
        log.info(f"\n→ Verificando: {page['nome']}")

        html = fetch_page(page["url"])
        if not html:
            log.warning("  Falha ao acessar página — pulando.")
            continue

        nts_encontradas = extrair_nts(html)
        log.info(f"  {len(nts_encontradas)} NT(s) encontrada(s) nesta página")

        # NTs já conhecidas nesta página
        conhecidas = {n["id"] for n in state["paginas"].get(pid, {}).get("nts", [])}
        # NTs globalmente conhecidas (todas as páginas)
        globais    = set(state.get("nts_conhecidas", []))

        novas_pagina = []
        grupos_antigos = state["paginas"].get(pid, {}).get("grupos", [])
        grupos_novos_detectados = comparar(grupos_antigos, nts_encontradas)

        for g in nts_encontradas:
            if any(gn["id"] == g["id"] for gn in grupos_novos_detectados) or forcar:
                g["novo"] = True
                novas_pagina.append(g)
                log.info(f"  + {g['id']} NOVO: {g['titulo'][:60]}")
            else:
                g["novo"] = False

        if novas_pagina:
            houve_mudanca = True
            nts_novas.extend(novas_pagina)

        # Salvar todos os grupos desta página
        state["paginas"][pid] = {
            "ultima_verificacao": datetime.now().isoformat(),
            "nts": nts_encontradas,  # compatibilidade
            "grupos": nts_encontradas,
        }

    # Atualizar lista global de NTs conhecidas
    if nts_novas:
        conhecidas_global = set(state.get("nts_conhecidas", []))
        for nt in nts_novas:
            conhecidas_global.add(nt["id"])
        state["nts_conhecidas"] = sorted(conhecidas_global)

    state["ultima_verificacao"] = datetime.now().strftime("%d/%m/%Y %H:%M")

    # ── Modo --check: só imprimir resultado ──────────────────────────────────
    if check:
        resultado = {
            "houve_mudanca": houve_mudanca,
            "nts_novas":     len(nts_novas),
            "ids":           [nt["id"] for nt in nts_novas],
        }
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        return

    # ── Salvar estado sempre ──────────────────────────────────────────────────
    save_state(state)

    if not houve_mudanca and not forcar:
        log.info("\n✔ Nenhuma NT nova detectada. Estado salvo.")
        log.info("Monitor encerrado.\n")
        return

    # ── Salvar dados dinâmicos em JSON (NÃO modifica index.html) ─────────────
    log.info(f"\n{'='*55}")
    log.info(f"  {len(nts_novas)} NT(s) nova(s) detectada(s)!")
    log.info(f"{'='*55}")

    # 1. Salvar dados da documentação em arquivo JSON separado
    log.info("\n[1/3] Salvando dados de documentação em docs_dynamic.json...")
    # Garantir que state já tem os grupos salvos antes de gerar o dynamic
    save_state(state)
    docs_dynamic = _gerar_docs_dynamic(state, nts_novas)
    DOCS_DYNAMIC = BASE / "tabelas" / "docs_dynamic.json"
    DOCS_DYNAMIC.parent.mkdir(exist_ok=True)
    DOCS_DYNAMIC.write_text(
        json.dumps(docs_dynamic, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(f"  ✔ docs_dynamic.json salvo ({len(docs_dynamic.get('nts',[]))} NTs)")

    # 2. Criar notificações
    log.info("\n[2/3] Criando notificações no sistema...")
    criar_notificacao(nts_novas)

    # 3. Sentinel para recarregar servidor
    log.info("\n[3/3] Sinalizando servidor...")
    SENTINEL.parent.mkdir(exist_ok=True)
    SENTINEL.write_text(datetime.now().isoformat(), encoding="utf-8")
    log.info("  ✔ Sentinel criado — servidor vai recarregar automaticamente")

    log.info(f"\n{'='*55}")
    log.info(f"CONCLUÍDO: {len(nts_novas)} NT(s) adicionada(s) ao sistema")
    for nt in nts_novas:
        log.info(f"  • {nt['id']}: {nt.get('texto','')[:60]}")
    log.info(f"{'='*55}")
    log.info("Monitor encerrado.\n")


# Permite ser chamado tanto como script quanto via importlib pelo servidor
def _executar_como_modulo():
    """Chamado pelo servidor via importlib — equivale a rodar como __main__."""
    main()

if __name__ == "__main__":
    main()
