"""
反事实模拟分析器（Direction 4）

CounterfactualAnalyzer 利用 SensitiveWordDelta 分类体系 + DominoAnalyzer 引用链 + DeepSeek LLM，
实现"如果将某条文向某个方向偏移，会波及哪些条文"的立法仿真分析。

核心流程：
1. 目标条文解析：提取条文中的敏感词及其 category
2. 方向解析：将用户输入的方向映射到受影响的 sensitive word categories
3. 下游候选筛选：沿引用链找到下游条文，筛选出含同类敏感词的候选
4. LLM 深度分析：构建 prompt，让 LLM 判断波及范围和风险
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

import jieba

from .lineage import SENSITIVE_WORD_CATEGORIES, classify_word
from .domino import DominoAnalyzer
from .llm_client import LLMAuthError, chat_answer
from .prompting import COUNTERFACTUAL_SYSTEM_PROMPT

# ----------------------------------------------------------------------
# 偏移方向结构化映射
# ----------------------------------------------------------------------
DIRECTION_REGISTRY: dict[str, dict] = {
    "obligation_increase":  {"affected": ["obligation"], "desc": "义务加重", "polarity": "+"},
    "obligation_decrease":  {"affected": ["obligation"], "desc": "义务减轻", "polarity": "-"},
    "scope_expand":         {"affected": ["scope"],      "desc": "范围扩大", "polarity": "+"},
    "scope_narrow":         {"affected": ["scope"],      "desc": "范围缩小", "polarity": "-"},
    "threshold_raise":      {"affected": ["threshold"],  "desc": "门槛提高", "polarity": "+"},
    "threshold_lower":      {"affected": ["threshold"],  "desc": "门槛降低", "polarity": "-"},
    "right_strengthen":     {"affected": ["right"],      "desc": "权利强化", "polarity": "+"},
    "right_weaken":         {"affected": ["right"],      "desc": "权利弱化", "polarity": "-"},
    "procedure_tighten":    {"affected": ["procedure"],  "desc": "程序收紧", "polarity": "+"},
    "procedure_loosen":     {"affected": ["procedure"],  "desc": "程序放宽", "polarity": "-"},
    "protection_shift":     {"affected": ["obligation", "right", "scope"], "desc": "保护重心转移", "polarity": "~"},
}

# 自然语言方向 keyword 映射（用于未命中结构化方向时的兜底解析）
_NATURAL_DIRECTION_KEYWORDS: dict[str, list[str]] = {
    "obligation": ["义务", "责任", "应当", "必须", "不得", "禁止"],
    "scope":      ["范围", "扩大", "缩小", "所有", "任何", "仅", "仅限"],
    "threshold":  ["门槛", "标准", "以上", "以下", "不超过", "不低于", "不少于"],
    "right":      ["权利", "有权", "允许", "保护", "强化", "弱化"],
    "procedure":  ["程序", "步骤", "方式", "手续", "流程", "时限"],
}

# 极性 keyword（用于判断方向是加强还是减弱）
_POLARITY_POSITIVE = ["加重", "加强", "强化", "扩大", "提高", "增加", "收紧", "上升", "严格"]
_POLARITY_NEGATIVE = ["减轻", "减弱", "弱化", "缩小", "降低", "减少", "放宽", "下降", "宽松"]

 # ------------------------------------------------------------------
 # 反事实模拟分析器
 # ------------------------------------------------------------------
class CounterfactualAnalyzer:
    """反事实模拟分析器"""

    # ------------------------------------------------------------------
    def __init__(
        self,    # 初始化
        chunks_path: str | Path | None = None,  # 法律条文文件路径
        domino_analyzer: DominoAnalyzer | None = None,  # DominoAnalyzer 实例
    ):
        self.chunks_path = Path(chunks_path) if chunks_path else Path("data/chunks.jsonl")  # 法律条文文件路径
        self._chunks_by_key: dict[str, dict] = {}    # 法律条文缓存，键为标题+文章号
        self._loaded = False    # 是否已加载数据
        self._domino = domino_analyzer    # 引用链分析器

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:    # 确保数据已加载
        if self._loaded:    # 如果已加载，直接返回
            return
        if self.chunks_path.exists():    # 如果文件存在，则加载数据
            with open(self.chunks_path, "r", encoding="utf-8") as f:    # 读取文件
                for line in f:    # 遍历文件行
                    d = json.loads(line.strip())    # 解析 JSON 行
                    key = self._make_chunk_key(d.get("doc_title", ""), d.get("article_no", ""))    # 生成键
                    # 只保留最新版本（按 effective_start 倒序，后写入覆盖）
                    existing = self._chunks_by_key.get(key)    # 获取缓存中的条文
                    # 如果不存在或当前条文 effective_start 较新，则更新缓存
                    if existing is None or (d.get("effective_start") or "") > (existing.get("effective_start") or ""):    # 比较 effective_start 时间戳
                        self._chunks_by_key[key] = d
        self._loaded = True    # 标记为已加载

    @staticmethod    # 生成条文键名
    def _make_chunk_key(doc_title: str, article_no: str) -> str:    # 生成条文键名
        return f"《{doc_title}》{article_no}"    # 生成键名

    def _get_chunk_text(self, law_title: str, article_no: str) -> str | None:    # 获取条文文本
        self._ensure_loaded()    # 确保数据已加载
        key = self._make_chunk_key(law_title, article_no)    # 生成键名
        d = self._chunks_by_key.get(key)    # 获取缓存中的条文
        return d.get("text") if d else None    # 返回文本或 None

    # ------------------------------------------------------------------
    # 1. 敏感词提取
    # ------------------------------------------------------------------
    def extract_sensitive_words(self, text: str) -> list[dict]:    # 提取敏感词
        """从条文中提取敏感词及其分类"""
        words = set(jieba.lcut(text))    # 分词并去重

        results: list[dict] = []    # 结果列表
        seen: set[str] = set()    # 已处理的词
        for word in words:    # 遍历每个词
            cat = classify_word(word)    # 分类词
            if cat and word not in seen:    # 如果分类词存在且未处理过
                seen.add(word)    # 标记为已处理
                results.append({"word": word, "category": cat})    # 添加到结果列表
        return results

    # ------------------------------------------------------------------
    # 2. 方向解析
    # ------------------------------------------------------------------
    def resolve_direction(self, direction: str) -> tuple[list[str], str]:    # 解析方向
        """解析用户输入的方向，返回 (受影响的 categories, 方向描述)

        先查结构化注册表，未命中则做自然语言 keyword 匹配。
        """
        # 直接匹配结构化方向名
        if direction in DIRECTION_REGISTRY:    # 如果方向在注册表中
            info = DIRECTION_REGISTRY[direction]    # 获取方向信息
            return info["affected"], info["desc"]    # 返回受影响的 categories和描述

        # 模糊匹配：遍历注册表的 desc
        for key, info in DIRECTION_REGISTRY.items():    # 遍历每个方向
            if info["desc"] in direction or key in direction:    # 如果描述或键在方向中
                return info["affected"], info["desc"]    # 返回受影响的 categories和描述

        # 自然语言兜底解析
        affected: set[str] = set()    # 受影响的 categories
        for cat, keywords in _NATURAL_DIRECTION_KEYWORDS.items():    # 遍历每个分类词
            for kw in keywords:    # 遍历每个关键词
                if kw in direction:    # 如果关键词在方向中
                    affected.add(cat)    # 添加到受影响的 categories
                    break

        if not affected:    # 如果没有受影响的 categories
            # 完全无法解析时，返回全部 categories（让 LLM 自行判断）
            return list(SENSITIVE_WORD_CATEGORIES.keys()), direction    # 返回所有 categories和方向

        # 根据极性 keyword 推断是加强还是减弱
        pos_count = sum(1 for p in _POLARITY_POSITIVE if p in direction)    # 正极性关键词数量
        neg_count = sum(1 for p in _POLARITY_NEGATIVE if p in direction)    # 负极性关键词数量
        if pos_count > neg_count:    # 如果正极性关键词数量大于负极性关键词数量
            desc = f"{direction}（系统推断为加强型）"
        elif neg_count > pos_count:    # 如果负极性关键词数量大于正极性关键词数量
            desc = f"{direction}（系统推断为减弱型）"
        else:
            desc = direction    # 如果正极性关键词数量等于负极性关键词数量，返回方向

        return list(affected), desc    # 返回受影响的 categories和描述

    # ------------------------------------------------------------------
    # 3. 下游候选筛选
    # ------------------------------------------------------------------
    def find_downstream_candidates(
        self,    # 查找下游候选
        law_title: str,    # 法律标题
        article_no: str,    # 文章编号
        affected_categories: list[str],    # 受影响的 categories
        recursive: bool = False,    # 是否递归查找
        max_depth: int = 2,    # 最大查找深度
        max_candidates: int = 20,    # 最大候选数量
    ) -> tuple[list[dict], list[dict]]:     # 找到下游候选
        """沿引用链找到下游条文，筛选含同类敏感词的候选

        Returns:
            (direct_candidates, indirect_candidates)
        """
        if self._domino is None:     # 创建 DominoAnalyzer 实例
            self._domino = DominoAnalyzer.get_instance()    # 获取 DominoAnalyzer 实例
        self._domino.load()    # 加载模型

        chain = self._domino.get_impact_chain(     # 获取引用链
            law_title=law_title,    # 法律标题
            article_no=article_no,    # 文章编号
            recursive=recursive,    # 是否递归查找
            max_depth=max_depth,    # 最大查找深度
        )

        direct: list[dict] = []    # 直接引用候选
        indirect: list[dict] = []    # 间接引用候选

        for item in chain.get("direct_impacts", []):    # 遍历直接引用候选
            cand = self._build_candidate(item, affected_categories)    # 构建候选条文
            if cand:    # 如果候选条文有效
                direct.append(cand)    # 添加到直接引用候选

        for item in chain.get("indirect_impacts", []):    # 遍历间接引用候选
            cand = self._build_candidate(item, affected_categories)    # 构建候选条文
            if cand:    # 如果候选条文有效
                indirect.append(cand)    # 添加到间接引用候选

        # 去重 + 限制数量
        seen: set[str] = set()    # 已见的候选条文
        def dedup(cands: list[dict]) -> list[dict]:    # 去重函数
            result: list[dict] = []    # 去重后的候选条文
            for c in cands:    # 遍历候选条文
                key = c["law"] + c["article"]    # 去重键
                if key not in seen:    # 如果去重键不在已见的候选条文中
                    seen.add(key)    # 添加到已见的候选条文
                    result.append(c)    # 添加到去重后的候选条文
            return result

        direct = dedup(direct)[:max_candidates]    # 去重后的直接引用候选
        indirect = dedup(indirect)[:max_candidates]    # 去重后的间接引用候选

        return direct, indirect    # 返回直接引用候选和间接引用候选

    def _build_candidate(self, impact_item: dict, affected_categories: list[str]) -> dict | None:    # 构建候选条文
        """构建候选条文，并检查是否含同类敏感词"""
        law = impact_item.get("citing_law", "").strip("《》")    # 法律标题
        article = impact_item.get("citing_article", "")    # 文章编号
        text = self._get_chunk_text(law, article)    # 获取条文原文
        if not text:    # 如果条文原文为空
            return None    # 返回 None 表示无效候选条文

        # 提取敏感词
        sens_words = self.extract_sensitive_words(text)    # 提取敏感词
        matched_cats = {sw["category"] for sw in sens_words}    # 匹配的 categories

        # 检查是否有重叠的 category
        overlap = set(affected_categories) & matched_cats    # 重叠的 categories
        if not overlap:
            # 如果目标条文本身含有很多敏感词，且下游条文完全不含同类词，
            # 则降低相关性，但仍保留（LLM 可能发现跨 category 的传导）
            # 这里采用宽松策略：只要下游条文有敏感词就保留
            if not sens_words:     # 如果目标条文本身不含敏感词
                return None    # 返回 None 表示无效候选条文

        return {      # 构建候选条文
            "law": law,    # 法律标题
            "article": article,    # 文章编号
            "text": text,    # 文条原文
            "keyword": impact_item.get("keyword"),    # 引用关键词
            "matched_categories": list(overlap) if overlap else [sw["category"] for sw in sens_words[:1]],    # 匹配的 categories
            "sensitive_words": sens_words,    # 敏感词
        }

    # ------------------------------------------------------------------
    # 4. LLM Prompt 构建
    # ------------------------------------------------------------------
    @staticmethod    # 构建 LLM Prompt
    def build_llm_prompt(     # 构建 LLM Prompt
        target_law: str,     # 目标条文法律标题
        target_article: str,     # 目标条文文章编号
        target_text: str,     # 目标条文原文
        direction_desc: str,     # 法律偏移方向
        magnitude: str | None,     # 偏移幅度
        direct_candidates: list[dict],     # 直接引用候选
        indirect_candidates: list[dict],     # 间接引用候选
    ) -> str:
        """构建反事实分析的用户 prompt"""
        lines: list[str] = []      # 构建 LLM Prompt 行列
        lines.append(f"目标条文：《{target_law}》{target_article}")     # 目标条文
        lines.append(f"条文原文：{target_text.strip()}")     # 条文原文
        lines.append(f"立法偏移方向：{direction_desc}")     # 法律偏移方向
        if magnitude:     # 如果偏移幅度存在
            lines.append(f"偏移幅度：{magnitude}")     # 偏移幅度
        lines.append("")

        all_candidates = direct_candidates + indirect_candidates     # 所有候选条文
        if not all_candidates:     # 如果所有候选条文为空
            lines.append("候选下游条文：无（该条文未被其他条文引用）")     # 无候选条文
        else:
            lines.append("候选下游条文（仅能从以下列表中选择）：")     # 候选条文列表
            for i, cand in enumerate(all_candidates, 1):     # 遍历所有候选条文
                depth_label = "[直接引用]" if cand in direct_candidates else "[间接引用]"
                lines.append(f"[{i}] {depth_label} 《{cand['law']}》{cand['article']}")     # 候选条文标题
                # 截断到80字
                preview = cand["text"].strip()[:80]     # 候选条文内容预览
                lines.append(f"    内容：{preview}")     # 候选条文内容预览
                if cand.get("keyword"):     # 如果引用关键词存在
                    lines.append(f"    引用关键词：{cand['keyword']}")     # 引用关键词
                if cand.get("matched_categories"):     # 如果匹配的 categories 存在
                    lines.append(f"    相关敏感词分类：{', '.join(cand['matched_categories'])}")     # 相关敏感词分类
                lines.append("")

        lines.append("请分析目标条文的偏移会波及哪些候选条文，返回 JSON 数组。")      # 请求 LLM 分析
        return "\n".join(lines)     # 返回 LLM Prompt

    # ------------------------------------------------------------------
    # 5. LLM 响应解析
    # ------------------------------------------------------------------
    @staticmethod
    def parse_llm_response(response: str) -> list[dict]:
        """解析 LLM 返回的 JSON 数组"""
        response = response.strip()
        if not response or response == "[]":
            return []

        # 提取 ```json ... ``` 中的内容
        m = re.search(r"```json\s*([\s\S]*?)\s*```", response)
        if m:
            json_str = m.group(1).strip()
        else:
            # 尝试直接解析
            json_str = response

        try:
            data = json.loads(json_str)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "impacts" in data:
                return data["impacts"]
            return []
        except json.JSONDecodeError:
            # 尝试用正则提取数组
            m2 = re.search(r"\[\s*\{[\s\S]*\}\s*\]", json_str)
            if m2:
                try:
                    return json.loads(m2.group(0))
                except json.JSONDecodeError:
                    pass
            return []

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def analyze(         # 运行反事实模拟分析
        self,           # 运行反事实模拟分析
        law_title: str,     # 目标条文法律标题
        article_no: str,     # 目标条文文章编号
        direction: str,     # 法律偏移方向
        magnitude: str | None = None,     # 偏移幅度
        include_indirect: bool = True,     # 是否包含间接引用候选
        max_depth: int = 2,     # 最大递归深度
        max_candidates: int = 20,     # 最大候选条文数量
    ) -> dict:
        """运行反事实模拟分析

        Returns:
            {
                "target_law": str,
                "target_article": str,
                "target_text": str | None,
                "original_direction": str,
                "interpreted_direction": str,
                "affected_categories": list[str],
                "direct_candidates_count": int,
                "indirect_candidates_count": int,
                "direct_impacts": list[dict],
                "indirect_impacts": list[dict],
                "llm_summary": str,
                "total_affected": int,
            }
        """
        # 1. 加载目标条文
        target_text = self._get_chunk_text(law_title, article_no)

        # 2. 解析方向
        affected_categories, interpreted_direction = self.resolve_direction(direction)     # 解析用户指定方向

        # 3. 提取目标条文敏感词
        target_sens = self.extract_sensitive_words(target_text or "")     # 提取目标条文敏感词
        target_cats = {sw["category"] for sw in target_sens}     # 提取目标条文敏感词分类
        # 合并：用户指定方向 + 目标条文实际含有的 categories
        merged_categories = list(set(affected_categories) | target_cats)     # 合并用户指定方向和目标条文敏感词分类

        # 4. 查找下游候选
        direct_candidates, indirect_candidates = self.find_downstream_candidates(     # 查找下游候选条文
            law_title=law_title,     # 目标条文法律标题
            article_no=article_no,     # 目标条文文章编号
            affected_categories=merged_categories,     # 合并用户指定方向和目标条文敏感词分类
            recursive=include_indirect,     # 是否包含间接引用候选
            max_depth=max_depth,     # 最大递归深度
            max_candidates=max_candidates,     # 最大候选条文数量
        )

        # 5. 构建 prompt 并调用 LLM
        if not direct_candidates and not indirect_candidates:     # 如果没有直接引用候选和间接引用候选
            return {
                "target_law": law_title,     # 目标条文法律标题
                "target_article": article_no,     # 目标条文文章编号
                "target_text": target_text,     # 目标条文文本
                "original_direction": direction,     # 用户指定方向
                "interpreted_direction": interpreted_direction,     # 解析后的方向
                "affected_categories": merged_categories,     # 合并用户指定方向和目标条文敏感词分类
                "direct_candidates_count": 0,     # 直接引用候选数量
                "indirect_candidates_count": 0,     # 间接引用候选数量
                "direct_impacts": [],     # 直接引用候选条文影响
                "indirect_impacts": [],     # 间接引用候选条文影响
                "llm_summary": "该条文未被其他条文引用，偏移不会产生波及效应。",     # LLM 分析结果
                "total_affected": 0,     # 总影响条文数量
            }

        user_prompt = self.build_llm_prompt(     # 构建 LLM 提示
            target_law=law_title,     # 目标条文法律标题
            target_article=article_no,     # 目标条文文章编号
            target_text=target_text or "（条文文本未找到）",     # 目标条文文本
            direction_desc=interpreted_direction,     # 解析后的方向描述
            magnitude=magnitude,     # 偏移幅度
            direct_candidates=direct_candidates,     # 直接引用候选条文
            indirect_candidates=indirect_candidates if include_indirect else [],     # 间接引用候选条文
        )

        try:      # 调用 LLM 分析
            llm_response = chat_answer(      # 调用 LLM 获取答案
                COUNTERFACTUAL_SYSTEM_PROMPT,     # 系统提示
                user_prompt,     # 用户提示
                max_tokens=1200,     # 最大 tokens
            )
        except LLMAuthError:      # 认证错误
            raise  # 向上抛，由 app/main.py 的端点统一处理

        parsed = self.parse_llm_response(llm_response)     # 解析 LLM 分析结果

        # 6. 将 LLM 结果与 direct/indirect 标记关联
        direct_impacts: list[dict] = []     # 直接引用候选条文影响
        indirect_impacts: list[dict] = []     # 间接引用候选条文影响

        # 建立候选索引
        all_candidates = direct_candidates + indirect_candidates    # 所有候选
        for item in parsed:
            key = item.get("article_key", "")
            # 尝试匹配到 direct 或 indirect
            is_direct = False
            for cand in direct_candidates:
                if cand["law"] in key and cand["article"] in key:
                    is_direct = True
                    break

            impact_item = {
                "law_title": item.get("article_key", "").strip("《》"),
                "article_no": "",
                "risk_level": item.get("risk_level", "Unknown"),
                "llm_reasoning": item.get("reasoning", ""),
            }
            # 提取条文号
            m = re.search(r"第[零一二三四五六七八九十百千万\d]+条", key)
            if m:
                impact_item["article_no"] = m.group(0)

            if is_direct:
                direct_impacts.append(impact_item)
            else:
                indirect_impacts.append(impact_item)

        return {
            "target_law": law_title,     # 目标条文法律标题
            "target_article": article_no,     # 目标条文文章编号
            "target_text": target_text,     # 目标条文文本
            "original_direction": direction,     # 用户指定方向
            "interpreted_direction": interpreted_direction,     # 解析后的方向
            "affected_categories": merged_categories,     # 合并用户指定方向和目标条文敏感词分类
            "direct_candidates_count": len(direct_candidates),     # 直接引用候选数量
            "indirect_candidates_count": len(indirect_candidates),     # 间接引用候选数量
            "direct_impacts": direct_impacts,     # 直接引用候选条文影响
            "indirect_impacts": indirect_impacts,     # 间接引用候选条文影响
            "llm_summary": llm_response[:500] if llm_response else "",     # LLM 分析结果
            "total_affected": len(direct_impacts) + len(indirect_impacts),     # 总影响条文数量
        }
