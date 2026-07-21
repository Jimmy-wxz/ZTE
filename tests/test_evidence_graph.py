from evidence_test_utils import load_evidence_graph_module


graph_module = load_evidence_graph_module()
build_evidence_graph = graph_module.build_evidence_graph
parse_markdown_sections = graph_module.parse_markdown_sections


def _edge_set(graph):
    return {
        (edge["source"], edge["target"], edge["type"])
        for edge in graph["edges"]
    }


def test_evidence_graph_links_sections_claims_and_evidence():
    ledger_items = [
        {
            "evidence_id": "kb1",
            "node_id": "1",
            "node_goal": "Explain IAST",
            "sub_question": "What is IAST?",
            "source_type": "kb",
            "source_uri": "local-kb:///docs/iast.md",
            "source_title": "iast.md",
            "chunk_text": "IAST observes runtime behavior during testing.",
            "verify_label": "direct_support",
            "verify_score": 0.92,
            "global_index": 1,
            "citation_label": "[reference:1]",
        },
        {
            "evidence_id": "web2",
            "node_id": "2",
            "node_goal": "Compare market vendors",
            "sub_question": "Who competes in the IAST market?",
            "source_type": "web",
            "source_uri": "https://example.com/iast-market",
            "source_title": "IAST market overview",
            "chunk_text": "The market includes multiple AST and DevSecOps vendors.",
            "verify_label": "partial_support",
            "verify_score": 0.74,
            "global_index": 2,
            "citation_label": "[reference:2]",
        },
    ]
    article = (
        "# Overview\n"
        "IAST observes runtime behavior during tests. [reference:1]\n\n"
        "## Market\n"
        "The IAST market overlaps with AST and DevSecOps vendors. [reference:2]\n"
    )

    graph = build_evidence_graph(ledger_items=ledger_items, article=article)
    edges = _edge_set(graph)

    assert graph["summary"]["evidence_total"] == 2
    assert graph["summary"]["cited_evidence"] == 2
    assert graph["summary"]["claim_count"] == 2
    assert graph["summary"]["source_type_counts"] == {"kb": 1, "web": 1}
    assert graph["summary"]["evidence_cluster_count"] == 2
    assert len(graph["summary"]["section_evidence_map"]) == 2
    assert any(node["type"] == "evidence_cluster" for node in graph["nodes"])
    assert any(node["type"] == "section_evidence_map" for node in graph["nodes"])
    assert any(edge[1] == "evidence:kb1" and edge[2] == "cites" for edge in edges)
    assert any(edge[1] == "evidence:web2" and edge[2] == "supported_by" for edge in edges)
    assert any(edge[2] == "uses_evidence_cluster" for edge in edges)


def test_evidence_graph_adds_rubric_dimensions_and_missing_summary():
    ledger_items = [
        {
            "evidence_id": "web2",
            "node_id": "2",
            "node_goal": "Compare market vendors",
            "source_type": "web",
            "source_uri": "https://example.com/iast-market",
            "source_title": "IAST market overview",
            "chunk_text": "Vendor comparison evidence.",
            "verify_label": "direct_support",
            "verify_score": 0.88,
            "global_index": 2,
        },
    ]
    root_node_json = {
        "result": {
            "rubric_gap": {
                "dimensions": [
                    {
                        "dimension_id": "competitors",
                        "description": "Competitor coverage",
                        "required": True,
                        "prefers_web": True,
                        "covered": True,
                        "score": 1.0,
                        "keywords": ["competitor", "vendor"],
                        "evidence_ids": ["web2"],
                    },
                    {
                        "dimension_id": "market_context",
                        "description": "Market context coverage",
                        "required": True,
                        "prefers_web": True,
                        "covered": False,
                        "score": 0.0,
                        "keywords": ["market size"],
                        "evidence_ids": [],
                    },
                ],
                "missing_required": ["market_context"],
                "preferred_web_missing": ["market_context"],
            }
        }
    }

    graph = build_evidence_graph(
        ledger_items=ledger_items,
        article="# Market\nVendor comparison. [reference:2]",
        root_node_json=root_node_json,
    )

    rubric_nodes = [
        node for node in graph["nodes"]
        if node["type"] == "rubric_dimension"
    ]
    assert len(rubric_nodes) == 2
    assert graph["summary"]["rubric_dimension_count"] == 2
    assert graph["summary"]["rubric_missing"] == ["market_context"]
    assert any(
        edge["source"] == "evidence:web2" and edge["type"] == "covers"
        for edge in graph["edges"]
    )


def test_parse_markdown_sections_stops_before_references():
    sections = parse_markdown_sections(
        "# One\nBody\n\n## References\n[reference:1]"
    )

    assert len(sections) == 1
    assert sections[0]["title"] == "One"
