#!/usr/bin/env python
"""测试 testData 中的向量数据是否可以正常读取"""

import sys
import os

# Fix for ChromaDB on Python 3.8 - must be done before importing chromadb
if sys.version_info < (3, 9):
    try:
        import pysqlite3
        sys.modules["sqlite3"] = pysqlite3
    except ImportError:
        pass

# Add recursive module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from recursive.knowledge_base.service import KnowledgeBaseService
from recursive.knowledge_base.vector_store import ChromaVectorStore

def test_vector_search():
    """测试向量搜索功能"""

    # 直接使用 testData 中的 chroma_data 路径
    chroma_path = os.path.join(os.path.dirname(__file__), 'testdata', 'chroma_data')

    print(f"ChromaDB 路径：{chroma_path}")
    print(f"路径存在：{os.path.exists(chroma_path)}")

    # 创建 ChromaVectorStore 实例，直接指向 testData
    store = ChromaVectorStore(persist_dir=chroma_path)

    # 列出所有 collection（通过直接访问 chromadb）
    import chromadb
    client = chromadb.PersistentClient(path=chroma_path)
    collections = client.list_collections()
    print(f"\n找到 {len(collections)} 个 collections:")
    collection_names = []
    for coll in collections:
        print(f"  - {coll.name} ({coll.count()} chunks)")
        collection_names.append(coll.name)

    if not collection_names:
        print("\n警告：未找到任何 collection！")
        return

    # 测试第一个 collection 的搜索
    test_collection_name = collection_names[0]
    print(f"\n测试搜索 collection '{test_collection_name}':")

    # 尝试几个不同的查询
    test_queries = [
        "人工智能",
        "机器学习",
        "深度学习",
        "神经网络",
        "自然语言处理",
        "大语言模型",
        "transformer",
        "attention mechanism"
    ]

    for query in test_queries:
        try:
            results = store.search(test_collection_name, query, topk=3)
            print(f"\n查询：'{query}' -> 找到 {len(results)} 条结果")
            for i, result in enumerate(results, 1):
                distance = result.get('distance', 0)
                text = result.get('text', '')[:150]
                source = result.get('source', 'unknown')
                title = result.get('title', '')
                print(f"  {i}. [距离={distance:.4f}] [{source}] {title}")
                print(f"     内容：{text}...")
        except Exception as e:
            print(f"查询 '{query}' 失败：{e}")
            import traceback
            traceback.print_exc()

    print("\n=== 测试完成! ===")
    print("\n提示：在 WriteHERE 系统中使用此知识库时，需要设置环境变量:")
    print(f"  export WRITEHERE_KB_PATH=\"{os.path.join(os.path.dirname(__file__), 'backend', 'knowledge_bases')}\"")
    print(f"  export WRITEHERE_KB_NAME=\"{test_collection_name}\"")

if __name__ == "__main__":
    test_vector_search()
