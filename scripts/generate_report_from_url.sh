#!/bin/bash
# 从指定URL生成报告的脚本
# 用法: ./scripts/generate_report_from_url.sh "https://example.com/article" "报告主题"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ $# -lt 1 ]; then
    echo "用法: $0 <网页URL> [报告主题]"
    echo ""
    echo "示例:"
    echo "  $0 'https://zh.wikipedia.org/wiki/人工智能'"
    echo "  $0 'https://example.com/ai-article' '分析人工智能的发展趋势'"
    exit 1
fi

URL="$1"
TOPIC="${2:-请根据上述网页内容生成一份详细的分析报告}"

echo "========================================="
echo "📄 网页内容提取与报告生成工具"
echo "========================================="
echo ""

# 1. 提取网页内容
echo "步骤 1/3: 正在提取网页内容..."
python3 "$SCRIPT_DIR/web_extractor.py" "$URL" --output /tmp/webpage_content.txt

if [ $? -ne 0 ]; then
    echo "❌ 网页内容提取失败"
    exit 1
fi

CONTENT_LENGTH=$(wc -c < /tmp/webpage_content.txt)
echo "✅ 成功提取网页内容 ($CONTENT_LENGTH 字符)"
echo ""

# 2. 创建输入文件
echo "步骤 2/3: 准备报告生成任务..."
INPUT_FILE="/tmp/report_input.jsonl"
cat > "$INPUT_FILE" << EOF
{"id": "web-report-$(date +%s)", "topic": "", "intent": "", "domain": "", "prompt": "$TOPIC\n\n---\n\n请参考以下网页内容进行分析:\n\n$(cat /tmp/webpage_content.txt | head -c 15000)"}
EOF

echo "✅ 输入文件已准备"
echo ""

# 3. 运行报告生成
echo "步骤 3/3: 开始生成报告..."
source "$PROJECT_ROOT/venv/bin/activate"
cd "$PROJECT_ROOT/recursive"

OUTPUT_FILE="$PROJECT_ROOT/web_report_output.jsonl"
DONE_FILE="$PROJECT_ROOT/web_report_done.txt"

python engine.py \
  --filename "$INPUT_FILE" \
  --output-filename "$OUTPUT_FILE" \
  --done-flag-file "$DONE_FILE" \
  --model deepseek-chat \
  --engine-backend none \
  --mode report

if [ -f "$DONE_FILE" ]; then
    echo ""
    echo "========================================="
    echo "✅ 报告生成完成!"
    echo "========================================="
    echo ""
    echo "输出文件: $OUTPUT_FILE"
    echo ""
    echo "查看报告内容:"
    echo "  cat $OUTPUT_FILE | python3 -m json.tool"
    echo ""
    echo "或者在Web界面查看历史记录"
else
    echo "❌ 报告生成失败"
    exit 1
fi
