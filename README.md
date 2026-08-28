# Validador NFS-e Nacional v3.19.0 — Central Interna de Suporte DPS

Interface web profissional para validação de **DPS**, **NFS-e**, **CNC** e **TecnoNFSeNacional (TX2)**.

## Início rápido — Sistema com Backend

```bash
# Dependência: apenas lxml (nativo Python)
pip install lxml

# Iniciar o servidor
python server.py

# Abrir no navegador
# http://localhost:8000
```

> **Não precisa de FastAPI, uvicorn ou qualquer outro pacote.**  
> O servidor usa `http.server` nativo do Python 3.

## Início rápido — Standalone (sem instalação)

A rotina principal é o backend local. A antiga modalidade standalone só deve ser anunciada quando o arquivo estiver presente e validado no build.

O sistema é destinado aos **analistas de suporte**, para investigação de erros de DPS da NFS-e Nacional. Não transmite documentos ao SEFAZ e não é uma interface para clientes finais.

---

## Formatos suportados

| Formato | Elemento raiz | Schema XSD | Versões |
|---------|--------------|-----------|---------|
| DPS Nacional | `<DPS>` | `DPS_v1.01.xsd` | 1.00, 1.01 |
| NFS-e Nacional | `<NFSe>` | `NFSe_v1.01.xsd` | 1.00, 1.01 |
| CNC | `<CNC>` | `CNC_v1.00.xsd` | 1.00 |
| TecnoNFSeNacional | `<TecnoNFSeNacional>` | `TecnoNFSeNacional_v1.xsd` | 1 |

A detecção é **automática** — basta colar ou carregar o XML.

---

## O que valida

### Para todos os formatos
- XML bem-formado (well-formedness)
- Namespace correto (Nacional)
- CNPJ/CPF com dígito verificador (módulo 11)
- Código IBGE de município (5.571 municípios)
- Alíquota ISSQN (máx 5%, mín 2%)
- Retenção incompatível com imunidade/exportação
- Desconto incondicional ≥ valor do serviço
- IBS/CBS antes de 01/2026 (LC 214/2025)

### DPS/NFSe Nacional (validação XSD real com lxml)
- Schema XSD completo (lxml/libxml2)
- 448 rejeições oficiais (Anexo VI NT007)
- Tabela de serviços LC 116/2003 (337 códigos cTribNac)
- Código NBS (9 dígitos sem pontos)
- Regras de negócio: tpAmb, dCompet, serie, nDPS, tpEmit, cLocEmi, opSimpNac, regEspTrib, tpRetISSQN, tribISSQN, indOp, cLocPrestacao

### TecnoNFSeNacional / TX2
- Schema XSD Tecnospeed (`TecnoNFSeNacional_v1.xsd`)
- CpfCnpjPrestador, CpfCnpjTomador, CpfCnpjIntermediário
- CodigoCidadeEmitente, CodigoCidadePrestacao (lookup IBGE)
- AliquotaISS, TipoTributacaoIss, TipoRetIss
- OptanteSimplesNacional, RegimeEspecialTributacao
- ValorServicos, DescontoIncondicionado
- CodigoNbs (formato 9 dígitos)
- PaisPrestador / PaisTomador (tabela ISO)
- SituacaoTributariaIbsCbs, ClassificacaoTributariaIbsCbs (vigência 2026)

---

## API

```
POST /api/validar      → body: XML bruto → JSON com ocorrências
GET  /api/tabelas      → JSON com rejeições + serviços + indOp
GET  /api/cidades      → JSON com 5571 municípios IBGE
GET  /api/paises       → JSON com 189 países ISO
GET  /api/health       → status do servidor e schemas
GET  /api/versao       → versão canônica do sistema
GET  /api/casos        → busca de casos internos de suporte
POST /api/casos        → cadastra caso interno de suporte
GET  /api/reload-status→ status da recarga de schemas
GET  /standalone       → somente se a versão offline estiver instalada
```

Exemplo cURL:
```bash
curl -X POST http://localhost:8000/api/validar \
  -H "Content-Type: application/xml" \
  --data-binary @minha_dps.xml
```

---

## Estrutura

```
sistema-nfse/
├── server.py                  ← Backend (http.server nativo, lxml)
├── README.md
│
├── static/
│   ├── index.html             ← Interface web principal
│   └── validador-nfse-standalone.html  ← Versão offline completa
│
├── schemas/
│   ├── v100/                  ← XSDs DPS/NFSe/CNC v1.00
│   ├── v101/                  ← XSDs DPS/NFSe v1.01 (patchados para libxml2)
│   └── tecno/                 ← TecnoNFSeNacional_v1.xsd
│
└── tabelas/
    ├── rejeicoes.json         ← 448 rejeições oficiais (Anexo VI NT007)
    ├── codigos_servico.json   ← 337 serviços cTribNac (LC 116/2003)
    ├── cidades_ibge.json      ← 5571 municípios IBGE
    ├── paises_iso.json        ← 189 países (SiglaISOPaises.txt)
    ├── indop_ibs_cbs.json     ← 36 códigos indOp IBS/CBS (Anexo VII)
    └── todas.json             ← consolidado para API
```

---

## Central interna de Soluções DPS

A aba **Soluções** permite pesquisar e registrar casos internos por E-code, campo, cenário, causa, solução, versão e referência técnica. Os casos não são publicados para clientes nem enviados ao fórum externo. O fórum aparece apenas como referência complementar na aba **Referências**.

A base inicial fica em `tabelas/casos_suporte.json`. Em uma próxima etapa, ela deve ser substituída por armazenamento com autenticação, perfis, aprovação de soluções, histórico e auditoria.

## Variáveis de execução

| Variável | Padrão | Função |
|---|---|---|
| `NFSE_HOST` | `127.0.0.1` | Endereço de escuta local |
| `NFSE_PORT` | `8000` | Porta do backend |
| `NFSE_ALLOWED_ORIGIN` | `http://127.0.0.1:8000` | Origem permitida para CORS |

Para uso em rede interna, configurar autenticação, TLS/reverse proxy e uma origem autorizada. Não expor o backend diretamente na internet.

## Notas técnicas

**Patch XSD:** O schema `tiposSimples_v1.01.xsd` usa padrões com âncoras `^...$`
incompatíveis com libxml2 (XSD 1.0). O arquivo foi patchado automaticamente
(`^0{0,4}\d{1,5}$` → `[0-9]{1,5}`). O original está preservado no histórico.

**Detecção automática:** O elemento raiz determina o formato:
- `<DPS>` + `xmlns="http://www.sped.fazenda.gov.br/nfse"` → DPS Nacional
- `<NFSe>` + namespace → NFS-e Nacional
- `<CNC>` → CNC Nacional
- `<TecnoNFSeNacional>` → TX2/Tecnospeed (sem namespace obrigatório)
