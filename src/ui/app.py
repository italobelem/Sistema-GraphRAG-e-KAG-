import sys
import os
import tempfile
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.retrieval.hybrid_retriever import gerar_resposta_graphrag

st.set_page_config(
    page_title="GraphRAG & KAG - Cyber Threat Intelligence",
    page_icon="🕸️",
    layout="wide"
)

CORES_POR_TIPO = {
    "GrupoAmeaca": "#EF4444",      # Vermelho (Ator de Ameaça)
    "Malware": "#F97316",          # Laranja (Malware)
    "Vulnerabilidade": "#EAB308",  # Amarelo (CVE)
    "Tecnica": "#3B82F6",          # Azul (MITRE ATT&CK)
    "Alvo": "#10B981",             # Verde (Setor / Software Alvo)
}

def renderizar_subgrafo_interativo(subgrafo: list) -> str:
    """Gera o HTML interativo do subgrafo retornado usando PyVis."""
    net = Network(height="520px", width="100%", bgcolor="#0F172A", font_color="white", directed=True)
    net.barnes_hut(gravity=-3500, central_gravity=0.3, spring_length=140)

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
                    title=f"Tipo: {tipo}\nEntidade: {nome}",
                    color=cor,
                    size=26 if tipo == "GrupoAmeaca" else 20
                )
                nos_adicionados.add(nome)

        for passo in item.get("passos", []):
            origem = passo["origem"]
            destino = passo["destino"]
            rel = passo["relacao"]
            chave_aresta = (origem, rel, destino)
            if origem in nos_adicionados and destino in nos_adicionados and chave_aresta not in arestas_adicionadas:
                net.add_edge(origem, destino, label=rel, title=rel, color="#64748B", arrows="to")
                arestas_adicionadas.add(chave_aresta)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as tmp:
        net.save_graph(tmp.name)
        caminho_html = tmp.name

    with open(caminho_html, "r", encoding="utf-8") as f:
        html_content = f.read()
    os.remove(caminho_html)
    return html_content

# =====================================================================
# CABEÇALHO E SIDEBAR
# =====================================================================

st.title("🕸️ Sistema GraphRAG & KAG — Cyber Threat Intelligence (CTI)")
st.markdown(
    "**Disciplina:** Tendências em Ciência da Computação | **Docente:** Prof. Ricardo Roberto de Lima  \n"
    "Arquitetura Híbrida combinando **Neo4j LPG**, **Busca Vetorial + Léxica**, **Travessia Multi-hop** e **PageRank (GDS)**."
)

with st.sidebar:
    st.header("🎯 Consultas Multi-hop Sugeridas")
    pergunta_exemplo = st.radio(
        "Selecione um caso de teste ou digite abaixo:",
        [
            "Quais setores e sistemas estão em risco de ataques realizados pelo grupo APT29?",
            "Como o grupo Cozy Bear (Midnight Blizzard) consegue atingir o Setor de Energia Elétrica?",
            "Quais grupos exploram a vulnerabilidade CVE-2023-38831 e quais alvos financeiros são afetados?",
            "Quais grupos de ameaça compartilham o uso da técnica T1078 e quais malwares estão associados?"
        ]
    )
    st.markdown("---")
    st.subheader("🎨 Legenda do Grafo (LPG)")
    st.markdown(
        "- 🔴 **GrupoAmeaca** *(APT29, APT28, Lazarus)*\n"
        "- 🟠 **Malware** *(SUNBURST, AppleJeus, X-Agent)*\n"
        "- 🟡 **Vulnerabilidade** *(CVEs)*\n"
        "- 🔵 **Tecnica** *(MITRE ATT&CK)*\n"
        "- 🟢 **Alvo** *(Setores e Sistemas)*"
    )

pergunta_usuario = st.text_input("🔍 Digite sua consulta complexa para o GraphRAG:", value=pergunta_exemplo)

if st.button("Executar Raciocínio Multi-hop no Grafo", type="primary"):
    with st.spinner("Consultando Índices Vetoriais, executando Travessia Cypher Multi-hop e ancorando resposta..."):
        resultado = gerar_resposta_graphrag(pergunta_usuario)

    col_esq, col_dir = st.columns([1.15, 1])

    with col_esq:
        st.subheader("💡 Resposta Ancorada no Grafo (Grounding Semântico)")
        st.info(resultado["resposta"])

        st.subheader("🛡️ Métricas de Rastreabilidade e Proveniência (Provenance)")
        m1, m2, m3 = st.columns(3)
        m1.metric("Nível de Confiança Híbrida", f"{resultado['confianca']:.2%}")
        m2.metric("Nós Âncora Consultados", len(resultado["nos_ancora"]))
        m3.metric("Caminhos Multi-hop", len(resultado["subgrafo"]))

        st.markdown("**📌 Lista de Nós Âncora Identificados:**")
        st.code(", ".join(resultado["nos_ancora"]) if resultado["nos_ancora"] else "Nenhum")

        with st.expander("📄 Ver Caminhos Completos do Subgrafo (Contexto enviado ao LLM)", expanded=True):
            st.text(resultado["contexto_texto"])

        with st.expander("⚙️ Ver Consulta Cypher Híbrida Executada no Neo4j"):
            st.code(resultado["cypher_executada"], language="cypher")

    with col_dir:
        st.subheader("🕸️ Visualização Interativa do Subgrafo de Contexto")
        if resultado["subgrafo"]:
            html_grafo = renderizar_subgrafo_interativo(resultado["subgrafo"])
            components.html(html_grafo, height=540, scrolling=False)
            st.caption("Dica: Arraste os nós, use o scroll do mouse para zoom e passe o cursor para ver os rótulos LPG.")
        else:
            st.warning("Nenhum subgrafo retornado para visualização.")