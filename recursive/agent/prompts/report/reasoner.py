#!/usr/bin/env python3
from recursive.agent.prompts.base import PromptTemplate
from recursive.agent.prompts.base import prompt_register
from datetime import datetime
now = datetime.now()

@prompt_register.register_module()
class ReportReasoner(PromptTemplate):
    def __init__(self) -> None:
        system_message = "".strip()

        content_template = """
需要完成的协作报告撰写任务：**{to_run_root_question}**

您需要完成的具体分析任务：**{to_run_task}**

---
现有的报告分析结论和搜索结果如下：
```
{to_run_outer_graph_dependent}

{to_run_same_graph_dependent}
```

---
已撰写的报告：
```
{to_run_article}
```

---
今天是 {today_date}，您是一位专业的报告撰写专家，与其他专业作家合作生产满足指定用户需求的专业报告。您的任务是完成分配给您的分析任务，旨在支持其他作家的撰写和分析工作，从而为整个报告的完成做出贡献。

注意！！
1. 您的分析结果应与现有报告分析结论逻辑一致且连贯。
2. 并非所有搜索结果都相关和有用，您应该仔细识别。
3. 永远不要产生幻觉。仔细思考。

* 数据准确性和引用支持：
   * 使用 [reference:X] 格式在适当句子的末尾引用来源
   * 如果信息来自多个来源，列出所有相关引用，例如 [reference:3][reference:5]
   * 引用应出现在正文中，而不是集中在末尾
   * 搜索结果中的 <source_type>Local KB</source_type> 表示本地知识库，属于内部权威材料；<source_type>Web Search</source_type> 或 <source_type>Web Search (SerpAPI)</source_type> 表示公开网络资料
   * 内部项目、岗位、课程、历史培训、流程实践等事实应优先依据 Local KB；公开网络资料只用于补充外部趋势、公开案例、行业报告和横向对比
   * 不要自行重排或改写引用编号；系统会在最终报告中自动把本地知识库引用转换为 [KB:N]，把网络引用转换为 [WEB:N]
   * 如果来源之间存在冲突或可信度不足，应明确说明“内部资料显示”“公开资料显示”或“不足以确认”，不要写成绝对结论

# 输出格式
1. 首先，在 <thinking> 中进行思考
2. 然后，在 `<result></result>` 中，以结构化和可读的格式撰写分析结果，提供尽可能多的细节。具体格式如下：
<thinking>
在此思考
</thinking>

<result>
分析结果
</result>


请按照 # 要求 中的指示以专业和创新的方式完成分析任务 **{to_run_task}**。您应该按照 # 输出格式 输出，首先在 <thinking> 中思考，然后在 <result></result> 中输出分析结果，在 </result> 之后不要附加任何其他信息。
""".strip()
        content_template += """

---
额外格式约束：
* 第一章必须是引言、概述或背景说明，不能让最终报告直接从第二章开始。
* 章节数应与实际写作任务数匹配，禁止把分析大纲过度拆成最终写作无法覆盖的章节。
* 分析设计只是给 Writer 的结构参考；章节编号必须服务于最终报告的真实顺序。
* 如需使用表格，表格单元格内禁止使用 Markdown 加粗（**text**），表格内文字应为纯文本。
"""
        super().__init__(system_message, content_template)




if __name__ == "__main__":
    from recursive.agent.agent_base import DummyRandomPlanningAgent
    agent = DummyRandomPlanningAgent()
