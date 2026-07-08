#!/bin/bash
# testData 向量库测试启动脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT" || exit 1

echo "=================================================="
echo "WriteHERE testData 向量库测试环境"
echo "=================================================="

# 检查 Python 虚拟环境
if [ ! -d "venv" ]; then
    echo "错误：未找到虚拟环境 venv"
    exit 1
fi

# 激活虚拟环境
source venv/bin/activate

# 检查是否设置了 OpenAI API Key
if [ -z "$OPENAI" ]; then
    echo ""
    echo "警告：未设置 OPENAI 环境变量"
    echo "testData 使用 1024 维向量，需要 OpenAI text-embedding-3-large 模型"
    echo ""
    echo "请设置 API Key:"
    echo "  export OPENAI='sk-your-api-key-here'"
    echo ""
    read -p "是否继续？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 设置 testData 专用的 embedding 模型
export WRITEHERE_EMBEDDING_MODEL='text-embedding-3-large'
export WRITEHERE_KB_PATH="$(pwd)/testdata"
export WRITEHERE_KB_NAME='rag_chunks'

echo ""
echo "环境配置："
echo "  - OPENAI: ${OPENAI:0:10}... (已设置)"
echo "  - Embedding Model: $WRITEHERE_EMBEDDING_MODEL"
echo "  - KB Path: $WRITEHERE_KB_PATH"
echo "  - KB Name: $WRITEHERE_KB_NAME"
echo ""

# 运行快速测试
echo "运行快速向量搜索测试..."
python -c "
import sys, os
sys.path.insert(0, '.')
if sys.version_info < (3, 9):
    try:
        import pysqlite3
        sys.modules['sqlite3'] = pysqlite3
    except ImportError:
        pass

from recursive.knowledge_base.vector_store import ChromaVectorStore

chroma_path = 'testdata/chroma_data'
store = ChromaVectorStore(persist_dir=chroma_path, embedding_model='text-embedding-3-large')

print('Testing query: AgC 平台')
results = store.search('rag_chunks', 'AgC 平台', topk=2)
print(f'Found {len(results)} results')
for i, r in enumerate(results, 1):
    title = r.get('title', '')[:50]
    print(f'  {i}. {title}')
print('测试完成!')
"

if [ $? -ne 0 ]; then
    echo ""
    echo "向量搜索测试失败，请检查配置"
    exit 1
fi

echo ""
echo "=================================================="
echo "启动后端服务器..."
echo "=================================================="
echo ""
echo "后端将在 http://localhost:5001 运行"
echo ""
echo "测试 API 端点:"
echo "  GET  /api/knowledge-base          - 列出知识库"
echo "  POST /api/test-knowledge-base/search - 搜索 testData"
echo ""
echo "按 Ctrl+C 停止服务器"
echo ""

# 启动后端服务器
python backend/server.py --port 5001
