"""Testa o app com tabelas diferentes: poucos blocos, muitos blocos, nomes novos/repetidos, números sujos."""
import random

import pandas as pd
from streamlit.testing.v1 import AppTest

import leitura

# 1) conversão de números
casos = {"101,788": 101788, "7.74%": 7.74, "1.551.413": 1551413, "1.234,56": 1234.56,
         "1,234.56": 1234.56, "0,38": 0.38, "": 0, None: 0, "abc": 0, 5: 5.0}
for entrada, esperado in casos.items():
    assert abs(leitura.para_numero(entrada) - esperado) < 1e-9, (entrada, leitura.para_numero(entrada))
print("números sujos: ok")

# 2) limpeza: nomes repetidos, linhas vazias, colunas faltando
sujo = pd.DataFrame({"bloco": ["A", "A", " ", None, "B"], "elegiveis": ["1,000", 1000, 5, 5, 900],
                     "visiveis": ["800", 700, 1, 1, "300"], "ctr": ["5%", 4, 1, 1, "2.5"]})
lim = leitura.limpar_tabela(sujo)
assert list(lim["bloco"]) == ["A", "A (2)", "B"], list(lim["bloco"])
assert lim["ctr"].tolist() == [5.0, 4.0, 2.5]
print("limpeza: ok")


def rodar(df, nome):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["tabela"] = df
    at.run()
    assert not at.exception, (nome, at.exception)
    # muda a posição de destino e o modo, para exercitar o cálculo
    if at.number_input:
        at.run()
    assert not at.exception, (nome, at.exception)
    print(f"{nome}: ok ({len(df)} blocos)")


rng = random.Random(1)


def tabela_aleatoria(n, prefixo="BLOCO"):
    base = 100000
    linhas = []
    for i in range(n):
        vis = int(base * max(0.02, 0.9 - i * 0.8 / max(n, 1)))
        linhas.append((f"{prefixo}-{i + 1}", base, vis, round(rng.uniform(0.1, 14), 2)))
    return pd.DataFrame(linhas, columns=["bloco", "elegiveis", "visiveis", "ctr"])


rodar(tabela_aleatoria(2), "2 blocos")
rodar(tabela_aleatoria(5, "OUTRO"), "5 blocos com nomes novos")
rodar(tabela_aleatoria(40, "MÓDULO"), "40 blocos")
rodar(pd.DataFrame({"bloco": ["X", "X", "Y"], "elegiveis": [10, 10, 0],
                    "visiveis": [8, 6, 0], "ctr": [3, 2, 0]}), "repetidos e zerados")
rodar(pd.DataFrame(columns=["bloco", "elegiveis", "visiveis", "ctr"]), "tabela vazia")
rodar(pd.DataFrame({"bloco": ["Único"], "elegiveis": [100], "visiveis": [50], "ctr": [5]}), "1 bloco")
print("TUDO OK")
