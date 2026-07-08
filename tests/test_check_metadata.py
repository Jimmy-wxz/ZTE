#!/usr/bin/env python
"""检查 ChromaDB collection 的 metadata 信息"""

import sys
import os
import json

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
client = chromadb.PersistentClient(path=chroma_path)

# 获取 collection
collection = client.get_collection(name='rag_chunks')

# 检查 collection 的 metadata
print("=== Collection Metadata ===")
print(f"Name: {collection.name}")
print(f"Count: {collection.count()}")
print(f"Collection metadata: {collection.metadata}")

# 获取一些样本数据的完整 metadata
print("\n=== Sample Document Metadata ===")
sample = collection.get(limit=1, include=["documents", "metadatas"])
if sample['metadatas'] and sample['metadatas'][0]:
    meta = sample['metadatas'][0]
    print(f"Metadata keys: {list(meta.keys())}")
    print(f"Full metadata:")
    for key, value in meta.items():
        print(f"  {key}: {value}")

# 检查 ChromaDB 的 sqlite 数据库中是否有 embedding 信息
import sqlite3
db_path = os.path.join(chroma_path, 'chroma.sqlite3')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("\n=== Database Schema ===")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
for table in tables:
    table_name = table[0]
    print(f"\nTable: {table_name}")
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  {col[1]} ({col[2]})")

# 检查 embeddings 表
cursor.execute("SELECT * FROM embeddings LIMIT 1")
try:
    row = cursor.fetchone()
    if row:
        print(f"\nSample embedding row (first 5 elements): {row[:5]}...")
        # Check if we can determine the dimension
        for i, val in enumerate(row):
            if isinstance(val, bytes) and len(val) > 100:
                print(f"  Possible embedding at index {i}, size={len(val)} bytes")
except Exception as e:
    print(f"Cannot read embeddings: {e}")

conn.close()
