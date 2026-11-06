import os
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "senha_forte_123")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))