#!/usr/bin/env python
"""测试 testData 中的向量数据搜索功能（使用 1024 维 embedding）"""

import sys
import os
import json

# Fix for ChromaDB on Python 3.8 - must be done before importing chromadb
if sys.version_info < (3, 9):
    try:
        import pysqlite3
        sys.modules["sqlite3"] = pysqlite3
    except ImportError:
        pass

# Set up environment for OpenAI embedding (1024-dim)
os.environ['OPENAI'] = os.environ.get('OPENAI', 'your-openai-api-key-here')
os.environ['WRITEHERE_EMBEDDING_MODEL'] = 'text-embedding-3-large'

# Add recursive module to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from recursive.knowledge_base.vector_store import ChromaVectorStore

def test_testdata_search():
    """测试 testData 的向量搜索功能"""

    print("=" * 60)
    print("Testing testData Vector Search")
    print("=" * 60)
    print(f"Embedding Model: text-embedding-3-large (1024-dim)")
    print(f"Collection: rag_chunks (597 documents)")
    print("=" * 60)

    # Check if OPENAI env is set
    if not os.environ.get('OPENAI'):
        print("\nWARNING: OPENAI environment variable is not set!")
        print("To use testData, you need an OpenAI API key for text-embedding-3-large.")
        print("You can skip this test and use the built-in knowledge base instead.")
        return

    # Test queries
    test_queries = [
        "AgC 平台如何使用",
        "智能体开发流程",
        "API 接口调用",
        "数据可视化",
        "权限管理",
    ]

    # Create ChromaVectorStore with OpenAI embedding
    from recursive.knowledge_base.vector_store import ChromaVectorStore

    chroma_path = os.path.join(PROJECT_ROOT, 'testdata', 'chroma_data')
    store = ChromaVectorStore(
        persist_dir=chroma_path,
        embedding_model='text-embedding-3-large'  # 1024-dim embeddings
    )

    print("\n=== Test Queries ===\n")

    for query in test_queries:
        try:
            results = store.search('rag_chunks', query, topk=3)
            print(f"Query: '{query}' -> Found {len(results)} results")
            for i, result in enumerate(results, 1):
                distance = result.get('distance', 0)
                text = result.get('text', '')[:100]
                title = result.get('title', '')
                source = result.get('source_path', '')
                print(f"  {i}. [dist={distance:.4f}] [{os.path.basename(source)}] {title}")
                print(f"     {text}...")
            print()
        except Exception as e:
            print(f"Query '{query}' FAILED: {e}")
            import traceback
            traceback.print_exc()
            print()

    print("=" * 60)
    print("Test Complete!")
    print("=" * 60)

    print("\n=== Usage in WriteHERE System ===")
    print("To use testData in WriteHERE, set these environment variables:")
    print(f"  export OPENAI='your-api-key'")
    print(f"  export WRITEHERE_EMBEDDING_MODEL='text-embedding-3-large'")
    print(f"  export WRITEHERE_KB_PATH='{os.path.join(PROJECT_ROOT, 'testdata')}'")
    print(f"  export WRITEHERE_KB_NAME='rag_chunks'")
    print("\nOr use the new API endpoint:")
    print("  POST /api/test-knowledge-base/search")
    print("  Body: {\"query\": \"your query here\", \"topk\": 5}")

if __name__ == "__main__":
    # Fix for ChromaDB on Python 3.8
    if sys.version_info < (3, 9):
        try:
            import pysqlite3
            sys.modules["sqlite3"] = pysqlite3
        except ImportError:
            pass

    test_testdata_search()
