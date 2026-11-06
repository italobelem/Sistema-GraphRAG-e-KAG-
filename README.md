# 🕸️ Sistema GraphRAG & KAG Aplicado à Inteligência de Ameaças Cibernéticas (CTI)

**Curso:** Bacharelado em Ciência da Computação (P7 / P8)  
**Disciplina:** Tendências em Ciência da Computação (2026)  
**Docente Responsável:** Prof. Ricardo Roberto de Lima  

---

## 📌 1. Visão Geral e Contexto Pedagógico

Este projeto implementa uma arquitetura de nível de produção baseada em **GraphRAG (*Graph-Augmented Retrieval-Augmented Generation*)** e **KAG (*Knowledge-Augmented Generation*)**, integrando o banco de dados orientado a grafos **Neo4j** a **Modelos de Linguagem de Grande Porte (Google Gemini API)**.

O sistema foi projetado para superar três limitações clássicas de LLMs puros e arquiteturas RAG vetoriais tradicionais no domínio crítico de **Cyber Threat Intelligence (CTI)**:
1. **Mitigação de Alucinações (*Grounding Semântico*):** As respostas são estritamente ancoradas em caminhos explícitos e verificáveis extraídos do grafo de conhecimento.
2. **Raciocínio Multietapa (*Multi-hop Reasoning*):** Capacidade de responder a consultas complexas atravessando de $1$ a $3+$ saltos relacionais (ex: `GrupoAmeaca` $\rightarrow$ `Malware` $\rightarrow$ `Vulnerabilidade` $\rightarrow$ `Alvo`), conectando fatos fragmentados em documentos distintos.
3. **Rastreabilidade e Explicabilidade (*Provenance*):** Exibição transparente dos nós âncora consultados, escore de confiança híbrida, consulta Cypher gerada (*Text-to-Cypher* e busca híbrida parametrizada) e renderização visual interativa do subgrafo de contexto.

---

## 🏗️ 2. Arquitetura do Sistema (Os 4 Pilares Obrigatórios)

```text
+-------------------+      +--------------------+      +----------------------+      +----------------------+
|  1. Text-to-Graph | ---> | 2. Neo4j LPG Store | ---> | 3. Hybrid Retrieval  | ---> | 4. Interface & Vis   |
|  (NER/RE + Res.)  |      | (Vector+FT+BTree)  |      | (Vec+Cypher+PageRank)|      | (Streamlit + PyVis)  |
+-------------------+      +--------------------+      +----------------------+      +----------------------+
```

### 2.1. Pipeline Text-to-Graph (NER, RE e Resolução de Entidades)
- **Extração Estruturada (`src/ingestion/pipeline_ner_re.py`):** Extração automatizada de Entidades Nomeadas (NER) e Relações (RE) a partir de boletins técnicos não estruturados utilizando a API Google Gemini com validação estrita via *Pydantic* e mecanismo resiliente de contingência contra indisponibilidades de rede (HTTP 503).
- **Resolução de Entidades (*Entity Resolution / Canonicalization*):** Normalização e fusão canônica de sinônimos e codinomes da indústria de cibersegurança para evitar duplicidade de nós no grafo:
  - *"Cozy Bear"*, *"Midnight Blizzard"* e *"APT29"* $\rightarrow$ Consolidados no nó único `APT29`.
  - *"HIDDEN COBRA"* e *"Lazarus Group"* $\rightarrow$ Consolidados em `Lazarus Group`.
  - *"Fancy Bear"*, *"Strontium"* e *"APT28"* $\rightarrow$ Consolidados em `APT28`.

### 2.2. Modelagem LPG no Neo4j (`src/database/setup_schema.py`)
Implementação rigorosa do modelo **LPG (*Labeled Property Graph*)**:
- **Rótulos de Nós (*Labels*):** `:Documento`, `:GrupoAmeaca`, `:Malware`, `:Vulnerabilidade`, `:Tecnica`, `:Alvo` (agrupados sob o supertipo `:Entidade`).
- **Tipos de Relacionamento (*Relationship Types*):** `[:UTILIZA]`, `[:IMPLANTA_TECNICA]`, `[:EXPLORA]`, `[:AFETA]`, `[:ATACA]` e `[:MENCIONADO_EM]`.
- **Constraints de Unicidade:** Aplicadas sobre `Documento.id`, `GrupoAmeaca.nome_canonico`, `Malware.nome_canonico`, `Vulnerabilidade.cve_id`, `Tecnica.mitre_id` e `Alvo.nome_canonico`.
- **Três Categorias de Índices Ativos:**
  1. **Índices Range / B-Tree:** Indexação de propriedades seletivas (`severidade_cvss`, `categoria_setor`) e chaves de constraints.
  2. **Índice Fulltext (`entidade_fulltext_idx`):** Busca léxica via Apache Lucene sobre `nome_canonico`, `aliases`, `descricao`, `cve_id` e `mitre_id`.
  3. **Índices Vetoriais (`entidade_vector_idx` e `documento_vector_idx`):** Busca semântica por similaridade de cosseno em *embeddings* de $768$ dimensões (`text-embedding-004`).

### 2.3. Recuperação Híbrida, Algoritmos de Grafo e Multi-hop Traversal
- **Algoritmos de Grafo via Neo4j GDS (`src/retrieval/graph_algorithms.py`):**
  - **PageRank:** Calcula a centralidade e relevância estrutural de cada entidade ($20$ iterações, $\text{damping factor} = 0.85$), gravando a propriedade `pagerank`.
  - **Louvain (*Community Detection*):** Detecta comunidades e agrupamentos de ameaças, gravando a propriedade `comunidade_id`.
  - **Shortest Path:** Determina o caminho mais curto entre atores de ameaça e infraestruturas críticas.
- **Busca Híbrida e Text-to-Cypher (`src/retrieval/hybrid_retriever.py`):** Combina busca vetorial (similaridade de cosseno) + busca no índice Fulltext + verificação de *aliases* para localizar nós âncora, expandindo a travessia Cypher por $1$ a $3$ saltos ponderada pelo `pagerank`, além de módulo **Text-to-Cypher** via LLM.

### 2.4. Interface Gráfica e Explicabilidade (`src/ui/app.py`)
- Construída em **Streamlit** com renderização interativa do subgrafo em **PyVis** (física *Barnes-Hut*, zoom, arraste de nós e codificação visual por cores de rótulo LPG).
- Painel transparente de **Rastreabilidade (*Provenance*)** exibindo: Nível de Confiança Híbrida, Nós Âncora Consultados, Caminhos Multi-hop Verificados e as Consultas Cypher geradas/executadas.

---

## 📂 3. Estrutura do Repositório

```text
graphrag-cti/
├── data/
│   └── cti_reports.json         # Corpus de relatórios técnicos CTI (gerado automaticamente)
├── docs/
│   └── artigo_sbc_graphrag.md   # Artigo Técnico completo no padrão SBC/IEEE
├── src/
│   ├── __init__.py
│   ├── config.py                # Gerenciamento centralizado de variáveis de ambiente
│   ├── database/
│   │   ├── __init__.py
│   │   └── setup_schema.py      # [Fase 1] Criação do Schema LPG, Constraints e Índices
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── dataset_generator.py # [Fase 2] Gerador do dataset de relatórios CTI
│   │   └── pipeline_ner_re.py   # [Fase 2] Extração NER/RE, Embeddings e Entity Resolution
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── graph_algorithms.py  # [Fase 3] Algoritmos GDS (PageRank, Louvain, Shortest Path)
│   │   └── hybrid_retriever.py  # [Fase 3] Busca Híbrida, Multi-hop, Text-to-Cypher e Grounding
│   └── ui/
│       └── app.py               # [Fase 4] Interface Streamlit + Renderização PyVis + Provenance
├── tests/
│   └── test_project.py          # [Fase 4] Suíte de testes operacionais automatizados (Pytest)
├── .env.example                 # Template de variáveis de ambiente
├── .gitignore                   # Exclusão de venv, dados locais do Neo4j e credenciais
├── docker-compose.yml           # Container Neo4j 5.23 configurado com APOC e GDS
├── requirements.txt             # Dependências Python do projeto
└── README.md                    # Documentação técnica e guia de execução/deploy
```

---

## 🚀 4. Instruções de Reprodução e Execução Local

### 4.1. Pré-requisitos
- **Python 3.11+** (testado em Python 3.12)
- **Docker Desktop** instalado e em execução (*Engine running*)
- Chave de API do Google Gemini ([Google AI Studio](https://aistudio.google.com/apikey))

### 4.2. Configuração do Ambiente
1. **Clone o repositório e acesse o diretório do projeto:**
   ```bash
   git clone <URL_DO_REPOSITORIO>
   cd graphrag-cti
   ```

2. **Crie e ative o ambiente virtual Python (`venv`):**
   - **Windows (PowerShell):**
     ```powershell
     python -m venv venv
     .\venv\Scripts\activate
     ```
   - **Linux / macOS:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   pip install --upgrade google-genai
   ```

4. **Configure o arquivo `.env`:**
   Crie um arquivo `.env` na raiz do projeto (baseado no `.env.example`) com o seguinte conteúdo:
   ```env
   NEO4J_URI=bolt://127.0.0.1:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=senha_forte_123
   GEMINI_API_KEY=COLE_SUA_CHAVE_AQUI
   EMBEDDING_DIMENSION=768
   ```

### 4.3. Inicialização do Banco de Dados e Execução das Fases
1. **Inicie o container do Neo4j (com plugins APOC e GDS):**
   ```powershell
   docker compose up -d
   ```
   *(Aguarde cerca de 30 a 45 segundos na primeira execução para a inicialização completa do Neo4j. O painel do Neo4j Browser estará acessível em `http://localhost:7474` com login `neo4j` e senha `senha_forte_123`).*

2. **Fase 1 — Configurar o Schema LPG, Constraints e Índices:**
   ```powershell
   python src/database/setup_schema.py
   ```

3. **Fase 2 — Gerar Dataset e Executar Pipeline de Ingestão (NER/RE + Entity Resolution):**
   ```powershell
   python src/ingestion/pipeline_ner_re.py
   ```

4. **Fase 3 — Executar Algoritmos de Grafo (GDS) e Validar Motor Híbrido Multi-hop:**
   ```powershell
   python src/retrieval/graph_algorithms.py
   python src/retrieval/hybrid_retriever.py
   ```

5. **Fase 4 — Executar Testes Operacionais e Iniciar a Interface Gráfica:**
   ```powershell
   pytest -v
   streamlit run src/ui/app.py
   ```
   A interface web abrirá automaticamente em **`http://localhost:8501`**.

---

## ☁️ 5. Instruções para Deployment em Nuvem (Opcional)

O sistema suporta implantação em nuvem utilizando **Neo4j AuraDB** + **Streamlit Community Cloud**:
1. Crie uma instância gratuita no **Neo4j AuraDB** (ou instância com GDS habilitado).
2. Substitua as variáveis `NEO4J_URI` (ex: `neo4j+s://xxxx.databases.neo4j.io`), `NEO4J_USER` e `NEO4J_PASSWORD` no `.env` (ou no painel *Secrets* do Streamlit Cloud).
3. Execute `setup_schema.py` e `pipeline_ner_re.py` apontando para a instância em nuvem.
4. Conecte o repositório GitHub ao **Streamlit Community Cloud** apontando para o arquivo principal `src/ui/app.py`.

---

## 🤖 6. Uso do Agente Mentor Técnico (System Prompt Oficial)

Em conformidade com a **Seção 2 da Especificação Técnica e Pedagógica**, o desenvolvimento, a modelagem conceitual LPG, a resolução de entidades e a construção das queries híbridas seguiram as diretrizes do **Mentor Técnico Especialista em GraphRAG e KAG**, priorizando:
- Rigor técnico no modelo LPG e uso combinado de índices *Vector*, *Fulltext* e *Range/B-Tree*;
- Foco estrito na redução de alucinações via *grounding* semântico e citação explícita dos caminhos do subgrafo;
- Arquitetura híbrida unindo *embeddings* vetoriais, travessia Cypher multi-hop e algoritmos clássicos de grafos (*PageRank*, *Louvain* e *Shortest Path*).

---

## 📚 7. Atribuição e Créditos de Bibliotecas Open-Source

Em cumprimento às normas acadêmicas de atribuição da disciplina, este projeto utiliza e credita as seguintes tecnologias e bibliotecas:
- **[Neo4j Database, APOC & Graph Data Science (GDS)](https://neo4j.com/):** Armazenamento LPG, busca vetorial/fulltext nativa e algoritmos de centralidade/comunidades.
- **[Neo4j Python Driver (`neo4j`)](https://pypi.org/project/neo4j/):** Comunicação via protocolo Bolt.
- **[Google GenAI SDK (`google-genai`)](https://pypi.org/project/google-genai/):** Geração de *embeddings* (`text-embedding-004`) e extração/síntese com modelos Gemini.
- **[Pydantic (`pydantic`)](https://docs.pydantic.dev/):** Validação formal de esquemas de dados para o pipeline NER/RE.
- **[Streamlit (`streamlit`)](https://streamlit.io/) & [PyVis (`pyvis`)](https://pyvis.readthedocs.io/):** Construção da interface de usuário e renderização interativa de redes baseadas em *Vis.js*.
- **[Pytest (`pytest`)](https://docs.pytest.org/):** Framework de testes operacionais automatizados.