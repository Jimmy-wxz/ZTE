"""
评估器核心模块

提供单步评估和轨迹评估的评分逻辑
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

from .models import (
    StepRecord,
    TrajectoryRecord,
    EvaluationResult,
    EvaluationConfig,
    LLMCallDetails,
    ToolCallDetails,
    StepType,
    AgentType,
    TaskStatus
)
from .logger import EvaluationLogger


class StepEvaluator:
    """
    单步评估器

    负责评估单个步骤（LLM 调用或工具调用）的正确性和效率
    """

    def __init__(self, config: Optional[EvaluationConfig] = None):
        """
        初始化单步评估器

        Args:
            config: 评估配置
        """
        self.config = config or EvaluationConfig()

    def evaluate_llm_call(self, step: StepRecord) -> Tuple[float, float, Dict[str, Any]]:
        """
        评估 LLM 调用步骤

        Args:
            step: LLM 调用的步骤记录

        Returns:
            (correctness_score, efficiency_score, details)
        """
        if not step.llm_details:
            raise ValueError("步骤不是 LLM 调用类型")

        details = step.llm_details
        correctness_score = 100.0
        efficiency_score = 100.0

        # === 正确性评估 ===

        # 1. Prompt 格式正确性（权重：25%）
        if not details.prompt_format_correct:
            correctness_score -= 25

        # 2. 参数有效性（权重：25%）
        if not details.parameters_valid:
            correctness_score -= 25

        # 3. 响应解析成功（权重：30%）
        if not details.response_parsed_successfully:
            correctness_score -= 30

        # 4. 错误信息（权重：20%）
        if details.error_message:
            correctness_score -= 20

        # === 效率评估 ===

        # 基于耗时评估效率
        duration_ms = step.duration_ms
        if duration_ms > self.config.max_acceptable_step_duration_ms * 2:
            efficiency_score = 50.0
        elif duration_ms > self.config.max_acceptable_step_duration_ms:
            efficiency_score = 70.0
        elif duration_ms > self.config.max_acceptable_step_duration_ms * 0.5:
            efficiency_score = 90.0

        # 基于 token 使用效率
        if details.total_tokens > 0:
            # 输出/输入比率，过高可能表示冗余
            output_input_ratio = details.completion_tokens / max(details.prompt_tokens, 1)
            if output_input_ratio > 2.0:  # 输出远多于输入，可能不够简洁
                efficiency_score *= 0.9
            elif output_input_ratio < 0.1:  # 输出过少，可能没有充分响应
                efficiency_score *= 0.95

        # 确保分数在合理范围内
        correctness_score = max(0, min(100, correctness_score))
        efficiency_score = max(0, min(100, efficiency_score))

        evaluation_details = {
            "prompt_format_correct": details.prompt_format_correct,
            "parameters_valid": details.parameters_valid,
            "response_parsed_successfully": details.response_parsed_successfully,
            "has_error": bool(details.error_message),
            "duration_ms": duration_ms,
            "token_efficiency": output_input_ratio if details.total_tokens > 0 else None
        }

        return correctness_score, efficiency_score, evaluation_details

    def evaluate_tool_call(self, step: StepRecord) -> Tuple[float, float, Dict[str, Any]]:
        """
        评估工具调用步骤

        Args:
            step: 工具调用的步骤记录

        Returns:
            (correctness_score, efficiency_score, details)
        """
        if not step.tool_details:
            raise ValueError("步骤不是工具调用类型")

        details = step.tool_details
        correctness_score = 100.0
        efficiency_score = 100.0

        # === 正确性评估 ===

        # 1. 参数格式正确性（权重：30%）
        if not details.parameters_format_correct:
            correctness_score -= 30

        # 2. 工具执行成功（权重：40%）
        if not details.tool_execution_successful:
            correctness_score -= 40

        # 3. 输出格式有效（权重：20%）
        if not details.output_format_valid:
            correctness_score -= 20

        # 4. 错误信息（权重：10%）
        if details.error_message:
            correctness_score -= 10

        # === 效率评估 ===

        duration_ms = step.duration_ms
        if duration_ms > self.config.max_acceptable_step_duration_ms * 3:
            efficiency_score = 50.0
        elif duration_ms > self.config.max_acceptable_step_duration_ms:
            efficiency_score = 70.0
        elif duration_ms > self.config.max_acceptable_step_duration_ms * 0.5:
            efficiency_score = 90.0

        # 确保分数在合理范围内
        correctness_score = max(0, min(100, correctness_score))
        efficiency_score = max(0, min(100, efficiency_score))

        evaluation_details = {
            "parameters_format_correct": details.parameters_format_correct,
            "tool_execution_successful": details.tool_execution_successful,
            "output_format_valid": details.output_format_valid,
            "has_error": bool(details.error_message),
            "duration_ms": duration_ms
        }

        return correctness_score, efficiency_score, evaluation_details

    def evaluate_step(self, step: StepRecord) -> Tuple[float, float, Dict[str, Any]]:
        """
        评估一个步骤

        Args:
            step: 步骤记录

        Returns:
            (correctness_score, efficiency_score, details)
        """
        if step.step_type == StepType.LLM_CALL:
            return self.evaluate_llm_call(step)
        elif step.step_type == StepType.TOOL_CALL:
            return self.evaluate_tool_call(step)
        else:
            # 其他类型步骤，返回默认分数
            return 100.0, 100.0, {"step_type": step.step_type.value}


class TrajectoryEvaluator:
    """
    轨迹评估器

    负责评估整个执行轨迹的合理性和效率
    """

    def __init__(self, config: Optional[EvaluationConfig] = None):
        """
        初始化轨迹评估器

        Args:
            config: 评估配置
        """
        self.config = config or EvaluationConfig()
        self.step_evaluator = StepEvaluator(config)

    def evaluate_rationality_dict(self, traj_data: Dict) -> Tuple[float, Dict[str, Any]]:
        """评估轨迹合理性（字典版本）"""
        # 将字典转换为临时对象
        class TempTrajectory:
            def __init__(self, data):
                self.__dict__.update(data)
                self.steps = [type('obj', (object,), s)() for s in data.get('steps', [])]

        temp_traj = TempTrajectory(traj_data)
        return self.evaluate_rationality(temp_traj)

    def evaluate_rationality(self, trajectory) -> Tuple[float, Dict[str, Any]]:
        """
        评估轨迹的合理性

        合理性关注点：
        1. 步骤顺序是否合理
        2. 是否有不必要的重复
        3. 错误处理是否得当
        4. 资源使用是否合理

        Args:
            trajectory: 轨迹记录（TrajectoryRecord 对象或字典）

        Returns:
            (rationality_score, details)
        """
        rationality_score = 100.0
        details = {
            "issues": [],
            "warnings": []
        }

        # 处理 TrajectoryRecord 对象或字典
        if hasattr(trajectory, 'steps'):
            steps = trajectory.steps
            traj_status = trajectory.status.value if hasattr(trajectory.status, 'value') else trajectory.status
            get_attr = lambda s, attr, default=None: getattr(s, attr, default)
        else:
            steps = trajectory.get('steps', [])
            traj_status = trajectory.get('status', TaskStatus.COMPLETED.value)
            get_attr = lambda s, attr, default=None: s.get(attr, default) if isinstance(s, dict) else getattr(s, attr, default)

        if len(steps) == 0:
            return 0.0, {"error": "轨迹中没有步骤"}

        # === 检查项 1: 成功率 ===
        failed_steps = sum(1 for s in steps if get_attr(s, 'correctness_score', 100) < 60)
        failure_rate = failed_steps / len(steps)
        if failure_rate > 0.3:
            rationality_score -= 30
            details["issues"].append(f"失败步骤比例过高：{failure_rate:.1%}")
        elif failure_rate > 0.1:
            rationality_score -= 15
            details["warnings"].append(f"存在一定比例的失败步骤：{failure_rate:.1%}")

        # === 检查项 2: 步骤冗余度 ===
        # 检查是否有连续相同类型的步骤（可能表示重试或冗余）
        consecutive_same_type = 0
        max_consecutive_same_type = 0
        for i in range(1, len(steps)):
            step_i_type = get_attr(steps[i], 'step_type', '')
            step_prev_type = get_attr(steps[i-1], 'step_type', '')
            # 处理枚举值
            if hasattr(step_i_type, 'value'):
                step_i_type = step_i_type.value
            if hasattr(step_prev_type, 'value'):
                step_prev_type = step_prev_type.value
            if step_i_type == step_prev_type:
                consecutive_same_type += 1
                max_consecutive_same_type = max(max_consecutive_same_type, consecutive_same_type)
            else:
                consecutive_same_type = 0

        if max_consecutive_same_type >= 3:
            rationality_score -= 10
            details["warnings"].append(f"检测到连续 {max_consecutive_same_type + 1} 个相同类型的步骤，可能存在冗余")

        # === 检查项 3: LLM 与工具调用的平衡 ===
        def is_step_type(step, target_type):
            """检查步骤类型（兼容对象和字典）"""
            if isinstance(step, dict):
                return step.get('step_type') == target_type
            step_t = getattr(step, 'step_type', None)
            if hasattr(step_t, 'value'):
                return step_t.value == target_type
            return step_t == target_type

        llm_calls = sum(1 for s in steps if is_step_type(s, StepType.LLM_CALL.value))
        tool_calls = sum(1 for s in steps if is_step_type(s, StepType.TOOL_CALL.value))

        if llm_calls > 0 and tool_calls > 0:
            ratio = tool_calls / llm_calls
            # 理想的 LLM:工具调用比例因任务而异，这里做一个宽松的评估
            if ratio > 3.0 or ratio < 0.2:
                rationality_score -= 5
                details["warnings"].append(f"LLM 调用与工具调用比例失衡：{ratio:.2f}")

        # === 检查项 4: 异常步骤检测 ===
        # 检测耗时异常的步骤
        durations = [get_attr(s, 'duration_ms', 0) for s in steps]
        avg_duration = sum(durations) / len(durations) if durations else 0
        outlier_threshold = avg_duration * 5  # 超过平均 5 倍视为异常

        outliers = [d for d in durations if d > outlier_threshold]
        if len(outliers) > 0:
            rationality_score -= 5 * len(outliers)
            details["warnings"].append(f"检测到 {len(outliers)} 个耗时异常的步骤")

        # === 检查项 5: 轨迹完整性 ===
        if traj_status != TaskStatus.COMPLETED.value:
            rationality_score -= 20
            details["issues"].append(f"轨迹未正常完成，状态：{traj_status}")

        # 确保分数在合理范围内
        rationality_score = max(0, min(100, rationality_score))

        return rationality_score, details

    def evaluate_efficiency_dict(self, traj_data: Dict) -> Tuple[float, Dict[str, Any]]:
        """评估轨迹效率（字典版本）"""
        return self.evaluate_efficiency(type('obj', (object,), traj_data)())

    def evaluate_trajectory_dict(self, traj_data: Dict) -> Tuple[float, float, Dict[str, Any]]:
        """综合评估轨迹（字典版本）"""
        rat_score, rat_details = self.evaluate_rationality_dict(traj_data)
        eff_score, eff_details = self.evaluate_efficiency_dict(traj_data)
        return rat_score, eff_score, {"rationality": rat_details, "efficiency": eff_details}

    def evaluate_efficiency(self, trajectory) -> Tuple[float, Dict[str, Any]]:
        """
        评估轨迹的效率

        效率关注点：
        1. 总耗时
        2. 步骤数量
        3. 资源利用率
        4. 并行化程度（如果适用）

        Args:
            trajectory: 轨迹记录

        Returns:
            (efficiency_score, details)
        """
        efficiency_score = 100.0
        details = {}

        steps = trajectory.steps

        if len(steps) == 0:
            return 0.0, {"error": "轨迹中没有步骤"}

        # === 指标 1: 总耗时 ===
        total_duration_s = trajectory.total_duration_ms / 1000.0

        # 根据任务复杂度设定不同的阈值
        if len(steps) <= 5:
            # 简单任务应该在 30 秒内完成
            if total_duration_s > 60:
                efficiency_score -= 30
            elif total_duration_s > 30:
                efficiency_score -= 15
        elif len(steps) <= 15:
            # 中等任务应该在 2 分钟内完成
            if total_duration_s > 180:
                efficiency_score -= 30
            elif total_duration_s > 120:
                efficiency_score -= 15
        else:
            # 复杂任务应该在 5 分钟内完成
            if total_duration_s > 360:
                efficiency_score -= 30
            elif total_duration_s > 300:
                efficiency_score -= 15

        details["total_duration_s"] = total_duration_s

        # === 指标 2: 步骤效率 ===
        # 每个步骤的平均耗时
        avg_step_duration = trajectory.avg_step_duration_ms
        if avg_step_duration > self.config.max_acceptable_step_duration_ms:
            efficiency_score -= 20
            details["avg_step_duration_issue"] = True
        else:
            details["avg_step_duration_ok"] = True

        # === 指标 3: Token 使用效率（如果有 LLM 调用）===
        def is_llm_step(s):
            if isinstance(s, dict):
                return s.get('step_type') == StepType.LLM_CALL.value
            st = getattr(s, 'step_type', None)
            if hasattr(st, 'value'):
                return st.value == StepType.LLM_CALL.value
            return st == StepType.LLM_CALL

        llm_steps = [s for s in steps if is_llm_step(s)]
        if llm_steps:
            total_tokens = sum(
                s.get('llm_details', {}).get('total_tokens', 0) if isinstance(s, dict)
                else (s.llm_details.total_tokens if s.llm_details else 0)
                for s in llm_steps
            )
            avg_tokens_per_step = total_tokens / len(llm_steps)

            # 假设平均每步 1000 tokens 是合理的
            if avg_tokens_per_step > 5000:
                efficiency_score -= 15
                details["high_token_usage"] = True
            elif avg_tokens_per_step > 2000:
                efficiency_score -= 5
                details["moderate_token_usage"] = True
            else:
                details["good_token_usage"] = True

            details["total_tokens"] = total_tokens
            details["avg_tokens_per_step"] = avg_tokens_per_step

        # === 指标 4: 步骤数量合理性 ===
        num_steps = len(steps)
        if num_steps > 20:
            efficiency_score -= 10
            details["many_steps"] = True
        elif num_steps > 10:
            details["moderate_steps"] = True
        else:
            details["few_steps"] = True

        # 确保分数在合理范围内
        efficiency_score = max(0, min(100, efficiency_score))

        return efficiency_score, details

    def evaluate_trajectory(
        self,
        trajectory: TrajectoryRecord
    ) -> Tuple[float, float, Dict[str, Any]]:
        """
        综合评估轨迹

        Args:
            trajectory: 轨迹记录

        Returns:
            (rationality_score, efficiency_score, details)
        """
        rationality_score, rat_details = self.evaluate_rationality(trajectory)
        efficiency_score, eff_details = self.evaluate_efficiency(trajectory)

        details = {
            "rationality": rat_details,
            "efficiency": eff_details
        }

        return rationality_score, efficiency_score, details


class AgentEvaluator:
    """
    Agent 评估器

    整合单步评估和轨迹评估，提供完整的评估功能
    """

    def __init__(
        self,
        agent_type: AgentType,
        config: Optional[EvaluationConfig] = None,
        log_dir: str = "./evaluation/logs",
        results_dir: str = "./evaluation/results"
    ):
        """
        初始化 Agent 评估器

        Args:
            agent_type: Agent 类型
            config: 评估配置
            log_dir: 日志目录
            results_dir: 结果目录
        """
        self.agent_type = agent_type
        self.config = config or EvaluationConfig()
        self.log_dir = Path(log_dir)
        self.results_dir = Path(results_dir)

        # 创建目录
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # 初始化组件
        self.logger = EvaluationLogger(
            log_dir=str(self.log_dir),
            agent_type=agent_type
        )
        self.step_evaluator = StepEvaluator(self.config)
        self.trajectory_evaluator = TrajectoryEvaluator(self.config)

        # 当前评估会话
        self._current_evaluation_id: Optional[str] = None
        self._trajectories: List[TrajectoryRecord] = []

    def start_evaluation_session(self) -> str:
        """
        开始一个新的评估会话

        Returns:
            evaluation_id: 评估会话 ID
        """
        self._current_evaluation_id = f"eval_{self.agent_type.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._trajectories = []
        return self._current_evaluation_id

    def record_llm_call(
        self,
        trajectory_id: str,
        step_name: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        temperature: float,
        **kwargs
    ) -> StepRecord:
        """
        记录一次 LLM 调用

        这是主要的接口方法，供 Agent 在执行过程中调用
        """
        return self.logger.record_llm_call(
            trajectory_id=trajectory_id,
            step_name=step_name,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            temperature=temperature,
            **kwargs
        )

    def record_tool_call(
        self,
        trajectory_id: str,
        step_name: str,
        tool_name: str,
        tool_type: str,
        input_parameters: Dict[str, Any],
        output_result: Any,
        **kwargs
    ) -> StepRecord:
        """
        记录一次工具调用

        这是主要的接口方法，供 Agent 在执行过程中调用
        """
        return self.logger.record_tool_call(
            trajectory_id=trajectory_id,
            step_name=step_name,
            tool_name=tool_name,
            tool_type=tool_type,
            input_parameters=input_parameters,
            output_result=output_result,
            **kwargs
        )

    def start_trajectory(
        self,
        task_id: str,
        task_description: Optional[str] = None,
        expected_output: Optional[str] = None
    ) -> str:
        """开始一个新的轨迹"""
        return self.logger.start_trajectory(
            task_id=task_id,
            task_description=task_description,
            expected_output=expected_output
        )

    def end_trajectory(
        self,
        trajectory_id: str,
        status: TaskStatus = TaskStatus.COMPLETED,
        actual_output: Optional[str] = None
    ) -> TrajectoryRecord:
        """结束一个轨迹"""
        return self.logger.end_trajectory(
            trajectory_id=trajectory_id,
            status=status,
            actual_output=actual_output
        )

    def evaluate_current_session(self) -> EvaluationResult:
        """
        评估当前会话

        Returns:
            EvaluationResult: 评估结果
        """
        if not self._current_evaluation_id:
            raise ValueError("尚未开始评估会话，请先调用 start_evaluation_session()")

        # 从日志中读取所有轨迹
        trajectories_data = self.logger.get_completed_trajectories()

        # 转换为 TrajectoryRecord 对象并进行评估
        trajectories = []
        total_rationality = 0.0
        total_efficiency = 0.0
        total_duration = 0
        total_steps = 0
        successful_trajectories = 0

        all_steps = []

        for traj_data in trajectories_data:
            # 使用字典数据进行评估（从 JSON 读取的是字典）

            # 评估轨迹
            rat_score, eff_score, _ = self.trajectory_evaluator.evaluate_trajectory_dict(traj_data)

            total_rationality += rat_score
            total_efficiency += eff_score
            total_duration += traj_data.get('total_duration_ms', 0)
            total_steps += traj_data.get('num_steps', 0)

            if traj_data.get('status') == TaskStatus.COMPLETED.value:
                successful_trajectories += 1

            # 收集所有步骤
            all_steps.extend(traj_data.get('steps', []))

        num_trajectories = len(trajectories_data)

        # 计算单步级别的指标
        llm_calls = [s for s in all_steps if s.get('step_type') == StepType.LLM_CALL.value]
        tool_calls = [s for s in all_steps if s.get('step_type') == StepType.TOOL_CALL.value]

        # LLM 调用准确率
        llm_accurate = sum(
            1 for s in llm_calls
            if s.get('llm_details', {}).get('parameters_valid', True) and
               s.get('llm_details', {}).get('response_parsed_successfully', True)
        )
        llm_accuracy = llm_accurate / len(llm_calls) * 100 if llm_calls else 100.0

        # 工具调用准确率
        tool_accurate = sum(
            1 for s in tool_calls
            if s.get('tool_details', {}).get('tool_execution_successful', True)
        )
        tool_accuracy = tool_accurate / len(tool_calls) * 100 if tool_calls else 100.0

        # 参数格式准确率
        param_accurate = 0
        param_total = 0
        for s in all_steps:
            llm_det = s.get('llm_details')
            tool_det = s.get('tool_details')
            if llm_det:
                param_total += 1
                if llm_det.get('parameters_valid', True):
                    param_accurate += 1
            if tool_det:
                param_total += 1
                if tool_det.get('parameters_format_correct', True):
                    param_accurate += 1
        param_accuracy = param_accurate / param_total * 100 if param_total else 100.0

        # 响应解析准确率
        parse_accurate = 0
        parse_total = 0
        for s in all_steps:
            llm_det = s.get('llm_details')
            if llm_det:
                parse_total += 1
                if llm_det.get('response_parsed_successfully', True):
                    parse_accurate += 1
        parse_accuracy = parse_accurate / parse_total * 100 if parse_total else 100.0

        # 计算综合得分
        overall_step_score = (
            llm_accuracy * self.config.llm_call_weight +
            tool_accuracy * self.config.tool_call_weight +
            param_accuracy * self.config.parameter_format_weight +
            parse_accuracy * self.config.response_parse_weight
        )

        overall_trajectory_score = (
            (total_rationality / num_trajectories * self.config.rationality_weight) +
            (total_efficiency / num_trajectories * self.config.efficiency_weight)
        ) if num_trajectories > 0 else 0.0

        # 创建评估结果
        result = EvaluationResult(
            evaluation_id=self._current_evaluation_id,
            agent_type=self.agent_type,
            evaluation_timestamp=datetime.now(),
            total_steps_evaluated=len(all_steps),
            llm_call_accuracy=llm_accuracy,
            tool_call_accuracy=tool_accuracy,
            parameter_format_accuracy=param_accuracy,
            response_parse_accuracy=parse_accuracy,
            total_trajectories=num_trajectories,
            avg_trajectory_duration_ms=total_duration / num_trajectories if num_trajectories else 0,
            avg_steps_per_trajectory=total_steps / num_trajectories if num_trajectories else 0,
            trajectory_success_rate=successful_trajectories / num_trajectories * 100 if num_trajectories else 0,
            avg_rationality_score=total_rationality / num_trajectories if num_trajectories else 0,
            avg_efficiency_score=total_efficiency / num_trajectories if num_trajectories else 0,
            overall_step_level_score=overall_step_score,
            overall_trajectory_level_score=overall_trajectory_score
        )

        # 生成详细报告
        result.detailed_report = self._generate_detailed_report(all_steps, trajectories_data)

        # 识别问题和改进建议
        result.identified_issues, result.improvement_suggestions = \
            self._identify_issues_and_suggestions(result)

        # 保存评估结果
        self._save_evaluation_result(result)

        return result

    def _generate_detailed_report(
        self,
        steps: List[Dict],
        trajectories: List[Dict]
    ) -> Dict[str, Any]:
        """生成详细报告"""
        report = {
            "summary": {
                "total_steps": len(steps),
                "total_trajectories": len(trajectories),
                "llm_calls": len([s for s in steps if s.get('step_type') == StepType.LLM_CALL.value]),
                "tool_calls": len([s for s in steps if s.get('step_type') == StepType.TOOL_CALL.value])
            },
            "step_distribution": {},
            "performance_metrics": {},
            "error_analysis": {
                "llm_errors": [],
                "tool_errors": []
            }
        }

        # 步骤分布
        for step_type in StepType:
            count = len([s for s in steps if s.get('step_type') == step_type.value])
            report["step_distribution"][step_type.value] = count

        # 性能指标
        if steps:
            durations = [s.get('duration_ms', 0) for s in steps]
            report["performance_metrics"]["avg_duration_ms"] = sum(durations) / len(durations)
            report["performance_metrics"]["max_duration_ms"] = max(durations)
            report["performance_metrics"]["min_duration_ms"] = min(durations)

        # 错误分析
        for step in steps:
            if step.get('step_type') == StepType.LLM_CALL.value:
                llm_details = step.get('llm_details', {})
                if llm_details.get('error_message'):
                    report["error_analysis"]["llm_errors"].append({
                        "step_id": step.get('step_id'),
                        "error": llm_details.get('error_message')
                    })
            elif step.get('step_type') == StepType.TOOL_CALL.value:
                tool_details = step.get('tool_details', {})
                if tool_details.get('error_message'):
                    report["error_analysis"]["tool_errors"].append({
                        "step_id": step.get('step_id'),
                        "error": tool_details.get('error_message')
                    })

        return report

    def _identify_issues_and_suggestions(
        self,
        result: EvaluationResult
    ) -> Tuple[List[str], List[str]]:
        """识别问题和改进建议"""
        issues = []
        suggestions = []

        # 检查 LLM 调用准确率
        if result.llm_call_accuracy < 90:
            issues.append(f"LLM 调用准确率较低：{result.llm_call_accuracy:.1f}%")
            suggestions.append("检查 LLM 调用的参数设置和 prompt 格式")

        # 检查工具调用准确率
        if result.tool_call_accuracy < 90:
            issues.append(f"工具调用准确率较低：{result.tool_call_accuracy:.1f}%")
            suggestions.append("验证工具调用的参数格式和错误处理逻辑")

        # 检查轨迹成功率
        if result.trajectory_success_rate < 80:
            issues.append(f"轨迹成功率较低：{result.trajectory_success_rate:.1f}%")
            suggestions.append("分析失败轨迹的共同特征，优化错误恢复机制")

        # 检查平均耗时
        if result.avg_trajectory_duration_ms > 60000:  # 1 分钟
            issues.append(f"平均轨迹耗时较长：{result.avg_trajectory_duration_ms/1000:.1f}秒")
            suggestions.append("考虑优化长耗时步骤，或引入并行执行机制")

        # 检查合理性得分
        if result.avg_rationality_score < 80:
            issues.append(f"轨迹合理性得分较低：{result.avg_rationality_score:.1f}")
            suggestions.append("审查执行流程，减少不必要的步骤和重试")

        # 检查效率得分
        if result.avg_efficiency_score < 70:
            issues.append(f"轨迹效率得分较低：{result.avg_efficiency_score:.1f}")
            suggestions.append("优化资源使用，减少冗余操作")

        return issues, suggestions

    def _save_evaluation_result(self, result: EvaluationResult) -> None:
        """保存评估结果"""
        result_file = self.results_dir / f"{result.evaluation_id}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

        # 同时保存为人类可读的格式
        report_file = self.results_dir / f"{result.evaluation_id}_report.md"
        self._save_markdown_report(result, report_file)

    def _save_markdown_report(
        self,
        result: EvaluationResult,
        filepath: Path
    ) -> None:
        """保存 Markdown 格式的评估报告"""
        md_content = f"""# Agent 评估报告

## 基本信息
- **评估 ID**: {result.evaluation_id}
- **Agent 类型**: {result.agent_type.value}
- **评估时间**: {result.evaluation_timestamp.strftime('%Y-%m-%d %H:%M:%S')}

## 单步级别评估

### 总体得分
- **综合得分**: {result.overall_step_level_score:.1f}/100

### 详细指标
| 指标 | 得分 |
|------|------|
| LLM 调用准确率 | {result.llm_call_accuracy:.1f}% |
| 工具调用准确率 | {result.tool_call_accuracy:.1f}% |
| 参数格式准确率 | {result.parameter_format_accuracy:.1f}% |
| 响应解析准确率 | {result.response_parse_accuracy:.1f}% |

### 统计信息
- 评估步骤总数：{result.total_steps_evaluated}

## 轨迹级别评估

### 总体得分
- **综合得分**: {result.overall_trajectory_level_score:.1f}/100

### 详细指标
| 指标 | 得分 |
|------|------|
| 平均合理性得分 | {result.avg_rationality_score:.1f} |
| 平均效率得分 | {result.avg_efficiency_score:.1f} |

### 统计信息
| 指标 | 数值 |
|------|------|
| 轨迹总数 | {result.total_trajectories} |
| 轨迹成功率 | {result.trajectory_success_rate:.1f}% |
| 平均轨迹耗时 | {result.avg_trajectory_duration_ms/1000:.1f}秒 |
| 平均每轨迹步骤数 | {result.avg_steps_per_trajectory:.1f} |

## 问题与建议

### 已识别的问题
{chr(10).join('- ' + issue for issue in result.identified_issues) if result.identified_issues else '暂无'}

### 改进建议
{chr(10).join('- ' + suggestion for suggestion in result.improvement_suggestions) if result.improvement_suggestions else '暂无'}

---
*报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md_content)
