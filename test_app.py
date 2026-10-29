"""Testa as telas do app com os números do print: modo automático, modo arrastar e caminho sem o componente."""
import os
import sys
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import calc
from test_calc import DADOS

os.environ["APP_PASSWORD"] = "teste"
TABELA = pd.DataFrame(DADOS, columns=calc.COLUNAS)
MODO_B = "Testar movimentos arrastando os blocos"


def abrir(tabela=TABELA):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["autenticado"] = True
    at.session_state["tabela"] = tabela
    return at.run()


def metricas(at):
    return {m.label: m.value for m in at.metric}


def numero(txt):
    return float(txt.replace(".", "").replace("+", "").replace("−", "-").replace("-", "-"))


# 1) Modo automático (padrão): manchete fixa por padrão, resultado positivo
at = abrir()
assert not at.exception, at.exception
m = metricas(at)
assert at.multiselect[0].value == ["HP-MANCHETE"], at.multiselect[0].value
assert numero(m["Saldo"]) > 0 and numero(m["Ganho de quem sobe"]) > 0 and numero(m["Perda de quem desce"]) < 0
print("modo automático:", {k: m[k] for k in ("Cliques hoje", "Cliques depois", "Saldo")})

# 2) Mudar os fixos recalcula (fixar mais blocos reduz o ganho possível)
saldo_1 = numero(m["Saldo"])
at.multiselect[0].set_value(["HP-MANCHETE", "HP-VALE A LEITURA", "HP-VOZES AUTOMÁTICO + ÚLTIMAS"]).run()
assert not at.exception, at.exception
saldo_3 = numero(metricas(at)["Saldo"])
assert 0 <= saldo_3 < saldo_1, (saldo_1, saldo_3)
print(f"fixando mais blocos: saldo {saldo_1:,.0f} -> {saldo_3:,.0f}")

# 3) Tudo fixo: avisa que não há o que melhorar
at.multiselect[0].set_value(list(TABELA["bloco"])).run()
assert not at.exception, at.exception
assert any("já é a melhor" in s.value for s in at.success), "deveria avisar que nada compensa"
print("tudo fixo: ok")

# 4) Modo arrastar, sem mexer: pede para arrastar
with patch("streamlit_sortables.sort_items", side_effect=lambda itens, **kw: list(itens)):
    at = abrir()
    at.radio[0].set_value(MODO_B).run()
    assert not at.exception, at.exception
    assert any("Arraste um bloco" in i.value for i in at.info)
    print("arrastar sem mexer: ok")

# 5) Modo arrastar com o seu exemplo: HP-Shorts vai para a posição 2
def shorts_para_2(itens, **kw):
    itens = list(itens)
    shorts = next(i for i in itens if i.startswith("HP-Shorts"))
    itens.remove(shorts)
    itens.insert(1, shorts)
    return itens

with patch("streamlit_sortables.sort_items", side_effect=shorts_para_2):
    at = abrir()
    at.radio[0].set_value(MODO_B).run()
    assert not at.exception, at.exception
    m = metricas(at)
    assert numero(m["Saldo"]) < 0 and numero(m["Ganho de quem sobe"]) > 0 and numero(m["Perda de quem desce"]) < 0
    print("Shorts para a posição 2:", {k: m[k] for k in ("Ganho de quem sobe", "Perda de quem desce", "Saldo")})

# 6) Componente devolvendo lixo (lista incompleta): o app ignora e mostra a ordem original
with patch("streamlit_sortables.sort_items", side_effect=lambda itens, **kw: ["qualquer coisa"]):
    at = abrir()
    at.radio[0].set_value(MODO_B).run()
    assert not at.exception, at.exception
    print("retorno inválido do componente: ok")

# 7) Sem o componente instalado: cai para a edição por números
with patch.dict(sys.modules, {"streamlit_sortables": None}):
    at = abrir()
    at.radio[0].set_value(MODO_B).run()
    assert not at.exception, at.exception
    assert any("não está disponível" in i.value for i in at.info)
    print("sem o componente: ok")

# 8) Coluna de posição editada: a ordem da tabela muda os cálculos
invertida = TABELA.copy()
invertida.insert(0, "posicao", range(len(invertida), 0, -1))
at = abrir(invertida)
assert not at.exception, at.exception
assert at.multiselect[0].value == ["HP-Reflexões"], at.multiselect[0].value   # o primeiro agora é o último da lista
print("coluna de posição: ok")

# 9) Tabelas de tamanhos diferentes nos dois modos
for n in (2, 3, 30):
    t = pd.DataFrame({"bloco": [f"B{i}" for i in range(n)], "elegiveis": [1000] * n,
                      "visiveis": [900 - i * (800 // n) for i in range(n)], "ctr": [1 + (i * 7) % 9 for i in range(n)]})
    for modo in ("Calcular a melhor ordem", MODO_B):
        at = abrir(t)
        at.radio[0].set_value(modo).run()
        assert not at.exception, (n, modo, at.exception)
print("tamanhos diferentes: ok")
print("TUDO OK")
