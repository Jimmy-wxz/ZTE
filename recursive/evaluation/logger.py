"""
评估日志记录器

负责记录 Agent 执行过程中的各种事件和指标
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from .models import (
    StepRecord,
    TrajectoryRecord,
    LLMCallDetails,
    ToolCallDetails,
    StepType,
    AgentType,
    TaskStatus
)


class EvaluationLogger:
    """
    评估日志记录器

    功能：
    1. 记录每个步骤的详细信息（LLM 调用、工具调用）
    2. 追踪轨迹级别的执行流程
    3. 自动计算耗时和效率指标
    4. 生成结构化的日志文件供后续分析
    """

    def __init__(
        self,
        log_dir: str = "./evaluation/logs",
        agent_type: AgentType = AgentType.WRITEHERE,
        session_id: Optional[str] = None
    ):
        """
        初始化评估日志记录器

        Args:
            log_dir: 日志存储目录
            agent_type: Agent 类型（writehere 或 mo_shen）
            session_id: 会话 ID，用于区分不同的评估会话
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.agent_type = agent_type
        self.session_id = session_id or str(uuid.uuid4())

        # 当前活跃的轨迹
        self._active_trajectories: Dict[str, TrajectoryRecord] = {}

        # 当前活跃的步骤
        self._active_steps: Dict[str, StepRecord] = {}

        # 设置日志记录器
        self.logger = self._setup_logger()

        # 元数据
        self.metadata: Dict[str, Any] = {
            "session_id": self.session_id,
            "agent_type": agent_type.value,
            "start_time": datetime.now().isoformat()
        }

    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger_name = f"eval_{self.agent_type.value}_{self.session_id[:8]}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)

        # 创建文件处理器
        log_file = self.log_dir / f"{logger_name}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)

        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # 设置格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # 添加处理器
        if not logger.handlers:
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)

        return logger

    def start_trajectory(
        self,
        task_id: str,
        task_description: Optional[str] = None,
        expected_output: Optional[str] = None
    ) -> str:
        """
        开始一个新的轨迹记录

        Args:
            task_id: 任务唯一标识符
            task_description: 任务描述
            expected_output: 预期输出

        Returns:
            trajectory_id: 轨迹 ID
        """
        trajectory_id = f"traj_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        trajectory = TrajectoryRecord(
            trajectory_id=trajectory_id,
            task_id=task_id,
            agent_type=self.agent_type,
            start_time=datetime.now(),
            task_description=task_description,
            expected_output=expected_output
        )

        self._active_trajectories[trajectory_id] = trajectory
        self.logger.info(f"开始轨迹：{trajectory_id}, 任务：{task_id}")

        return trajectory_id

    def end_trajectory(
        self,
        trajectory_id: str,
        status: TaskStatus = TaskStatus.COMPLETED,
        actual_output: Optional[str] = None
    ) -> TrajectoryRecord:
        """
        结束一个轨迹记录

        Args:
            trajectory_id: 轨迹 ID
            status: 任务状态
            actual_output: 实际输出

        Returns:
            trajectory: 完成的轨迹记录
        """
        if trajectory_id not in self._active_trajectories:
            raise ValueError(f"轨迹 {trajectory_id} 不存在")

        trajectory = self._active_trajectories[trajectory_id]
        trajectory.finalize(status)
        trajectory.actual_output = actual_output

        # 保存到文件
        self._save_trajectory(trajectory)

        # 从活跃列表中移除
        del self._active_trajectories[trajectory_id]

        self.logger.info(
            f"结束轨迹：{trajectory_id}, "
            f"状态：{status.value}, "
            f"耗时：{trajectory.total_duration_ms}ms, "
            f"步骤数：{trajectory.num_steps}"
        )

        return trajectory

    def start_step(
        self,
        step_type: StepType,
        step_name: str,
        trajectory_id: str,
        parent_task_id: Optional[str] = None
    ) -> str:
        """
        开始一个步骤记录

        Args:
            step_type: 步骤类型
            step_name: 步骤名称
            trajectory_id: 所属轨迹 ID
            parent_task_id: 父任务 ID

        Returns:
            step_id: 步骤 ID
        """
        step_id = f"step_{uuid.uuid4().hex[:8]}"

        step = StepRecord(
            step_id=step_id,
            timestamp_start=datetime.now(),
            timestamp_end=datetime.now(),  # 临时值，end_step 时会更新
            duration_ms=0,
            agent_type=self.agent_type,
            step_type=step_type,
            step_name=step_name,
            parent_task_id=parent_task_id
        )

        self._active_steps[step_id] = step

        # 如果提供了轨迹 ID，添加到轨迹中
        if trajectory_id and trajectory_id in self._active_trajectories:
            # 注意：这里先不添加到轨迹，等 end_step 时再添加
            pass

        self.logger.debug(f"开始步骤：{step_id}, 类型：{step_type.value}, 名称：{step_name}")

        return step_id

    def end_step(
        self,
        step_id: str,
        llm_details: Optional[LLMCallDetails] = None,
        tool_details: Optional[ToolCallDetails] = None,
        correctness_score: float = 100.0,
        efficiency_score: float = 100.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> StepRecord:
        """
        结束一个步骤记录

        Args:
            step_id: 步骤 ID
            llm_details: LLM 调用详情
            tool_details: 工具调用详情
            correctness_score: 正确性得分
            efficiency_score: 效率得分
            metadata: 额外元数据

        Returns:
            step: 完成的步骤记录
        """
        if step_id not in self._active_steps:
            raise ValueError(f"步骤 {step_id} 不存在")

        step = self._active_steps[step_id]
        step.timestamp_end = datetime.now()
        step.duration_ms = int((step.timestamp_end - step.timestamp_start).total_seconds() * 1000)
        step.llm_details = llm_details
        step.tool_details = tool_details
        step.correctness_score = correctness_score
        step.efficiency_score = efficiency_score
        step.metadata = metadata or {}

        # 根据详情调整分数
        if llm_details:
            if not llm_details.parameters_valid:
                step.correctness_score -= 20
            if not llm_details.response_parsed_successfully:
                step.correctness_score -= 30
            if llm_details.error_message:
                step.correctness_score -= 10

        if tool_details:
            if not tool_details.parameters_format_correct:
                step.correctness_score -= 20
            if not tool_details.tool_execution_successful:
                step.correctness_score -= 30
            if not tool_details.output_format_valid:
                step.correctness_score -= 10
            if tool_details.error_message:
                step.correctness_score -= 10

        # 确保分数在合理范围内
        step.correctness_score = max(0, min(100, step.correctness_score))
        step.efficiency_score = max(0, min(100, step.efficiency_score))

        # 添加到所属轨迹
        # 这里需要找到对应的轨迹，简化处理：通过 parent_task_id 关联
        # 实际使用时可能需要更复杂的关联逻辑

        # 保存到文件
        self._save_step(step)

        # 从活跃列表中移除
        del self._active_steps[step_id]

        self.logger.debug(
            f"结束步骤：{step_id}, "
            f"耗时：{step.duration_ms}ms, "
            f"正确性：{step.correctness_score}, "
            f"效率：{step.efficiency_score}"
        )

        return step

    def add_step_to_trajectory(
        self,
        step: StepRecord,
        trajectory_id: str
    ) -> None:
        """
        将步骤添加到轨迹中

        Args:
            step: 步骤记录
            trajectory_id: 轨迹 ID
        """
        if trajectory_id in self._active_trajectories:
            self._active_trajectories[trajectory_id].add_step(step)

    def record_llm_call(
        self,
        trajectory_id: str,
        step_name: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        temperature: float,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None,
        response_format: Optional[str] = None,
        prompt_format_correct: bool = True,
        parameters_valid: bool = True,
        response_parsed_successfully: bool = True,
        error_message: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> StepRecord:
        """
        记录一次 LLM 调用

        这是最常用的方法，封装了 start_step 和 end_step

        Args:
            trajectory_id: 轨迹 ID
            step_name: 步骤名称
            model_name: 模型名称
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
            total_tokens: 总 token 数
            temperature: 温度参数
            max_tokens: 最大生成 token 数
            top_p: Top-p 采样参数
            stop_sequences: 停止序列
            response_format: 响应格式
            prompt_format_correct: prompt 格式是否正确
            parameters_valid: 参数是否有效
            response_parsed_successfully: 响应是否成功解析
            error_message: 错误信息
            parent_task_id: 父任务 ID
            metadata: 额外元数据

        Returns:
            step: 步骤记录
        """
        step_id = self.start_step(
            step_type=StepType.LLM_CALL,
            step_name=step_name,
            trajectory_id=trajectory_id,
            parent_task_id=parent_task_id
        )

        llm_details = LLMCallDetails(
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop_sequences=stop_sequences,
            response_format=response_format,
            prompt_format_correct=prompt_format_correct,
            parameters_valid=parameters_valid,
            response_parsed_successfully=response_parsed_successfully,
            error_message=error_message
        )

        step = self.end_step(
            step_id=step_id,
            llm_details=llm_details,
            metadata=metadata
        )

        # 添加到轨迹
        self.add_step_to_trajectory(step, trajectory_id)

        return step

    def record_tool_call(
        self,
        trajectory_id: str,
        step_name: str,
        tool_name: str,
        tool_type: str,
        input_parameters: Dict[str, Any],
        output_result: Any,
        parameters_format_correct: bool = True,
        tool_execution_successful: bool = True,
        output_format_valid: bool = True,
        error_message: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> StepRecord:
        """
        记录一次工具调用

        Args:
            trajectory_id: 轨迹 ID
            step_name: 步骤名称
            tool_name: 工具名称
            tool_type: 工具类型
            input_parameters: 输入参数
            output_result: 输出结果
            parameters_format_correct: 参数格式是否正确
            tool_execution_successful: 工具执行是否成功
            output_format_valid: 输出格式是否有效
            error_message: 错误信息
            parent_task_id: 父任务 ID
            metadata: 额外元数据

        Returns:
            step: 步骤记录
        """
        step_id = self.start_step(
            step_type=StepType.TOOL_CALL,
            step_name=step_name,
            trajectory_id=trajectory_id,
            parent_task_id=parent_task_id
        )

        tool_details = ToolCallDetails(
            tool_name=tool_name,
            tool_type=tool_type,
            input_parameters=input_parameters,
            output_result=output_result,
            parameters_format_correct=parameters_format_correct,
            tool_execution_successful=tool_execution_successful,
            output_format_valid=output_format_valid,
            error_message=error_message
        )

        step = self.end_step(
            step_id=step_id,
            tool_details=tool_details,
            metadata=metadata
        )

        # 添加到轨迹
        self.add_step_to_trajectory(step, trajectory_id)

        return step

    def _save_step(self, step: StepRecord) -> None:
        """保存步骤记录到文件"""
        step_file = self.log_dir / f"step_{step.step_id}.json"
        with open(step_file, 'w', encoding='utf-8') as f:
            json.dump(step.to_dict(), f, ensure_ascii=False, indent=2)

    def _save_trajectory(self, trajectory: TrajectoryRecord) -> None:
        """保存轨迹记录到文件"""
        traj_file = self.log_dir / f"trajectory_{trajectory.trajectory_id}.json"
        with open(traj_file, 'w', encoding='utf-8') as f:
            json.dump(trajectory.to_dict(), f, ensure_ascii=False, indent=2)

    def save_metadata(self) -> None:
        """保存元数据"""
        self.metadata["end_time"] = datetime.now().isoformat()
        metadata_file = self.log_dir / f"metadata_{self.session_id}.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def get_active_trajectories(self) -> List[TrajectoryRecord]:
        """获取所有活跃的轨迹"""
        return list(self._active_trajectories.values())

    def get_completed_trajectories(self) -> List[TrajectoryRecord]:
        """获取所有已完成的轨迹（从文件中读取）"""
        trajectories = []
        for traj_file in self.log_dir.glob("trajectory_*.json"):
            with open(traj_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 这里可以从字典重建 TrajectoryRecord，但为了简单直接返回字典
                trajectories.append(data)
        return trajectories

    def get_all_steps(self) -> List[StepRecord]:
        """获取所有步骤（从文件中读取）"""
        steps = []
        for step_file in self.log_dir.glob("step_*.json"):
            with open(step_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                steps.append(data)
        return steps

    def clear_logs(self) -> None:
        """清除所有日志文件"""
        for file in self.log_dir.glob("*.json"):
            file.unlink()
        for file in self.log_dir.glob("*.log"):
            file.unlink()
        self.logger.info("已清除所有日志文件")


# 便捷函数
def create_evaluator_logger(
    agent_type: str = "writehere",
    log_dir: str = "./evaluation/logs"
) -> EvaluationLogger:
    """
    创建评估日志记录器的便捷函数

    Args:
        agent_type: Agent 类型（"writehere" 或 "mo_shen"）
        log_dir: 日志目录

    Returns:
        EvaluationLogger 实例
    """
    agent_enum = AgentType.WRITEHERE if agent_type == "writehere" else AgentType.MO_SHEN
    return EvaluationLogger(log_dir=log_dir, agent_type=agent_enum)
