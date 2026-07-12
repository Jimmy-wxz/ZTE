from recursive.utils.file_io import auto_read, auto_write
from collections import defaultdict
import sys
from loguru import logger

def traverse(data, web_pages):
    if isinstance(data, dict):
        if "global_index" in data:
            # Only require url and title; position is optional (KB results may not have it)
            if "url" not in data or "title" not in data:
                logger.warning("Missing url or title in web page data with global_index={}".format(data.get("global_index", "unknown")))
            else:
                if "position" not in data:
                    data["position"] = ""
                web_pages[data["global_index"]] = data
        else:
            for k, v in data.items():
                traverse(v, web_pages)
    elif isinstance(data, list):
        for v in data:
            traverse(v, web_pages)

import re
import re
from typing import Dict, List, Tuple

def is_local_kb_url(url: str) -> bool:
    """Check if URL is from local knowledge base."""
    return url.startswith("local-kb://") or url.startswith("kb://")

def format_kb_reference(page: dict) -> dict:
    """Format local KB reference to be more user-friendly."""
    # Create a more readable reference for KB
    formatted = page.copy()
    # Keep the URL as is for tracing, but we'll handle display later
    return formatted

def extract_and_renumber_citations(text: str, citation_urls):
    """
    Extract citation numbers, renumber them sequentially, and update both text and URLs.

    Args:
        text (str): Original text with citations
        citation_urls (dict): Original citation ID to URL mapping

    Returns:
        tuple: (Updated text, New citation ID to URL mapping)
    """
    # Extract all citation numbers
    pattern = r'\[reference:(\d+)\]'
    citation_numbers = re.findall(pattern, text)
    citation_numbers = [int(n) for n in citation_numbers]

    # Get unique URLs while maintaining order of first appearance
    # Filter out local KB URLs for now (they'll be handled separately)
    seen_urls = {}  # url -> first citation number that referenced it
    for num in citation_numbers:
        if num in citation_urls:
            url = citation_urls[num]["url"]
            if not is_local_kb_url(url):
                if url not in seen_urls:
                    seen_urls[url] = num

    # Create mapping from URL to new citation number (for web URLs only)
    url_to_new_num = {url: i+1 for i, url in enumerate(seen_urls.keys())}

    # Create old to new number mapping (for web URLs only)
    old_to_new = {}
    new_citation_urls = {}
    new_id = 1
    for old_num in citation_numbers:
        if old_num in citation_urls:
            url = citation_urls[old_num]["url"]
            if not is_local_kb_url(url):
                if url not in url_to_new_num:
                    url_to_new_num[url] = len(url_to_new_num) + 1
                old_to_new[old_num] = url_to_new_num[url]

    # Create new URL mapping (only for web URLs)
    for url, new_num in url_to_new_num.items():
        new_citation_urls[new_num] = citation_urls[list(seen_urls.values())[new_num-1]]

    # Replace citations in text and remove consecutive duplicates
    def replace_match(match):
        old_num = int(match.group(1))
        if old_num in old_to_new:
            new_num = old_to_new[old_num]
            return f'[reference:{new_num}]'
        else:
            # For local KB citations, keep them as [reference:X] but they won't appear in web references
            # We'll create a separate section for KB references
            return f'[reference:{old_num}]'

    # First replace all citations
    updated_text = re.sub(pattern, replace_match, text)

    # Then remove consecutive duplicate citations
    pattern_consecutive = r'(\[reference:\d+\])(\1)+'
    while re.search(pattern_consecutive, updated_text):
        updated_text = re.sub(pattern_consecutive, r'\1', updated_text)

    return updated_text, new_citation_urls

def _source_key(page):
    """Return the deduplication key used for a cited source."""
    url = page.get("url", "")
    if is_local_kb_url(url):
        return url.replace("local-kb://", "").replace("kb://", "")
    return url


def _remove_duplicate_labels(text):
    """Collapse accidental repeated adjacent citation labels."""
    pattern = r'(\[(?:WEB|KB):\d+\])(\1)+'
    while re.search(pattern, text):
        text = re.sub(pattern, r'\1', text)
    return text


def process_citations(text, citation_to_url):
    """Process citations in text and build URL reference mapping.

    Supports these citation formats in text:
      - [reference:1] — canonical format from writer LLM
      - [ref:1]       — shorthand variant
      - [1]           — plain numeric (treated as reference)
      - [WEB:1]/[KB:1] — explicit namespace variant, where 1 is the
        original search result index
      - [Local KB: 1]/[Web Search: 1] — labels sometimes emitted by the LLM

    Returns (updated_text, web_refs_dict, kb_refs_dict). The returned text uses
    unambiguous source namespaces:
      - [WEB:N] for public web search sources
      - [KB:N] for local knowledge-base sources
    """
    # Step 1: find all citation patterns in the article text.
    citation_pattern = r'\[(?:reference|ref):(\d+)\]'
    bare_pattern = r'(?<!\[reference)(?<!\[ref)\[(\d+)\](?!\()'  # [N] not followed by (
    namespaced_pattern = r'\[(Local\s+KB|Web\s+Search|WEB|KB|Web):\s*(\d+)\]'

    matches = []
    for m in re.finditer(citation_pattern, text):
        matches.append((m.start(), int(m.group(1))))
    for m in re.finditer(bare_pattern, text):
        matches.append((m.start(), int(m.group(1))))
    for m in re.finditer(namespaced_pattern, text, flags=re.IGNORECASE):
        matches.append((m.start(), int(m.group(2))))

    # Separate web URLs and KB URLs
    web_citation_to_url = {}
    kb_citation_to_url = {}
    for cid, page in citation_to_url.items():
        url = page.get("url", "")
        if is_local_kb_url(url):
            kb_citation_to_url[cid] = page
        else:
            web_citation_to_url[cid] = page

    # Step 2: assign stable source labels by first citation appearance.
    source_positions = {}
    source_pages = {}
    old_to_label = {}

    for pos, old_id in sorted(matches, key=lambda x: x[0]):
        page = citation_to_url.get(old_id)
        if not page:
            continue
        namespace = "KB" if is_local_kb_url(page.get("url", "")) else "WEB"
        key = (namespace, _source_key(page))
        if key not in source_positions:
            source_positions[key] = pos
            source_pages[key] = page

    web_keys = [
        key for key, _ in sorted(source_positions.items(), key=lambda x: x[1])
        if key[0] == "WEB"
    ]
    kb_keys = [
        key for key, _ in sorted(source_positions.items(), key=lambda x: x[1])
        if key[0] == "KB"
    ]

    web_key_to_new_id = {key: idx for idx, key in enumerate(web_keys, start=1)}
    kb_key_to_new_id = {key: idx for idx, key in enumerate(kb_keys, start=1)}

    new_web_citation_to_url = {
        new_id: source_pages[key] for key, new_id in web_key_to_new_id.items()
    }
    new_kb_citation_to_url = {
        new_id: source_pages[key] for key, new_id in kb_key_to_new_id.items()
    }

    for old_id, page in citation_to_url.items():
        namespace = "KB" if is_local_kb_url(page.get("url", "")) else "WEB"
        key = (namespace, _source_key(page))
        if namespace == "WEB" and key in web_key_to_new_id:
            old_to_label[old_id] = "WEB:{}".format(web_key_to_new_id[key])
        elif namespace == "KB" and key in kb_key_to_new_id:
            old_to_label[old_id] = "KB:{}".format(kb_key_to_new_id[key])

    def _label_for_old_id(old_id, original=None):
        if old_id in old_to_label:
            return "[{}]".format(old_to_label[old_id])
        return original or "[{}]".format(old_id)

    # Step 3: replace all citation styles with explicit source namespaces.
    def replace_ref_citation(match):
        old_id = int(match.group(1))
        return _label_for_old_id(old_id, match.group(0))

    def replace_namespaced_citation(match):
        explicit_label = match.group(1).strip().lower().replace(" ", "")
        explicit_namespace = "KB" if explicit_label == "localkb" else "WEB"
        old_id = int(match.group(2))
        page = citation_to_url.get(old_id)
        if page:
            actual_namespace = "KB" if is_local_kb_url(page.get("url", "")) else "WEB"
            if actual_namespace != explicit_namespace:
                return match.group(0)
        return _label_for_old_id(old_id, match.group(0))

    updated_text = re.sub(
        namespaced_pattern, replace_namespaced_citation, text,
        flags=re.IGNORECASE
    )
    updated_text = re.sub(citation_pattern, replace_ref_citation, updated_text)

    def replace_bare_citation(match):
        old_id = int(match.group(1))
        return _label_for_old_id(old_id, match.group(0))

    updated_text = re.sub(bare_pattern, replace_bare_citation, updated_text)
    updated_text = _remove_duplicate_labels(updated_text)

    return updated_text, new_web_citation_to_url, new_kb_citation_to_url


def get_report_with_ref(data, article):
    web_pages = {}
    traverse(data, web_pages)

    article, web_pages, kb_pages = process_citations(article, web_pages)

    if not web_pages and not kb_pages:
        return article

    # Build a single clean References section
    lines = ["\n\n---", "\n## 参考资料 (References)"]

    # Web search references
    if web_pages:
        lines.append("\n### 网络来源")
        for index, page in sorted(web_pages.items()):
            title = page.get("title", "无标题")
            url = page.get("url", "")
            if len(title) > 100:
                title = title[:97] + "..."
            lines.append("- **[WEB:{}]** [{}]({})".format(index, title, url))

    # Knowledge base references
    if kb_pages:
        lines.append("\n### 知识库来源")
        for index, page in sorted(kb_pages.items()):
            url = page.get("url", "")
            if url.startswith("local-kb://"):
                source = url.replace("local-kb://", "")
                title = page.get("title", "本地知识库: {}".format(source))
                if len(title) > 100:
                    title = title[:97] + "..."
                lines.append("- **[KB:{}]** {} - `{}`".format(index, title, source))

    article += "\n".join(lines) + "\n"
    return article


if __name__ == "__main__":
    web_pages = {}
    folder = sys.argv[1]
    data = auto_read("{}/nodes.json".format(folder))
    traverse(data, web_pages)
    # print(len(web_pages))
    # print(sorted(web_pages.keys()))
    # article = open("{}/report.md".format(folder)).read()
    article = open("{}/article.txt".format(folder)).read()

    article, web_pages, kb_pages = process_citations(article, web_pages)

    refs = []

    # 网页引用
    if web_pages:
        refs.append("## 网页来源")
        for index, page in sorted(web_pages.items()):
            refs.append("- [WEB:{}]({}). {} ".format(index, page["url"], page["title"]))

    # KB 引用
    if kb_pages:
        if refs:
            refs.append("")
        refs.append("## 知识库来源")
        for cid, page in sorted(kb_pages.items()):
            url = page.get("url", "")
            if url.startswith("local-kb://"):
                source = url.replace("local-kb://", "")
                title = page.get("title", f"本地知识库: {source}")
                refs.append("- [KB:{}] {} (来源: {})".format(cid, title, source))

    article += "\n\n# References\n{}".format("\n\n".join(refs))
    open("{}/report_with_ref.md".format(folder), "w").write(article.strip())
