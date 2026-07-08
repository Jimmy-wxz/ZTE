import os
import threading
from typing import Any, Dict, List, Optional

from loguru import logger

from recursive.executor.actions import BaseAction, tool_api
from recursive.executor.actions.bing_browser import FORMAT_STRING_TEMPLATE
from recursive.executor.actions.register import tool_register
from recursive.knowledge_base.service import KnowledgeBaseService


_SERVICE_CACHE = {}
_SERVICE_CACHE_LOCK = threading.Lock()


@tool_register.register_module()
class LocalKnowledgeBase(BaseAction):
    """Local Chroma-based RAG knowledge base retrieval action.

    This action retrieves relevant passages from uploaded documents stored in a
    Chroma vector database. Its return format mirrors ``BingBrowser.full_pipeline_search``
    so the SearchAgent can consume it without any extra parsing logic.
    """

    def __init__(
        self,
        knowledge_base_name: Optional[str] = None,
        topk: int = 5,
        distance_threshold: float = None,
        **kwargs,
    ):
        super().__init__()
        self.knowledge_base_name = (
            knowledge_base_name
            or os.environ.get("WRITEHERE_KB_NAME")
        )
        self.topk = topk
        self.distance_threshold = distance_threshold
        self._service = None

    def _get_service(self) -> KnowledgeBaseService:
        if self._service is None:
            base_path = os.environ.get("WRITEHERE_KB_PATH")
            cache_key = os.path.abspath(base_path) if base_path else "__default__"
            with _SERVICE_CACHE_LOCK:
                if cache_key not in _SERVICE_CACHE:
                    _SERVICE_CACHE[cache_key] = KnowledgeBaseService(base_path=base_path)
                self._service = _SERVICE_CACHE[cache_key]
        return self._service

    @tool_api()
    def search(
        self,
        query_list,
        user_question,
        think,
        global_start_index,
    ):
        """Retrieve relevant passages from the local knowledge base.

        Args:
            query_list (list[str]): A set of search queries to be searched in parallel.
            user_question (str): User question.
            think (str): Thinking context.
            global_start_index (int): Start index for result numbering.

        Returns:
            dict: Matching ``BingBrowser.full_pipeline_search`` output with keys
            ``web_pages``, ``result``, ``juege_and_summarized_search_results`` and
            ``exclude_search_results``.
        """
        if not self.knowledge_base_name:
            logger.warning("LocalKnowledgeBase called without knowledge_base_name")
            return self._empty_result()

        service = self._get_service()
        all_pages = []
        seen_ids = set()

        for query in query_list:
            try:
                results = service.search(
                    self.knowledge_base_name, query,
                    topk=self.topk,
                    distance_threshold=self.distance_threshold)
            except Exception as e:
                logger.warning("Knowledge base search failed for '{}': {}".format(query, e))
                results = []

            for hit in results:
                chunk_id = "{}:{}".format(hit.get("source", "unknown"), hit.get("chunk_index", -1))
                if chunk_id in seen_ids:
                    continue
                seen_ids.add(chunk_id)
                source = hit.get("source", "unknown")
                file_path = hit.get("file_path", "")
                page = {
                    "global_index": global_start_index + len(all_pages),
                    "title": "Local KB: {}".format(source),
                    "url": "local-kb://{}".format(source),
                    "publish_time": "Local Knowledge Base",
                    "summary": hit.get("text", ""),
                    "search_query": query,
                    "source": source,
                    "file_path": file_path,
                    "chunk_index": hit.get("chunk_index", -1),
                    "distance": hit.get("distance", None),
                    "pk_index": len(all_pages) + 1,
                }
                all_pages.append(page)

        if not all_pages:
            return self._empty_result()

        formatted_results = []
        for page in all_pages:
            formatted_results.append(FORMAT_STRING_TEMPLATE.format(
                index=page["global_index"],
                source_type="Local KB",
                title=page["title"],
                url=page["url"],
                publish_time=page["publish_time"],
                content=page["summary"],
            ))

        result_xml = "\n\n".join(formatted_results)
        return {
            "web_pages": all_pages,
            "result": result_xml,
            "juege_and_summarized_search_results": all_pages,
            "exclude_search_results": [],
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "web_pages": [],
            "result": "No relevant passages found in the local knowledge base.",
            "juege_and_summarized_search_results": [],
            "exclude_search_results": [],
        }
