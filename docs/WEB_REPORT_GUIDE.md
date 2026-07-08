# 📄 从指定网页生成报告 - 使用指南

## 🎯 **功能说明**

这个工具可以让你基于**特定网页的内容**来生成分析报告，而不是让AI自己去搜索。

---

## 🚀 **使用方法**

### **方法一：两步法（推荐）**

#### **第1步：提取网页内容**

```bash
source venv/bin/activate
python scripts/web_extractor.py "https://example.com/article" --output webpage_content.txt
```

这会：
- 访问指定的URL
- 提取网页的纯文本内容
- 保存到 `webpage_content.txt`

#### **第2步：在Web界面中使用**

1. 打开 http://localhost:3000
2. 进入 **"Report Generation"** 页面
3. **取消勾选 "Enable Search"** ✓
4. 在提示词框中输入：

```
请根据以下网页内容生成一份详细的分析报告：

[复制 webpage_content.txt 的全部内容]

要求：
1. 总结文章的核心观点和主要论据
2. 分析作者的立场和论证方式
3. 评价内容的可信度和价值
4. 提出你的独立见解和补充信息
```

5. 选择模型（推荐：DeepSeek-V4）
6. 点击 **"Generate Report"**

---

### **方法二：一键脚本（快速测试）**

```bash
./scripts/generate_report_from_url.sh "https://example.com/article"
```

这个脚本会：
1. 自动提取网页内容
2. 调用LLM生成报告
3. 保存结果到JSON文件

**注意**：需要先在 `recursive/api_key.env` 中配置好API密钥。

---

### **方法三：命令行直接使用（高级用户）**

```bash
source venv/bin/activate

# 提取网页内容
python scripts/web_extractor.py "https://zh.wikipedia.org/wiki/人工智能" > ai_article.txt

# 创建输入文件
cat > input.jsonl << EOF
{
  "topic": "人工智能",
  "intent": "分析",
  "domain": "科技",
  "id": "web-report-001",
  "prompt": "请根据以下维基百科文章内容，生成一份关于人工智能发展历史的分析报告：\n\n$(cat ai_article.txt)"
}
EOF

# 运行报告生成（禁用搜索）
cd recursive
python engine.py \
  --filename ../input.jsonl \
  --output-filename ../report_output.jsonl \
  --done-flag-file ../done.txt \
  --model deepseek-chat \
  --engine-backend none \
  --mode report
```

---

## 💡 **实用示例**

### **示例1：分析新闻文章**

```bash
python scripts/web_extractor.py "https://news.example.com/tech/ai-breakthrough" > news.txt
```

然后在Web界面输入：
```
请分析这篇新闻报道：
[粘贴news.txt内容]

重点关注：
1. 报道的核心事实是什么？
2. 使用了哪些信息来源？
3. 报道角度是否客观？
4. 有什么潜在偏见？
```

---

### **示例2：研究论文摘要**

```bash
python scripts/web_extractor.py "https://arxiv.org/abs/2301.xxxxx" > paper.txt
```

提示词：
```
请总结这篇论文的主要内容：
[粘贴paper.txt内容]

包括：
1. 研究问题和目标
2. 提出的方法
3. 实验结果
4. 主要贡献和局限性
```

---

### **示例3：产品评测分析**

```bash
python scripts/web_extractor.py "https://techcrunch.com/review/new-gadget" > review.txt
```

提示词：
```
请分析这个产品评测：
[粘贴review.txt内容]

分析要点：
1. 产品的优缺点
2. 评测者的评价标准
3. 与竞品的对比
4. 购买建议
```

---

## ⚙️ **技术细节**

### **网页提取器的工作原理**

1. **发送HTTP请求**：模拟浏览器访问URL
2. **解析HTML**：使用BeautifulSoup库
3. **智能提取**：
   - 移除导航栏、广告、页脚等无关内容
   - 优先提取文章主体（`<article>`、`<main>`标签）
   - 保留段落文本
4. **清理格式**：去除多余空白和短行

### **支持的网站**

✅ **大多数新闻网站、博客、维基百科**  
✅ **GitHub README、技术文档**  
⚠️ **需要登录的网站（不支持）**  
⚠️ **JavaScript动态加载内容的网站（可能提取不全）**  

---

## 🔧 **故障排查**

### **问题1：无法获取网页内容**

```
ERROR: 无法获取网页内容 - HTTPSConnectionPool...
```

**原因**：
- 网络连接问题
- 网站屏蔽了爬虫
- URL不正确

**解决方法**：
- 检查网络连接
- 尝试在浏览器中打开URL
- 确认URL完整且正确

---

### **问题2：提取的内容太少**

**原因**：
- 网站使用大量JavaScript渲染
- 内容在iframe中

**解决方法**：
- 手动复制网页内容（Ctrl+A → Ctrl+C）
- 或者使用浏览器的"阅读模式"再复制

---

### **问题3：报告质量不佳**

**可能原因**：
- 网页内容太长，超出LLM上下文限制
- 提示词不够明确

**解决方法**：
- 截取网页的关键部分（前2000-3000字）
- 提供更具体的分析要求

---

## 📊 **最佳实践**

### **1. 选择合适的网页**
- ✅ 内容丰富的长文（1000字以上）
- ✅ 结构清晰的文章
- ❌ 短视频页面、图片为主的页面

### **2. 编写好的提示词**
```
坏例子："分析一下这篇文章"

好例子：
"请作为科技评论家分析这篇文章：
1. 总结核心观点（200字以内）
2. 列出3个主要论据
3. 评价论证的逻辑性
4. 指出可能的偏见或遗漏
5. 给出你的专业见解"
```

### **3. 分步骤处理长内容**
如果网页非常长（超过5000字）：
1. 先让AI总结大意
2. 然后针对重点段落深入分析
3. 最后综合成完整报告

---

## 🎓 **进阶技巧**

### **多网页对比分析**

```bash
# 提取多个网页
python scripts/web_extractor.py "https://site1.com/article" > article1.txt
python scripts/web_extractor.py "https://site2.com/article" > article2.txt
```

然后在Web界面：
```
请对比分析这两篇关于同一主题的文章：

【文章1】
[粘贴article1.txt内容]

【文章2】
[粘贴article2.txt内容]

对比维度：
1. 观点差异
2. 论据质量
3. 写作风格
4. 目标受众
5. 可信度评估
```

---

### **结构化输出**

在提示词中指定输出格式：
```
请以Markdown格式输出报告，包含以下章节：

## 概要
（200字总结）

## 核心观点
- 观点1：...
- 观点2：...

## 关键论据
1. ...
2. ...

## 批判性分析
...

## 结论与建议
...
```

---

## 📝 **总结**

现在你可以：
1. ✅ 提取任何网页的内容
2. ✅ 在Web界面中基于该内容生成报告
3. ✅ 完全不需要SerpAPI
4. ✅ 精确控制分析的角度和深度

**开始创作吧！** 🚀

有任何问题随时问我。
