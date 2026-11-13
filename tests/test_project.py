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

def test_medical_entity_resolution_canonicalization():
    """Valida se sinônimos clínicos e comerciais são unificados na mesma entidade canônica."""
    doenca1, _ = resolver_entidade_canonica("IAM")
    doenca2, _ = resolver_entidade_canonica("Ataque Cardíaco")
    med1, _ = resolver_entidade_canonica("Tylenol")
    med2, _ = resolver_entidade_canonica("Acetaminofeno")
    med3, _ = resolver_entidade_canonica("Plavix")

    assert doenca1 == "Infarto Agudo do Miocárdio"
    assert doenca2 == "Infarto Agudo do Miocárdio"
    assert med1 == "Paracetamol" and med2 == "Paracetamol"
    assert med3 == "Clopidogrel"

def test_neo4j_constraints_and_indexes(neo4j_session):
    """Verifica se as Constraints e Índices (Vector, Fulltext e Range) estão ativos no Neo4j."""
    constraints = neo4j_session.run("SHOW CONSTRAINTS").data()
    indexes = neo4j_session.run("SHOW INDEXES").data()

    nomes_indexes = [idx["name"] for idx in indexes]
    assert len(constraints) >= 6, "Devem existir pelo menos 6 constraints de unicidade LPG."
    assert "entidade_vector_idx" in nomes_indexes
    assert "documento_vector_idx" in nomes_indexes
    assert "entidade_fulltext_idx" in nomes_indexes

def test_pdfs_and_chunks_ingested_with_pagerank(neo4j_session):
    """Verifica se os 6 PDFs médicos, seus Chunks e o PageRank estão gravados no Neo4j."""
    res_docs = neo4j_session.run("MATCH (c:Chunk)-[:PARTE_DE]->(d:Documento) RETURN count(DISTINCT d) AS pdfs, count(c) AS chunks").single()
    res_pr = neo4j_session.run("MATCH (e:Entidade) RETURN count(e) AS total, count(e.pagerank) AS com_pr").single()

    assert res_docs["pdfs"] >= 6, "Os 6 arquivos PDF médicos devem estar indexados no grafo."
    assert res_docs["chunks"] >= 6, "Os chunks extraídos das páginas dos PDFs devem estar vinculados."
    assert res_pr["com_pr"] > 0, "A propriedade pagerank deve estar calculada nas entidades."

def test_multihop_clinical_interaction_iam_to_ulcer(neo4j_session):
    """Comprova travessia Multi-hop cruzando o PDF de Cardiologia (IAM/Clopidogrel) e o PDF de Gastroenterologia (Úlcera/Omeprazol)."""
    query = """
    MATCH path = (d1:Doenca {nome_canonico: 'Infarto Agudo do Miocárdio'})-[:TRATADO_COM]->(m1:Medicamento {nome_canonico: 'Clopidogrel'})<-[:INTERAGE_COM]-(m2:Medicamento {nome_canonico: 'Omeprazol'})<-[:TRATADO_COM]-(d2:Doenca {nome_canonico: 'Úlcera Péptica Gástrica'})
    RETURN count(path) AS caminhos
    """
    res = neo4j_session.run(query).single()
    assert res["caminhos"] >= 1, "Deve existir caminho multi-hop conectando IAM -> Clopidogrel <- Omeprazol <- Úlcera Péptica."