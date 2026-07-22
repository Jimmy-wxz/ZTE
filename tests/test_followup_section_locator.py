from followup_test_utils import load_followup_module


section_module = load_followup_module("section_locator")
find_target_sections = section_module.find_target_sections
parse_report_sections = section_module.parse_report_sections
replace_section = section_module.replace_section


REPORT = (
    "# Report\n\n"
    "## 技术架构评估\n"
    "Architecture text.\n\n"
    "## 竞品分析\n"
    "Competitor text.\n\n"
    "## 参考资料 References\n"
    "- source\n"
)


def test_parse_report_sections_excludes_references():
    sections = parse_report_sections(REPORT)

    assert [section["title"] for section in sections] == ["Report", "技术架构评估", "竞品分析"]


def test_find_target_sections_uses_hint():
    sections = find_target_sections(
        REPORT,
        "请修改竞品分析章节",
        {"target_section_hint": "竞品分析", "scope": "section"},
    )

    assert sections[0]["title"] == "竞品分析"


def test_replace_section_preserves_other_sections_and_references():
    section = find_target_sections(
        REPORT,
        "请修改竞品分析章节",
        {"target_section_hint": "竞品分析", "scope": "section"},
    )[0]

    updated = replace_section(REPORT, section, "## 竞品分析\nUpdated competitor text.")

    assert "Updated competitor text." in updated
    assert "Architecture text." in updated
    assert "## 参考资料 References" in updated
