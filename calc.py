"""Cálculo do simulador de posições da home.

A ideia é simples:
- Cada POSIÇÃO da home é vista por um número de pessoas: o "Module Viewable" que o print mostra
  para o bloco que está lá hoje.
- Cada BLOCO tem o seu open rate (CTR), que é do conteúdo e acompanha o bloco quando ele muda de lugar.
- Quando um bloco muda de posição, ele passa a ser visto pelo número de pessoas da posição nova,
  mas nunca por mais gente do que o público elegível dele.
      cliques = visíveis da posição  x  CTR do bloco
"""
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

COLUNAS = ["bloco", "elegiveis", "visiveis", "ctr"]

# Na busca pela melhor ordem, um bloco só sai do lugar se isso render pelo menos este tanto de cliques.
# Evita sugerir mexidas que não valem a pena (e desempata a favor de não mexer).
GANHO_MINIMO = 1.0


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Põe os blocos na ordem das posições e numera de 1 em diante.

    Se a tabela tiver a coluna `posicao`, ela manda; blocos sem posição vão para o fim,
    do mais visto para o menos visto. Sem a coluna, a ordem é do mais visto para o menos visto.
    """
    d = df.copy()
    for c in ["elegiveis", "visiveis", "ctr"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    if "posicao" in d.columns:
        pos = pd.to_numeric(d["posicao"], errors="coerce")
        d["_pos"] = pos.fillna((pos.max() if pos.notna().any() else 0) + 1)
        d = d.sort_values(["_pos", "visiveis"], ascending=[True, False], kind="stable").drop(columns="_pos")
    else:
        d = d.sort_values("visiveis", ascending=False, kind="stable")
    d = d.reset_index(drop=True)
    d["posicao"] = d.index + 1
    return d


def _teto(d: pd.DataFrame) -> np.ndarray:
    """Máximo de pessoas que podem ver cada bloco (o público elegível dele)."""
    return np.maximum(d["elegiveis"].to_numpy(float), d["visiveis"].to_numpy(float))


def avaliar(d: pd.DataFrame, nova_ordem: list) -> pd.DataFrame:
    """Calcula os cliques de cada bloco se a home ficasse na `nova_ordem` (lista de nomes, topo primeiro).

    `d` precisa ter passado por `preparar`.
    """
    nomes = list(d["bloco"])
    if sorted(nova_ordem) != sorted(nomes):
        raise ValueError("A nova ordem precisa ter exatamente os mesmos blocos da tabela.")
    pos_atual = {n: i for i, n in enumerate(nomes)}
    vis_posicao = d["visiveis"].to_numpy(float)
    teto = _teto(d)

    linhas = []
    for p, nome in enumerate(nova_ordem):
        i = pos_atual[nome]
        vis_novo = min(vis_posicao[p], teto[i])
        ctr = float(d.at[i, "ctr"])
        linhas.append({
            "bloco": nome,
            "pos_antes": i + 1,
            "pos_depois": p + 1,
            "visiveis_antes": float(d.at[i, "visiveis"]),
            "visiveis_depois": float(vis_novo),
            "ctr": ctr,
            "cliques_antes": float(d.at[i, "visiveis"]) * ctr / 100,
            "cliques_depois": float(vis_novo) * ctr / 100,
        })
    out = pd.DataFrame(linhas).sort_values("pos_depois").reset_index(drop=True)
    out["variacao"] = out["cliques_depois"] - out["cliques_antes"]
    return out


def resumo(out: pd.DataFrame) -> dict:
    antes, depois = out["cliques_antes"].sum(), out["cliques_depois"].sum()
    return {
        "antes": antes,
        "depois": depois,
        "saldo": depois - antes,
        "saldo_pct": (depois - antes) / antes * 100 if antes else 0.0,
        "ganho": out.loc[out["variacao"] > 0, "variacao"].sum(),   # soma de quem ganha cliques
        "perda": out.loc[out["variacao"] < 0, "variacao"].sum(),   # soma de quem perde cliques (negativo)
    }


def otimizar(d: pd.DataFrame, fixos=()) -> list:
    """Melhor ordem possível, mantendo os blocos `fixos` exatamente onde estão.

    Devolve a lista de nomes na nova ordem. É um problema de "quem fica em qual posição" resolvido de
    forma exata (algoritmo húngaro), sem tentativa e erro.
    """
    nomes = list(d["bloco"])
    fixos = set(fixos)
    livres = [i for i, n in enumerate(nomes) if n not in fixos]
    if len(livres) < 2:
        return nomes

    vis_posicao = d["visiveis"].to_numpy(float)[livres]
    teto = _teto(d)[livres]
    ctr = d["ctr"].to_numpy(float)[livres] / 100

    # valor[a, c] = cliques do bloco livre `a` se ficar na posição livre `c`
    valor = np.minimum(vis_posicao[None, :], teto[:, None]) * ctr[:, None]
    valor = valor + GANHO_MINIMO * np.eye(len(livres))   # pequeno bônus por ficar onde já está

    linhas, colunas = linear_sum_assignment(valor, maximize=True)
    nova = list(nomes)
    for a, c in zip(linhas, colunas):
        nova[livres[c]] = nomes[livres[a]]
    return nova
