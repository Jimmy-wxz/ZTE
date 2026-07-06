"""
评估系统的数据模型定义

兼容 Python 3.6+，在 Python 3.6 时需要安装 dataclasses 包:
pip install dataclasses
"""

try:
    from dataclasses import dataclass, field
except ImportError:
    # Python 3.6 需要额外安装包
    from typing import Any, Dict, List, Optional
    def dataclass(cls):
        return cls
    def field(default_factory=None):
        return None

from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum


class StepType(str, Enum):
    """步骤类型枚举"""
    LLM_CALL = "llm_call"           # LLM 调用
    TOOL_CALL = "tool_call"         # 工具调用
    PLANNING = "planning"           # 规划步骤
    EXECUTION = "execution"         # 执行步骤
    MEMORY_READ = "memory_read"     # 记忆读取
    MEMORY_WRITE = "memory_write"   # 记忆写入
    OTHER = "other"                 # 其他类型


class AgentType(str, Enum):
    """Agent 类型枚举"""
    WRITEHERE = "writehere"
    MO_SHEN = "mo_shen"


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class LLMCallDetails:
    """LLM 调用的详细信息"""
    model_name: str                              # 使用的模型名称
    prompt_tokens: int                           # 输入 token 数
    completion_tokens: int                       # 输出 token 数
    total_tokens: int                            # 总 token 数
    temperature: float                           # 温度参数
    max_tokens: Optional[int] = None             # 最大生成 token 数
    top_p: Optional[float] = None                # Top-p 采样参数
    stop_sequences: Optional[List[str]] = None   # 停止序列
    response_format: Optional[str] = None        # 响应格式（如 json_schema）

    # 正确性评估字段
    prompt_format_correct: bool = True           # prompt 格式是否正确
    parameters_valid: bool = True                # 参数是否有效
    response_parsed_successfully: bool = True    # 响应是否成功解析
    error_message: Optional[str] = None          # 错误信息（如果有）


@dataclass
class ToolCallDetails:
    """工具调用的详细信息"""
    tool_name: str                               # 工具名称
    tool_type: str                               # 工具类型（search, file_io, etc.）
    input_parameters: Dict[str, Any]             # 输入参数
    output_result: Any = None                    # 输出结果

    # 正确性评估字段
    parameters_format_correct: bool = True       # 参数格式是否正确
    tool_execution_successful: bool = True       # 工具执行是否成功
    output_format_valid: bool = True             # 输出格式是否有效
    error_message: Optional[str] = None          # 错误信息（如果有）


@dataclass
class StepRecord:
    """
    单步记录 - 用于追踪每个独立的操作步骤

    这是最小评估单元，对应一次 LLM 调用或工具调用
    """
    step_id: str                                 # 步骤唯一标识符
    timestamp_start: datetime                    # 开始时间
    timestamp_end: datetime                      # 结束时间
    duration_ms: int                             # 耗时（毫秒）
    agent_type: AgentType                        # Agent 类型（writehere/mo_shen）
    step_type: StepType                          # 步骤类型
    step_name: str                               # 步骤名称/描述
    parent_task_id: Optional[str] = None         # 父任务 ID（用于层级追踪）

    # 详细内容
    llm_details: Optional[LLMCallDetails] = None  # LLM 调用详情（如果是 LLM 步骤）
    tool_details: Optional[ToolCallDetails] = None  # 工具调用详情（如果是工具步骤）

    # 评估分数（0-100）
    correctness_score: float = 100.0             # 正确性得分
    efficiency_score: float = 100.0              # 效率得分（基于耗时等）

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，便于序列化"""
        return {
            "step_id": self.step_id,
            "timestamp_start": self.timestamp_start.isoformat(),
            "timestamp_end": self.timestamp_end.isoformat(),
            "duration_ms": self.duration_ms,
            "agent_type": self.agent_type.value,
            "step_type": self.step_type.value,
            "step_name": self.step_name,
            "parent_task_id": self.parent_task_id,
            "llm_details": self._llm_details_to_dict(),
            "tool_details": self._tool_details_to_dict(),
            "correctness_score": self.correctness_score,
            "efficiency_score": self.efficiency_score,
            "metadata": self.metadata
        }

    def _llm_details_to_dict(self) -> Optional[Dict[str, Any]]:
        """将 LLM 详情转换为字典"""
        if self.llm_details is None:
            return None
        return {
            "model_name": self.llm_details.model_name,
            "prompt_tokens": self.llm_details.prompt_tokens,
            "completion_tokens": self.llm_details.completion_tokens,
            "total_tokens": self.llm_details.total_tokens,
            "temperature": self.llm_details.temperature,
            "max_tokens": self.llm_details.max_tokens,
            "top_p": self.llm_details.top_p,
            "stop_sequences": self.llm_details.stop_sequences,
            "response_format": self.llm_details.response_format,
            "prompt_format_correct": self.llm_details.prompt_format_correct,
            "parameters_valid": self.llm_details.parameters_valid,
            "response_parsed_successfully": self.llm_details.response_parsed_successfully,
            "error_message": self.llm_details.error_message
        }

    def _tool_details_to_dict(self) -> Optional[Dict[str, Any]]:
        """将工具详情转换为字典"""
        if self.tool_details is None:
            return None
        return {
            "tool_name": self.tool_details.tool_name,
            "tool_type": self.tool_details.tool_type,
            "input_parameters": self.tool_details.input_parameters,
            "output_result": str(self.tool_details.output_result) if self.tool_details.output_result else None,
            "parameters_format_correct": self.tool_details.parameters_format_correct,
            "tool_execution_successful": self.tool_details.tool_execution_successful,
            "output_format_valid": self.tool_details.output_format_valid,
            "error_message": self.tool_details.error_message
        }


@dataclass
class TrajectoryRecord:
    """
    轨迹记录 - 用于追踪整个任务执行链路

    包含一系列相关的步骤，用于评估整体流程的合理性和效率
    """
    trajectory_id: str                           # 轨迹唯一标识符
    task_id: str                                 # 任务唯一标识符
    agent_type: AgentType                        # Agent 类型
    start_time: datetime                         # 开始时间
    end_time: Optional[datetime] = None          # 结束时间
    status: TaskStatus = TaskStatus.IN_PROGRESS  # 当前状态

    # 步骤列表
    steps: List[StepRecord] = field(default_factory=list)

    # 轨迹级评估
    total_duration_ms: int = 0                   # 总耗时（毫秒）
    num_llm_calls: int = 0                       # LLM 调用次数
    num_tool_calls: int = 0                      # 工具调用次数
    num_steps: int = 0                           # 总步骤数

    # 效率指标
    avg_step_duration_ms: float = 0.0            # 平均步骤耗时
    longest_step_id: Optional[str] = None        # 最耗时步骤的 ID
    shortest_step_id: Optional[str] = None       # 最快速步骤的 ID

    # 质量指标
    success_rate: float = 100.0                  # 成功率（成功步骤/总步骤）
    avg_correctness_score: float = 100.0         # 平均正确性得分
    avg_efficiency_score: float = 100.0          # 平均效率得分

    # 轨迹合理性评估
    trajectory_rationality_score: float = 100.0  # 轨迹合理性得分
    trajectory_efficiency_score: float = 100.0   # 轨迹效率得分

    # 元数据
    task_description: Optional[str] = None       # 任务描述
    expected_output: Optional[str] = None        # 预期输出
    actual_output: Optional[str] = None          # 实际输出
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_step(self, step: StepRecord) -> None:
        """添加一个步骤到轨迹中"""
        self.steps.append(step)
        self._update_metrics()

    def _update_metrics(self) -> None:
        """更新轨迹指标"""
        if not self.steps:
            return

        self.num_steps = len(self.steps)

        # 计算 LLM 和工具调用次数
        self.num_llm_calls = sum(1 for s in self.steps if s.step_type == StepType.LLM_CALL)
        self.num_tool_calls = sum(1 for s in self.steps if s.step_type == StepType.TOOL_CALL)

        # 计算总耗时
        if self.steps:
            self.total_duration_ms = sum(s.duration_ms for s in self.steps)
            self.avg_step_duration_ms = self.total_duration_ms / self.num_steps

            # 找出最长和最短的步骤
            durations = [(s.step_id, s.duration_ms) for s in self.steps]
            self.longest_step_id = max(durations, key=lambda x: x[1])[0]
            self.shortest_step_id = min(durations, key=lambda x: x[1])[0]

        # 计算成功率
        failed_steps = sum(1 for s in self.steps if
                          (s.llm_details and not s.llm_details.response_parsed_successfully) or
                          (s.tool_details and not s.tool_details.tool_execution_successful))
        self.success_rate = ((self.num_steps - failed_steps) / self.num_steps * 100) if self.num_steps > 0 else 100.0

        # 计算平均分数
        if self.steps:
            self.avg_correctness_score = sum(s.correctness_score for s in self.steps) / self.num_steps
            self.avg_efficiency_score = sum(s.efficiency_score for s in self.steps) / self.num_steps

    def finalize(self, status: TaskStatus = TaskStatus.COMPLETED) -> None:
        """完成轨迹记录"""
        self.end_time = datetime.now()
        self.status = status
        self._update_metrics()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "trajectory_id": self.trajectory_id,
            "task_id": self.task_id,
            "agent_type": self.agent_type.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "total_duration_ms": self.total_duration_ms,
            "num_llm_calls": self.num_llm_calls,
            "num_tool_calls": self.num_tool_calls,
            "num_steps": self.num_steps,
            "avg_step_duration_ms": self.avg_step_duration_ms,
            "longest_step_id": self.longest_step_id,
            "shortest_step_id": self.shortest_step_id,
            "success_rate": self.success_rate,
            "avg_correctness_score": self.avg_correctness_score,
            "avg_efficiency_score": self.avg_efficiency_score,
            "trajectory_rationality_score": self.trajectory_rationality_score,
            "trajectory_efficiency_score": self.trajectory_efficiency_score,
            "task_description": self.task_description,
            "expected_output": self.expected_output,
            "actual_output": self.actual_output,
            "metadata": self.metadata
        }


@dataclass
class EvaluationResult:
    """
    评估结果 - 综合单步和轨迹评估的最终结果
    """
    evaluation_id: str                           # 评估唯一标识符
    agent_type: AgentType                        # Agent 类型
    evaluation_timestamp: datetime               # 评估时间

    # 单步评估汇总
    total_steps_evaluated: int = 0               # 评估的总步骤数
    llm_call_accuracy: float = 0.0               # LLM 调用准确率
    tool_call_accuracy: float = 0.0              # 工具调用准确率
    parameter_format_accuracy: float = 0.0       # 参数格式准确率
    response_parse_accuracy: float = 0.0         # 响应解析准确率

    # 轨迹评估汇总
    total_trajectories: int = 0                  # 轨迹总数
    avg_trajectory_duration_ms: float = 0.0      # 平均轨迹耗时
    avg_steps_per_trajectory: float = 0.0        # 每条轨迹的平均步骤数
    trajectory_success_rate: float = 0.0         # 轨迹成功率
    avg_rationality_score: float = 0.0           # 平均合理性得分
    avg_efficiency_score: float = 0.0            # 平均效率得分

    # 综合评分
    overall_step_level_score: float = 0.0        # 单步级别综合得分
    overall_trajectory_level_score: float = 0.0  # 轨迹级别综合得分

    # 详细报告
    trajectories: List[TrajectoryRecord] = field(default_factory=list)
    detailed_report: Dict[str, Any] = field(default_factory=dict)

    # 问题和建议
    identified_issues: List[str] = field(default_factory=list)
    improvement_suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "evaluation_id": self.evaluation_id,
            "agent_type": self.agent_type.value,
            "evaluation_timestamp": self.evaluation_timestamp.isoformat(),
            "total_steps_evaluated": self.total_steps_evaluated,
            "llm_call_accuracy": self.llm_call_accuracy,
            "tool_call_accuracy": self.tool_call_accuracy,
            "parameter_format_accuracy": self.parameter_format_accuracy,
            "response_parse_accuracy": self.response_parse_accuracy,
            "total_trajectories": self.total_trajectories,
            "avg_trajectory_duration_ms": self.avg_trajectory_duration_ms,
            "avg_steps_per_trajectory": self.avg_steps_per_trajectory,
            "trajectory_success_rate": self.trajectory_success_rate,
            "avg_rationality_score": self.avg_rationality_score,
            "avg_efficiency_score": self.avg_efficiency_score,
            "overall_step_level_score": self.overall_step_level_score,
            "overall_trajectory_level_score": self.overall_trajectory_level_score,
            "trajectories": [t.to_dict() for t in self.trajectories],
            "detailed_report": self.detailed_report,
            "identified_issues": self.identified_issues,
            "improvement_suggestions": self.improvement_suggestions
        }


@dataclass
class EvaluationConfig:
    """评估配置"""
    # 性能阈值
    max_acceptable_step_duration_ms: int = 5000  # 可接受的最大步骤耗时
    min_efficiency_threshold: float = 70.0       # 最低效率阈值

    # 正确性权重
    llm_call_weight: float = 0.4                 # LLM 调用权重
    tool_call_weight: float = 0.3                # 工具调用权重
    parameter_format_weight: float = 0.2         # 参数格式权重
    response_parse_weight: float = 0.1           # 响应解析权重

    # 轨迹评估权重
    rationality_weight: float = 0.6              # 合理性权重
    efficiency_weight: float = 0.4               # 效率权重

    # 日志配置
    log_level: str = "INFO"                      # 日志级别
    save_raw_logs: bool = True                   # 是否保存原始日志
    save_aggregated_stats: bool = True           # 是否保存聚合统计

    # 输出配置
    output_format: str = "json"                  # 输出格式（json/csv/html）
    output_directory: str = "./evaluation_results"  # 输出目录
