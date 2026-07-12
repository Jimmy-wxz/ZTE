import os
from typing import List, Union

from loguru import logger


_FALSE_VALUES = {"0", "false", "no", "off", "disable", "disabled"}


def _hf_network_allowed() -> bool:
    return os.environ.get("WRITEHERE_ALLOW_HF_NETWORK", "").strip().lower() not in (
        "", *_FALSE_VALUES
    )


def _force_hf_offline_env():
    if _hf_network_allowed():
        return
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


_force_hf_offline_env()


def _configure_hf_offline() -> bool:
    """Default HuggingFace-backed models to local-only/offline loading.

    The VM used for large_kb tests has the required models cached but no
    internet access. Without these flags, sentence-transformers still performs
    HuggingFace HEAD requests before consulting cache, which can add long
    retry delays. Set WRITEHERE_ALLOW_HF_NETWORK=1 only when intentionally
    downloading a new model.
    """
    if _hf_network_allowed():
        return False
    _force_hf_offline_env()
    return True


def _local_model_device() -> str:
    """Default local retrieval models to CPU for broad VM compatibility."""
    return os.environ.get("WRITEHERE_LOCAL_MODEL_DEVICE", "cpu").strip() or "cpu"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


class LocalEmbedding:
    """Local sentence-transformers embedding wrapper."""

    def __init__(self, model_name: str = None):
        self.model_name = model_name or os.environ.get(
            "WRITEHERE_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
        self._model = None
        self._dimension = None
        self.device = _local_model_device()

    def _load_model(self):
        if self._model is not None:
            return
        local_only = _configure_hf_offline()
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required for local embedding. "
                "Install it with: pip install sentence-transformers"
            ) from e
        logger.info("Loading local embedding model: {} on {}".format(
            self.model_name, self.device))
        try:
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
                local_files_only=local_only,
            )
        except TypeError:
            # Older sentence-transformers versions may not expose
            # local_files_only on SentenceTransformer; the offline env vars
            # above still prevent network access.
            self._model = SentenceTransformer(self.model_name, device=self.device)
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
    cache_key = "{}::{}".format(name if name else "__default_local__", _local_model_device())
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
        self.device = _local_model_device()
        self.max_length = _env_int("WRITEHERE_RERANKER_MAX_LENGTH", 256)
        self.batch_size = _env_int("WRITEHERE_RERANKER_BATCH_SIZE", 8)

    def _load_model(self):
        if self._model is not None:
            return
        local_only = _configure_hf_offline()
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required for reranker. "
                "Install it with: pip install sentence-transformers"
            ) from e
        logger.info("Loading reranker model: {} on {} (max_length={}, batch_size={})".format(
            self.model_name, self.device, self.max_length, self.batch_size))
        cross_encoder_kwargs = {
            "max_length": self.max_length,
            "device": self.device,
        }
        if local_only:
            cross_encoder_kwargs["automodel_args"] = {"local_files_only": True}
            cross_encoder_kwargs["tokenizer_args"] = {"local_files_only": True}
        try:
            self._model = CrossEncoder(self.model_name, **cross_encoder_kwargs)
        except TypeError:
            self._model = CrossEncoder(
                self.model_name, max_length=self.max_length, device=self.device)

    def rerank(self, query: str, documents: List[str]) -> List[float]:
        """Return relevance scores for each document against the query.

        Scores are in range roughly [-10, 10] with higher = more relevant.
        """
        if not documents:
            return []
        self._load_model()
        pairs = [(query, doc) for doc in documents]
        scores = self._model.predict(
            pairs, show_progress_bar=False, batch_size=self.batch_size)
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
    cache_key = "{}::{}::{}".format(
        name if name else "__default_reranker__",
        _local_model_device(),
        _env_int("WRITEHERE_RERANKER_MAX_LENGTH", 256),
    )
    if cache_key in _RERANKER_CACHE:
        return _RERANKER_CACHE[cache_key]
    reranker = Reranker(model_name=name if name else None)
    _RERANKER_CACHE[cache_key] = reranker
    return reranker
