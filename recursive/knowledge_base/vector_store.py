import os
from typing import List, Dict, Any, Optional

from loguru import logger

from .constants import DEFAULT_CHROMA_PERSIST_DIR, DEFAULT_EMBEDDING_MODEL
from .embedding import get_embedding_provider, LocalEmbedding, OpenAIEmbedding


EXTERNAL_KB_DEFAULT_EMBEDDINGS = {
    "large_kb": "BAAI/bge-large-zh-v1.5",
    "testdata": "BAAI/bge-large-zh-v1.5",
}


def _sanitize_collection_name(name: str) -> str:
    """Chroma collection names must be 3-63 chars and match [a-zA-Z0-9_-]."""
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
    safe = safe.strip("-_")
    if len(safe) < 3:
        safe = "kb_" + safe
    if len(safe) > 63:
        safe = safe[:63]
    return safe


class ChromaVectorStore:
    def __init__(
        self,
        persist_dir: str = None,
        embedding_model: str = None,
    ):
        self.persist_dir = persist_dir or DEFAULT_CHROMA_PERSIST_DIR
        # Check if using OpenAI embedding model (for 1024-dim vectors like testData)
        embedding_model_name = embedding_model or os.environ.get("WRITEHERE_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
        self.embedding_model_name = embedding_model_name
        self._client = None
        self._embedding = None
        # Support external Chroma databases, e.g. project-root/testdata/chroma_data
        self._external_clients = {}

    def _ensure_client(self):
        if self._client is not None:
            return
        try:
            import chromadb
        except ImportError as e:
            raise ImportError(
                "chromadb is required for vector store. Install it with: pip install chromadb"
            ) from e

        # Handle old system sqlite3 on Python 3.8
        try:
            import pysqlite3
            import sys
            sys.modules["sqlite3"] = pysqlite3
            logger.info("Using pysqlite3-binary to satisfy Chroma sqlite3 requirement.")
        except ImportError:
            pass

        self._client = chromadb.PersistentClient(path=self.persist_dir)
        self._embedding = get_embedding_provider(self.embedding_model_name)

    def _get_client_for_kb(self, knowledge_base_name: str):
        """Return (client, collection_name, embedding_provider) for the given KB.

        Resolution order:
        1. If ``WRITEHERE_KB_<NAME>_PATH`` is set, use that external Chroma DB.
        2. If the current Chroma client already contains a collection whose name
           exactly matches ``knowledge_base_name`` (e.g. pre-built DBs like
           ``rag_chunks``), use it directly.
        3. Otherwise treat it as an internal KB prefixed with ``kb_``.
        """
        self._ensure_client()
        normalized = knowledge_base_name.strip()

        # External DB configured via environment variable.
        external_path = os.environ.get("WRITEHERE_KB_{}_PATH".format(normalized.upper()))
        if external_path and os.path.isdir(external_path):
            import chromadb
            try:
                import pysqlite3
                import sys
                sys.modules["sqlite3"] = pysqlite3
            except ImportError:
                pass
            # Cache both client and embedding provider to avoid reloading
            # the local embedding model on every search call
            if normalized not in self._external_clients:
                external_embedding = (
                    os.environ.get("WRITEHERE_KB_{}_EMBEDDING".format(normalized.upper()))
                    or EXTERNAL_KB_DEFAULT_EMBEDDINGS.get(normalized.lower())
                    or self.embedding_model_name
                )
                self._external_clients[normalized] = (
                    chromadb.PersistentClient(path=external_path),
                    get_embedding_provider(external_embedding),
                )
            client, cached_embedding = self._external_clients[normalized]
            try:
                client.get_collection(name=normalized)
                return client, normalized, cached_embedding
            except Exception:
                try:
                    collections = client.list_collections()
                    if collections:
                        return client, collections[0].name, cached_embedding
                except Exception:
                    pass
            return client, normalized, cached_embedding

        # Direct collection lookup (for stores that point at a pre-built DB).
        try:
            self._client.get_collection(name=normalized)
            return self._client, normalized, self._embedding
        except Exception:
            pass

        return self._client, _sanitize_collection_name("kb_{}".format(normalized)), self._embedding

    def _collection_name(self, knowledge_base_name: str) -> str:
        return _sanitize_collection_name("kb_{}".format(knowledge_base_name))

    def index_chunks(
        self,
        knowledge_base_name: str,
        chunks: List[Dict[str, Any]],
    ) -> int:
        self._ensure_client()
        if not chunks:
            return 0

        collection = self._client.get_or_create_collection(
            name=self._collection_name(knowledge_base_name)
        )

        texts = [chunk["text"] for chunk in chunks]
        embeddings = self._embedding.embed(texts)
        ids = [chunk["id"] for chunk in chunks]
        metadatas = [chunk["metadata"] for chunk in chunks]

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info(
            "Indexed {} chunks into collection {}".format(len(chunks), self._collection_name(knowledge_base_name))
        )
        return len(chunks)

    def search(
        self,
        knowledge_base_name: str,
        query: str,
        topk: int = 5,
        distance_threshold: float = None,
    ) -> List[Dict[str, Any]]:
        """Search the knowledge base for chunks similar to the query.

        Args:
            knowledge_base_name: Name of the knowledge base collection.
            query: The search query text.
            topk: Maximum number of results to return.
            distance_threshold: Optional cosine distance threshold.
                Chunks with distance > threshold are filtered out.
                For cosine distance (Chroma default), lower = more similar.
                Recommended: 0.5 (strict), 0.8 (moderate), None (no filter).

        Returns:
            List of dicts with keys: text, source, file_path, chunk_index,
            distance, title.
        """
        # Use external client if configured via environment variable
        client, collection_name, embedding = self._get_client_for_kb(knowledge_base_name)

        try:
            collection = client.get_collection(name=collection_name)
        except Exception:
            return []

        query_embedding = embedding.embed([query])[0]
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(topk, collection.count() or 1),
            include=["documents", "metadatas", "distances"],
        )

        output = []
        docs = results.get("documents", [[]])[0] or []
        metadatas = results.get("metadatas", [[]])[0] or []
        distances = results.get("distances", [[]])[0] or []
        for doc, meta, distance in zip(docs, metadatas, distances):
            # Apply distance threshold filter if configured
            if distance_threshold is not None and distance > distance_threshold:
                logger.debug(
                    "Filtered chunk (distance={:.3f} > threshold={:.2f})".format(
                        distance, distance_threshold))
                continue

            # Normalize metadata keys across internal and external collections.
            if isinstance(meta, dict):
                source = meta.get("source") or meta.get("source_path") or meta.get("single_title") or meta.get("title", "")
                file_path = meta.get("file_path") or meta.get("source_path") or ""
                chunk_index = meta.get("chunk_index", -1)
                title = meta.get("title") or meta.get("single_title") or ""
            else:
                source, file_path, chunk_index, title = "", "", -1, ""
            output.append({
                "text": doc,
                "source": source,
                "file_path": file_path,
                "chunk_index": chunk_index,
                "distance": distance,
                "title": title,
            })

        if distance_threshold is not None:
            filtered_count = len(docs) - len(output)
            if filtered_count > 0:
                logger.info(
                    "Distance threshold {:.2f}: filtered {} of {} chunks".format(
                        distance_threshold, filtered_count, len(docs)))

        return output

    def delete_collection(self, knowledge_base_name: str):
        client, collection_name, _ = self._get_client_for_kb(knowledge_base_name)
        try:
            client.delete_collection(name=collection_name)
            logger.info("Deleted collection {}".format(collection_name))
        except Exception as e:
            logger.warning("Failed to delete collection {}: {}".format(collection_name, e))

    def count(self, knowledge_base_name: str) -> int:
        client, collection_name, _ = self._get_client_for_kb(knowledge_base_name)
        try:
            collection = client.get_collection(name=collection_name)
            return collection.count()
        except Exception:
            return 0
