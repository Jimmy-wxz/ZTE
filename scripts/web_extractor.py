#!/usr/bin/env python3
"""
网页内容提取工具
用于从指定URL获取网页内容，然后传递给LLM生成报告
"""

import requests
from bs4 import BeautifulSoup
import sys
import argparse

def extract_webpage_content(url):
    """
    从URL提取网页的纯文本内容

    Args:
        url (str): 网页URL

    Returns:
        str: 提取的网页文本内容
    """
    try:
        # 发送HTTP请求
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        # 解析HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # 移除script和style标签
        for script in soup(['script', 'style', 'nav', 'footer', 'header']):
            script.decompose()

        # 提取标题
        title = soup.title.string if soup.title else "无标题"

        # 提取正文内容（尝试常见的文章容器）
        article_containers = ['article', 'main', '.post-content', '.article-content', '.entry-content']
        content_div = None

        for container in article_containers:
            if '.' in container:
                content_div = soup.find(class_=container.split('.')[1])
            else:
                content_div = soup.find(container)
            if content_div:
                break

        # 如果没有找到特定容器，就提取所有段落
        if not content_div:
            paragraphs = soup.find_all('p')
            text = '\n\n'.join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 50])
        else:
            paragraphs = content_div.find_all('p')
            text = '\n\n'.join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 50])

        # 清理文本
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if line and len(line) > 10:  # 跳过太短的行
                lines.append(line)

        cleaned_text = '\n'.join(lines)

        return f"=== 网页标题: {title} ===\n=== 网页URL: {url} ===\n\n{cleaned_text}"

    except requests.RequestException as e:
        return f"ERROR: 无法获取网页内容 - {str(e)}"
    except Exception as e:
        return f"ERROR: 解析失败 - {str(e)}"


def main():
    parser = argparse.ArgumentParser(description='提取网页内容用于报告生成')
    parser.add_argument('url', type=str, help='要提取的网页URL')
    parser.add_argument('--output', '-o', type=str, default='', help='输出文件路径（可选）')

    args = parser.parse_args()

    print(f"正在提取网页内容: {args.url}")
    content = extract_webpage_content(args.url)

    if content.startswith("ERROR"):
        print(content)
        sys.exit(1)

    # 输出结果
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"\n内容已保存到: {args.output}")
    else:
        print("\n" + "="*80)
        print(content[:2000])  # 只显示前2000字符
        if len(content) > 2000:
            print(f"\n... (还有 {len(content)-2000} 字符)")

    # 返回内容长度信息
    print(f"\n总字符数: {len(content)}")


if __name__ == '__main__':
    main()
