import streamlit as st
import pandas as pd
import plotly.express as px

from datetime import date, datetime, timedelta
from database import (
    conectar,
    inicializar_banco,
    cadastrar_produto,
    listar_produtos,
    obter_metricas_dashboard,
)


# Formato visual da moeda. Não altera valores no banco.
MOEDA = "R$"

COLUNAS_PRODUTOS = [
    "ID",
    "Código",
    "Produto",
    "Categoria",
    "Custo",
    "Preço de venda",
    "Quantidade",
    "Estoque mínimo",
]

TRADUCAO_CATEGORIAS = {
    "Electronics": "Eletrônicos",
    "Office Supplies": "Material de escritório",
    "Raw Materials": "Matérias-primas",
    "Packaging": "Embalagens",
    "Tools": "Ferramentas",
}

CATEGORIAS_PADRAO = list(TRADUCAO_CATEGORIAS.keys())


# O page_config deve ser chamado antes dos demais comandos Streamlit.
st.set_page_config(
    page_title="Depot ERP",
    page_icon="📦",
    layout="wide",
)

inicializar_banco()


# Estilo visual. Não usa fontes ou recursos externos.
st.markdown(
    """
    <style>
    html, body, [class*="css"] {
        font-family: "Inter", "Segoe UI", Arial, sans-serif;
    }

    .stApp {
        background: #F4F7FB;
    }

    .block-container {
        max-width: 1500px;
        padding-top: 2rem;
        padding-bottom: 2.5rem;
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #10213B 0%, #0C192E 100%);
        border-right: 1px solid #213653;
    }

    section[data-testid="stSidebar"] * {
        color: #E8EEF8;
    }

    div[data-testid="stTextInput"] input {
        border-radius: 10px;
        border: 1px solid #DCE4EF;
        background: #FFFFFF;
    }

    div.stButton > button,
    div.stFormSubmitButton > button {
        border-radius: 9px;
        font-weight: 600;
    }

    .kpi-card {
        background: #FFFFFF;
        border: 1px solid #E5EAF2;
        border-radius: 14px;
        padding: 16px 18px;
        min-height: 132px;
        box-shadow: 0 3px 12px rgba(26, 48, 78, 0.06);
    }

    .kpi-icon {
        width: 34px;
        height: 34px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
        margin-bottom: 10px;
    }

    .kpi-label {
        color: #64748B;
        font-size: 13px;
        margin: 0 0 3px 0;
    }

    .kpi-value {
        color: #10213B;
        font-size: 24px;
        line-height: 1.2;
        font-weight: 700;
        margin: 0;
    }

    .kpi-note {
        color: #718096;
        font-size: 11px;
        margin-top: 7px;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid #E5EAF2;
        border-radius: 10px;
        overflow: hidden;
    }

    div[data-testid="stPlotlyChart"] {
        background: #FFFFFF;
        border: 1px solid #E5EAF2;
        border-radius: 12px;
        padding: 5px;
    }

    .subtle {
        color: #718096;
        font-size: 13px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def formatar_moeda(valor):
    """Formata um número como moeda, sem alterar o valor armazenado."""
    valor = float(valor or 0)
    numero = f"{valor:,.2f}"
    numero = numero.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{MOEDA} {numero}"


def carregar_produtos():
    produtos = listar_produtos()
    df = pd.DataFrame(produtos, columns=COLUNAS_PRODUTOS)

    if not df.empty:
        df["Valor em estoque"] = df["Custo"] * df["Quantidade"]

        df["Status"] = df.apply(
            lambda linha: (
                "Estoque baixo"
                if linha["Quantidade"] <= linha["Estoque mínimo"]
                else "Normal"
            ),
            axis=1,
        )

        df["Categoria exibida"] = df["Categoria"].map(
            lambda categoria: TRADUCAO_CATEGORIAS.get(
                str(categoria), str(categoria)
            )
        )

    return df


def consultar_sql(query, parametros=()):
    """Executa uma consulta de leitura e sempre fecha a conexão."""
    conn = conectar()
    try:
        return pd.read_sql_query(query, conn, params=parametros)
    finally:
        conn.close()


def carregar_movimentacoes_recentes(limite=8):
    return consultar_sql(
        """
        SELECT
            m.data_hora AS Data,
            COALESCE(p.nome, 'Produto não encontrado') AS Produto,
            upper(m.tipo) AS Tipo,
            m.quantidade AS Quantidade
        FROM movimentacoes AS m
        LEFT JOIN produtos AS p ON p.id = m.produto_id
        ORDER BY m.data_hora DESC, m.id DESC
        LIMIT ?
        """,
        (limite,),
    )


def carregar_movimentacoes_7_dias():
    data_inicio = (date.today() - timedelta(days=6)).isoformat()

    return consultar_sql(
        """
        SELECT
            date(data_hora) AS Dia,
            upper(tipo) AS Tipo,
            SUM(abs(quantidade)) AS Quantidade
        FROM movimentacoes
        WHERE date(data_hora) >= date(?)
        GROUP BY date(data_hora), upper(tipo)
        """,
        (data_inicio,),
    )


def contar_movimentacoes_hoje():
    hoje = date.today().isoformat()

    resultado = consultar_sql(
        """
        SELECT COUNT(*) AS total
        FROM movimentacoes
        WHERE date(data_hora) = date(?)
        """,
        (hoje,),
    )

    if resultado.empty:
        return 0

    return int(resultado.iloc[0]["total"])


def montar_grafico_movimentacoes():
    datas = pd.date_range(
        end=pd.Timestamp.today().normalize(),
        periods=7,
    )
    nomes_dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

    grafico = pd.DataFrame(
        {
            "Data": [data.strftime("%Y-%m-%d") for data in datas],
            "Dia": [nomes_dias[data.weekday()] for data in datas],
            "Entradas": [0] * 7,
            "Saídas": [0] * 7,
        }
    )

    movimentacoes = carregar_movimentacoes_7_dias()

    for _, movimentacao in movimentacoes.iterrows():
        dia = str(movimentacao["Dia"])[:10]
        tipo = str(movimentacao["Tipo"]).strip().upper()
        tipo = tipo.replace("Í", "I")

        if tipo == "ENTRADA":
            coluna = "Entradas"
        elif tipo == "SAIDA":
            coluna = "Saídas"
        else:
            continue

        linhas = grafico.index[grafico["Data"] == dia]
        if len(linhas) > 0:
            indice = linhas[0]
            grafico.loc[indice, coluna] = float(
                movimentacao["Quantidade"] or 0
            )

    return grafico


def desenhar_cartao(coluna, icone, rotulo, valor, detalhe, cor):
    with coluna:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-icon"
                     style="background:{cor}18;color:{cor}">
                    {icone}
                </div>
                <p class="kpi-label">{rotulo}</p>
                <p class="kpi-value">{valor}</p>
                <div class="kpi-note">{detalhe}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def filtrar_produtos(df, busca):
    if df.empty or not busca.strip():
        return df

    termo = busca.strip()

    mascara = (
        df["Código"]
        .astype(str)
        .str.contains(termo, case=False, regex=False, na=False)
        | df["Produto"]
        .astype(str)
        .str.contains(termo, case=False, regex=False, na=False)
        | df["Categoria exibida"]
        .astype(str)
        .str.contains(termo, case=False, regex=False, na=False)
    )

    return df[mascara]


def preparar_tabela_produtos(df, colunas=None):
    if colunas is None:
        colunas = [
            "Código",
            "Produto",
            "Categoria exibida",
            "Custo",
            "Preço de venda",
            "Valor em estoque",
            "Quantidade",
            "Estoque mínimo",
            "Status",
        ]

    tabela = df[colunas].copy()

    for coluna in ["Custo", "Preço de venda", "Valor em estoque"]:
        if coluna in tabela.columns:
            tabela[coluna] = tabela[coluna].apply(formatar_moeda)

    return tabela


def mostrar_tabela_produtos(df, colunas=None):
    if df.empty:
        st.info("Nenhum produto para mostrar.")
        return

    tabela = preparar_tabela_produtos(df, colunas)
    st.dataframe(tabela, use_container_width=True)


# Navegação lateral
with st.sidebar:
    st.markdown("## 📦 Depot")
    st.caption("Controle de estoque")
    st.markdown("---")

    pagina = st.radio(
        "Navegação",
        [
            "Painel executivo",
            "Produtos",
            "Movimentações",
            "Estoque baixo",
            "Fornecedores",
            "Relatórios",
            "Configurações",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.caption("Sistema de gestão")
    st.caption("Depot ERP")


# Barra superior
topo_busca, topo_data, topo_usuario = st.columns([2.2, 0.8, 0.65])

with topo_busca:
    busca_global = st.text_input(
        "Buscar produto",
        placeholder="Buscar produto, código ou categoria...",
        label_visibility="collapsed",
        key="busca_global",
    )

with topo_data:
    st.markdown(
        f"""
        <div class="subtle" style="padding-top:9px">
            📅 {datetime.now().strftime("%d/%m/%Y")}
        </div>
        """,
        unsafe_allow_html=True,
    )

with topo_usuario:
    st.markdown(
        """
        <div style="padding-top:8px;color:#334155;font-weight:600">
            👤 Administrador
        </div>
        """,
        unsafe_allow_html=True,
    )


# Painel executivo
if pagina == "Painel executivo":
    st.title("Painel executivo")
    st.caption("Acompanhe os principais indicadores do seu estoque.")

    df_produtos = carregar_produtos()
    total_skus, valor_estoque, estoque_baixo = obter_metricas_dashboard()

    total_unidades = (
        int(df_produtos["Quantidade"].sum())
        if not df_produtos.empty
        else 0
    )
    movimentos_hoje = contar_movimentacoes_hoje()

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    desenhar_cartao(
        kpi1,
        "📦",
        "Produtos cadastrados",
        f"{total_skus:,}",
        "SKUs no inventário",
        "#2563EB",
    )
    desenhar_cartao(
        kpi2,
        "💰",
        "Valor total em estoque",
        formatar_moeda(valor_estoque),
        f"{total_unidades:,} unidades cadastradas",
        "#059669",
    )
    desenhar_cartao(
        kpi3,
        "⚠️",
        "Estoque baixo",
        f"{estoque_baixo:,}",
        "No mínimo ou abaixo dele",
        "#E11D48",
    )
    desenhar_cartao(
        kpi4,
        "↔️",
        "Movimentações hoje",
        f"{movimentos_hoje:,}",
        "Registros no banco hoje",
        "#7C3AED",
    )

    st.markdown("<br>", unsafe_allow_html=True)

    col_movimentacoes, col_categorias = st.columns([1.35, 1])

    with col_movimentacoes:
        st.subheader("Movimentações dos últimos 7 dias")

        df_semana = montar_grafico_movimentacoes()
        quantidade_movimentada = (
            df_semana["Entradas"].sum() + df_semana["Saídas"].sum()
        )

        if quantidade_movimentada == 0:
            st.info("Ainda não há movimentações registradas nesse período.")
        else:
            fig_movimentacoes = px.bar(
                df_semana,
                x="Dia",
                y=["Entradas", "Saídas"],
                barmode="group",
                color_discrete_map={
                    "Entradas": "#2563EB",
                    "Saídas": "#F97316",
                },
                labels={
                    "Dia": "",
                    "value": "Quantidade",
                    "variable": "Tipo",
                },
            )
            fig_movimentacoes.update_layout(
                height=310,
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend_title_text="",
                font=dict(color="#475569"),
            )
            fig_movimentacoes.update_yaxes(
                gridcolor="#E8EDF4",
                zeroline=False,
            )
            fig_movimentacoes.update_xaxes(showgrid=False)

            st.plotly_chart(
                fig_movimentacoes,
                use_container_width=True,
                config={"displayModeBar": False},
            )

    with col_categorias:
        st.subheader("Valor do estoque por categoria")

        if df_produtos.empty:
            st.info("Cadastre produtos para ver os dados por categoria.")
        else:
            por_categoria = (
                df_produtos.groupby(
                    "Categoria exibida",
                    as_index=False,
                )["Valor em estoque"]
                .sum()
                .sort_values("Valor em estoque", ascending=False)
            )

            if por_categoria["Valor em estoque"].sum() <= 0:
                st.info("Ainda não há valor de estoque para exibir.")
            else:
                fig_categorias = px.pie(
                    por_categoria,
                    names="Categoria exibida",
                    values="Valor em estoque",
                    hole=0.62,
                    color_discrete_sequence=[
                        "#2563EB",
                        "#10B981",
                        "#F59E0B",
                        "#8B5CF6",
                        "#64748B",
                        "#EC4899",
                    ],
                )
                fig_categorias.update_traces(
                    textposition="inside",
                    textinfo="percent",
                    hovertemplate=(
                        "%{label}<br>Valor: "
                        + MOEDA
                        + " %{value:,.2f}<extra></extra>"
                    ),
                )
                fig_categorias.update_layout(
                    height=310,
                    margin=dict(l=5, r=5, t=5, b=5),
                    paper_bgcolor="rgba(0,0,0,0)",
                    showlegend=True,
                    legend=dict(orientation="h", y=-0.08),
                    font=dict(color="#475569"),
                    annotations=[
                        {
                            "text": formatar_moeda(valor_estoque),
                            "x": 0.5,
                            "y": 0.5,
                            "showarrow": False,
                            "font": {
                                "size": 15,
                                "color": "#10213B",
                            },
                        }
                    ],
                )

                st.plotly_chart(
                    fig_categorias,
                    use_container_width=True,
                    config={"displayModeBar": False},
                )

    st.markdown("<br>", unsafe_allow_html=True)

    col_alertas, col_recentes = st.columns([1, 1.25])

    with col_alertas:
        st.subheader("⚠️ Produtos que precisam de atenção")

        if df_produtos.empty:
            st.info("Ainda não existem produtos cadastrados.")
        else:
            df_alertas = df_produtos[
                df_produtos["Quantidade"] <= df_produtos["Estoque mínimo"]
            ]
            df_alertas = filtrar_produtos(df_alertas, busca_global)

            if df_alertas.empty:
                st.success("Nenhum produto precisa de atenção.")
            else:
                mostrar_tabela_produtos(
                    df_alertas,
                    [
                        "Código",
                        "Produto",
                        "Quantidade",
                        "Estoque mínimo",
                    ],
                )

    with col_recentes:
        st.subheader("↔️ Movimentações recentes")

        recentes = carregar_movimentacoes_recentes(6)

        if recentes.empty:
            st.info("Ainda não há movimentações registradas.")
        else:
            recentes["Tipo"] = recentes["Tipo"].replace(
                {
                    "ENTRADA": "Entrada",
                    "SAIDA": "Saída",
                }
            )
            st.dataframe(recentes, use_container_width=True)


# Produtos
elif pagina == "Produtos":
    st.title("Produtos")
    st.caption("Cadastre produtos e consulte o catálogo do inventário.")

    aba_cadastro, aba_catalogo = st.tabs(
        ["Cadastrar produto", "Catálogo"]
    )

    with aba_cadastro:
        st.subheader("Novo produto")

        df_atual = carregar_produtos()

        if not df_atual.empty:
            categorias_existentes = (
                df_atual["Categoria"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )
        else:
            categorias_existentes = []

        categorias = sorted(
            set(CATEGORIAS_PADRAO + categorias_existentes)
        )

        with st.form("formulario_produto"):
            col1, col2 = st.columns(2)

            with col1:
                codigo = st.text_input("Código do produto")
                nome = st.text_input("Nome do produto")
                categoria = st.selectbox(
                    "Categoria",
                    categorias,
                    format_func=lambda valor: TRADUCAO_CATEGORIAS.get(
                        valor,
                        valor,
                    ),
                )
                custo = st.number_input(
                    f"Custo ({MOEDA})",
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                )

            with col2:
                preco = st.number_input(
                    f"Preço de venda ({MOEDA})",
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                )
                quantidade = st.number_input(
                    "Quantidade inicial",
                    min_value=0,
                    step=1,
                )
                estoque_minimo = st.number_input(
                    "Estoque mínimo",
                    min_value=0,
                    step=1,
                )

            salvar = st.form_submit_button("Cadastrar produto")

        if salvar:
            if not codigo.strip() or not nome.strip():
                st.warning("Preencha o código e o nome do produto.")
            else:
                sucesso = cadastrar_produto(
                    codigo.strip(),
                    nome.strip(),
                    categoria,
                    custo,
                    preco,
                    int(quantidade),
                    int(estoque_minimo),
                )

                if sucesso:
                    st.success(
                        f"Produto “{nome.strip()}” cadastrado com sucesso."
                    )
                else:
                    st.error(
                        "Não foi possível cadastrar. Verifique se o código "
                        "já está em uso."
                    )

    with aba_catalogo:
        st.subheader("Catálogo de produtos")

        df_produtos = carregar_produtos()

        if df_produtos.empty:
            st.info("Ainda não existem produtos cadastrados.")
        else:
            df_filtrado = filtrar_produtos(
                df_produtos,
                busca_global,
            )
            st.caption(
                f"{len(df_filtrado)} produto(s) encontrados."
            )

            if df_filtrado.empty:
                st.info("Nenhum produto corresponde à busca.")
            else:
                mostrar_tabela_produtos(df_filtrado)


# Estoque baixo
elif pagina == "Estoque baixo":
    st.title("Estoque baixo")
    st.caption("Produtos no estoque mínimo ou abaixo dele.")

    df_produtos = carregar_produtos()

    if df_produtos.empty:
        st.info("Ainda não existem produtos cadastrados.")
    else:
        df_baixo = df_produtos[
            df_produtos["Quantidade"] <= df_produtos["Estoque mínimo"]
        ]
        df_baixo = filtrar_produtos(df_baixo, busca_global)

        if df_baixo.empty:
            st.success("Nenhum produto corresponde a este filtro.")
        else:
            mostrar_tabela_produtos(df_baixo)


# Movimentações
elif pagina == "Movimentações":
    st.title("Movimentações")
    st.caption("Registros existentes no histórico do estoque.")

    movimentos = carregar_movimentacoes_recentes(100)

    if movimentos.empty:
        st.info("Ainda não há movimentações registradas.")
    else:
        movimentos["Tipo"] = movimentos["Tipo"].replace(
            {
                "ENTRADA": "Entrada",
                "SAIDA": "Saída",
            }
        )

        if busca_global.strip():
            movimentos = movimentos[
                movimentos["Produto"].astype(str).str.contains(
                    busca_global.strip(),
                    case=False,
                    regex=False,
                    na=False,
                )
            ]

        if movimentos.empty:
            st.info("Nenhuma movimentação corresponde à busca.")
        else:
            st.dataframe(movimentos, use_container_width=True)


# Páginas sem backend disponível no código enviado
else:
    st.title(pagina)
    st.info(
        "Esta seção ainda não tem operações implementadas no código "
        "fornecido. Ela permanece sem dados ilustrativos."
    )