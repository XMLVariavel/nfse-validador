"""
Execute este script UMA VEZ na pasta sistema-nfse para corrigir
o arquivo tabelas/notificacoes_lidas.json que pode estar em formato inválido.

python corrigir_notificacoes.py
"""
import json
from pathlib import Path

f = Path("tabelas/notificacoes_lidas.json")
if f.exists():
    try:
        dados = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(dados, list):
            print(f"Arquivo já está no formato correto (lista com {len(dados)} itens)")
        elif isinstance(dados, dict):
            print("Convertendo formato antigo (dict) para novo (lista)...")
            nova_lista = [{"id": nid, "lida": True} for nid in dados.get("ids", [])]
            f.write_text(json.dumps(nova_lista, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"✔ Convertido: {len(nova_lista)} IDs preservados")
        else:
            print("Formato desconhecido — resetando arquivo")
            f.write_text("[]", encoding="utf-8")
    except Exception as e:
        print(f"Arquivo corrompido ({e}) — resetando...")
        f.write_text("[]", encoding="utf-8")
        print("✔ Resetado para lista vazia")
else:
    f.parent.mkdir(exist_ok=True)
    f.write_text("[]", encoding="utf-8")
    print("✔ Arquivo criado como lista vazia")

print("Pronto! Reinicie o servidor.")
