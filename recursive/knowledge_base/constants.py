import os

DEFAULT_KB_BASE_PATH = os.environ.get(
    "WRITEHERE_KB_PATH",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "backend",
        "knowledge_bases",
    ),
)

DEFAULT_CHROMA_PERSIST_DIR = os.path.join(DEFAULT_KB_BASE_PATH, "chroma_db")

DEFAULT_EMBEDDING_MODEL = os.environ.get(
    "WRITEHERE_EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50
DEFAULT_TOPK = 5
