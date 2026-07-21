import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_report_quality_module():
    spec = importlib.util.spec_from_file_location(
        "report_quality_under_test",
        ROOT / "recursive" / "utils" / "report_quality.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


report_quality = load_report_quality_module()


def test_postprocess_moves_executive_summary_before_first_chapter():
    markdown = (
        "# AgC Security Report\n\n"
        "## 一、引言\n"
        "正文。[KB:1]\n\n"
        "## 五、行业对标分析\n"
        "正文。[WEB:1]\n\n"
        "## 执行摘要\n"
        "摘要内容。[KB:1]\n\n"
        "## 六、实施路线图\n"
        "正文。[KB:2]\n"
    )

    fixed, audit = report_quality.postprocess_report_quality(
        markdown, add_audit_section=False)

    assert audit["executive_summary_moved"] is True
    assert fixed.index("## 执行摘要") < fixed.index("## 一、引言")
    assert fixed.index("## 五、行业对标分析") < fixed.index("## 六、实施路线图")


def test_audit_flags_unsupported_roi_and_keeps_references_after_warning():
    markdown = (
        "# Report\n\n"
        "## 一、路线图\n"
        "三阶段总投入 430 万元，3 年 ROI 200%。\n\n"
        "## 参考资料 (References)\n"
        "- [KB:1] source\n"
    )

    fixed, audit = report_quality.postprocess_report_quality(markdown)

    assert audit["unsupported_quantitative_count"] == 1
    assert "## 证据审计提示" in fixed
    assert fixed.index("## 证据审计提示") < fixed.index("## 参考资料")


def test_audit_does_not_flag_cited_or_qualified_estimates():
    markdown = (
        "# Report\n\n"
        "## 一、路线图\n"
        "投入 430 万元。[KB:1]\n"
        "ROI 200% 为基于行业经验估算，需验证。\n"
    )

    _, audit = report_quality.postprocess_report_quality(
        markdown, add_audit_section=False)

    assert audit["unsupported_quantitative_count"] == 0
