import sys
import os
import pytest
from neo4j import GraphDatabase

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from src.ingestion.pipeline_ner_re import resolver_entidade_canonica

@pytest.fixture(scope="module")
def neo4j_session():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        yield session
    driver.close()

def test_entity_resolution_canonicalization():
    """Valida se sinônimos de CTI são resolvidos para a mesma entidade canônica."""
    nome1, aliases1 = resolver_entidade_canonica("Cozy Bear")
    nome2, aliases2 = resolver_entidade_canonica("Midnight Blizzard")
    nome3, _ = resolver_entidade_canonica("HIDDEN COBRA")

    assert nome1 == "APT29"
    assert nome2 == "APT29"
    assert "Cozy Bear" in aliases1 and "Midnight Blizzard" in aliases2
    assert nome3 == "Lazarus Group"

def test_neo4j_constraints_and_indexes(neo4j_session):
    """Verifica se as Constraints e Índices (Vector, Fulltext e Range) estão ativos no Neo4j."""
    constraints = neo4j_session.run("SHOW CONSTRAINTS").data()
    indexes = neo4j_session.run("SHOW INDEXES").data()

    nomes_indexes = [idx["name"] for idx in indexes]
    assert len(constraints) >= 6, "Devem existir pelo menos 6 constraints de unicidade LPG."
    assert "entidade_vector_idx" in nomes_indexes, "Índice vetorial de entidades ausente."
    assert "documento_vector_idx" in nomes_indexes, "Índice vetorial de documentos ausente."
    assert "entidade_fulltext_idx" in nomes_indexes, "Índice Fulltext ausente."

def test_lpg_graph_populated_and_pagerank(neo4j_session):
    """Verifica se o grafo possui nós, relações e propriedade PageRank calculada."""
    res_nos = neo4j_session.run("MATCH (e:Entidade) RETURN count(e) AS total, count(e.pagerank) AS com_pr").single()
    assert res_nos["total"] >= 15, "O grafo deve conter as entidades extraídas."
    assert res_nos["com_pr"] > 0, "A propriedade pagerank deve estar gravada nos nós."

def test_multihop_traversal_apt29_to_energy_sector(neo4j_session):
    """Comprova a capacidade de travessia Multi-hop (3 saltos) entre APT29 e Setor de Energia Elétrica."""
    query = """
    MATCH path = (g:GrupoAmeaca {nome_canonico: 'APT29'})-[:UTILIZA]->(m:Malware)-[:EXPLORA]->(v:Vulnerabilidade)-[:AFETA]->(a:Alvo)
    RETURN count(path) AS caminhos, collect(a.nome_canonico) AS alvos
    """
    res = neo4j_session.run(query).single()
    assert res["caminhos"] >= 1, "Deve existir caminho multi-hop de 3 saltos a partir do APT29."
    assert "Setor de Energia Elétrica" in res["alvos"] or "Zoho ManageEngine" in res["alvos"]