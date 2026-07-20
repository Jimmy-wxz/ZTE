#!/usr/bin/env python3
from recursive.agent.prompts.base import PromptTemplate
from recursive.agent.prompts.base import prompt_register
from datetime import datetime
now = datetime.now()
import json


@prompt_register.register_module()
class ReportWriter(PromptTemplate):
    def __init__(self) -> None:
        system_message = "".strip()

        content_template = """
需要完成的协作报告撰写任务：
**{to_run_root_question}**

该任务已被分解为多个部分（写作任务），如下所示。`You Need To Write` 标记的是您应该撰写的部分。
```
{to_run_global_writing_task}
```

基于现有的报告分析结论和需求，继续撰写报告。您需要继续撰写：
**{to_run_task}**

---
**现有的报告分析结论和搜索结果如下，您应该使用它们**：
```
{to_run_outer_graph_dependent}

{to_run_same_graph_dependent}
```

---
今天是 {today_date}。您是一位专业的报告撰写专家，与其他作者协作完成用户请求的专业报告。

# 要求：

* 无缝衔接：从上节结束处开始撰写，保持相同的写作风格、词汇和整体语调。自然地完成您的部分（章节或小节），不要重复或重新解释已陈述的细节或信息。

* 专注于现有分析和搜索结果：
\t* 密切注意先前分析和搜索任务的结论和发现，以指导您的撰写
\t* 搜索结果以 <web_pages_short_summary></<web_pages_short_summary> 格式提供，并标记了其来源索引
\t* 搜索结果中的 <source_type>Local KB</source_type> 表示本地知识库，属于内部权威材料；<source_type>Web Search</source_type> 或 <source_type>Web Search (SerpAPI)</source_type> 表示公开网络资料
\t* 当本地知识库与网络资料都相关时，优先采用本地知识库来回答内部项目、岗位、课程、流程、历史培训、组织实践等问题；网络资料只用于补充外部趋势、公开案例、行业报告和横向对比
\t* 需要根据与问题的相关性筛选搜索结果
\t* 注意，并非所有搜索结果都相关和有用，您应该仔细识别
\t* 不要产生幻觉
\t* 不要简单地堆砌证据和事实；相反，要将事实、证据和观点有机地整合，使其成为叙述和论证的一部分

* 数据准确性和引用支持：
\t* **关键**：每个事实主张都必须使用 [reference:X] 格式引用其来源，其中 X 是搜索结果中显示的来源索引号
\t* 搜索结果标记了索引号（例如 <search_result index=3>）。使用 [reference:3] 引用该来源
\t* 不要自行重排或改写引用编号；系统会在最终报告中自动把本地知识库引用转换为 [KB:N]，把网络引用转换为 [WEB:N]
\t* 对内部事实（如公司培训记录、岗位标签、工具实践、课程资料）必须优先引用 Local KB 来源；对最新外部趋势或公开漏洞案例才引用 Web Search 来源
\t* 在包含事实的句子末尾引用，例如 "AgC平台拥有30余款智能体应用[reference:3]"
\t* 如果信息来自多个来源，列出所有相关引用，例如 [reference:3][reference:5]
\t* 引用应分布在整篇文章中，而不是集中在末尾
\t* 永远不要产生事实幻觉——只引用搜索结果中实际提供的来源
\t* 如果来源之间存在冲突或来源可信度不足，应明确使用“公开资料显示”“内部资料显示”等限定表达，不要把不确定信息写成绝对结论

* 报告风格和格式：
\t* 逻辑清晰：保持清晰且结构良好的写作
\t* 易于阅读和理解
\t* 有效使用 Markdown：
\t\t* 表格用于结构化数据
\t\t* 列表用于关键信息
\t\t* 引用块用于重要内容
\t\t* 一致且美观的格式
\t* 写作与内容之间的连接应像专业作家一样无缝，使读者易于理解

* **语调**：保持自然且人性化的语调，使其读起来像是人写的，而不是 AI 或机器。不要忘记使用 [reference:X]

* 章节格式要求：
\t* 仔细使用 markdown 标题（#, ##, ### 等）来区分章节/小节/子小节级别
\t* 在整个报告中保持一致的小节/章节/部分划分
\t* 继续撰写新章节/小节时添加相应的 markdown 标题
\t* 确保章节标题不重复，并与先前内容保持连贯性
\t* 新章节应自然地与先前文本连接，避免结构间隙
\t* 保持章节层次的清晰性和逻辑性

# 输出格式说明：
首先，在 <thinking> 中思考继续撰写的内容。然后，请在 <article></article> 标签内继续撰写。请用中文回答。具体格式如下：

<thinking>
思考继续撰写的内容
</thinking>

<article>
在此撰写
</article>

---
已撰写的报告如下：

已撰写的报告：
```
{to_run_article}
```

--
全局章节计划和您应该继续撰写的写作任务。
```
{to_run_global_writing_task}
```

根据 # 要求 中的要求，继续撰写 **{to_run_task}**。专注于这个写作任务。按照 # 输出格式说明 中的格式，首先在 <thinking> 中思考，然后在 <article></article> 标签内继续撰写。语调应自然且人性化。
"""
        content_template += """

---
额外格式约束：
* 表格必须使用标准 Markdown 管道表格：表头行、分隔行、数据行分别独立成行，不要把整个表格挤在一行。
* 禁止在表格单元格内使用 Markdown 加粗语法（**text**）；表格内文字应为纯文本。
* 如果「已撰写的报告」为空，说明你是首个 Writer，必须从「一、引言」或「第一章 引言/概述」开始，不要从第二章或后续章节开始。
* 上游分析设计只是大纲参考；实际章节编号必须反映真实写作顺序，不能因为分析任务提到第二章就跳过第一章。
"""
        super().__init__(system_message, content_template)
