import hmac
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import calc
import leitura

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

st.title("Simulador de posições da home")
st.caption("Suba o print da tela de análise, confira a tabela lida e simule trocas de posição. "
           "Funciona com qualquer quantidade de blocos e com nomes novos.")


def fmt(n, sinal=False):
    t = f"{n:+,.0f}" if sinal else f"{n:,.0f}"
    return t.replace(",", ".")


if "versao" not in st.session_state:
    st.session_state["versao"] = 0
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
        st.error("Informe a OPENAI_API_KEY (no .env ou na barra lateral).")
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
st.caption("Corrija qualquer número lido errado. Você pode adicionar, apagar ou renomear linhas à vontade. "
           "Também dá para digitar a tabela inteira à mão.")
editada = st.data_editor(st.session_state["tabela"], num_rows="dynamic", width="stretch",
                         key=f"editor_{st.session_state['versao']}")
tabela = leitura.limpar_tabela(editada)

if len(tabela):
    soma_vis = tabela["visiveis"].sum()
    cliques_tot = (tabela["visiveis"] * tabela["ctr"] / 100).sum()
    c1, c2 = st.columns(2)
    total_print = st.session_state["total_print"]
    c1.metric("Soma de visíveis (tabela)", fmt(soma_vis),
              delta=f"{fmt(soma_vis - total_print, True)} vs total do print" if total_print else None)
    c2.metric("Cliques estimados na home", fmt(cliques_tot))
    if total_print:
        st.caption("Se a diferença contra o total do print for grande, alguma linha foi lida errada.")

if len(tabela) < 2:
    st.info("Preciso de pelo menos 2 blocos para simular.")
    st.stop()

# ---------- 3. Regras da simulação ----------
st.header("3. Como ler as posições")
c1, c2 = st.columns(2)
ordem_label = c1.radio("Qual é a ordem dos blocos na home?",
                       ["Do mais visto para o menos visto (como no print)", "Na ordem das linhas da tabela"])
base_home = c2.number_input("Acessos à home (base da visibilidade)", min_value=1,
                            value=int(calc.base_da_home(tabela) or 1),
                            help="Por padrão é o valor de elegíveis mais comum entre os blocos. Mude se souber o número exato.")

if ordem_label.startswith("Na ordem"):
    tabela = tabela.assign(posicao=range(1, len(tabela) + 1))
base = calc.preparar(tabela)

# ---------- 4. Simulação ----------
st.header("4. Simular uma mudança")
c1, c2, c3 = st.columns(3)
bloco = c1.selectbox("Bloco que vai se mover", base["bloco"])
pos_atual = int(base.loc[base["bloco"] == bloco, "posicao"].iloc[0])
destino = c2.number_input("Nova posição (1 = topo)", 1, len(base), min(2, len(base)))
modo_label = c3.radio("O que acontece com o bloco que estava lá?",
                      ["Desce uma posição", "Troca de lugar com o que sobe"])
modo = "descer" if modo_label.startswith("Desce") else "trocar"
ajuste = st.slider("Ajuste do CTR do bloco movido (%)", -50, 50, 0,
                   help="Na prática o CTR costuma mudar com a posição. Use isso para testar cenários mais otimista ou mais conservador.")

if destino == pos_atual:
    st.warning("O bloco já está nessa posição.")
else:
    out = calc.simular(base, bloco, destino, modo, ajuste, base_home)
    r = calc.resumo(out)
    m1, m2, m3 = st.columns(3)
    m1.metric("Cliques antes", fmt(r["antes"]))
    m2.metric("Cliques depois", fmt(r["depois"]))
    m3.metric("Saldo", fmt(r["saldo"], True), f"{r['saldo_pct']:+.1f}%")

    mov = out[out["bloco"] == bloco].iloc[0]
    st.write(f"**{bloco}** vai da posição {int(mov.pos_antes)} para a {int(mov.pos_depois)} e passa de "
             f"{fmt(mov.cliques_antes)} para {fmt(mov.cliques_depois)} cliques ({fmt(mov.variacao, True)}).")
    st.dataframe(out.round(2), width="stretch", hide_index=True)
    st.bar_chart(out.set_index("bloco")[["cliques_antes", "cliques_depois"]])

# ---------- 5. Melhores movimentos ----------
st.header("5. Quais movimentos mais valem a pena?")
fixos = st.multiselect("Blocos que não podem sair do lugar", base["bloco"])
if st.button("Testar todos os movimentos"):
    rk = calc.ranking(base, modo, ajuste, top=10, ignorar=fixos, base_home=base_home)
    st.dataframe(rk.round(2), width="stretch", hide_index=True)

st.caption("Aviso: a visibilidade de cada posição vem do print; o CTR de cada bloco é mantido ao mover. "
           "É uma estimativa, e o resultado real deve ser validado com um teste.")
