"""
Validador NFS-e Nacional — v3.0
Suporte: DPS Nacional, NFSe Nacional, CNC, TecnoNFSeNacional (TX2/XML)
Novidades v3.0: XXE Protection · Rate Limiting · Cache de Schemas (pré-compilados no startup)
"""
import json, re, time, threading, warnings, os, pathlib
_START_TIME = time.time()
_VALIDACOES_TOTAL = 0

# Gemini API key — lida de .env ou variável de ambiente
def _load_env():
    env = pathlib.Path(__file__).parent / '.env'
    if not env.exists(): env = pathlib.Path('.env')
    if env.exists():
        for ln in env.read_text(encoding='utf-8').splitlines():
            ln = ln.strip()
            if ln and not ln.startswith('#') and '=' in ln:
                k, v = ln.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())
try: _load_env()
except: pass
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '')

# Cache de análises de NT (url → {ts, resumo})
_NT_CACHE     = {}
_NT_CACHE_TTL = 24 * 3600
_NT_JOBS      = {}  # job_key → {"status":"running"|"done"|"error", "result":...}
warnings.filterwarnings("ignore", category=FutureWarning)
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
from urllib.parse import urlparse
from collections import defaultdict
from lxml import etree

BASE   = Path(__file__).parent
NS_NAC = "http://www.sped.fazenda.gov.br/nfse"
MAX_BODY_BYTES = 5 * 1024 * 1024
RATE_LIMIT     = 60
RATE_WINDOW    = 60

# ── Rate Limiting ──────────────────────────────────────────────────────────
_rl_lock    = threading.Lock()
_rl_buckets = defaultdict(list)

def _rate_ok(ip):
    now = time.time()
    with _rl_lock:
        _rl_buckets[ip] = [t for t in _rl_buckets[ip] if now - t < RATE_WINDOW]
        if len(_rl_buckets[ip]) >= RATE_LIMIT:
            return False
        _rl_buckets[ip].append(now)
        return True

# ── Proteção XXE ───────────────────────────────────────────────────────────
def _safe_parser():
    return etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
    )

def _safe_parse(body):
    return etree.fromstring(body, _safe_parser())

# ── Tabelas ────────────────────────────────────────────────────────────────
def _load(name):
    p = BASE / "tabelas" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

TAB_REJ    = _load("rejeicoes.json")
TAB_SERV   = _load("codigos_servico.json")
TAB_CIDADES= _load("cidades_ibge.json")
TAB_PAISES = _load("paises_iso.json")
TAB_INDOP  = _load("indop_ibs_cbs.json")
TAB_TODAS  = _load("todas.json")

# Dados completos para os menus do frontend (arrays com todos os campos)
def _load_list(name):
    p = BASE / "tabelas" / name
    if not p.exists():
        # Tentar na pasta static
        p2 = BASE / "static" / name
        if p2.exists(): p = p2
        else: return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

TAB_LEIAUTE_FULL   = _load_list("leiaute_data.json")
TAB_REJEICOES_FULL = _load_list("rejeicoes_data.json")

# ── Cache de Schemas — pré-compilados no startup ───────────────────────────
_SCH        = {}
_SCH_STATUS = {}
_SENTINEL   = BASE / "tabelas" / "reload_schemas.flag"
_SENTINEL_TS: str = ""   # timestamp do sentinel na última verificação

def _compile_schema(key, path):
    p = BASE / path
    if not p.exists():
        _SCH_STATUS[key] = f"arquivo não encontrado: {path}"
        return False
    try:
        doc = etree.parse(str(p), _safe_parser())
        _SCH[key] = etree.XMLSchema(doc)
        _SCH_STATUS[key] = "ok"
        return True
    except Exception as ex:
        _SCH_STATUS[key] = f"erro: {ex}"
        return False

def _preload_schemas():
    specs = [
        ("DPS_1.00",  "schemas/v100/DPS_v1.00.xsd"),
        ("NFSe_1.00", "schemas/v100/NFSe_v1.00.xsd"),
        ("DPS_1.01",  "schemas/v101/DPS_v1.01.xsd"),
        ("NFSe_1.01", "schemas/v101/NFSe_v1.01.xsd"),
        ("CNC_1.00",  "schemas/v101/CNC_v1.00.xsd"),
        ("tecno",     "schemas/tecno/TecnoNFSeNacional_v1.xsd"),
    ]
    ok = 0
    for key, path in specs:
        if _compile_schema(key, path):
            ok += 1; print(f"  \u2714 Schema {key}")
        else:
            print(f"  \u2718 Schema {key}: {_SCH_STATUS[key]}")
    return ok

# ── Lock para recarga thread-safe ────────────────────────────────────────
_RELOAD_LOCK   = threading.Lock()
_RELOAD_STATUS = {"ultima": None, "em_andamento": False, "historico": []}

def _executar_recarga(motivo: str = "sentinel"):
    """Recarrega todos os schemas XSD. Thread-safe via _RELOAD_LOCK."""
    global _SENTINEL_TS
    with _RELOAD_LOCK:
        if _RELOAD_STATUS["em_andamento"]:
            return  # já está recarregando
        _RELOAD_STATUS["em_andamento"] = True
    try:
        ts_inicio = time.time()
        print(f"\n[hot-reload] {motivo} — recarregando schemas XSD...")
        _SCH.clear()
        _SCH_STATUS.clear()
        n = _preload_schemas()
        duracao = round(time.time() - ts_inicio, 2)
        msg = f"{n}/6 schemas recarregados em {duracao}s ({motivo})"
        print(f"[hot-reload] {msg}")
        _RELOAD_STATUS["ultima"] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "schemas": n,
            "duracao_s": duracao,
            "motivo": motivo,
        }
        _RELOAD_STATUS["historico"].append(_RELOAD_STATUS["ultima"])
        if len(_RELOAD_STATUS["historico"]) > 20:
            _RELOAD_STATUS["historico"] = _RELOAD_STATUS["historico"][-20:]
    finally:
        _RELOAD_STATUS["em_andamento"] = False

def _verificar_sentinel():
    """
    Verifica sentinel de recarga (chamado a cada POST /api/validar como fallback).
    A thread watchdog já monitora continuamente — este é backup redundante.
    """
    global _SENTINEL_TS
    if not _SENTINEL.exists():
        return
    ts = _SENTINEL.read_text(encoding="utf-8").strip()
    if ts == _SENTINEL_TS:
        return
    _SENTINEL_TS = ts
    try:
        _SENTINEL.unlink()
    except Exception:
        pass
    threading.Thread(
        target=_executar_recarga,
        args=("sentinel detectado em requisição",),
        daemon=True
    ).start()

# ── Watchdog: monitora XSDs e sentinel em background ─────────────────────
def _iniciar_watchdog(intervalo: int = 10):
    """
    Thread de fundo que monitora:
    1. Arquivo sentinel (tabelas/reload_schemas.flag)
    2. Timestamps dos arquivos XSD — recarga automática se algum mudar
    Polling a cada `intervalo` segundos (padrão: 10s).
    """
    global _SENTINEL_TS

    SCHEMAS_WATCH = [
        BASE / "schemas/v100/DPS_v1.00.xsd",
        BASE / "schemas/v100/NFSe_v1.00.xsd",
        BASE / "schemas/v101/DPS_v1.01.xsd",
        BASE / "schemas/v101/NFSe_v1.01.xsd",
        BASE / "schemas/v101/CNC_v1.00.xsd",
        BASE / "schemas/tecno/TecnoNFSeNacional_v1.xsd",
    ]

    # Snapshot inicial dos timestamps
    _xsd_ts: dict = {}
    for p in SCHEMAS_WATCH:
        try:
            _xsd_ts[str(p)] = p.stat().st_mtime
        except Exception:
            _xsd_ts[str(p)] = 0.0

    def _watch():
        nonlocal _xsd_ts
        while True:
            time.sleep(intervalo)
            try:
                # 1. Verificar sentinel
                if _SENTINEL.exists():
                    ts = _SENTINEL.read_text(encoding="utf-8").strip()
                    if ts and ts != _SENTINEL_TS:
                        _SENTINEL_TS = ts
                        try: _SENTINEL.unlink()
                        except Exception: pass
                        threading.Thread(
                            target=_executar_recarga,
                            args=("sentinel (watchdog)",),
                            daemon=True
                        ).start()
                        continue  # já recarregou, pular verificação XSD

                # 2. Verificar timestamps dos XSDs
                alterados = []
                novo_ts   = {}
                for p in SCHEMAS_WATCH:
                    key = str(p)
                    try:
                        mtime = p.stat().st_mtime
                    except Exception:
                        mtime = 0.0
                    novo_ts[key] = mtime
                    if mtime != _xsd_ts.get(key, 0.0) and mtime > 0:
                        alterados.append(p.name)

                if alterados:
                    _xsd_ts = novo_ts
                    motivo  = f"XSD alterado: {', '.join(alterados)}"
                    threading.Thread(
                        target=_executar_recarga,
                        args=(motivo,),
                        daemon=True
                    ).start()
                else:
                    _xsd_ts = novo_ts

            except Exception as ex:
                print(f"[watchdog] erro: {ex}")

    t = threading.Thread(target=_watch, daemon=True, name="schema-watchdog")
    t.start()
    print(f"[watchdog] monitorando {len(SCHEMAS_WATCH)} schemas a cada {intervalo}s")
    return t

def schema_nac(doc_tipo, ver):
    key = f"{doc_tipo}_{ver}"
    if key in _SCH: return _SCH[key]
    d  = "v101" if ver == "1.01" else "v100"
    fn = f"DPS_v{ver}.xsd" if doc_tipo=="DPS" else f"NFSe_v{ver}.xsd" if doc_tipo=="NFSe" else "CNC_v1.00.xsd"
    _compile_schema(key, f"schemas/{d}/{fn}")
    if key not in _SCH: raise RuntimeError(f"Schema {key} indisponível: {_SCH_STATUS.get(key)}")
    return _SCH[key]

def schema_tecno():
    if "tecno" in _SCH: return _SCH["tecno"]
    _compile_schema("tecno","schemas/tecno/TecnoNFSeNacional_v1.xsd")
    if "tecno" not in _SCH: raise RuntimeError(f"Schema tecno indisponível: {_SCH_STATUS.get('tecno')}")
    return _SCH["tecno"]

# ── Helpers ────────────────────────────────────────────────────────────────
def _get(root, tag, ns=None):
    nsm = {"ns": ns or NS_NAC}
    n = root.xpath(f"//ns:{tag}", namespaces=nsm) if ns != "" else root.xpath(f"//{tag}")
    if n: return (n[0].text or "").strip()
    return None

def _get_nt(root, tag):
    n = root.xpath(f"//{tag}")
    return (n[0].text or "").strip() if n else None

def _val_cnpj(v):
    c = re.sub(r"\D","",v or "")
    if len(c)!=14 or len(set(c))==1: return False
    def dv(s,p): r=sum(int(a)*b for a,b in zip(s,p))%11; return 0 if r<2 else 11-r
    return dv(c[:12],[5,4,3,2,9,8,7,6,5,4,3,2])==int(c[12]) and \
           dv(c[:13],[6,5,4,3,2,9,8,7,6,5,4,3,2])==int(c[13])

def _val_cpf(v):
    c = re.sub(r"\D","",v or "")
    if len(c)!=11 or len(set(c))==1: return False
    def dv(s,n):
        r=(sum(int(a)*(n-i) for i,a in enumerate(s))*10)%11
        return 0 if r>=10 else r
    return dv(c[:9],10)==int(c[9]) and dv(c[:10],11)==int(c[10])

def _val_cnpj_cpf(v):
    v2 = re.sub(r"\D","",v or "")
    return _val_cnpj(v2) if len(v2)==14 else _val_cpf(v2)

_NT_PDF = "https://www.nfse.gov.br/wp-content/uploads/2023/01/NT007_Anexo_VI_Tabela_de_Rejeicoes.pdf"

def _oc(cod, campo, msg, fix="", tipo="erro", linha=None):
    base = TAB_REJ.get(cod, {})
    titulo = base.get("msg", cod) if isinstance(base,dict) else str(base)
    doc_url = _NT_PDF if re.match(r"^E\d{4}$", cod) else None
    return {"codigo":cod,"tipo":tipo,"campo":campo,"titulo":titulo[:100],
            "mensagem":msg,"correcao":fix,"linha":linha,"doc_url":doc_url}

def _err(cod,campo,msg,fix=""): return _oc(cod,campo,msg,fix,"erro")
def _av(cod,campo,msg,fix=""):  return _oc(cod,campo,msg,fix,"alerta")
def _inf(campo,msg):            return _oc("INFO",campo,msg,"","info")

# ── Detecção ───────────────────────────────────────────────────────────────
def detectar(root):
    tag = etree.QName(root.tag).localname
    ns  = root.nsmap.get(None,"")
    ver = root.get("versao","1.01") if root.get("versao") in ("1.00","1.01") else "1.01"

    # ── TX2: tag raiz é <rps> (formato Tecnospeed/RPS municipal) ──────────
    if tag.lower() == "rps":
        # Tentar encontrar o nó de DPS dentro do RPS
        dps_node = None
        for _c in ["IncluirDPS","INCLUIRDPS","SalvarDPS","SALVARDPS","Dps","dps"]:
            _n = root.find(_c)
            if _n is not None: dps_node = _n; break
        # Verificar se é explicitamente TecnoNFSe pelo Cabecalho/padrao
        cab = root.find("Cabecalho") or root.find("cabecalho")
        padrao = cab.findtext("padrao","").strip() if cab is not None else ""
        tipo = "TX2/TecnoNFSeNacional" if "TecnoNFSe" in padrao or not padrao else "TX2/TecnoNFSeNacional"
        return {"formato":"tecnospeed","tipo":tipo,"ver":"1.01","dps_node":dps_node if dps_node is not None else root}

    # ── TX2: tag raiz é <TecnoNFSeNacional> ───────────────────────────────
    if tag == "TecnoNFSeNacional":
        _dps = root.find("Dps")
        return {"formato":"tecnospeed","tipo":"TecnoNFSeNacional","ver":"1.01","dps_node":_dps if _dps is not None else root}

    # ── Nacional: tem namespace NFS-e ─────────────────────────────────────
    if NS_NAC in ns:
        return {"formato":"nacional","tipo":tag if tag in ("DPS","NFSe","CNC") else "desconhecido","ver":ver,"dps_node":None}

    # ── TX2: heurística por campos típicos Tecnospeed (sem namespace) ──────
    if root.find(".//CpfCnpjPrestador") is not None or root.find(".//Dps") is not None:
        _dn2 = root.find("Dps") or root.find("IncluirDPS")
        return {"formato":"tecnospeed","tipo":"TecnoNFSeNacional","ver":"1.01","dps_node":_dn2 if _dn2 is not None else root}

    return {"formato":"desconhecido","tipo":"desconhecido","ver":ver,"dps_node":None}

# ── Validações Nacional ────────────────────────────────────────────────────
def validar_nacional(root, tipo, ver, det_tipo=None):
    oc=[]; nsm={"ns":NS_NAC}
    def add(cod,campo,msg,fix=""): oc.append(_err(cod,campo,msg,fix))
    def av(cod,campo,msg,fix=""):  oc.append(_av(cod,campo,msg,fix))
    def inf(campo,msg):            oc.append(_inf(campo,msg))
    def get(tag):                  return _get(root,tag)

    tpAmb=get("tpAmb")
    if tpAmb and tpAmb not in ("1","2"): add("E0006","tpAmb",f'tpAmb="{tpAmb}" inválido. Use 1=Produção, 2=Homologação.','Corrija para "1" ou "2".')
    elif tpAmb=="1": av("E0006","tpAmb","⚠ Ambiente de PRODUÇÃO. Certifique-se que o documento está correto.","Revise todos os dados.")

    dhEmi=get("dhEmi")
    if dhEmi and not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",dhEmi): add("E0008","dhEmi",f'Data/hora "{dhEmi}" inválida.','Use ISO 8601: 2025-03-10T09:00:00-03:00')

    dCompet=get("dCompet")
    if dCompet:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$",dCompet): add("E0015","dCompet",f'Competência "{dCompet}" deve ser AAAA-MM-DD.','Ex: 2025-03-01')
        else:
            ano,mes=int(dCompet[:4]),int(dCompet[5:7])
            if mes<1 or mes>12: add("E0015","dCompet",f'Mês {mes} inválido.','Use 01–12.')
            if ano<2023: av("E0016","dCompet",f'Competência {dCompet} anterior a 03/2023.','Verifique a data.')

    serie=get("serie")
    if serie and not re.match(r"^\d{1,5}$",serie): av("E0010","serie",f'Série "{serie}" não numérica.','Use série numérica (ex: 1).')

    nDPS=get("nDPS")
    if nDPS:
        try:
            if int(nDPS)<=0: add("E1235","nDPS",f'nDPS="{nDPS}" deve ser ≥ 1.','Número sequencial positivo.')
        except: add("E1235","nDPS",f'nDPS="{nDPS}" não é número.','Use apenas dígitos.')

    cLocEmi=get("cLocEmi")
    if cLocEmi:
        if not re.match(r"^\d{7}$",cLocEmi): add("E0037","cLocEmi",f'Código IBGE "{cLocEmi}" deve ter 7 dígitos.','Ex: 3550308=São Paulo.')
        elif cLocEmi not in TAB_CIDADES: av("E0037","cLocEmi",f'Código IBGE "{cLocEmi}" não encontrado.','Verifique o código do município.')
        else: inf("cLocEmi",f'Município emissor: {TAB_CIDADES[cLocEmi]}')

    tpEmit=get("tpEmit")
    if tpEmit and tpEmit not in ("1","2","3"): add("E9996","tpEmit",f'tpEmit="{tpEmit}" inválido. 1=Prestador,2=Tomador,3=Intermediário.','Use 1 para emissão pelo prestador.')

    prest_nodes=root.xpath("//ns:prest",namespaces=nsm); cnpj_prest=None
    if prest_nodes:
        p=prest_nodes[0]
        cnpj_n=p.xpath("ns:CNPJ",namespaces=nsm); cpf_n=p.xpath("ns:CPF",namespaces=nsm)
        cnpj_prest=(cnpj_n[0].text or "").strip() if cnpj_n else None
        cpf_prest=(cpf_n[0].text or "").strip() if cpf_n else None
        if cnpj_prest and not _val_cnpj(cnpj_prest): add("E0080","prest/CNPJ",f'CNPJ do prestador "{cnpj_prest}" inválido.','Verifique os 14 dígitos (módulo 11 duplo).')
        if cpf_prest and not _val_cpf(cpf_prest): add("E0096","prest/CPF",f'CPF do prestador "{cpf_prest}" inválido.','Verifique os 11 dígitos.')
        opSN=p.xpath("ns:regTrib/ns:opSimpNac",namespaces=nsm)
        if opSN:
            v=(opSN[0].text or "").strip()
            if v not in ("1","2","3"): add("E0160","prest/regTrib/opSimpNac",f'opSimpNac="{v}" inválido.','1=Não optante,2=MEI,3=ME/EPP.')
        regEsp=p.xpath("ns:regTrib/ns:regEspTrib",namespaces=nsm)
        if regEsp:
            v=(regEsp[0].text or "").strip()
            if v not in [str(i) for i in range(7)]+["9"]: add("E0172","prest/regTrib/regEspTrib",f'regEspTrib="{v}" inválido. Use 0–6 ou 9.','0=Nenhum,1=Cooperativa,2=Estimativa,3=Microempresa,4=Notário,5=Autônomo,6=Soc.Prof.,9=Outros.')

    toma_nodes=root.xpath("//ns:toma",namespaces=nsm)
    if toma_nodes:
        t=toma_nodes[0]
        cnpj_tn=t.xpath("ns:CNPJ",namespaces=nsm); cpf_tn=t.xpath("ns:CPF",namespaces=nsm)
        cnpj_t=(cnpj_tn[0].text or "").strip() if cnpj_tn else None
        cpf_t=(cpf_tn[0].text or "").strip() if cpf_tn else None
        if cnpj_t:
            if not _val_cnpj(cnpj_t): add("E0188","toma/CNPJ",f'CNPJ do tomador "{cnpj_t}" inválido.','Verifique os 14 dígitos.')
            if cnpj_prest and cnpj_t==cnpj_prest: add("E0202","toma/CNPJ","Tomador idêntico ao prestador.","Devem ser entidades distintas.")
        if cpf_t and not _val_cpf(cpf_t): add("E0206","toma/CPF",f'CPF do tomador "{cpf_t}" inválido.','Verifique os 11 dígitos.')

    cTribNac=get("cTribNac")
    if cTribNac:
        if not re.match(r"^\d{6}$",cTribNac): add("E0310","serv/cServ/cTribNac",f'cTribNac="{cTribNac}" deve ter 6 dígitos.','Ex: 010101.')
        elif cTribNac not in TAB_SERV and cTribNac not in (TAB_TODAS.get("servicos") or {}): av("E0310","serv/cServ/cTribNac",f'Código "{cTribNac}" não encontrado (LC 116/2003).','Verifique o Anexo VI.')
        else:
            desc=TAB_SERV.get(cTribNac) or (TAB_TODAS.get("servicos") or {}).get(cTribNac,"")
            if desc: inf("serv/cServ/cTribNac",f'Serviço: {desc[:80]}')

    cNBS=get("cNBS")
    if cNBS and not re.match(r"^\d{9}$",cNBS): add("E0316","serv/cServ/cNBS",f'NBS="{cNBS}" inválido. Exige 9 dígitos sem pontos.','Ex: 115021000. Remova pontos.')
    if root.xpath("//ns:IBSCBS",namespaces=nsm) and not cNBS: add("E0322","serv/cServ/cNBS","NBS obrigatório quando há dados IBS/CBS.",'Informe o código NBS de 9 dígitos.')

    indOp=get("indOp")
    if indOp and indOp not in TAB_INDOP: add("E0901","IBSCBS/indOp",f'indOp="{indOp}" inexistente (Anexo VII).','Consulte o Anexo VII — Tabela indOp IBS/CBS.')

    pAliq=get("pAliq"); pAliq_num=None; pAliq_inf=False
    if pAliq is not None and pAliq.strip():
        try: pAliq_num=float(pAliq); pAliq_inf=True
        except: add("E0595","tribMun/pAliq",f'pAliq="{pAliq}" não é número.','Use decimal. Ex: 5.00')

    opSN_n=_get(root,"opSimpNac") or ""; rgTrib_n=_get(root,"regApTribSN") or ""
    tpRetN=_get(root,"tpRetISSQN") or ""; tribIN=_get(root,"tribISSQN") or ""; rEspN=_get(root,"regEspTrib") or "0"

    if pAliq_inf and pAliq_num is not None:
        if pAliq_num>5: add("E0595","tribMun/pAliq",f'Alíquota {pAliq_num}% acima do máximo de 5% (LC 116/2003).','Máximo: 5%.')
        elif opSN_n=="2": add("E0600","tribMun/pAliq",'pAliq não permitido para MEI.','Remova pAliq.')
        elif tribIN in ("2","3","4"): add("E0602","tribMun/pAliq",f'pAliq não permitido com tribISSQN={tribIN}.','Remova pAliq.')
        elif rEspN not in ("0",""): add("E0604","tribMun/pAliq",f'pAliq não permitido com regEspTrib={rEspN}.','Remova pAliq.')
        elif opSN_n=="3" and rgTrib_n in ("1","") and tpRetN=="1":
            if pAliq_num==0: av("E0625","tribMun/pAliq","⚠ pAliq=0.00 com ME/EPP+SN+sem retenção: SEFAZ pode rejeitar.","Remova pAliq.")
            else: add("E0625","tribMun/pAliq",f"pAliq={pAliq_num}% não permitido para ME/EPP+SN+sem retenção.","Remova pAliq.")
        elif opSN_n=="3" and rgTrib_n in ("2","3"): av("E0635","tribMun/pAliq",f'⚠ ME/EPP fora SN: se município conveniado, pAliq não deve ser informado.','Verifique se município está ativo no SEFAZ Nacional.')
        elif 0<pAliq_num<2: av("E0595","tribMun/pAliq",f'Alíquota {pAliq_num}% abaixo do mínimo de 2% (LC 157/2016).','Mínimo: 2%.')

    if opSN_n=="3" and rgTrib_n in ("2","3") and tpRetN in ("2","3") and not pAliq_inf: add("E0621","tribMun/pAliq",'pAliq obrigatório para ME/EPP fora SN com retenção.','Informe a alíquota municipal.')
    if opSN_n=="1" and pAliq_inf: av("E0617","tribMun/pAliq",'⚠ Para Não Optante, se município conveniado, pAliq não deve ser informado.','Verifique convênio municipal.')

    tpRet=get("tpRetISSQN"); tribI=get("tribISSQN")
    if tpRet in ("2","3") and tribI in ("2","3","4"): add("E0580","tribMun/tpRetISSQN",f'Retenção tpRetISSQN={tpRet} incompatível com tribISSQN={tribI}.','Use tpRetISSQN=1.')

    vS_n=root.xpath("//ns:vServ",namespaces=nsm); vD_n=root.xpath("//ns:vDescIncond",namespaces=nsm)
    if vS_n and vD_n:
        try:
            vs=float(vS_n[0].text or "0"); vd=float(vD_n[0].text or "0")
            if vd>=vs: add("E0431","valores/vDescIncond",f'Desconto R${vd:.2f} ≥ valor do serviço R${vs:.2f}.','O desconto deve ser menor que o valor do serviço.')
        except: pass

    # ── Validações IBS/CBS expandidas (NT-007 / LC 214/2025) ─────────────────
    ibscbs_nodes=root.xpath("//ns:IBSCBS",namespaces=nsm)
    if ibscbs_nodes and dCompet:
        try:
            if int(dCompet[:4])<2026: av("E0850","IBSCBS",f'IBS/CBS para {dCompet}. Vigência inicia 01/2026 (LC 214/2025).','Remova IBSCBS para competências < 2026.')
        except: pass

    if ibscbs_nodes:
        ib=ibscbs_nodes[0]
        def ib_get(tag): return ib.findtext(f"{{{NS_NAC}}}{tag}") or ib.findtext(tag) or ""
        def ib_xpath(expr): return ib.xpath(expr.replace("ns:", f"{{{NS_NAC}}}"))

        cIndOp_v = ib_get("cIndOp")
        if not cIndOp_v.strip(): add("E0901","IBSCBS/cIndOp","cIndOp obrigatório quando há grupo IBSCBS.","Informe o código indicador de operação (Anexo VII).")
        elif cIndOp_v not in TAB_INDOP: add("E0901","IBSCBS/cIndOp",f'cIndOp="{cIndOp_v}" inexistente (Anexo VII).','Consulte o Anexo VII — Tabela cIndOp IBS/CBS.')

        indDest_v = ib_get("indDest")
        if not indDest_v.strip(): add("E1501","IBSCBS/indDest","indDest obrigatório no grupo IBSCBS.","0=tomador é destinatário; 1=outro destinatário.")
        elif indDest_v not in ("0","1"): add("E1501","IBSCBS/indDest",f'indDest="{indDest_v}" inválido.','Use 0 (tomador=destinatário) ou 1 (outro).')

        # Destinatário obrigatório quando indDest=1
        if indDest_v=="1":
            dest_nodes = ib_xpath("ns:dest") if "{" in str(ib.tag) else ib.findall("dest")
            if not dest_nodes: add("E1503","IBSCBS/dest","Grupo dest obrigatório quando indDest=1.","Informe os dados do destinatário.")

        # tpOper: quando há ente governamental
        tpOper_v = ib_get("tpOper")
        tpEnteGov_v = ib_get("tpEnteGov")
        if tpEnteGov_v and not tpOper_v: add("E1505","IBSCBS/tpOper","tpOper obrigatório quando tpEnteGov informado.","Informe o tipo de operação governamental.")
        if tpOper_v and tpOper_v not in ("1","2","3","4","5"):
            add("E1507","IBSCBS/tpOper",f'tpOper="{tpOper_v}" inválido.','Valores válidos: 1-5.')

        # CST do gIBSCBS obrigatório
        gIBSCBS_nodes = ib_xpath(".//ns:gIBSCBS") if "{" in str(ib.tag) else ib.findall(".//gIBSCBS")
        for g in gIBSCBS_nodes:
            cst_ibs = (g.findtext(f"{{{NS_NAC}}}CST") or g.findtext("CST") or "").strip()
            cClass  = (g.findtext(f"{{{NS_NAC}}}cClassTrib") or g.findtext("cClassTrib") or "").strip()
            if not cst_ibs: add("E1509","IBSCBS/gIBSCBS/CST","CST do IBS/CBS obrigatório em gIBSCBS.","Informe o Código de Situação Tributária.")
            if not cClass:  add("E1511","IBSCBS/gIBSCBS/cClassTrib","cClassTrib obrigatório em gIBSCBS.","Informe a Classificação Tributária IBS/CBS.")

        # NBS obrigatório com IBSCBS (NT-007)
        cNBS_v = get("cNBS") if callable(get) else ""
        if not cNBS_v: add("E0322","serv/cServ/cNBS","NBS obrigatório quando há grupo IBSCBS (NT-007).","Informe o código NBS de 9 dígitos.")

        # Vigência por fase (2026 = fase inicial)
        if dCompet:
            try:
                ano_c = int(dCompet[:4])
                mes_c = int(dCompet[5:7]) if len(dCompet)>=7 else 1
                if ano_c==2026 and mes_c<1: av("E0851","IBSCBS","IBS/CBS: vigência inicia 01/2026.","Remova IBSCBS para competências anteriores.")
            except: pass

    cLocPrest=_get(root,"cLocPrestacao")
    if cLocPrest:
        if not re.match(r"^\d{7}$",cLocPrest): add("E0302","serv/locPrest/cLocPrestacao",f'cLocPrestacao="{cLocPrest}" deve ter 7 dígitos IBGE.','Informe o código IBGE do município.')
        elif cLocPrest not in TAB_CIDADES: av("E0302","serv/locPrest/cLocPrestacao",f'Código "{cLocPrest}" não encontrado.','Verifique o código IBGE.')
        else: inf("serv/locPrest/cLocPrestacao",f'Local de prestação: {TAB_CIDADES[cLocPrest]}')

    if serie:
        try:
            s_num=int(serie)
            if not (1<=s_num<=89999): av("E0010","serie",f'Série {s_num} fora das faixas permitidas (1-89999).','Use série 1-49999 para aplicativo próprio.')
        except: pass

    cMot=get("cMotivoEmisTI")
    if cMot and tpEmit=="1": add("E0029","cMotivoEmisTI",'cMotivoEmisTI não pode existir com tpEmit=1 (Prestador).','Remova o campo cMotivoEmisTI.')

    cMotSubst=_get(root,"cMotivo"); xMotSubst=_get(root,"xMotivo")
    if cMotSubst=="99" and not xMotSubst: add("E0078","subst/xMotivo",'xMotivo obrigatório quando cMotivo=99.','Informe a descrição do motivo.')

    if prest_nodes:
        if rgTrib_n:
            if opSN_n in ("1","2"): add("E0162","prest/regTrib/regApTribSN",f'regApTribSN não pode ser preenchido para opSimpNac={opSN_n}.','Remova regApTribSN.')
        else:
            if opSN_n=="3": add("E0166","prest/regTrib/regApTribSN",'regApTribSN obrigatório para ME/EPP (opSimpNac=3).','1=SN,2=ISSQN fora SN,3=Todos fora SN.')

    rEspN=_get(root,"regEspTrib") or "0"
    if opSN_n=="2" and rEspN not in ("0",""): add("E0174","prest/regTrib/regEspTrib",f'regEspTrib={rEspN} não permitido para MEI.','Use regEspTrib=0.')
    if opSN_n=="3" and rgTrib_n in ("1","") and rEspN not in ("0",""): add("E0175","prest/regTrib/regEspTrib",f'regEspTrib={rEspN} não permitido para ME/EPP com regApTribSN=1.','Use regEspTrib=0.')

    if tpRetN=="2":
        has_toma=False
        if toma_nodes:
            tn=toma_nodes[0]; has_toma=bool(tn.xpath("ns:CNPJ",namespaces={"ns":NS_NAC}) or tn.xpath("ns:CPF",namespaces={"ns":NS_NAC}))
        if not has_toma: add("E0204","toma/CNPJ",'CNPJ/CPF do tomador obrigatório com tpRetNSSQN=2.','Identifique o tomador.')
    if tpRetN=="3":
        interm_n=root.xpath("//ns:interm",namespaces={"ns":NS_NAC}); has_interm=False
        if interm_n: has_interm=bool(interm_n[0].xpath("ns:CNPJ",namespaces={"ns":NS_NAC}) or interm_n[0].xpath("ns:CPF",namespaces={"ns":NS_NAC}))
        if not has_interm: add("E0264","interm/CNPJ",'CNPJ/CPF do intermediário obrigatório com tpRetNSSQN=3.','Identifique o intermediário.')

    cPaisPresta=_get(root,"cPaisPrestacao")
    if cPaisPresta and cPaisPresta not in TAB_PAISES: add("E0304","serv/locPrest/cPaisPrestacao",f'Código de país "{cPaisPresta}" não existe na tabela ISO.','Informe código ISO válido. Ex: 2496=EUA.')
    if opSN_n=="2" and tpRetN in ("2","3"): add("E0583","tribMun/tpRetNSSQN",f'Retenção tpRetNSSQN={tpRetN} não permitida para MEI.','Use tpRetNSSQN=1.')

    tpSusp=_get(root,"tpSUSP") or _get(root,"tpSusp")
    if tpSusp and tpSusp not in ("","0") and tribIN in ("2","3","4"): add("E0585","tribMun/exigSusp",f'Suspensão não permitida com tribISSQN={tribIN}.','Remova exigSusp ou corrija tribISSQN.')

    tpImun=_get(root,"tpImunidade")
    if tribIN=="2":
        if not tpImun or tpImun.strip()=="": add("E0592","tribMun/tpImunidade",'tpImunidade obrigatório quando tribISSQN=2.','Informe o tipo de imunidade.')
        elif tpImun=="0": add("E0593","tribMun/tpImunidade",'tpImunidade=0 não é permitido.','Informe o tipo correto (1–9).')
    elif tpImun and tpImun.strip() not in ("","0"): add("E0592","tribMun/tpImunidade",f'tpImunidade só quando tribISSQN=2. Atual={tribIN}.','Remova tpImunidade ou corrija tribISSQN.')

    cTribNac_v=get("cTribNac") or ""
    if cTribNac_v=="220101" and tpRetN in ("2","3"): add("E0596","tribMun/tpRetNSSQN",'Retenção não permitida para cTribNac=220101 (Exploração de rodovia).','Use tpRetNSSQN=1.')

    cLocIncid=_get(root,"cLocIncid"); xLocIncid=_get(root,"xLocIncid")
    if det_tipo=="NFSe":
        if cLocIncid:
            if tribIN in ("2","3","4"): add("E1301","cLocIncid",f'cLocIncid não pode existir com tribISSQN={tribIN}.','Remova cLocIncid.')
            elif not re.match(r"^\d{7}$",cLocIncid): add("E1309","cLocIncid",f'cLocIncid "{cLocIncid}" deve ter 7 dígitos IBGE.','Informe o código IBGE.')
            elif cLocIncid not in TAB_CIDADES: add("E1309","cLocIncid",f'Código "{cLocIncid}" não encontrado na tabela IBGE.','Verifique o código.')
            else: inf("cLocIncid",f'Local de incidência: {TAB_CIDADES[cLocIncid]}')
        elif tribIN=="1": add("E1305","cLocIncid",'cLocIncid obrigatório na NFS-e com tribISSQN=1.','Informe o código IBGE do município de incidência.')
        if cLocIncid and not xLocIncid: add("E1327","xLocIncid",'xLocIncid obrigatório quando cLocIncid informado.','Informe o nome do município.')
        if xLocIncid and not cLocIncid: add("E1329","xLocIncid",'xLocIncid não pode existir sem cLocIncid.','Remova xLocIncid ou informe cLocIncid.')

    vBCPis=_get(root,"vBCPisCofins"); pAliqPis=_get(root,"pAliqPis"); pAliqCof=_get(root,"pAliqCofins")
    vPis=_get(root,"vPis"); vCofins=_get(root,"vCofins"); vServN=_get(root,"vServ") or _get(root,"vReceb"); cst_n=_get(root,"CST") or ""
    if vBCPis and vServN:
        try:
            if float(vBCPis)>float(vServN): add("E0677","tribFed/piscofins/vBCPisCofins",f'vBCPisCofins={vBCPis} > vServ={vServN}.','BC do PIS/COFINS deve ser ≤ valor do serviço.')
        except: pass
    if vBCPis and float(vBCPis or "0")>0:
        if cst_n not in ("0","8","9","","None"):
            if not pAliqPis: add("E0684","tribFed/piscofins/pAliqPis",'pAliqPis obrigatório quando vBCPisCofins informado.','Informe a alíquota do PIS.')
            if not pAliqCof: add("E0690","tribFed/piscofins/pAliqCofins",'pAliqCofins obrigatório quando vBCPisCofins informado.','Informe a alíquota do COFINS.')
    if pAliqPis:
        try:
            a=float(pAliqPis)
            if not (0<=a<=100): add("E0686","tribFed/piscofins/pAliqPis",f'pAliqPis={a}% deve estar entre 0% e 100%.','Corrija a alíquota.')
        except: pass
    if pAliqCof:
        try:
            a=float(pAliqCof)
            if not (0<=a<=100): add("E0692","tribFed/piscofins/pAliqCofins",f'pAliqCofins={a}% deve estar entre 0% e 100%.','Corrija a alíquota.')
        except: pass
    if cst_n in ("4","6") and (pAliqPis and float(pAliqPis or "0")!=0 or pAliqCof and float(pAliqCof or "0")!=0):
        add("E0688","tribFed/piscofins",f'CST={cst_n} (Alíq. Zero): pAliqPis e pAliqCofins devem ser 0.','Zere as alíquotas de PIS e COFINS.')
    if vBCPis and pAliqPis and vPis:
        try:
            esp=round(float(vBCPis)*float(pAliqPis)/100,2)
            if abs(esp-round(float(vPis),2))>0.02: add("E0694","tribFed/piscofins/vPis",f'vPis={vPis} ≠ BC×alíq/100={esp}.',f'Corrija vPis para {esp}.')
        except: pass
    if vBCPis and pAliqCof and vCofins:
        try:
            esp=round(float(vBCPis)*float(pAliqCof)/100,2)
            if abs(esp-round(float(vCofins),2))>0.02: add("E0696","tribFed/piscofins/vCofins",f'vCofins={vCofins} ≠ BC×alíq/100={esp}.',f'Corrija vCofins para {esp}.')
        except: pass
    for campo,cod,nome in [("vRetCP","E0699","CP"),("vRetIRRF","E0700","IRRF"),("vRetCSLL","E0701","CSLL")]:
        val=_get(root,campo)
        if val and vServN:
            try:
                v,vs=float(val),float(vServN)
                if v<=0 or v>=vs: add(cod,f"tribFed/{campo}",f'{campo}={val} deve ser > 0 e < vServ ({vServN}).',f'Corrija o valor de {nome}.')
            except: pass
    for campo,cod,nome in [("vTotTribFed","E0702","federal"),("vTotTribEst","E0703","estadual"),("vTotTribMun","E0704","municipal")]:
        val=_get(root,campo)
        if val and vServN:
            try:
                v,vs=float(val),float(vServN)
                if v<0 or v>vs: av(cod,f"totTrib/{campo}",f'{campo}={val} deve estar entre 0 e vServ ({vServN}).',f'Corrija total de tributos {nome}.')
            except: pass
    if cTribNac_v=="990101" and tribIN!="4": add("E0532","tribMun/tribISSQN",'Para cTribNac=990101, tribISSQN deve ser 4 (Não Incidência).','Defina tribISSQN=4.')
    if det_tipo=="NFSe":
        ibscbs_dps=root.xpath("//ns:DPS//ns:IBSCBS",namespaces={"ns":NS_NAC}); ibscbs_nfs=root.xpath("//ns:infNFSe/ns:IBSCBS",namespaces={"ns":NS_NAC})
        if ibscbs_dps and not ibscbs_nfs: add("E1515","infNFSe/IBSCBS",'Grupo IBSCBS da NFS-e obrigatório quando IBSCBS da DPS informado.','Informe o grupo IBSCBS na NFS-e.')
        if not ibscbs_dps and ibscbs_nfs: add("E1517","infNFSe/IBSCBS",'Grupo IBSCBS não pode existir na NFS-e sem IBSCBS na DPS.','Remova IBSCBS da NFS-e.')
    return oc

# ── Validações Tecnospeed ──────────────────────────────────────────────────
def validar_tecnospeed(root, dps_node=None):
    _root=dps_node if dps_node is not None else root; oc=[]
    def add(cod,campo,msg,fix=""): oc.append(_err(cod,campo,msg,fix))
    def av(cod,campo,msg,fix=""):  oc.append(_av(cod,campo,msg,fix))
    def inf(campo,msg):            oc.append(_inf(campo,msg))
    def get(tag):                  return _get_nt(_root,tag)

    cpfcnpj_p=get("CpfCnpjPrestador")
    if cpfcnpj_p and not _val_cnpj_cpf(cpfcnpj_p): add("E0080","CpfCnpjPrestador",f'CNPJ/CPF do prestador "{cpfcnpj_p}" inválido.','Verifique os dígitos verificadores.')
    cpfcnpj_t=get("CpfCnpjTomador")
    if cpfcnpj_t:
        if not _val_cnpj_cpf(cpfcnpj_t): add("E0188","CpfCnpjTomador",f'CNPJ/CPF do tomador "{cpfcnpj_t}" inválido.','Verifique os dígitos verificadores.')
        if cpfcnpj_p and cpfcnpj_t==cpfcnpj_p: add("E0202","CpfCnpjTomador","Tomador idêntico ao prestador.","Devem ser entidades distintas.")
    cod_em=get("CodigoCidadeEmitente")
    if cod_em:
        if not re.match(r"^\d{7}$",cod_em): add("E0037","CodigoCidadeEmitente",f'Código IBGE "{cod_em}" deve ter 7 dígitos.','Ex: 3550308=São Paulo.')
        elif cod_em not in TAB_CIDADES: av("E0037","CodigoCidadeEmitente",f'Código "{cod_em}" não encontrado.','Verifique o código IBGE.')
        else: inf("CodigoCidadeEmitente",f'Município emissor: {TAB_CIDADES[cod_em]}')
    cod_pr=get("CodigoCidadePrestacao")
    if cod_pr:
        if re.match(r"^\d{7}$",cod_pr) and cod_pr in TAB_CIDADES: inf("CodigoCidadePrestacao",f'Local de prestação: {TAB_CIDADES[cod_pr]}')
        elif cod_pr and not re.match(r"^\d{7}$",cod_pr): av("E0302","CodigoCidadePrestacao",f'Código IBGE "{cod_pr}" deve ter 7 dígitos.','Ex: 3550308=São Paulo.')
    cod_serv=get("CodigoItemListaServico")
    if cod_serv:
        cod_norm=cod_serv.replace(".","").zfill(4) if cod_serv else ""
        tab_s=TAB_TODAS.get("servicos") or TAB_SERV
        if cod_serv not in tab_s and cod_norm+"00" not in tab_s: av("E0310","CodigoItemListaServico",f'Código "{cod_serv}" não encontrado (LC 116/2003).','Ex: 01.01=Análise e desenvolvimento de sistemas.')

    aliq=get("AliquotaISS"); aliq_num=None; aliq_informada=False
    if aliq is not None and aliq.strip():
        try: aliq_num=float(aliq); aliq_informada=True
        except: add("E0595","AliquotaISS",f'AliquotaISS="{aliq}" não é número.','Use decimal. Ex: 5.00')

    osn=get("OptanteSimplesNacional") or ""; rgt=get("RegimeApuracaoTributaria") or ""
    tret=get("TipoRetIss") or ""; trib=get("TipoTributacaoIss") or ""; regesp=get("RegimeEspecialTributacao") or "0"

    if aliq_informada and aliq_num is not None:
        if aliq_num>5: add("E0595","AliquotaISS",f'Alíquota ISS {aliq_num}% acima do máximo de 5%.','Máximo: 5%.')
        elif osn=="2": add("E0600","AliquotaISS",'Alíquota não permitida para MEI.','Remova AliquotaISS.')
        elif trib in ("2","3","4","5","8"): add("E0602","AliquotaISS",f'Alíquota não permitida com TipoTributacaoIss={trib}.','Remova AliquotaISS.')
        elif regesp not in ("0",""): add("E0604","AliquotaISS",f'Alíquota não permitida com RegimeEspecialTributacao={regesp}.','Remova AliquotaISS.')
        elif osn=="3" and rgt in ("1","") and tret=="1":
            if aliq_num==0 or aliq_num is None: av("E0625","AliquotaISS","⚠ AliquotaISS=0 com ME/EPP+SN+sem retenção: SEFAZ pode rejeitar.","Remova ou deixe vazio.")
            else: add("E0625","AliquotaISS",f'AliquotaISS={aliq_num}% não permitido para ME/EPP+SN+sem retenção.','Remova AliquotaISS.')
        elif osn=="3" and rgt in ("2","3"): av("E0635","AliquotaISS",f'⚠ ME/EPP fora SN: se município conveniado, AliquotaISS não deve ser informada.','Verifique convênio no SEFAZ Nacional.')
        elif 0<aliq_num<2: av("E0595","AliquotaISS",f'Alíquota ISS {aliq_num}% abaixo do mínimo de 2%.','Mínimo: 2%.')

    if osn=="3" and rgt in ("2","3") and tret in ("2","3") and not aliq_informada: add("E0621","AliquotaISS",'AliquotaISS obrigatória para ME/EPP fora SN com retenção.','Informe a AliquotaISS.')
    if osn=="1" and aliq_informada and aliq_num and aliq_num>0: av("E0617","AliquotaISS",'⚠ Para Não Optante, se município conveniado, AliquotaISS não deve ser informada.','Verifique convênio municipal.')

    trib_iss=get("TipoTributacaoIss")
    if trib_iss and trib_iss not in [str(i) for i in range(1,9)]: add("E0529","TipoTributacaoIss",f'TipoTributacaoIss="{trib_iss}" inválido.','1=Tributado,2=Tributado Fixo,3=Tributado Especial,4=Isento,5=Imune,6=Susp.Admin,7=Susp.Judicial,8=Exportação.')
    tret=get("TipoRetIss")
    if tret and tret not in ("1","2","3"): add("E0580","TipoRetIss",f'TipoRetIss="{tret}" inválido.','1=Não Retido,2=Retido Tomador,3=Retido Intermediário.')
    if tret in ("2","3") and trib_iss in ("5","8"): add("E0580","TipoRetIss",f'Retenção TipoRetIss={tret} incompatível com TipoTributacaoIss={trib_iss}.','Use TipoRetIss=1.')
    opt_sn=get("OptanteSimplesNacional")
    if opt_sn and opt_sn not in ("1","2","3"): add("E0160","OptanteSimplesNacional",f'OptanteSimplesNacional="{opt_sn}" inválido.','1=Não optante,2=MEI,3=ME/EPP.')
    comp=get("Competencia")
    if comp and not (re.match(r"^\d{4}-\d{2}-\d{2}$",comp) or re.match(r"^\d{2}/\d{2}/\d{4}$",comp)): av("E0015","Competencia",f'Competência="{comp}" — verifique o formato.','Use AAAA-MM-DD.')
    v_serv=get("ValorServicos")
    if v_serv:
        try:
            v=float(v_serv.replace(",","."))
            if v<=0: add("E0427","ValorServicos",f'ValorServicos="{v_serv}" deve ser > 0.','Informe valor positivo.')
        except: add("E0427","ValorServicos",f'ValorServicos="{v_serv}" não é número.','Use decimal. Ex: 1000.00')
    v_desc=get("DescontoIncondicionado")
    if v_serv and v_desc:
        try:
            vs=float(v_serv.replace(",",".")); vd=float(v_desc.replace(",","."))
            if vd>=vs: add("E0431","DescontoIncondicionado",f'Desconto R${vd:.2f} ≥ valor do serviço R${vs:.2f}.','O desconto deve ser menor que o valor do serviço.')
        except: pass
    pais_p=get("PaisPrestador")
    if pais_p and pais_p.strip() and pais_p not in TAB_PAISES and pais_p not in TAB_PAISES.values(): av("E0146","PaisPrestador",f'Código de país "{pais_p}" não encontrado na tabela ISO.','Ex: 1058=Brasil.')
    ibs_sit=get("SituacaoTributariaIbsCbs"); ibs_clas=get("ClassificacaoTributariaIbsCbs")
    if ibs_sit or ibs_clas:
        comp_v=get("Competencia") or ""; ano_ibs=0
        try: ano_ibs=int(comp_v[:4]) if comp_v else 0
        except: pass
        if ano_ibs>0 and ano_ibs<2026: av("E0850","SituacaoTributariaIbsCbs",f'Dados IBS/CBS para competência {comp_v}. Vigência inicia 01/2026.','Remova campos IBS/CBS.')
    cNBS=get("CodigoNbs")
    if cNBS and not re.match(r"^\d{9}$",cNBS): add("E0316","CodigoNbs",f'CodigoNbs="{cNBS}" inválido. 9 dígitos sem pontos.','Ex: 115021000.')
    rgt_v=get("RegimeApuracaoTributaria") or ""
    if rgt_v and osn in ("1","2"): add("E0162","RegimeApuracaoTributaria",f'RegimeApuracaoTributaria não pode existir para OptanteSimplesNacional={osn}.','Remova o campo.')
    elif not rgt_v and osn=="3": av("E0166","RegimeApuracaoTributaria",'RegimeApuracaoTributaria obrigatório para ME/EPP.','1=SN,2=ISSQN fora SN,3=Todos fora SN.')
    regesp_v=get("RegimeEspecialTributacao") or "0"
    if osn=="2" and regesp_v not in ("0",""): add("E0174","RegimeEspecialTributacao",f'RegimeEspecialTributacao={regesp_v} não permitido para MEI.','Use 0.')
    if osn=="3" and rgt_v=="1" and regesp_v not in ("0",""): add("E0175","RegimeEspecialTributacao",f'RegimeEspecialTributacao={regesp_v} não permitido com RegimeApuracaoTributaria=1.','Use 0.')
    cpT2=get("CpfCnpjTomador") or ""
    if tret=="2" and not cpT2.strip(): add("E0204","CpfCnpjTomador",'CpfCnpjTomador obrigatório com TipoRetIss=2.','Identifique o tomador.')
    cpI=get("CpfCnpjIntermediario") or ""
    if tret=="3" and not cpI.strip(): add("E0264","CpfCnpjIntermediario",'CpfCnpjIntermediario obrigatório com TipoRetIss=3.','Identifique o intermediário.')
    cpais_prest=get("CodigoPaisPrestacao") or ""
    if cpais_prest.strip() and cpais_prest not in TAB_PAISES and cpais_prest not in TAB_PAISES.values(): add("E0304","CodigoPaisPrestacao",f'Código de país "{cpais_prest}" não existe na tabela ISO.','Informe código ISO válido.')
    if osn=="2" and tret in ("2","3"): add("E0583","TipoRetIss",f'Retenção TipoRetIss={tret} não permitida para MEI.','Use TipoRetIss=1.')
    tpSusp_v=get("TipoExigibilidadeSuspensa") or ""; trib_v=get("TipoTributacaoIss") or ""
    if tpSusp_v.strip() and tpSusp_v not in ("0","") and trib_v in ("2","3","4","5","8"): add("E0585","TipoExigibilidadeSuspensa",f'TipoExigibilidadeSuspensa não permitida com TipoTributacaoIss={trib_v}.','Remova ou corrija TipoTributacaoIss.')
    tipoImun_v=get("TipoImunidade") or ""
    if trib_v=="5":
        if not tipoImun_v.strip(): av("E0592","TipoImunidade",'TipoImunidade deve ser informado quando TipoTributacaoIss=5.','Informe o tipo de imunidade.')
        elif tipoImun_v=="0": add("E0593","TipoImunidade",'TipoImunidade=0 não é permitido.','Informe o tipo correto.')
    elif tipoImun_v.strip() and tipoImun_v not in ("0",""): av("E0592","TipoImunidade",f'TipoImunidade só para TipoTributacaoIss=5. Atual={trib_v}.','Remova TipoImunidade.')
    cod_serv_v=get("CodigoItemListaServico") or ""
    if cod_serv_v in ("22.01","2201","220101","22.01.01") and tret in ("2","3"): add("E0596","TipoRetIss",'Retenção não permitida para exploração de rodovia (22.01).','Use TipoRetIss=1.')
    vBC_v=get("ValorBCPisCofins") or ""; vS_v=get("ValorServicos") or ""
    pPis_v=get("AliquotaPIS") or ""; pCof_v=get("AliquotaCOFINS") or ""
    vPis_v=get("ValorPIS") or ""; vCof_v=get("ValorCOFINS") or ""
    if vBC_v.strip() and vS_v.strip():
        try:
            if float(vBC_v.replace(",","."))>float(vS_v.replace(",",".")): add("E0677","ValorBCPisCofins",f'ValorBCPisCofins={vBC_v} > ValorServicos={vS_v}.','BC do PIS/COFINS deve ser ≤ valor do serviço.')
        except: pass
    if pPis_v.strip():
        try:
            a=float(pPis_v.replace(",","."))
            if not (0<=a<=100): add("E0686","AliquotaPIS",f'AliquotaPIS={a}% deve estar entre 0% e 100%.','Corrija a alíquota.')
        except: pass
    if pCof_v.strip():
        try:
            a=float(pCof_v.replace(",","."))
            if not (0<=a<=100): add("E0692","AliquotaCOFINS",f'AliquotaCOFINS={a}% deve estar entre 0% e 100%.','Corrija a alíquota.')
        except: pass
    if vBC_v.strip() and pPis_v.strip() and vPis_v.strip():
        try:
            _bc=float(vBC_v.replace(",","."))
            if _bc>0:
                esp=round(_bc*float(pPis_v.replace(",","."))/100,2); inf2=round(float(vPis_v.replace(",",".")),2)
                if abs(esp-inf2)>0.02: add("E0694","ValorPIS",f'ValorPIS={vPis_v} ≠ BC×alíq/100={esp}.',f'Corrija para {esp}.')
        except: pass
    if vBC_v.strip() and pCof_v.strip() and vCof_v.strip():
        try:
            _bc2=float(vBC_v.replace(",","."))
            if _bc2>0:
                esp=round(_bc2*float(pCof_v.replace(",","."))/100,2); inf2=round(float(vCof_v.replace(",",".")),2)
                if abs(esp-inf2)>0.02: add("E0696","ValorCOFINS",f'ValorCOFINS={vCof_v} ≠ BC×alíq/100={esp}.',f'Corrija para {esp}.')
        except: pass
    for campo_t,cod_t,nome_t in [("ValorCP","E0699","CP"),("ValorIRRF","E0700","IRRF"),("ValorCSLL","E0701","CSLL")]:
        val_t=get(campo_t) or ""
        if val_t.strip() and vS_v.strip():
            try:
                v_t=float(val_t.replace(",",".")); vs_t=float(vS_v.replace(",","."))
                if v_t<0 or v_t>=vs_t:
                    if v_t!=0: add(cod_t,campo_t,f'{campo_t}={val_t} deve ser > 0 e < ValorServicos ({vS_v}).',f'Corrija o valor de {nome_t}.')
            except: pass
    for campo_t,cod_t,nome_t in [("ValorTotalTribFed","E0702","federal"),("ValorTotalTribEst","E0703","estadual"),("ValorTotalTribMun","E0704","municipal")]:
        val_t=get(campo_t) or ""
        if val_t.strip() and vS_v.strip():
            try:
                v_t=float(val_t.replace(",",".")); vs_t=float(vS_v.replace(",","."))
                if v_t<0 or v_t>vs_t: av(cod_t,campo_t,f'{campo_t}={val_t} deve estar entre 0 e ValorServicos ({vS_v}).',f'Corrija total de tributos {nome_t}.')
            except: pass
    return oc

# ── Processador principal ──────────────────────────────────────────────────
def processar(body):
    result={"formato":"?","tipo":"?","versao":"?","valido":False,"resumo":{"erros":0,"alertas":0,"info":0,"total":0},"ocorrencias":[]}
    try:
        root=_safe_parse(body)
    except etree.XMLSyntaxError as ex:
        oc=_err("E1235","documento",f"XML mal formado: {ex}","Verifique tags, encoding UTF-8 e caracteres especiais.")
        oc["linha"]=getattr(ex,"lineno",None)
        result["ocorrencias"]=[oc]; result["resumo"]={"erros":1,"alertas":0,"info":0,"total":1}
        return result
    det=detectar(root)
    result["formato"]=det["formato"]; result["tipo"]=det["tipo"]; result["versao"]=det["ver"]
    result["subtipo"]="TX2" if det["tipo"].startswith("TX2") else det["tipo"]
    if det["formato"]=="desconhecido":
        result["ocorrencias"].append(_err("E1242","documento","Formato não reconhecido. Esperado: DPS Nacional, NFSe Nacional, CNC ou TecnoNFSeNacional.","Verifique o elemento raiz e o namespace do XML."))
    elif det["formato"]=="nacional":
        ns=root.nsmap.get(None,"")
        if NS_NAC not in ns: result["ocorrencias"].append(_err("E1228","xmlns",f'Namespace "{ns}" incorreto. Esperado: {NS_NAC}',f'Adicione xmlns="{NS_NAC}" no elemento raiz.'))
        try:
            sch=schema_nac(det["tipo"],det["ver"]); sch.validate(root)
            for e in sch.error_log:
                oc2=_err("E1235",e.path or "schema",f"Linha {e.line}: {e.message}",f"Schema {det['tipo']}_v{det['ver']}.xsd"); oc2["linha"]=e.line; result["ocorrencias"].append(oc2)
        except Exception as ex:
            result["ocorrencias"].append(_err("E1235","schema",f"Erro ao carregar schema: {ex}"))
        result["ocorrencias"].extend(validar_nacional(root,det["tipo"],det["ver"],det["tipo"]))
    elif det["formato"]=="tecnospeed":
        tag_raiz=etree.QName(root.tag).localname
        if tag_raiz=="TecnoNFSeNacional":
            try:
                sch=schema_tecno(); sch.validate(root)
                for e in sch.error_log:
                    oc2=_err("E1235",e.path or "schema",f"Linha {e.line}: {e.message}","Verifique o schema TecnoNFSeNacional_v1.xsd"); oc2["linha"]=e.line; result["ocorrencias"].append(oc2)
            except Exception as ex:
                result["ocorrencias"].append(_err("E1235","schema",f"Erro ao validar XSD Tecnospeed: {ex}"))
        result["ocorrencias"].extend(validar_tecnospeed(root,det.get("dps_node")))
    erros=sum(1 for o in result["ocorrencias"] if o["tipo"]=="erro")
    alertas=sum(1 for o in result["ocorrencias"] if o["tipo"]=="alerta")
    infos=sum(1 for o in result["ocorrencias"] if o["tipo"]=="info")
    result["valido"]=erros==0; result["resumo"]={"erros":erros,"alertas":alertas,"info":infos,"total":erros+alertas+infos}
    return result

# ── Servidor HTTP ──────────────────────────────────────────────────────────


# ── Análise de NT via Gemini 1.5 Flash ───────────────────────────────────
def _analisar_nt_gemini(url_pdf: str, nt_id: str) -> dict:
    import urllib.request, urllib.error, base64
    agora = time.time()
    if url_pdf in _NT_CACHE and (agora - _NT_CACHE[url_pdf]["ts"]) < _NT_CACHE_TTL:
        return {"ok": True, "resumo": _NT_CACHE[url_pdf]["resumo"], "from_cache": True}
    if not GEMINI_KEY:
        return {"ok": False, "erro": "GEMINI_API_KEY nao configurada. Crie o arquivo .env na pasta do sistema com: GEMINI_API_KEY=sua_chave_aqui"}
    try:
        req = urllib.request.Request(url_pdf, headers={"User-Agent": "NFS-e Validador/3.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            pdf_bytes = r.read()
        if len(pdf_bytes) < 500:
            return {"ok": False, "erro": "PDF invalido ou inacessivel."}
        pdf_b64 = base64.b64encode(pdf_bytes).decode()
    except Exception as ex:
        return {"ok": False, "erro": f"Erro ao baixar PDF: {ex}"}
    prompt = f"""Voce e um especialista em NFS-e Nacional (Nota Fiscal de Servico Eletronico do governo brasileiro).
Analise esta Nota Tecnica ({nt_id}) e produza um relatorio estruturado em portugues:

## RESUMO EXECUTIVO
O que muda e por que (3-5 linhas).

## CAMPOS NOVOS
Liste cada campo novo: nome, caminho XML, descricao, obrigatorio/opcional.

## CAMPOS ALTERADOS
Mudancas de ocorrencia, tamanho ou regra. Formato: campo: antes -> depois.

## CAMPOS REMOVIDOS
Se houver.

## NOVAS REGRAS DE VALIDACAO
Regras de negocio que sistemas emissores precisam implementar.

## IMPACTO PRATICO
O que precisa ser ajustado em sistemas emissores e validadores.

## VIGENCIA
Quando entra em vigor e em qual ambiente (producao, producao restrita, homologacao).

## PONTOS DE ATENCAO
Erros comuns que podem ocorrer apos esta NT.

Seja direto e tecnico. Se uma secao nao se aplicar, escreva "Nao especificado na NT"."""
    try:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
        payload = json.dumps({"contents":[{"parts":[{"inline_data":{"mime_type":"application/pdf","data":pdf_b64}},{"text":prompt}]}],"generationConfig":{"temperature":0.2,"maxOutputTokens":4096}}).encode()
        req2 = urllib.request.Request(api_url, data=payload, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req2, timeout=180) as r2:
            resp = json.loads(r2.read().decode())
        texto = resp.get("candidates",[{}])[0].get("content",{}).get("parts",[{}])[0].get("text","")
        if not texto:
            return {"ok": False, "erro": "Gemini nao retornou texto. Tente novamente."}
        _NT_CACHE[url_pdf] = {"ts": agora, "resumo": texto}
        return {"ok": True, "resumo": texto, "from_cache": False}
    except urllib.error.HTTPError as ex:
        corpo = ex.read().decode("utf-8", errors="ignore")[:300]
        if ex.code == 400: return {"ok": False, "erro": f"Chave invalida ou PDF rejeitado: {corpo}"}
        if ex.code == 429: return {"ok": False, "erro": "Limite de requisicoes Gemini atingido. Aguarde 1 minuto."}
        return {"ok": False, "erro": f"Erro Gemini HTTP {ex.code}: {corpo}"}
    except Exception as ex:
        return {"ok": False, "erro": f"Erro ao chamar Gemini: {ex}"}

# ── Fórum NFS-e Brasil — proxy server-side (evita CORS) ────────────────────
_FORUM_CACHE     = {"topics": [], "ts": 0}
_FORUM_CACHE_TTL = 2 * 3600  # 2 horas

def _get_forum_topics() -> dict:
    """Busca tópicos do fórum via Discourse API. Retorna cache se ainda válido."""
    import urllib.request, urllib.error

    agora = time.time()
    if _FORUM_CACHE["topics"] and (agora - _FORUM_CACHE["ts"]) < _FORUM_CACHE_TTL:
        return {"ok": True, "topics": _FORUM_CACHE["topics"],
                "ts": int(_FORUM_CACHE["ts"]), "from_cache": True}

    try:
        url = "https://forum.nfsebrasil.com.br/c/geral/4.json?page=0"
        req = urllib.request.Request(url, headers={
            "User-Agent": "NFS-e Validador/3.0 (interno)",
            "Accept":     "application/json",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        raw = data.get("topic_list", {}).get("topics", [])
        topics = [
            {
                "id":      t["id"],
                "titulo":  t["title"],
                "slug":    t["slug"],
                "replies": max(0, t.get("posts_count", 1) - 1),
                "views":   t.get("views", 0),
                "data":    t.get("last_posted_at") or t.get("created_at", ""),
                "tags":    t.get("tags", []),
            }
            for t in raw
            if not t.get("pinned_globally") and t.get("title")
        ][:40]

        _FORUM_CACHE["topics"] = topics
        _FORUM_CACHE["ts"]     = agora
        return {"ok": True, "topics": topics, "ts": int(agora), "from_cache": False}

    except Exception as ex:
        # Retornar cache antigo se houver, com flag de erro
        if _FORUM_CACHE["topics"]:
            return {"ok": False, "topics": _FORUM_CACHE["topics"],
                    "ts": int(_FORUM_CACHE["ts"]), "erro": str(ex), "from_cache": True}
        return {"ok": False, "topics": [], "ts": 0, "erro": str(ex)}


_DOCS_STATE    = BASE / "tabelas" / "docs_state.json"
_DOCS_DYNAMIC  = BASE / "tabelas" / "docs_dynamic.json"
_XSD_STATE   = BASE / "tabelas" / "xsd_update_state.json"
_NOTIF_LIDAS = BASE / "tabelas" / "notificacoes_lidas.json"

def _load_json_safe(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}

def _get_notificacoes() -> dict:
    """
    Lê docs_state.json e xsd_update_state.json e retorna notificações não lidas.
    Retorna: {"total": N, "docs": [...], "schemas": [...], "ultima_verificacao": "..."}
    """
    lidas_raw  = _load_json_safe(_NOTIF_LIDAS)
    # Suportar dois formatos:
    # - antigo: {"ids": [...]}
    # - novo (monitorar_docs.py): lista de objetos [{id, lida, ...}]
    if isinstance(lidas_raw, list):
        ids_lidos = set(n.get("id","") for n in lidas_raw if n.get("lida", False))
    elif isinstance(lidas_raw, dict):
        ids_lidos = set(lidas_raw.get("ids", []))
    else:
        ids_lidos = set()

    docs_state = _load_json_safe(_DOCS_STATE)
    xsd_state  = _load_json_safe(_XSD_STATE)

    notifs_docs    = []
    notifs_schemas = []

    # ── Novos documentos do gov.br ──────────────────────────────────────
    NOMES_PAGINAS = {
        "rtc":      "RTC — Reforma Tributária do Consumo",
        "atual":    "Documentação Atual",
        "restrita": "Produção Restrita",
    }
    for pid, pdata in docs_state.get("paginas", {}).items():
        for link in pdata.get("links", []):
            if not link.get("novo"):
                continue
            nid = f"doc_{link.get('nome','')}"
            notifs_docs.append({
                "id":       nid,
                "tipo":     "documento",
                "titulo":   link.get("texto", link.get("nome", "Novo documento"))[:80],
                "subtitulo": NOMES_PAGINAS.get(pid, pid),
                "url":      link.get("url", ""),
                "nt":       link.get("nt", ""),
                "data":     link.get("data", ""),
                "lida":     nid in ids_lidos,
            })

    # ── Novo schema XSD ─────────────────────────────────────────────────
    if xsd_state:
        nid = f"xsd_{xsd_state.get('ultimo_zip','')}"
        notifs_schemas.append({
            "id":        nid,
            "tipo":      "schema",
            "titulo":    f"Schemas XSD atualizados — v{xsd_state.get('versao','?')}",
            "subtitulo": f"Data do arquivo: {xsd_state.get('data_xsd','?')}",
            "arquivo":   xsd_state.get("ultimo_zip", ""),
            "data":      xsd_state.get("atualizado_em", ""),
            "schemas":   xsd_state.get("schemas_instalados", {}),
            "lida":      nid in ids_lidos,
        })

    total_nao_lidas = sum(1 for n in notifs_docs + notifs_schemas if not n["lida"])

    return {
        "total":               total_nao_lidas,
        "docs":                notifs_docs,
        "schemas":             notifs_schemas,
        "ultima_verificacao":  docs_state.get("ultima_verificacao", "—"),
        "ultima_xsd":          xsd_state.get("atualizado_em", "—"),
    }

def _marcar_lidas():
    """Marca todas as notificações como lidas — suporta formato lista e dict."""
    dados = _get_notificacoes()
    todos_ids = set(
        [n["id"] for n in dados.get("docs", [])] +
        [n["id"] for n in dados.get("schemas", [])]
    )
    # Ler arquivo existente e preservar notificações do monitorar_docs.py
    lidas_raw = _load_json_safe(_NOTIF_LIDAS)
    if isinstance(lidas_raw, list):
        # Formato novo: lista de objetos — marcar todos como lidos
        for item in lidas_raw:
            item["lida"] = True
        # Adicionar IDs do servidor que ainda não estão na lista
        ids_na_lista = {n.get("id") for n in lidas_raw}
        for nid in todos_ids:
            if nid not in ids_na_lista:
                lidas_raw.append({"id": nid, "lida": True})
        novo = lidas_raw
    else:
        # Formato antigo: dict com "ids"
        novo = {"ids": list(todos_ids), "em": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _NOTIF_LIDAS.parent.mkdir(exist_ok=True)
    _NOTIF_LIDAS.write_text(json.dumps(novo, ensure_ascii=False), encoding="utf-8")

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): pass
    def _send(self,code,body,ct="application/json"):
        b=body.encode() if isinstance(body,str) else body
        self.send_response(code); self.send_header("Content-Type",ct); self.send_header("Content-Length",len(b))
        self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type"); self.send_header("X-Content-Type-Options","nosniff")
        self.end_headers(); self.wfile.write(b)
    def do_OPTIONS(self): self._send(204,b"")
    def _get_ip(self): return self.headers.get("X-Forwarded-For",self.client_address[0]).split(",")[0].strip()
    def do_GET(self):
        path=urlparse(self.path).path
        if path in ("/","/index.html"):
            f=BASE/"static/index.html"; self._send(200,f.read_bytes(),"text/html; charset=utf-8")
        elif path=="/standalone":
            f=BASE/"static/validador-nfse-standalone.html"
            if f.exists(): self._send(200,f.read_bytes(),"text/html; charset=utf-8")
            else: self._send(404,b'{"erro":"standalone nao encontrado"}')
        elif path.startswith("/static/") and path.endswith(".json"):
            # Servir JSONs de dados (leiaute, rejeições)
            fname = path.split("/")[-1]
            f = BASE / "static" / fname
            if f.exists(): self._send(200,f.read_bytes(),"application/json; charset=utf-8")
            else: self._send(404,b'{"erro":"arquivo nao encontrado"}')
        elif path=="/api/leiaute":
            self._send(200,json.dumps(TAB_LEIAUTE_FULL,ensure_ascii=False).encode())
        elif path=="/api/rejeicoes":
            self._send(200,json.dumps(TAB_REJEICOES_FULL,ensure_ascii=False).encode())
        elif path=="/api/tabelas": self._send(200,json.dumps(TAB_TODAS,ensure_ascii=False).encode())
        elif path=="/api/cidades": self._send(200,json.dumps(TAB_CIDADES,ensure_ascii=False).encode())
        elif path=="/api/paises":  self._send(200,json.dumps(TAB_PAISES,ensure_ascii=False).encode())
        elif path=="/api/health":
            self._send(200,json.dumps({"status":"ok","versao":"3.0","schemas":_SCH_STATUS,"tabelas":{"rejeicoes":len(TAB_REJ),"servicos":len(TAB_SERV),"cidades":len(TAB_CIDADES),"paises":len(TAB_PAISES)},"rate_limit":f"{RATE_LIMIT} req/{RATE_WINDOW}s por IP","xxe_protection":True,"max_body_mb":MAX_BODY_BYTES//1024//1024},ensure_ascii=False).encode())
        elif path=="/api/reload-status":
            self._send(200, json.dumps({
                "em_andamento": _RELOAD_STATUS["em_andamento"],
                "ultima_recarga": _RELOAD_STATUS["ultima"],
                "historico": _RELOAD_STATUS["historico"][-5:],
                "schemas_ok": [k for k,v in _SCH_STATUS.items() if v=="ok"],
                "schemas_erro": {k:v for k,v in _SCH_STATUS.items() if v!="ok"},
            }, ensure_ascii=False).encode())
        elif path=="/api/status":
            uptime_s = int(time.time() - _START_TIME)
            h,m,sec = uptime_s//3600,(uptime_s%3600)//60,uptime_s%60
            self._send(200,json.dumps({
                "versao":"3.0",
                "status":"ok",
                "uptime_segundos":uptime_s,
                "uptime_fmt":f"{h}h {m}m {sec}s",
                "validacoes_sessao":_VALIDACOES_TOTAL,
                "schemas":_SCH_STATUS,
                "cache_schemas":len(_SCH),
                "tabelas":{"rejeicoes":len(TAB_REJ),"servicos":len(TAB_SERV),"cidades":len(TAB_CIDADES),"paises":len(TAB_PAISES)},
                "rate_limit":f"{RATE_LIMIT} req/{RATE_WINDOW}s por IP",
                "xxe_protection":True,
                "max_body_mb":MAX_BODY_BYTES//1024//1024,
                "forum_cache_topics":len(_FORUM_CACHE.get("topics",[])),
                "xsd_state": _load_json_safe(_XSD_STATE),
            },ensure_ascii=False).encode())
        elif path=="/api/nt-resumo":
            from urllib.parse import parse_qs as _pqs, urlparse as _up
            _qs = _pqs(_up(self.path).query)
            _url = _qs.get("url",[""])[0]
            _nid = _qs.get("id",["NT"])[0]
            _poll = _qs.get("poll",["0"])[0] == "1"
            if not _url:
                self._send(400,b'{"ok":false,"erro":"parametro url obrigatorio"}')
            elif _poll:
                # Polling: retorna status do job em andamento
                _jk = _url
                _job = _NT_JOBS.get(_jk)
                if not _job:
                    self._send(200,json.dumps({"status":"not_found"}).encode())
                elif _job["status"]=="running":
                    self._send(200,b'{"status":"running"}')
                else:
                    self._send(200,json.dumps({"status":_job["status"],"result":_job.get("result",{})}).encode())
            else:
                # Verificar cache primeiro
                _agora = time.time()
                if _url in _NT_CACHE and (_agora-_NT_CACHE[_url]["ts"])<_NT_CACHE_TTL:
                    self._send(200,json.dumps({"status":"done","result":{"ok":True,"resumo":_NT_CACHE[_url]["resumo"],"from_cache":True}}).encode())
                elif _url in _NT_JOBS and _NT_JOBS[_url]["status"]=="running":
                    self._send(200,b'{"status":"running"}')
                else:
                    # Iniciar job em thread separada
                    _NT_JOBS[_url] = {"status":"running","result":None}
                    def _run_job(url=_url, nid=_nid):
                        res = _analisar_nt_gemini(url, nid)
                        _NT_JOBS[url] = {"status":"done" if res.get("ok") else "error","result":res}
                    threading.Thread(target=_run_job, daemon=True).start()
                    self._send(200,b'{"status":"running"}')
        elif path=="/api/monitorar-docs":
            # Roda monitorar_docs.py em background e retorna status
            import subprocess as _sp
            _script = BASE / "monitorar_docs.py"
            if not _script.exists():
                self._send(404, b'{"ok":false,"erro":"monitorar_docs.py nao encontrado"}')
            else:
                def _rodar_monitor():
                    try:
                        import importlib.util as _ilu, traceback as _tb
                        _spec = _ilu.spec_from_file_location("monitorar_docs", str(_script))
                        _mod  = _ilu.module_from_spec(_spec)
                        _spec.loader.exec_module(_mod)
                        # Chamar função principal
                        if hasattr(_mod, "_executar_como_modulo"):
                            _mod._executar_como_modulo()
                        elif hasattr(_mod, "main"):
                            _mod.main()
                    except Exception as ex:
                        print(f"[monitor] erro: {_tb.format_exc()}")
                threading.Thread(target=_rodar_monitor, daemon=True).start()
                self._send(200, b'{"ok":true,"msg":"Monitor iniciado em background"}')
        elif path=="/api/docs":
            # Serve docs_dynamic.json gerado pelo monitorar_docs.py
            if _DOCS_DYNAMIC.exists():
                self._send(200, _DOCS_DYNAMIC.read_bytes())
            else:
                self._send(200, json.dumps({
                    "ultima_verificacao": "—",
                    "nts": [], "total": 0, "novas": [],
                    "msg": "Execute monitorar_docs.py para gerar os dados"
                }, ensure_ascii=False).encode())
        elif path=="/api/forum":
            self._send(200,json.dumps(_get_forum_topics(),ensure_ascii=False).encode())
        elif path=="/api/notificacoes":
            self._send(200,json.dumps(_get_notificacoes(),ensure_ascii=False).encode())
        elif path=="/api/notificacoes/marcar-lidas":
            _marcar_lidas()
            self._send(200,b'{"ok":true}')

        elif path=="/api/check-update":
            # Verifica versão no GitHub e retorna se há atualização
            import urllib.request as _ur, json as _js
            try:
                _url = "https://raw.githubusercontent.com/XMLVariavel/nfse-validador/main/versao.json"
                _req = _ur.Request(_url, headers={"User-Agent":"NFS-e-Updater/1.0"})
                with _ur.urlopen(_req, timeout=8) as _r:
                    _remote = _js.loads(_r.read())
                _local_file = BASE / "versao.json"
                _local = _js.loads(_local_file.read_text(encoding="utf-8")) if _local_file.exists() else {}
                _rv = _remote.get("versao","0")
                _lv = _local.get("versao","0")
                _has_update = _rv != _lv
                self._send(200, _js.dumps({
                    "tem_atualizacao": _has_update,
                    "versao_local": _lv,
                    "versao_remota": _rv,
                    "data_remota": _remote.get("data",""),
                }).encode())
            except Exception as _ex:
                self._send(200, json.dumps({"tem_atualizacao": False, "erro": str(_ex)}).encode())

        elif path=="/api/aplicar-update":
            # Baixa e aplica arquivos atualizados do GitHub
            import urllib.request as _ur, json as _js, shutil as _sh, threading as _th
            _ARQUIVOS = [
                ("static/index.html",  BASE.parent / "static" / "index.html"),
                ("server.py",          BASE / "server.py"),
                ("versao.json",        BASE.parent / "versao.json"),
                ("monitorar_docs.py",  BASE / "monitorar_docs.py"),
            ]
            _resultados = []
            def _baixar_e_aplicar():
                for _rel, _dst in _ARQUIVOS:
                    try:
                        _url = f"https://raw.githubusercontent.com/XMLVariavel/nfse-validador/main/{_rel}"
                        _req = _ur.Request(_url, headers={"User-Agent":"NFS-e-Updater/1.0"})
                        with _ur.urlopen(_req, timeout=15) as _r:
                            _conteudo = _r.read()
                        _dst.parent.mkdir(parents=True, exist_ok=True)
                        _dst.write_bytes(_conteudo)
                        _resultados.append({"arquivo": _rel, "ok": True})
                        print(f"[update] {_rel} atualizado")
                    except Exception as _ex:
                        _resultados.append({"arquivo": _rel, "ok": False, "erro": str(_ex)})
                        print(f"[update] ERRO {_rel}: {_ex}")
            _t = _th.Thread(target=_baixar_e_aplicar, daemon=True)
            _t.start()
            _t.join(timeout=60)
            _ok = all(r["ok"] for r in _resultados)
            self._send(200, _js.dumps({"ok": _ok, "arquivos": _resultados}).encode())

        else: self._send(404,b'{"erro":"nao encontrado"}')
    def do_POST(self):
        path=urlparse(self.path).path
        if path!="/api/validar": self._send(404,b'{"erro":"endpoint nao encontrado"}'); return
        ip=self._get_ip()
        if not _rate_ok(ip): self._send(429,json.dumps({"erro":f"Muitas requisições. Limite: {RATE_LIMIT} req/{RATE_WINDOW}s."}).encode()); return
        length=int(self.headers.get("Content-Length",0))
        if length>MAX_BODY_BYTES: self._send(413,json.dumps({"erro":f"Payload muito grande. Máximo: {MAX_BODY_BYTES//1024//1024} MB."}).encode()); return
        body=self.rfile.read(length)
        if not body: self._send(400,b'{"erro":"body vazio"}'); return
        # Verificar se há schemas novos para recarregar (custo ~1 stat())
        _verificar_sentinel()
        try:
            result=processar(body); code=200
            global _VALIDACOES_TOTAL; _VALIDACOES_TOTAL += 1
            self._send(code,json.dumps(result,ensure_ascii=False).encode())
        except Exception as ex:
            self._send(500,json.dumps({"erro":str(ex)}).encode())

if __name__=="__main__":
    import os as _os, sys as _sys, io as _io
    # Forcar UTF-8 globalmente (evita UnicodeEncodeError no Windows)
    _os.environ['PYTHONUTF8'] = '1'
    if hasattr(_sys.stdout, 'buffer'):
        try:
            _sys.stdout = _io.TextIOWrapper(_sys.stdout.buffer, encoding='utf-8', errors='replace')
            _sys.stderr = _io.TextIOWrapper(_sys.stderr.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass
    HOST, PORT = "0.0.0.0", 8000
    try:
        print(f"NFS-e Validador v3.1 | http://{HOST}:{PORT}", flush=True)
    except Exception:
        pass
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()
