"""Leitura do print (via OpenAI) e limpeza da tabela.

Nada aqui depende de nomes ou quantidade de blocos: o que estiver na imagem vira linha da tabela.
"""
import base64
import json
import os

import pandas as pd

import calc

PROMPT = """Esta imagem é uma tabela de análise de módulos (blocos) da home de um site, com colunas
como Module Eligible, Module Viewable e Module Open Rate.
Leia TODAS as linhas de blocos que aparecem, sejam quantas forem, e devolva SOMENTE um JSON neste formato:
{"total_elegiveis": number, "total_visiveis": number, "total_open_rate": number,
 "blocos": [{"bloco": "nome exato como aparece", "elegiveis": number, "visiveis": number, "ctr": number}]}
Regras:
- números sem separador de milhar (101,788 vira 101788);
- ctr em porcentagem como número (7.74% vira 7.74);
- mantenha a ordem em que as linhas aparecem;
- não invente linhas e não pule linhas;
- se algum total do cabeçalho não aparecer, use 0."""


def para_numero(v) -> float:
    """Converte '101,788', '7.74%', '1.551.413' ou número em float. Se não der, devolve 0."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return 0.0 if pd.isna(v) else float(v)
    s = str(v).strip().replace("%", "").replace(" ", "")
    if not s:
        return 0.0
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):          # 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:                                     # 1,234.56
            s = s.replace(",", "")
    elif "," in s:
        ultimo = s.split(",")[-1]
        s = s.replace(",", "") if len(ultimo) == 3 else s.replace(",", ".")
    elif s.count(".") > 1:                        # 1.551.413
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def limpar_tabela(df: pd.DataFrame) -> pd.DataFrame:
    """Garante as 4 colunas, números de verdade, sem linhas sem nome e sem nomes repetidos."""
    d = df.copy()
    for c in calc.COLUNAS:
        if c not in d.columns:
            d[c] = "" if c == "bloco" else 0
    tem_posicao = "posicao" in d.columns
    d = d[calc.COLUNAS + (["posicao"] if tem_posicao else [])]
    d["bloco"] = d["bloco"].fillna("").astype(str).str.strip()
    d = d[d["bloco"] != ""].copy()
    for c in ["elegiveis", "visiveis", "ctr"]:
        d[c] = d[c].map(para_numero)
    if tem_posicao:   # posição em branco continua em branco (o cálculo põe esses blocos no fim)
        d["posicao"] = pd.to_numeric(d["posicao"], errors="coerce")
    vistos, nomes = {}, []
    for n in d["bloco"]:
        vistos[n] = vistos.get(n, 0) + 1
        nomes.append(n if vistos[n] == 1 else f"{n} ({vistos[n]})")
    d["bloco"] = nomes
    return d.reset_index(drop=True)


MODELO_PADRAO = "gpt-5.4-mini"
TOLERANCIA = 0.005   # 0,5% de diferença entre a soma das linhas e o total do cabeçalho


def _ler(client, modelo: str, b64: str, mime: str, esforco: str) -> dict:
    """Uma leitura da imagem. `detail: high` faz o modelo enxergar os números pequenos."""
    args = dict(
        model=modelo,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}},
        ]}],
    )
    if modelo.startswith("gpt-5"):
        args["reasoning_effort"] = esforco   # só a família gpt-5 aceita esse parâmetro
    resp = client.chat.completions.create(**args)
    return json.loads(resp.choices[0].message.content)


def _erro_totais(dados: dict) -> float:
    """Maior diferença relativa entre a soma das linhas e os totais do cabeçalho (0 = bate certinho)."""
    blocos = pd.DataFrame(dados.get("blocos", []))
    erros = []
    for coluna, chave in (("visiveis", "total_visiveis"), ("elegiveis", "total_elegiveis")):
        total = para_numero(dados.get(chave))
        if total > 0 and coluna in blocos.columns:
            erros.append(abs(blocos[coluna].map(para_numero).sum() - total) / total)
    return max(erros) if erros else 0.0


def com_posicao(df: pd.DataFrame) -> pd.DataFrame:
    """Garante a coluna `posicao` (primeira da tabela). Se faltar, assume a ordem do mais visto para o menos visto."""
    d = df.copy()
    if "posicao" not in d.columns:
        d.insert(0, "posicao", pd.to_numeric(d["visiveis"], errors="coerce").rank(ascending=False, method="first"))
    else:
        d = d[["posicao"] + [c for c in d.columns if c != "posicao"]]
    d["posicao"] = pd.to_numeric(d["posicao"], errors="coerce")
    return d.sort_values("posicao", kind="stable").reset_index(drop=True)


def extrair(imagens, api_key: str, modelo: str | None = None):
    """imagens: lista de (bytes, tipo_mime). Devolve (tabela, total_visiveis_do_print).

    Aceita várias imagens (ex.: print dividido em duas partes); linhas idênticas repetidas
    entre as imagens são descartadas.
    """
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    modelo = modelo or os.getenv("OPENAI_MODEL", MODELO_PADRAO)
    partes, total_visiveis = [], 0.0

    for conteudo, mime in imagens:
        b64 = base64.b64encode(conteudo).decode()
        dados = _ler(client, modelo, b64, mime, "low")
        # Autoconferência: com uma imagem só, a soma das linhas tem que bater com os totais do cabeçalho.
        # Se não bater, tenta de novo com mais esforço e fica com a leitura que mais se aproxima.
        if len(imagens) == 1 and _erro_totais(dados) > TOLERANCIA and modelo.startswith("gpt-5"):
            segunda = _ler(client, modelo, b64, mime, "high")
            if _erro_totais(segunda) < _erro_totais(dados):
                dados = segunda
        total_visiveis = max(total_visiveis, para_numero(dados.get("total_visiveis")))
        partes.append(pd.DataFrame(dados.get("blocos", [])))

    if not partes:
        return pd.DataFrame(columns=calc.COLUNAS), 0.0

    juntas = pd.concat(partes, ignore_index=True)
    for c in ["elegiveis", "visiveis", "ctr"]:
        if c in juntas.columns:
            juntas[c] = juntas[c].map(para_numero)
    juntas = juntas.drop_duplicates(subset=[c for c in calc.COLUNAS if c in juntas.columns])
    return com_posicao(limpar_tabela(juntas)), total_visiveis
