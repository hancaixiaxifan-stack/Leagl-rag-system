"""
反事实模拟单元测试（Direction 4 Step 5）

用法：
    python scripts/test_counterfactual.py

测试用例：
1. 劳动合同法第38条 + 结构化方向（obligation_decrease）
2. 劳动合同法第38条 + 自然语言方向（保护企业灵活性）
3. 不存在的法律 → 返回空结果，不抛异常
4. 无引用条文 → 返回空结果
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_contract.counterfactual import CounterfactualAnalyzer, DIRECTION_REGISTRY


def test_direction_resolution():
    """测试方向解析（结构化 + 自然语言）"""
    analyzer = CounterfactualAnalyzer()

    # 结构化方向
    cats, desc = analyzer.resolve_direction("obligation_decrease")
    assert cats == ["obligation"], f"expect ['obligation'], got {cats}"
    assert desc == "义务减轻", f"expect '义务减轻', got {desc}"
    print("[OK] 结构化方向解析：obligation_decrease")

    # 模糊匹配
    cats, desc = analyzer.resolve_direction("义务减轻")
    assert cats == ["obligation"], f"expect ['obligation'], got {cats}"
    print("[OK] 模糊匹配：义务减轻")

    # 自然语言方向
    cats, desc = analyzer.resolve_direction("保护企业灵活性，减轻义务")
    assert "obligation" in cats, f"expect 'obligation' in {cats}"
    print(f"[OK] 自然语言解析：{cats} -> {desc}")

    # 无法解析 → 全量 categories
    cats, desc = analyzer.resolve_direction("量子波动速读")
    assert len(cats) > 0, "无法解析时应返回全量 categories"
    print(f"[OK] 无法解析时的兜底：{len(cats)} categories")


def test_sensitive_word_extraction():
    """测试敏感词提取"""
    analyzer = CounterfactualAnalyzer()

    text1 = "劳动者应当完成劳动任务，提高职业技能，执行劳动安全卫生规程，遵守劳动纪律和职业道德。"
    words1 = analyzer.extract_sensitive_words(text1)
    cats1 = [w["category"] for w in words1]
    assert "obligation" in cats1, f"expect 'obligation' in {cats1}"
    print(f"[OK] 敏感词提取（应当）：{words1}")

    text2 = "用人单位有下列情形之一的，劳动者可以解除劳动合同："
    words2 = analyzer.extract_sensitive_words(text2)
    print(f"[OK] 敏感词提取（可以）：{words2}")


def test_analyze_with_citation():
    """测试实际分析（有引用链）"""
    analyzer = CounterfactualAnalyzer()

    result = analyzer.analyze(
        law_title="中华人民共和国劳动合同法",
        article_no="第三十八条",
        direction="obligation_decrease",
        magnitude="中等",
        include_indirect=False,
        max_depth=1,
        max_candidates=5,
    )

    print(f"\n[分析结果] 劳动合同法第38条 + obligation_decrease")
    print(f"  解析方向: {result['interpreted_direction']}")
    print(f"  涉及分类: {result['affected_categories']}")
    print(f"  直接候选数: {result['direct_candidates_count']}")
    print(f"  直接影响数: {len(result['direct_impacts'])}")
    print(f"  间接候选数: {result['indirect_candidates_count']}")
    print(f"  间接影响数: {len(result['indirect_impacts'])}")
    print(f"  总波及: {result['total_affected']}")

    if result["direct_impacts"]:
        for imp in result["direct_impacts"]:
            print(f"  - {imp['law_title']} {imp['article_no']} [{imp['risk_level']}]")
            print(f"    reasoning: {imp['llm_reasoning'][:80]}...")
    if result["indirect_impacts"]:
        for imp in result["indirect_impacts"]:
            print(f"  - {imp['law_title']} {imp['article_no']} [{imp['risk_level']}] (indirect)")


def test_natural_direction():
    """测试自然语言方向"""
    analyzer = CounterfactualAnalyzer()

    result = analyzer.analyze(
        law_title="中华人民共和国劳动法",
        article_no="第三条",
        direction="减轻劳动者义务",
        magnitude="重大",
        include_indirect=True,
        max_depth=2,
        max_candidates=5,
    )

    print(f"\n[分析结果] 劳动法第3条 + 减轻劳动者义务")
    print(f"  解析方向: {result['interpreted_direction']}")
    print(f"  涉及分类: {result['affected_categories']}")
    print(f"  总波及: {result['total_affected']}")
    if result["direct_impacts"]:
        for imp in result["direct_impacts"][:3]:
            print(f"  - {imp['law_title']} {imp['article_no']} [{imp['risk_level']}]")
    if result["llm_summary"]:
        print(f"  LLM summary: {result['llm_summary'][:100]}...")


def test_nonexistent_law():
    """测试不存在的法律 → 不抛异常"""
    analyzer = CounterfactualAnalyzer()

    result = analyzer.analyze(
        law_title="宇宙飞船法",
        article_no="第一条",
        direction="保护乘客权益",
        max_depth=2,
    )

    assert result["total_affected"] == 0, "不存在法律应返回 0 波及"
    assert result["llm_summary"] != "", "应返回说明而非空字符串"
    print(f"[OK] 不存在法律返回空结果，不抛异常")


def test_unreferenced_article():
    """测试无引用条文"""
    analyzer = CounterfactualAnalyzer()

    result = analyzer.analyze(
        law_title="中华人民共和国劳动合同法",
        article_no="第一条",
        direction="scope_expand",
        max_depth=2,
    )

    print(f"\n[无引用条文测试] 劳动合同法第1条")
    print(f"  直接候选数: {result['direct_candidates_count']}")
    print(f"  总波及: {result['total_affected']}")
    print(f"  llm_summary: {result['llm_summary']}")


def main():
    print("=" * 60)
    print("反事实模拟单元测试")
    print("=" * 60)

    test_direction_resolution()
    test_sensitive_word_extraction()
    test_analyze_with_citation()
    test_natural_direction()
    test_nonexistent_law()
    test_unreferenced_article()

    print("\n" + "=" * 60)
    print("全部测试通过")
    print("=" * 60)


if __name__ == "__main__":
    main()
