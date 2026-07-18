import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_query_module():
    spec = importlib.util.spec_from_file_location(
        "search_query_under_test",
        ROOT / "recursive" / "search" / "query.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


query_module = load_query_module()


def test_rubric_gap_queries_target_missing_dimensions():
    queries = query_module.build_rubric_gap_queries(
        "AIOps",
        "zh",
        {
            "missing_required": ["competitors"],
            "preferred_web_missing": ["market_context"],
        },
    )

    joined = "\n".join(queries)
    assert "竞品" in joined
    assert "市场规模" in joined


def test_infer_page_source_type_distinguishes_kb_and_web():
    kb_page = {"url": "local-kb:///doc/aiops#chunk-1"}
    web_page = {"url": "https://example.com/report"}

    assert query_module.infer_page_source_type(kb_page) == "kb"
    assert query_module.infer_page_source_type(web_page) == "web"
    assert query_module.source_type_label("kb") == "Local KB"


def test_extract_relevance_terms_is_not_security_specific():
    terms = query_module.extract_relevance_terms(
        "Explain Kubernetes autoscaling architecture and observability metrics."
    )
    lowered = {term.lower() for term in terms}

    assert "kubernetes" in lowered
    assert "autoscaling" in lowered
    assert "observability" in lowered
