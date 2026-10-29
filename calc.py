"""Lógica de cálculo do simulador de posições da home.

Ideia central (simples):
- Cada POSIÇÃO da home tem uma taxa de visibilidade: visíveis / base da home.
  A base da home é o número de acessos à home (o "elegível" típico, ~101 mil), e não o
  elegível do bloco, porque alguns blocos só aparecem para uma parte do público.
- Cada BLOCO tem a sua taxa de clique (open rate), que é do conteúdo e acompanha o bloco.
- Quando um bloco muda de posição, ele passa a ter a visibilidade da posição nova,
  mas mantém o próprio CTR.   cliques = elegíveis do bloco x visibilidade da posição x CTR
"""
import pandas as pd

COLUNAS = ["bloco", "elegiveis", "visiveis", "ctr"]


def base_da_home(d: pd.DataFrame) -> float:
    """Acessos à home: o valor de elegíveis mais comum entre os blocos (mediana)."""
    return float(d["elegiveis"].median())


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Ordena por posição (se existir) ou por visíveis (como no print) e numera as posições."""
    d = df.copy()
    for c in ["elegiveis", "visiveis", "ctr"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    if "posicao" in d.columns and d["posicao"].notna().all():
        d = d.sort_values("posicao")
    else:
        d = d.sort_values("visiveis", ascending=False)
    d = d.reset_index(drop=True)
    d["posicao"] = d.index + 1
    return d


def cliques(d: pd.DataFrame) -> pd.Series:
    return d["visiveis"] * d["ctr"] / 100


def simular(df, bloco, nova_posicao, modo="descer", ajuste_ctr_pct=0.0, base_home=None):
    """Move `bloco` para `nova_posicao` (1 = topo).

    modo="descer": quem estava no caminho desce uma posição (os demais ficam como estão).
    modo="trocar": o bloco que estava na posição de destino vai para a posição de origem.
    ajuste_ctr_pct: correção opcional no CTR do bloco movido (ex.: +10 ou -15).
    """
    d = preparar(df)
    nomes = list(d["bloco"])
    if bloco not in nomes:
        raise ValueError(f"Bloco '{bloco}' não encontrado.")
    i = nomes.index(bloco)
    j = int(nova_posicao) - 1

    nova_ordem = nomes.copy()
    if modo == "trocar":
        nova_ordem[i], nova_ordem[j] = nova_ordem[j], nova_ordem[i]
    else:
        nova_ordem.pop(i)
        nova_ordem.insert(j, bloco)

    # taxa de visibilidade de cada posição (da foto original), sobre a base da home
    base_home = base_home or base_da_home(d) or 1.0
    taxa_pos = (d["visiveis"] / base_home).clip(upper=1.0).tolist()

    base = d.set_index("bloco")
    linhas = []
    for pos_nova, nome in enumerate(nova_ordem):
        r = base.loc[nome]
        vis_novo = r["elegiveis"] * taxa_pos[pos_nova]
        ctr_novo = r["ctr"] * (1 + ajuste_ctr_pct / 100) if nome == bloco else r["ctr"]
        linhas.append({
            "bloco": nome,
            "pos_antes": int(r["posicao"]),
            "pos_depois": pos_nova + 1,
            "visiveis_antes": r["visiveis"],
            "visiveis_depois": round(vis_novo),
            "ctr": r["ctr"],
            "ctr_depois": ctr_novo,
            "cliques_antes": r["visiveis"] * r["ctr"] / 100,
            "cliques_depois": vis_novo * ctr_novo / 100,
        })
    out = pd.DataFrame(linhas).sort_values("pos_antes").reset_index(drop=True)
    out["variacao"] = out["cliques_depois"] - out["cliques_antes"]
    return out


def resumo(out: pd.DataFrame) -> dict:
    antes, depois = out["cliques_antes"].sum(), out["cliques_depois"].sum()
    return {
        "antes": antes,
        "depois": depois,
        "saldo": depois - antes,
        "saldo_pct": (depois - antes) / antes * 100 if antes else 0.0,
    }


def ranking(df, modo="descer", ajuste_ctr_pct=0.0, top=10, ignorar=(), base_home=None):
    """Testa todos os movimentos possíveis e devolve os de maior saldo de cliques."""
    d = preparar(df)
    linhas = []
    for _, r in d.iterrows():
        if r["bloco"] in ignorar:
            continue
        for p in range(1, len(d) + 1):
            if p == r["posicao"]:
                continue
            s = resumo(simular(d, r["bloco"], p, modo, ajuste_ctr_pct, base_home))
            linhas.append({"bloco": r["bloco"], "de": int(r["posicao"]), "para": p,
                           "saldo_cliques": s["saldo"], "saldo_pct": s["saldo_pct"]})
    return pd.DataFrame(linhas).sort_values("saldo_cliques", ascending=False).head(top).reset_index(drop=True)
