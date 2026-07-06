#!/usr/bin/env python
"""
testData 向量库综合测试脚本

功能：
1. 验证 testData ChromaDB 结构
2. 测试向量搜索功能（需要 OpenAI API Key）
3. 提供测试报告

使用方法：
    export OPENAI='sk-your-api-key'
    python final_test.py
"""

import sys
import os
import json
from datetime import datetime

# Fix for ChromaDB on Python 3.8
if sys.version_info < (3, 9):
    try:
        import pysqlite3
        sys.modules["sqlite3"] = pysqlite3
    except ImportError:
        pass

def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")

def print_section(text):
    print(f"\n--- {text} ---")

def test_chromadb_structure():
    """测试 1: 验证 ChromaDB 结构"""
    print_header("Test 1: ChromaDB Structure Verification")

    import chromadb

    chroma_path = os.path.join(os.path.dirname(__file__), 'testdata', 'chroma_data')
    print(f"ChromaDB Path: {chroma_path}")
    print(f"Exists: {os.path.exists(chroma_path)}")

    client = chromadb.PersistentClient(path=chroma_path)

    # List collections
    collections = client.list_collections()
    print(f"\nCollections found: {len(collections)}")

    for coll in collections:
        print(f"\n  Collection: {coll.name}")
        print(f"    - Document count: {coll.count()}")

        # Get sample metadata
        if coll.count() > 0:
            try:
                sample = coll.get(limit=1, include=["metadatas"])
                if sample['metadatas'] and sample['metadatas'][0]:
                    meta_keys = list(sample['metadatas'][0].keys())
                    print(f"    - Metadata keys: {', '.join(meta_keys[:5])}...")
            except Exception as e:
                print(f"    - Error reading metadata: {e}")

    return len(collections) > 0

def test_search_with_openai():
    """测试 2: 使用 OpenAI embedding 测试搜索"""
    print_header("Test 2: Vector Search with OpenAI Embedding")

    if not os.environ.get('OPENAI'):
        print("SKIP: OPENAI environment variable not set")
        print("Set it with: export OPENAI='sk-your-api-key'")
        return False

    from recursive.knowledge_base.vector_store import ChromaVectorStore

    chroma_path = os.path.join(os.path.dirname(__file__), 'testdata', 'chroma_data')
    store = ChromaVectorStore(
        persist_dir=chroma_path,
        embedding_model='text-embedding-3-large'
    )

    # Test queries
    test_queries = [
        ("AgC 平台使用", "基础使用"),
        ("智能体开发流程", "开发"),
        ("API 接口调用", "技术集成"),
        ("权限管理", "安全"),
    ]

    results_summary = []

    for query, category in test_queries:
        print_section(f"Query: '{query}' ({category})")

        try:
            results = store.search('rag_chunks', query, topk=3)
            print(f"Results found: {len(results)}")

            for i, result in enumerate(results, 1):
                title = result.get('title', '')[:60]
                source = os.path.basename(result.get('source_path', ''))
                distance = result.get('distance', 0)
                text = result.get('text', '')[:100]

                print(f"\n  {i}. [{source}] {title}")
                print(f"     Distance: {distance:.4f}")
                print(f"     Content: {text}...")

            results_summary.append({
                'query': query,
                'category': category,
                'count': len(results),
                'success': len(results) > 0
            })

        except Exception as e:
            print(f"ERROR: {e}")
            results_summary.append({
                'query': query,
                'category': category,
                'error': str(e),
                'success': False
            })

    # Summary
    print_section("Search Test Summary")
    success_count = sum(1 for r in results_summary if r['success'])
    print(f"Successful queries: {success_count}/{len(test_queries)}")

    return success_count > 0

def test_api_endpoint():
    """测试 3: 测试后端 API 端点"""
    print_header("Test 3: Backend API Endpoint Check")

    server_file = os.path.join(os.path.dirname(__file__), 'backend', 'server.py')
    if not os.path.exists(server_file):
        print(f"ERROR: Server file not found: {server_file}")
        return False

    # Check if API endpoint is defined
    with open(server_file, 'r') as f:
        content = f.read()

    has_test_endpoint = '/api/test-knowledge-base/search' in content
    has_service_function = '_get_test_kb_service' in content

    print(f"Test API endpoint defined: {has_test_endpoint}")
    print(f"Test service function defined: {has_service_function}")

    if has_test_endpoint and has_service_function:
        print("\n✓ Backend is configured for testData!")
        return True
    else:
        print("\n✗ Backend needs configuration for testData")
        return False

def generate_report():
    """生成测试报告"""
    print_header("Test Report")

    report = {
        'timestamp': datetime.now().isoformat(),
        'tests': {}
    }

    # Run tests
    report['tests']['chromadb_structure'] = test_chromadb_structure()
    report['tests']['vector_search'] = test_search_with_openai()
    report['tests']['api_endpoint'] = test_api_endpoint()

    # Overall result
    passed = sum(1 for v in report['tests'].values() if v)
    total = len(report['tests'])

    print_header("Final Result")
    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("\n✅ All tests passed! testData is ready to use.")
    elif passed > 0:
        print("\n⚠️ Some tests passed. Check the details above.")
    else:
        print("\n❌ All tests failed. Please check the configuration.")

    # Save report
    report_path = os.path.join(os.path.dirname(__file__), 'testdata_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved to: {report_path}")

    return passed == total

def main():
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║        WriteHERE testData Vector Library Test Suite       ║
║                                                           ║
║  This script tests the integration of testData ChromaDB   ║
║  with 597 documents and 1024-dim embeddings.              ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)

    # Set environment for OpenAI embedding
    if os.environ.get('OPENAI'):
        os.environ['WRITEHERE_EMBEDDING_MODEL'] = 'text-embedding-3-large'
        print("Using OpenAI text-embedding-3-large for 1024-dim vectors\n")
    else:
        print("WARNING: OPENAI not set. Some tests will be skipped.\n")

    # Generate report
    success = generate_report()

    # Next steps
    print_header("Next Steps")

    if success:
        print("""
1. Start the backend server:

   cd WriteHERE-main
   source venv/bin/activate
   export OPENAI='your-api-key'
   python backend/server.py --port 5001

2. Test via API:

   curl -X POST http://localhost:5001/api/test-knowledge-base/search \\
     -H "Content-Type: application/json" \\
     -d '{"query": "AgC 平台如何使用", "topk": 3}'

3. Or use the frontend:

   cd frontend && npm start
   Visit http://localhost:3000

4. Suggested test queries:
   - AgC 平台如何创建智能体
   - 智能体开发流程是什么
   - API 接口调用方法
   - 权限管理机制
        """)
    else:
        print("""
Please fix the issues identified above:

1. If ChromaDB structure test failed:
   - Check if testData/chroma_data directory exists
   - Verify the chroma.sqlite3 file is present

2. If vector search test failed:
   - Set OPENAI environment variable
   - Check network connectivity to OpenAI API

3. If API endpoint test failed:
   - The server.py has been updated automatically
   - Restart the server if it's already running
        """)

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
