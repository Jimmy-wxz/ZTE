from recursive.utils.get_index import get_report_with_ref, process_citations


def test_process_citations_uses_separate_web_and_kb_namespaces():
    pages = {
        1: {
            "title": "Local KB: training.json",
            "url": "local-kb:///doc/training.json",
        },
        2: {
            "title": "Threat report",
            "url": "https://example.com/report",
        },
        3: {
            "title": "Same threat report",
            "url": "https://example.com/report",
        },
    }
    text = "Internal fact[reference:1], web trend[reference:2][reference:3]."

    updated, web_refs, kb_refs = process_citations(text, pages)

    assert updated == "Internal fact[KB:1], web trend[WEB:1]."
    assert web_refs[1]["url"] == "https://example.com/report"
    assert kb_refs[1]["url"] == "local-kb:///doc/training.json"


def test_get_report_with_ref_outputs_labeled_reference_sections():
    data = {
        "web_pages": [
            {
                "global_index": 1,
                "title": "Local KB: training.json",
                "url": "local-kb:///doc/training.json",
            },
            {
                "global_index": 2,
                "title": "Threat report",
                "url": "https://example.com/report",
            },
        ]
    }
    article = "Internal fact[reference:1], public trend[reference:2]."

    result = get_report_with_ref(data, article)

    assert "Internal fact[KB:1], public trend[WEB:1]." in result
    assert "- **[WEB:1]** [Threat report](https://example.com/report)" in result
    assert "- **[KB:1]** Local KB: training.json - `/doc/training.json`" in result


def test_process_citations_normalizes_llm_local_kb_labels():
    pages = {
        2: {
            "title": "Local KB: training.json",
            "url": "local-kb:///doc/training.json",
        },
        6: {
            "title": "IAST report",
            "url": "https://example.com/iast",
        },
    }
    text = "Internal practice[Local KB: 2], market source[Web Search: 6]."

    updated, web_refs, kb_refs = process_citations(text, pages)

    assert updated == "Internal practice[KB:1], market source[WEB:1]."
    assert web_refs[1]["url"] == "https://example.com/iast"
    assert kb_refs[1]["url"] == "local-kb:///doc/training.json"
