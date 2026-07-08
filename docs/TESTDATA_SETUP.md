# testData 向量库接入指南

## 概述

`testdata/chroma_data`包含了一个预构建的 ChromaDB 向量数据库，其中有：
- **Collection 名称**: `rag_chunks`
- **文档数量**: 597 个文档块
- **Embedding 维度**: 1024 维（使用 OpenAI `text-embedding-3-large`生成）
- **内容**: AgC 智能体平台相关文档

## 问题与解决方案

### 问题
系统默认使用 `sentence-transformers/all-MiniLM-L6-v2`模型（384 维），与 testData 中的 1024 维向量不匹配。

### 解决方案
需要使用 OpenAI 的 `text-embedding-3-large` 模型来生成查询向量，以匹配 testData 中的向量维度。

## 配置步骤

### 方法一：环境变量配置（推荐）

1. **设置 OpenAI API Key**
   ```bash
   export OPENAI='sk-your-api-key-here'
   ```

2. **设置 Embedding 模型**
   ```bash
   export WRITEHERE_EMBEDDING_MODEL='text-embedding-3-large'
   ```

3. **设置知识库路径**
   ```bash
   export WRITEHERE_KB_PATH="/path/to/ZTE/testdata"
   ```

4. **设置知识库名称**
   ```bash
   export WRITEHERE_KB_NAME='rag_chunks'
   ```

### 方法二：通过 API 使用

后端服务器已经添加了新的 API 端点 `/api/test-knowledge-base/search`，专门用于测试 testData 搜索。

#### API 请求示例
```bash
curl -X POST http://localhost:5001/api/test-knowledge-base/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "AgC 平台如何使用",
    "topk": 5
  }'
```

#### API 响应示例
```json
{
  "knowledgeBaseName": "testData/rag_chunks",
  "query": "AgC 平台如何使用",
  "embedding_model": "text-embedding-3-large (1024-dim)",
  "results": [
    {
      "text": "...",
      "source": "...",
      "title": "...",
      "distance": 0.1234
    }
  ]
}
```

## 测试脚本

### 1. 直接测试 ChromaDB
```bash
cd /path/to/ZTE
source venv/bin/activate
python tests/test_check_chroma.py
```

### 2. 测试 testData 搜索（需要 OpenAI API Key）
```bash
export OPENAI='your-api-key'
python tests/test_testdata_search.py
```

### 3. 测试后端 API
启动后端服务器后，访问前端页面或使用 curl 测试：
```bash
# 启动后端
python backend/server.py --port 5001

# 在另一个终端测试 API
curl -X POST http://localhost:5001/api/test-knowledge-base/search \
  -H "Content-Type: application/json" \
  -d '{"query": "智能体开发", "topk": 3}'
```

## 在前端中使用 testData

### 修改前端配置（可选）

如果需要将 testData 作为默认知识库，可以修改前端的 API 调用逻辑。

### 使用现有知识库界面

1. 启动后端服务器（确保设置了正确的环境变量）
2. 打开前端页面（通常是 http://localhost:3000）
3. 在知识库管理界面中，应该能看到 `rag_chunks` 知识库
4. 进行搜索测试

## 建议的测试提示词

以下是针对 testData 内容设计的测试查询：

### AgC 平台使用相关
- "AgC 平台如何创建智能体"
- "智能体开发流程是什么"
- "如何部署已开发的智能体"
- "AgC 平台的权限管理机制"

### API 和技术相关
- "API 接口调用方法"
- "Webhook 配置教程"
- "数据可视化功能介绍"
- "智能体调试工具使用"

### 生态和功能相关
- "AgC 生态合作伙伴计划"
- "智能体 marketplace 功能"
- "多模态智能体支持"
- "低代码开发工具介绍"

## 故障排除

### 问题：Embedding dimension mismatch
**错误信息**: `Embedding dimension 384 does not match collection dimensionality 1024`

**解决方案**: 
1. 确保设置了 `WRITEHERE_EMBEDDING_MODEL='text-embedding-3-large'`
2. 确保设置了有效的 `OPENAI` API key

### 问题：ChromaDB sqlite3 版本过低
**错误信息**: `Your system has an unsupported version of sqlite3`

**解决方案**: 
系统已经自动使用 `pysqlite3-binary`，如果仍有问题，手动安装：
```bash
pip install pysqlite3-binary
```

### 问题：OpenAI API 调用失败
**可能原因**: API key 无效或网络问题

**解决方案**:
1. 检查 API key 是否正确
2. 确认网络连接正常
3. 考虑使用本地 embedding 模型重新生成 testData 向量

## 高级配置

### 使用本地 1024 维 Embedding 模型

如果不想依赖 OpenAI API，可以使用其他 1024 维的本地模型，例如：
- `BAAI/bge-large-en-v1.5` (1024 维)
- `intfloat/e5-large-v2` (1024 维)

修改 `WRITEHERE_EMBEDDING_MODEL` 环境变量即可。

### 重新生成 testData 向量

如果需要使用不同的 embedding 模型，可以重新处理原始文档：
```python
from recursive.knowledge_base.service import KnowledgeBaseService

service = KnowledgeBaseService(
    base_path='/path/to/testdata',
    embedding_model='sentence-transformers/all-MiniLM-L6-v2'  # 或其他模型
)
service.reindex('rag_chunks')
```

## 性能优化建议

1. **缓存查询结果**: 对于频繁查询，可以考虑添加缓存层
2. **批量查询**: 如果需要多次查询，考虑批量处理
3. **索引优化**: ChromaDB 的 HNSW 索引已经配置好，通常不需要调整

## 下一步

完成 testData 测试后，可以：
1. 将类似的向量库集成到生产环境
2. 开发自定义的数据处理和向量化流程
3. 实现更复杂的 RAG（检索增强生成）功能
