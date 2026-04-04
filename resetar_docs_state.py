"""
Execute na pasta sistema-nfse para forçar o monitorar_docs.py
a reimportar todos os documentos com os nomes corretos.

python resetar_docs_state.py
"""
import json
from pathlib import Path

f = Path("tabelas/docs_state.json")
if f.exists():
    dados = json.loads(f.read_text(encoding="utf-8"))
    # Limpar grupos de todas as páginas para redetectar
    for pid in dados.get("paginas", {}):
        dados["paginas"][pid]["grupos"] = []
        dados["paginas"][pid]["nts"] = []
    dados["nts_conhecidas"] = []
    f.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    print("✔ docs_state.json resetado — execute monitorar_docs.py --force para reimportar")
else:
    print("Arquivo não encontrado — não é necessário resetar")
