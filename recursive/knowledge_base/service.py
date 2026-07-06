import json
import os
import shutil
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional

from loguru import logger

from .chunker import chunk_documents
from .constants import DEFAULT_KB_BASE_PATH, DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP, DEFAULT_TOPK
from .document_parser import list_supported_files
from .vector_store import ChromaVectorStore


class KnowledgeBaseService:
    """Manage local knowledge bases: document upload, indexing, search, delete."""

    def __init__(
        self,
        base_path: str = None,
        embedding_model: str = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self.base_path = base_path or DEFAULT_KB_BASE_PATH
        # Handle OpenAI embedding models (they start with "text-embedding-")
        self.embedding_model = embedding_model or os.environ.get("WRITEHERE_EMBEDDING_MODEL")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        # Pass embedding model to ChromaVectorStore
        self._store = ChromaVectorStore(
            persist_dir=os.path.join(base_path, "chroma_db") if base_path else None,
            embedding_model=self.embedding_model
        )
        self._index_lock = threading.Lock()
        os.makedirs(self.base_path, exist_ok=True)

    def _is_external_kb(self, name: str) -> bool:
        normalized = name.strip().upper()
        return bool(os.environ.get("WRITEHERE_KB_{}_PATH".format(normalized)))

    def _kb_dir(self, name: str) -> str:
        return os.path.join(self.base_path, name)

    def _docs_dir(self, name: str) -> str:
        return os.path.join(self._kb_dir(name), "documents")

    def _meta_path(self, name: str) -> str:
        return os.path.join(self._kb_dir(name), "metadata.json")

    def _load_meta(self, name: str) -> Dict[str, Any]:
        path = self._meta_path(name)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load metadata for {}: {}".format(name, e))
        return {
            "name": name,
            "created_at": None,
            "updated_at": None,
            "files": [],
            "chunk_count": 0,
            "status": "pending",
            "embedding_model": self.embedding_model or os.environ.get("WRITEHERE_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        }

    def _save_meta(self, name: str, meta: Dict[str, Any]):
        path = self._meta_path(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def create_kb(self, name: str) -> Dict[str, Any]:
        os.makedirs(self._docs_dir(name), exist_ok=True)
        meta = self._load_meta(name)
        if meta.get("created_at") is None:
            meta["created_at"] = datetime.now().isoformat()
            self._save_meta(name, meta)
        return meta

    def save_files(self, name: str, file_paths: List[str]) -> List[str]:
        """Copy files into the knowledge base documents directory."""
        os.makedirs(self._docs_dir(name), exist_ok=True)
        saved = []
        for src in file_paths:
            dst = os.path.join(self._docs_dir(name), os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.copy2(src, dst)
            saved.append(dst)
        return saved

    def process_and_index(
        self,
        name: str,
        file_paths: Optional[List[str]] = None,
        remove_old: bool = False,
    ) -> Dict[str, Any]:
        """Parse, chunk, embed and store documents for a knowledge base."""
        with self._index_lock:
            self.create_kb(name)
            meta = self._load_meta(name)
            meta["status"] = "indexing"
            self._save_meta(name, meta)

            docs_dir = self._docs_dir(name)
            if remove_old:
                self._store.delete_collection(name)
                if os.path.exists(docs_dir):
                    shutil.rmtree(docs_dir)
                os.makedirs(docs_dir, exist_ok=True)

            if file_paths:
                self.save_files(name, file_paths)

            files_to_index = list_supported_files(docs_dir)
            if not files_to_index:
                meta["files"] = []
                meta["chunk_count"] = 0
                meta["status"] = "empty"
                meta["updated_at"] = datetime.now().isoformat()
                self._save_meta(name, meta)
                return meta

            chunks = chunk_documents(
                files_to_index,
                knowledge_base_name=name,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )

            if remove_old:
                self._store.delete_collection(name)
            chunk_count = self._store.index_chunks(name, chunks)

            meta["files"] = [os.path.basename(f) for f in files_to_index]
            meta["chunk_count"] = chunk_count
            meta["status"] = "ready"
            meta["updated_at"] = datetime.now().isoformat()
            self._save_meta(name, meta)
            return meta

    def search(
        self,
        name: str,
        query: str,
        topk: int = DEFAULT_TOPK,
        distance_threshold: float = None,
    ) -> List[Dict[str, Any]]:
        return self._store.search(name, query, topk=topk, distance_threshold=distance_threshold)

    def get_kb(self, name: str) -> Dict[str, Any]:
        meta = self._load_meta(name)
        meta["chunk_count"] = self._store.count(name)
        meta["documents_dir"] = self._docs_dir(name) if not self._is_external_kb(name) else ""
        return meta

    def list_kbs(self) -> List[Dict[str, Any]]:
        kbs = []
        if not os.path.exists(self.base_path):
            return kbs
        for entry in os.listdir(self.base_path):
            kb_dir = self._kb_dir(entry)
            if os.path.isdir(kb_dir):
                meta = self._load_meta(entry)
                meta["chunk_count"] = self._store.count(entry)
                kbs.append(meta)
        return kbs

    def delete_kb(self, name: str):
        if self._is_external_kb(name):
            # External KBs are read-only; do not delete the underlying collection.
            logger.warning("Refusing to delete external knowledge base {}".format(name))
            return
        self._store.delete_collection(name)
        kb_dir = self._kb_dir(name)
        if os.path.exists(kb_dir):
            shutil.rmtree(kb_dir)

    def reindex(self, name: str) -> Dict[str, Any]:
        return self.process_and_index(name, file_paths=None, remove_old=True)
