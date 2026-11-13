import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from neo4j import GraphDatabase
from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

def executar_algoritmos_gds():
    print("Iniciando algoritmos de Grafo Médico via Neo4j GDS (PageRank + Louvain + Shortest Path)...")
    with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
        with driver.session() as session:
            session.run("CALL gds.graph.drop('med_graph', false) YIELD graphName")

            session.run("""
                CALL gds.graph.project(
                    'med_graph',
                    'Entidade',
                    {
                        DIAGNOSTICADO_COM: {orientation: 'UNDIRECTED'},
                        CAUSADO_POR: {orientation: 'UNDIRECTED'},
                        TRATADO_COM: {orientation: 'UNDIRECTED'},
                        INTERAGE_COM: {orientation: 'UNDIRECTED'},
                        CONTRAINDICADO_EM: {orientation: 'UNDIRECTED'},
                        CAUSA_RISCO: {orientation: 'UNDIRECTED'}
                    }
                )
            """)

            pr = session.run("""
                CALL gds.pageRank.write('med_graph', {
                    maxIterations: 20,
                    dampingFactor: 0.85,
                    writeProperty: 'pagerank'
                })
                YIELD nodePropertiesWritten, ranIterations
                RETURN nodePropertiesWritten, ranIterations
            """).single()
            print(f"[OK] PageRank concluído! {pr['nodePropertiesWritten']} entidades médicas atualizadas (Iterações: {pr['ranIterations']}).")

            louvain = session.run("""
                CALL gds.louvain.write('med_graph', {
                    writeProperty: 'comunidade_id'
                })
                YIELD communityCount, modularity
                RETURN communityCount, modularity
            """).single()
            print(f"[OK] Louvain Community Detection concluído! {louvain['communityCount']} clusters clínicos detectados (Modularidade: {louvain['modularity']:.4f}).")

            session.run("CALL gds.graph.drop('med_graph') YIELD graphName")

            sp = session.run("""
                MATCH (origem:Entidade {nome_canonico: 'Infarto Agudo do Miocárdio'}),
                      (destino:Entidade {nome_canonico: 'Trombose Aguda de Stent'}),
                      p = shortestPath((origem)-[:DIAGNOSTICADO_COM|CAUSADO_POR|TRATADO_COM|INTERAGE_COM|CONTRAINDICADO_EM|CAUSA_RISCO*..6]-(destino))
                RETURN [n IN nodes(p) | n.nome_canonico] AS caminho_mais_curto,
                       length(p) AS saltos
            """).single()
            if sp:
                print(f"[OK] Shortest Path Clínico verificado ({sp['saltos']} saltos): {' -> '.join(sp['caminho_mais_curto'])}")

if __name__ == "__main__":
    executar_algoritmos_gds()