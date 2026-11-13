import sys
import os
import re
from collections import defaultdict
from google import genai
from google.genai import types
from neo4j import GraphDatabase

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from src.ingestion.pipeline_ner_re import inicializar_cliente_gemini, gerar_embedding

EXPANSAO_CLINICA = {
    "cardiac": "Infarto Agudo do Miocárdio",
    "coracao": "Infarto Agudo do Miocárdio",
    "coração": "Infarto Agudo do Miocárdio",
    "estomago": "Úlcera Péptica Gástrica",
    "estômago": "Úlcera Péptica Gástrica",
    "gastr": "Úlcera Péptica Gástrica",
    "pulm": "Asma Brônquica Alérgica",
    "respirat": "Asma Brônquica Alérgica",
    "crianca": "Asma Brônquica Alérgica",
    "criança": "Asma Brônquica Alérgica",
    "pediatr": "Asma Brônquica Alérgica",
    "mosquito": "Dengue Clássica com Sinais de Alarme",
    "febre": "Dengue Clássica com Sinais de Alarme",
    "renal": "Nefropatia Diabética Crônica",
    "rim": "Nefropatia Diabética Crônica",
    "rins": "Nefropatia Diabética Crônica",
    "diabet": "Diabetes Mellitus Tipo 2",
    "cabeca": "Enxaqueca Crônica com Aura",
    "cabeça": "Enxaqueca Crônica com Aura",
    "neuro": "Enxaqueca Crônica com Aura",
}

CYPHER_HYBRID_QUERY = """
// 1. Busca Híbrida: Índice Vetorial (Cosseno) + Índice Fulltext (Lucene) + Aliases Médicos
CALL db.index.vector.queryNodes('entidade_vector_idx', 4, $embedding) YIELD node AS vec_node, score AS vec_score
WITH collect({no: vec_node, score: vec_score}) AS vec_results

CALL db.index.fulltext.queryNodes('entidade_fulltext_idx', $fulltext_query) YIELD node AS ft_node, score AS ft_score
WITH vec_results, collect({no: ft_node, score: CASE WHEN ft_score > 1.0 THEN 1.0 ELSE ft_score END}) AS ft_results

OPTIONAL MATCH (lex_node:Entidade)
WHERE toLower($query_expanded) CONTAINS toLower(coalesce(lex_node.nome_canonico, '___'))
   OR toLower($query_expanded) CONTAINS toLower(coalesce(lex_node.cid10, '___'))
   OR any(alias IN coalesce(lex_node.aliases, []) WHERE toLower($query_expanded) CONTAINS toLower(alias))
WITH vec_results, ft_results, collect({no: lex_node, score: 1.0}) AS lex_results

UNWIND (lex_results + ft_results + vec_results) AS item
WITH item WHERE item.no IS NOT NULL
WITH item.no AS ancora, max(item.score) AS score
ORDER BY score DESC LIMIT 3

// 2. Recupera os PDFs vinculados às âncoras
OPTIONAL MATCH (ancora)-[:MENCIONADO_EM]->(doc:Documento)
WITH ancora, score, collect(DISTINCT doc.arquivo_pdf) AS pdfs_ancora

// 3. Travessia Multi-hop (1 a 3 saltos) ponderada pelo PageRank
MATCH path = (ancora)-[:DIAGNOSTICADO_COM|CAUSADO_POR|TRATADO_COM|INTERAGE_COM|CONTRAINDICADO_EM|CAUSA_RISCO*1..3]-(vizinho:Entidade)
WHERE all(n IN nodes(path) WHERE 'Entidade' IN labels(n))
WITH ancora, score, pdfs_ancora, path,
     reduce(peso = 0.0, n IN nodes(path) | peso + coalesce(n.pagerank, 0.15)) AS path_score
ORDER BY score DESC, length(path) DESC, path_score DESC LIMIT 20

RETURN collect(DISTINCT {
    nos: [n IN nodes(path) | n.nome_canonico],
    tipos: [n IN nodes(path) | [lbl IN labels(n) WHERE lbl <> 'Entidade'][0]],
    passos: [rel IN relationships(path) | {
        origem: startNode(rel).nome_canonico,
        relacao: type(rel),
        destino: endNode(rel).nome_canonico,
        pdf: coalesce(rel.fonte_pdf, 'Base PDF')
    }]
}) AS subgrafo,
collect(DISTINCT ancora.nome_canonico) AS nos_ancora,
collect(DISTINCT pdfs_ancora) AS pdfs_consultados,
avg(score) AS confianca_media
"""

def expandir_termos_clinicos(pergunta: str) -> str:
    q_lower = pergunta.lower()
    extras = [canon for chave, canon in EXPANSAO_CLINICA.items() if chave in q_lower]
    if extras:
        return f"{pergunta} ({', '.join(set(extras))})"
    return pergunta

def gerar_cypher_via_llm(pergunta: str, client: genai.Client, nos_ancora: list) -> str:
    prompt_cypher = f"""
    Gere APENAS uma consulta Cypher válida para Neo4j 5 (sem blocos markdown) que responda à pergunta clínica abaixo.
    Schema LPG de Saúde:
    - Labels: Paciente, Doenca, Causa, Medicamento, RiscoClinico, Documento, Chunk
    - Propriedades: nome_canonico, aliases, cid10, faixa_etaria, classe_terapeutica, pagerank
    - Relações: DIAGNOSTICADO_COM, CAUSADO_POR, TRATADO_COM, INTERAGE_COM, CONTRAINDICADO_EM, CAUSA_RISCO, MENCIONADO_EM
    Nós âncora identificados: {nos_ancora}
    Pergunta: {pergunta}
    """
    for modelo in ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-1.5-flash"]:
        try:
            resp = client.models.generate_content(
                model=modelo,
                contents=prompt_cypher,
                config=types.GenerateContentConfig(temperature=0.0)
            )
            cypher_limpa = resp.text.replace("```cypher", "").replace("```", "").strip()
            if "MATCH" in cypher_limpa.upper():
                return cypher_limpa
        except Exception:
            continue

    ancora = nos_ancora[0] if nos_ancora else "Infarto Agudo do Miocárdio"
    return (
        f"MATCH path = (a:Entidade)-[:DIAGNOSTICADO_COM|CAUSADO_POR|TRATADO_COM|INTERAGE_COM|CONTRAINDICADO_EM|CAUSA_RISCO*1..3]-(b:Entidade)\n"
        f"WHERE a.nome_canonico = '{ancora}' OR '{ancora}' IN coalesce(a.aliases, [])\n"
        f"OPTIONAL MATCH (a)-[:MENCIONADO_EM]->(d:Documento)\n"
        f"RETURN [n IN nodes(path) | n.nome_canonico] AS cadeia_clinica, collect(DISTINCT d.arquivo_pdf) AS prontuarios_pdf\n"
        f"ORDER BY length(path) DESC LIMIT 15;"
    )

def sintetizar_resposta_legivel(pergunta: str, subgrafo: list, nos_ancora: list) -> str:
    """Gera um Resumo Direto da pergunta seguido de bullet points curtos, agrupados e ordenados."""
    pacientes_map = defaultdict(set)
    causas_map = defaultdict(set)
    tratamentos_map = defaultdict(set)
    alertas_lista = set()
    docs_envolvidos = set()

    for item in subgrafo:
        for p in item.get("passos", []):
            orig, rel, dest, pdf = p["origem"], p["relacao"], p["destino"], p["pdf"]
            docs_envolvidos.add(pdf)

            if rel == "DIAGNOSTICADO_COM":
                pacientes_map[orig].add(f"**{dest}** (`{pdf}`)")
            elif rel == "CAUSADO_POR":
                causas_map[orig].add(f"{dest} (`{pdf}`)")
            elif rel == "TRATADO_COM":
                tratamentos_map[orig].add(f"{dest} (`{pdf}`)")
            elif rel == "INTERAGE_COM":
                alertas_lista.add(f"**Interação:** `{orig}` ↔ `{dest}` *(risco farmacológico cruzado — {pdf})*")
            elif rel == "CONTRAINDICADO_EM":
                alertas_lista.add(f"**Contraindicação:** `{orig}` é proibido em **{dest}** *({pdf})*")
            elif rel == "CAUSA_RISCO":
                alertas_lista.add(f"**Risco Clínico:** `{orig}` pode desencadear **{dest}** *({pdf})*")

    # 1. Bloco de Resumo Executivo da Pergunta
    foco_principal = nos_ancora[0] if nos_ancora else "entidades clínicas"
    docs_str = ", ".join(sorted(docs_envolvidos)) if docs_envolvidos else "Base PDF"

    resumo_linhas = [
        f"**📌 Resumo da Consulta:** Para a pergunta *\"{pergunta}\"*, o grafo rastreou **{foco_principal}** "
        f"cruzando **{len(docs_envolvidos)} prontuários PDF** (`{docs_str}`)."
    ]

    if pacientes_map:
        pac_str = "; ".join([f"{pac} com {', '.join(sorted(diags))}" for pac, diags in sorted(pacientes_map.items())])
        resumo_linhas.append(f"Paciente(s) identificado(s): {pac_str}.")
    elif alertas_lista:
        resumo_linhas.append(f"Foram detectados **{len(alertas_lista)} alertas clínicos** de interação ou contraindicação entre os prontuários.")

    blocos = ["\n\n".join(resumo_linhas)]

    # 2. Listas Ordenadas e Agrupadas (Máx. 4 itens por categoria para leitura rápida)
    if pacientes_map:
        itens = [f"1. **{pac}** → Diagnóstico: {', '.join(sorted(diags))}" for pac, diags in sorted(pacientes_map.items())][:4]
        blocos.append("**👤 Pacientes e Diagnósticos**\n" + "\n".join(itens))

    if tratamentos_map:
        itens = [f"- **{doenca}:** tratado com {', '.join(sorted(meds))}" for doenca, meds in sorted(tratamentos_map.items())][:4]
        blocos.append("**💊 Conduta e Tratamentos**\n" + "\n".join(itens))

    if causas_map:
        itens = [f"- **{doenca}:** causado por {', '.join(sorted(cs))}" for doenca, cs in sorted(causas_map.items())][:4]
        blocos.append("**🧬 Causas e Fatores Etiológicos**\n" + "\n".join(itens))

    if alertas_lista:
        itens = [f"- {alerta}" for alerta in sorted(alertas_lista)][:5]
        blocos.append("**⚠️ Alertas e Interações Multi-hop**\n" + "\n".join(itens))

    return "\n\n".join(blocos)

def buscar_contexto_hibrido(query: str, client: genai.Client) -> dict:
    query_expandida = expandir_termos_clinicos(query)
    query_embedding = gerar_embedding(client, query_expandida)
    termos_limpos = re.sub(r"[^\w\s]", " ", query_expandida).strip() or "Infarto"

    linhas_contexto = []
    subgrafo_bruto = []
    nos_ancora = []
    pdfs_lista = set()
    confianca = 0.0

    with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
        with driver.session() as session:
            result = session.run(
                CYPHER_HYBRID_QUERY,
                embedding=query_embedding,
                fulltext_query=termos_limpos,
                query_expanded=query_expandida
            ).single()

            if result and result["subgrafo"]:
                subgrafo_bruto = result["subgrafo"]
                nos_ancora = result["nos_ancora"]
                confianca = round(float(result["confianca_media"] or 0.90), 4)

                for sub_lista in (result["pdfs_consultados"] or []):
                    for p in sub_lista:
                        if p:
                            pdfs_lista.add(p)

                for item in subgrafo_bruto:
                    cadeia = " ; ".join(
                        [f"({p['origem']}) -[:{p['relacao']} [{p['pdf']}]]-> ({p['destino']})" for p in item["passos"]]
                    )
                    linhas_contexto.append(cadeia)

    cypher_llm = gerar_cypher_via_llm(query, client, nos_ancora)

    return {
        "contexto_texto": "\n".join(linhas_contexto),
        "subgrafo": subgrafo_bruto,
        "nos_ancora": nos_ancora,
        "pdfs_consultados": sorted(list(pdfs_lista)),
        "confianca": confianca,
        "cypher_executada": f"// [A] Cypher Gerada via Text-to-Cypher (LLM):\n{cypher_llm}\n\n// [B] Cypher Híbrida Executada (Vector + Fulltext + Multi-hop + PageRank):\n{CYPHER_HYBRID_QUERY.strip()}"
    }

def gerar_resposta_graphrag(pergunta: str) -> dict:
    client = inicializar_cliente_gemini()
    dados_busca = buscar_contexto_hibrido(pergunta, client)
    contexto = dados_busca["contexto_texto"]

    if not contexto:
        dados_busca["resposta"] = "Nenhum registro clínico correspondente foi encontrado nos prontuários PDF indexados."
        return dados_busca

    prompt_anti_alucinacao = f"""
    Você é um Assistente de Decisão Clínica baseado em GraphRAG e KAG.
    Formate a resposta EXATAMENTE assim, de forma limpa, curta e sem repetir setas brutas de grafo:
    1. Comece com "**📌 Resumo da Consulta:**" respondendo diretamente em 2 linhas o que o usuário perguntou.
    2. Liste no máximo 4 a 6 bullet points curtos, ordenados por categoria (**👤 Pacientes**, **💊 Tratamentos**, **🧬 Causas**, **⚠️ Alertas Multi-hop**), citando o código do PDF entre parênteses (ex: `DOC-MED-001`).
    Baseie-se EXCLUSIVAMENTE nos dados abaixo:

    {contexto}

    Pergunta: {pergunta}
    """

    resposta_final = None
    for modelo in ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-1.5-flash"]:
        try:
            response = client.models.generate_content(
                model=modelo,
                contents=prompt_anti_alucinacao,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            resposta_final = response.text
            break
        except Exception:
            continue

    if not resposta_final:
        resposta_final = sintetizar_resposta_legivel(
            pergunta,
            dados_busca["subgrafo"],
            dados_busca["nos_ancora"]
        )

    dados_busca["resposta"] = resposta_final
    return dados_busca