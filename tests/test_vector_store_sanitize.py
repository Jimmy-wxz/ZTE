import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KB_DIR = ROOT / "recursive" / "knowledge_base"
PACKAGE_NAME = "knowledge_base_under_test"


def load_vector_store_module():
    if "loguru" not in sys.modules:
        loguru = types.ModuleType("loguru")

        class _Logger:
            def debug(self, *_args, **_kwargs):
                pass

            def info(self, *_args, **_kwargs):
                pass

            def warning(self, *_args, **_kwargs):
                pass

        loguru.logger = _Logger()
        sys.modules["loguru"] = loguru

    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(KB_DIR)]
    sys.modules[PACKAGE_NAME] = package

    constants = types.ModuleType(f"{PACKAGE_NAME}.constants")
    constants.DEFAULT_CHROMA_PERSIST_DIR = ""
    constants.DEFAULT_EMBEDDING_MODEL = "dummy"
    sys.modules[f"{PACKAGE_NAME}.constants"] = constants

    embedding = types.ModuleType(f"{PACKAGE_NAME}.embedding")
    embedding.get_embedding_provider = lambda *_args, **_kwargs: None
    embedding.LocalEmbedding = object
    embedding.OpenAIEmbedding = object
    sys.modules[f"{PACKAGE_NAME}.embedding"] = embedding

    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE_NAME}.vector_store",
        KB_DIR / "vector_store.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{PACKAGE_NAME}.vector_store"] = module
    spec.loader.exec_module(module)
    return module


vector_store = load_vector_store_module()


def test_sanitize_retrieved_document_keeps_informative_text():
    text = "IAST observes runtime behavior and correlates requests with vulnerabilities."

    assert vector_store.sanitize_retrieved_document(text, {}) == text


def test_sanitize_retrieved_document_uses_metadata_fallback_for_gibberish():
    text = "*0+1*1+1*0+1*1+1*0+1"
    meta = {
        "title": "AI Checker development workflow",
        "summary": "AI Checker uses quality gates across design, coding, and release stages.",
    }

    sanitized = vector_store.sanitize_retrieved_document(text, meta)

    assert "AI Checker" in sanitized
    assert "quality gates" in sanitized


def test_sanitize_retrieved_document_skips_empty_low_information_chunk():
    assert vector_store.sanitize_retrieved_document("", {"title": "短"}) == ""
