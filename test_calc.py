"""Testes do cálculo, com os números do print do Marfeel."""
import itertools

import numpy as np
import pandas as pd

import calc

DADOS = [
    ("HP-MANCHETE", 101787, 85772, 7.74), ("HP-TOPO DE HOME", 101788, 78526, 13.6),
    ("HP-TOPO DE HOME - Destaque de citação", 79899, 42958, 0.3), ("HP-DESTAQUES VOZES", 101788, 40088, 8.71),
    ("HP-MAIS LIDAS / MAIS COMENTADAS", 101788, 28993, 6.1), ("HP-OUTROS DESTAQUES", 101788, 22552, 6.28),
    ("HP-Shorts", 102322, 15192, 4.12), ("HP-POLÍTICA automática", 101788, 13676, 6.82),
    ("HP-TOPO DE HOME - Bom dia", 21111, 11724, 0.38), ("HP-VALE A LEITURA", 101788, 11007, 8.56),
    ("HP-MUNDO - automática", 101788, 8492, 3.03), ("HP-VOZES AUTOMÁTICO + ÚLTIMAS", 101788, 7272, 7.47),
    ("HP-DESTAQUES VOZES - Destaque de citação", 21111, 7174, 0.1), ("HP-ECONOMIA", 101788, 5454, 2.26),
    ("HP-PROGRAMAÇÃO YT", 101788, 4885, 2.93), ("HP-PARA ENTENDER", 101168, 4084, 2.67),
    ("HP-PIANO SOFT", 4217, 3436, 4.31), ("HP-PIANO SOFT - Chamadas OP", 101787, 3372, 0.06),
    ("HP-Reflexões", 131, 3, 0.0),
]
df = pd.DataFrame(DADOS, columns=calc.COLUNAS)
d = calc.preparar(df)
nomes = list(d["bloco"])


def total(ordem):
    return calc.resumo(calc.avaliar(d, ordem))["depois"]


# 1) Sem mexer em nada, o resultado é exatamente o de hoje (nenhum bloco ganha nem perde)
out0 = calc.avaliar(d, nomes)
assert np.allclose(out0["variacao"], 0)
hoje = out0["cliques_antes"].sum()
print(f"cliques hoje: {hoje:,.0f} (print: 394.660 x 7,09% = {394660 * 0.0709:,.0f})")
assert abs(hoje - 394660 * 0.0709) / hoje < 0.01

# 2) Seu exemplo: HP-Shorts vai para a posição do HP-TOPO DE HOME (2), quem estava lá desce uma posição
ordem = [n for n in nomes if n != "HP-Shorts"]
ordem.insert(1, "HP-Shorts")
r = calc.resumo(calc.avaliar(d, ordem))
print(f"Shorts para a posição 2: saldo {r['saldo']:+,.0f} ({r['saldo_pct']:+.1f}%) | ganho {r['ganho']:+,.0f} | perda {r['perda']:+,.0f}")
assert r["saldo"] < 0 and r["ganho"] > 0 and r["perda"] < 0
assert abs(r["ganho"] + r["perda"] - r["saldo"]) < 1e-6

# 3) Bloco com público pequeno nunca passa do público elegível dele, mesmo subindo para o topo
ordem = ["HP-TOPO DE HOME - Bom dia"] + [n for n in nomes if n != "HP-TOPO DE HOME - Bom dia"]
o = calc.avaliar(d, ordem).set_index("bloco")
assert o.loc["HP-TOPO DE HOME - Bom dia", "visiveis_depois"] == 21111
print("teto de público: ok")

# 4) Otimização: nunca fica pior que hoje, respeita os fixos e é uma ordem válida
for fixos in ([], ["HP-MANCHETE"], ["HP-MANCHETE", "HP-TOPO DE HOME"], nomes[:5]):
    nova = calc.otimizar(d, fixos)
    assert sorted(nova) == sorted(nomes)
    for f in fixos:
        assert nova.index(f) == nomes.index(f), f"{f} saiu do lugar"
    assert total(nova) >= hoje - 1e-6
    r = calc.resumo(calc.avaliar(d, nova))
    movidos = int((calc.avaliar(d, nova)["pos_antes"] != calc.avaliar(d, nova)["pos_depois"]).sum())
    print(f"fixos={len(fixos)}: saldo {r['saldo']:+,.0f} ({r['saldo_pct']:+.1f}%), {movidos} blocos mudam de lugar")

# 5) Tudo fixo ou só um livre: nada muda
assert calc.otimizar(d, nomes) == nomes
assert calc.otimizar(d, nomes[1:]) == nomes

# 6) A otimização é mesmo a melhor: confere contra testar TODAS as ordens (tabela pequena, 7 blocos)
pequena = calc.preparar(df.iloc[[0, 1, 3, 4, 6, 9, 11]])
nm = list(pequena["bloco"])
melhor = max(calc.resumo(calc.avaliar(pequena, list(p)))["depois"] for p in itertools.permutations(nm))
achada = calc.resumo(calc.avaliar(pequena, calc.otimizar(pequena)))["depois"]
assert achada >= melhor - len(nm) * calc.GANHO_MINIMO, (achada, melhor)
print(f"otimização vs todas as {len(list(itertools.permutations(nm)))} ordens: {achada:,.0f} vs {melhor:,.0f}")

# 7) Com fixos, também confere contra todas as ordens que mantêm os fixos
fixos = {nm[0]}
melhor = max(calc.resumo(calc.avaliar(pequena, [nm[0]] + list(p)))["depois"]
             for p in itertools.permutations(nm[1:]))
achada = calc.resumo(calc.avaliar(pequena, calc.otimizar(pequena, fixos)))["depois"]
assert achada >= melhor - len(nm) * calc.GANHO_MINIMO, (achada, melhor)
print("otimização com fixos: ok")

# 8) A coluna `posicao` manda na ordem; posição em branco vai para o fim
com_pos = df.copy()
com_pos["posicao"] = list(range(len(com_pos), 0, -1))   # ordem invertida de propósito
assert calc.preparar(com_pos)["bloco"].iloc[0] == "HP-Reflexões"
com_pos.loc[0, "posicao"] = None
assert calc.preparar(com_pos)["bloco"].iloc[-1] == "HP-MANCHETE"
print("coluna posição: ok")

print("TUDO OK")
