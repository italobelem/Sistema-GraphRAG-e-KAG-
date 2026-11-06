import sys
import os

# Permite importar src.config mesmo rodando o script diretamente
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from neo4j import GraphDatabase
from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, EMBEDDING_DIMENSION

DDL_QUERIES = [
    # 1. CONSTRAINTS DE UNICIDADE (Garantem integridade e criam índices B-Tree/Range implícitos)
    "CREATE CONSTRAINT doc_id_unique IF NOT EXISTS FOR (d:Documento) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT grupo_nome_unique IF NOT EXISTS FOR (g:GrupoAmeaca) REQUIRE g.nome_canonico IS UNIQUE",
    "CREATE CONSTRAINT malware_nome_unique IF NOT EXISTS FOR (m:Malware) REQUIRE m.nome_canonico IS UNIQUE",
    "CREATE CONSTRAINT vuln_cve_unique IF NOT EXISTS FOR (v:Vulnerabilidade) REQUIRE v.cve_id IS UNIQUE",
    "CREATE CONSTRAINT tecnica_mitre_unique IF NOT EXISTS FOR (t:Tecnica) REQUIRE t.mitre_id IS UNIQUE",
    "CREATE CONSTRAINT alvo_nome_unique IF NOT EXISTS FOR (a:Alvo) REQUIRE a.nome_canonico IS UNIQUE",

    # 2. ÍNDICES RANGE / B-TREE PARA FILTRAGEM DE PROPRIEDADES
    "CREATE INDEX vuln_severidade_idx IF NOT EXISTS FOR (v:Vulnerabilidade) ON (v.severidade_cvss)",
    "CREATE INDEX alvo_setor_idx IF NOT EXISTS FOR (a:Alvo) ON (a.categoria_setor)",

    # 3. ÍNDICE FULLTEXT (Para busca léxica/híbrida em nomes, aliases e códigos CVE/MITRE)
    """
    CREATE FULLTEXT INDEX entidade_fulltext_idx IF NOT EXISTS
    FOR (n:GrupoAmeaca|Malware|Vulnerabilidade|Tecnica|Alvo)
    ON EACH [n.nome_canonico, n.aliases, n.descricao, n.cve_id, n.mitre_id]
    """,

    # 4. ÍNDICES VETORIAIS (Similaridade de cosseno para Nós e Documentos)
    f"""
    CREATE VECTOR INDEX documento_vector_idx IF NOT EXISTS
    FOR (d:Documento) ON (d.embedding)
    OPTIONS {{indexConfig: {{
      `vector.dimensions`: {EMBEDDING_DIMENSION},
      `vector.similarity_function`: 'cosine'
    }}}}
    """,
    f"""
    CREATE VECTOR INDEX entidade_vector_idx IF NOT EXISTS
    FOR (e:Entidade) ON (e.embedding)
    OPTIONS {{indexConfig: {{
      `vector.dimensions`: {EMBEDDING_DIMENSION},
      `vector.similarity_function`: 'cosine'
    }}}}
    """
]

def configurar_schema():
    print(f"Conectando ao Neo4j em {NEO4J_URI}...")
    with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
        driver.verify_connectivity()
        with driver.session() as session:
            for query in DDL_QUERIES:
                session.run(query)
                primeira_linha = query.strip().splitlines()[0]
                print(f"[OK] {primeira_linha}")
    print("\n[FASE 1 CONCLUÍDA] Schema LPG, Constraints e Índices criados com sucesso no Neo4j!")

if __name__ == "__main__":
    configurar_schema()