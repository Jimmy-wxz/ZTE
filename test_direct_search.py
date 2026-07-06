#!/usr/bin/env python
"""直接测试 ChromaDB 搜索功能"""

import sys
import os

# Fix for ChromaDB on Python 3.8
if sys.version_info < (3, 9):
    try:
        import pysqlite3
        sys.modules["sqlite3"] = pysqlite3
    except ImportError:
        pass

import chromadb

chroma_path = os.path.join(os.path.dirname(__file__), 'testdata', 'chroma_data')
print(f"ChromaDB 路径：{chroma_path}")

client = chromadb.PersistentClient(path=chroma_path)

# 获取 collection
collection = client.get_collection(name='rag_chunks')
print(f"Collection: {collection.name}, 文档数：{collection.count()}")

# 测试不同的查询
test_queries = [
    "AI",
    "人工智能",
    "machine learning",
    "机器学习",
]

for query in test_queries:
    print(f"\n=== 查询：'{query}' ===")

    # 使用内置的 create_embedding 函数（如果可用）
    # 或者使用简单的平均词向量
    try:
        # 尝试使用 chromadb 的默认 embedding
        results = collection.query(
            query_texts=[query],
            n_results=3,
            include=["documents", "metadatas", "distances"]
        )

        print(f"找到 {len(results['ids'][0])} 条结果:")
        for i, (doc_id, doc, meta, dist) in enumerate(zip(
            results['ids'][0],
            results['documents'][0],
            results['metadatas'][0],
            results['distances'][0]
        ), 1):
            title = meta.get('title', '') if meta else ''
            source = meta.get('source_path', '') if meta else ''
            print(f"  {i}. [距离={dist:.4f}] [{source}] {title}")
            print(f"     内容：{doc[:150]}...")

    except Exception as e:
        print(f"查询失败：{e}")
        import traceback
        traceback.print_exc()
