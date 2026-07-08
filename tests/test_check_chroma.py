#!/usr/bin/env python
"""检查 testData 中 ChromaDB 的实际结构"""

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

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
chroma_path = os.path.join(PROJECT_ROOT, 'testdata', 'chroma_data')
print(f"ChromaDB 路径：{chroma_path}")
print(f"路径存在：{os.path.exists(chroma_path)}")

client = chromadb.PersistentClient(path=chroma_path)

# 列出所有 collections
print("\n=== ChromaDB Collections ===")
try:
    collections = client.list_collections()
    print(f"找到 {len(collections)} 个 collections:")
    for coll in collections:
        print(f"  - {coll.name}")
        print(f"    文档数量：{coll.count()}")

        # 尝试获取一些样本数据
        if coll.count() > 0:
            try:
                sample = coll.get(limit=2, include=["documents", "metadatas"])
                print(f"    样本 ID: {sample['ids']}")
                if sample['metadatas'] and sample['metadatas'][0]:
                    print(f"    样本 metadata keys: {list(sample['metadatas'][0].keys())}")
            except Exception as e:
                print(f"    无法获取样本：{e}")
except Exception as e:
    print(f"列出 collections 失败：{e}")
