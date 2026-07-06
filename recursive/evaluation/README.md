# 🎯 Agent 能力评估系统

企业文档生产 Agent 评估框架，用于追踪和评估 WriteHERE 和 Mo-Shen 两个 Agent 的执行过程。

## 📋 评估标准

本系统采用三级评估标准：

### 1. 单步评估 (Step-level Evaluation)

评估每个独立操作步骤的正确性和效率：

- **LLM 调用正确性**
  - Prompt 格式是否正确
  - 参数是否有效
  - 响应是否成功解析
  
- **工具调用正确性**
  - 参数格式是否正确
  - 工具执行是否成功
  - 输出格式是否有效

- **效率指标**
  - 步骤耗时
  - Token 使用效率

### 2. 轨迹评估 (Trajectory-level Evaluation)

评估整个执行链路的合理性和效率：

- **合理性**
  - 步骤顺序是否合理
  - 是否有不必要的重复
  - 错误处理是否得当
  - 资源使用是否合理

- **效率**
  - 总耗时
  - 步骤数量
  - 并行化程度

### 3. 任务完成度评估 (Task Completion Evaluation)

*注：此级别需要手动评估*

- 最终输出质量
- 需求满足程度
- 内容准确性
- 创造性与连贯性

## 🚀 快速开始

### 安装

```bash
# Python 3.7+
pip install -e .

# Python 3.6 需要额外安装 dataclasses
pip install dataclasses
```

### 基本使用

```python
from evaluation import AgentEvaluator
from evaluation.models import AgentType, TaskStatus

# 创建评估器
evaluator = AgentEvaluator(
    agent_type=AgentType.WRITEHERE,  # 或 MO_SHEN
    log_dir="./logs",
    results_dir="./results"
)

# 开始评估会话
evaluator.start_evaluation_session()

# 开始记录一个任务轨迹
trajectory_id = evaluator.start_trajectory(
    task_id="task_001",
    task_description="生成技术报告",
    expected_output="2000 字的报告"
)

# 记录 LLM 调用
evaluator.record_llm_call(
    trajectory_id=trajectory_id,
    step_name="生成大纲",
    model_name="gpt-4o",
    prompt_tokens=1000,
    completion_tokens=500,
    total_tokens=1500,
    temperature=0.7,
    prompt_format_correct=True,
    parameters_valid=True,
    response_parsed_successfully=True
)

# 记录工具调用
evaluator.record_tool_call(
    trajectory_id=trajectory_id,
    step_name="搜索信息",
    tool_name="bing_search",
    tool_type="search",
    input_parameters={"query": "AI trends 2025"},
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

### 运行示例

```bash
# 运行完整演示
python evaluation/example_usage.py

# 查看生成的日志
ls evaluation/logs/
ls evaluation/results/
```

## 📁 目录结构

```
evaluation/
├── __init__.py              # 包初始化
├── models.py                # 数据模型定义
├── logger.py                # 日志记录器
├── evaluator.py             # 评估器核心逻辑
├── example_usage.py         # 使用示例
├── integration_guide.md     # 集成指南
├── README.md                # 本文件
├── schemas/
│   └── evaluation.schema.json  # JSON Schema 定义
├── frontend/
│   └── EvaluationDashboard.js  # React 展示组件
├── logs/                    # 运行时日志（自动生成）
│   ├── writehere/          # WriteHERE 日志
│   ├── mo_shen/            # Mo-Shen 日志
│   └── test/               # 测试日志
└── results/                 # 评估结果（自动生成）
    ├── writehere/          # WriteHERE 结果
    ├── mo_shen/            # Mo-Shen 结果
    └── test/               # 测试结果
```

## 📊 输出格式

### JSON 评估结果

每个评估会话生成一个 JSON 文件，包含：

```json
{
  "evaluation_id": "eval_writehere_20260624_143022",
  "agent_type": "writehere",
  "overall_step_level_score": 87.5,
  "overall_trajectory_level_score": 82.3,
  "llm_call_accuracy": 92.0,
  "tool_call_accuracy": 88.5,
  "avg_rationality_score": 85.0,
  "avg_efficiency_score": 79.6,
  "trajectories": [...],
  "identified_issues": ["部分轨迹耗时较长"],
  "improvement_suggestions": ["优化长耗时步骤"]
}
```

### Markdown 报告

同时生成人类可读的 Markdown 报告：

```markdown
# Agent 评估报告

## 基本信息
- 评估 ID: eval_writehere_20260624_143022
- Agent 类型: writehere
- 评估时间: 2026-06-24 14:30:22

## 单步级别评估
| 指标 | 得分 |
|------|------|
| LLM 调用准确率 | 92.0% |
| 工具调用准确率 | 88.5% |

## 轨迹级别评估
| 指标 | 得分 |
|------|------|
| 平均合理性得分 | 85.0 |
| 平均效率得分 | 79.6 |

## 问题与建议
- ⚠️ 部分轨迹耗时较长
- 💡 优化长耗时步骤
```

## 🔌 集成到现有项目

### WriteHERE 集成

在 `WriteHERE-main/recursive/engine.py` 中：

```python
from evaluation import AgentEvaluator
from evaluation.models import AgentType

class Engine:
    def __init__(self):
        self.evaluator = AgentEvaluator(
            agent_type=AgentType.WRITEHERE,
            log_dir="./project/evaluation/logs"
        )
    
    def run(self, ...):
        self.evaluator.start_evaluation_session()
        
        # 在执行过程中记录
        for step in self.steps:
            trajectory_id = self.evaluator.start_trajectory(...)
            
            # LLM 调用时
            self.evaluator.record_llm_call(...)
            
            # 工具调用时
            self.evaluator.record_tool_call(...)
            
            self.evaluator.end_trajectory(trajectory_id, ...)
        
        # 生成报告
        result = self.evaluator.evaluate_current_session()
```

### Mo-Shen 集成

在 `Mo-Shen-main/storyagents/server.py` 中：

```python
from evaluation import AgentEvaluator
from evaluation.models import AgentType

class StoryAgentsServer:
    def __init__(self):
        self.evaluator = AgentEvaluator(
            agent_type=AgentType.MO_SHEN,
            log_dir="./evaluation/logs"
        )
    
    async def generate_story(self, ...):
        self.evaluator.start_evaluation_session()
        
        try:
            # 执行工作流
            await self.workflow.run(...)
        finally:
            result = self.evaluator.evaluate_current_session()
```

详细集成说明见 [integration_guide.md](integration_guide.md)。

## 🎨 前端展示

将 `EvaluationDashboard.js` 复制到你的 React 项目中：

```jsx
import EvaluationDashboard from './components/EvaluationDashboard';

function App() {
  return (
    <Route path="/evaluation" element={<EvaluationDashboard />} />
  );
}
```

前端组件提供：
- 实时评分展示
- Agent 对比分析
- 问题与建议列表
- 轨迹详情查看

## ⚙️ 配置选项

```python
from evaluation.models import EvaluationConfig

config = EvaluationConfig(
    # 性能阈值
    max_acceptable_step_duration_ms=5000,
    
    # 权重配置
    llm_call_weight=0.4,
    tool_call_weight=0.3,
    parameter_format_weight=0.2,
    response_parse_weight=0.1,
    
    rationality_weight=0.6,
    efficiency_weight=0.4,
    
    # 日志配置
    save_raw_logs=True,
    save_aggregated_stats=True,
    
    # 输出配置
    output_format="json"
)

evaluator = AgentEvaluator(
    agent_type=AgentType.WRITEHERE,
    config=config
)
```

## 📈 评分计算

### 单步级别

```
单步综合得分 = LLM 准确率 × 0.4 
           + 工具准确率 × 0.3 
           + 参数格式准确率 × 0.2 
           + 响应解析准确率 × 0.1
```

### 轨迹级别

```
轨迹综合得分 = 平均合理性得分 × 0.6 
           + 平均效率得分 × 0.4
```

## 🔍 故障排除

### 常见问题

**Q: 日志文件过大**

A: 定期清理旧日志：
```python
from pathlib import Path
from datetime import datetime, timedelta

cutoff = datetime.now() - timedelta(days=7)
for f in Path('./logs').glob('*.json'):
    if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
        f.unlink()
```

**Q: 评估影响性能**

A: 使用采样：
```python
import random

if random.random() < 0.1:  # 10% 采样
    evaluator.record_llm_call(...)
```

**Q: Python 3.6 报错**

A: 安装 dataclasses 包：
```bash
pip install dataclasses
```

## 📝 下一步

完成集成后：

1. ✅ 在网页上测试前端仪表盘
2. ✅ 收集实际运行数据
3. ⏳ 进行第三步：任务完成度手动评估
4. ⏳ 对比两个 Agent 的综合表现

## 📄 许可证

MIT License

## 👥 贡献

欢迎提交问题和改进建议！

---

**注意**: 本评估系统设计用于研究和开发目的，帮助改进 Agent 的性能和可靠性。
