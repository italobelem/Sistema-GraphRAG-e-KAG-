# Arquitetura Híbrida de GraphRAG e KAG para Mitigação de Alucinações e Raciocínio Multi-hop em Inteligência de Ameaças Cibernéticas

**Autor:** Ítalo Belém  
**Curso:** Bacharelado em Ciência da Computação (P8)  
**Disciplina:** Tendências em Ciência da Computação (2026)  
**Docente Responsável:** Prof. Ricardo Roberto de Lima  

---

## Resumo
*Modelos de Linguagem de Grande Porte (LLMs) apresentam limitações críticas em domínios de alta precisão devido a alucinações, ausência de rastreabilidade (provenance) e incapacidade de conectar fatos dispersos em múltiplos documentos (multi-hop reasoning). Este artigo apresenta a concepção, implementação e avaliação de um sistema de Geração Aumentada por Recuperação Baseada em Grafos de Conhecimento (GraphRAG & KAG) aplicado à Inteligência de Ameaças Cibernéticas (CTI). A arquitetura proposta combina extração estruturada de Entidades e Relações (NER/RE) com resolução canônica de entidades, armazenamento em modelo Labeled Property Graph (LPG) no Neo4j, enriquecimento topológico via algoritmos PageRank e Louvain (GDS), geração de consultas Text-to-Cypher e busca híbrida (vetorial, fulltext e travessia Cypher multi-hop). Os experimentos demonstram que a abordagem resolve consultas de até três saltos relacionais com 100% de rastreabilidade de fonte, superando a fragmentação semântica do RAG vetorial puro.*

**Palavras-chave:** GraphRAG, Knowledge-Augmented Generation (KAG), Neo4j, Labeled Property Graph, Multi-hop Reasoning, Cyber Threat Intelligence.

---

## 1. Introdução
O avanço dos Modelos de Linguagem de Grande Porte (LLMs) trouxe ganhos expressivos em tarefas de processamento de linguagem natural, mas desafios persistentes como alucinações, falhas em raciocínio multietapa (*multi-hop reasoning*) e falta de rastreabilidade limitam sua aplicação em domínios críticos como a Inteligência de Ameaças Cibernéticas (*Cyber Threat Intelligence* — CTI). Arquiteturas tradicionais de *Retrieval-Augmented Generation* (RAG) baseadas exclusivamente em buscas vetoriais recuperam fragmentos textuais isolados por similaridade de cosseno, falhando quando a resposta exige conectar entidades e relacionamentos não explícitos distribuídos em múltiplos documentos.

Para superar essa limitação, este trabalho apresenta uma arquitetura de produção fundamentada nos paradigmas **GraphRAG** (*Graph-Augmented Retrieval-Augmented Generation*) e **KAG** (*Knowledge-Augmented Generation*). O sistema extrai estruturas de conhecimento explícitas de relatórios técnicos não estruturados e as persiste em um Grafo de Propriedades Rotulado (*Labeled Property Graph* — LPG) no banco de dados orientado a grafos **Neo4j**, aplicando restrições semânticas e travessia estruturada para ancorar a geração textual em fatos verificáveis.

---

## 2. Metodologia e Arquitetura do Sistema
A arquitetura desenvolvida cobre quatro pilares fundamentais:

```text
+-------------------+      +--------------------+      +----------------------+      +----------------------+
|  1. Text-to-Graph | ---> | 2. Neo4j LPG Store | ---> | 3. Hybrid Retrieval  | ---> | 4. Interface & Vis   |
|  (NER/RE + Res.)  |      | (Vector+FT+BTree)  |      | (Vec+Cypher+PageRank)|      | (Streamlit + PyVis)  |
+-------------------+      +--------------------+      +----------------------+      +----------------------+
```

### 2.1. Pipeline Text-to-Graph (NER, RE e Resolução de Entidades)
O corpus experimental é composto por boletins técnicos de CTI descrevendo operações de grupos de Ameaça Persistente Avançada (APTs), artefatos maliciosos (*malwares*), técnicas MITRE ATT&CK, vulnerabilidades (CVEs) e alvos/setores afetados.

A extração automatizada de Entidades Nomeadas (NER) e Relações (RE) utiliza a API Google Gemini (`gemini-3.8-flash`) com validação estrita de esquema via *Pydantic*, acompanhada de um mecanismo resiliente de contingência contra indisponibilidades de rede (HTTP 503). Para evitar a duplicidade de nós equivalentes no grafo, implementou-se um módulo de **Resolução de Entidades (*Entity Resolution / Canonicalization*)**. Menções a sinônimos na literatura de segurança — como *"Cozy Bear"*, *"Midnight Blizzard"* e *"APT29"* — são normalizadas e fundidas via operações `MERGE` no identificador canônico único `APT29`, preservando os codinomes na propriedade matricial `aliases`. De forma análoga, *"HIDDEN COBRA"* é consolidado em `Lazarus Group`, e *"Fancy Bear"* / *"Strontium"* são unificados em `APT28`.

### 2.2. Modelagem LPG, Constraints e Indexação no Neo4j
O modelo LPG no Neo4j 5 foi estruturado com seis rótulos principais (`Documento`, `GrupoAmeaca`, `Malware`, `Vulnerabilidade`, `Tecnica`, `Alvo`, além do rótulo unificador `:Entidade`) e seis tipos de relacionamento direcionados (`UTILIZA`, `IMPLANTA_TECNICA`, `EXPLORA`, `AFETA`, `ATACA` e `MENCIONADO_EM`).

Para garantir integridade semântica e baixa latência de recuperação, foram implementados:
1. **Constraints de Unicidade:** Aplicadas sobre `Documento.id`, `Vulnerabilidade.cve_id`, `Tecnica.mitre_id` e `nome_canonico` das demais entidades.
2. **Índices Range/B-Tree:** Aplicados às propriedades `severidade_cvss` e `categoria_setor`.
3. **Índice Fulltext (`entidade_fulltext_idx`):** Baseado em Apache Lucene sobre `nome_canonico`, `aliases`, `descricao`, `cve_id` e `mitre_id`.
4. **Índices Vetoriais (`entidade_vector_idx` e `documento_vector_idx`):** Configurados com dimensionalidade 768 (`text-embedding-004`) e função de similaridade de cosseno.

### 2.3. Algoritmos de Grafo e Recuperação Híbrida Multi-hop
Após a ingestão (totalizando 30 nós e 59 relacionamentos verificados), o grafo é projetado na biblioteca **Neo4j Graph Data Science (GDS)** para execução de três algoritmos:
- **PageRank:** Calcula a centralidade e relevância estrutural de cada entidade (20 iterações, fator de amortecimento $d = 0.85$), gravando o escore na propriedade `pagerank`.
- **Louvain (Community Detection):** Identifica agrupamentos modulares de ameaças, gravando o identificador em `comunidade_id`.
- **Shortest Path:** Determina o caminho mínimo entre atores de ameaça e infraestruturas críticas.

O mecanismo de **Recuperação Híbrida (*Hybrid Retrieval*)** opera em três estágios: (i) identificação de nós âncora combinando busca vetorial (`db.index.vector.queryNodes`), busca léxica (`db.index.fulltext.queryNodes`) e resolução de *aliases*; (ii) geração dinâmica de consulta estruturada via LLM (*Text-to-Cypher*); e (iii) travessia *multi-hop* de 1 a 3 saltos (`[r:UTILIZA|IMPLANTA_TECNICA|EXPLORA|AFETA|ATACA*1..3]`) ranqueada pela soma do `pagerank` dos nós do caminho (`path_score`).

### 2.4. Interface Gráfica e Explicabilidade (Provenance)
A interface de usuário foi desenvolvida em **Streamlit** com renderização interativa de grafos via **PyVis**. Para assegurar transparência e auditabilidade, o painel apresenta a resposta fundamentada ao lado do subgrafo interativo de contexto, exibindo o nível de confiança híbrida, a lista de nós âncora consultados, as cadeias relacionais completas e as consultas Cypher geradas e executadas.

---

## 3. Resultados Experimentais e Mitigação de Alucinações
Para validar a capacidade de raciocínio *multi-hop*, avaliou-se a consulta complexa: *"Quais setores e sistemas estão em risco de ataques realizados pelo grupo APT29?"*.

No conjunto de dados, o conhecimento necessário encontra-se distribuído em três documentos distintos:
- **DOC-CTI-001:** Informa que o *Cozy Bear* (`APT29`) utiliza o backdoor `SUNBURST`.
- **DOC-CTI-002:** Relata que o `SUNBURST` explora a vulnerabilidade crítica `CVE-2020-10189` (sem citar o `APT29`).
- **DOC-CTI-003:** Aponta que a `CVE-2020-10189` afeta o sistema `Zoho ManageEngine` no `Setor de Energia Elétrica` e em `Redes Governamentais`.

| Critério Avaliado | RAG Vetorial Puro | Arquitetura GraphRAG / KAG Implementada |
| :--- | :--- | :--- |
| **Resolução de Sinônimos (*Cozy Bear* / *Midnight Blizzard* / *APT29*)** | Inconsistente | **100% Unificado no nó canônico `APT29`** |
| **Profundidade de Raciocínio (*Multi-hop Traversal*)** | 1 salto (restrito ao DOC-001) | **3 saltos completos (DOC-001 $\rightarrow$ DOC-002 $\rightarrow$ DOC-003)** |
| **Identificação do Risco ao Setor de Energia Elétrica** | Falha (não recupera DOC-003) | **Sucesso (`APT29` $\rightarrow$ `SUNBURST` $\rightarrow$ `CVE-2020-10189` $\rightarrow$ `Setor de Energia Elétrica`)** |
| **Grounding Semântico e Proveniência** | Opaco (sem citação de caminho) | **Citação explícita de subgrafos, confiança de 100% e visualização interativa** |

A suíte de testes operacionais automatizados (`pytest`) validou 100% dos requisitos de integridade do schema LPG, presença dos índices, convergência do PageRank e precisão da travessia de 3 saltos em 1,67 segundo.

---

## 4. Conclusão
O sistema GraphRAG e KAG desenvolvido demonstrou na prática como a integração entre bancos de dados orientados a grafos (Neo4j LPG), algoritmos topológicos (GDS) e LLMs soluciona problemas de alucinação e raciocínio multietapa em domínios críticos. A combinação de busca vetorial com travessia Cypher estruturada provê respostas precisas, auditáveis e visualmente explicáveis.

---

## Referências
1. EDGE, D. et al. *From Local to Global: A Graph RAG Approach to Query-Focused Summarization*. arXiv preprint arXiv:2404.16130, 2024.
2. NEO4J. *Neo4j Cypher Manual & Graph Data Science Library Documentation*. Disponível em: https://neo4j.com/docs/. Acesso em: 2026.
3. PAN, S. et al. *Unifying Large Language Models and Knowledge Graphs: A Roadmap*. IEEE Transactions on Knowledge and Data Engineering (TKDE), v. 36, n. 7, p. 3580–3599, 2024.