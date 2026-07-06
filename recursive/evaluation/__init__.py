"""
企业文档生产 Agent 评估系统

评估标准分为 3 级：
1. 单步评估（Step-level Evaluation）- LLM 调用及工具调用的正确性
2. 轨迹评估（Trajectory-level Evaluation）- 整体链路的合理性和效率
3. 任务完成度评估（Task Completion Evaluation）- 最终输出质量（手动评估）
"""

from .evaluator import AgentEvaluator
from .models import StepRecord, TrajectoryRecord, EvaluationResult
from .logger import EvaluationLogger

__version__ = "1.0.0"
__all__ = [
    "AgentEvaluator",
    "StepRecord",
    "TrajectoryRecord",
    "EvaluationResult",
    "EvaluationLogger"
]
