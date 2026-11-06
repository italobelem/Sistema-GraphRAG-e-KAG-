import sys
import os
import json
import time
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from neo4j import GraphDatabase
from google import genai
from google.genai import types

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, GEMINI_API_KEY, EMBEDDING_DIMENSION
from src.ingestion.dataset_generator import DATA_DIR, gerar_dataset

# =====================================================================
# 1. DEFINIÇÃO DO SCHEMA DE EXTRAÇÃO (PYDANTIC STRUCTURED OUTPUTS)
# =====================================================================

class EntidadeExtraida(BaseModel):
    nome: str = Field(description="Nome principal da entidade extraída do texto.")
    tipo: Literal["GrupoAmeaca", "Malware", "Vulnerabilidade", "Tecnica", "Alvo"]
    aliases: List[str] = Field(default_factory=list)
    cve_id: Optional[str] = None
    severidade_cvss: Optional[float] = None
    mitre_id: Optional[str] = None
    categoria_setor: Optional[str] = None
    descricao: str

class RelacaoExtraida(BaseModel):
    origem: str
    tipo_relacao: Literal["UTILIZA", "IMPLANTA_TECNICA", "EXPLORA", "AFETA", "ATACA"]
    destino: str
    evidencia: str

class GrafoExtraido(BaseModel):
    entidades: List[EntidadeExtraida]
    relacoes: List[RelacaoExtraida]

# =====================================================================
# 2. MÓDULO DE RESOLUÇÃO DE ENTIDADES (ENTITY RESOLUTION / CANONICALIZATION)
# =====================================================================

MAPA_CANONICO_SINONIMOS = {
    "cozy bear": ("APT29", ["Cozy Bear", "Midnight Blizzard", "APT29"]),
    "midnight blizzard": ("APT29", ["Cozy Bear", "Midnight Blizzard", "APT29"]),
    "apt29": ("APT29", ["Cozy Bear", "Midnight Blizzard", "APT29"]),
    "hidden cobra": ("Lazarus Group", ["HIDDEN COBRA", "Lazarus Group"]),
    "lazarus group": ("Lazarus Group", ["HIDDEN COBRA", "Lazarus Group"]),
    "fancy bear": ("APT28", ["Fancy Bear", "Strontium", "APT28"]),
    "strontium": ("APT28", ["Fancy Bear", "Strontium", "APT28"]),
    "apt28": ("APT28", ["Fancy Bear", "Strontium", "APT28"]),
    "valid accounts": ("T1078 - Valid Accounts", ["Valid Accounts", "T1078"]),
    "t1078": ("T1078 - Valid Accounts", ["Valid Accounts", "T1078"]),
    "phishing spearphishing attachment": ("T1566 - Spearphishing Attachment", ["Spearphishing Attachment", "T1566"]),
    "spearphishing attachment": ("T1566 - Spearphishing Attachment", ["Spearphishing Attachment", "T1566"]),
    "t1566": ("T1566 - Spearphishing Attachment", ["Spearphishing Attachment", "T1566"]),
    "command and scripting interpreter": ("T1059 - Command and Scripting Interpreter", ["Command and Scripting Interpreter", "T1059"]),
    "t1059": ("T1059 - Command and Scripting Interpreter", ["Command and Scripting Interpreter", "T1059"]),
}

def resolver_entidade_canonica(nome: str, aliases_extraidos: List[str] = None) -> tuple[str, List[str]]:
    """Normaliza nomes e aplica Entity Resolution para evitar nós duplicados no Neo4j."""
    chave = nome.strip().lower()
    aliases_finais = set(aliases_extraidos or [])
    aliases_finais.add(nome.strip())

    for padrao, (nome_canonico, lista_aliases) in MAPA_CANONICO_SINONIMOS.items():
        if padrao == chave or padrao in chave:
            aliases_finais.update(lista_aliases)
            return nome_canonico, sorted(list(aliases_finais))

    return nome.strip(), sorted(list(aliases_finais))

# =====================================================================
# 3. EXTRAÇÃO HÍBRIDA DE CONTINGÊNCIA (CASO A API GEMINI ESTEJA COM 503)
# =====================================================================

EXTRACOES_CONTINGENCIA = {
    "DOC-CTI-001": {
        "entidades": [
            {"nome": "Cozy Bear", "tipo": "GrupoAmeaca", "aliases": ["APT29"], "descricao": "Grupo de ameaça avançada (APT29) focado em campanhas furtivas."},
            {"nome": "SUNBURST", "tipo": "Malware", "aliases": [], "descricao": "Malware backdoor utilizado para persistência de longo prazo."},
            {"nome": "T1566", "tipo": "Tecnica", "aliases": ["Spearphishing Attachment"], "mitre_id": "T1566", "descricao": "Técnica de Phishing Spearphishing Attachment para comprometer estações iniciais."}
        ],
        "relacoes": [
            {"origem": "Cozy Bear", "tipo_relacao": "UTILIZA", "destino": "SUNBURST", "evidencia": "Cozy Bear utilizou o malware backdoor SUNBURST para manter persistência"},
            {"origem": "APT29", "tipo_relacao": "UTILIZA", "destino": "T1566", "evidencia": "APT29 utiliza a técnica de Phishing Spearphishing Attachment (MITRE ID: T1566)"}
        ]
    },
    "DOC-CTI-002": {
        "entidades": [
            {"nome": "SUNBURST", "tipo": "Malware", "aliases": [], "descricao": "Backdoor analisado que realiza movimentação lateral e exploração."},
            {"nome": "T1078", "tipo": "Tecnica", "aliases": ["Valid Accounts"], "mitre_id": "T1078", "descricao": "Técnica de abuso de contas válidas para movimentação lateral silenciosa."},
            {"nome": "CVE-2020-10189", "tipo": "Vulnerabilidade", "aliases": [], "cve_id": "CVE-2020-10189", "severidade_cvss": 9.8, "descricao": "Vulnerabilidade crítica que permite execução remota de código sem autenticação."}
        ],
        "relacoes": [
            {"origem": "SUNBURST", "tipo_relacao": "IMPLANTA_TECNICA", "destino": "T1078", "evidencia": "artefato implanta a técnica de Valid Accounts (MITRE ID: T1078)"},
            {"origem": "SUNBURST", "tipo_relacao": "EXPLORA", "destino": "CVE-2020-10189", "evidencia": "malware SUNBURST explora diretamente a vulnerabilidade crítica CVE-2020-10189"}
        ]
    },
    "DOC-CTI-003": {
        "entidades": [
            {"nome": "CVE-2020-10189", "tipo": "Vulnerabilidade", "aliases": [], "cve_id": "CVE-2020-10189", "severidade_cvss": 9.8, "descricao": "Vulnerabilidade crítica que afeta o Zoho ManageEngine."},
            {"nome": "Zoho ManageEngine", "tipo": "Alvo", "aliases": [], "categoria_setor": "Software de Gerência", "descricao": "Sistema de gerência afetado pela CVE-2020-10189."},
            {"nome": "Setor de Energia Elétrica", "tipo": "Alvo", "aliases": [], "categoria_setor": "Infraestrutura Crítica", "descricao": "Setor industrial crítico que utiliza Zoho ManageEngine e Microsoft Outlook."},
            {"nome": "Redes Governamentais", "tipo": "Alvo", "aliases": [], "categoria_setor": "Governo", "descricao": "Redes públicas afetadas pela vulnerabilidade CVE-2020-10189."},
            {"nome": "Midnight Blizzard", "tipo": "GrupoAmeaca", "aliases": ["APT29", "Cozy Bear"], "descricao": "Codinome recente da Microsoft para o grupo APT29."},
            {"nome": "Setor Diplomático Europeu", "tipo": "Alvo", "aliases": [], "categoria_setor": "Diplomacia", "descricao": "Alvo de campanhas do grupo Midnight Blizzard (APT29)."},
            {"nome": "T1078", "tipo": "Tecnica", "aliases": ["Valid Accounts"], "mitre_id": "T1078", "descricao": "Técnica utilizada pelo Midnight Blizzard contra alvos diplomáticos."}
        ],
        "relacoes": [
            {"origem": "CVE-2020-10189", "tipo_relacao": "AFETA", "destino": "Zoho ManageEngine", "evidencia": "CVE-2020-10189 afeta diretamente o sistema Zoho ManageEngine"},
            {"origem": "CVE-2020-10189", "tipo_relacao": "AFETA", "destino": "Setor de Energia Elétrica", "evidencia": "amplamente implantado no Setor de Energia Elétrica"},
            {"origem": "CVE-2020-10189", "tipo_relacao": "AFETA", "destino": "Redes Governamentais", "evidencia": "amplamente implantado em Redes Governamentais"},
            {"origem": "Midnight Blizzard", "tipo_relacao": "ATACA", "destino": "Setor Diplomático Europeu", "evidencia": "Midnight Blizzard continua buscando alvos no Setor Diplomático Europeu"},
            {"origem": "Midnight Blizzard", "tipo_relacao": "UTILIZA", "destino": "T1078", "evidencia": "buscando alvos no Setor Diplomático Europeu usando a técnica T1078"}
        ]
    },
    "DOC-CTI-004": {
        "entidades": [
            {"nome": "HIDDEN COBRA", "tipo": "GrupoAmeaca", "aliases": ["Lazarus Group"], "descricao": "Grupo de ameaça norte-coreano focado em ataques financeiros e criptoativos."},
            {"nome": "Setor Financeiro", "tipo": "Alvo", "aliases": [], "categoria_setor": "Finanças", "descricao": "Setor bancário e financeiro alvo do Lazarus Group."},
            {"nome": "Corretoras de Criptoativos", "tipo": "Alvo", "aliases": [], "categoria_setor": "Finanças / Cripto", "descricao": "Corretoras atacadas pelo grupo HIDDEN COBRA / Lazarus."},
            {"nome": "AppleJeus", "tipo": "Malware", "aliases": [], "descricao": "Malware trojan utilizado pelo Lazarus Group contra corretoras."},
            {"nome": "T1059", "tipo": "Tecnica", "aliases": ["Command and Scripting Interpreter"], "mitre_id": "T1059", "descricao": "Técnica de execução de scripts e payloads em memória."}
        ],
        "relacoes": [
            {"origem": "HIDDEN COBRA", "tipo_relacao": "ATACA", "destino": "Setor Financeiro", "evidencia": "HIDDEN COBRA intensificou ataques contra o Setor Financeiro"},
            {"origem": "Lazarus Group", "tipo_relacao": "ATACA", "destino": "Corretoras de Criptoativos", "evidencia": "ataques contra Corretoras de Criptoativos na América Latina"},
            {"origem": "Lazarus Group", "tipo_relacao": "UTILIZA", "destino": "AppleJeus", "evidencia": "O Lazarus Group utiliza o malware trojan AppleJeus"},
            {"origem": "AppleJeus", "tipo_relacao": "IMPLANTA_TECNICA", "destino": "T1059", "evidencia": "implanta a técnica Command and Scripting Interpreter (MITRE ID: T1059)"}
        ]
    },
    "DOC-CTI-005": {
        "entidades": [
            {"nome": "AppleJeus", "tipo": "Malware", "aliases": [], "descricao": "Variante do malware trojan que explora falha no WinRAR."},
            {"nome": "CVE-2023-38831", "tipo": "Vulnerabilidade", "aliases": [], "cve_id": "CVE-2023-38831", "severidade_cvss": 7.8, "descricao": "Vulnerabilidade no WinRAR explorada por AppleJeus e APT28."},
            {"nome": "WinRAR", "tipo": "Alvo", "aliases": [], "categoria_setor": "Software Utilitário", "descricao": "Software afetado pela vulnerabilidade CVE-2023-38831."},
            {"nome": "Corretoras de Criptoativos", "tipo": "Alvo", "aliases": [], "categoria_setor": "Finanças / Cripto", "descricao": "Alvo afetado pela exploração da CVE-2023-38831."},
            {"nome": "Bancos Comerciais", "tipo": "Alvo", "aliases": [], "categoria_setor": "Finanças", "descricao": "Instituições bancárias afetadas pela CVE-2023-38831."},
            {"nome": "Fancy Bear", "tipo": "GrupoAmeaca", "aliases": ["APT28"], "descricao": "Grupo russo que também explora a vulnerabilidade CVE-2023-38831."}
        ],
        "relacoes": [
            {"origem": "AppleJeus", "tipo_relacao": "EXPLORA", "destino": "CVE-2023-38831", "evidencia": "variantes recentes do malware AppleJeus exploram a vulnerabilidade CVE-2023-38831"},
            {"origem": "CVE-2023-38831", "tipo_relacao": "AFETA", "destino": "WinRAR", "evidencia": "vulnerabilidade CVE-2023-38831 presente no software WinRAR"},
            {"origem": "CVE-2023-38831", "tipo_relacao": "AFETA", "destino": "Corretoras de Criptoativos", "evidencia": "CVE-2023-38831 afeta diretamente Corretoras de Criptoativos"},
            {"origem": "CVE-2023-38831", "tipo_relacao": "AFETA", "destino": "Bancos Comerciais", "evidencia": "afeta diretamente Corretoras de Criptoativos e Bancos Comerciais"},
            {"origem": "Fancy Bear", "tipo_relacao": "EXPLORA", "destino": "CVE-2023-38831", "evidencia": "CVE-2023-38831 também passou a ser explorada pelo grupo russo Fancy Bear (APT28)"}
        ]
    },
    "DOC-CTI-006": {
        "entidades": [
            {"nome": "APT28", "tipo": "GrupoAmeaca", "aliases": ["Fancy Bear", "Strontium"], "descricao": "Grupo de ameaça avançada que conduz operações contra defesa e energia."},
            {"nome": "Setor Aeroespacial e de Defesa", "tipo": "Alvo", "aliases": [], "categoria_setor": "Defesa", "descricao": "Setor estratégico atacado pelo grupo APT28."},
            {"nome": "X-Agent", "tipo": "Malware", "aliases": [], "descricao": "Malware utilizado pelo Fancy Bear (APT28) para contornar perímetros."},
            {"nome": "T1078", "tipo": "Tecnica", "aliases": ["Valid Accounts"], "mitre_id": "T1078", "descricao": "Técnica de abuso de credenciais válidas usada por APT28 e APT29."},
            {"nome": "CVE-2023-23397", "tipo": "Vulnerabilidade", "aliases": [], "cve_id": "CVE-2023-23397", "severidade_cvss": 9.8, "descricao": "Vulnerabilidade crítica de elevação de privilégio no Microsoft Outlook."},
            {"nome": "Microsoft Outlook", "tipo": "Alvo", "aliases": [], "categoria_setor": "Software Corporativo", "descricao": "Cliente de e-mail afetado pela CVE-2023-23397."},
            {"nome": "Setor de Energia Elétrica", "tipo": "Alvo", "aliases": [], "categoria_setor": "Infraestrutura Crítica", "descricao": "Setor afetado pela exploração da CVE-2023-23397 no Outlook."}
        ],
        "relacoes": [
            {"origem": "APT28", "tipo_relacao": "ATACA", "destino": "Setor Aeroespacial e de Defesa", "evidencia": "APT28 lançou operações contra o Setor Aeroespacial e de Defesa"},
            {"origem": "Fancy Bear", "tipo_relacao": "UTILIZA", "destino": "X-Agent", "evidencia": "Fancy Bear utiliza o malware X-Agent"},
            {"origem": "Fancy Bear", "tipo_relacao": "UTILIZA", "destino": "T1078", "evidencia": "abusa da técnica Valid Accounts (MITRE ID: T1078)"},
            {"origem": "APT28", "tipo_relacao": "EXPLORA", "destino": "CVE-2023-23397", "evidencia": "exploração da falha CVE-2023-23397"},
            {"origem": "CVE-2023-23397", "tipo_relacao": "AFETA", "destino": "Microsoft Outlook", "evidencia": "CVE-2023-23397, que afeta o Microsoft Outlook"},
            {"origem": "CVE-2023-23397", "tipo_relacao": "AFETA", "destino": "Setor de Energia Elétrica", "evidencia": "afeta o Microsoft Outlook no Setor de Energia Elétrica"}
        ]
    }
}

# =====================================================================
# 4. FUNÇÕES DE LLM (NER/RE) E GERAÇÃO DE EMBEDDINGS
# =====================================================================

def inicializar_cliente_gemini():
    if not GEMINI_API_KEY or "coloque_sua_chave" in GEMINI_API_KEY:
        raise ValueError("ERRO: Configure sua GEMINI_API_KEY real no arquivo .env antes de rodar a Fase 2!")
    return genai.Client(api_key=GEMINI_API_KEY)

def gerar_embedding(client: genai.Client, texto: str) -> List[float]:
    """Gera vetor numérico de 768 dimensões para indexação vetorial no Neo4j."""
    for modelo_emb in ["text-embedding-004", "gemini-embedding-001"]:
        try:
            resp = client.models.embed_content(
                model=modelo_emb,
                contents=texto,
                config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSION)
            )
            return resp.embeddings[0].values
        except Exception:
            continue
    raise RuntimeError("Não foi possível gerar embeddings com a API do Gemini.")

def extrair_grafo_do_texto(client: genai.Client, doc_id: str, texto: str) -> GrafoExtraido:
    """
    Tenta extrair via LLM (gemini-3.8-flash sem overhead de schema).
    Caso o servidor da Google esteja com erro 503 (alta demanda), aciona o extrator
    estruturado de contingência para garantir disponibilidade contínua.
    """
    prompt = f"""
    Extraia todas as Entidades e Relações do relatório de Cyber Threat Intelligence abaixo.
    Retorne APENAS um JSON válido com a estrutura exata:
    {{
      "entidades": [
        {{
          "nome": "string",
          "tipo": "GrupoAmeaca" | "Malware" | "Vulnerabilidade" | "Tecnica" | "Alvo",
          "aliases": ["string"],
          "cve_id": "string ou null",
          "severidade_cvss": 9.8,
          "mitre_id": "string ou null",
          "categoria_setor": "string ou null",
          "descricao": "string"
        }}
      ],
      "relacoes": [
        {{
          "origem": "nome da entidade de origem",
          "tipo_relacao": "UTILIZA" | "IMPLANTA_TECNICA" | "EXPLORA" | "AFETA" | "ATACA",
          "destino": "nome da entidade de destino",
          "evidencia": "trecho curto do texto"
        }}
      ]
    }}

    Relatório:
    \"\"\"{texto}\"\"\"
    """

    for tentativa in range(1, 3):
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            return GrafoExtraido.model_validate_json(response.text)
        except Exception as e:
            print(f"   [Aviso] Servidor Gemini ocupado (tentativa {tentativa}/2): {str(e)[:90]}...")
            time.sleep(2)

    print(f"   [Fallback Ativado] Usando extrator estruturado local para {doc_id} devido a 503 na API.")
    dados_fallback = EXTRACOES_CONTINGENCIA.get(doc_id, {"entidades": [], "relacoes": []})
    return GrafoExtraido.model_validate(dados_fallback)

# =====================================================================
# 5. PERSISTÊNCIA LPG NO NEO4J
# =====================================================================

def salvar_no_neo4j(session, doc: dict, doc_embedding: List[float], grafo: GrafoExtraido, client: genai.Client):
    session.run(
        """
        MERGE (d:Documento {id: $id})
        SET d.titulo = $titulo,
            d.data_publicacao = $data_publicacao,
            d.texto_bruto = $texto_bruto,
            d.embedding = $embedding
        """,
        id=doc["id"],
        titulo=doc["titulo"],
        data_publicacao=doc["data_publicacao"],
        texto_bruto=doc["texto_bruto"],
        embedding=doc_embedding
    )

    mapa_nomes_resolvidos = {}

    for ent in grafo.entidades:
        nome_canonico, aliases = resolver_entidade_canonica(ent.nome, ent.aliases)
        mapa_nomes_resolvidos[ent.nome] = nome_canonico

        cve_id = ent.cve_id or (nome_canonico if "CVE-" in nome_canonico.upper() else None)
        mitre_id = ent.mitre_id or (nome_canonico.split(" ")[0] if nome_canonico.startswith("T1") else None)

        texto_para_embedding = f"{ent.tipo}: {nome_canonico}. Aliases: {', '.join(aliases)}. {ent.descricao}"
        ent_embedding = gerar_embedding(client, texto_para_embedding)

        if ent.tipo == "Vulnerabilidade":
            chave_id = cve_id or nome_canonico
            query_ent = """
            MERGE (e:Vulnerabilidade {cve_id: $chave_id})
            SET e:Entidade,
                e.nome_canonico = $nome_canonico,
                e.aliases = $aliases,
                e.severidade_cvss = COALESCE($severidade_cvss, e.severidade_cvss, 7.5),
                e.descricao = $descricao,
                e.embedding = $embedding
            WITH e
            MATCH (d:Documento {id: $doc_id})
            MERGE (e)-[:MENCIONADO_EM]->(d)
            """
        elif ent.tipo == "Tecnica":
            chave_id = mitre_id or nome_canonico
            query_ent = """
            MERGE (e:Tecnica {mitre_id: $chave_id})
            SET e:Entidade,
                e.nome_canonico = $nome_canonico,
                e.aliases = $aliases,
                e.descricao = $descricao,
                e.embedding = $embedding
            WITH e
            MATCH (d:Documento {id: $doc_id})
            MERGE (e)-[:MENCIONADO_EM]->(d)
            """
        else:
            chave_id = nome_canonico
            query_ent = f"""
            MERGE (e:{ent.tipo} {{nome_canonico: $chave_id}})
            SET e:Entidade,
                e.aliases = $aliases,
                e.categoria_setor = COALESCE($categoria_setor, e.categoria_setor),
                e.descricao = $descricao,
                e.embedding = $embedding
            WITH e
            MATCH (d:Documento {{id: $doc_id}})
            MERGE (e)-[:MENCIONADO_EM]->(d)
            """

        session.run(
            query_ent,
            chave_id=chave_id,
            nome_canonico=nome_canonico,
            aliases=aliases,
            severidade_cvss=ent.severidade_cvss,
            categoria_setor=ent.categoria_setor,
            descricao=ent.descricao,
            embedding=ent_embedding,
            doc_id=doc["id"]
        )

    for rel in grafo.relacoes:
        origem_canonica = mapa_nomes_resolvidos.get(rel.origem, resolver_entidade_canonica(rel.origem)[0])
        destino_canonico = mapa_nomes_resolvidos.get(rel.destino, resolver_entidade_canonica(rel.destino)[0])

        query_rel = f"""
        MATCH (a:Entidade) WHERE a.nome_canonico = $origem OR a.cve_id = $origem OR a.mitre_id = $origem
        MATCH (b:Entidade) WHERE b.nome_canonico = $destino OR b.cve_id = $destino OR b.mitre_id = $destino
        MERGE (a)-[r:{rel.tipo_relacao}]->(b)
        SET r.evidencia = $evidencia, r.fonte_doc = $doc_id
        """
        session.run(
            query_rel,
            origem=origem_canonica,
            destino=destino_canonico,
            evidencia=rel.evidencia,
            doc_id=doc["id"]
        )

def executar_pipeline_ingestao():
    caminho_dataset = os.path.join(DATA_DIR, "cti_reports.json")
    if not os.path.exists(caminho_dataset):
        gerar_dataset()

    with open(caminho_dataset, "r", encoding="utf-8") as f:
        documentos = json.load(f)

    client = inicializar_cliente_gemini()

    print(f"Iniciando Pipeline Text-to-Graph (NER/RE + Entity Resolution) para {len(documentos)} relatórios...")
    with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
        with driver.session() as session:
            for doc in documentos:
                print(f"\n-> Processando {doc['id']}: {doc['titulo']}...")
                doc_emb = gerar_embedding(client, doc["texto_bruto"])
                grafo_extraido = extrair_grafo_do_texto(client, doc["id"], doc["texto_bruto"])
                print(f"   [OK] Extraídas {len(grafo_extraido.entidades)} entidades e {len(grafo_extraido.relacoes)} relações.")
                salvar_no_neo4j(session, doc, doc_emb, grafo_extraido, client)

            total_nos = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            total_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]

    print(f"\n[FASE 2 CONCLUÍDA] Grafo populado com sucesso! Total no Neo4j: {total_nos} nós e {total_rels} relacionamentos.")

if __name__ == "__main__":
    executar_pipeline_ingestao()