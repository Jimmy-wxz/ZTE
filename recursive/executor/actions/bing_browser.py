import json
import logging
import os
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
import concurrent
from typing import List, Optional, Tuple, Type, Union

import requests

from recursive.executor.actions import BaseAction, tool_api
from recursive.executor.actions.parser import BaseParser, JsonParser
from recursive.executor.actions.register import tool_register
from recursive.executor.actions.selector_and_summazier import selector, summarizier
from recursive.memory import caches

from langchain_text_splitters import RecursiveCharacterTextSplitter
from trafilatura import extract
import httpx
import concurrent.futures
from loguru import logger
from charset_normalizer import detect
from dotenv import load_dotenv

load_dotenv(dotenv_path='api_key.env')


class WebPageHelper:
    """Helper class to process web pages.

    Acknowledgement: Part of the code is adapted from https://github.com/stanford-oval/WikiChat project.
    """

    def __init__(
        self,
        min_char_count: int = 150,
        snippet_chunk_size: int = 1000,
        max_thread_num: int = 10,
    ):
        """
        Args:
            min_char_count: Minimum character count for the article to be considered valid.
            snippet_chunk_size: Maximum character count for each snippet.
            max_thread_num: Maximum number of threads to use for concurrent requests (e.g., downloading webpages).
        """
        self.header_pools = [
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.google.com/",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "cross-site"
            },
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.bing.com/",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin"
            },
            {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.youtube.com/",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none"
            },
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.yahoo.com/",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-site"
            },
            {
                "User-Agent": "Mozilla/5.0 (Linux; Android 14; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.amazon.com/",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin"
            },
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.reddit.com/",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "cross-site"
            },
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 OPR/85.0.4341.18",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.wikipedia.org/",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin"
            },
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.netflix.com/",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-site"
            },
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.linkedin.com/",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "cross-site"
            },
            {
                "User-Agent": "Mozilla/5.0 (Linux; Android 14; SM-A536U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36 EdgA/122.0.2365.47",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.ebay.com/",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin"
            }
        ]
    
        
        # self.httpx_client = httpx.Client(verify=False, headers=headers, follow_redirects=True)
        self.min_char_count = min_char_count
        self.max_thread_num = max_thread_num
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=snippet_chunk_size,
            chunk_overlap=0,
            length_function=len,
            is_separator_regex=False,
            separators=[
                "\n\n",
                "\n",
                ".",
                "\uff0e",  # Fullwidth full stop
                "\u3002",  # Ideographic full stop
                ",",
                "\uff0c",  # Fullwidth comma
                "\u3001",  # Ideographic comma
                " ",
                "\u200B",  # Zero-width space
                "",
            ],
        )

    def download_webpage(self, url: str, overwrite_cache=False):
        # cached
        web_page_cache = caches["web_page"]
        # Load Cache
        cache_name = "WebPageHelper.download_webpage"
        call_args_dict = {
            "url": url,
        }
        
        if web_page_cache is not None and not overwrite_cache:
            cache_result = web_page_cache.get_cache(
                name = cache_name,
                call_args_dict = call_args_dict
            )
            if cache_result is not None:
                return cache_result["result"]
            
        try:
            import random
            with httpx.Client(verify=False, headers=random.choice(self.header_pools), follow_redirects=True) as client:
                res = client.get(url, timeout=10)
            if res.status_code >= 400:
                res.raise_for_status()
            encoding = detect(res.content)['encoding']
            res.encoding = encoding
            # save cache
            if web_page_cache is not None:
                web_page_cache.save_cache(
                    name = cache_name,
                    call_args_dict = call_args_dict,
                    value = {"result": res.text}
                )
            return res.text
        except httpx.HTTPError as exc:
            logger.error(f"Error while requesting {exc.request.url!r} - {exc!r}")
            return None

    def urls_to_articles(self, urls):
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_thread_num
        ) as executor:
            htmls = list(executor.map(self.download_webpage, urls))

        articles = {}

        for h, u in zip(htmls, urls):
            if h is None:
                continue
            article_text = extract(
                h,
                # include_tables=False,
                include_tables=True,
                include_comments=False,
                output_format="txt",
            )
            if article_text is not None and len(article_text) > self.min_char_count:
                articles[u] = {"text": article_text}

        return articles

    def urls_to_snippets(self, urls):
        articles = self.urls_to_articles(urls)
        for u in articles:
            # articles[u]["snippets"] = self.text_splitter.split_text(articles[u]["text"])
            articles[u]["snippets"] = articles[u]["text"]
            
        return articles

class BaseSearch:
    def __init__(self, topk: int = 3, black_list: List[str] = None):
        self.topk = topk
        self.black_list = black_list

    def _filter_results(self, results: List[tuple]) -> dict:
        filtered_results = {}
        count = 0
        for url, snippet, title in results:
            if all(domain not in url
                   for domain in self.black_list) and not url.endswith('.pdf'):
                filtered_results[count] = {
                    'url': url,
                    'summ': json.dumps(snippet, ensure_ascii=False)[1:-1],
                    'title': title
                }
                count += 1
                if count >= self.topk:
                    break
        return filtered_results

    def _filter_results_for_dict_return(self, results: List[tuple]) -> dict:
        filtered_results = {}
        count = 0
        for item in results:
            url = item["url"]
            if all(domain not in url
                   for domain in self.black_list) and not url.endswith('.pdf'):
                filtered_results[count] = item
                count += 1
        return filtered_results

class SerpApiSearch(BaseSearch):

    def __init__(self,
                 serp_api_key=None,
                 topk = 20,
                 is_valid_source = None,
                 min_char_count = 150,
                 snippet_chunk_size = 1000,
                 webpage_helper_max_threads = 10,
                 backend_engine = "google", # default search engine changed to google
                 cc = "US", # default search region
                 language = "en", # language hint for search params
                 **kwargs,):
        black_list = []
        # Get API key from parameter or environment variable
        self.serp_api_key = serp_api_key or str(os.getenv('SERPAPI', ''))

        # Log which search engine is being used
        if not self.serp_api_key:
            logger.warning("No SERPAPI key found - searches may fail")

        self.language = language

        # Use SerpApi endpoint for Google search
        self.endpoint = "https://serpapi.com/search"
        if backend_engine == "google":
            logger.info("USE GOOGLE (SerpAPI)")
            self.params = {
                "engine": "google",
                "num": min(topk, 100),  # Google max is 100
                "gl": cc.lower(),
                "hl": "zh-CN" if language == "zh" else "en",
                **kwargs
            }
        elif backend_engine == "bing":
            logger.info("USE BING (SerpAPI)")
            self.params = {
                "engine": "bing",
                "count": min(topk, 50),  # Bing max is 50
                "cc": cc,
                "mkt": "zh-CN" if language == "zh" else "en-US",
                **kwargs
            }
        else:
            logger.info("USE custom engine: {}".format(backend_engine))
            self.params = {"engine": backend_engine, "count": topk, **kwargs}
            
            
        self.webpage_helper = WebPageHelper(
            min_char_count=min_char_count,
            snippet_chunk_size=snippet_chunk_size,
            max_thread_num=webpage_helper_max_threads,
        )
        self.usage = 0

        # If not None, is_valid_source shall be a function that takes a URL and returns a boolean.
        self.is_valid_source = is_valid_source if is_valid_source else lambda x: True
        
        super().__init__(topk, black_list)
        
    def get_usage_and_reset(self):
        usage = self.usage
        self.usage = 0
        return {"SerpApiSearch": usage}
    
    def search(self, query, exclude_urls: List[str] = [], overwrite_cache=False):
        search_cache = caches["search"]
        cache_name = "SerpApiSearch"
        call_args_dict = {
            "query": query,
            "params": self.params,
            "exclude_urls": exclude_urls
        }
        logger.debug("SerpApiSearch: overwrite_cache={}".format(overwrite_cache))

        url_to_results = {}
        if search_cache is not None and not overwrite_cache:
            cache_result = search_cache.get_cache(
                name = cache_name,
                call_args_dict = call_args_dict
            )
            if cache_result is not None:
                url_to_results = cache_result
                logger.info("SerpApiSearch: cache hit for '{}' ({} results)".format(
                    query[:60], len(url_to_results)))

        # No Cache, True Call
        if len(url_to_results) == 0:
            queries = [query]
            self.usage += len(queries)
            headers = {"Content-Type": "application/json"}

            for query_text in queries:
                last_error = None
                # Retry up to 2 times for transient errors
                for attempt in range(2):
                    try:
                        params = {**self.params, "q": query_text, "api_key": self.serp_api_key}
                        resp = requests.get(
                            self.endpoint, headers=headers,
                            params=params, timeout=30)
                        resp.raise_for_status()

                        # Defensive JSON parsing: handle empty/truncated responses
                        raw_text = (resp.text or "").strip()
                        if not raw_text:
                            logger.error(
                                "SerpAPI returned empty body for '{}' (status={})".format(
                                    query_text[:60], resp.status_code))
                            if attempt < 1:
                                import time
                                time.sleep(1)
                            continue

                        try:
                            results = json.loads(raw_text)
                        except (json.JSONDecodeError, ValueError) as je:
                            logger.error(
                                "SerpAPI returned invalid JSON for '{}': {}. "
                                "Body (first 300 chars): {}".format(
                                    query_text[:60], je, raw_text[:300]))
                            break

                        # Check for SerpAPI error responses
                        if "error" in results:
                            logger.error(
                                "SerpAPI error for query '{}': {}".format(
                                    query_text[:80], results["error"]))
                            break

                        if "organic_results" in results:
                            result_count = 0
                            for d in results["organic_results"]:
                                if "link" in d and self.is_valid_source(d["link"]) and d["link"] not in exclude_urls:
                                    url_to_results[d["link"]] = {
                                        "url": d["link"],
                                        "title": d.get("title", ""),
                                        "description": d.get("snippet", ""),
                                        "position": d.get("position", 100),
                                        "publish_time": d.get("date", "Not Provided")
                                    }
                                    result_count += 1
                            logger.info(
                                "SerpAPI: '{}' returned {} organic results ({} after filtering)".format(
                                    query_text[:60],
                                    len(results["organic_results"]),
                                    result_count))
                        else:
                            logger.warning(
                                "SerpAPI: '{}' returned no organic_results. Keys: {}".format(
                                    query_text[:60], list(results.keys())))
                        break  # success, exit retry loop

                    except requests.exceptions.Timeout as e:
                        last_error = e
                        logger.warning(
                            "SerpAPI timeout for '{}' (attempt {}/2): {}".format(
                                query_text[:60], attempt + 1, e))
                        if attempt < 1:
                            import time
                            time.sleep(1)
                    except requests.exceptions.RequestException as e:
                        last_error = e
                        logger.error(
                            "SerpAPI request error for '{}': {}".format(
                                query_text[:60], e))
                        break
                    except Exception as e:
                        last_error = e
                        logger.error(
                            "SerpAPI unexpected error for '{}': {}".format(
                                query_text[:60], e))
                        break
                else:
                    # All retries exhausted
                    logger.error(
                        "SerpAPI: all retries failed for '{}': {}".format(
                            query_text[:60], last_error))

            # Log summary
            if len(url_to_results) == 0:
                logger.warning(
                    "SerpAPI: ZERO results for query '{}'. "
                    "Check SERPAPI key, network, and search parameters.".format(
                        query[:80]))

            # Save Cache
            if search_cache is not None:
                search_cache.save_cache(
                    name = cache_name,
                    call_args_dict = call_args_dict,
                    value = url_to_results
                )
        results = sorted(list(url_to_results.values()), key=lambda x: x["position"])
        pos2results = {}
        for idx, page in enumerate(results, start=1):
            page["position"] = idx
            pos2results[idx-1] = page
        return pos2results
    
    def fetch_content(
        self, pages
    ):
        urls = [page["url"] for page in pages]
        valid_url_to_snippets = self.webpage_helper.urls_to_snippets(urls)
        fetched_pages = []
        for page in pages:
            url = page["url"]
            if url not in valid_url_to_snippets: continue
            page["snippet"] = page["description"]
            del page["description"]
            long_res = "Snippet: {}\nContent: {}".format(
                page["snippet"], valid_url_to_snippets[url]["text"]
            )
            page["content"] = long_res
            fetched_pages.append(page)
        return fetched_pages
        


FORMAT_STRING_TEMPLATE = """
<search_result index={index}>
<source_type>{source_type}</source_type>
<title>
{title}
</title>
<url>
{url}
</url>
<page_time>
{publish_time}
</page_time>
<summary>
{content}
</summary>
</search_result>
"""

@tool_register.register_module()
class BingBrowser(BaseAction):
# class BingBrowser():
    """Wrapper around the Web Browser Tool.
    """
    def __init__(self,
                 searcher_type: str = 'SerpApiSearch',
                 timeout: int = 5,
                 black_list: Optional[List[str]] = [
                     'enoN',
                     'youtube.com',
                     'bilibili.com',
                     'researchgate.net',
                 ],
                 topk: int = 20,
                 pk_quota: int = 20,
                 select_quota: int = 8,
                 description: Optional[dict] = None,
                 parser: Type[BaseParser] = JsonParser,
                 search_max_thread: int = 10,
                 enable: bool = True,
                 language = "en",
                 selector_max_workers = 8,
                 summarizier_max_workers = 8,
                 selector_model = "gpt-4o-mini",
                 summarizer_model = "gpt-4o-mini",
                 backend_engine: str = "google",  # default to Google
                 cc: str = "US",  # default region
                 **kwargs):
        
        self.searcher_type = searcher_type
        self.select_quota = select_quota
        self.search_max_thread = search_max_thread
        self.language = language

        # Lazy import LocalKnowledgeBase to avoid circular import
        if searcher_type == "LocalKnowledgeBase":
            from recursive.executor.actions.local_knowledge_base import LocalKnowledgeBase
            self.searcher = LocalKnowledgeBase(topk=topk, **kwargs)
        elif searcher_type == "SerpApiSearch":
            # Pass backend_engine, cc, and language to SerpApiSearch
            self.searcher = SerpApiSearch(
                topk=topk, backend_engine=backend_engine, cc=cc,
                language=language, **kwargs)
        else:
            self.searcher = eval(searcher_type)(topk=topk, **kwargs)
        self.search_results = None
        self.pk_quota = pk_quota
        self.selector_max_workers = selector_max_workers
        self.summarizier_max_workers = summarizier_max_workers
        
        self.selector_model = selector_model
        self.summarizer_model = summarizer_model
        
        super().__init__(description, parser, enable)
    
    def __search(self, query_list, search_N):
        queries = query_list if isinstance(query_list, list) else [query_list]
        search_results = {}
        
        query2search_results = {}

        # Search 
        with ThreadPoolExecutor(max_workers=self.search_max_thread) as executor:
            future_to_query = {
                executor.submit(self.searcher.search, q): q
                for q in queries
            }
            for future in as_completed(future_to_query):
                query = future_to_query[future]
                try:
                    results = future.result()
                except Exception as exc:
                    import traceback
                    logger.error(f'{query} generated an exception: {traceback.format_exc()}')
                    query2search_results[query] = {}
                else:
                    query2search_results[query] = results
        N = search_N
        pk_results = []
        dedup_urls = set()
        cursors = {query:0 for query in queries}
        while len(pk_results) < N:
            find = False
            for query in queries:
                index = cursors[query]
                if index >= len(query2search_results[query]):
                    continue
                find = True
                page = query2search_results[query][index]
                page["search_query"] = query
                cursors[query] += 1
                if page['url'].endswith(".pdf"): continue
                if page['url'] in dedup_urls: continue 
                dedup_urls.add(page['url'])
                pk_results.append(page)
                page["pk_index"] = len(pk_results)
            if not find: break
        
        return pk_results
    
    def __single_fetch(self, search_results):
        return self.searcher.fetch_content(search_results)
        
    
    def __fetch(self, search_results):
        new_search_results = []
        with ThreadPoolExecutor() as executor:
            future_to_id = {
                executor.submit(self.searcher.fetch_content,
                                [page]): page for page in search_results
            }

            for future in as_completed(future_to_id):
                page = future_to_id[future]
                try:
                    fetched = future.result()
                    if fetched:
                        new_search_results.extend(fetched)
                except Exception as exc:
                    logger.error(f'{page["url"]} generated an exception: {exc}')
        new_search_results = sorted(new_search_results, key=lambda x: x["pk_index"])
        return new_search_results
    
    def __select_and_summarize(self, search_results, question, think, N, query_list):
        search_results = selector(search_results, question, think, N, query_list, 
                                  self.language, self.selector_max_workers,
                                  self.selector_model)
        search_results = summarizier(search_results, question, think, 
                                     self.language, self.summarizier_max_workers,
                                     self.summarizer_model)
        return search_results

 
    @tool_api()
    def direct_url_fetch(self, url_list: List[str], user_question: str):
        """Direct URL Fetch API - Fetches content directly from specified URLs without search.

        ### Specific Functions
        1. Directly fetches webpage content from given URLs
        2. Useful when you already know the exact URL(s) to retrieve
        3. Bypasses search engine indexing limitations

        ### Specific Return Content
        1. Returns the full text content of each successfully fetched URL
        2. Includes URL, title, and complete article text
        3. Returns error messages for URLs that fail to fetch

        Args:
            url_list ({"type"-"array","items"-{"type"-"string"}}): List of URLs to fetch directly
            user_question ({"type": "string"}): User's original question/context

        Returns:
            Dict[str, Any]: Dictionary containing:
                - web_pages: List of successfully fetched pages with url, title, content
                - result: Concatenated text of all fetched pages
                - failed_urls: List of URLs that failed to fetch with error reasons
        """
        import requests
        from bs4 import BeautifulSoup

        fetched_pages = []
        failed_urls = []

        for url in url_list:
            try:
                # Download webpage
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }

                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()

                # Extract content using trafilatura
                from trafilatura import extract
                article_text = extract(
                    response.text,
                    include_tables=True,
                    include_comments=False,
                    output_format="txt",
                )

                if article_text and len(article_text) > 50:
                    # Try to get page title
                    soup = BeautifulSoup(response.text, 'html.parser')
                    title_tag = soup.find('title')
                    title = title_tag.get_text().strip() if title_tag else url

                    fetched_pages.append({
                        "url": url,
                        "title": title,
                        "content": article_text,
                        "snippet": article_text[:200] + "..." if len(article_text) > 200 else article_text
                    })
                else:
                    failed_urls.append({
                        "url": url,
                        "reason": f"Content too short ({len(article_text) if article_text else 0} chars)"
                    })

            except Exception as e:
                logger.error(f"Failed to fetch URL {url}: {e}")
                failed_urls.append({
                    "url": url,
                    "reason": str(e)
                })

        # Format results
        result_parts = []
        for page in fetched_pages:
            result_parts.append(f"<url>{page['url']}</url>\n<title>{page['title']}</title>\n<content>{page['content']}\n")

        result = "\n\n".join(result_parts) if result_parts else "No content could be fetched from the provided URLs."

        return {
            "web_pages": fetched_pages,
            "result": result,
            "failed_urls": failed_urls
        }

    @tool_api()
    def full_pipeline_search(self, query_list, user_question, think, global_start_index, overwrite_cache=False):
        """Bing Web Browser Search API, which can retrieve webpage information
        ### Specific Functions
        1. Through this API, you can search multiple search queries in parallel, obtaining summaries of Bing search results corresponding to each search query. You must further retrieve the full text.
        2. The content of search results will only return titles and summaries, not the full text (thus some information may be missing). You can further retrieve all information by calling the BingBrowser-select_click tool to get the full text of multiple specified search results.
        3. Unless the summary contains all the needed information, you must call this tool to get the full text of the search results you need.

        ### Specific Return Content
        1. Returns all search query results in XML format, with everything contained within <search_results></search_results> tags. Each search result is contained within <result></result> tags, which have an index attribute specifying the sequence number of the search result. This sequence number can be used as a parameter for the subsequent BingBrowser-select_click tool to specify which full texts need to be retrieved.
        2. Within a single search result, there are the following tags:
            - <title></title>: Search result title
            - <url></url>: URL of the search result
            - <snippet></snippet>: Summary information of the search result. This information is a summary of the webpage content. To further get the full text, you need to use the BingBrowser-select_click tool
            - <publish_time></publish_time>: Webpage publication time, 'Not provided' indicates that the webpage does not provide a specific time

        Args:
            query_list ({"type"-"array","items"-{"type"-"string"}}): A set of search queries to be searched in parallel
            user_question ({"type": "string"}): User question
            think ({"type": "string"}): Thinking
            global_start_index ({"type": "int"}): start_index
            overwrite_cache ({"type": "boolean"}): Whether to force search and ignore cache

        Returns:
            Dict[str, str]: dict of search results
        """
        search_N = self.pk_quota # 20
        select_N = max(len(query_list), self.select_quota) # 4
        search_cache = caches["search"]

        # Load Cache
        cache_name = "BingBrowser.full_pipeline_search.BingSearch"
        call_args_dict = {
            "search_N": search_N,
            "query_list": query_list,
            "user_question": user_question,
            "think": think,
            "global_start_index": global_start_index,
            "searcher": self.searcher_type,
        }

        if search_cache is not None and not overwrite_cache:
            cache_result = search_cache.get_cache(
                name = cache_name,
                call_args_dict = call_args_dict
            )
            if cache_result is not None:
                logger.info("Returning cached search result (set overwrite_cache=True to force fresh search)")
                return cache_result

        # search
        pk_search_results = self.__search(query_list, search_N)
        
        ori_cnt = len(pk_search_results)
        ori_urls = [res["url"] for res in pk_search_results]
        # fetch web page content
        # pk_search_results = self.__fetch(pk_search_results)
        if self.searcher_type in ("SerpApiSearch", "SearXNG"):
            pk_search_results = self.__single_fetch(pk_search_results)
        else:
            raise Exception()
            
        logger.info("Querys {} after pk get {} results, fetched {} results, succ urls: \n{}, \nfailed urls: \n{}".format(
            str(query_list), ori_cnt, len(pk_search_results), 
            "\n".join([res["url"] for res in pk_search_results]),
            "\n".join(list(set(ori_urls) - set([res["url"] for res in pk_search_results])))
        ))
        
        # Check if we have any valid results
        if not pk_search_results:
            logger.warning("No web_pages found in search results")
            # Return a default response when all web page requests fail
            default_result = {
                "web_pages": [],
                "result": "No web pages could be retrieved due to access restrictions (403 Forbidden) or other errors.",
                "juege_and_summarized_search_results": [],
                "exclude_search_results": []
            }
            # save cache
            search_cache.save_cache(
                name=cache_name,
                call_args_dict=call_args_dict,
                value=default_result
            )
            return default_result
            
        logger.info("Start Select and Summarize")
            
        # select
        juege_and_summarized_search_results = self.__select_and_summarize(pk_search_results, user_question, think, select_N, query_list)
        # Final
        results = []
        for idx, page in enumerate(juege_and_summarized_search_results, start=global_start_index):
            page["global_index"] = idx
            results.append(FORMAT_STRING_TEMPLATE.format(
                index = idx,
                source_type="Web Search",
                title=page["title"],
                url=page["url"],
                publish_time=page["publish_time"],
                content=page["summary"]
            ))
        results = "\n\n".join(results)
        select_urls = set([page["url"] for page in juege_and_summarized_search_results])
        
        search_result = {
            "web_pages": juege_and_summarized_search_results,
            "result": results,
            "juege_and_summarized_search_results": juege_and_summarized_search_results,
            "exclude_search_results": [res for res in pk_search_results if res["url"] not in select_urls]
        }
        
        # save cache
        search_cache.save_cache(
            name = cache_name,
            call_args_dict = call_args_dict,
            value = search_result
        )
    
        return search_result


class SearXNG(BaseSearch):
    """SearXNG-based search backend (self-hosted, no API key required)."""
    def __init__(
        self,
        searxng_api_url: str = None,
        searxng_api_key: str = None,
        topk: int = 3,
        is_valid_source = None,
        backend_engine: str = None,
        min_char_count: int = 150,
        snippet_chunk_size: int = 1000,
        webpage_helper_max_threads: int = 10,
        **kwargs
    ):
        super().__init__(topk=topk, black_list=[])
        self.searxng_api_url = searxng_api_url or os.environ.get("SearXNG", "http://127.0.0.1:8080/search")
        try:
            requests.get(self.searxng_api_url, timeout=5).raise_for_status() # one-liner health check
        except requests.RequestException as e:
            logger.error(f"SearXNG API URL `{self.searxng_api_url}` is not reachable: {e} / set an env variable `SearXNG` or by pas searxng_api_url parameter. Don't forget to prefix with http:// or https://")
        self.searxng_api_key = searxng_api_key
        self.backend = backend_engine
        self.usage = 0
        self.is_valid_source = is_valid_source or (lambda x: True)
        self.webpage_helper = WebPageHelper(
            min_char_count=min_char_count,
            snippet_chunk_size=snippet_chunk_size,
            max_thread_num=webpage_helper_max_threads,
        )
        self.usage = 0
        self.is_valid_source = is_valid_source or (lambda x: True)
        self.webpage_helper = WebPageHelper(
            min_char_count=min_char_count,
            snippet_chunk_size=snippet_chunk_size,
            max_thread_num=webpage_helper_max_threads,
        )

    def get_usage_and_reset(self):
        u = self.usage
        self.usage = 0
        return {"SearXNG": u}

    def search(
        self, query: str, exclude_urls: List[str] = [], overwrite_cache: bool = False
    ) -> dict:
        """Search using SearXNG (and optionally SerpApi).

        Args:
            query: Search query string
            exclude_urls: List of URLs to exclude from results
            overwrite_cache: Whether to overwrite cached results

        Returns:
            Dictionary of search results indexed by position
        """
        self.usage += 1

        # Decide search method based on configuration
        if self.backend == "serpapi":
            return self._search_with_serpapi(query, exclude_urls, overwrite_cache)
        else:
            return self._search_with_api(query)

    def _search_with_api(self, query: str, exclude_urls: List[str] = [], overwrite_cache: bool = False):
        """Use SerpApi (or fallback to plain text search)"""
        import time
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh"
            }

            # Try SerpApi first
            try:
                params = {
                    "q": query,
                    "format": "json",
                    "engine": "google",  # Use Google via SerpApi
                    "cc": "cn",
                    "num": self.topk,
                    "device": "mobile",
                    "site": "news"
                }

                resp = requests.get(
                    "https://serperp.dev/search",
                    params=params,
                    headers=headers,
                    timeout=10
                )
                resp.raise_for_status()

                if resp.status_code == 200:
                    json_value = resp.json()
                    hits = json_value.get("organic_results", [])
                    pages = []
                    idx = 1
                    for r in hits:
                        url = r.get("link")
                        title = r.get("title", "")
                        description = r.get("snippet", "")
                        if (url and self.is_valid_source(url)):
                            pages.append({
                                "url": url,
                                "title": title,
                                "description": description,
                                "position": idx,
                                "publish_time": "Not Provided"
                            })
                            idx += 1
                    return {i: p for i, p in enumerate(pages)}

            except Exception as e:
                logger.error(f"SerpApi search failed for `{query}`: {e}")
        except Exception as e:
            logger.error(f"Error during SerpApi request: {e}")

        # Fallback to plain text search
        return self._search_plain(query)

    def _search_plain(self, query: str) -> dict:
        """Fallback plain text search (no API or API failed)"""
        # Use basic text search as fallback
        try:
            from duckduckgo_search import DDGS
            results_gen = DDGS()
            results_gen = results_gen.text(f"site:developer.aliyun.com \"{query}\"")
            idx = 1
            pages = []
            for r in results_gen:
                url = r.get("href", "")
                title = r.get("title", "")
                snippet = r.get("body", "")
                if url and self.is_valid_source(url):
                    pages.append({
                        "url": url,
                        "title": title,
                        "description": snippet,
                        "position": idx,
                        "publish_time": "Not Provided"
                    })
                    idx += 1
                if idx > self.topk:
                    break
            return {i: p for i, p in enumerate(pages)}
        except Exception as e:
            logger.error(f"Error during text search fallback for `{query}`: {e}")
            return {}
    def get_usage_and_reset(self):
        u = self.usage
        self.usage = 0
        return {"SearXNG": u}

    def search(
        self, query: str, exclude_urls: List[str] = [], overwrite_cache: bool = False
    ) -> dict:
        self.usage += 1
        headers = (
            {"Authorization": f"Bearer {self.searxng_api_key}"}
            if self.searxng_api_key
            else {}
        )
        try:
            resp = requests.get(
                self.searxng_api_url,
                headers=headers,
                params={"q": query, "format": "json"},
                timeout=10,
            )
            resp.raise_for_status()
            json_value = resp.json()
            hits = json_value.get("results", [])
        except Exception as e:
            logger.error(f"SearXNG lookup failed for `{query}`: {e}")
            return {}

        pages = []
        idx = 1
        for r in hits:
            url = r.get("url")
            if (
                not url
                or not self.is_valid_source(url)
                or url.endswith(".pdf")
                or url in exclude_urls
            ):
                continue
            pages.append({"url": url, "title": r.get("title", ""), "description": r.get("content", ""), "position": idx, "publish_time": "Not Provided",})
            idx += 1
            if idx > self.topk:
                break
        return {i: p for i, p in enumerate(pages)}

    def fetch_content(
        self, pages: List[dict]
    ) -> List[dict]:
        urls = [page["url"] for page in pages]
        valid_url_to_snippets = self.webpage_helper.urls_to_snippets(urls)
        fetched_pages = []
        for page in pages:
            url = page["url"]
            if url not in valid_url_to_snippets:
                continue
            page["snippet"] = page["description"]
            del page["description"]
            long_res = "Snippet: {}\nContent: {}".format(
                page["snippet"], valid_url_to_snippets[url]["text"]
            )
            page["content"] = long_res
            fetched_pages.append(page)
        return fetched_pages


class DuckDuckGoSearch(BaseSearch):
    """DuckDuckGo search engine implementation using duckduckgo_search package.

    This is a free search engine that doesn't require API keys.
    Acknowledgement: Uses https://pypi.org/project/duckduckgo-search/ package.
    """

    def __init__(
        self,
        topk: int = 10,
        is_valid_source = None,
        min_char_count: int = 150,
        snippet_chunk_size: int = 1000,
        webpage_helper_max_threads: int = 10,
        region: str = "en-US",
        safesearch: str = "moderate",
        timelimit: str = None,
        backend: str = "html",  # Use HTML backend instead of API to reduce ratelimit issues
        **kwargs
    ):
        super().__init__(topk=topk, black_list=[])
        self.region = region
        self.safesearch = safesearch
        self.timelimit = timelimit
        self.backend = backend
        self.usage = 0
        self.is_valid_source = is_valid_source or (lambda x: True)
        self.webpage_helper = WebPageHelper(
            min_char_count=min_char_count,
            snippet_chunk_size=snippet_chunk_size,
            max_thread_num=webpage_helper_max_threads,
        )

    def get_usage_and_reset(self):
        u = self.usage
        self.usage = 0
        return {"DuckDuckGoSearch": u}

    def search(
        self, query: str, exclude_urls: List[str] = [], overwrite_cache: bool = False
    ) -> dict:
        """Search using DuckDuckGo.

        Args:
            query: Search query string
            exclude_urls: List of URLs to exclude from results
            overwrite_cache: Whether to overwrite cached results

        Returns:
            Dictionary of search results indexed by position
        """
        from duckduckgo_search import DDGS
        import time

        self.usage += 1

        # Check cache first
        search_cache = caches["search"]
        cache_name = "DuckDuckGoSearch.search"
        call_args_dict = {
            "query": query,
            "region": self.region,
            "safesearch": self.safesearch,
            "timelimit": self.timelimit,
        }

        if search_cache is not None and not overwrite_cache:
            cache_result = search_cache.get_cache(
                name=cache_name,
                call_args_dict=call_args_dict
            )
            if cache_result is not None:
                return cache_result

        max_retries = 3
        retry_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                # Perform search using DDGS with HTML backend
                with DDGS() as ddgs:
                    results_gen = ddgs.text(
                        query,
                        region=self.region,
                        safesearch=self.safesearch,
                        timelimit=self.timelimit,
                        max_results=self.topk,
                        backend=self.backend
                    )

                    pages = []
                    idx = 1
                    for r in results_gen:
                        url = r.get("href") or r.get("url")
                        title = r.get("title", "")
                        description = r.get("body", "")

                        if (
                            not url
                            or not self.is_valid_source(url)
                            or url.endswith(".pdf")
                            or url in exclude_urls
                        ):
                            continue

                        pages.append({
                            "url": url,
                            "title": title,
                            "description": description,
                            "position": idx,
                            "publish_time": "Not Provided"
                        })
                        idx += 1
                        if idx > self.topk:
                            break

                    # Save to cache
                    if search_cache is not None:
                        result_dict = {i: p for i, p in enumerate(pages)}
                        search_cache.save_cache(
                            name=cache_name,
                            call_args_dict=call_args_dict,
                            value=result_dict
                        )

                    return {i: p for i, p in enumerate(pages)}

            except Exception as e:
                error_msg = str(e)
                if "Ratelimit" in error_msg and attempt < max_retries - 1:
                    logger.warning(f"DuckDuckGo rate limit hit, retrying in {retry_delay}s... (attempt {attempt+1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # exponential backoff
                else:
                    logger.error(f"DuckDuckGo search failed for `{query}`: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    break

        return {}

    def fetch_content(
        self, pages: List[dict]
    ) -> List[dict]:
        """Fetch full content from web pages.

        Args:
            pages: List of page dictionaries with 'url' keys

        Returns:
            List of pages with added 'content' field
        """
        urls = [page["url"] for page in pages]
        valid_url_to_snippets = self.webpage_helper.urls_to_snippets(urls)
        fetched_pages = []
        for page in pages:
            url = page["url"]
            if url not in valid_url_to_snippets:
                continue
            page["snippet"] = page["description"]
            del page["description"]
            long_res = "Snippet: {}\nContent: {}".format(
                page["snippet"], valid_url_to_snippets[url]["text"]
            )
            page["content"] = long_res
            fetched_pages.append(page)
        return fetched_pages

class BingSearch(BaseSearch):
    """Bing search engine implementation using web scraping.

    This is a free search engine that doesn't require API keys.
    Uses requests and BeautifulSoup to scrape Bing search results.
    """

    def __init__(
        self,
        topk: int = 10,
        is_valid_source = None,
        min_char_count: int = 150,
        snippet_chunk_size: int = 1000,
        webpage_helper_max_threads: int = 10,
        lang: str = "en",
        region: str = "us",
        **kwargs
    ):
        super().__init__(topk=topk, black_list=[])
        self.lang = lang
        self.region = region
        self.usage = 0
        self.is_valid_source = is_valid_source or (lambda x: True)
        self.webpage_helper = WebPageHelper(
            min_char_count=min_char_count,
            snippet_chunk_size=snippet_chunk_size,
            max_thread_num=webpage_helper_max_threads,
        )

    def get_usage_and_reset(self):
        u = self.usage
        self.usage = 0
        return {"BingSearch": u}

    def search(
        self, query: str, exclude_urls: List[str] = [], overwrite_cache: bool = False
    ) -> dict:
        """Search using Bing web scraping.

        Args:
            query: Search query string
            exclude_urls: List of URLs to exclude from results
            overwrite_cache: Whether to overwrite cached results

        Returns:
            Dictionary of search results indexed by position
        """
        import requests
        from bs4 import BeautifulSoup

        self.usage += 1

        # Check cache first
        search_cache = caches["search"]
        cache_name = "BingSearch.search"
        call_args_dict = {
            "query": query,
            "lang": self.lang,
            "region": self.region,
        }

        if search_cache is not None and not overwrite_cache:
            cache_result = search_cache.get_cache(
                name=cache_name,
                call_args_dict=call_args_dict
            )
            if cache_result is not None:
                return cache_result

        try:
            url = "https://www.bing.com/search"
            params = {
                "q": query,
                "count": self.topk * 2,  # Get more results to filter
                "setlang": self.lang,
                "cc": self.region
            }

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            pages = []
            idx = 1

            # Find search result li elements with class b_algo
            for g in soup.find_all('li', class_='b_algo'):
                anchor = g.find('a')
                title_div = g.find('h2')
                snippet = g.find('div', class_='b_caption') or g.find('p')

                if anchor and title_div:
                    link = anchor['href']
                    title = title_div.get_text()
                    description = snippet.get_text() if snippet else ""

                    # Filter out Bing redirect URLs
                    if link.startswith("https://www.bing.com/ck/a"):
                        # Extract actual URL from redirect
                        import urllib.parse as urlparse
                        import base64
                        parsed = urlparse.urlparse(link)
                        query_params = urlparse.parse_qs(parsed.query)

                        # Try to get the 'u' parameter which contains the encoded target URL
                        if 'u' in query_params:
                            encoded_url = query_params['u'][0]
                            try:
                                # Bing uses base64 encoding for the u parameter with 'a1' prefix
                                # Add padding if necessary
                                encoded_part = encoded_url[2:]  # Remove 'a1' prefix
                                # Add padding to make length divisible by 4
                                padding_needed = (4 - len(encoded_part) % 4) % 4
                                encoded_part += '=' * padding_needed
                                decoded_link = base64.b64decode(encoded_part).decode('utf-8')
                                link = decoded_link
                                logger.debug(f"Successfully decoded Bing URL: {link[:80]}...")
                            except Exception as e:
                                logger.debug(f"Failed to decode Bing URL ({encoded_url[:50]}...): {e}")
                                # Skip this result as we can't get the actual URL
                                continue
                        else:
                            # No 'u' parameter, skip this result
                            logger.debug(f"Bing URL has no 'u' parameter: {link[:100]}...")
                            continue

                    if (
                        not link
                        or not self.is_valid_source(link)
                        or link.endswith(".pdf")
                        or link in exclude_urls
                    ):
                        continue

                    pages.append({
                        "url": link,
                        "title": title,
                        "description": description,
                        "position": idx,
                        "publish_time": "Not Provided"
                    })
                    idx += 1
                    if idx > self.topk:
                        break

            # Save to cache
            if search_cache is not None:
                result_dict = {i: p for i, p in enumerate(pages)}
                search_cache.save_cache(
                    name=cache_name,
                    call_args_dict=call_args_dict,
                    value=result_dict
                )

            return {i: p for i, p in enumerate(pages)}

        except Exception as e:
            logger.error(f"Bing search failed for `{query}`: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return {}

    def fetch_content(
        self, pages: List[dict]
    ) -> List[dict]:
        """Fetch full content from web pages.

        Args:
            pages: List of page dictionaries with 'url' keys

        Returns:
            List of pages with added 'content' field
        """
        urls = [page["url"] for page in pages]
        valid_url_to_snippets = self.webpage_helper.urls_to_snippets(urls)
        fetched_pages = []
        for page in pages:
            url = page["url"]
            if url not in valid_url_to_snippets:
                continue
            page["snippet"] = page["description"]
            del page["description"]
            long_res = "Snippet: {}\nContent: {}".format(
                page["snippet"], valid_url_to_snippets[url]["text"]
            )
            page["content"] = long_res
            fetched_pages.append(page)
        return fetched_pages


class GoogleSearch(BaseSearch):
    """Google search engine implementation using web scraping.

    This is a free search engine that doesn't require API keys.
    Uses requests and BeautifulSoup to scrape Google search results.
    """

    def __init__(
        self,
        topk: int = 10,
        is_valid_source = None,
        min_char_count: int = 150,
        snippet_chunk_size: int = 1000,
        webpage_helper_max_threads: int = 10,
        lang: str = "en",
        region: str = "us",
        **kwargs
    ):
        super().__init__(topk=topk, black_list=[])
        self.lang = lang
        self.region = region
        self.usage = 0
        self.is_valid_source = is_valid_source or (lambda x: True)
        self.webpage_helper = WebPageHelper(
            min_char_count=min_char_count,
            snippet_chunk_size=snippet_chunk_size,
            max_thread_num=webpage_helper_max_threads,
        )

    def get_usage_and_reset(self):
        u = self.usage
        self.usage = 0
        return {"GoogleSearch": u}

    def search(
        self, query: str, exclude_urls: List[str] = [], overwrite_cache: bool = False
    ) -> dict:
        """Search using Google.

        Args:
            query: Search query string
            exclude_urls: List of URLs to exclude from results
            overwrite_cache: Whether to overwrite cached results

        Returns:
            Dictionary of search results indexed by position
        """
        from googlesearch import search

        self.usage += 1

        # Check cache first
        search_cache = caches["search"]
        cache_name = "GoogleSearch.search"
        call_args_dict = {
            "query": query,
            "lang": self.lang,
            "region": self.region,
        }

        if search_cache is not None and not overwrite_cache:
            cache_result = search_cache.get_cache(
                name=cache_name,
                call_args_dict=call_args_dict
            )
            if cache_result is not None:
                return cache_result

        try:
            # Perform search using Google
            pages = []
            idx = 1

            # Use the googlesearch package to get results
            for result in search(query, lang=self.lang, region=self.region, num_results=self.num_results, advanced=True):
                url = result.url
                title = result.title
                description = result.description
                if (
                    not url
                    or not self.is_valid_source(url)
                    or url.endswith(".pdf")
                    or url in exclude_urls
                ):
                    continue

                pages.append({
                    "url": url,
                    "title": title,
                    "description": description,
                    "position": idx,
                    "publish_time": "Not Provided"
                })
                idx += 1
                if idx > self.topk:
                    break

            # Save to cache
            if search_cache is not None:
                result_dict = {i: p for i, p in enumerate(pages)}
                search_cache.save_cache(
                    name=cache_name,
                    call_args_dict=call_args_dict,
                    value=result_dict
                )

            return {i: p for i, p in enumerate(pages)}

        except Exception as e:
            logger.error(f"Google search failed for `{query}`: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return {}

    def fetch_content(
        self, pages: List[dict]
    ) -> List[dict]:
        """Fetch full content from web pages.

        Args:
            pages: List of page dictionaries with 'url' keys

        Returns:
            List of pages with added 'content' field
        """
        urls = [page["url"] for page in pages]
        valid_url_to_snippets = self.webpage_helper.urls_to_snippets(urls)
        fetched_pages = []
        for page in pages:
            url = page["url"]
            if url not in valid_url_to_snippets:
                continue
            page["snippet"] = page["description"]
            del page["description"]
            long_res = "Snippet: {}\nContent: {}".format(
                page["snippet"], valid_url_to_snippets[url]["text"]
            )
            page["content"] = long_res
            fetched_pages.append(page)
        return fetched_pages


if __name__ == "__main__":
    from recursive.cache import Cache
    caches["search"] = Cache("temp/search")
    caches["web_page"] = Cache("temp/web_page")
    caches["llm"] = Cache("temp/llm")

    browser = BingBrowser(searcher_type="SerpApiSearch",
                          backend_engine = "bing",
                          cc = "US",
                          webpage_helper_max_threads = 10,
                          search_max_thread = 10,
                          pk_quota = 20,
                          select_quota = 4,
                          language = "en"
                          )
