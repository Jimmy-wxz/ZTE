# DeepSeek-V4 配置完成指南 🎉

## ✅ 已完成的配置

### 1. API 集成代码修改

**文件**: `recursive/llm/llm.py`

- ✅ 添加了 DeepSeek API 端点配置（第 164-166 行）
  ```python
  elif "deepseek" in model:
      url = 'https://api.deepseek.com/v1/chat/completions'
      api_key = str(os.getenv('DEEPSEEK'))
  ```

- ✅ 添加了 DeepSeek 价格信息（第 379-382 行）
  ```python
  elif "deepseek" in model:
      ip = 0.27  # Input tokens ($/million)
      op = 1.10  # Output tokens ($/million)
  ```

### 2. API 密钥配置

**文件**: `recursive/api_key.env`

```
DEEPSEEK=<your-deepseek-api-key>
```

✅ 已为你填入你的 DeepSeek API 密钥

### 3. 依赖安装

✅ 已安装所有必需的依赖包：
- openai (用于 OpenAI 客户端)
- anthropic (用于 Anthropic 支持)
- python-dotenv (环境变量加载)
- botocore & boto3 (AWS SDK，可选)

---

## 🚀 使用 DeepSeek 运行写作任务

### 方式一：Web 界面（推荐）

1. **启动服务**（如果还未启动）：
   ```bash
   ./start.sh
   ```

2. **打开浏览器**：http://localhost:3000

3. **在输入框中**：
   - 输入你的写作提示（如："写一篇关于机器人与人类友谊的科幻故事"）
   - 在模型选择中输入：`deepseek-chat`
   - 点击生成按钮

4. **实时查看**：
   - 任务分解树
   - 执行进度
   - 最终生成的文章

---

### 方式二：命令行快速测试

```bash
# 1. 激活虚拟环境
source venv/bin/activate

# 2. 进入 recursive 目录
cd recursive

# 3. 运行故事生成（使用 DeepSeek）
python engine.py \
  --filename ../test_data/meta_fiction.jsonl \
  --output-filename ./project/story/deepseek_output.jsonl \
  --done-flag-file ./project/story/deepseek_done.txt \
  --model deepseek-chat \
  --mode story
```

---

### 方式三：使用测试脚本

```bash
# 运行我创建的快速测试脚本
source venv/bin/activate
python test_deepseek.py

# 然后按照提示运行命令
cd recursive
python engine.py \
  --filename ../test_deepseek_input.jsonl \
  --output-filename ../test_deepseek_output.jsonl \
  --done-flag-file ../test_deepseek_done.txt \
  --model deepseek-chat \
  --mode story
```

---

## 📊 DeepSeek 模型信息

### 支持的模型标识符

| 模型名称 | 用途 | 推荐场景 |
|---------|------|---------|
| `deepseek-chat` | DeepSeek-V4 | 通用对话、写作（推荐） |
| `deepseek-coder` | DeepSeek-Coder | 代码生成、技术文档 |

### 定价（每百万 tokens）

- **输入**: $0.27 USD
- **输出**: $1.10 USD

💡 **性价比提示**：DeepSeek-V4 相比 GPT-4o 便宜约 10 倍，性能相当！

---

## 🔍 验证配置

运行以下命令验证 DeepSeek API 是否正常工作：

```bash
source venv/bin/activate
cd recursive
python -c "
from llm.llm import OpenAIApiProxy
from cache import Cache
import tempfile, os

os.environ['DEEPSEEK'] = '<your-deepseek-api-key>'
temp_cache = tempfile.mkdtemp()
from recursive.memory import caches
caches['llm'] = Cache(temp_cache + '/llm')

proxy = OpenAIApiProxy(verbose=False)
messages = [{'role': 'user', 'content': 'Hello! Test with DeepSeek.'}]
result = proxy.call('deepseek-chat', messages, temperature=0.7, no_cache=True)
print('✅ DeepSeek API 工作正常!')
print('响应:', result[0]['message']['content'])
"
```

预期输出：
```
✅ DeepSeek API 工作正常!
响应: Hello! How can I assist you today?
```

---

## 📁 重要文件位置

| 文件 | 说明 |
|------|------|
| `recursive/api_key.env` | API 密钥配置（已包含你的 DeepSeek 密钥） |
| `recursive/llm/llm.py` | LLM API 集成代码（已添加 DeepSeek 支持） |
| `RUNNING_GUIDE.md` | 完整运行指南 |
| `test_deepseek.py` | DeepSeek 快速测试脚本 |
| `DEEPSEEK_SETUP.md` | 本文件 - DeepSeek 配置说明 |

---

## ⚠️ 常见问题

### Q: 可以使用其他 DeepSeek 模型吗？
A: 可以！只需在 `--model` 参数中使用不同的模型名称，如 `deepseek-coder`。

### Q: DeepSeek 支持网络搜索吗？
A: 是的！在报告模式下，DeepSeek 可以与搜索引擎结合使用：
```bash
python engine.py \
  --filename ../test_data/qa_test.jsonl \
  --output-filename ./report_output.jsonl \
  --model deepseek-chat \
  --engine-backend google \
  --mode report
```

### Q: 如何监控 DeepSeek 的使用成本？
A: 框架会自动记录每个模型的 token 使用和估算成本。查看日志文件中的 "Usage" 和 "price" 信息。

### Q: API 密钥安全吗？
A: 是的！API 密钥只存储在本地 `api_key.env` 文件中，不会上传到任何服务器。

---

## 🎯 立即开始！

最简单的使用方式：

```bash
# 1. 启动 Web 界面
./start.sh

# 2. 打开浏览器 http://localhost:3000

# 3. 输入写作请求并选择模型 deepseek-chat

# 4. 观察 AI 如何分解和执行写作任务！
```

或者直接使用命令行：

```bash
source venv/bin/activate
cd recursive
python engine.py \
  --filename ../test_data/meta_fiction.jsonl \
  --output-filename ./story_output.jsonl \
  --done-flag-file ./done.txt \
  --model deepseek-chat \
  --mode story
```

---

**祝你使用 DeepSeek 愉快！** 🚀📝

如有问题，请查看 `RUNNING_GUIDE.md` 或检查日志文件。
