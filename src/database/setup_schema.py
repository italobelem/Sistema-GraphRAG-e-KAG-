import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from neo4j import GraphDatabase
from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, EMBEDDING_DIMENSION

DDL_QUERIES = [
    # 1. Constraints de Unicidade (Garantia de Integridade LPG)
    "CREATE CONSTRAINT doc_id_unique IF NOT EXISTS FOR (d:Documento) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT entidade_nome_unique IF NOT EXISTS FOR (e:Entidade) REQUIRE e.nome_canonico IS UNIQUE",
    "CREATE CONSTRAINT paciente_nome_unique IF NOT EXISTS FOR (p:Paciente) REQUIRE p.nome_canonico IS UNIQUE",
    "CREATE CONSTRAINT doenca_nome_unique IF NOT EXISTS FOR (do:Doenca) REQUIRE do.nome_canonico IS UNIQUE",
    "CREATE CONSTRAINT med_nome_unique IF NOT EXISTS FOR (m:Medicamento) REQUIRE m.nome_canonico IS UNIQUE",

    # 2. Índices Range / B-Tree para filtragem rápida de propriedades
    "CREATE INDEX doenca_cid_idx IF NOT EXISTS FOR (do:Doenca) ON (do.cid10)",
    "CREATE INDEX paciente_idade_idx IF NOT EXISTS FOR (p:Paciente) ON (p.faixa_etaria)",
    "CREATE INDEX med_classe_idx IF NOT EXISTS FOR (m:Medicamento) ON (m.classe_terapeutica)",

    # 3. Índice Fulltext (Apache Lucene) para Busca Léxica Híbrida e Aliases
    """
    CREATE FULLTEXT INDEX entidade_fulltext_idx IF NOT EXISTS
    FOR (n:Entidade|Doenca|Medicamento|Causa|RiscoClinico|Paciente)
    ON EACH [n.nome_canonico, n.descricao, n.cid10, n.classe_terapeutica]
    """,

    # 4. Índices Vetoriais (Similaridade de Cosseno - 768 dimensões)
    f"""
    CREATE VECTOR INDEX entidade_vector_idx IF NOT EXISTS
    FOR (e:Entidade) ON (e.embedding)
    OPTIONS {{indexConfig: {{
        `vector.dimensions`: {EMBEDDING_DIMENSION},
        `vector.similarity_function`: 'cosine'
    }}}}
    """,
    f"""
    CREATE VECTOR INDEX documento_vector_idx IF NOT EXISTS
    FOR (d:Documento) ON (d.embedding)
    OPTIONS {{indexConfig: {{
        `vector.dimensions`: {EMBEDDING_DIMENSION},
        `vector.similarity_function`: 'cosine'
    }}}}
    """
]

def configurar_schema_neo4j(limpar_banco: bool = True):
    print("Conectando ao Neo4j para configurar Schema LPG Médico (Saúde & Diagnóstico)...")
    with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
        with driver.session() as session:
            if limpar_banco:
                print("-> Limpando nós e relacionamentos antigos para recriar base médica limpa...")
                session.run("MATCH (n) DETACH DELETE n")
                # Remove índices fulltext/vector antigos caso mudem de definição
                try:
                    session.run("DROP INDEX entidade_fulltext_idx IF EXISTS")
                except Exception:
                    pass

            for query in DDL_QUERIES:
                session.run(query)

            constraints = session.run("SHOW CONSTRAINTS").data()
            indexes = session.run("SHOW INDEXES").data()
            print(f"[FASE 1 CONCLUÍDA] Schema LPG configurado: {len(constraints)} Constraints e {len(indexes)} Índices ativos.")

if __name__ == "__main__":
    configurar_schema_neo4j(limpar_banco=True)