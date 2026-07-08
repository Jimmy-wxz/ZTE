# testData 向量库快速入门指南

## ✅ 系统状态

根据最新测试结果：

| 测试项 | 状态 | 说明 |
|--------|------|------|
| ChromaDB 结构 | ✅ 通过 | testData/chroma_data 包含 1 个 collection，597 个文档 |
| 后端 API | ✅ 已配置 | `/api/test-knowledge-base/search`端点已添加 |
| 向量搜索 | ⚠️ 需配置 | 需要 OpenAI API Key 来使用 text-embedding-3-large |

---

## 🚀 快速启动

### 方法一：使用测试脚本（推荐）

```bash
cd /path/to/ZTE

# 设置 OpenAI API Key（如果已有）
export OPENAI='sk-your-api-key-here'

# 运行测试脚本验证配置
python tests/final_test.py

# 启动后端服务器
./scripts/test_startup.sh
```

### 方法二：手动启动

```bash
# 1. 激活虚拟环境
source venv/bin/activate

# 2. 设置环境变量
export OPENAI='sk-your-api-key-here'  # 可选，但推荐
export WRITEHERE_EMBEDDING_MODEL='text-embedding-3-large'

# 3. 启动后端服务器
python backend/server.py --port 5001

# 4. （另一个终端）启动前端
cd frontend && npm start
```

---

## 📊 testData 数据集信息

**基本信息：**
- **Collection**: `rag_chunks`
- **文档数量**: 597 个文档块
- **Embedding 维度**: 1024 维
- **Embedding 模型**: OpenAI text-embedding-3-large
- **内容主题**: AgC 智能体平台相关文档

**Metadata 字段：**
- `title`: 文档标题
- `full_title`: 完整标题（含层级路径）
- `source_path`: 源文件路径
- `document_type`: 文档类型（json、markdown等）
- `chunk_index`: 块索引
- `link`: 原始链接
- `update_time`: 更新时间

---

## 🔍 测试查询示例

### 基础查询

```bash
curl -X POST http://localhost:5001/api/test-knowledge-base/search \
  -H "Content-Type: application/json" \
  -d '{"query": "AgC 平台如何使用", "topk": 3}'
```

### 推荐测试查询列表

#### AgC 平台使用
1. "AgC 平台新用户如何开始"
2. "如何创建一个智能体"
3. "智能体开发需要什么技能"

#### 开发与部署
4. "智能体开发的完整流程"
5. "如何调试智能体代码"
6. "API 接口调用示例"

#### 功能特性
7. "AgC 支持哪些类型的智能体"
8. "多模态智能体是什么"
9. "低代码开发工具介绍"

#### 权限与安全
10. "如何管理智能体的访问权限"
11. "数据安全如何保障"

#### 生态与集成
12. "如何发布智能体到 marketplace"
13. "智能体如何与其他系统集成"

---

## 🛠️ 故障排除

### 问题 1: "Embedding dimension mismatch"

**错误信息：**
```
chromadb.errors.InvalidDimensionException: 
Embedding dimension 384 does not match collection dimensionality 1024
```

**解决方案：**
```bash
# 确保设置了正确的 embedding 模型
export WRITEHERE_EMBEDDING_MODEL='text-embedding-3-large'

# 或者在代码中指定
store = ChromaVectorStore(
    persist_dir='testdata/chroma_data',
    embedding_model='text-embedding-3-large'
)
```

### 问题 2: "OPENAI environment variable not set"

**解决方案：**
1. 获取 OpenAI API Key：https://platform.openai.com/api-keys
2. 设置环境变量：`export OPENAI='sk-your-api-key'`
3. 重启服务器

**备选方案：**
如果不使用 OpenAI，可以重新生成 testData 的向量：
```python
from recursive.knowledge_base.service import KnowledgeBaseService

service = KnowledgeBaseService(
    base_path='testdata',
    embedding_model='sentence-transformers/all-MiniLM-L6-v2'
)
service.reindex('rag_chunks')
```

### 问题 3: ChromaDB sqlite3 版本过低

**错误信息：**
```
RuntimeError: Your system has an unsupported version of sqlite3.
```

**解决方案：**
系统已自动处理，如果仍有问题：
```bash
pip install pysqlite3-binary
```

---

## 📝 API 端点参考

### 列出所有知识库
```bash
GET /api/knowledge-base
```

### 获取特定知识库详情
```bash
GET /api/knowledge-base/{name}
```

### 搜索知识库
```bash
POST /api/knowledge-base/{name}/search
Body: {"query": "...", "topk": 5}
```

### 搜索 testData（新增）
```bash
POST /api/test-knowledge-base/search
Body: {"query": "...", "topk": 5}
Response: {
  "knowledgeBaseName": "testData/rag_chunks",
  "query": "...",
  "embedding_model": "text-embedding-3-large (1024-dim)",
  "results": [...]
}
```

---

## 🔧 高级配置

### 使用自定义 Embedding 模型

编辑 `recursive/knowledge_base/embedding.py` 添加新模型：

```python
class CustomEmbedding:
    def __init__(self, model_name="BAAI/bge-large-en-v1.5"):
        self.model_name = model_name
        # ... implementation
    
    def embed(self, texts):
        # ... embedding logic
```

### 配置外部知识库路径

通过环境变量指向外部 ChromaDB：
```bash
export WRITEHERE_KB_RAG_CHUNKS_PATH='/path/to/external/chroma_db'
export WRITEHERE_KB_RAG_CHUNKS_EMBEDDING='text-embedding-3-large'
```

然后在代码中使用：
```python
store.search('rag_chunks', query)  # 自动使用外部配置
```

---

## 📈 性能基准

基于测试数据：

| 指标 | 值 |
|------|-----|
| 文档总数 | 597 |
| 平均查询时间 | ~200ms (含 OpenAI API) |
| Top-3 准确率 | 待测试 |
| 最大并发查询 | 取决于 OpenAI API 限制 |

---

## 🎯 下一步行动

1. ✅ **完成配置**: 设置 OpenAI API Key
2. 🔄 **运行测试**: `python tests/final_test.py`
3. 📊 **评估效果**: 使用推荐查询测试检索质量
4. 📝 **记录结果**: 填写测试报告模板
5. 🚀 **生产部署**: 规划正式环境配置

---

## 📞 支持与反馈

如有问题或建议，请：
1. 查看 `TESTDATA_SETUP.md` 详细配置指南
2. 查看 `TESTDATA_PROMPTS.md` 测试提示词集合
3. 运行 `python tests/final_test.py` 获取诊断报告

---

**最后更新**: 2026-06-29
**版本**: 1.0.0
