import os
from typing import List, Union

from loguru import logger


class LocalEmbedding:
    """Local sentence-transformers embedding wrapper."""

    def __init__(self, model_name: str = None):
        self.model_name = model_name or os.environ.get(
            "WRITEHERE_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
        self._model = None
        self._dimension = None

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required for local embedding. "
                "Install it with: pip install sentence-transformers"
            ) from e
        logger.info("Loading local embedding model: {}".format(self.model_name))
        self._model = SentenceTransformer(self.model_name)
        self._dimension = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        self._load_model()
        if isinstance(texts, str):
            texts = [texts]
        texts = [t.strip() for t in texts]
        embeddings = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return embeddings.tolist()

    @property
    def dimension(self) -> int:
        self._load_model()
        return self._dimension


class OpenAIEmbedding:
    """OpenAI embedding wrapper using the existing OpenAIApiProxy."""

    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model

    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        if isinstance(texts, str):
            texts = [texts]
        from recursive.llm.llm import OpenAIApiProxy

        proxy = OpenAIApiProxy()
        resp = proxy.call_embedding(model=self.model, text=texts)
        data = resp.get("data", [])
        data.sort(key=lambda x: x.get("index", 0))
        return [item.get("embedding", []) for item in data]


_EMBEDDING_CACHE = {}  # module-level singleton: avoid reloading large models
_RERANKER_CACHE = {}   # module-level singleton for reranker


def get_embedding_provider(model_name: str = None):
    """Factory to select embedding provider by model name.

    Embedding providers are cached at module level so that expensive models
    (e.g. BAAI/bge-large-zh-v1.5) are loaded only once across all searches.
    """
    name = (model_name or os.environ.get("WRITEHERE_EMBEDDING_MODEL", "")).strip()
    cache_key = name if name else "__default_local__"
    if cache_key in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[cache_key]
    if name.startswith("text-embedding-"):
        provider = OpenAIEmbedding(model=name)
    else:
        provider = LocalEmbedding(model_name=name if name else None)
    _EMBEDDING_CACHE[cache_key] = provider
    return provider


class Reranker:
    """Cross-encoder reranker for precise relevance scoring.

    Bi-encoder (embedding) retrieves candidates quickly but scores are
    coarse because query and document are encoded independently.
    Cross-encoder feeds (query, doc) pairs jointly through a transformer,
    yielding much more accurate relevance scores at the cost of speed.

    We only run rerank on the top-k retrieved candidates, so the speed
    penalty is acceptable.
    """

    DEFAULT_MODEL = "BAAI/bge-reranker-large"

    def __init__(self, model_name: str = None):
        self.model_name = model_name or os.environ.get(
            "WRITEHERE_RERANKER_MODEL", self.DEFAULT_MODEL
        )
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required for reranker. "
                "Install it with: pip install sentence-transformers"
            ) from e
        logger.info("Loading reranker model: {}".format(self.model_name))
        # max_length=512 is sufficient for most KB chunks
        self._model = CrossEncoder(self.model_name, max_length=512)

    def rerank(self, query: str, documents: List[str]) -> List[float]:
        """Return relevance scores for each document against the query.

        Scores are in range roughly [-10, 10] with higher = more relevant.
        """
        if not documents:
            return []
        self._load_model()
        pairs = [(query, doc) for doc in documents]
        scores = self._model.predict(pairs, show_progress_bar=False)
        # Ensure list of floats
        if hasattr(scores, "tolist"):
            scores = scores.tolist()
        return [float(s) for s in scores]

    def rerank_dicts(self, query: str, items: List[dict], text_key: str = "text") -> List[dict]:
        """Rerank a list of dicts and attach 'rerank_score' to each."""
        texts = [item.get(text_key, "") for item in items]
        scores = self.rerank(query, texts)
        for item, score in zip(items, scores):
            item["rerank_score"] = score
        # Sort by rerank score descending
        return sorted(items, key=lambda x: x.get("rerank_score", 0), reverse=True)


def get_reranker(model_name: str = None) -> Reranker:
    """Factory for reranker with module-level caching."""
    name = (model_name or os.environ.get("WRITEHERE_RERANKER_MODEL", "")).strip()
    cache_key = name if name else "__default_reranker__"
    if cache_key in _RERANKER_CACHE:
        return _RERANKER_CACHE[cache_key]
    reranker = Reranker(model_name=name if name else None)
    _RERANKER_CACHE[cache_key] = reranker
    return reranker
