# 🩺 MedGraph KAG — Sistema GraphRAG & KAG Aplicado à Decisão Clínica sobre Prontuários PDF

**Curso:** Bacharelado em Ciência da Computação (P7 / P8)  
**Disciplina:** Tendências em Ciência da Computação (2026)  
**Docente Responsável:** Prof. Ricardo Roberto de Lima  
**Autor:** Ítalo Belém  
**Repositório Oficial:** [github.com/italobelem/Sistema-GraphRAG-e-KAG-](https://github.com/italobelem/Sistema-GraphRAG-e-KAG-)

---

## 📌 1. Visão Geral e Contexto Pedagógico

Este projeto implementa uma arquitetura completa de **GraphRAG (*Graph-Augmented Retrieval-Augmented Generation*)** e **KAG (*Knowledge-Augmented Generation*)**, integrando o banco de dados orientado a grafos **Neo4j** a **Modelos de Linguagem de Grande Porte (Google Gemini API)** para suporte à decisão clínica a partir de **prontuários médicos eletrônicos em PDF**.

O sistema foi projetado para superar três limitações críticas de LLMs puros e arquiteturas RAG vetoriais tradicionais no domínio crítico da **Saúde e Farmacologia Clínica**:

1. **Mitigação de Alucinações (*Grounding Semântico*):** Toda resposta clínica é estritamente ancorada em caminhos verificáveis extraídos do subgrafo do Neo4j, citando explicitamente o código e o arquivo PDF de origem de cada evidência.
2. **Raciocínio Multietapa (*Multi-hop Reasoning*):** Capacidade de navegar por $1$ a $3+$ saltos relacionais entre diferentes prontuários PDF (ex: `Paciente` $\rightarrow$ `Doenca` $\rightarrow$ `Medicamento` $\leftrightarrow$ `Medicamento` $\rightarrow$ `RiscoClinico`), revelando interações medicamentosas e contraindicações ocultas em buscas vetoriais isoladas.
3. **Rastreabilidade e Explicabilidade (*Provenance*):** Exibição transparente das entidades âncora identificadas via *Entity Resolution*, nível de confiança híbrida, arquivos PDF consultados, consultas Cypher (*Text-to-Cypher* e busca híbrida parametrizada) e visualização interativa do subgrafo.

---

## 🏗️ 2. Arquitetura do Sistema (Os 4 Pilares Obrigatórios)

```text
+-----------------------+      +----------------------+      +-----------------------+      +-----------------------+
|  1. PDF Text-to-Graph | ---> |  2. Neo4j LPG Store  | ---> |  3. Hybrid Retrieval  | ---> | 4. Interface & Vis    |
| (pypdf+Chunks+NER/RE) |      | (Vector+FT+BTree)    |      | (Vec+Cypher+PageRank) |      | (Streamlit 3 Abas)    |
+-----------------------+      +----------------------+      +-----------------------+      +-----------------------+
```

### 2.1. Pipeline Text-to-Graph sobre PDFs (`src/ingestion/pipeline_ner_re.py`)
* **Leitura de PDFs e Segmentação (*Chunking com Overlap*):** Extração automatizada de texto de múltiplas páginas utilizando `pypdf` sobre os prontuários armazenados em `data/pdfs/` (ou enviados via *upload* ao vivo na interface), dividindo cada documento em blocos sobrepostos (`(:Chunk)-[:PARTE_DE]->(:Documento)`).
* **Extração NER/RE Estruturada:** Extração de entidades e relações clínicas via **Google Gemini API** validada com *Pydantic* (`GrafoExtraido`), acompanhada de extrator determinístico de contingência para garantir alta disponibilidade mesmo sob picos de demanda (HTTP 503).
* **Resolução de Entidades (*Entity Resolution / Canonicalization*):** Normalização e fusão canônica de sinônimos médicos, siglas CID-10 e nomes comerciais de fármacos para evitar duplicidade de nós no grafo:
  * *"IAM"*, *"Ataque Cardíaco"* $\rightarrow$ Consolidados no nó único `Infarto Agudo do Miocárdio`.
  * *"Tylenol"*, *"Acetaminofeno"* $\rightarrow$ Consolidados em `Paracetamol`.
  * *"Plavix"* $\rightarrow$ `Clopidogrel` | *"Losec"* $\rightarrow$ `Omeprazol` | *"Glifage"* $\rightarrow$ `Metformina` | *"Aerolin"* $\rightarrow$ `Salbutamol`.
  * *"HAS"*, *"Pressão Alta"* $\rightarrow$ `Hipertensão Arterial Sistêmica` | *"DM2"* $\rightarrow$ `Diabetes Mellitus Tipo 2`.

### 2.2. Modelagem LPG no Neo4j (`src/database/setup_schema.py`)
Implementação rigorosa do modelo **LPG (*Labeled Property Graph*)**:
* **Rótulos de Nós (*Labels*):** `:Documento`, `:Chunk`, `:Paciente`, `:Doenca`, `:Causa`, `:Medicamento` e `:RiscoClinico` (agrupados sob o supertipo `:Entidade`).
* **Tipos de Relacionamento (*Relationship Types*):** `[:DIAGNOSTICADO_COM]`, `[:CAUSADO_POR]`, `[:TRATADO_COM]`, `[:INTERAGE_COM]`, `[:CONTRAINDICADO_EM]`, `[:CAUSA_RISCO]`, `[:MENCIONADO_EM]` e `[:PARTE_DE]`.
* **6 Constraints de Unicidade:** Aplicadas sobre `Documento.id`, `Chunk.id`, `Entidade.nome_canonico`, `Paciente.nome_canonico`, `Doenca.nome_canonico` e `Medicamento.nome_canonico`.
* **Três Categorias de Índices Ativos:**
  1. **Índices Range / B-Tree:** Indexação sobre `Doenca.cid10`, `Paciente.faixa_etaria` e `Medicamento.classe_terapeutica`.
  2. **Índice Fulltext (`entidade_fulltext_idx`):** Busca léxica via Apache Lucene sobre `nome_canonico`, `descricao`, `cid10` e `classe_terapeutica`.
  3. **Índices Vetoriais (`entidade_vector_idx` e `documento_vector_idx`):** Busca semântica por similaridade de cosseno em *embeddings* de $768$ dimensões (`text-embedding-004`).

### 2.3. Algoritmos de Grafo (GDS) e Recuperação Híbrida Multi-hop
* **Algoritmos Topológicos (`src/retrieval/graph_algorithms.py`):**
  * **PageRank:** Calcula a centralidade clínica de cada entidade ($20$ iterações, $\text{damping factor} = 0.85$), gravando `pagerank`.
  * **Louvain (*Community Detection*):** Detecta agrupamentos clínicos e farmacológicos, gravando `comunidade_id`.
  * **Shortest Path:** Determina o caminho mais curto entre uma condição clínica e um evento adverso crítico (ex: `Infarto Agudo do Miocárdio` $\rightarrow$ `Trombose Aguda de Stent`).
* **Busca Híbrida e Text-to-Cypher (`src/retrieval/hybrid_retriever.py`):** Combina expansão de termos clínicos + busca vetorial + busca no índice Fulltext + verificação de *aliases* para ancorar entidades, gerando consultas Cypher via LLM (*Text-to-Cypher*) e percorrendo $1$ a $3$ saltos ponderados pelo `pagerank`.

### 2.4. Interface Gráfica Executiva em 3 Abas (`src/ui/app.py`)
Desenvolvida em **Streamlit** + **PyVis** com tema clínico escuro (Esmeralda & Ciano) e organizada em três abas funcionais:
1. **🩺 Consulta Clínica & Grafo Interativo:** Parecer clínico sintetizado com resumo direto, *bullet points* agrupados, cartões de métricas KPI e grafo interativo colorido por categoria LPG.
2. **📂 Prontuários PDF Indexados (Gestão & Upload):** Tabela dinâmica consultada diretamente do Neo4j exibindo páginas, *chunks* e entidades de cada PDF, além de *uploader* para ingestão de novos prontuários PDF em tempo real.
3. **🔍 Auditoria Multi-hop & Cypher (Provenance):** Exibição completa das triplas extraídas (*grounding*) e das consultas Cypher geradas e executadas.

---

## 📋 3. Base de Conhecimento Clínica (6 Prontuários PDF)

O diretório `data/pdfs/` contém $6$ prontuários médicos eletrônicos de $2$ páginas cada ($12$ páginas no total, segmentadas em $29$ *chunks*), interconectados por relações farmacológicas e etiológicas:

| ID | Arquivo PDF | Paciente (Idade) | Diagnóstico (CID-10) | Causas Principais | Tratamento e Conexão Multi-hop |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DOC-MED-001** | `prontuario01cardiologiaiam.pdf` | **P-01** ($68$a, Masc) | **Infarto Agudo do Miocárdio** (`I21.0`) | Hipertensão Arterial (HAS) e Tabagismo | **Angioplastia (Contraste Iodado)**, **AAS** e **Clopidogrel** |
| **DOC-MED-002** | `prontuario02gastroenterologiaulcera.pdf` | **P-02** ($54$a, Fem) | **Úlcera Péptica Gástrica** (`K25.4`) | *Helicobacter pylori* e uso contínuo de **AAS** | **Omeprazol** *(inibe CYP2C19 e reduz eficácia do Clopidogrel do DOC-001)* |
| **DOC-MED-003** | `prontuario03pneumologiaasma.pdf` | **P-03** ($7$a, Masc) | **Asma Brônquica Alérgica** (`J45.0`) | Alérgenos Domésticos (Ácaros) | **Salbutamol** e **Budesonida** *(contraindicação de Propranolol)* |
| **DOC-MED-004** | `prontuario04infectologiadengue.pdf` | **P-04** ($29$a, Fem) | **Dengue Clássica com Sinais de Alarme** (`A97.1`) | Vírus da Dengue `DENV-2` (*Aedes aegypti*) | Hidratação e **Paracetamol** *(proibição absoluta de AAS por hemorragia)* |
| **DOC-MED-005** | `prontuario05nefrologiadiabetes.pdf` | **P-05** ($61$a, Masc) | **Nefropatia Diabética Crônica** (`E11.2`) | Diabetes Tipo 2 (`DM2`) e **HAS** | **Metformina** e **Losartana** *(risco de Acidose Lática com Contraste do DOC-001)* |
| **DOC-MED-006** | `prontuario06neurologiaenxaqueca.pdf` | **P-06** ($42$a, Fem) | **Enxaqueca Crônica com Aura** (`G43.1`) | Estresse Crônico e Privação de Sono | **Propranolol** *(risco na Asma do DOC-003)*, **Sumatriptano** e **Paracetamol** |

---

## 📂 4. Estrutura do Repositório

```text
graphrag-cti/
├── data/
│   └── pdfs/
│       ├── prontuario01cardiologiaiam.pdf          # Prontuário Cardiologia (2 págs)
│       ├── prontuario02gastroenterologiaulcera.pdf # Prontuário Gastroenterologia (2 págs)
│       ├── prontuario03pneumologiaasma.pdf         # Prontuário Pneumologia Pediátrica (2 págs)
│       ├── prontuario04infectologiadengue.pdf      # Prontuário Infectologia (2 págs)
│       ├── prontuario05nefrologiadiabetes.pdf      # Prontuário Nefrologia/Endócrino (2 págs)
│       └── prontuario06neurologiaenxaqueca.pdf     # Prontuário Neurologia (2 págs)
├── docs/
│   ├── artigo_sbc_graphrag.md                      # Artigo Técnico (Markdown)
│   ├── Artigo_Tecnico_SBC_IEEE_GraphRAG_KAG.pdf    # Artigo Técnico diagramado (PDF)
│   └── Artigo_Tecnico_SBC_IEEE_GraphRAG_KAG.docx   # Artigo Técnico editável (DOCX)
├── src/
│   ├── __init__.py
│   ├── config.py                                   # Carregamento centralizado de variáveis .env
│   ├── database/
│   │   ├── __init__.py
│   │   └── setup_schema.py                         # [Fase 1] Schema LPG Médico, Constraints e Índices
│   ├── ingestion/
│   │   ├── __init__.py
│   │   └── pipeline_ner_re.py                      # [Fase 2] Leitor PDF, Chunking, NER/RE e Entity Resolution
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── graph_algorithms.py                     # [Fase 3] GDS (PageRank, Louvain e Shortest Path)
│   │   └── hybrid_retriever.py                     # [Fase 3] Busca Híbrida, Text-to-Cypher e Síntese Clínica
│   └── ui/
│       └── app.py                                  # [Fase 4] Interface Streamlit em 3 Abas + PyVis
├── tests/
│   └── test_project.py                             # [Fase 4] Suíte de testes automatizados (Pytest)
├── .env.example                                    # Exemplo de configuração de credenciais
├── .gitignore                                      # Proteção de .env, venv e dados locais do Neo4j
├── docker-compose.yml                              # Neo4j 5.23 com plugins APOC e GDS habilitados
├── requirements.txt                                # Dependências Python (incluindo pypdf)
└── README.md                                       # Documentação técnica e guia de execução
```

---

## 🚀 5. Instruções de Reprodução e Execução Local

### 5.1. Pré-requisitos
* **Python 3.11+** (testado em Python 3.12)
* **Docker Desktop** instalado e em execução
* Chave de API do Google Gemini ([Google AI Studio](https://aistudio.google.com/apikey))

### 5.2. Configuração do Ambiente
1. **Clone o repositório e acesse a pasta:**
   ```bash
   git clone https://github.com/italobelem/Sistema-GraphRAG-e-KAG-.git
   cd Sistema-GraphRAG-e-KAG-
   ```

2. **Crie e ative o ambiente virtual (`venv`):**
   * **Windows (PowerShell):**
     ```powershell
     python -m venv venv
     .\venv\Scripts\activate
     ```
   * **Linux / macOS:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure o arquivo `.env` na raiz do projeto:**
   ```env
   NEO4J_URI=bolt://127.0.0.1:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=senha_forte_123
   GEMINI_API_KEY=COLE_SUA_CHAVE_AQUI
   EMBEDDING_DIMENSION=768
   ```

### 5.3. Execução das Fases (Pipeline Completo)

1. **Inicie o container do Neo4j (com plugins APOC e GDS):**
   ```bash
   docker compose up -d
   ```
   *(Aguarde cerca de 30 segundos na primeira inicialização até que o serviço esteja ativo na porta `7687` e o Neo4j Browser disponível em `http://localhost:7474`).*

2. **Fase 1 — Criar Schema LPG, Constraints e Índices Médicos:**
   ```bash
   python src/database/setup_schema.py
   ```

3. **Fase 2 — Processar os 6 Prontuários PDF (`data/pdfs/`), Gerar Chunks e Popular o Grafo:**
   ```bash
   python src/ingestion/pipeline_ner_re.py
   ```

4. **Fase 3 — Executar Algoritmos GDS (PageRank, Louvain, Shortest Path) e Validar Busca Híbrida:**
   ```bash
   python src/retrieval/graph_algorithms.py
   python src/retrieval/hybrid_retriever.py
   ```

5. **Fase 4 — Executar Testes Operacionais e Iniciar a Interface Gráfica:**
   ```bash
   pytest -v
   streamlit run src/ui/app.py
   ```
   A aplicação abrirá automaticamente em **`http://localhost:8501`**.

---

## ☁️ 6. Instruções para Deployment em Nuvem (Opcional)

Para implantar o sistema em nuvem utilizando **Neo4j AuraDB** + **Streamlit Community Cloud**:
1. Crie uma instância gratuita no **Neo4j AuraDB** e copie a URI (`neo4j+s://...`), usuário e senha.
2. Configure `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` e `GEMINI_API_KEY` no arquivo `.env` (para rodar a ingestão inicial) e no painel **Secrets** do Streamlit Community Cloud.
3. Execute `setup_schema.py` e `pipeline_ner_re.py` localmente apontando para o AuraDB para popular os $6$ PDFs.
4. Publique o repositório no **Streamlit Community Cloud** definindo `src/ui/app.py` como arquivo principal.

---

## 🤖 7. Uso do Agente Mentor Técnico (System Prompt Oficial)

Em conformidade com a **Seção 2 da Especificação Técnica e Pedagógica**, a modelagem LPG, a resolução canônica de entidades clínicas, a indexação tripla (*Vector*, *Fulltext* e *Range/B-Tree*) e a arquitetura híbrida de mitigação de alucinações seguiram as diretrizes do **Mentor Técnico Especialista em GraphRAG e KAG**.

---

## 📚 8. Atribuição e Créditos de Bibliotecas Open-Source

Em conformidade com as diretrizes de integridade acadêmica da disciplina, este projeto utiliza e credita as seguintes ferramentas e bibliotecas de código aberto:

* [**Neo4j Database, APOC & Graph Data Science (GDS)**](https://neo4j.com/) — Banco de dados orientado a grafos LPG, índices vetoriais/fulltext nativos e algoritmos *PageRank*, *Louvain* e *Shortest Path*.
* [**Neo4j Python Driver (`neo4j`)**](https://pypi.org/project/neo4j/) — Driver oficial de comunicação via protocolo Bolt.
* [**Google GenAI SDK (`google-genai`)**](https://pypi.org/project/google-genai/) — Geração de *embeddings* (`text-embedding-004`) e extração/síntese com modelos Gemini.
* [**PyPDF (`pypdf`)**](https://pypi.org/project/pypdf/) — Extração textual de documentos PDF multipágina para o pipeline de *chunking* e NER/RE.
* [**Pydantic (`pydantic`)**](https://docs.pydantic.dev/) — Validação de esquemas estruturados no pipeline de extração.
* [**Streamlit (`streamlit`)**](https://streamlit.io/) **& [PyVis (`pyvis`)](https://pyvis.readthedocs.io/)** — Interface web interativa e renderização dinâmica de subgrafos baseada em *Vis.js*.
* [**Pytest (`pytest`)**](https://docs.pytest.org/) — Framework de testes operacionais automatizados.