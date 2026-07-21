#coding:utf8

import sys
import os
from pathlib import Path

from collections import defaultdict, deque
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from recursive.graph import TaskStatus, RegularDummyNode, NodeType
from recursive.utils.display import display_graph, display_plan
from recursive.agent.proxy import AgentProxy
from recursive.memory import Memory, article
import random
from pprint import pprint
import dill as pickle
import json
import argparse
from loguru import logger
import traceback
from recursive.memory import caches
from recursive.cache import Cache
from recursive.evidence.claim_verification import save_claim_verification, verify_report_claims
from recursive.evidence.graph import build_evidence_graph, save_evidence_graph
from recursive.evidence.repair_loop import run_writer_repair_loop, save_repair_report
from recursive.evidence.search_repair import (
    augment_writer_feedback_with_search_repair,
    run_search_repair,
    save_search_repair,
)
from recursive.evidence.writer_feedback import build_writer_feedback, save_writer_feedback
from recursive.utils.get_index import get_report_with_ref
from recursive.utils.markdown_tables import normalize_markdown_tables
from recursive.utils.report_quality import postprocess_report_quality, save_report_quality_audit
from datetime import datetime


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() not in ("0", "false", "no", "off", "disable", "disabled")


def _root_node_json_with_memory_pages(engine):
    data = engine.root_node.to_json()
    try:
        memory_pages = []
        for page in getattr(engine.memory, "all_search_results", []) or []:
            if not (page.get("global_index") and page.get("url") and page.get("title")):
                continue
            memory_pages.append(page)
        if memory_pages:
            data["_memory_search_results"] = memory_pages
    except Exception:
        logger.warning("Failed to attach memory search results to root JSON:\n{}".format(
            traceback.format_exc()))
    return data


def _save_final_evidence_graph(engine, folder, article):
    try:
        graph_data = build_evidence_graph(
            memory=engine.memory,
            article=article,
            root_node_json=_root_node_json_with_memory_pages(engine),
        )
        save_evidence_graph("{}/evidence_graph.json".format(folder), graph_data)
        logger.info(
            "Evidence graph saved: nodes={}, edges={}".format(
                graph_data.get("summary", {}).get("node_count", 0),
                graph_data.get("summary", {}).get("edge_count", 0),
            )
        )
        return graph_data
    except Exception:
        logger.warning("Failed to save evidence graph:\n{}".format(traceback.format_exc()))
        return {}


def _postprocess_final_report(result, folder, add_audit_section=True):
    result, audit = postprocess_report_quality(
        result, add_audit_section=add_audit_section)
    try:
        save_report_quality_audit("{}/report_quality_audit.json".format(folder), audit)
        logger.info(
            "Report quality audit saved: unsupported_quantitative={}, low_citation_sections={}".format(
                audit.get("unsupported_quantitative_count", 0),
                audit.get("low_citation_section_count", 0),
            )
        )
    except Exception:
        logger.warning("Failed to save report quality audit:\n{}".format(traceback.format_exc()))
    return result, audit


def _save_claim_verification(
    engine,
    folder,
    article,
    llm_verifier=False,
    verifier_model=None,
    max_llm_claims=6,
):
    try:
        verification = verify_report_claims(
            article=article,
            memory=engine.memory,
            llm_verifier=llm_verifier,
            verifier_model=verifier_model,
            max_llm_claims=max_llm_claims,
        )
        save_claim_verification("{}/claim_verification.json".format(folder), verification)
        logger.info(
            "Claim verification saved: claims={}, unsupported={}, needs_review={}".format(
                verification.get("summary", {}).get("claim_count", 0),
                verification.get("summary", {}).get("unsupported_count", 0),
                verification.get("summary", {}).get("needs_review_count", 0),
            )
        )
        return verification
    except Exception:
        logger.warning("Failed to save claim verification:\n{}".format(traceback.format_exc()))
        return {}


def _save_writer_feedback(engine, folder, claim_verification, quality_audit, evidence_graph):
    try:
        feedback = build_writer_feedback(
            claim_verification=claim_verification,
            quality_audit=quality_audit,
            evidence_graph=evidence_graph,
            root_node_json=_root_node_json_with_memory_pages(engine),
        )
        save_writer_feedback("{}/writer_feedback.json".format(folder), feedback)
        logger.info(
            "Writer feedback saved: actions={}, repair_needed={}".format(
                feedback.get("summary", {}).get("action_count", 0),
                feedback.get("summary", {}).get("repair_needed", False),
            )
        )
        return feedback
    except Exception:
        logger.warning("Failed to save writer feedback:\n{}".format(traceback.format_exc()))
        return {}


def _run_report_repair_loop(engine, folder, article, writer_feedback, repair_model):
    try:
        repaired_article, repair_report = run_writer_repair_loop(
            article=article,
            writer_feedback=writer_feedback,
            memory=engine.memory,
            model=repair_model,
            max_sections=int(os.environ.get("WRITEHERE_REPAIR_MAX_SECTIONS", "2")),
        )
        save_repair_report("{}/repair_loop.json".format(folder), repair_report)
        logger.info(
            "Repair loop saved: attempted={}, repaired={}".format(
                repair_report.get("attempted_section_count", 0),
                repair_report.get("repaired_section_count", 0),
            )
        )
        return repaired_article, repair_report
    except Exception:
        logger.warning("Failed to run report repair loop:\n{}".format(traceback.format_exc()))
        return article, {
            "version": "1.0",
            "enabled": True,
            "attempted_section_count": 0,
            "repaired_section_count": 0,
            "repaired_sections": [],
            "skipped": [],
            "error": traceback.format_exc(),
        }


def _run_search_repair(
    engine,
    folder,
    writer_feedback,
    root_goal,
    enabled=True,
    execute_kb=True,
):
    try:
        if not enabled:
            report = {
                "version": "1.0",
                "enabled": False,
                "executed": False,
                "execute_kb": False,
                "targets": [],
                "queries": [],
                "kb_results": [],
                "new_evidence_ids": [],
                "skipped": ["Search repair disabled."],
                "error": "",
                "summary": {
                    "target_count": 0,
                    "query_count": 0,
                    "kb_result_count": 0,
                    "new_evidence_count": 0,
                    "executed": False,
                },
            }
        else:
            report = run_search_repair(
                writer_feedback=writer_feedback,
                root_goal=root_goal,
                memory=engine.memory,
                kb_name=os.environ.get(
                    "WRITEHERE_SEARCH_REPAIR_KB_NAME",
                    os.environ.get("WRITEHERE_KB_NAME", ""),
                ),
                execute_kb=execute_kb,
                kb_topk=int(os.environ.get("WRITEHERE_SEARCH_REPAIR_TOPK", "3")),
                max_queries=int(os.environ.get("WRITEHERE_SEARCH_REPAIR_MAX_QUERIES", "6")),
                max_results=int(os.environ.get("WRITEHERE_SEARCH_REPAIR_MAX_RESULTS", "10")),
                verify_mode=os.environ.get("WRITEHERE_EVIDENCE_VERIFY_MODE", "heuristic"),
            )
        save_search_repair("{}/search_repair.json".format(folder), report)
        logger.info(
            "Search repair saved: targets={}, queries={}, new_evidence={}".format(
                report.get("summary", {}).get("target_count", 0),
                report.get("summary", {}).get("query_count", 0),
                report.get("summary", {}).get("new_evidence_count", 0),
            )
        )
        if report.get("new_evidence_ids"):
            writer_feedback = augment_writer_feedback_with_search_repair(
                writer_feedback, report)
            save_writer_feedback("{}/writer_feedback.json".format(folder), writer_feedback)
        return report, writer_feedback
    except Exception:
        logger.warning("Failed to run search repair:\n{}".format(traceback.format_exc()))
        report = {
            "version": "1.0",
            "enabled": enabled,
            "executed": False,
            "execute_kb": execute_kb,
            "targets": [],
            "queries": [],
            "kb_results": [],
            "new_evidence_ids": [],
            "skipped": [],
            "error": traceback.format_exc(),
            "summary": {
                "target_count": 0,
                "query_count": 0,
                "kb_result_count": 0,
                "new_evidence_count": 0,
                "executed": False,
            },
        }
        try:
            save_search_repair("{}/search_repair.json".format(folder), report)
        except Exception:
            pass
        return report, writer_feedback


class GraphRunEngine:
    """
    """
    def __init__(self, root_node, memory_format, config):
        self.root_node = root_node
        self.memory = Memory(root_node, format=memory_format, config=config)
        self.root_node = root_node
        self.memory = Memory(root_node, format=memory_format, config=config)

    def find_need_next_step_nodes(self, single=False):
        nodes = []
        queue = deque([self.root_node])
        # Root node, starts in READY state
        while len(queue) > 0:
            # logger.info("in find_need_next_step_nodes, queue: {}".format(queue))
            node = queue.popleft()
            # logger.info("in find_need_next_step_nodes, select node: {}".format(node))
            if node.is_activate:
                nodes.append(node)
            if node.is_suspend: # If the node is in a suspended state internally, traverse the topological_task_queue of internal nodes
                queue.extend(node.topological_task_queue)
            if single and len(nodes) > 0:
                return nodes[0]
        if not single:
            return nodes
        else:
            return None

    def save(self, folder):
        # save root_node
        # save memory
        # save article while running
        root_node_file = "{}/nodes.pkl".format(folder)
        root_node_json_file = "{}/nodes.json".format(folder)
        article_file = "{}/article.txt".format(folder)
        evidence_file = "{}/evidence_ledger.json".format(folder)
        with open(root_node_file, "wb") as f:
            pickle.dump(self.root_node, f)

        with open(root_node_json_file, "w") as f:
            json.dump(self.root_node.to_json(), f, indent=4, ensure_ascii=False)

        self.memory.save(folder)
        if hasattr(self.memory, "evidence_ledger"):
            with open(evidence_file, "w", encoding="utf-8") as f:
                json.dump(
                    self.memory.evidence_ledger.to_list(),
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

        with open(article_file, 'w', encoding='utf-8') as file:
            file.write(self.memory.article)

    def load(self, folder):
        root_node_file = "{}/nodes.pkl".format(folder)
        with open(root_node_file, "rb") as f:
            self.root_node = pickle.load(f)

        self.memory = self.memory.load(folder)

    def forward_exam(self, node, verbose):
        # The exam order is bottom-up hierarchically, and top-down based on dependencies.
        # not_ready -> ready: Need to check the execution status of dependent nodes, and whether upper-level nodes have entered the doing state
        # doing -> final_to_finish: Need to check if all lower-level nodes have finished
        # plan_reflection_done -> doing:
        if node.is_suspend:
            for inner_node in node.topological_task_queue:
                self.forward_exam(inner_node, verbose)
            node.do_exam(verbose)

    def forward_one_step_not_parallel(self, full_step=False, select_node_hashkey=None, log_fn=None,
                                      nodes_json_file=None, *action_args, **action_kwargs):
        # Find tasks that need to enter the next step
        if select_node_hashkey is not None:
            need_next_step_node = self.find_need_next_step_nodes(single=False)
            for node in need_next_step_node:
                if node.hashkey == select_node_hashkey:
                    break
            else:
                raise Exception("Error, the select node {} can not be executed".format(select_node_hashkey))
            need_next_step_node = node
        else:
            need_next_step_node = self.find_need_next_step_nodes(single=True)
        if need_next_step_node is None:
            logger.info("All Done")
            # display_graph(self.root_node.inner_graph, fn=log_fn)
            display_plan(self.root_node.inner_graph)

            # Save final nodes.json if path provided
            if nodes_json_file:
                with open(nodes_json_file, "w") as f:
                    json.dump(self.root_node.to_json(), f, indent=4, ensure_ascii=False)

            return "done"
        logger.info("select node: {}".format(need_next_step_node.task_str()))

        # Execute the next step for this node
        # Update Memory
        self.memory.update_infos([need_next_step_node])

        # Update nodes.json after each step if path provided
        if nodes_json_file:
            with open(nodes_json_file, "w") as f:
                json.dump(self.root_node.to_json(), f, indent=4, ensure_ascii=False)

        if not full_step:
            action_name, action_result = need_next_step_node.next_action_step(self.memory,
                                                               *action_args,
                                                               **action_kwargs)
        else:
            action_name = need_next_step_node.next_full_action_step(self.memory)

        verbose = action_name not in ("update", "prior_reflect", \
                               "planning_post_reflect", \
                               "execute_post_reflect")

        # After the action ends, update the entire graph status
        self.forward_exam(self.root_node, verbose)

        if verbose:
            display_plan(self.root_node.inner_graph)

    def _is_parallel_safe_node(self, node):
        return (
            node.status == TaskStatus.READY and
            node.node_type == NodeType.EXECUTE_NODE and
            node.task_type_tag in ("RETRIEVAL", "REASONING")
        )

    def _select_parallel_batch(self, nodes):
        if not nodes:
            return []
        first = nodes[0]
        if not self._is_parallel_safe_node(first):
            return []
        outer = first.node_graph_info.get("outer_node")
        outer_key = outer.hashkey if outer is not None else None
        layer = first.node_graph_info.get("layer")
        return [
            node for node in nodes
            if self._is_parallel_safe_node(node) and
            (node.node_graph_info.get("outer_node").hashkey if node.node_graph_info.get("outer_node") is not None else None) == outer_key and
            node.node_graph_info.get("layer") == layer
        ]

    def forward_one_step_parallel(self, full_step=False, log_fn=None,
                                  nodes_json_file=None, *action_args, **action_kwargs):
        need_next_step_nodes = self.find_need_next_step_nodes(single=False)
        if len(need_next_step_nodes) == 0:
            return self.forward_one_step_not_parallel(
                full_step=full_step,
                log_fn=log_fn,
                nodes_json_file=nodes_json_file,
                *action_args,
                **action_kwargs
            )

        parallel_nodes = self._select_parallel_batch(need_next_step_nodes)
        if len(parallel_nodes) < 2:
            return self.forward_one_step_not_parallel(
                full_step=full_step,
                log_fn=log_fn,
                nodes_json_file=nodes_json_file,
                *action_args,
                **action_kwargs
            )

        max_workers = int(self.root_node.config.get("parallel_max_workers", 4))
        max_workers = max(1, min(max_workers, len(parallel_nodes)))
        logger.info("Parallel step: executing {} nodes with {} workers".format(
            len(parallel_nodes), max_workers))

        self.memory.update_infos(parallel_nodes)
        if nodes_json_file:
            with open(nodes_json_file, "w") as f:
                json.dump(self.root_node.to_json(), f, indent=4, ensure_ascii=False)

        def run_node(node):
            start_time = time.time()
            if not full_step:
                action_name, action_result = node.next_action_step(
                    self.memory, *action_args, **action_kwargs)
            else:
                action_name = node.next_full_action_step(self.memory)
                action_result = None
            return node, action_name, action_result, time.time() - start_time

        errors = []
        action_names = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_node = {
                executor.submit(run_node, node): node for node in parallel_nodes
            }
            for future in as_completed(future_to_node):
                node = future_to_node[future]
                try:
                    _, action_name, _, duration = future.result()
                    action_names.append(action_name)
                    logger.info("Parallel node finished in {:.2f}s: {}".format(
                        duration, node.task_str()))
                except Exception as e:
                    logger.error("Parallel node failed: {}\n{}".format(
                        node.task_str(), traceback.format_exc()))
                    errors.append(e)

        if errors:
            raise errors[0]

        verbose = any(action_name not in (
            "update", "prior_reflect", "planning_post_reflect", "execute_post_reflect"
        ) for action_name in action_names)

        self.forward_exam(self.root_node, verbose)
        if verbose:
            display_plan(self.root_node.inner_graph)

    def forward_one_step_untill_done(self, full_step=False,
                                           parallel=False,
                                           save_folder=None,
                                           nl=False,
                                           nodes_json_file=None,
                                           *action_args, **action_kwargs):
        self.root_node.status = TaskStatus.READY
        use_parallel = parallel or self.root_node.config.get("parallel_execute", False)
        for step in range(10000):
            logger.info("Step {}".format(step))
            if use_parallel:
                ret = self.forward_one_step_parallel(
                    full_step=False,
                    log_fn="logs/temp/{}".format(step),
                    nodes_json_file=nodes_json_file,
                    *action_args,
                    **action_kwargs
                )
            else:
                ret = self.forward_one_step_not_parallel(
                    full_step=False,
                    log_fn="logs/temp/{}".format(step),
                    nodes_json_file=nodes_json_file,
                    *action_args,
                    **action_kwargs
                )
            self.save(save_folder)
            if ret == "done":
                break

            if step > 3000:
                logger.error("Step > 3000, break")
                break

        if step <= 3000:
            final_answer = self.root_node.get_node_final_result()["result"]
        else:
            final_answer = "Out of Step"
        logger.info("Final Result: \n{}".format(final_answer))
        return final_answer



def read_jsonl(filename: str, jsonl_format=True) -> List[Dict]:
    with open(filename, 'r') as f:
        if filename.endswith(".jsonl") or jsonl_format:
            data = []
            for line in f.readlines():
                try:
                    data.append(json.loads(line))
                except SyntaxError as e:
                    print("load jsonl line error, msg: {}".format(str(e)))
                    continue
        else:
            data = json.load(f)

    return data


def story_writing(input_filename,
                  output_filename,
                  start,
                  end,
                  done_flag_file,
                  global_use_model,
                  nodes_json_file=None):

    config = {
        "language": "en",
        "action_mapping": {
            "plan": ["UpdateAtomPlanningAgent", {}],
            "update": ["DummyRandomUpdateAgent", {}],
            "execute": ["SimpleExcutor", {}],
            "final_aggregate": ["FinalAggregateAgent", {}],
            "prior_reflect": ["DummyRandomPriorReflectionAgent", {}],
            "planning_post_reflect": ["DummyRandomPlanningPostReflectionAgent", {}],
            "execute_post_reflect": ["DummyRandomExecutorPostReflectionAgent", {}],
        },
        "task_type2tag": {
            "COMPOSITION": "write",
            "REASONING": "think",
            "RETRIEVAL": "search",
        },
        "require_keys": {
            "COMPOSITION": ["id", "dependency", "goal", "task_type", "length"],
            "RETRIEVAL": ["id", "dependency", "goal", "task_type"],
            "REASONING": ["id", "dependency", "goal", "task_type"],
        },
        "COMPOSITION": {
            "execute": {
                "prompt_version": "StoryWrtingNLWriterEN",
                "llm_args": {
                    "model": global_use_model,
                    "temperature": 0.3
                },
                "parse_arg_dict": {
                    "result": ["article"],
                },
            },
            "atom": {
                "update_diff": True,
                "without_update_prompt_version": "StoryWritingNLWriteAtomEN",
                "with_update_prompt_version": "StoryWritingNLWriteAtomWithUpdateEN",
                "llm_args": {
                    "model": global_use_model,
                    "temperature": 0.1
                },
                "parse_arg_dict": {
                    "atom_think": ["think"],
                    "atom_result": ["atomic_task_determination"],
                    "update_result": ["goal_updating"]
                },
                "atom_result_flag": "atomic"
            },
            "planning": {
                "prompt_version": "StoryWritingNLPlanningEN",
                "llm_args": {
                    "model": global_use_model,
                    "temperature": 0.1
                },
                "parse_arg_dict": {
                    "plan_think": ["think"],
                    "plan_result": ["result"],
                },
            },
            "update": {},
            "final_aggregate": {},
        },
        "RETRIEVAL": {
            "all_atom": True
        },
        "REASONING": {
            "execute": {
                "prompt_version": "StoryWrtingNLReasonerEN",
                "llm_args": {
                    "model": global_use_model,
                    "temperature": 0.3
                },
                "parse_arg_dict": {
                    "result": ["result"],
                },
            },
            "atom": {
                "use_candidate_plan": True
            },
            "planning": {},
            "update": {},
            "final_aggregate": {
                "prompt_version": "StoryWritingReasonerFinalAggregate",
                "mode": "llm",
                "parse_arg_dict": {
                    "result": ["result"],
                },
            },
        },
    }
    config["tag2task_type"] = {v: k for k,v in config["task_type2tag"].items()}


    data = read_jsonl(input_filename)


    items = data[start:end]

    # Auto-detect language from user prompt
    if items:
        prompt = items[0].get("ori", {}).get("inputs", "") if isinstance(items[0].get("ori"), dict) else items[0].get("prompt", "")
        if not prompt:
            prompt = items[0].get("prompt", "")
        chinese_chars = sum(1 for c in prompt if '一' <= c <= '鿿')
        if chinese_chars > 5:
            config["language"] = "zh"
        else:
            config["language"] = "en"

    import pathlib
    root_folder = "{}/{}".format(str(pathlib.Path(output_filename).parent.parent),
                                 "records")
    caches["search"] = Cache("{}/../cache/{}-{}-search".format(root_folder, start, end))
    caches["llm"] = Cache("{}/../cache/{}-{}-llm".format(root_folder, start, end))

    import os
    if os.path.exists(output_filename):
        done_ques = [item["ori"]["inputs"]  for item in read_jsonl(output_filename)]
        filtered_items = [item for item in items if item["ori"]["inputs"] not in done_ques]
        print("Has Done {} item, left {} items to run".format(len(done_ques), len(filtered_items)))
        items = filtered_items

    output_f = open(output_filename, "w", encoding="utf8")
    print("Need Run {} items".format(len(items)), flush=True)


    for item in items:
        question = item["ori"]["inputs"]
        root_node = RegularDummyNode(
            config = config,
            nid = "",
            node_graph_info = {
                "outer_node": None,
                "root_node": None,
                "parent_nodes": [],
                "layer": 0
            },
            task_info = {
                "goal": question,
                "task_type": "write",
                "length": "determine based on the task requirements:",
                "dependency": []
            },
            node_type = NodeType.PLAN_NODE
        )
        root_node.node_graph_info["root_node"] = root_node
        engine = GraphRunEngine(root_node, "xml", config)
        import os
        # qstr = question if len(question) < 40 else question[:40]
        qstr = item["id"]
        folder = "{}/{}".format(root_folder, qstr)
        os.makedirs(folder, exist_ok=True)
        custom_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
        log_id = logger.add("{}/engine.log".format(folder), format=custom_format)
        try:
            # result = engine.forward_one_step_untill_done(save_folder=folder, to_run_check_str = check_str)
            result = engine.forward_one_step_untill_done(save_folder=folder, nl=True, nodes_json_file=nodes_json_file)
        except Exception as e:
            logger.error("Encounter exception: {}\nWhen Process {}".format(traceback.format_exc(), question))
            continue

        item["result"] = result
        output_f.write(json.dumps(item, ensure_ascii=False) + "\n")
        output_f.flush()

        logger.remove(log_id)

    # output_f.close()
    if done_flag_file is not None:
        with open(done_flag_file, "w") as f:
            f.write("done")


def report_writing(input_filename,
                   output_filename,
                   start,
                   end,
                   done_flag_file,
                   global_use_model,
                   engine_backend,
                   nodes_json_file=None,
                   today_date=None):
    # Use current date if not provided
    if today_date is None:
        today_date = datetime.now().strftime("%b %d, %Y")
    fast_model = os.environ.get("WRITEHERE_FAST_MODEL", global_use_model)
    writer_model = os.environ.get("WRITEHERE_WRITER_MODEL", global_use_model)
    reasoner_model = os.environ.get("WRITEHERE_REASONER_MODEL", global_use_model)
    search_model = os.environ.get("WRITEHERE_SEARCH_MODEL", fast_model)
    merge_model = os.environ.get("WRITEHERE_MERGE_MODEL", fast_model)
    config = {
        "language": "en",
        "parallel_execute": True,
        "parallel_max_workers": int(os.environ.get("WRITEHERE_PARALLEL_MAX_WORKERS", "4")),
        # Agent is Defined in recursive.agent.agents.regular
        # update, prior_reflect, planning_post_reflect and execute_post_reflect is skipped, by using Dummy Agent
        # prompt is Defined in recursive.agent.prompts
        "today_date": today_date,  # Add the today_date parameter to config
        "action_mapping": {
            "plan": ["UpdateAtomPlanningAgent", {}],
            "update": ["DummyRandomUpdateAgent", {}],
            "execute": ["SimpleExcutor", {}],
            "final_aggregate": ["FinalAggregateAgent", {}],
            "prior_reflect": ["DummyRandomPriorReflectionAgent", {}],
            "planning_post_reflect": ["DummyRandomPlanningPostReflectionAgent", {}],
            "execute_post_reflect": ["DummyRandomExecutorPostReflectionAgent", {}],
        },
        "task_type2tag": {
            "COMPOSITION": "write",
            "REASONING": "think",
            "RETRIEVAL": "search",
        },
        "require_keys": {
            "COMPOSITION": ["id", "dependency", "goal", "task_type", "length"],
            "RETRIEVAL": ["id", "dependency", "goal", "task_type"],
            "REASONING": ["id", "dependency", "goal", "task_type"],
        },
        "offer_global_writing_plan": True,
        "COMPOSITION": {
            "execute": {
                "prompt_version": "ReportWriter",
                "llm_args": {
                    "model": writer_model,
                    "temperature": 0.3
                },
                "parse_arg_dict": {
                    "result": ["article"],
                },
            },
            "atom": {
                "update_diff": True,  # Combine Atom and Update, see agent.agents.regular.get_llm_output
                "without_update_prompt_version": "ReportAtom",
                "with_update_prompt_version": "ReportAtomWithUpdate",
                "llm_args": {
                    "model": fast_model,
                    "temperature": 0.1
                },
                "parse_arg_dict": { # parse args from llm output in xml format
                    "atom_think": ["think"],
                    "atom_result": ["atomic_task_determination"],
                    "update_result": ["goal_updating"]
                },
                "atom_result_flag": "atomic",
                "atom_retry_limit": int(os.environ.get("WRITEHERE_RETRY_LIMIT", "2")),
                "force_atom_layer": 2 # >= 2, force to atom and skip atom judgement (was 3; lowered to save ~2-3 LLM calls per run)
            },
            "planning": {
                "prompt_version": "ReportPlanning",
                "llm_args": {
                    "model": fast_model,
                    "temperature": 0.1
                },
                "parse_arg_dict": {
                    "plan_think": ["think"],
                    "plan_result": ["result"],
                },
                "planning_retry_limit": int(os.environ.get("WRITEHERE_RETRY_LIMIT", "2")),
                # Fast report mode keeps the root plan shallow and prevents write nodes
                # from recursively expanding into many more LLM calls.
                "fast_mode": os.environ.get("WRITEHERE_FAST_REPORT", "1").lower() not in ("0", "false", "no", "off"),
                "fast_max_write_length": int(os.environ.get("WRITEHERE_FAST_MAX_WRITE_LENGTH", "1200")),
                "fast_force_write_atom_layer": int(os.environ.get("WRITEHERE_FAST_FORCE_WRITE_ATOM_LAYER", "1")),
                "fast_strip_nested_subtasks": os.environ.get("WRITEHERE_FAST_STRIP_NESTED_SUBTASKS", "1").lower() not in ("0", "false", "no", "off"),
            },
            "update": {},
            "final_aggregate": {},
        },
        "RETRIEVAL": {
            "execute": {
                "react_agent": True, # use Search Agent
                "prompt_version": "SearchAgentENPrompt", # see recursive.agent.prompts.search_agent.main
                "searcher_type": "LocalKnowledgeBase" if str(engine_backend).lower() in ('kb', 'knowledge_base', 'local_kb') else ("SearXNG" if str(engine_backend).lower() == 'searxng' else ("SerpApiSearch" if str(engine_backend).lower() in ('bing', 'duckduckgo', 'google') else "SerpApiSearch")), # see recursive.executor.actions.bing_browser
                "llm_args": {
                    "model": search_model, # set the llm
                },
                "parse_arg_dict": {
                    "result": ["result"],
                },
                "react_parse_arg_dict": { # for search agent, parse result from xml format llm response
                    "observation": ["observation"],
                    "missing_info": ["missing_info"],
                    "think": ["planning_and_think"],
                    "action_think": ["current_turn_query_think"],
                    "search_querys": ["current_turn_search_querys"],
                },
                "temperature": 0.2, # search agent
                "max_turn": 1, # single-turn query generation plus one search execution
                "search_structured_output": True,
                "llm_merge": "auto", # merge only when the retrieved context is large/complex
                "only_use_react_summary": False,
                "kb_web_fallback_coverage_threshold": 0.55,
                "kb_web_force_supplement": False,
                "merge_context_char_threshold": 12000,
                "merge_page_threshold": 8,
                "execute_retry_limit": int(os.environ.get("WRITEHERE_RETRY_LIMIT", "2")),
                "merge_retry_limit": int(os.environ.get("WRITEHERE_RETRY_LIMIT", "2")),
                "search_parse_retry_limit": int(os.environ.get("WRITEHERE_RETRY_LIMIT", "2")),
                "search_mode_dispatch": os.environ.get("WRITEHERE_SEARCH_MODE_DISPATCH", "1").lower() not in ("0", "false", "no", "off"),
                "search_mode": os.environ.get("WRITEHERE_SEARCH_MODE", "auto"),
                "max_search_queries": int(os.environ.get("WRITEHERE_MAX_SEARCH_QUERIES", "6")),
                "kb_variant_topk": int(os.environ.get("WRITEHERE_KB_VARIANT_TOPK", "4")),
                "kb_rerank_candidate_limit": int(os.environ.get("WRITEHERE_KB_RERANK_CANDIDATES", "24")),
                "kb_rerank_cpu_candidates": int(os.environ.get("WRITEHERE_KB_RERANK_CPU_CANDIDATES", "8")),
                "kb_rerank_mode": os.environ.get("WRITEHERE_KB_RERANK_MODE", "auto"),
                "kb_final_topk": int(os.environ.get("WRITEHERE_KB_FINAL_TOPK", "5")),
                "kb_diverse_per_source": int(os.environ.get("WRITEHERE_KB_DIVERSE_PER_SOURCE", "1")),
                "evidence_ledger": os.environ.get("WRITEHERE_EVIDENCE_LEDGER", "1").lower() not in ("0", "false", "no", "off"),
                "evidence_verify_mode": os.environ.get("WRITEHERE_EVIDENCE_VERIFY_MODE", "heuristic"),
                "rubric_gap_check": os.environ.get("WRITEHERE_RUBRIC_GAP_CHECK", "1").lower() not in ("0", "false", "no", "off"),
                "rubric_min_dimension_score": float(os.environ.get("WRITEHERE_RUBRIC_MIN_DIMENSION_SCORE", "0.42")),
                "rubric_min_supported_pages": int(os.environ.get("WRITEHERE_RUBRIC_MIN_SUPPORTED_PAGES", "2")),
                "webpage_helper_max_threads": 10, # use requests to download web page
                "search_max_thread": 4, # serpapi parallel
                "backend_engine": engine_backend, # google or bing, defined in serpapi
                "cc": "US", # search region
                "topk": 20,
                "pk_quota": 20, # search agent, pk quota, see __search
                "select_quota": 8, # search agent select quota
                "selector_max_workers": 8, # selector parallel
                "summarizier_max_workers": 8, # summarizer parallel
                "selector_model": "gpt-4o-mini",
                # "selector_model": "gemini-2.0-flash",
                "summarizer_model": "gpt-4o-mini",
                # "summarizer_model": "gemini-2.0-flash",
            },
            "search_merge": {
                "prompt_version": "MergeSearchResultVFinal", # search merge prompt
                "llm_args": {
                    "model": merge_model,
                },
                "parse_arg_dict": {
                    "result": ["result"],
                }
            },
            "atom": {
                "prompt_version": "ReportSearchOnlyUpdate",
                "llm_args": {
                    "model": fast_model,
                },
                "parse_arg_dict": {
                    "atom_think": ["think"],
                    "update_result": ["goal_updating"]
                },
                "all_atom": True,
                "only_on_depend": True
            },
            "planning": {},
            "update": {},
            "final_aggregate": {},
        },
        "REASONING": {
            "execute": {
                "prompt_version": "ReportReasoner",
                "llm_args": {
                    "model": reasoner_model,
                    "temperature": 0.3
                },
                "parse_arg_dict": {
                    "think": ["think"],
                    "result": ["result"],
                },
            },
            "atom": {
                # "use_candidate_plan": True
                "all_atom": True # force to atom
            },
            "planning": {},
            "update": {},
            "final_aggregate": {},
        },
    }
    config["tag2task_type"] = {v: k for k,v in config["task_type2tag"].items()}


    data = read_jsonl(input_filename)
    items = data[start:end]

    # Auto-detect language from user prompt
    if items:
        prompt = items[0].get("prompt", "")
        chinese_chars = sum(1 for c in prompt if '一' <= c <= '鿿')
        if chinese_chars > 5:
            config["language"] = "zh"
        else:
            config["language"] = "en"

    # 根据语言选择对应的prompt版本
    if config["language"] == "zh":
        # 中文版本的prompt配置
        # 注意：需要创建对应的中文prompt模板类
        # 如果不存在，系统会回退到英文版本，但prompt中会明确要求用中文回答
        logger.info("使用中文模式 - Language: zh")
    else:
        logger.info("使用英文模式 - Language: en")

    import pathlib
    root_folder = "{}/{}".format(str(pathlib.Path(output_filename).parent.parent),
                                 "records")
    caches["search"] = Cache("{}/../cache/{}-{}-search".format(root_folder, start, end)) # cache search and llm result
    caches["llm"] = Cache("{}/../cache/{}-{}-llm".format(root_folder, start, end))

    if os.path.exists(output_filename):
        done_ques = [item["prompt"]  for item in read_jsonl(output_filename)]
        filtered_items = [item for item in items if item["prompt"] not in done_ques]
        print("Has Done {} item, left {} items to run".format(len(done_ques), len(filtered_items)))
        items = filtered_items

    output_f = open(output_filename, "a", encoding="utf8")
    for item in items:
        question = item["prompt"]
        root_node = RegularDummyNode(
            config = config,
            nid = "",
            node_graph_info = {
                "outer_node": None,
                "root_node": None,
                "parent_nodes": [],
                "layer": 0
            },
            task_info = {
                "goal": question,
                "task_type": "write",
                "length": "You should determine itself, according to the question",
                "dependency": []
            },
            node_type = NodeType.PLAN_NODE
        )
        root_node.node_graph_info["root_node"] = root_node
        engine = GraphRunEngine(root_node, "xml", config)
        qstr = item["id"]
        folder = "{}/{}".format(root_folder, qstr)
        os.makedirs(folder, exist_ok=True)
        rf = open("{}/report.md".format(folder), "w")

        custom_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
        log_id = logger.add("{}/engine.log".format(folder), format=custom_format)
        try:
            result = engine.forward_one_step_untill_done(save_folder=folder, nl=True, nodes_json_file=nodes_json_file)
        except Exception as e:
            logger.error("Encounter exception: {}\nWhen Process {}".format(traceback.format_exc(), question))
            continue


        claim_verifier_enabled = _env_bool("WRITEHERE_LLM_CLAIM_VERIFIER", False)
        claim_verifier_model = os.environ.get(
            "WRITEHERE_CLAIM_VERIFIER_MODEL", fast_model)
        max_llm_claims = int(os.environ.get("WRITEHERE_CLAIM_VERIFIER_MAX_CLAIMS", "6"))
        repair_loop_enabled = _env_bool("WRITEHERE_REPAIR_LOOP", True)
        repair_model = os.environ.get("WRITEHERE_REPAIR_MODEL", writer_model)
        search_repair_enabled = _env_bool("WRITEHERE_SEARCH_REPAIR", True)
        search_repair_execute_kb = _env_bool(
            "WRITEHERE_SEARCH_REPAIR_EXECUTE_KB", True)

        evidence_graph = _save_final_evidence_graph(engine, folder, result)
        claim_verification = _save_claim_verification(
            engine, folder, result,
            llm_verifier=claim_verifier_enabled,
            verifier_model=claim_verifier_model,
            max_llm_claims=max_llm_claims,
        )
        draft_result = get_report_with_ref(
            _root_node_json_with_memory_pages(engine), result)
        draft_result = normalize_markdown_tables(draft_result)
        _, quality_audit = _postprocess_final_report(
            draft_result, folder, add_audit_section=False)
        writer_feedback = _save_writer_feedback(
            engine, folder, claim_verification, quality_audit, evidence_graph)
        search_repair, writer_feedback = _run_search_repair(
            engine,
            folder,
            writer_feedback,
            root_goal=question,
            enabled=search_repair_enabled,
            execute_kb=search_repair_execute_kb,
        )

        if (
            repair_loop_enabled
            and writer_feedback.get("summary", {}).get("repair_needed", False)
        ):
            repaired_result, repair_report = _run_report_repair_loop(
                engine, folder, result, writer_feedback, repair_model)
            if repair_report.get("repaired_section_count", 0) > 0:
                result = repaired_result
                evidence_graph = _save_final_evidence_graph(engine, folder, result)
                claim_verification = _save_claim_verification(
                    engine, folder, result,
                    llm_verifier=claim_verifier_enabled,
                    verifier_model=claim_verifier_model,
                    max_llm_claims=max_llm_claims,
                )
                draft_result = get_report_with_ref(
                    _root_node_json_with_memory_pages(engine), result)
                draft_result = normalize_markdown_tables(draft_result)
                _, quality_audit = _postprocess_final_report(
                    draft_result, folder, add_audit_section=False)
                writer_feedback = _save_writer_feedback(
                    engine, folder, claim_verification, quality_audit, evidence_graph)
                if search_repair.get("new_evidence_ids"):
                    writer_feedback = augment_writer_feedback_with_search_repair(
                        writer_feedback, search_repair)
                    save_writer_feedback(
                        "{}/writer_feedback.json".format(folder), writer_feedback)
        else:
            save_repair_report("{}/repair_loop.json".format(folder), {
                "version": "1.0",
                "enabled": repair_loop_enabled,
                "attempted_section_count": 0,
                "repaired_section_count": 0,
                "repaired_sections": [],
                "skipped": ["Repair loop disabled or no repair needed."],
                "error": "",
            })

        result = get_report_with_ref(_root_node_json_with_memory_pages(engine), result)
        result = normalize_markdown_tables(result)
        result, quality_audit = _postprocess_final_report(
            result, folder, add_audit_section=True)
        writer_feedback = _save_writer_feedback(
            engine, folder, claim_verification, quality_audit, evidence_graph)
        if search_repair.get("new_evidence_ids"):
            writer_feedback = augment_writer_feedback_with_search_repair(
                writer_feedback, search_repair)
            save_writer_feedback("{}/writer_feedback.json".format(folder), writer_feedback)
        item["result"] = result
        output_f.write(json.dumps(item, ensure_ascii=False) + "\n")
        output_f.flush()
        rf.write(item["result"])
        rf.flush()
        rf.close()

        logger.remove(log_id)

    if done_flag_file is not None:
        with open(done_flag_file, "w") as f:
            f.write("done")



def define_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--filename", type=str, required=True)
    parser.add_argument("--mode", type=str, choices=["story", "report"], required=True)
    parser.add_argument("--output-filename", type=str, required=True)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--length", type=int)
    parser.add_argument("--engine-backend", type=str)
    parser.add_argument("--nodes-json-file", type=str, help="Path to save nodes.json for real-time visualization")
    current_date = datetime.now().strftime("%b %d, %Y")  # Format: "Apr 1, 2025"
    parser.add_argument("--today-date", type=str, default=current_date, help="Today's date to use in prompts (default: current date)")

    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--done-flag-file", type=str, default=None)
    parser.add_argument("--need-continue", action="store_true")
    return parser



if __name__ == "__main__":
    parser = define_args()
    args = parser.parse_args()
    if args.mode == "story":
        story_writing(args.filename, args.output_filename,
                      args.start, args.end, args.done_flag_file, args.model,
                      nodes_json_file=args.nodes_json_file)
    else:
        report_writing(args.filename, args.output_filename,
                       args.start, args.end, args.done_flag_file, args.model, args.engine_backend,
                       nodes_json_file=args.nodes_json_file, today_date=args.today_date)
