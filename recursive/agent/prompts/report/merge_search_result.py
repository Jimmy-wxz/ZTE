#!/usr/bin/env python3
from recursive.agent.prompts.base import PromptTemplate
from recursive.agent.prompts.base import prompt_register
from datetime import datetime
now = datetime.now()


@prompt_register.register_module()
class MergeSearchResultVFinal(PromptTemplate):
    def __init__(self) -> None:
        system_message = """
# 您的任务
今天是 {today_date}，您是一位搜索结果整合专家。基于给定的搜索任务，您需要对该任务的一组搜索结果执行全面、彻底、准确和可追溯的二次信息组织和整合，以支持后续的检索增强撰写任务。

# 输入信息
- **搜索任务**：与搜索结果对应的搜索任务。您需要围绕该任务尽可能从搜索结果中组织、整合和提取信息，细节越详细、完整越好。
- **搜索结果和简短摘要**：为搜索任务收集的一组搜索结果（网页），以XML格式表示。我将为您提供原始网页（摘要），以及一系列搜索结果的简单整合，您需要进行二次整合。原始网页是可选的。
    - search_result：每个网页的摘要和元信息。
    - web_pages_short_summary：搜索网页的**简单整合**。此整合将出现多次，每次整合覆盖此标签出现之前的搜索结果（我没有提供给您）。**index=x** 或 **id=x** 表示来源网页编号。

# 要求
- 不允许捏造——所有信息必须完全来自提供的搜索结果摘要
- 必须使用 "webpage[网页索引]" 标记信息来源以实现可追溯性，其中 web_pages_short_summary 中的 index 表示网页 ID
- 细节越详细、完整越好——细节很重要，不要丢失 **web_pages_short_summary** 中的任何详细信息
- 不要为了满足细节要求而编造内容
- 注意，并非所有网页结果都相关和有用，要仔细并整理有用的内容。

# 输出格式
1. 首先，在 <thinking> 标签内提供简短的思考
2. 在 <result></result> 标签中，输出您的二次信息组织和整合结果，必须尽可能完整、精细和彻底，并通过网页 ID 进行来源追溯
在 </result> 之后不要附加任何其他信息
""".strip()


        content_template = """
用户的整体写作任务是：**{to_run_root_question}**。该任务已被进一步分解为需要您收集信息的子写作任务：**{to_run_outer_write_task}**。

在整体写作请求和子写作任务的背景下，您需要理解您分配的搜索结果整合子任务的要求，并且只为它整合：**{to_run_search_task}**，从**搜索结果和简短摘要**中。

---
**搜索结果和简短摘要**：
```
{to_run_search_results}
```
--

按照 # 您的任务、# 输入信息和 # 要求 中的说明，组织和整合来自 **搜索结果和简短摘要** 的信息。按照 # 输出格式 输出，首先在 <thinking> 中简短思考，然后在 <result></result> 中给出完整结果。不要忘记使用 "webpage[网页索引]" 标记信息来源以实现可追溯性，其中 web_pages_short_summary 中的 index 表示网页 ID。
""".strip()
        super().__init__(system_message, content_template)

