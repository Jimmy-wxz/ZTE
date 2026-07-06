#!/usr/bin/env python3
"""
Agent 评估系统使用示例

这个脚本演示了如何使用评估系统来追踪和评估 Agent 的执行过程。
可以独立运行进行测试，也可以作为集成参考。
"""

import time
import random
from datetime import datetime
from pathlib import Path

# 导入评估系统
from evaluation import AgentEvaluator, EvaluationLogger
from evaluation.models import (
    AgentType,
    TaskStatus,
    StepType,
    LLMCallDetails,
    ToolCallDetails,
    EvaluationConfig
)


def simulate_writehere_execution():
    """
    模拟 WriteHERE Agent 的执行过程

    这个函数模拟了一个技术报告生成任务，展示了如何记录各种步骤。
    """
    print("\n" + "="*60)
    print("📝 WriteHERE - 技术报告生成任务")
    print("="*60)

    # 创建评估器
    evaluator = AgentEvaluator(
        agent_type=AgentType.WRITEHERE,
        log_dir="./evaluation/logs/writehere",
        results_dir="./evaluation/results/writehere"
    )

    # 开始评估会话
    eval_id = evaluator.start_evaluation_session()
    print(f"✓ 开始评估会话：{eval_id}")

    # 模拟多个任务的执行
    tasks = [
        {
            "id": "task_001",
            "description": "生成人工智能技术报告",
            "expected_output": "2000 字的技术报告",
            "steps": [
                {"name": "需求分析", "type": "llm_call", "duration": 2.5, "tokens": 1500},
                {"name": "信息检索", "type": "tool_call", "duration": 3.0, "success": True},
                {"name": "大纲规划", "type": "llm_call", "duration": 1.8, "tokens": 800},
                {"name": "内容撰写 - 引言", "type": "llm_call", "duration": 4.2, "tokens": 2000},
                {"name": "内容撰写 - 主体", "type": "llm_call", "duration": 6.5, "tokens": 3500},
                {"name": "内容撰写 - 结论", "type": "llm_call", "duration": 3.0, "tokens": 1200},
                {"name": "格式检查", "type": "tool_call", "duration": 1.5, "success": True}
            ]
        },
        {
            "id": "task_002",
            "description": "生成市场分析文档",
            "expected_output": "1500 字的分析报告",
            "steps": [
                {"name": "市场数据收集", "type": "tool_call", "duration": 4.0, "success": True},
                {"name": "数据分析", "type": "llm_call", "duration": 3.5, "tokens": 1800},
                {"name": "趋势预测", "type": "llm_call", "duration": 2.8, "tokens": 1000},
                {"name": "报告生成", "type": "llm_call", "duration": 5.0, "tokens": 2500}
            ]
        },
        {
            "id": "task_003",
            "description": "生成产品说明书",
            "expected_output": "1000 字的产品说明",
            "steps": [
                {"name": "产品信息提取", "type": "llm_call", "duration": 2.0, "tokens": 900},
                {"name": "功能描述", "type": "llm_call", "duration": 3.5, "tokens": 1500},
                {"name": "使用指南编写", "type": "llm_call", "duration": 4.0, "tokens": 1800},
                {"name": "注意事项整理", "type": "llm_call", "duration": 2.5, "tokens": 1000}
            ]
        }
    ]

    # 执行每个任务
    for task in tasks:
        print(f"\n▶ 执行任务：{task['id']} - {task['description']}")

        # 开始轨迹
        trajectory_id = evaluator.start_trajectory(
            task_id=task["id"],
            task_description=task["description"],
            expected_output=task["expected_output"]
        )

        try:
            # 执行每个步骤
            for step_info in task["steps"]:
                print(f"  ↳ 执行步骤：{step_info['name']}")

                if step_info["type"] == "llm_call":
                    # 模拟 LLM 调用
                    time.sleep(step_info["duration"] * 0.1)  # 加速模拟

                    # 随机模拟一些错误情况（5% 概率）
                    has_error = random.random() < 0.05

                    evaluator.record_llm_call(
                        trajectory_id=trajectory_id,
                        step_name=step_info["name"],
                        model_name="gpt-4o",
                        prompt_tokens=int(step_info["tokens"] * 0.3),
                        completion_tokens=step_info["tokens"],
                        total_tokens=int(step_info["tokens"] * 1.3),
                        temperature=0.7,
                        max_tokens=4000,
                        top_p=0.9,
                        prompt_format_correct=not has_error,
                        parameters_valid=True,
                        response_parsed_successfully=not has_error,
                        error_message="解析失败" if has_error else None,
                        metadata={
                            "simulated_duration_s": step_info["duration"],
                            "step_category": "generation"
                        }
                    )

                    if has_error:
                        print(f"    ⚠️ 发生错误：解析失败")
                    else:
                        print(f"    ✓ 完成，生成 {step_info['tokens']} tokens")

                elif step_info["type"] == "tool_call":
                    # 模拟工具调用
                    time.sleep(step_info["duration"] * 0.1)

                    # 随机模拟一些错误情况（3% 概率）
                    success = step_info.get("success", True) and random.random() > 0.03

                    tool_name = "bing_search" if "检索" in step_info["name"] or "收集" in step_info["name"] else "format_checker"
                    tool_type = "search" if "检索" in step_info["name"] or "收集" in step_info["name"] else "validation"

                    evaluator.record_tool_call(
                        trajectory_id=trajectory_id,
                        step_name=step_info["name"],
                        tool_name=tool_name,
                        tool_type=tool_type,
                        input_parameters={"query": f"sample query for {step_info['name']}"},
                        output_result={"data": "sample result"} if success else None,
                        parameters_format_correct=True,
                        tool_execution_successful=success,
                        output_format_valid=success,
                        error_message=None if success else "工具执行超时",
                        metadata={
                            "simulated_duration_s": step_info["duration"]
                        }
                    )

                    if success:
                        print(f"    ✓ 工具调用成功")
                    else:
                        print(f"    ✗ 工具调用失败：超时")

            # 结束轨迹（成功）
            evaluator.end_trajectory(
                trajectory_id=trajectory_id,
                status=TaskStatus.COMPLETED,
                actual_output=f"Generated output for {task['id']}"
            )
            print(f"  ✓ 任务完成")

        except Exception as e:
            # 结束轨迹（失败）
            evaluator.end_trajectory(
                trajectory_id=trajectory_id,
                status=TaskStatus.FAILED,
                actual_output=None
            )
            print(f"  ✗ 任务失败：{e}")

    # 生成评估报告
    print("\n" + "="*60)
    print("📊 生成评估报告...")
    print("="*60)

    result = evaluator.evaluate_current_session()

    # 打印结果摘要
    print(f"\n✅ 评估完成!")
    print(f"\n单步级别评估:")
    print(f"  • 综合得分：{result.overall_step_level_score:.1f}/100")
    print(f"  • LLM 调用准确率：{result.llm_call_accuracy:.1f}%")
    print(f"  • 工具调用准确率：{result.tool_call_accuracy:.1f}%")
    print(f"  • 参数格式准确率：{result.parameter_format_accuracy:.1f}%")
    print(f"  • 响应解析准确率：{result.response_parse_accuracy:.1f}%")

    print(f"\n轨迹级别评估:")
    print(f"  • 综合得分：{result.overall_trajectory_level_score:.1f}/100")
    print(f"  • 平均合理性得分：{result.avg_rationality_score:.1f}/100")
    print(f"  • 平均效率得分：{result.avg_efficiency_score:.1f}/100")
    print(f"  • 轨迹成功率：{result.trajectory_success_rate:.1f}%")
    print(f"  • 平均耗时：{result.avg_trajectory_duration_ms/1000:.1f}秒")

    if result.identified_issues:
        print(f"\n⚠️ 识别出的问题:")
        for issue in result.identified_issues:
            print(f"  - {issue}")

    if result.improvement_suggestions:
        print(f"\n💡 改进建议:")
        for suggestion in result.improvement_suggestions:
            print(f"  - {suggestion}")

    print(f"\n📁 详细报告已保存到：{evaluator.results_dir}")
    print(f"   - JSON 格式：{result.evaluation_id}.json")
    print(f"   - Markdown 格式：{result.evaluation_id}_report.md")

    return result


def simulate_mo_shen_execution():
    """
    模拟 Mo-Shen Agent 的执行过程

    这个函数模拟了一个小说创作任务，展示了多智能体协作的评估。
    """
    print("\n" + "="*60)
    print("🖋️ Mo-Shen - 小说创作任务")
    print("="*60)

    # 使用自定义配置
    config = EvaluationConfig(
        max_acceptable_step_duration_ms=6000,  # 更宽松的耗时阈值
        llm_call_weight=0.5,                   # LLM 调用权重更高
        tool_call_weight=0.2,                  # 工具调用权重较低
        rationality_weight=0.7                 # 更注重合理性
    )

    evaluator = AgentEvaluator(
        agent_type=AgentType.MO_SHEN,
        config=config,
        log_dir="./evaluation/logs/mo_shen",
        results_dir="./evaluation/results/mo_shen"
    )

    # 开始评估会话
    eval_id = evaluator.start_evaluation_session()
    print(f"✓ 开始评估会话：{eval_id}")

    # 模拟标准模式的完整工作流
    workflow_steps = [
        {"agent": "Planner", "action": "分析创作需求", "type": "llm_call", "duration": 2.0, "tokens": 1200},
        {"agent": "Worldbuilder", "action": "构建世界观设定", "type": "llm_call", "duration": 4.5, "tokens": 2500},
        {"agent": "CharacterDesigner", "action": "设计主要角色", "type": "llm_call", "duration": 3.8, "tokens": 2000},
        {"agent": "Outliner", "action": "制定章节大纲", "type": "llm_call", "duration": 3.0, "tokens": 1500},
        {"agent": "ChapterWriter", "action": "撰写第 1 章", "type": "llm_call", "duration": 6.0, "tokens": 3000},
        {"agent": "ChapterWriter", "action": "撰写第 2 章", "type": "llm_call", "duration": 5.5, "tokens": 2800},
        {"agent": "ChapterWriter", "action": "撰写第 3 章", "type": "llm_call", "duration": 6.2, "tokens": 3200},
        {"agent": "ContinuityReviewer", "action": "连续性审查", "type": "llm_call", "duration": 3.5, "tokens": 1800},
        {"agent": "Showrunner", "action": "最终审校", "type": "llm_call", "duration": 2.5, "tokens": 1000}
    ]

    # 开始轨迹
    trajectory_id = evaluator.start_trajectory(
        task_id="novel_creation_001",
        task_description="创作一篇海上记忆之城的悬疑故事（3 章）",
        expected_output="3 章连贯的悬疑小说，约 9000 字"
    )

    try:
        for i, step in enumerate(workflow_steps):
            print(f"\n▶ [{step['agent']}] {step['action']}")

            # 模拟执行
            time.sleep(step["duration"] * 0.1)

            # 模拟高质量输出（Mo-Shen 通常表现更好）
            success_prob = 0.98  # 98% 成功率

            is_success = random.random() < success_prob

            evaluator.record_llm_call(
                trajectory_id=trajectory_id,
                step_name=f"{step['agent']}: {step['action']}",
                model_name="deepseek-chat",
                prompt_tokens=int(step["tokens"] * 0.4),
                completion_tokens=step["tokens"],
                total_tokens=int(step["tokens"] * 1.4),
                temperature=0.8 if "Writer" in step["agent"] else 0.6,
                max_tokens=4096,
                top_p=0.95,
                prompt_format_correct=is_success,
                parameters_valid=is_success,
                response_parsed_successfully=is_success,
                error_message=None if is_success else "模型调用失败",
                metadata={
                    "agent": step["agent"],
                    "workflow_position": i + 1,
                    "total_agents": len(workflow_steps),
                    "simulated_duration_s": step["duration"]
                }
            )

            if is_success:
                print(f"  ✓ 完成，生成 {step['tokens']} tokens")
            else:
                print(f"  ✗ 失败：模型调用失败")

        # 结束轨迹
        evaluator.end_trajectory(
            trajectory_id=trajectory_id,
            status=TaskStatus.COMPLETED,
            actual_output="Completed novel with 3 chapters"
        )

        print(f"\n✓ 小说创作完成")

    except Exception as e:
        evaluator.end_trajectory(
            trajectory_id=trajectory_id,
            status=TaskStatus.FAILED
        )
        print(f"✗ 创作失败：{e}")

    # 生成评估报告
    print("\n" + "="*60)
    print("📊 生成评估报告...")
    print("="*60)

    result = evaluator.evaluate_current_session()

    # 打印结果
    print(f"\n✅ 评估完成!")
    print(f"\n单步级别评估:")
    print(f"  • 综合得分：{result.overall_step_level_score:.1f}/100")
    print(f"  • LLM 调用准确率：{result.llm_call_accuracy:.1f}%")
    print(f"  • 工具调用准确率：{result.tool_call_accuracy:.1f}%")

    print(f"\n轨迹级别评估:")
    print(f"  • 综合得分：{result.overall_trajectory_level_score:.1f}/100")
    print(f"  • 平均合理性得分：{result.avg_rationality_score:.1f}/100")
    print(f"  • 平均效率得分：{result.avg_efficiency_score:.1f}/100")
    print(f"  • 轨迹成功率：{result.trajectory_success_rate:.1f}%")

    print(f"\n📁 详细报告已保存到：{evaluator.results_dir}")

    return result


def compare_results(writehere_result, mo_shen_result):
    """
    对比两个 Agent 的评估结果
    """
    print("\n" + "="*60)
    print("🏆 Agent 能力对比")
    print("="*60)

    metrics = [
        ("单步级别综合得分", "overall_step_level_score"),
        ("轨迹级别综合得分", "overall_trajectory_level_score"),
        ("LLM 调用准确率", "llm_call_accuracy"),
        ("轨迹成功率", "trajectory_success_rate"),
        ("平均合理性得分", "avg_rationality_score"),
        ("平均效率得分", "avg_efficiency_score")
    ]

    print(f"\n{'指标':<20} {'WriteHERE':>12} {'Mo-Shen':>12} {'差异':>10}")
    print("-" * 60)

    for label, key in metrics:
        wh_value = getattr(writehere_result, key, 0)
        ms_value = getattr(mo_shen_result, key, 0)
        diff = wh_value - ms_value

        diff_str = f"+{diff:.1f}" if diff > 0 else f"{diff:.1f}"

        # 标记优胜者
        if wh_value > ms_value:
            print(f"{label:<20} {wh_value:>11.1f}* {ms_value:>12.1f} {diff_str:>10}")
        elif ms_value > wh_value:
            print(f"{label:<20} {wh_value:>12.1f} {ms_value:>11.1f}* {diff_str:>10}")
        else:
            print(f"{label:<20} {wh_value:>12.1f} {ms_value:>12.1f} {diff_str:>10}")

    print("\n* 表示该项领先")

    # 总体评价
    wh_total = writehere_result.overall_step_level_score + writehere_result.overall_trajectory_level_score
    ms_total = mo_shen_result.overall_step_level_score + mo_shen_result.overall_trajectory_level_score

    print(f"\n📈 总体评价:")
    if wh_total > ms_total:
        print(f"   WriteHERE 在综合评估中略占优势 (+{wh_total - ms_total:.1f}分)")
    elif ms_total > wh_total:
        print(f"   Mo-Shen 在综合评估中略占优势 (+{ms_total - wh_total:.1f}分)")
    else:
        print(f"   两个 Agent 表现相当")


def main():
    """主函数"""
    print("\n" + "█"*60)
    print("█  Agent 评估系统演示")
    print("█  Enterprise Document Production Agent Evaluation")
    print("█"*60)

    # 确保输出目录存在
    Path("./evaluation/logs/writehere").mkdir(parents=True, exist_ok=True)
    Path("./evaluation/results/writehere").mkdir(parents=True, exist_ok=True)
    Path("./evaluation/logs/mo_shen").mkdir(parents=True, exist_ok=True)
    Path("./evaluation/results/mo_shen").mkdir(parents=True, exist_ok=True)

    # 运行 WriteHERE 评估
    writehere_result = simulate_writehere_execution()

    # 运行 Mo-Shen 评估
    mo_shen_result = simulate_mo_shen_execution()

    # 对比结果
    compare_results(writehere_result, mo_shen_result)

    print("\n" + "="*60)
    print("✅ 演示完成!")
    print("="*60)
    print("\n下一步:")
    print("1. 查看生成的日志文件：./evaluation/logs/")
    print("2. 查看评估结果：./evaluation/results/")
    print("3. 在网页上测试前端仪表盘")
    print("4. 进行第三步：任务完成度手动评估")
    print("\n")


if __name__ == "__main__":
    main()
