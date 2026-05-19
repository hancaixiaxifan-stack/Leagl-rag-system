"""
测试修改后的 keyword 捕获率提升情况
对比修改前后的 null 比例
"""
import json
from collections import defaultdict
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.extract_citations import extract_from_chunk, clean_title
from rag_contract.settings import settings


def main():
    chunks_path = Path(settings.chunks_path)
    
    chunks = []
    with open(chunks_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
    
    # 构建 title_lookup（简化版）
    title_versions = defaultdict(list)
    for c in chunks:
        title = c['doc_title']
        cleaned = clean_title(title)
        title_versions[cleaned].append((c.get('effective_start') or '', title))
    
    title_lookup = {}
    for cleaned, versions in title_versions.items():
        versions.sort(key=lambda x: x[0], reverse=True)
        title_lookup[cleaned] = versions[0][1]
    
    # 统计 keyword 情况
    total_citations = 0
    keyword_null = 0
    keyword_filled = 0
    keyword_distribution = defaultdict(int)
    
    # 抽样：只看有 article_no 的 chunk
    sample_chunks = [c for c in chunks if c.get('article_no')]
    
    for chunk in sample_chunks[:5000]:  # 取前5000条加速测试
        cleaned_chunk_title = clean_title(chunk['doc_title'])
        current_full = title_lookup.get(cleaned_chunk_title)
        
        citations = extract_from_chunk(chunk, title_lookup, current_full)
        for cite in citations:
            total_citations += 1
            kw = cite.get('keyword')
            if kw is None:
                keyword_null += 1
            else:
                keyword_filled += 1
                keyword_distribution[kw] += 1
    
    print(f"=== Keyword 捕获统计 ===")
    print(f"总引用数: {total_citations}")
    print(f"keyword 为 null: {keyword_null} ({keyword_null/total_citations*100:.1f}%)")
    print(f"keyword 有值: {keyword_filled} ({keyword_filled/total_citations*100:.1f}%)")
    print()
    print("=== Keyword 分布 (Top 20) ===")
    for kw, cnt in sorted(keyword_distribution.items(), key=lambda x: -x[1])[:20]:
        print(f"  {cnt:4d}  {kw}")
    
    # 展示一些 keyword=null 的例子
    print()
    print("=== 仍为 null 的示例 (前10条) ===")
    null_examples = []
    for chunk in sample_chunks:
        if len(null_examples) >= 10:
            break
        cleaned_chunk_title = clean_title(chunk['doc_title'])
        current_full = title_lookup.get(cleaned_chunk_title)
        citations = extract_from_chunk(chunk, title_lookup, current_full)
        for cite in citations:
            if cite.get('keyword') is None:
                null_examples.append({
                    'text': cite['raw'][:100],
                    'law': cite['cited_law'],
                    'article': cite['cited_article'],
                })
                if len(null_examples) >= 10:
                    break
    
    for i, ex in enumerate(null_examples, 1):
        print(f"\n{i}. {ex['law']} {ex['article']}")
        print(f"   文本: {ex['text']}")


if __name__ == '__main__':
    main()
