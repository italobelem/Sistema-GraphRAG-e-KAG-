import sys
import os
import importlib
import tempfile
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network
from neo4j import GraphDatabase

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
import src.retrieval.hybrid_retriever as hr
import src.ingestion.pipeline_ner_re as ing
import src.retrieval.graph_algorithms as ga

importlib.reload(hr)

st.set_page_config(
    page_title="MedGraph KAG — Inteligência Clínica em PDFs",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================================
# ESTILIZAÇÃO VISUAL LIMPA (SEM CONFLITO COM WRAPPERS DO STREAMLIT)
# =====================================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .block-container {
        padding-top: 3.5rem;
        padding-bottom: 2rem;
        max-width: 1420px;
    }

    /* Cabeçalho Principal */
    .hero-header {
        box-sizing: border-box;
        width: 100%;
        background: linear-gradient(135deg, #0B1120 0%, #131C31 65%, #0F292E 100%);
        border: 1px solid #263244;
        border-left: 5px solid #10B981;
        border-radius: 12px;
        padding: 1.15rem 1.5rem;
        margin-top: 0.25rem;
        margin-bottom: 1.1rem;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    }
    .hero-title {
        font-size: 1.48rem;
        font-weight: 700;
        color: #F8FAFC;
        letter-spacing: -0.02em;
        margin: 0 0 0.25rem 0;
    }
    .hero-subtitle {
        font-size: 0.87rem;
        color: #94A3B8;
        margin: 0;
    }
    .hero-subtitle b {
        color: #CBD5E1;
        font-weight: 600;
    }

    /* Botão Primário em Esmeralda */
    button[kind="primary"] {
        background: linear-gradient(135deg, #0D9488 0%, #10B981 100%) !important;
        border: none !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        height: 42px !important;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.22) !important;
        transition: all 0.15s ease !important;
    }
    button[kind="primary"]:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 16px rgba(16, 185, 129, 0.35) !important;
    }

    /* Abas e Indicador Ativo em Esmeralda (remove a barra vermelha padrão) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        border-bottom: 1px solid #1E293B;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
        font-weight: 500;
        color: #94A3B8;
        border-radius: 8px 8px 0 0;
    }
    .stTabs [aria-selected="true"] {
        color: #10B981 !important;
        background-color: rgba(16, 185, 129, 0.08) !important;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: #10B981 !important;
    }

    /* Input de Pesquisa */
    .stTextInput input {
        background-color: #111827 !important;
        border: 1px solid #263244 !important;
        border-radius: 10px !important;
        color: #F8FAFC !important;
        height: 42px !important;
        padding: 0 0.95rem !important;
    }
    .stTextInput input:focus {
        border-color: #10B981 !important;
        box-shadow: 0 0 0 1px #10B981 !important;
    }

    /* Badges de Entidades Âncora e PDFs */
    .badges-wrapper {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 12px;
    }
    .badge-pill {
        display: inline-flex;
        align-items: center;
        background-color: rgba(56, 189, 248, 0.1);
        border: 1px solid rgba(56, 189, 248, 0.32);
        color: #7DD3FC;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 500;
    }
    .badge-pdf {
        display: inline-flex;
        align-items: center;
        background-color: rgba(16, 185, 129, 0.1);
        border: 1px solid rgba(16, 185, 129, 0.32);
        color: #6EE7B7;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 500;
    }

    /* Suaviza os códigos inline (DOC-MED-001) dentro do Parecer */
    .stMarkdown code {
        background-color: rgba(56, 189, 248, 0.12) !important;
        color: #7DD3FC !important;
        border: 1px solid rgba(56, 189, 248, 0.22) !important;
        border-radius: 5px !important;
        padding: 1px 6px !important;
        font-size: 0.78rem !important;
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Cartões KPI Customizados (Sem truncamento de texto) */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 10px;
        margin-top: 12px;
    }
    .kpi-card {
        background-color: #111827;
        border: 1px solid #1E293B;
        border-radius: 10px;
        padding: 12px 14px;
    }
    .kpi-label {
        font-size: 0.75rem;
        color: #94A3B8;
        font-weight: 500;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 1.32rem;
        font-weight: 700;
        color: #F8FAFC;
        line-height: 1.2;
    }

    /* Cartões da Barra Lateral */
    .sidebar-card {
        background-color: #111827;
        border: 1px solid #1E293B;
        border-radius: 10px;
        padding: 11px 13px;
        font-size: 0.82rem;
        color: #CBD5E1;
        margin-bottom: 10px;
    }
    .legend-row {
        display: flex;
        align-items: center;
        margin-bottom: 7px;
    }
    .legend-row:last-child {
        margin-bottom: 0;
    }
    .dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 9px;
        flex-shrink: 0;
    }
    .sidebar-stats {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
    }
    .stat-box {
        background-color: #111827;
        border: 1px solid #1E293B;
        border-radius: 10px;
        padding: 10px 12px;
        text-align: center;
    }
    .stat-title {
        font-size: 0.74rem;
        color: #94A3B8;
        margin-bottom: 2px;
    }
    .stat-num {
        font-size: 1.25rem;
        font-weight: 700;
        color: #10B981;
    }

    /* Moldura do Grafo PyVis */
    iframe {
        border-radius: 12px !important;
        border: 1px solid #1E293B !important;
    }

    /* Dica discreta abaixo do grafo */
    .graph-hint {
        font-size: 0.8rem;
        color: #94A3B8;
        margin-top: 6px;
        padding: 8px 12px;
        background-color: #111827;
        border: 1px solid #1E293B;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

CORES_POR_TIPO = {
    "Paciente": "#38BDF8",      # Azul Celeste
    "Doenca": "#F43F5E",        # Vermelho Coral
    "Causa": "#FBBF24",         # Amarelo Âmbar
    "Medicamento": "#10B981",   # Verde Esmeralda
    "RiscoClinico": "#C084FC",  # Roxo Lavanda
}

def obter_estatisticas_pdfs_neo4j() -> list[dict]:
    try:
        with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
            with driver.session() as session:
                return session.run("""
                    MATCH (d:Documento)
                    OPTIONAL MATCH (c:Chunk)-[:PARTE_DE]->(d)
                    OPTIONAL MATCH (e:Entidade)-[:MENCIONADO_EM]->(d)
                    RETURN d.id AS id,
                           d.arquivo_pdf AS arquivo,
                           coalesce(d.num_paginas, 1) AS paginas,
                           count(DISTINCT c) AS chunks,
                           count(DISTINCT e) AS entidades
                    ORDER BY d.id ASC
                """).data()
    except Exception:
        return []

def renderizar_subgrafo_interativo(subgrafo: list) -> str:
    net = Network(height="560px", width="100%", bgcolor="#0B1120", font_color="#F8FAFC", directed=True)
    # Física equilibrada para manter os nós compactos e com rótulos legíveis logo na abertura
    net.barnes_hut(gravity=-3600, central_gravity=0.32, spring_length=145, spring_strength=0.05, damping=0.15)

    nos_adicionados = set()
    arestas_adicionadas = set()

    for item in subgrafo:
        nomes = item.get("nos", [])
        tipos = item.get("tipos", [])
        for nome, tipo in zip(nomes, tipos):
            if nome and nome not in nos_adicionados:
                cor = CORES_POR_TIPO.get(tipo, "#94A3B8")
                net.add_node(
                    nome,
                    label=nome,
                    title=f"Categoria: {tipo} | Entidade: {nome}",
                    color={
                        "background": cor,
                        "border": "#F8FAFC",
                        "highlight": {"background": cor, "border": "#FFFFFF"},
                        "hover": {"background": cor, "border": "#FFFFFF"}
                    },
                    font={
                        "size": 15,
                        "face": "Inter, Arial, sans-serif",
                        "color": "#F8FAFC",
                        "strokeWidth": 3,
                        "strokeColor": "#0B1120"
                    },
                    borderWidth=2,
                    size=25 if tipo in ("Doenca", "Paciente") else 19
                )
                nos_adicionados.add(nome)

        for passo in item.get("passos", []):
            origem = passo["origem"]
            destino = passo["destino"]
            rel = passo["relacao"]
            pdf_fonte = passo.get("pdf", "")
            chave_aresta = (origem, rel, destino)
            if origem in nos_adicionados and destino in nos_adicionados and chave_aresta not in arestas_adicionadas:
                net.add_edge(
                    origem,
                    destino,
                    label=rel.replace("_", " ").lower(),
                    title=f"Relação: {rel} | Fonte: {pdf_fonte}",
                    color={"color": "rgba(148, 163, 184, 0.42)", "highlight": "#38BDF8", "hover": "#38BDF8"},
                    font={
                        "size": 11,
                        "face": "Inter, Arial, sans-serif",
                        "color": "#94A3B8",
                        "strokeWidth": 2,
                        "strokeColor": "#0B1120",
                        "align": "middle"
                    },
                    width=1.6,
                    arrows={"to": {"enabled": True, "scaleFactor": 0.7}},
                    smooth={"type": "curvedCW", "roundness": 0.14}
                )
                arestas_adicionadas.add(chave_aresta)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as tmp:
        net.save_graph(tmp.name)
        caminho_html = tmp.name

    with open(caminho_html, "r", encoding="utf-8") as f:
        html_content = f.read()
    os.remove(caminho_html)
    return html_content

# =====================================================================
# CABEÇALHO PRINCIPAL
# =====================================================================
st.markdown("""
<div class="hero-header">
    <div class="hero-title">🩺 MedGraph KAG — Suporte à Decisão Clínica sobre Prontuários PDF</div>
    <div class="hero-subtitle">
        Tendências em Ciência da Computação (2026) &bull; Prof. Ricardo Roberto de Lima &bull;
        Arquitetura Híbrida: <b>Leitura de PDFs + Neo4j LPG + Entity Resolution + PageRank/Louvain + Travessia Multi-hop</b>
    </div>
</div>
""", unsafe_allow_html=True)

# =====================================================================
# BARRA LATERAL LIMPA E SEM CORTES
# =====================================================================
with st.sidebar:
    st.markdown("#### 📋 Roteiro de Consultas")
    pergunta_sugerida = st.selectbox(
        "Selecione um caso clínico:",
        [
            "Quais pacientes são afetados por condições cardíacas e quais seus tratamentos?",
            "Quais os riscos de interação medicamentosa caso o paciente com Infarto Agudo do Miocárdio utilize Omeprazol para Úlcera Péptica ou tenha Nefropatia Diabética em uso de Metformina?",
            "Por que o medicamento preventivo usado na Enxaqueca Crônica é contraindicado para o paciente pediátrico com Asma Brônquica?",
            "Por que o Ácido Acetilsalicílico (AAS) usado no Infarto é proibido na Dengue Clássica e qual analgésico seguro (Tylenol) é compartilhado com a Enxaqueca?",
            "Quais doenças nos prontuários PDF compartilham a Hipertensão Arterial Sistêmica (HAS) como causa?"
        ]
    )

    st.markdown("#### 🎨 Legenda do Grafo")
    st.markdown("""
    <div class="sidebar-card">
        <div class="legend-row"><span class="dot" style="background:#38BDF8;"></span><span><b>Paciente</b> &nbsp;<i>(Perfis e idades)</i></span></div>
        <div class="legend-row"><span class="dot" style="background:#F43F5E;"></span><span><b>Doença</b> &nbsp;<i>(Diagnósticos CID-10)</i></span></div>
        <div class="legend-row"><span class="dot" style="background:#FBBF24;"></span><span><b>Causa</b> &nbsp;<i>(Fatores etiológicos)</i></span></div>
        <div class="legend-row"><span class="dot" style="background:#10B981;"></span><span><b>Medicamento</b> &nbsp;<i>(Prescrições)</i></span></div>
        <div class="legend-row"><span class="dot" style="background:#C084FC;"></span><span><b>Risco Clínico</b> &nbsp;<i>(Interações)</i></span></div>
    </div>
    """, unsafe_allow_html=True)

    docs_info = obter_estatisticas_pdfs_neo4j()
    total_pdfs = len(docs_info)
    total_chunks = sum(d["chunks"] for d in docs_info)

    st.markdown("#### 📊 Base PDF (Neo4j)")
    st.markdown(f"""
    <div class="sidebar-stats">
        <div class="stat-box">
            <div class="stat-title">PDFs Ativos</div>
            <div class="stat-num">{total_pdfs}</div>
        </div>
        <div class="stat-box">
            <div class="stat-title">Chunks</div>
            <div class="stat-num">{total_chunks}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# =====================================================================
# ABAS DE NAVEGAÇÃO
# =====================================================================
aba_consulta, aba_pdfs, aba_auditoria = st.tabs([
    "🩺 Consulta Clínica & Grafo Interativo",
    "📂 Prontuários PDF Indexados (Gestão & Upload)",
    "🔍 Auditoria Multi-hop & Cypher (Provenance)"
])

with aba_consulta:
    col_input, col_btn = st.columns([4.6, 1.2], gap="small")
    with col_input:
        pergunta_usuario = st.text_input(
            "Pergunta clínica:",
            value=pergunta_sugerida,
            label_visibility="collapsed",
            placeholder="Digite sua consulta clínica sobre pacientes, doenças, causas ou medicamentos..."
        )
    with col_btn:
        executar = st.button("🔎 Analisar Grafo", type="primary", use_container_width=True)

    if executar or st.session_state.get("ultima_pergunta") != pergunta_usuario:
        with st.spinner("Consultando prontuários PDF e percorrendo relações multi-hop no Neo4j..."):
            st.session_state["ultimo_resultado"] = hr.gerar_resposta_graphrag(pergunta_usuario)
            st.session_state["ultima_pergunta"] = pergunta_usuario

    resultado = st.session_state["ultimo_resultado"]

    col_esq, col_dir = st.columns([1.15, 1.0], gap="large")

    with col_esq:
        st.markdown("##### 💡 Parecer Clínico Fundamentado")

        badges_html = '<div class="badges-wrapper">'
        for ancora in resultado.get("nos_ancora", []):
            badges_html += f'<span class="badge-pill">🎯 {ancora}</span>'
        for pdf_nome in resultado.get("pdfs_consultados", []):
            badges_html += f'<span class="badge-pdf">📄 {pdf_nome}</span>'
        badges_html += '</div>'
        st.markdown(badges_html, unsafe_allow_html=True)

        # Único contêiner limpo para o Parecer Clínico
        with st.container(border=True):
            st.markdown(resultado["resposta"])

        # Cartões KPI limpos e sem truncamento
        st.markdown(f"""
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-label">Confiança Híbrida</div>
                <div class="kpi-value">{resultado['confianca']:.1%}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Entidades Âncora</div>
                <div class="kpi-value">{len(resultado['nos_ancora'])}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Caminhos Multi-hop</div>
                <div class="kpi-value">{len(resultado['subgrafo'])}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_dir:
        st.markdown("##### 🕸️ Subgrafo Interativo do Caso")
        if resultado["subgrafo"]:
            html_grafo = renderizar_subgrafo_interativo(resultado["subgrafo"])
            components.html(html_grafo, height=565, scrolling=False)
            st.markdown(
                '<div class="graph-hint">💡 Arraste os nós para reorganizar, use o scroll para zoom e passe o mouse sobre as arestas para ver o PDF de origem.</div>',
                unsafe_allow_html=True
            )
        else:
            st.info("Nenhum subgrafo retornado para esta consulta.")

with aba_pdfs:
    st.markdown("##### 📚 Base de Conhecimento em PDF Carregada no Neo4j")
    st.write("Prontuários médicos reais lidos da pasta `data/pdfs/`, segmentados em *chunks* e convertidos em entidades e relações:")

    if docs_info:
        st.dataframe(
            docs_info,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": st.column_config.TextColumn("ID do Prontuário", width="small"),
                "arquivo": st.column_config.TextColumn("Arquivo PDF Original", width="large"),
                "paginas": st.column_config.NumberColumn("Páginas", width="small"),
                "chunks": st.column_config.NumberColumn("Chunks Gerados", width="small"),
                "entidades": st.column_config.NumberColumn("Entidades Extraídas", width="small"),
            }
        )
    else:
        st.warning("Nenhum PDF encontrado no Neo4j. Verifique se o Docker está ativo.")

    st.markdown("---")
    st.markdown("##### ➕ Adicionar Novo Prontuário PDF à Base KAG")
    pdf_upload = st.file_uploader("Selecione um arquivo .pdf clínico para ingestão automática:", type=["pdf"])
    if pdf_upload is not None:
        os.makedirs("data/pdfs", exist_ok=True)
        caminho_salvo = os.path.join("data/pdfs", pdf_upload.name)
        with open(caminho_salvo, "wb") as f:
            f.write(pdf_upload.getbuffer())
        if st.button("Processar e Indexar PDF no Neo4j", type="primary"):
            with st.spinner("Extraindo páginas, gerando chunks, resolvendo entidades e recalculando PageRank..."):
                ing.executar_pipeline_ingestao_pdfs("data/pdfs")
                ga.executar_algoritmos_gds()
            st.success(f"Arquivo '{pdf_upload.name}' processado e integrado ao Grafo de Conhecimento!")
            st.rerun()

with aba_auditoria:
    st.markdown("##### 🛡️ Cadeias Relacionais Verificadas (Grounding Semântico)")
    st.write("Triplas exatas extraídas do subgrafo do Neo4j e enviadas como contexto restrito anti-alucinação:")
    st.code(resultado["contexto_texto"] or "Sem caminhos retornados.", language="text")

    st.markdown("##### ⚙️ Consultas Cypher (Text-to-Cypher LLM + Busca Híbrida)")
    st.code(resultado["cypher_executada"], language="cypher")