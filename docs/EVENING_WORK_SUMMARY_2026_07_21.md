# 2026-07-21 至 2026-07-22 晚间工作总结

## 一、总体目标

本轮工作围绕“可审计、证据驱动、可迭代优化的企业技术报告生成系统”继续推进。项目原本已经具备 KB-first RAG、Web 辅助搜索、rerank、递归写作和实时节点状态展示能力；这次重点把它从“一次性生成报告”扩展为更接近论文系统的闭环框架：

```text
历史生成记录
-> 自适应检索策略选择
-> KB/Web 检索与 rerank
-> 报告生成
-> Evidence Graph
-> Claim-Level Verification
-> Rubric/Writer Feedback
-> Search Repair
-> 局部修复
-> 用户追问小修改
-> 新记录回写历史
```

这条链路对应之前讨论的几个研究方向：

- Evidence Graph / 层次证据图
- Claim-Level Verification / 观点级证据校验
- Rubric-Guided Writer Feedback Loop / 评分规约驱动写作反馈
- Adaptive Search Policy Learning / 基于历史表现的自适应检索策略
- Follow-up Edit / 报告生成后的追问式局部修改

## 二、Evidence Graph：从证据列表升级为证据结构图

新增 Evidence Graph 能力后，系统不再只保存一组检索结果，而是会把报告中的章节、观点、证据、引用、来源、rubric 维度建立结构化关系。

主要能力：

- 将最终报告解析为 section 节点。
- 从章节正文中抽取 claim 节点。
- 将 claim 与 `[reference:N]` citation 对应到 evidence。
- 建立 `section -> claim -> evidence -> source` 的关系。
- 统计每个章节的证据覆盖情况、KB/Web 证据占比和引用密度。
- 聚合 Evidence Unit 到 Evidence Cluster，为后续论文中的“层次证据图”提供实现基础。
- 输出 `evidence_graph.json`，用于后端接口、前端展示、实验统计和后续修复闭环。

相关价值：

- 能解释“报告中的某个观点由哪些证据支持”。
- 能发现“某个章节几乎没有引用”。
- 能作为 claim verification、writer feedback、search repair 的共同数据底座。

## 三、Claim-Level Verification：观点级证据校验

在 Evidence Graph 之上，新增了 Claim-Level Verification。它的目标是降低 RAG 长文报告中最常见的问题：当检索证据不足时，LLM 会自动补全成本、ROI、市场规模、竞品能力、CVE/0day 等高风险内容。

主要能力：

- 规则抽取包含数字、比例、年份、成本、预算、ROI、市场规模、CVE、0day、漏洞、安全风险、竞品对比等高风险句子。
- 对带引用的 claim，检查引用 evidence 是否真的能支持该 claim。
- 对未引用的高风险 claim 标记为 `unsupported` 或 `needs_review`。
- 对证据弱相关的 claim 标记为 `partially_supported`。
- 支持选择性 LLM verifier，只对高风险 claim 调用模型，避免全量逐句校验造成耗时暴涨。
- 输出 `claim_verification.json`，记录 claim 文本、章节、风险级别、支持证据和状态。

相关价值：

- 能把“报告质量不好”拆解成具体 unsupported claim。
- 能支撑后续局部重写，而不是整篇重写。
- 能为论文实验提供可量化指标，例如 unsupported claim 数量、supported claim 占比、引用有效率。

## 四、Rubric-Guided Writer Feedback Loop

新增 Writer Feedback 模块后，系统可以把 Evidence Graph、Claim Verification、Rubric Gap Check、Report Quality Audit 的结果转成可执行修复动作。

主要动作类型：

- `rewrite_or_cite_claim`：对没有证据支撑的 claim，要求改写或补引用。
- `increase_section_citations`：对低引用密度章节增加证据引用要求。
- `supplement_missing_rubric_dimension`：对缺失的 rubric 维度触发补证据。
- `supplement_web_context`：对必须依赖外部最新信息的维度记录 Web 补充需求。
- `minimal_section_rewrite`：只重写问题章节，避免整篇报告结构漂移。

Repair Loop 的策略是“局部、最小、保守”：

- 只改目标章节。
- 保留原章节标题和整体结构。
- 保留有效 citation。
- 对无证据精确数字进行弱化、删除或标注估算性质。
- 不重新生成整篇报告，控制时间和风险。

## 五、Rubric-Guided Search Repair

Search Repair 是本轮质量闭环的关键补充。之前系统即使发现缺少竞品、市场、风险等维度，也只能要求 Writer 修复；但如果原始证据池里没有材料，Writer 仍然容易编造。Search Repair 解决的是“先补证据，再局部改写”。

主要能力：

- 从 writer feedback 中读取缺口动作。
- 将缺失维度映射为定向查询，例如：
  - `competitors` -> 竞品对比、厂商分析、竞争格局
  - `market_context` -> 市场规模、趋势、行业需求
  - `technology_definition` -> 技术架构、原理、核心能力
  - `application_scenarios` -> 应用场景、落地案例、部署实践
  - `challenges` -> 风险、挑战、实施障碍
  - `strategy_recommendation` -> 路线图、策略建议、发展方向
- 默认执行轻量 KB 补检索，不默认触发 SerpAPI，避免增加外部依赖和耗时。
- 对需要 Web 的缺口保留计划项，为后续条件化 SerpAPI 补搜做准备。
- 将新增 KB chunk 注册为 evidence，分配 evidence_id 和 citation_label。
- 将新增 evidence_id 写回 writer feedback，使 Repair Loop 能使用这些新证据。
- 输出 `search_repair.json`。

相关价值：

- 解决“发现缺口但没有材料可补写”的问题。
- 让 rubric gap 从检测项变成闭环修复项。
- 后续可以扩展为 KB 不足时才触发 Web 的 cost-aware 搜索策略。

## 六、Adaptive Search Policy：历史驱动的模式选择

本轮实现了方向 3 的第一阶段：基于历史报告生成记录的 Search Mode Dispatch 优化。它不是训练模型，而是先用可解释的启发式 + 历史均值 + bandit 机制，形成一个轻量自适应策略层。

新增模块：

- `recursive/policy/history_store.py`
- `recursive/policy/feature_extractor.py`
- `recursive/policy/adaptive_policy.py`
- `recursive/policy/outcome_analyzer.py`

主要能力：

- `HistoryStore` 以 JSONL 保存历史生成记录。
- `feature_extractor` 从 prompt 中抽取任务特征：
  - 任务类型
  - 是否涉及市场/竞品
  - 是否涉及风险、成本、ROI、高风险数字
  - 是否是研究型/战略型任务
  - 语言和复杂度估计
- `policy_decision.json` 记录每次任务开始前的策略判断。
- `policy_outcome.json` 记录生成后的耗时、质量、证据覆盖、修复情况和 reward。
- 支持 `WRITEHERE_POLICY_APPLY=1` 时将策略真正应用到运行时配置。
- 支持环境变量显式配置优先于策略建议，避免自动策略覆盖人工调参。
- 引入 hybrid 策略：
  - 启发式用于冷启动。
  - 历史均值用于利用已有经验。
  - bandit exploration 用于探索历史不足但可能更优的模式。

策略可以影响：

- search mode：atom / wide / deep
- KB rerank candidate limit
- KB final top-k
- 是否启用 claim verifier
- 是否启用 repair loop
- 是否启用 search repair
- repair 最大章节数

相关价值：

- 让系统开始利用历史生成记录优化后续任务。
- 为后续论文中的 “Cost-Aware Adaptive Retrieval Policy for Agentic RAG” 提供工程基础。
- 能围绕质量与耗时做可量化权衡，而不是固定规则。

## 七、Follow-up Edit：报告生成后的追问小修改闭环

本轮新增了报告生成后的追问式局部修改能力。用户不需要重跑完整报告，可以对已有报告提出“补充竞品分析”“把路线图压缩一下”“删除没有证据的 ROI”“润色执行摘要”等小修改。

新增模块：

- `recursive/followup/intent.py`
- `recursive/followup/section_locator.py`
- `recursive/followup/editor.py`
- `recursive/followup/session_store.py`

主要能力：

- 识别 follow-up intent：
  - style
  - compress
  - expand
  - add_table
  - verify_or_cite
  - remove_unsupported
- 定位目标章节：
  - 根据用户指定章节名定位。
  - 根据关键词匹配章节标题。
  - 对证据敏感请求优先定位含 ROI、成本、市场规模、CVE 等高风险内容的章节。
- 只把目标章节、相关 evidence、风险 claim 和报告 outline 发给 follow-up editor。
- 保存报告版本：
  - `report_versions/<version_id>.md`
  - `report_versions/<version_id>.json`
  - `report_versions/latest.json`
  - `records/report.md`
- 将 follow-up edit 写入 policy history，作为后续策略学习信号。

新增后端接口：

- `POST /api/tasks/<task_id>/follow-up`
- `GET /api/tasks/<task_id>/versions`
- `GET /api/tasks/<task_id>/versions/<version_id>`

## 八、Follow-up Edit + Search Repair 集成

今晚最后一步把追问小修改和补检索接了起来。现在如果用户追问本身需要新证据，例如“补充竞品对标分析”“增加市场趋势”“补充最新案例”，系统会先触发轻量 KB Search Repair，再把新证据交给局部改写器。

主要流程：

```text
用户追问
-> intent 判断 requires_search_repair
-> 追问内容映射 rubric dimension
-> Search Repair 生成查询
-> KB 补检索
-> 新 evidence 进入 follow-up edit payload
-> 局部改写目标章节
-> 如使用新引用，则追加 Follow-up Evidence 来源段
-> 保存新版本
-> 写入历史记录
```

后端支持参数：

- `allowSearchRepair`：是否允许追问触发补检索，默认 true。
- `searchRepairTopk`：每个查询的 KB top-k。
- `searchRepairMaxQueries`：最多生成多少个补检索查询。
- `searchRepairMaxResults`：最多保留多少条新证据。
- `knowledgeBaseName`：可显式指定知识库。

如果前端或任务上下文没有传知识库名称，后端会尝试从任务的 `run.sh` 恢复 `WRITEHERE_KB_NAME` 和 KB 路径环境变量。

新增 artifact：

- `followup_search_repair.json`

相关价值：

- 用户追问不再只是“用旧材料改写”。
- 当追问需要新事实时，系统能补证据后再改。
- 追问行为和补检索结果会回写历史，后续可作为 adaptive policy 的反馈信号。

## 九、报告质量与格式修复

本轮还保留并验证了之前修过的若干质量问题：

- 表格 Markdown 规范化。
- 表格单元格内 `**粗体**` 正常渲染，避免显示成字面量 `**ABC**`。
- 执行摘要位置修复，避免插在报告中段。
- 无引用 ROI、成本、市场规模等高风险数字会被审计标出。
- KB/Web citation 可点击化。
- References 展示更清晰。

这些修复提升的是用户最终看到的报告可读性和可信度。

## 十、测试与验证

本地 `.venv` 没有安装 `pytest`，因此本轮没有安装额外依赖，而是用轻量 runner 直接导入并执行测试函数。

已通过测试范围：

- Evidence Ledger
- Evidence Graph
- Claim Verification
- Writer Feedback
- Repair Loop
- Search Repair
- Evidence Repair Pipeline
- Search Query Helpers
- Search Mode Dispatch
- Rubric Gap
- Report Quality
- Markdown Table Bold
- Markdown Tables
- Clickable References
- Adaptive Policy Decision
- Policy History Store
- Policy Outcome
- Follow-up Intent
- Follow-up Section Locator
- Follow-up Editor
- Follow-up Session Store

验证结果：

```text
ALL_LIGHTWEIGHT_TESTS_OK
FOLLOWUP_SEARCH_REPAIR_TESTS_OK
py_compile OK
git diff --check OK
```

这些测试不联网、不调用 DeepSeek、不调用 SerpAPI，主要验证代码逻辑、数据结构和闭环流程。

## 十一、当前项目能力变化

当前项目已经从一个“KB + Web 混合搜索的 RAG 报告生成器”，升级为具备以下能力的研究型系统：

- KB-first 混合检索。
- search mode 自适应分流。
- rerank 和候选池控制。
- Evidence Ledger。
- Hierarchical Evidence Graph。
- Claim-Level Verification。
- Rubric Gap Check。
- Writer Feedback。
- Search Repair。
- Report Quality Audit。
- Section-level Repair Loop。
- HistoryStore。
- Heuristic + history mean + bandit 的自适应策略。
- 报告生成后 follow-up edit。
- 追问触发补检索和局部改写。
- 版本化保存报告。
- 策略决策和策略结果可审计落盘。

## 十二、后续建议

下一阶段可以优先推进三件事：

1. 前端接入 follow-up edit UI，让用户在报告页面直接追问、查看版本、回看修改历史。
2. 将 `followup_search_repair.json`、`evidence_graph.json`、`claim_verification.json` 可视化，让用户看到每节证据覆盖和 unsupported claim。
3. 做固定 benchmark prompt，比较开启/关闭 Evidence Graph、Claim Verification、Search Repair、Adaptive Policy 后的质量和耗时差异，为论文实验准备数据。
