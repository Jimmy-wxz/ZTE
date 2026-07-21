#!/usr/bin/env python3
from recursive.agent.prompts.base import PromptTemplate
from recursive.agent.prompts.base import prompt_register
from datetime import datetime

now = datetime.now()

@prompt_register.register_module()
class ReportPlanning(PromptTemplate):
    def __init__(self) -> None:
        system_message = ""
        content_template = """
需要进一步规划的写作任务：
{to_run_task}

参考规划：
{to_run_candidate_plan}

参考思考：
{to_run_candidate_think}
---

整体规划：
```
{to_run_full_plan}
```
---

已完成的分析任务结果：
```
{to_run_outer_graph_dependent}

{to_run_same_graph_dependent}
```
---


已撰写的报告内容：
```
{to_run_article}
```
---

# 整体介绍
您是一位递归的专业报告撰写和信息检索规划专家，专门基于深度研究、搜索和分析来规划专业报告撰写。已经有一个适合用户知识问题解决需求的高级计划，您的任务是在此框架内进一步递归规划指定的写作子任务。通过您的规划，生成的报告将严格遵守用户要求，在分析、逻辑和内容深度方面达到完美。

1. 为指定的专业报告撰写子任务继续递归规划。根据研究和分析理论，将报告撰写的组织和分析任务的结果分解为更细粒度的写作子任务，指定其范围和具体的撰写内容。
2. 根据需要规划分析子任务和搜索子任务，以协助和支持特定的撰写。分析子任务可以包括设计大纲、详细大纲、数据分析、信息组织、逻辑结构构建和关键论点确定等任务，以支持实际撰写。搜索子任务负责从互联网收集必要的信息和数据。
3. 为每个任务规划子任务的有向无环图（DAG），其中边表示同一层DAG内搜索和分析任务之间的依赖关系。递归规划每个子任务，直到所有子任务都成为原子任务。

# 任务类型
## 撰写（核心，实际撰写）
- **功能**：按照计划顺序执行实际的报告撰写任务。基于具体的撰写要求和已撰写的内容，结合分析任务和搜索任务的结论继续撰写。
- **所有撰写任务都是延续任务**：在规划期间确保与前内容的连续性和逻辑一致性。撰写任务应相互流畅无缝地连接，保持报告的整体连贯性和统一性。
- **可分解任务**：撰写、分析、搜索
- 默认以快速生成和覆盖关键要点为优先，每个撰写子任务建议控制在 800-1200 字，只有用户明确要求长篇报告时才规划更长篇幅。

## 分析
- **功能**：分析和设计实际报告撰写之外的任何需求。这包括但不限于研究计划设计、设计大纲、详细大纲、数据分析、信息组织、逻辑结构构建、关键论点确定等，以支持实际撰写。
- **可分解任务**：分析、搜索

## 搜索
- **功能**：执行信息收集任务，包括从互联网收集必要的数据、材料和信息，以支持分析和撰写任务。
- **可分解任务**：搜索

# 规划提示
# 快速模式约束
- 默认生成浅层规划：优先规划 1 个搜索任务、1 个分析任务和 1-3 个撰写任务。
- 除非用户明确要求长篇深度报告，不要为撰写任务继续嵌套子任务；让撰写任务直接成为可执行的原子任务。
- 把必要的结构要求、章节范围和引用要求写进撰写任务的 `goal`，而不是继续递归拆分。

1. 从撰写任务派生的最后一个子任务必须始终是撰写任务。
2. 合理控制DAG每一层中子任务的数量，**默认3-5个子任务**；速度优先时不要超过 5 个子任务。
3. **分析任务**和**搜索任务**优先放在顶层，为后续撰写任务提供共同依据，避免在每个撰写任务内部重复规划搜索和分析。
4. 使用 `dependency` 列出同一层DAG内分析任务和搜索任务的ID。尽可能全面地列出所有潜在的依赖关系。
5. **当分析子任务涉及设计具体的撰写结构时，后续依赖的撰写任务应直接执行，并在 goal 中承接该结构。**
6. **不要冗余规划 `整体规划` 中已覆盖的任务或复制 `已撰写的报告内容` 和先前分析任务中已存在的内容。**
7. 遵循分析任务和搜索任务的结果。
8. 搜索任务目标仅指定信息需求，不指定来源或指定如何搜索。
**9**。除非用户指定，否则每个撰写任务的长度应为 800-1200 字；不要主动规划 2000 字以上的单个撰写任务。

# 任务属性（必需）
1. **id**：子任务的唯一标识符，表示其级别和任务编号。
2. **goal**：子任务目标的精确和完整描述，以字符串格式。
3. **dependency**：同一层DAG中此任务依赖的搜索和分析任务的ID列表。尽可能全面地列出所有潜在的依赖关系。如果没有依赖的子任务，这应该是空的。
4. **task_type**：表示任务类型的字符串。撰写任务标记为 `write`，分析任务标记为 `think`，搜索任务标记为 `search`。
5. **length**：对于撰写任务，此属性指定范围。撰写任务需要此属性。分析任务和搜索任务不需要此属性。
6. **sub_tasks**：表示子任务DAG的JSON列表。列表中的每个元素是代表任务的JSON对象。

# 示例
<example index=1>
用户给定的撰写任务：
{{
    "id": "",
    "task_type": "write",
    "goal": "生成详细的商业传记以记录DeepSeek的崛起",
    "length": "8600字"
}}

提供一个部分完成的递归全局规划作为参考，以递归嵌套的JSON结构表示。`sub_tasks` 字段表示任务规划的DAG（有向无环图）。如果 `sub_tasks` 为空，则表示原子任务或尚未进一步规划的任务：

{{"id":"root","task_type":"write","goal":"生成详细的商业传记以记录DeepSeek的崛起","dependency":[],"length":"8600字","sub_tasks":[{{"id":"1","task_type":"search","goal":"简要收集DeepSeek的公司信息，包括：创始团队背景、成立时间、融资历史、产品发展历程、技术突破、市场表现等关键信息，以确定文章整体结构","dependency":[],"sub_tasks":[]}},{{"id":"2","task_type":"think","goal":"分析DeepSeek的发展轨迹和成功因素，识别关键里程碑事件，设计传记的整体结构和关键内容","dependency":["1"],"sub_tasks":[]}},{{"id":"3","task_type":"write","goal":"基于搜索结果和设计的整体结构与关键内容撰写传记内容","length":"8600字","dependency":["1","2"],"sub_tasks":[{{"id":"3.1","task_type":"write","goal":"撰写创始人和团队背景章节，重点关注梁文锋的量化投资经验和团队特点","length":"1200字","dependency":[],"sub_tasks":[{{"id":"3.1.1","task_type":"search","goal":"收集梁文锋在幻方量化经历的详细信息，包括创业过程、量化投资成就、技术积累等","dependency":[]}},{{"id":"3.1.2","task_type":"search","goal":"收集DeepSeek创始团队的详细背景信息，收集幻方量化的AI技术储备信息，特别是'萤火'系列超算平台的细节","dependency":[]}},{{"id":"3.1.3","task_type":"write","goal":"完成创始人和团队特点章节的撰写，突出梁文锋的量化投资成就和AI布局，以及年轻团队组成和技术实力","length":"1200字","dependency":["3.1.1","3.1.2"]}}]}},{{"id":"3.2","task_type":"write","goal":"撰写公司成立和初期愿景章节，描述2023年创业背景和定位","length":"1000字","dependency":[],"sub_tasks":[{{"id":"3.2.1","task_type":"search","goal":"收集2023年AI行业背景材料，搜索梁文锋选择AI赛道的深层原因，特别是DeepSeek的差异化定位","dependency":[],"sub_tasks":[]}},{{"id":"3.2.1","task_type":"write","goal":"撰写关于创业背景和时代机遇，以及初期战略定位和技术路线选择的内容，特别是梁文锋选择AI赛道的深层原因，以及DeepSeek的差异化定位","length":"1000字","dependency":["3.2.1"],"sub_tasks":[]}}]}},{{"id":"3.3","task_type":"write","goal":"撰写关键发展节点章节，详细说明V2、V3和R1三个重要产品的发布和影响","length":"1800字","dependency":[],"sub_tasks":[{{"id":"3.3.1","task_type":"search","goal":"收集DeepSeek V2、V3和R1发布的详细信息及其对行业的影响","dependency":[]}},{{"id":"3.3.2","task_type":"think","goal":"分析三个产品的技术进步路径及其对行业的影响","dependency":["3.3.1"]}},{{"id":"3.3.3","task_type":"write","goal":"撰写章节，包括三个部分：V2触发价格战、V3震撼发布和R1推理突破","length":"1800字","dependency":["3.3.1","3.3.2"],"sub_tasks":[]}}]}},{{"id":"3.4","task_type":"write","goal":"基于已撰写的V2、V3和R1的发布和影响，进一步撰写核心技术和产品优势章节，分析竞争力来源","length":"1500字","dependency":[],"sub_tasks":[{{"id":"3.4.1","task_type":"search","goal":"收集DeepSeek技术创新、算力优化方案和工程创新的信息","dependency":[],"sub_tasks":[]}},{{"id":"3.4.2","task_type":"write","goal":"基于收集的材料和分析结论，撰写关于模型架构创新、软硬件协同优化和模型优化与蒸馏策略的内容","length":"1500字","dependency":["3.4.1"],"sub_tasks":[]}}]}},{{"id":"3.5","task_type":"write","goal":"撰写市场竞争格局和商业策略章节，分析与国内外竞争对手的博弈","length":"1200字","dependency":[],"sub_tasks":[{{"id":"3.5.1","task_type":"search","goal":"收集国内外主要大模型公司（百度、阿里等）的产品策略和市场表现","dependency":[],"sub_tasks":[]}},{{"id":"3.5.2","task_type":"search","goal":"收集和分析DeepSeek与其他大模型公司的差异化竞争策略","dependency":["3.5.1","3.5.2"],"sub_tasks":[]}},{{"id":"3.5.3","task_type":"write","goal":"基于收集的材料和分析结论，撰写国内竞争格局、国际竞争力和影响力分析，以及商业策略创新分析","length":"1200字","dependency":["3.5.1","3.5.2"],"sub_tasks":[]}}]}},{{"id":"3.6","task_type":"write","goal":"进一步撰写行业影响和外部反响章节，总结DeepSeek的社会影响力","length":"1000字","dependency":[],"sub_tasks":[]}},{{"id":"3.7","task_type":"write","goal":"撰写未来展望章节，预测DeepSeek的发展方向和挑战","length":"900字","dependency":[],"sub_tasks":[{{"id":"3.7.1","task_type":"search","goal":"收集DeepSeek官方透露的未来发展计划和目标","dependency":[],"sub_tasks":[]}},{{"id":"3.7.2","task_type":"write","goal":"基于收集的材料和分析结论，撰写未来展望章节，包括未来计划、技术创新展望、生态建设展望、人才战略展望和国际化展望","length":"900字","dependency":["3.7.1"],"sub_tasks":[]}}]}}]}}
</example>

# 输出格式
1. 首先，在 <thinking> 中进行深入和全面的思考。
2. 在 `<result></result>` 中，按照示例中所示的JSON格式输出规划结果。顶层对象应代表给定任务，其 `sub_tasks` 为规划的结果。具体格式如下：
<thinking>
思考继续撰写的内容
</thinking>

<result>
在此撰写
</result>

---
需要进一步规划的写作任务，按照之前的要求，按照 # 输出格式 输出，首先在 <thinking> 中思考，然后直接在 <result></result> 中以该格式给出结果，不要忘记递归规划：
**{to_run_task}**
"""
        content_template += """

---
Evidence-grounded report planning constraints:
* If the report contains an Executive Summary, plan it immediately after the title and before the first numbered chapter.
* Plan shared search tasks for competitor benchmarking, market data, security incidents, costs, ROI, and named vulnerabilities so downstream writing tasks can cite retrieved evidence.
* Do not ask writers to produce exact budgets, ROI, market sizes, CVE details, or vendor security capabilities unless a dependent search/analysis task can provide evidence. Otherwise ask writers to mark them as estimates / needs validation.
"""
        super().__init__(system_message, content_template)
