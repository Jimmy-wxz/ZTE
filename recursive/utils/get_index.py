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

def process_citations(text, citation_to_url):
    """Process citations in text and build URL reference mapping.

    Supports these citation formats in text:
      - [reference:1] — canonical format from writer LLM
      - [ref:1]       — shorthand variant
      - [1]           — plain numeric (treated as reference)

    Returns (updated_text, web_refs_dict, kb_refs_dict).
    """
    # Step 1: find ALL citation patterns in the article text
    # Match [reference:N], [ref:N], and bare [N] (single or multi-digit)
    citation_pattern = r'\[(?:reference|ref):(\d+)\]'
    bare_pattern = r'(?<!\[reference)(?<!\[ref)\[(\d+)\](?!\()'  # [N] not followed by (

    # Collect all used IDs from [reference:N] format
    ref_ids = [int(m) for m in re.findall(citation_pattern, text)]
    bare_ids = [int(m) for m in re.findall(bare_pattern, text)]
    all_used_ids = set(ref_ids + bare_ids)

    # Find first position of each citation ID for ordering
    old2id_2_pos = {}
    for idx in all_used_ids:
        # Try [reference:N] first
        matches = list(re.finditer(r'\[(?:reference|ref):{}]'.format(idx), text))
        if matches:
            old2id_2_pos[idx] = matches[0].start()
        else:
            # Try bare [N]
            bare_matches = list(re.finditer(r'(?<!\[reference)(?<!\[ref)\[{}](?!\()'.format(idx), text))
            if bare_matches:
                old2id_2_pos[idx] = bare_matches[0].start()

    # Separate web URLs and KB URLs
    web_citation_to_url = {}
    kb_citation_to_url = {}
    url2page = {}

    for cid, page in citation_to_url.items():
        url = page.get("url", "")
        url2page[url] = page
        if is_local_kb_url(url):
            kb_citation_to_url[cid] = page
        else:
            web_citation_to_url[cid] = page

    # Build URL → old IDs mapping (only for actually cited IDs)
    url_to_old_ids = {}
    for cid in sorted(all_used_ids):
        if cid in web_citation_to_url:
            url = web_citation_to_url[cid]["url"]
            if url not in url_to_old_ids:
                url_to_old_ids[url] = []
            url_to_old_ids[url].append((cid, old2id_2_pos.get(cid, 0)))

    # Step 3: renumber unique web URLs as sequential [1], [2], ...
    old_to_new_id = {}
    new_web_citation_to_url = {}
    new_id = 1

    for url, old_id_and_pos in sorted(url_to_old_ids.items(), key=lambda x: x[1][0][1]):
        for old_id, pos in old_id_and_pos:
            old_to_new_id[old_id] = new_id
        new_web_citation_to_url[new_id] = url2page[url]
        new_id += 1

    # Step 4: replace all [reference:N] with renumbered IDs
    def replace_ref_citation(match):
        old_id = int(match.group(1))
        if old_id in old_to_new_id:
            return '[{}]'.format(old_to_new_id[old_id])
        return '[{}]'.format(old_id)

    updated_text = re.sub(citation_pattern, replace_ref_citation, text)

    # Step 5: replace bare [N] citations with renumbered IDs too
    def replace_bare_citation(match):
        old_id = int(match.group(1))
        if old_id in old_to_new_id:
            return '[{}]'.format(old_to_new_id[old_id])
        return '[{}]'.format(old_id)

    updated_text = re.sub(bare_pattern, replace_bare_citation, updated_text)

    # Step 6: remove consecutive duplicate citations
    pattern_consecutive = r'(\[\d+\])(\1)+'
    while re.search(pattern_consecutive, updated_text):
        updated_text = re.sub(pattern_consecutive, r'\1', updated_text)

    return updated_text, new_web_citation_to_url, kb_citation_to_url


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
            lines.append("- **[{}]** [{}]({})".format(index, title, url))

    # Knowledge base references
    if kb_pages:
        lines.append("\n### 知识库来源")
        seen_sources = {}
        for cid, page in kb_pages.items():
            url = page.get("url", "")
            if url.startswith("local-kb://"):
                source = url.replace("local-kb://", "")
                title = page.get("title", "本地知识库: {}".format(source))
                if source not in seen_sources:
                    seen_sources[source] = (len(seen_sources) + 1, title)
                    lines.append("- **{}** - `{}`".format(title, source))

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
            refs.append("- [{}]({}). {} ".format(index, page["url"], page["title"]))

    # KB 引用
    if kb_pages:
        if refs:
            refs.append("")
        refs.append("## 知识库来源")
        for cid, page in kb_pages.items():
            url = page.get("url", "")
            if url.startswith("local-kb://"):
                source = url.replace("local-kb://", "")
                title = page.get("title", f"本地知识库: {source}")
                refs.append("- {} (来源: {})".format(title, source))

    article += "\n\n# References\n{}".format("\n\n".join(refs))
    open("{}/report_with_ref.md".format(folder), "w").write(article.strip())