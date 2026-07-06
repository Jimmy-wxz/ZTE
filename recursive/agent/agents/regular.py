#coding:utf8

from typing import Dict, List
from abc import ABC, abstractmethod
from overrides import overrides
import os
import random
import json
from recursive.utils.register import Register
from recursive.executor.actions.register import executor_register, tool_register
from recursive.executor.actions import ActionExecutor
from recursive.utils.file_io import make_mappings
from recursive.llm.llm import OpenAIApiProxy
from recursive.utils.file_io import parse_hierarchy_tags_result
from copy import deepcopy
from pprint import pprint
from loguru import logger
from recursive.agent.agent_base import agent_register, Agent
from recursive.agent.prompts.base import prompt_register
from recursive.executor.agents.claude_fc_react import SearchAgent
from recursive.executor.actions.bing_browser import BingBrowser, SerpApiSearch, FORMAT_STRING_TEMPLATE
from recursive.executor.actions.local_knowledge_base import LocalKnowledgeBase
from recursive.knowledge_base.embedding import get_reranker
import re
    

def get_llm_output(node, agent, memory, agent_type, overwrite_cache=False, *args, **kwargs):
    memory_info = memory.collect_node_run_info(node)
    task_type = node.task_info.get("task_type", "")
    
    if task_type == "":
        inner_kwargs = node.config[task_type]
    else:
        task_type = node.task_type_tag
        inner_kwargs = node.config[task_type][agent_type]
        
    if agent_type == "planning":
        if not inner_kwargs.get("depth_diff", False):
            prompt_version = inner_kwargs["prompt_version"]
        else:
            if node.node_graph_info["outer_node"] is None:
                prompt_version = inner_kwargs["depth_1_prompt_version"]
            else:
                prompt_version = inner_kwargs["depth_N_prompt_version"]      
    elif agent_type == "atom":
        if inner_kwargs.get("update_diff", False):
            if len(node.node_graph_info["parent_nodes"]) > 0:
                prompt_version = inner_kwargs["with_update_prompt_version"]
            else:
                prompt_version = inner_kwargs["without_update_prompt_version"]
        else:
            prompt_version = inner_kwargs["prompt_version"]
    else:
        prompt_version = inner_kwargs["prompt_version"]
        
    to_run_check_str = kwargs.get("to_run_check_str", None)
    
    system_message = prompt_register.module_dict[prompt_version]().construct_system_message(
        to_run_check_str = to_run_check_str
    )
    to_run_task = deepcopy(node.task_info)
    for k in ("candidate_plan", "candidate_think"):
        if k in to_run_task:
            del to_run_task[k]
            
    if kwargs.get("nl", False) and agent_type in ("execute", "final_aggregate"):
        to_run_task = node.task_info["goal"]
        if "length" in node.task_info:
            if node.config.get("language", "") == "en":
                to_run_task += " Word count requirement: approximately {}".format(node.task_info["length"])
            else:
                to_run_task += " 要求字数：约{}".format(node.task_info["length"])
        to_run_outer_graph_dependent = []
        for layer_tasks in memory_info["upper_graph_precedents"]:
            for t in layer_tasks:
                to_run_outer_graph_dependent.append("【{}】:\n {}".format(t["goal"], t["result"]))
        to_run_outer_graph_dependent = "\n\n".join(to_run_outer_graph_dependent) 
        to_run_same_graph_dependent = "\n\n".join(["【{}】: \n{}".format(t["goal"], t["result"]) for t in memory_info["same_graph_precedents"]])
    else:
        to_run_task = json.dumps(to_run_task, ensure_ascii=False)
        to_run_outer_graph_dependent = []
        for layer_tasks in memory_info["upper_graph_precedents"]:
            for t in layer_tasks:
                to_run_outer_graph_dependent.append("【{}】:\n {}".format(t["goal"], t["result"]))
        to_run_outer_graph_dependent = "\n\n".join(to_run_outer_graph_dependent) 
        to_run_same_graph_dependent = "\n\n".join(["【{}】: \n{}".format(t["goal"], t["result"]) for t in memory_info["same_graph_precedents"]])

    to_run_target_write_tasks = ""
    if task_type == "RETRIEVAL":
        depend_write_task = node.get_direct_depend_write_task()
        if node.config["language"] == "zh":
            to_run_target_write_tasks = "\n".join(
                "COMPOSITION任务{}，字数：{}".format(idx, node.task_info["length"]) for idx, node in enumerate(depend_write_task, start=1)
            ) if (depend_write_task is not None and len(depend_write_task) > 0) else "Not Provided"
        else:
            to_run_target_write_tasks = "\n".join(
                "Write Task{}，word count requirements：{}".format(idx, node.task_info["length"]) for idx, node in enumerate(depend_write_task, start=1)
            ) if (depend_write_task is not None and len(depend_write_task) > 0) else "Not Provided"
        
    
    # Prepare prompt arguments
    prompt_args = {
        'to_run_root_question': memory.root_node.task_info["goal"],
        'to_run_article': memory.article,
        'to_run_full_plan': node.get_all_layer_plan(),
        'to_run_outer_graph_dependent': to_run_outer_graph_dependent,
        'to_run_same_graph_dependent': to_run_same_graph_dependent,
        'to_run_task': to_run_task,
        'to_run_candidate_plan': node.task_info.get("candidate_plan", "Missing"),
        'to_run_candidate_think': node.task_info.get("candidate_think", "Missing"),
        'to_run_final_aggregate': kwargs.get("to_run_final_aggregate", ""),
        'to_run_target_write_tasks': to_run_target_write_tasks,
        'to_run_global_writing_task': node.get_all_previous_writing_plan(),
        'today_date': node.config.get('today_date', 'Mar 26, 2025')  # Add today_date from config
    }
    
    prompt = prompt_register.module_dict[prompt_version]().construct_prompt(**prompt_args)
    llm_result = agent.call_llm(
        system_message = system_message,
        prompt = prompt,
        parse_arg_dict = inner_kwargs["parse_arg_dict"],
        overwrite_cache = overwrite_cache,
        **inner_kwargs.get("llm_args", {})
    ) 
    return llm_result


def extract_json_content(text):
    pattern = r'```json\s*(.*?)\s*```'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None



@agent_register.register_module()
class UpdateAtomPlanningAgent(Agent):
    @overrides
    def forward(self, node, memory, *args, **kwargs) -> str:
        """
        {
            atom: {
                prompt_version: xxx,
                llm_args: {xxx},
                parse_arg_dict: {},
                "atom_result_flag": "原子任务"
            }
            planning: {
                prompt_version: xxx,
                llm_args: {xxx},
                parse_arg_dict: {}
            }
        }
        """
        return_result = {}
        # Check Atom
        task_type = node.task_info.get("task_type", "")
        if task_type == "":
            inner_kwargs = node.config[task_type]
        else:
            task_type = node.task_type_tag
            inner_kwargs = node.config[task_type]["atom"]
            
        if inner_kwargs.get("all_atom", False):
            if not "prompt_version" in inner_kwargs:
                plan_result = []
                return_result["result"] = plan_result
            else:
                # update, but is atom task
                # judge only_on_depend
                if (not inner_kwargs.get("only_on_depend", False)) or (
                    len(node.node_graph_info["parent_nodes"]) > 0
                ):
                    atom_llm_result = get_llm_output(
                        node, self, memory, "atom", *args, **kwargs
                    )
                    atom_llm_result["atom_original"] = atom_llm_result.pop("original")
                    if atom_llm_result.get("update_result", ""):
                        ori_goal = node.task_info["goal"]
                        node.task_info["goal"] = atom_llm_result.get("update_result", "").replace("\n", "; ")
                        logger.info("Update goal from {} to {}".format(
                            ori_goal, node.task_info["goal"] 
                        )) 
                    return_result.update(atom_llm_result)
                plan_result = []
                return_result["result"] = plan_result     
                
        elif inner_kwargs.get("use_candidate_plan", False):
            candidate_plan = node.task_info["candidate_plan"]
            plan_result = []
            if not isinstance(candidate_plan, list):
                logger.info("Candidate Plan Missing: {}".format(candidate_plan))                
            else:
                plan_result = candidate_plan
            return_result["result"] = plan_result
            logger.info("Use Candidate Plan for: {}, the candidate plan is \n{}".format(
                node.task_info["goal"],
                return_result["result"]
            ))
        elif "force_atom_layer" in inner_kwargs and node.node_graph_info["layer"] >= inner_kwargs["force_atom_layer"]:
            plan_result = []
            return_result["result"] = plan_result
            logger.info("Current Node: {}, Layer = {}, >= force atom layer(), force to atom".format(
                node, node.node_graph_info["layer"], inner_kwargs["force_atom_layer"]
            ))
        else:
            succ = False
            retry_cnt = 0
            while not succ and retry_cnt < 10:
                atom_llm_result = get_llm_output(
                    node, self, memory, "atom", retry_cnt > 0, *args, **kwargs
                )
            # Determine if it failed. If atom_result is not one of "atomic" or "complex" then it's a failure, otherwise it's successful
                succ = (atom_llm_result["atom_result"].strip() in ("atomic", "complex"))
                if not succ:
                    logger.error("ATOM Judgement for {} is failed, Get Response: {}, retry_cnt={}".format(node, 
                                                                                                          atom_llm_result["original"],
                                                                                                          retry_cnt))
                    retry_cnt += 1

            atom_llm_result["atom_original"] = atom_llm_result.pop("original")
            return_result.update(atom_llm_result)
            # Use atom's thinking as candidate_think for recursive planning
            node.task_info["candidate_think"] = atom_llm_result["atom_think"]
            if atom_llm_result.get("update_result", ""):
                node.task_info["goal"] = atom_llm_result.get("update_result", "").replace("\n", "; ")
        
            if atom_llm_result["atom_result"] == inner_kwargs["atom_result_flag"]:
                plan_result = []
                return_result["result"] = plan_result
            else: # Need Recursive Planning
                succ = False
                retry_cnt = 0
                plan_result = []
                while not succ and retry_cnt < 10:
                    plan_llm_result = get_llm_output(
                        node, self, memory, "planning", retry_cnt > 0, *args, **kwargs
                    )
                    try:
                        plan_result = self.parse_result(plan_llm_result["plan_result"])
                    except Exception as e: 
                        # Incorrect format, cannot get plan_result, first check if planning can be extracted directly from the response
                        source = plan_llm_result["plan_result"].strip() if plan_llm_result["plan_result"].strip() != "" else plan_llm_result["original"]
                        plan_llm_result["plan_result"] = extract_json_content(source) # If fail to fetch, return None
                        try: 
                            plan_result = self.parse_result(plan_llm_result["plan_result"])
                        except Exception as e:
                            logger.error("Planning for {} failed, original is {}, retry {}".format(
                                node, plan_llm_result["original"], retry_cnt
                            ))
                            retry_cnt += 1
                            continue 
                    succ = True
                        
                plan_llm_result["result"] = plan_result
                return_result.update(plan_llm_result)
            
        return return_result

    @overrides
    def parse_result(self, agent_output, *args, **kwargs) -> Dict:
        return json.loads(agent_output.strip().strip('`').replace('json', '').strip())["sub_tasks"]


FORMAT_STRING_TEMPLATE = """
<web_page index={index}>
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
</web_page>
"""



@agent_register.register_module()
class SimpleExcutor(Agent):
    @overrides
    def forward(self, node, memory, *args, **kwargs) -> str:
        """
        {
            executor: {
                prompt_version: xxx,
                llm_args: {xxx},
                parse_arg_dict: {},
            }
        }
        """
        task_type = node.task_type_tag
        inner_kwargs = node.config[task_type]["execute"]
        if task_type == "RETRIEVAL" and inner_kwargs.get("react_agent", False):
            # Determine whether to use the local knowledge base
            use_kb = os.environ.get("WRITEHERE_USE_KB", "false").lower() == "true"
            kb_name = os.environ.get("WRITEHERE_KB_NAME", "")
            backend_engine = str(inner_kwargs.get("backend_engine", "")).lower()

            # Skip web search when engine_backend is "none", but still allow local KB retrieval
            if backend_engine == "none" and not use_kb:
                logger.info("Search engine backend is 'none' and no KB enabled, skipping search for: {}".format(
                    node.task_info.get("goal", "")[:80]))
                return {
                    "ori": [],
                    "result": "Search is disabled (engine_backend=none). No external information retrieved."
                }

            # -----------------------------------------------------------------
            # Common context for both KB and web search paths
            # -----------------------------------------------------------------
            depend_write_task = node.get_direct_depend_write_task()
            to_run_root_question = memory.root_node.task_info["goal"]
            if node.config["language"] == "zh":
                to_run_target_write_tasks = "\n".join(
                    "COMPOSITION任务{}，字数：{}".format(idx, node.task_info["length"])
                    for idx, node in enumerate(depend_write_task, start=1)
                ) if (depend_write_task is not None and len(depend_write_task) > 0) else "Not Provided"
                outer_write_task = node.get_outer_write_task()
                to_run_outer_write_task = "COMPOSITION任务{}，字数：{}".format(
                    outer_write_task.task_info["goal"], outer_write_task.task_info["length"])
            else:
                to_run_target_write_tasks = "\n".join(
                    "Write Task{}, word count requirements: {}".format(
                        idx, node.task_info["length"])
                    for idx, node in enumerate(depend_write_task, start=1)
                ) if (depend_write_task is not None and len(depend_write_task) > 0) else "Not Provided"
                outer_write_task = node.get_outer_write_task()
                to_run_outer_write_task = "Write Task {}, word count requirements: {}".format(
                    outer_write_task.task_info["goal"], outer_write_task.task_info["length"])

            # -----------------------------------------------------------------
            # KB-First Path with SerpAPI Fallback
            # When local KB is enabled, ALWAYS try KB first. If KB quality is
            # insufficient and a SerpAPI key is configured, automatically fall
            # back to web search to supplement or replace KB results.
            # Results always include URL references for traceability.
            # -----------------------------------------------------------------
            if use_kb and kb_name:
                logger.info("KB-First: retrieving from KB for '{}'".format(
                    node.task_info.get("goal", "")[:80]))
                return self._kb_first_with_web_fallback(
                    node, memory, kb_name, inner_kwargs,
                    to_run_outer_write_task,
                    to_run_target_write_tasks,
                    to_run_root_question)

            # -----------------------------------------------------------------
            # Pure Web Search Path (no KB configured)
            # Uses SearchAgent with configured searcher_type (SerpAPI, etc.)
            # -----------------------------------------------------------------
            has_web_search = backend_engine != "none"
            if not has_web_search:
                return {
                    "ori": [],
                    "result": "No search or knowledge base actions available. No information retrieved."
                }

            # Create SearchAgent with web search
            actions = [BingBrowser(
                searcher_type=inner_kwargs["searcher_type"],
                language=node.config["language"],
                search_max_thread=inner_kwargs["search_max_thread"],
                selector_max_workers=inner_kwargs["selector_max_workers"],
                summarizier_max_workers=inner_kwargs["summarizier_max_workers"],
                selector_model=inner_kwargs["selector_model"],
                summarizer_model=inner_kwargs["summarizer_model"],
                webpage_helper_max_threads=inner_kwargs["webpage_helper_max_threads"],
                backend_engine=inner_kwargs["backend_engine"],
                cc=inner_kwargs["cc"])]

            react_agent = SearchAgent(
                prompt_version=inner_kwargs["prompt_version"],
                action_executor=ActionExecutor(actions=actions),
                model=inner_kwargs["llm_args"]["model"],
                max_turn=inner_kwargs["max_turn"],
                action_memory=True,
                remove_history=True,
                parse_arg_dict=inner_kwargs["react_parse_arg_dict"]
            )

            react_agent_result = react_agent.chat(
                message=node.task_info["goal"],
                global_start_index=memory.global_start_index,
                to_run_target_write_tasks=to_run_target_write_tasks,
                to_run_root_question=to_run_root_question,
                to_run_outer_write_task=to_run_outer_write_task,
                today_date=node.config.get('today_date', 'Mar 26, 2025'),
                temperature=inner_kwargs.get("temperature", None))

            # Pure web search: format results directly (no KB merge)
            llm_result = self._format_search_agent_result(
                react_agent_result, memory, inner_kwargs)

            # Optional: LLM merge
            if inner_kwargs.get("llm_merge", False):
                execute_result = llm_result.get("result", "")
                merge_result = self.search_merge(
                    node, memory, execute_result, to_run_outer_write_task)
                llm_result = {
                    "ori": llm_result.get("ori", []),
                    "agent_result": execute_result,
                    "merge_result": merge_result,
                    "result": merge_result["result"]
                }

            return llm_result
        else:
            succ = False 
            retry_cnt = 0
            while not succ and retry_cnt < 50:
                llm_result = get_llm_output(
                    node, self, memory, "execute", retry_cnt > 0, *args, **kwargs
                )
                # 判定是否失败，如果result不为空则为成功
                succ = (llm_result["result"].strip() != "")
                if not succ:
                    logger.error("Execute for {} is failed, Get Response: {}, retry_cnt={}".format(node, 
                                                                                                   llm_result["original"],
                                                                                                   retry_cnt))
                    retry_cnt += 1
                
            # for write
            if node.task_type_tag == "COMPOSITION":
                memory.article += "\n\n" + llm_result["result"]
        
        return llm_result

    @overrides
    def parse_result(self, agent_output, *args, **kwargs) -> Dict:
        return agent_output

    # -----------------------------------------------------------------
    # Hybrid search helpers (with rerank)
    # -----------------------------------------------------------------
    def _is_kb_sufficient(self, kb_result: dict) -> tuple:
        """Evaluate KB quality using rerank scores AND Chroma distance scores.

        Two-stage filtering:
        1. Chroma distance check: filter out chunks with poor vector similarity
        2. Reranker coverage score: compute weighted quality metric

        Returns (is_sufficient: bool, coverage_score: float).
        Coverage score is in [0, 1], higher = better coverage.

        Distance thresholds (cosine distance, lower = more similar):
          - distance <= 0.5: highly relevant (close match)
          - distance <= 0.8: moderately relevant
          - distance > 0.8:  poor match, penalized in scoring
        """
        pages = kb_result.get("web_pages", [])
        if len(pages) < 2:
            return False, 0.0

        # Stage 1: Check Chroma distance scores
        # Chroma uses cosine distance by default (range [0, 2], lower = more similar)
        distance_ok_count = 0
        distance_penalty = 0.0
        for p in pages:
            dist = p.get("distance", None)
            if dist is not None:
                if dist <= 0.5:
                    distance_ok_count += 1
                elif dist > 0.8:
                    distance_penalty += 0.1  # penalize poor matches

        # Stage 2: Reranker scores
        scores = [p.get("rerank_score", 0.0) for p in pages]
        if not scores:
            return False, 0.0

        max_score = max(scores)
        avg_score = sum(scores) / len(scores)
        # Count how many are "highly relevant" (score > 0.5)
        high_quality_count = sum(1 for s in scores if s > 0.5)

        # Normalize scores to [0, 1] range (bge-reranker outputs roughly [-10, 10])
        def _norm(s):
            return max(0.0, min(1.0, (s + 5.0) / 10.0))

        norm_max = _norm(max_score)
        norm_avg = _norm(avg_score)
        norm_count = min(high_quality_count / 3.0, 1.0)

        # Weighted coverage score
        coverage = norm_max * 0.5 + norm_count * 0.3 + norm_avg * 0.2

        # Apply distance-based penalty
        distance_ratio = distance_ok_count / max(len(pages), 1)
        if distance_ratio < 0.5:
            coverage *= 0.7  # most chunks have poor vector similarity
        coverage -= distance_penalty
        coverage = max(0.0, min(1.0, coverage))

        logger.info(
            "KB quality: max={:.2f} avg={:.2f} high={}/{} distance_ok={}/{} → coverage={:.2f}"
            .format(max_score, avg_score, high_quality_count, len(pages),
                    distance_ok_count, len(pages), coverage)
        )
        return coverage >= 0.30, coverage

    def _do_kb_search(self, node, memory, kb_name, inner_kwargs):
        """Execute KB retrieval with multi-query variants + rerank.

        Strategy:
        1. Generate multiple query variants at different granularities:
           - Full task goal (long, broad semantic match)
           - Core topic (medium, stripped of verbose prefixes)
           - Short keyword (key entity name, best for bi-encoder recall)
        2. Search KB with each variant, merge and deduplicate by text content
        3. Rerank the merged set (cross-encoder), keep top-5

        This ensures short acronyms like "AgC" are not drowned out by long
        verbose queries in the bi-encoder embedding.
        """
        goal = node.task_info["goal"]

        # Generate query variants at different granularities
        query_variants = self._build_kb_query_variants(goal)
        logger.info("KB search: {} query variants for '{}'".format(
            len(query_variants), goal[:60]))

        # Step 1: coarse retrieval with each variant, merge & deduplicate
        kb_action = LocalKnowledgeBase(
            knowledge_base_name=kb_name,
            topk=8,  # per-variant candidates
        )
        all_pages = []  # list of (page dict, chunk_id)
        seen_chunks = set()

        for qvar in query_variants:
            try:
                result = kb_action.search(
                    query_list=[qvar],
                    user_question=goal,
                    think="Hybrid KB retrieval (variant: {})".format(qvar[:50]),
                    global_start_index=memory.global_start_index,
                )
                for page in result.get("web_pages", []):
                    # Deduplicate by text content hash
                    text = page.get("summary", "")
                    chunk_key = hash(text[:200])  # first 200 chars as key
                    if chunk_key not in seen_chunks:
                        seen_chunks.add(chunk_key)
                        all_pages.append(page)
            except Exception as e:
                logger.warning("KB search variant '{}' failed: {}".format(
                    qvar[:50], e))

        if not all_pages:
            return {"web_pages": [], "result": "", "ori": []}

        logger.info("KB search: {} unique chunks from {} queries".format(
            len(all_pages), len(query_variants)))

        # Step 2: rerank merged set with cross-encoder
        try:
            reranker = get_reranker()
            texts = [p.get("summary", "") for p in all_pages]
            scores = reranker.rerank(goal, texts)
            for p, s in zip(all_pages, scores):
                p["rerank_score"] = s
            # Sort by rerank score descending
            all_pages.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
            # Keep top-5
            top_pages = all_pages[:5]
            logger.info(
                "KB Rerank: {} chunks → top-5 (scores: {})".format(
                    len(all_pages),
                    ", ".join("{:.2f}".format(p.get("rerank_score", 0)) for p in top_pages)
                )
            )
        except Exception as e:
            logger.warning("Rerank failed ({}), falling back to raw top-5".format(e))
            top_pages = all_pages[:5]

        # Re-number global_index sequentially
        for idx, page in enumerate(top_pages, start=memory.global_start_index):
            page["global_index"] = idx

        kb_result = {
            "web_pages": top_pages,
            "result": "",
        }

        # Register results in memory
        for page in top_pages:
            memory.add_search_result(page)
        return kb_result

    def _build_kb_query_variants(self, goal):
        """Generate multiple query variants at different granularities.

        Long queries dilute short keyword signals in bi-encoder embeddings.
        Multiple variants at different lengths improve recall, especially for
        acronym-heavy enterprise content (e.g. "AgC平台" in a verbose query).
        """
        import re
        variants = [goal]  # always include the full goal

        # Variant 1: strip verbose instruction prefixes
        cleaned = goal
        for prefix in ["请搜索", "搜索", "检索", "查找", "收集", "基于搜索结果",
                       "Search for", "Find", "Retrieve", "请", "基于"]:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip("，,：:、 ")
        if cleaned and cleaned != goal:
            variants.append(cleaned)

        # Variant 2: extract core topic before "，包括/覆盖/如/例如/比如"
        short = re.split(r'[，,](?:包括|如|例如|覆盖|比如|诸如|其中|主要|至少)',
                         cleaned)[0].strip()
        short = re.sub(r'(?:的基本信息|的详细信息|的相关信息|的信息|'
                       r'的数据|的资料|的关键数据|等基本信息|'
                       r'等关键数据|等关键信息)$', '', short)
        if short and short not in variants and len(short) >= 3:
            variants.append(short)

        # Variant 3: extract key entity name (first 2-6 characters as standalone)
        # e.g. "AgC平台" from "AgC平台的基本信息"
        entity_match = re.match(r'([\w一-鿿A-Za-z]{2,12}?(?:平台|系统|工具|服务|模型|产品))',
                                short)
        if entity_match:
            entity = entity_match.group(1)
            if entity not in variants and len(entity) >= 2:
                variants.append(entity)

        # Variant 4: extract quoted entities
        quoted = re.findall(r'[「「]([^」」]+)[」」]', goal)
        for q in quoted[:2]:
            if q not in variants and len(q) >= 2:
                variants.append(q)

        # Variant 5: first few significant Chinese words as ultra-short query
        # e.g. "AgC平台" from any text containing it
        ultra_match = re.search(r'([A-Za-z]{2,6}平台|[A-Za-z]{2,6}系统|'
                                r'[A-Za-z]{2,6}工具|[A-Za-z]{2,6}模型)', goal)
        if ultra_match:
            ultra = ultra_match.group(1)
            if ultra not in variants:
                variants.append(ultra)

        # Deduplicate while preserving order
        seen = set()
        result = []
        for v in variants:
            v = v.strip()
            if v and v not in seen:
                seen.add(v)
                result.append(v)

        logger.info("KB query variants: {}".format(
            [v[:70] for v in result]))
        return result

    def _format_kb_result(self, kb_result: dict) -> dict:
        """Format KB-only result with priority note."""
        execute_result_parts = [
            "<kb_priority_note>\n"
            "IMPORTANT: These results are from your organization's internal "
            "knowledge base. Prioritize this content as the primary source.\n"
            "</kb_priority_note>"
        ]
        for page in kb_result.get("web_pages", []):
            execute_result_parts.append(FORMAT_STRING_TEMPLATE.format(
                index=page["global_index"],
                source_type="Local KB",
                title=page["title"],
                url=page["url"],
                publish_time=page["publish_time"],
                content=page["summary"]
            ))
        execute_result = "\n\n".join(execute_result_parts)
        return {
            "ori": [{"turn": 0, "tool_result": kb_result}],
            "result": execute_result
        }

    def _kb_first_with_web_fallback(
        self, node, memory, kb_name, inner_kwargs,
        to_run_outer_write_task, to_run_target_write_tasks, to_run_root_question
    ):
        """KB-first retrieval with automatic SerpAPI web search fallback.

        Strategy:
        1. KB retrieval with rerank (coarse top-10 → reranker → fine top-5)
        2. Quality check via _is_kb_sufficient
        3. Decision:
           - coverage >= 0.55 AND no SerpAPI: KB only
           - coverage >= 0.55 AND SerpAPI available: KB + Web (richer context)
           - coverage < 0.55 AND SerpAPI available: KB + Web
           - coverage < 0.55 AND no SerpAPI: KB only (never discard)
        4. KB results are NEVER fully discarded — they always merge with web results.
           The writer LLM makes the final relevance decision.
        """
        # Step 1: KB retrieval
        logger.info("KB-First: Step 1 – KB retrieval for '{}'".format(
            node.task_info.get("goal", "")[:80]))
        kb_result = self._do_kb_search(node, memory, kb_name, inner_kwargs)

        # Step 2: Quality check with rerank scores
        has_kb = len(kb_result.get("web_pages", [])) > 0
        _, coverage = self._is_kb_sufficient(kb_result)
        logger.info("KB-First: Step 2 – coverage={:.2f}, has_kb={}".format(
            coverage, has_kb))

        # Step 3: Check SerpAPI availability
        serpapi_key = os.environ.get("SERPAPI", "")
        has_serpapi = bool(serpapi_key and serpapi_key not in (
            "your_actual_serpapi_key_here", "", "xxx"))

        # If no KB results at all, web fallback or empty
        if not has_kb:
            if has_serpapi:
                logger.info("KB-First: KB returned 0 results, falling back to web search")
                web_result = self._do_web_search_fallback(
                    node, memory, inner_kwargs,
                    to_run_target_write_tasks, to_run_root_question,
                    to_run_outer_write_task)
                if web_result:
                    return self._format_search_agent_result(web_result, memory, inner_kwargs)
            return self._format_kb_result(kb_result)

        # Always supplement with web search when SerpAPI is available
        if has_serpapi:
            logger.info(
                "KB-First: Step 3 – KB coverage={:.2f}, supplementing with SerpAPI web search".format(coverage))
            web_result = self._do_web_search_fallback(
                node, memory, inner_kwargs,
                to_run_target_write_tasks, to_run_root_question,
                to_run_outer_write_task)

            if web_result and web_result.get("result"):
                # Check if web result has any pages
                has_web_pages = any(
                    t.get("web_pages") for t in web_result.get("result", []))
                if has_web_pages:
                    logger.info(
                        "KB-First: Step 4 – merging KB ({} pages, coverage={:.2f}) + Web".format(
                            len(kb_result.get("web_pages", [])), coverage))
                    return self._merge_kb_and_web(kb_result, web_result, memory, inner_kwargs)

            logger.warning("KB-First: Web fallback returned no results, using KB only")

        # KB only (no SerpAPI or web failed)
        logger.info("KB-First: using KB only ({} pages, coverage={:.2f})".format(
            len(kb_result.get("web_pages", [])), coverage))
        return self._format_kb_result(kb_result)

    def _do_web_search_fallback(
        self, node, memory, inner_kwargs,
        to_run_target_write_tasks, to_run_root_question, to_run_outer_write_task
    ):
        """Execute a direct SerpAPI web search as fallback when KB is insufficient.

        Uses SerpApiSearch directly (search + fetch_content) WITHOUT the LLM-based
        selector/summarizer pipeline. This avoids a hard dependency on the OPENAI
        API key, which full_pipeline_search requires for its gpt-4o-mini scorer.

        Returns a dict mimicking SearchAgent output format:
            {"result": [{"web_pages": [...], "observation": "..."}], "ori": [...]}
        """
        try:
            language = node.config.get("language", "en")
            search_purpose = node.task_info.get("goal", "")

            # Build queries
            queries = self._build_fallback_queries(search_purpose, language)

            # Check SerpAPI key
            serpapi_key = os.environ.get("SERPAPI", "")
            if not serpapi_key:
                logger.warning("Web Fallback: No SERPAPI key configured")
                return None

            # Create SerpApiSearch directly (bypasses BingBrowser to avoid
            # the LLM selector/summarizer dependency)
            searcher = SerpApiSearch(
                serp_api_key=serpapi_key,
                topk=inner_kwargs.get("topk", 20),
                backend_engine="google",
                cc=inner_kwargs.get("cc", "US"),
                language=language,
                webpage_helper_max_threads=inner_kwargs.get(
                    "webpage_helper_max_threads", 10),
            )

            # Step 1: Search all queries (parallel via ThreadPoolExecutor)
            from concurrent.futures import ThreadPoolExecutor, as_completed
            all_results = {}  # url → page dict (global dedup)
            seen_urls = set()

            search_max_thread = inner_kwargs.get("search_max_thread", 4)
            with ThreadPoolExecutor(max_workers=search_max_thread) as executor:
                future_to_query = {
                    executor.submit(searcher.search, q): q
                    for q in queries
                }
                for future in as_completed(future_to_query):
                    query = future_to_query[future]
                    try:
                        result_dict = future.result()
                    except Exception as exc:
                        logger.warning(
                            "Web Fallback: search failed for '{}': {}".format(
                                query[:60], exc))
                        continue
                    for pos, page in result_dict.items():
                        url = page.get("url", "")
                        if url and url not in seen_urls and not url.endswith(".pdf"):
                            seen_urls.add(url)
                            page["search_query"] = query
                            all_results[url] = page

            if not all_results:
                logger.warning("Web Fallback: SerpAPI returned 0 results across {} queries".format(
                    len(queries)))
                return None

            logger.info("Web Fallback: Step 1 – {} unique URLs from SerpAPI".format(
                len(all_results)))

            # Step 2: Fetch web page content (deduplicated, sorted by position)
            pk_quota = inner_kwargs.get("pk_quota", 20)
            pages_to_fetch = sorted(
                all_results.values(), key=lambda x: x.get("position", 100)
            )[:pk_quota]

            fetched_pages = searcher.fetch_content(pages_to_fetch)
            logger.info("Web Fallback: Step 2 – fetched content for {}/{} URLs".format(
                len(fetched_pages), len(pages_to_fetch)))

            if not fetched_pages:
                logger.warning("Web Fallback: all content fetches failed")
                return None

            # Step 3: Format results with explicit URL references
            # Each page already has: url, title, content, snippet, publish_time, position
            global_start = memory.global_start_index
            web_pages = []
            formatted_parts = []

            for idx, page in enumerate(fetched_pages, start=global_start):
                # Build a clean summary from snippet + content
                snippet = page.get("snippet", "")
                content = page.get("content", "")
                # Truncate very long content for readability
                max_content_len = 3000
                if len(content) > max_content_len:
                    content = content[:max_content_len] + "\n... [truncated]"

                combined_summary = content if content else snippet

                page_entry = {
                    "global_index": idx,
                    "title": page.get("title", "Untitled"),
                    "url": page.get("url", ""),
                    "publish_time": page.get("publish_time", "Not Provided"),
                    "summary": combined_summary,
                    "search_query": page.get("search_query", ""),
                    "pk_index": idx - global_start + 1,
                }
                web_pages.append(page_entry)

                formatted_parts.append(FORMAT_STRING_TEMPLATE.format(
                    index=idx,
                    source_type="Web Search (SerpAPI)",
                    title=page_entry["title"],
                    url=page_entry["url"],
                    publish_time=page_entry["publish_time"],
                    content=combined_summary,
                ))

            # Step 4: web_pages are stored in ori for get_report_with_ref to find

            observation = (
                "Web search fallback: Retrieved {} web pages from SerpAPI/Google "
                "to supplement insufficient local knowledge base results.".format(
                    len(web_pages))
            )

            logger.info("Web Fallback: complete – {} pages formatted".format(len(web_pages)))

            return {
                "result": [{
                    "web_pages": web_pages,
                    "observation": observation,
                }],
                "ori": [{"turn": 0, "tool_result": {
                    "web_pages": web_pages,
                    "result": "\n\n".join(formatted_parts),
                    "source": "SerpAPI direct fallback",
                }}],
            }

        except Exception as e:
            logger.error("Web Fallback: SerpAPI search failed: {}".format(e))
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _build_fallback_queries(self, search_purpose, language):
        """Build diverse search queries for the web fallback path.

        Generates multiple query variations to maximize the chance of
        finding relevant web content, especially for Chinese-language tasks.
        """
        queries = [search_purpose]

        # For Chinese tasks, add English translation-style queries for broader coverage
        if language == "zh":
            # Add a slightly rephrased Chinese query
            if len(search_purpose) > 20:
                # Try to extract core topic (first sentence or main subject)
                core = search_purpose.split("。")[0].split("；")[0][:100]
                if core != search_purpose:
                    queries.append(core)

        # Add a general knowledge query without specific constraints
        # Strip length requirements and task-specific prefixes
        cleaned = search_purpose
        for prefix in ["请搜索", "搜索", "检索", "查找", "Search for", "Find", "Retrieve"]:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        # Remove word count requirements
        import re
        cleaned = re.sub(r'字数[要求约至少]?\s*\d+[\s\w]*', '', cleaned)
        cleaned = re.sub(r'\d+字[左右]?', '', cleaned)
        cleaned = cleaned.strip()
        if cleaned and cleaned != search_purpose:
            queries.append(cleaned)

        logger.info("Web Fallback: generated {} diverse queries: {}".format(
            len(queries), [q[:80] for q in queries]))
        return queries

    def _format_search_agent_result(self, react_agent_result, memory, inner_kwargs):
        """Format raw SearchAgent output into the standard result dict."""
        execute_result = []
        for turn_result in react_agent_result["result"]:
            for page in turn_result["web_pages"]:
                memory.add_search_result(page)
                if not inner_kwargs.get("only_use_react_summary", False):
                    execute_result.append(FORMAT_STRING_TEMPLATE.format(
                        index=page["global_index"],
                        source_type="Web Search",
                        title=page["title"],
                        url=page["url"],
                        publish_time=page["publish_time"],
                        content=page["summary"]
                    ))
            execute_result.append("<web_pages_short_summary>\n{}\n</web_pages_short_summary>".format(
                turn_result["observation"]
            ))
        execute_result = "\n\n".join(execute_result)
        return {
            "ori": react_agent_result["ori"],
            "result": execute_result
        }

    def _merge_kb_and_web(self, kb_result, react_agent_result, memory, inner_kwargs):
        """Merge KB results (as turn 0) with web search turns.

        KB content is placed FIRST with an explicit priority note telling
        the writer LLM to use it as the primary source.
        """
        kb_pages = kb_result.get("web_pages", [])
        has_kb = len(kb_pages) > 0

        # KB priority instruction
        kb_priority_note = (
            "<kb_priority_note>\n"
            "IMPORTANT: The following Local KB results are from your organization's "
            "internal knowledge base. These documents are authoritative sources "
            "about internal projects/platforms. You MUST prioritize and base your "
            "answer primarily on these KB results. Use Web Search results only to "
            "supplement with external context or comparisons.\n"
            "</kb_priority_note>"
        )

        kb_turn = {
            "web_pages": kb_pages,
            "observation": "Local knowledge base: retrieved {} relevant passages. "
                           "PRIORITIZE these internal documents.".format(len(kb_pages))
        }
        merged_turns = [kb_turn] + react_agent_result["result"]

        execute_result = [kb_priority_note] if has_kb else []
        for turn_idx, turn_result in enumerate(merged_turns):
            source_type = "Local KB" if turn_idx == 0 else "Web Search"
            for page in turn_result["web_pages"]:
                memory.add_search_result(page)
                if not inner_kwargs.get("only_use_react_summary", False):
                    execute_result.append(FORMAT_STRING_TEMPLATE.format(
                        index=page["global_index"],
                        source_type=source_type,
                        title=page["title"],
                        url=page["url"],
                        publish_time=page["publish_time"],
                        content=page["summary"]
                    ))
            if turn_result.get("observation"):
                execute_result.append("<web_pages_short_summary>\n{}\n</web_pages_short_summary>".format(
                    turn_result["observation"]
                ))
        execute_result = "\n\n".join(execute_result)

        # Build merged ori (web_pages + URLs preserved in nodes.json for get_report_with_ref)
        merged_ori = [{"turn": 0, "tool_result": kb_result}]
        merged_ori.extend(react_agent_result.get("ori", []))

        return {
            "ori": merged_ori,
            "result": execute_result
        }

    def search_merge(self, node, memory, search_results, to_run_outer_write_task, *args, **kwargs):
        inner_kwargs = node.config["RETRIEVAL"]["search_merge"]
        prompt_version = inner_kwargs["prompt_version"]

        system_message = prompt_register.module_dict[prompt_version]().construct_system_message()
        
        to_run_search_task = node.task_info["goal"]
        to_run_search_results = search_results

        to_run_root_question = memory.root_node.task_info["goal"]
            
        # to_run_target_write_tasks
        depend_write_task = node.get_direct_depend_write_task()
        if node.config["language"] == "zh":
            to_run_target_write_tasks = "\n".join(
                "写作任务{}，字数：{}".format(idx, node.task_info["length"]) for idx, node in enumerate(depend_write_task, start=1)
            ) if (depend_write_task is not None and len(depend_write_task) > 0) else "Not Provided"
        else:
            to_run_target_write_tasks = "\n".join(
                "Write Task{}, word count requirements：{}".format(idx, node.task_info["length"]) for idx, node in enumerate(depend_write_task, start=1)
            ) if (depend_write_task is not None and len(depend_write_task) > 0) else "Not Provided"
        # Prepare prompt arguments
        prompt_args = {
            'to_run_search_task': to_run_search_task,
            'to_run_search_results': to_run_search_results,
            'to_run_target_write_tasks': to_run_target_write_tasks,
            'to_run_outer_write_task': to_run_outer_write_task,
            'to_run_root_question': to_run_root_question,
            'today_date': node.config.get('today_date', 'Mar 26, 2025')  # Add today_date from config
        }
        
        prompt = prompt_register.module_dict[prompt_version]().construct_prompt(**prompt_args)
        
        succ = False 
        retry_cnt = 0
        while not succ and retry_cnt < 50:
            llm_result = self.call_llm(
                system_message = system_message,
                prompt = prompt,
                parse_arg_dict = inner_kwargs["parse_arg_dict"],
                overwrite_cache = True if retry_cnt > 0 else False,
                **inner_kwargs.get("llm_args", {})
            )
            # 判定是否失败，如果result不为空则为成功
            succ = (llm_result["result"].strip() != "")
            if not succ:
                logger.error("Search Merge for {} is failed, Get Response: {}, retry_cnt={}".format(node, 
                                                                                                    llm_result["original"],
                                                                                                    retry_cnt))
                retry_cnt += 1
        if not succ:
            logger.error("Search Merge for {} after retry fail, return the original as result".format(node))
            llm_result = {"result": search_results}
            
        return llm_result
        

@agent_register.register_module()
class FinalAggregateAgent(Agent):
    @overrides
    def forward(self, node, memory, *args, **kwargs) -> str:
        return_result = {}
        task_type = node.task_type_tag
        if task_type == "RETRIEVAL":
            # Aggregate All Child Result
            results = []
            for child in node.topological_task_queue:
                results.append("【{}】:\n {}".format(child.task_info["goal"],
                                                child.get_node_final_result()["result"]))
            results = "\n\n".join(results)
            return_result["result"] = results
    
        elif task_type == "REASONING":
            inner_kwargs = node.config[task_type]["final_aggregate"]
            results = []
            for child in node.topological_task_queue:
                results.append("【{}】:\n {}".format(child.task_info["goal"],
                                                child.get_node_final_result()["result"]))
            results = "\n\n".join(results)
            if inner_kwargs.get("mode", "concat") == "concat":
                return_result["result"] = results
            else:
                assert inner_kwargs.get("mode", "concat") == "llm"
                fa_llm_result = get_llm_output(
                    node, self, memory, "final_aggregate", to_run_final_aggregate = results,
                    *args, **kwargs
                )
                return_result = fa_llm_result
                    
        elif task_type == "COMPOSITION":
            return_result["result"] = memory.article
        return return_result

    @overrides
    def parse_result(self, agent_output, *args, **kwargs) -> Dict:
        return agent_output