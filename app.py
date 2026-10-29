import hashlib
import hmac
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import calc
import leitura

try:
    from streamlit_sortables import sort_items   # arrastar e soltar
except ImportError:
    sort_items = None

load_dotenv()

st.set_page_config(page_title="Simulador de posições da home", layout="wide")


def ler_config(nome):
    """Lê do .env / variável de ambiente e, se não achar, dos Secrets do Streamlit."""
    valor = os.getenv(nome)
    if valor:
        return valor
    try:
        return st.secrets.get(nome)
    except Exception:
        return None


def exigir_senha():
    """Tela de senha: nada do app aparece (nem gasta a chave da OpenAI) sem a senha certa."""
    senha_certa = ler_config("APP_PASSWORD")
    if not senha_certa:
        st.error("Defina APP_PASSWORD (no .env ou nos Secrets do Streamlit) para liberar o app.")
        st.stop()
    if st.session_state.get("autenticado"):
        return
    st.title("Simulador de posições da home")
    senha = st.text_input("Senha", type="password")
    if senha:
        if hmac.compare_digest(senha.encode(), str(senha_certa).encode()):
            st.session_state["autenticado"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    st.stop()


exigir_senha()


def fmt(n, sinal=False):
    t = f"{n:+,.0f}" if sinal else f"{n:,.0f}"
    return t.replace(",", ".")


def mostrar_resultado(base, ordem):
    """Mostra quanto a nova ordem ganha e perde em cliques, bloco a bloco."""
    out = calc.avaliar(base, ordem)
    r = calc.resumo(out)

    c = st.columns(5)
    c[0].metric("Cliques hoje", fmt(r["antes"]))
    c[1].metric("Cliques depois", fmt(r["depois"]), f"{r['saldo_pct']:+.1f}%")
    c[2].metric("Ganho de quem sobe", fmt(r["ganho"], True))
    c[3].metric("Perda de quem desce", fmt(r["perda"], True))
    c[4].metric("Saldo", fmt(r["saldo"], True))

    tab = out.copy()
    tab["Mudança"] = ["—" if a == p else (f"↑ sobe {a - p}" if a > p else f"↓ desce {p - a}")
                      for a, p in zip(tab["pos_antes"], tab["pos_depois"])]
    tab = tab.rename(columns={"pos_depois": "Posição", "bloco": "Bloco", "cliques_antes": "Cliques hoje",
                              "cliques_depois": "Cliques depois", "variacao": "Variação"})
    for col in ["Cliques hoje", "Cliques depois", "Variação"]:
        tab[col] = tab[col].round(0).astype(int)
    tab = tab[["Posição", "Bloco", "Mudança", "Cliques hoje", "Cliques depois", "Variação"]]

    if (out["pos_antes"] == out["pos_depois"]).all():
        return False, tab
    st.dataframe(tab, width="stretch", hide_index=True)
    mudou = tab[tab["Mudança"] != "—"]
    st.bar_chart(mudou.set_index("Bloco")["Variação"], horizontal=True)
    return True, tab


st.title("Simulador de posições da home")
st.caption("Suba o print da tela de análise, confira a tabela e escolha: deixar o sistema calcular a melhor ordem "
           "ou testar você mesmo, arrastando os blocos.")

if "versao" not in st.session_state:
    st.session_state["versao"] = 0
if "reset_arrasto" not in st.session_state:
    st.session_state["reset_arrasto"] = 0
if "tabela" not in st.session_state:
    st.session_state["tabela"] = pd.DataFrame(columns=calc.COLUNAS)
if "total_print" not in st.session_state:
    st.session_state["total_print"] = 0.0

# ---------- 1. Leitura da imagem ----------
st.header("1. Print da tela")
arquivos = st.file_uploader("Imagem(ns) da tela", type=["png", "jpg", "jpeg", "webp"],
                            accept_multiple_files=True,
                            help="Se o print não coube numa imagem só, suba as partes juntas.")
api_key = ler_config("OPENAI_API_KEY") or st.sidebar.text_input("OPENAI_API_KEY", type="password")
modelo = st.sidebar.text_input("Modelo da OpenAI", value=ler_config("OPENAI_MODEL") or leitura.MODELO_PADRAO)

if arquivos and st.button("Ler a imagem"):
    if not api_key:
        st.error("Informe a OPENAI_API_KEY (no .env, nos Secrets ou na barra lateral).")
    else:
        with st.spinner("Lendo a tabela..."):
            try:
                tabela_lida, total = leitura.extrair([(a.getvalue(), a.type) for a in arquivos], api_key, modelo)
                if tabela_lida.empty:
                    st.error("Não encontrei nenhuma linha de bloco na imagem.")
                else:
                    st.session_state["tabela"] = tabela_lida
                    st.session_state["total_print"] = total
                    st.session_state["versao"] += 1   # força o editor a mostrar a tabela nova
            except Exception as e:
                st.error(f"Não consegui ler a imagem: {e}")

for a in arquivos or []:
    st.image(a, width="stretch")

# ---------- 2. Conferência ----------
st.header("2. Confira os dados")
st.caption("Corrija qualquer número lido errado. Você pode adicionar, apagar ou renomear linhas. "
           "A coluna **Posição na home** é a ordem em que os blocos aparecem na página: ela começa do mais visto "
           "para o menos visto, mas mude os números se a ordem real da sua home for outra.")
editada = st.data_editor(
    leitura.com_posicao(st.session_state["tabela"]),
    num_rows="dynamic", width="stretch", hide_index=True, key=f"editor_{st.session_state['versao']}",
    column_config={
        "posicao": st.column_config.NumberColumn("Posição na home", min_value=1, step=1, format="%d"),
        "bloco": st.column_config.TextColumn("Bloco"),
        "elegiveis": st.column_config.NumberColumn("Elegíveis", format="%d"),
        "visiveis": st.column_config.NumberColumn("Visíveis", format="%d"),
        "ctr": st.column_config.NumberColumn("Open rate (%)"),
    },
)
tabela = leitura.limpar_tabela(editada)

if len(tabela):
    soma_vis = tabela["visiveis"].sum()
    cliques_tot = (tabela["visiveis"] * tabela["ctr"] / 100).sum()
    total_print = st.session_state["total_print"]
    c1, c2 = st.columns(2)
    c1.metric("Soma de visíveis (tabela)", fmt(soma_vis),
              delta=f"{fmt(soma_vis - total_print, True)} vs total do print" if total_print else None)
    c2.metric("Cliques estimados na home", fmt(cliques_tot))
    if total_print:
        st.caption("Se a diferença contra o total do print for grande, alguma linha foi lida errada.")

if len(tabela) < 2:
    st.info("Preciso de pelo menos 2 blocos para simular.")
    st.stop()

base = calc.preparar(tabela)
nomes = list(base["bloco"])
assinatura = hashlib.md5("|".join(nomes).encode()).hexdigest()[:8]   # muda quando a tabela muda

# ---------- 3. Escolha do modo ----------
st.header("3. O que você quer fazer?")
modo = st.radio("Modo", ["Calcular a melhor ordem", "Testar movimentos arrastando os blocos"],
                horizontal=True, label_visibility="collapsed")

if modo == "Calcular a melhor ordem":
    st.caption("Escolha os blocos que **não podem sair do lugar** (por exemplo, a manchete). "
               "O sistema reorganiza todos os outros para render o máximo de cliques.")
    fixos = st.multiselect("Blocos fixos", nomes, default=nomes[:1], key=f"fixos_{assinatura}")
    nova = calc.otimizar(base, fixos)
    mexeu, _ = mostrar_resultado(base, nova)
    if not mexeu:
        st.success("Com esses blocos fixos, a ordem atual já é a melhor: nenhuma mudança compensa.")

else:
    st.caption("Arraste os blocos para a posição que quiser (o de cima é a posição 1). "
               "O resultado ao lado se atualiza a cada movimento: o que sobe ganha, o que desce perde.")
    esq, dir_ = st.columns([1, 1.6])
    with esq:
        rotulos = {f"{b}  ·  CTR {c:g}%": b for b, c in zip(base["bloco"], base["ctr"])}
        chave = f"{assinatura}_{st.session_state['versao']}_{st.session_state['reset_arrasto']}"
        if sort_items is not None:
            retorno = sort_items(list(rotulos), direction="vertical", key=f"arrasto_{chave}")
            valido = isinstance(retorno, list) and sorted(retorno) == sorted(rotulos)
            ordem = [rotulos[r] for r in retorno] if valido else nomes
        else:
            st.info("O arrastar e soltar não está disponível aqui. Mude os números da coluna **Nova posição**.")
            novo = st.data_editor(pd.DataFrame({"Bloco": nomes, "Nova posição": range(1, len(nomes) + 1)}),
                                  hide_index=True, disabled=["Bloco"], key=f"posicoes_{chave}")
            ordem = list(novo.sort_values("Nova posição", kind="stable")["Bloco"])
        if st.button("Voltar à ordem original"):
            st.session_state["reset_arrasto"] += 1
            st.rerun()
    with dir_:
        mexeu, _ = mostrar_resultado(base, ordem)
        if not mexeu:
            st.info("Arraste um bloco para uma nova posição para ver o efeito nos cliques.")

with st.expander("Como o cálculo funciona"):
    st.write(
        "Cada posição da home é vista por um número de pessoas: o valor de **Visíveis** do bloco que está lá hoje. "
        "Quando um bloco muda de posição, ele passa a ser visto pelo número de pessoas da posição nova "
        "(sem passar do público elegível dele) e mantém o próprio open rate. "
        "Cliques = visíveis × open rate. Quem sobe ganha cliques, quem desce perde, e o saldo é a soma de todos."
    )
    st.write("É uma estimativa feita só com os dados do print. Antes de mudar a home de vez, vale validar com um teste.")
