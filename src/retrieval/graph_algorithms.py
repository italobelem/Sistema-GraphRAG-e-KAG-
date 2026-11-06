import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from neo4j import GraphDatabase
from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

def executar_algoritmos_gds():
    print("Iniciando algoritmos de Grafo via Neo4j GDS (PageRank + Louvain Community Detection)...")
    with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
        with driver.session() as session:
            # 1. Remove projeção anterior se existir
            session.run("CALL gds.graph.drop('cti_graph', false) YIELD graphName")

            # 2. Projeta o grafo de Entidades na memória do GDS
            session.run("""
                CALL gds.graph.project(
                    'cti_graph',
                    'Entidade',
                    {
                        UTILIZA: {orientation: 'UNDIRECTED'},
                        IMPLANTA_TECNICA: {orientation: 'UNDIRECTED'},
                        EXPLORA: {orientation: 'UNDIRECTED'},
                        AFETA: {orientation: 'UNDIRECTED'},
                        ATACA: {orientation: 'UNDIRECTED'}
                    }
                )
            """)

            # 3. Algoritmo 1: PageRank (Centralidade e Importância)
            pr = session.run("""
                CALL gds.pageRank.write('cti_graph', {
                    maxIterations: 20,
                    dampingFactor: 0.85,
                    writeProperty: 'pagerank'
                })
                YIELD nodePropertiesWritten, ranIterations
                RETURN nodePropertiesWritten, ranIterations
            """).single()
            print(f"[OK] PageRank concluído! {pr['nodePropertiesWritten']} nós atualizados (Iterações: {pr['ranIterations']}).")

            # 4. Algoritmo 2: Louvain (Detecção de Comunidades / Clusters de Ameaça)
            louvain = session.run("""
                CALL gds.louvain.write('cti_graph', {
                    writeProperty: 'comunidade_id'
                })
                YIELD communityCount, modularity
                RETURN communityCount, modularity
            """).single()
            print(f"[OK] Louvain Community Detection concluído! {louvain['communityCount']} comunidades detectadas (Modularidade: {louvain['modularity']:.4f}).")

            # 5. Libera memória do GDS
            session.run("CALL gds.graph.drop('cti_graph') YIELD graphName")

            # 6. Algoritmo 3: Shortest Path (Caminho Mais Curto entre APT29 e Setor de Energia Elétrica)
            sp = session.run("""
                MATCH (origem:Entidade {nome_canonico: 'APT29'}),
                      (destino:Entidade {nome_canonico: 'Setor de Energia Elétrica'}),
                      p = shortestPath((origem)-[:UTILIZA|IMPLANTA_TECNICA|EXPLORA|AFETA|ATACA*..6]-(destino))
                RETURN [n IN nodes(p) | coalesce(n.nome_canonico, n.cve_id, n.mitre_id)] AS caminho_mais_curto,
                       length(p) AS saltos
            """).single()
            if sp:
                print(f"[OK] Shortest Path verificado ({sp['saltos']} saltos): {' -> '.join(sp['caminho_mais_curto'])}")

if __name__ == "__main__":
    executar_algoritmos_gds()