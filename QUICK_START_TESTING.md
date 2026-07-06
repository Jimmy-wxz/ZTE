# testData 快速测试指南

## ✅ 系统已就绪

**后端服务器**: http://localhost:5001 ✅ 运行中  
**前端界面**: http://localhost:3000 ✅ 运行中  
**testData API**: `/api/test-knowledge-base/search` ✅ 已配置

---

## 🔑 第一步：设置 OpenAI API Key

testData 使用 1024 维向量，需要 OpenAI text-embedding-3-large 模型进行查询。

```bash
# 在终端中设置（临时）
export OPENAI='sk-your-api-key-here'

# 或者添加到 ~/.bashrc（永久）
echo "export OPENAI='sk-your-api-key-here'" >> ~/.bashrc
source ~/.bashrc
```

**获取 API Key**: https://platform.openai.com/api-keys

---

## 🧪 第二步：测试 API

### 方法 A: 使用 curl

```bash
# 测试查询
curl -X POST http://localhost:5001/api/test-knowledge-base/search \
  -H "Content-Type: application/json" \
  -d '{"query": "AgC 平台如何创建智能体", "topk": 3}' | python -m json.tool
```

**期望输出**（设置 API Key 后）:
```json
{
  "knowledgeBaseName": "testData/rag_chunks",
  "query": "AgC 平台如何创建智能体",
  "embedding_model": "text-embedding-3-large (1024-dim)",
  "results": [
    {
      "text": "...",
      "title": "01 AgC 用户使用指南",
      "distance": 0.1234,
      ...
    }
  ]
}
```

### 方法 B: 使用前端界面

1. 打开浏览器访问：http://localhost:3000
2. 在搜索框输入查询
3. 查看返回结果和相关性评分

---

## 📝 第三步：使用建议的提示词

从 `suggested_prompts.txt` 中选择查询进行测试：

### 基础查询（推荐先测试这些）
```
AgC 平台如何创建智能体
智能体开发的完整流程是什么
API 接口调用方法有哪些
如何管理智能体的访问权限
低代码开发工具如何使用
```

### 进阶查询
```
多模态智能体支持哪些功能
智能体如何与其他系统集成
RAG 架构在 AgC 中的实现
Function Calling 机制说明
Chain of Thought 优化方法
```

---

## 📊 第四步：记录测试结果

使用以下模板记录每个查询的结果：

```markdown
## Query: "AgC 平台如何创建智能体"

**时间**: 2026-06-29 HH:MM:SS  
**TopK**: 3  
**响应时间**: ~500ms

### 返回结果

1. **Title**: 01 AgC 用户使用指南
   **Distance**: 0.1234
   **Relevance**: ⭐⭐⭐⭐⭐
   **Comment**: 直接回答了问题，包含完整的创建流程

2. **Title**: ...
   ...

### 总体评价
检索效果良好，第一条结果完全匹配查询意图...
```

---

## 🎯 测试检查清单

完成以下任务以验证系统功能：

- [ ] 设置了 OpenAI API Key
- [ ] 成功执行了至少 1 次 API 查询
- [ ] 测试了 5 个以上不同的查询
- [ ] 记录了查询结果和相关性评分
- [ ] 识别了检索效果好和差的查询类型
- [ ] 提出了至少 1 条改进建议

---

## 🔍 常见问题

### Q1: 为什么返回空结果？
**A**: 没有设置 OpenAI API Key。设置后重启服务器：
```bash
export OPENAI='sk-...'
# 停止服务器（Ctrl+C）
python backend/server.py --port 5001
```

### Q2: 响应时间太长怎么办？
**A**: OpenAI API 调用需要网络延迟。可以考虑：
- 实施查询结果缓存
- 使用本地 embedding 模型（如 BGE-Large）
- 批量处理多个查询

### Q3: 如何测试不使用 OpenAI 的情况？
**A**: 可以重新生成 testData 的向量：
```python
from recursive.knowledge_base.service import KnowledgeBaseService

service = KnowledgeBaseService(
    base_path='testdata',
    embedding_model='sentence-transformers/all-MiniLM-L6-v2'
)
service.reindex('rag_chunks')
```

---

## 🚀 下一步

完成基础测试后：

1. **深入评估**: 使用 `TESTDATA_PROMPTS.md` 中的 25+ 个分类查询进行全面测试
2. **性能分析**: 测量不同查询类型的响应时间和准确率
3. **对比实验**: 比较不同 embedding 模型的检索效果
4. **生产规划**: 基于测试结果设计正式环境的知识库架构

---

## 📞 需要帮助？

查看详细文档：
- **配置指南**: `TESTDATA_SETUP.md`
- **测试提示词**: `TESTDATA_PROMPTS.md`
- **快速入门**: `README_TESTDATA.md`
- **完成总结**: `COMPLETION_SUMMARY.md`

运行诊断工具：
```bash
python final_test.py
```

---

**祝测试顺利！** 🎉

有任何问题或发现，请记录下来并与团队分享。
