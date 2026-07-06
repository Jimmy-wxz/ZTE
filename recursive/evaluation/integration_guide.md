# Agent 评估系统集成指南

本文档说明如何将评估系统集成到 WriteHERE 和 Mo-Shen 两个项目中。

## 目录结构

```
evaluation/
├── __init__.py              # 包初始化
├── models.py                # 数据模型定义
├── logger.py                # 日志记录器
├── evaluator.py             # 评估器核心逻辑
├── schemas/
│   └── evaluation.schema.json  # JSON Schema 定义
├── frontend/
│   └── EvaluationDashboard.js  # React 展示组件
├── logs/                    # 运行时生成的日志目录
├── results/                 # 运行时生成的结果目录
└── integration_guide.md     # 本文件
```

## 快速开始

### 1. 基本使用模式

```python
from evaluation import AgentEvaluator, EvaluationLogger
from evaluation.models import AgentType, TaskStatus

# 创建评估器（以 WriteHERE 为例）
evaluator = AgentEvaluator(
    agent_type=AgentType.WRITEHERE,
    log_dir="./evaluation/logs",
    results_dir="./evaluation/results"
)

# 开始评估会话
evaluator.start_evaluation_session()

# 开始一个任务轨迹
trajectory_id = evaluator.start_trajectory(
    task_id="task_001",
    task_description="生成一篇关于人工智能的技术报告",
    expected_output="2000 字的技术报告"
)

# 在 Agent 执行过程中记录 LLM 调用
step = evaluator.record_llm_call(
    trajectory_id=trajectory_id,
    step_name="规划阶段 - 生成大纲",
    model_name="gpt-4o",
    prompt_tokens=1500,
    completion_tokens=500,
    total_tokens=2000,
    temperature=0.7,
    max_tokens=1000,
    prompt_format_correct=True,
    parameters_valid=True,
    response_parsed_successfully=True
)

# 记录工具调用
tool_step = evaluator.record_tool_call(
    trajectory_id=trajectory_id,
    step_name="搜索相关信息",
    tool_name="bing_search",
    tool_type="search",
    input_parameters={"query": "AI latest developments 2025"},
    output_result={"results": [...]},
    parameters_format_correct=True,
    tool_execution_successful=True,
    output_format_valid=True
)

# 结束轨迹
evaluator.end_trajectory(
    trajectory_id=trajectory_id,
    status=TaskStatus.COMPLETED,
    actual_output="生成的报告内容..."
)

# 生成评估报告
result = evaluator.evaluate_current_session()

# 查看结果
print(f"单步级别得分：{result.overall_step_level_score}")
print(f"轨迹级别得分：{result.overall_trajectory_level_score}")
```

## WriteHERE 集成

### 修改 engine.py

在 `WriteHERE-main/recursive/engine.py` 中添加评估逻辑：

```python
# 在文件开头添加导入
from evaluation import AgentEvaluator
from evaluation.models import AgentType, TaskStatus, StepType

class Engine:
    def __init__(self, ...):
        # ... 现有初始化代码
        
        # 添加评估器
        self.evaluator = AgentEvaluator(
            agent_type=AgentType.WRITEHERE,
            log_dir="./project/evaluation/logs",
            results_dir="./project/evaluation/results"
        )
        
    def run(self, filename, output_filename, done_flag_file, model, mode):
        # 开始评估会话
        self.evaluator.start_evaluation_session()
        
        # ... 现有运行逻辑
        
        # 在每个关键步骤添加记录
        try:
            while not self.is_done():
                # 记录规划步骤
                trajectory_id = self.evaluator.start_trajectory(
                    task_id=f"task_{self.step_count}",
                    task_description=self.current_task.description
                )
                
                # 执行 LLM 调用时记录
                start_time = time.time()
                response = self.llm.call(...)
                duration_ms = int((time.time() - start_time) * 1000)
                
                self.evaluator.record_llm_call(
                    trajectory_id=trajectory_id,
                    step_name=f"LLM Call - {self.current_step.name}",
                    model_name=model,
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens,
                    temperature=self.config.temperature,
                    duration_ms=duration_ms,
                    prompt_format_correct=True,  # 根据实际情况设置
                    parameters_valid=True,
                    response_parsed_successfully=True
                )
                
                # 执行工具调用时记录
                if self.needs_tool_call():
                    tool_start = time.time()
                    tool_result = self.execute_tool(...)
                    tool_duration = int((time.time() - tool_start) * 1000)
                    
                    self.evaluator.record_tool_call(
                        trajectory_id=trajectory_id,
                        step_name=f"Tool Call - {tool.name}",
                        tool_name=tool.name,
                        tool_type=tool.type,
                        input_parameters=tool.input,
                        output_result=tool_result,
                        parameters_format_correct=True,
                        tool_execution_successful=tool_result is not None,
                        output_format_valid=True,
                        duration_ms=tool_duration
                    )
                
                # 结束轨迹
                self.evaluator.end_trajectory(
                    trajectory_id=trajectory_id,
                    status=TaskStatus.COMPLETED if success else TaskStatus.FAILED
                )
                
        finally:
            # 生成评估报告
            result = self.evaluator.evaluate_current_session()
            
            # 保存额外信息
            self.save_evaluation_summary(result)
```

### 修改 agent 基类

在 `WriteHERE-main/recursive/agent/agent_base.py` 中：

```python
class AgentBase:
    def __init__(self, evaluator=None, ...):
        self.evaluator = evaluator
        # ... 其他初始化
        
    def execute_step(self, step):
        """执行单个步骤并记录"""
        if self.evaluator:
            step_start = time.time()
            
        try:
            # ... 现有执行逻辑
            
            if self.evaluator and step.type == StepType.LLM_CALL:
                self.evaluator.record_llm_call(
                    trajectory_id=self.current_trajectory_id,
                    step_name=step.name,
                    model_name=self.model_name,
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens,
                    temperature=self.temperature,
                    prompt_format_correct=self.validate_prompt(step.prompt),
                    parameters_valid=True,
                    response_parsed_successfully=self.parse_response(response)
                )
                
        except Exception as e:
            if self.evaluator:
                # 记录错误
                pass
            raise
```

## Mo-Shen 集成

### 修改 server.py

在 `Mo-Shen-main/storyagents/server.py` 中添加评估逻辑：

```python
# 在文件开头添加导入
from evaluation import AgentEvaluator
from evaluation.models import AgentType, TaskStatus

class StoryAgentsServer:
    def __init__(self, ...):
        # ... 现有初始化代码
        
        # 添加评估器
        self.evaluator = AgentEvaluator(
            agent_type=AgentType.MO_SHEN,
            log_dir="./evaluation/logs",
            results_dir="./evaluation/results"
        )
        
    async def generate_story(self, prompt, chapters, mode):
        """生成故事的 API 端点"""
        
        # 开始评估会话
        eval_session_id = self.evaluator.start_evaluation_session()
        
        try:
            # 根据模式选择工作流
            if mode == "quick":
                result = await self.quick_workflow(prompt, chapters)
            elif mode == "standard":
                result = await self.standard_workflow(prompt, chapters)
            else:  # deep
                result = await self.deep_workflow(prompt, chapters)
            
            # 记录最终结果
            self.evaluator.logger.metadata["output_chapters"] = chapters
            self.evaluator.logger.metadata["workflow_mode"] = mode
            
            return result
            
        finally:
            # 生成评估报告
            result = self.evaluator.evaluate_current_session()
            
            # 可以在这里添加额外的处理
            self.log_evaluation_result(result)
```

### 修改智能体基类

在 `Mo-Shen-main/storyagents/agents/base_agent.py` 中（如果不存在则创建）：

```python
class BaseAgent:
    def __init__(self, llm_client, evaluator=None):
        self.llm_client = llm_client
        self.evaluator = evaluator
        self.current_trajectory_id = None
        
    async def invoke(self, state):
        """调用智能体"""
        if self.evaluator and not self.current_trajectory_id:
            self.current_trajectory_id = self.evaluator.start_trajectory(
                task_id=f"agent_{self.__class__.__name__}_{id(state)}",
                task_description=self.get_description()
            )
        
        try:
            # 记录 LLM 调用
            start_time = time.time()
            response = await self.llm_client.invoke(state)
            duration_ms = int((time.time() - start_time) * 1000)
            
            if self.evaluator:
                self.evaluator.record_llm_call(
                    trajectory_id=self.current_trajectory_id,
                    step_name=f"{self.__class__.__name__}.invoke",
                    model_name=self.llm_client.model_name,
                    prompt_tokens=response.usage_metadata.get('input_tokens', 0),
                    completion_tokens=response.usage_metadata.get('output_tokens', 0),
                    total_tokens=response.usage_metadata.get('total_tokens', 0),
                    temperature=self.temperature,
                    prompt_format_correct=True,
                    parameters_valid=True,
                    response_parsed_successfully=True
                )
            
            return response
            
        except Exception as e:
            if self.evaluator:
                # 记录错误
                pass
            raise
        finally:
            if self.evaluator and self.should_end_trajectory():
                self.evaluator.end_trajectory(
                    trajectory_id=self.current_trajectory_id,
                    status=TaskStatus.COMPLETED
                )
                self.current_trajectory_id = None
```

## 配置选项

### EvaluationConfig 参数说明

```python
from evaluation.models import EvaluationConfig

config = EvaluationConfig(
    # 性能阈值
    max_acceptable_step_duration_ms=5000,  # 最大可接受步骤耗时（毫秒）
    min_efficiency_threshold=70.0,          # 最低效率阈值
    
    # 权重配置（用于计算综合得分）
    llm_call_weight=0.4,                    # LLM 调用权重
    tool_call_weight=0.3,                   # 工具调用权重
    parameter_format_weight=0.2,            # 参数格式权重
    response_parse_weight=0.1,              # 响应解析权重
    
    rationality_weight=0.6,                 # 轨迹合理性权重
    efficiency_weight=0.4,                  # 轨迹效率权重
    
    # 日志配置
    log_level="INFO",                       # 日志级别
    save_raw_logs=True,                     # 保存原始日志
    save_aggregated_stats=True,             # 保存聚合统计
    
    # 输出配置
    output_format="json",                   # 输出格式（json/csv/html）
    output_directory="./evaluation_results" # 输出目录
)

# 使用自定义配置创建评估器
evaluator = AgentEvaluator(
    agent_type=AgentType.WRITEHERE,
    config=config
)
```

## 数据格式

### StepRecord 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| step_id | str | 步骤唯一标识符 |
| timestamp_start | datetime | 开始时间 |
| timestamp_end | datetime | 结束时间 |
| duration_ms | int | 耗时（毫秒） |
| agent_type | AgentType | Agent 类型 |
| step_type | StepType | 步骤类型 |
| step_name | str | 步骤名称 |
| parent_task_id | Optional[str] | 父任务 ID |
| llm_details | Optional[LLMCallDetails] | LLM 调用详情 |
| tool_details | Optional[ToolCallDetails] | 工具调用详情 |
| correctness_score | float | 正确性得分 (0-100) |
| efficiency_score | float | 效率得分 (0-100) |
| metadata | Dict | 额外元数据 |

### TrajectoryRecord 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| trajectory_id | str | 轨迹唯一标识符 |
| task_id | str | 任务唯一标识符 |
| agent_type | AgentType | Agent 类型 |
| start_time | datetime | 开始时间 |
| end_time | Optional[datetime] | 结束时间 |
| status | TaskStatus | 当前状态 |
| steps | List[StepRecord] | 步骤列表 |
| total_duration_ms | int | 总耗时（毫秒） |
| num_llm_calls | int | LLM 调用次数 |
| num_tool_calls | int | 工具调用次数 |
| num_steps | int | 总步骤数 |
| avg_step_duration_ms | float | 平均步骤耗时 |
| success_rate | float | 成功率 (0-100) |
| avg_correctness_score | float | 平均正确性得分 |
| trajectory_rationality_score | float | 轨迹合理性得分 |
| trajectory_efficiency_score | float | 轨迹效率得分 |

## 前端集成

### 在现有项目中添加评估仪表盘

1. **复制组件文件**
   
   将 `EvaluationDashboard.js` 复制到你的前端项目组件目录。

2. **添加到路由**

   ```jsx
   // App.js 或类似文件
   import EvaluationDashboard from './components/EvaluationDashboard';
   
   function App() {
     return (
       <Router>
         <Routes>
           {/* 现有路由 */}
           <Route path="/evaluation" element={<EvaluationDashboard />} />
         </Routes>
       </Router>
     );
   }
   ```

3. **连接后端 API**

   修改组件中的 `loadEvaluations` 函数，使其调用真实的后端 API：

   ```javascript
   useEffect(() => {
     const loadEvaluations = async () => {
       try {
         const response = await fetch('/api/evaluations/latest');
         const data = await response.json();
         
         setWritehereEval(data.writehere);
         setMoShenEval(data.mo_shen);
       } catch (error) {
         console.error('加载失败:', error);
       } finally {
         setLoading(false);
       }
     };
     
     loadEvaluations();
   }, []);
   ```

4. **创建后端 API 端点**

   ```python
   # Flask 示例
   @app.route('/api/evaluations/latest')
   def get_latest_evaluations():
       import json
       from pathlib import Path
       
       results_dir = Path('./evaluation/results')
       
       # 查找最新的评估结果
       writehere_files = sorted(results_dir.glob('eval_writehere_*.json'))
       mo_shen_files = sorted(results_dir.glob('eval_mo_shen_*.json'))
       
       writehere_eval = json.load(open(writehere_files[-1])) if writehere_files else None
       mo_shen_eval = json.load(open(mo_shen_files[-1])) if mo_shen_files else None
       
       return jsonify({
           'writehere': writehere_eval,
           'mo_shen': mo_shen_eval
       })
   ```

## 最佳实践

### 1. 日志管理

```python
# 定期清理旧日志
import shutil
from datetime import datetime, timedelta

def cleanup_old_logs(days=7):
    """清理超过指定天数的日志"""
    cutoff = datetime.now() - timedelta(days=days)
    
    for log_file in Path('./evaluation/logs').glob('*.json'):
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        if mtime < cutoff:
            log_file.unlink()
```

### 2. 性能监控

```python
# 添加性能指标收集
import psutil

def record_system_metrics(evaluator, trajectory_id):
    """记录系统指标"""
    evaluator.record_tool_call(
        trajectory_id=trajectory_id,
        step_name="System Metrics",
        tool_name="system_monitor",
        tool_type="monitoring",
        input_parameters={},
        output_result={
            'cpu_percent': psutil.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('/').percent
        },
        parameters_format_correct=True,
        tool_execution_successful=True,
        output_format_valid=True
    )
```

### 3. 批量评估

```python
# 对多个任务进行批量评估
def batch_evaluate(evaluator, tasks):
    """批量评估多个任务"""
    all_results = []
    
    for i, task in enumerate(tasks):
        evaluator.start_evaluation_session()
        
        trajectory_id = evaluator.start_trajectory(
            task_id=f"batch_{i}",
            task_description=task['description']
        )
        
        # 执行任务...
        
        evaluator.end_trajectory(
            trajectory_id=trajectory_id,
            status=TaskStatus.COMPLETED
        )
        
        result = evaluator.evaluate_current_session()
        all_results.append(result)
    
    # 生成汇总报告
    generate_summary_report(all_results)
```

## 故障排除

### 常见问题

1. **日志文件过大**
   
   解决：启用日志轮转或定期清理
   ```python
   # 在 logger.py 中添加大小限制
   MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
   
   def _check_log_size(self):
       if self.log_file.exists() and self.log_file.stat().st_size > MAX_LOG_SIZE:
           # 轮转日志
           self.log_file.rename(self.log_file.with_suffix('.log.1'))
   ```

2. **评估影响性能**
   
   解决：异步记录或使用采样
   ```python
   # 只对一定比例的步骤进行详细记录
   import random
   
   if random.random() < 0.1:  # 10% 采样率
       evaluator.record_llm_call(...)
   ```

3. **数据不一致**
   
   确保在所有异常路径都调用 `end_trajectory()`，使用 try-finally 块：
   ```python
   try:
       trajectory_id = evaluator.start_trajectory(...)
       # 执行操作...
   finally:
       evaluator.end_trajectory(trajectory_id, status)
   ```

## 下一步

完成集成后：

1. 在网页上进行测试
2. 收集实际运行数据
3. 进行第三步的任务完成度评估（手动）
4. 对比两个 Agent 的综合表现

祝评估顺利！
