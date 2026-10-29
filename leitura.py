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
    d = d[calc.COLUNAS]
    d["bloco"] = d["bloco"].fillna("").astype(str).str.strip()
    d = d[d["bloco"] != ""].copy()
    for c in ["elegiveis", "visiveis", "ctr"]:
        d[c] = d[c].map(para_numero)
    vistos, nomes = {}, []
    for n in d["bloco"]:
        vistos[n] = vistos.get(n, 0) + 1
        nomes.append(n if vistos[n] == 1 else f"{n} ({vistos[n]})")
    d["bloco"] = nomes
    return d.reset_index(drop=True)


def extrair(imagens, api_key: str, modelo: str | None = None):
    """imagens: lista de (bytes, tipo_mime). Devolve (tabela, total_visiveis_do_print).

    Aceita várias imagens (ex.: print dividido em duas partes); linhas idênticas repetidas
    entre as imagens são descartadas.
    """
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    modelo = modelo or os.getenv("OPENAI_MODEL", "gpt-4o")
    partes, total_visiveis = [], 0.0

    for conteudo, mime in imagens:
        b64 = base64.b64encode(conteudo).decode()
        resp = client.chat.completions.create(
            model=modelo,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]}],
        )
        dados = json.loads(resp.choices[0].message.content)
        total_visiveis = max(total_visiveis, para_numero(dados.get("total_visiveis")))
        partes.append(pd.DataFrame(dados.get("blocos", [])))

    if not partes:
        return pd.DataFrame(columns=calc.COLUNAS), 0.0

    juntas = pd.concat(partes, ignore_index=True)
    for c in ["elegiveis", "visiveis", "ctr"]:
        if c in juntas.columns:
            juntas[c] = juntas[c].map(para_numero)
    juntas = juntas.drop_duplicates(subset=[c for c in calc.COLUNAS if c in juntas.columns])
    return limpar_tabela(juntas), total_visiveis
