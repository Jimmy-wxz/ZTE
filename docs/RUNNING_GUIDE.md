# WriteHERE 运行指南

## ✅ 环境配置已完成

已为你完成以下配置：
- Python 虚拟环境（使用 Python 3.8）
- 所有后端依赖已安装
- 前端依赖已安装
- API 密钥配置文件已创建

## 🔑 配置 API 密钥

在运行前，需要编辑 `recursive/api_key.env` 文件，添加你的 API 密钥：

```bash
nano recursive/api_key.env
```

**已为你配置 DeepSeek：**
- ✅ `DEEPSEEK=<your-deepseek-api-key>` - DeepSeek API 密钥

其他可选配置：
- `OPENAI=` - OpenAI API 密钥（用于 GPT 模型）
- `CLAUDE=` - Anthropic API 密钥（用于 Claude 模型）
- `SERPAPI=` - SerpAPI 密钥（用于报告模式中的网络搜索）
- `GEMINI=` - Google Gemini API 密钥
- `OPENROUTER=` - OpenRouter API 密钥

## 🚀 运行方式

### 方式一：使用可视化界面（推荐）

这是最简单的方式，提供 Web 界面来监控写作过程。

```bash
# 在项目根目录下执行
./start.sh
```

这会自动：
1. 启动后端服务器（端口 5001）
2. 启动前端服务器（端口 3000）
3. 自动打开浏览器访问 http://localhost:3000

**自定义端口：**
```bash
./start.sh --backend-port 8080 --frontend-port 8000
```

### 方式二：命令行直接运行（无需可视化界面）

适合批量处理或不需要实时监控的场景。

#### 生成故事：

```bash
source venv/bin/activate
cd recursive
python engine.py \
  --filename ../test_data/meta_fiction.jsonl \
  --output-filename ./project/story/output.jsonl \
  --done-flag-file ./project/story/done.txt \
  --model deepseek-chat \
  --mode story
```

**支持的 DeepSeek 模型：**
- `deepseek-chat` - DeepSeek-V4（推荐，性价比高）
- `deepseek-coder` - DeepSeek-Coder（代码专用）

#### 生成报告：

```bash
source venv/bin/activate
cd recursive
python engine.py \
  --filename ../test_data/qa_test.jsonl \
  --output-filename ./project/qa/result.jsonl \
  --done-flag-file ./project/qa/done.txt \
  --model claude-3-sonnet \
  --engine-backend google \
  --mode report
```

**参数说明：**
- `--filename`: 输入文件路径（JSONL 格式）
- `--output-filename`: 输出文件路径
- `--done-flag-file`: 完成标志文件路径
- `--model`: 使用的模型名称
- `--mode`: 模式选择（story 或 report）
- `--engine-backend`: 搜索引擎（google 或 searxng，仅报告模式需要）

### 方式三：手动启动前后端

如果你想分别控制前后端：

```bash
# 终端 1 - 启动后端
source venv/bin/activate
cd backend
python server.py --port 5001

# 终端 2 - 启动前端
cd frontend
PORT=3000 npm start
```

## 📝 输入文件格式

### 故事模式输入示例 (`test_data/meta_fiction.jsonl`)：
```json
{
  "id": "example",
  "field": "inputs",
  "value": "Please write a metafictional literary short story about AI and grief, around 1000 words.",
  "ori": {
    "example_id": "example",
    "inputs": "Please write a metafictional literary short story about AI and grief, around 1000 words.",
    "subset": "train"
  }
}
```

### 报告模式输入示例：
```json
{
  "topic": "",
  "intent": "",
  "domain": "",
  "id": "task-001",
  "prompt": "Explain the impact of climate change on global agriculture"
}
```

## 🔍 查看输出

运行完成后，输出文件包含生成的内容：

- **故事模式**：输出为 JSONL 格式，包含完整的故事文本
- **报告模式**：除了 JSONL 结果外，还会生成 `report.md` 文件

输出目录结构：
```
project/
├── records/          # 详细记录
│   └── [task-id]/
│       ├── nodes.json      # 任务图数据
│       ├── article.txt     # 生成的文章
│       ├── engine.log      # 引擎日志
│       └── report.md       # 格式化的报告（仅报告模式）
├── story/
│   ├── output.jsonl      # 故事输出
│   └── done.txt          # 完成标志
└── qa/
    ├── result.jsonl      # 报告输出
    └── done.txt          # 完成标志
```

## ⚠️ 常见问题

### 1. 端口冲突
如果提示端口已被占用，可以：
```bash
# 查找占用端口的进程
lsof -i :5001
# 或使用自定义端口启动
./start.sh --backend-port 8080 --frontend-port 8000
```

### 2. API 密钥错误
确保 `recursive/api_key.env` 文件中的密钥格式正确，没有多余空格。

### 3. 内存不足
生成长文本时可能消耗大量内存，建议至少 4GB 可用内存。

### 4. Python 版本问题
本项目需要 Python 3.8+，已为你配置好虚拟环境。

## 🛑 停止服务

- **使用 start.sh 启动**：按 `Ctrl+C` 停止
- **手动启动的后端**：按 `Ctrl+C` 或 `kill` 进程
- **手动启动的前端**：按 `Ctrl+C`

## 📊 实时任务可视化

使用 Web 界面时，你可以看到：
1. 任务的层次分解结构
2. 当前正在执行的任务
3. 每个任务的状态（就绪、进行中、已完成）
4. 任务类型（检索、推理、创作）

这让你能够洞察 AI 的"思考过程"，了解复杂写作任务是如何被逐步分解和解决的。

## 🎯 快速测试

最简单的测试方式：

```bash
# 1. 编辑 API 密钥
nano recursive/api_key.env

# 2. 启动应用
./start.sh

# 3. 在浏览器中访问 http://localhost:3000
# 4. 输入写作请求，选择模型，点击生成
```

祝你使用愉快！🎉
