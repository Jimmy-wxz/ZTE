# Project Structure

这个项目现在按“入口清晰、源码稳定、数据独立、产物忽略”的方式整理。

## Top Level

```text
.
├── backend/                Flask API、知识库管理接口、本地知识库数据
├── frontend/               React 可视化界面
├── recursive/              递归规划、RAG、写作、搜索、rerank、状态图核心逻辑
├── docs/                   项目说明、部署、故障排查、测试数据和优化记录
├── scripts/                辅助脚本，例如 URL 报告生成和网页提取
├── tests/                  本地 smoke/integration 测试脚本
├── test_data/              小型输入样例、测试 prompt、示例报告
├── testdata/               测试用 Chroma 向量库
├── start.sh                主启动入口
├── setup_env.sh            环境初始化入口
├── run_with_anaconda.sh    Conda 环境启动入口
├── requirements.txt        Python 依赖
├── setup.py / setup.cfg    Python 包配置
└── README.md               项目首页说明
```

## Important Subdirectories

- `backend/knowledge_bases/`: 后端知识库目录，包含 demo/test KB 和恢复回来的 large KB Chroma 数据。大型 Chroma 二进制数据保留在本地，已加入 `.gitignore`，避免再次上传失败。
- `recursive/agent/`: 写作、检索、规划等 agent 编排逻辑。
- `recursive/executor/`: action 执行器、搜索 agent、知识库 action。
- `recursive/knowledge_base/`: Chroma 向量库服务和检索封装。
- `recursive/llm/`: LLM provider 接入。
- `recursive/evaluation/`: 评估框架代码。运行结果会生成到 `recursive/evaluation/results/`，该目录已加入 `.gitignore`。
- `test_data/examples/`: 示例报告和 PDF 等较大的演示文件。
- `test_data/prompts/`: 可复用的测试 prompt。

## Ignored Generated Files

以下内容是运行产物，不再作为项目源码管理：

- `*.log`
- `temp/`
- `recursive/cache/`
- `recursive/records/`
- `recursive/evaluation/results/`
- `backend/results/`
- `backend/knowledge_bases/large_kb/chroma_data/`
- `testdata/chroma_data/`
- `testdata/chroma_data_backup/`
- `testdata_report.json`
- `web_report_output.jsonl`
- `web_report_done.txt`
