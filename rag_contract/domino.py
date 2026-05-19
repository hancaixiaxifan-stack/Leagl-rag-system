"""
跨法律多米诺效应检测（Direction 3）

DominoAnalyzer 加载 reference_graph.json，提供 BFS 影响链查询。
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Iterable


class DominoAnalyzer:
    """引用网络分析器（单例）

    职责：加载 reference_graph.json，提供 by_article / cites 查询和 BFS 影响链追溯。
    """
    # 单例模式，确保全局唯一实例
    _instance: "DominoAnalyzer | None" = None

    # 获取单例实例，确保全局唯一
    @classmethod
    def get_instance(cls, graph_path: str | Path | None = None) -> "DominoAnalyzer":
        if cls._instance is None:
            if graph_path is None:
                from rag_contract.settings import settings
                graph_path = Path(settings.reference_graph_path)
            cls._instance = cls(graph_path)
        return cls._instance

    # 初始化引用网络分析器，加载 reference_graph.json
    def __init__(self, graph_path: str | Path) -> None:
        self.graph_path = Path(graph_path)
        self._graph: dict = {}
        self._loaded = False

    # 加载 reference_graph.json 文件，初始化引用网络
    def load(self) -> None:
        if self._loaded:
            return
        if not self.graph_path.exists():
            self._graph = {"by_article": {}, "cites": {}, "laws": [], "version": "0"}
        else:
            with open(self.graph_path, "r", encoding="utf-8") as f:
                self._graph = json.load(f)
        self._loaded = True

    # 提供 by_article / cites / laws 属性，自动加载 graph
    @property
    def by_article(self) -> dict:
        self.load()
        return self._graph.get("by_article", {})

    # 提供 cites 属性，自动加载 graph，返回引用关系字典
    @property
    def cites(self) -> dict:
        self.load()
        return self._graph.get("cites", {})

    # 提供 laws 属性，自动加载 graph，返回法律条文列表
    @property
    def laws(self) -> list[str]:
        self.load()
        return self._graph.get("laws", [])

    # 构建全局 key：'《法名》第X条'
    @staticmethod
    def make_key(law_title: str, article_no: str) -> str:
        """构建全局 key：'《法名》第X条'"""
        wrapped = law_title if (law_title.startswith("《") and law_title.endswith("》")) else f"《{law_title}》"
        return f"{wrapped}{article_no}"

    # 查找匹配的全局 key（可能因换行/版本差异有多个候选）
    def find_keys(self, law_title: str, article_no: str) -> list[str]:
        """查找匹配的全局 key（可能因换行/版本差异有多个候选）

        实际实现：reference_graph 中 doc_title 已经是清理过的最新版，
        但用户传入可能带换行或别名，做一次模糊匹配。
        """
        self.load()
        target = self.make_key(law_title, article_no)
        if target in self.by_article or target in self.cites:
            return [target]

        # 模糊匹配：去除空格后比较
        target_norm = target.replace(" ", "").replace("\n", "").replace("　", "")
        candidates = []
        for key in self.by_article.keys():
            if key.replace(" ", "").replace("\n", "").replace("　", "") == target_norm:
                candidates.append(key)
        return candidates


    # BFS 追溯影响链
    def get_impact_chain(
        self,
        law_title: str,
        article_no: str,
        recursive: bool = False,
        max_depth: int = 2,
        decay_factor: float = 0.7,
        base_drift_score: float | None = None,
    ) -> dict:
        """BFS 追溯影响链（增强版：环检测、深度衰减、重复引用合并）

        Args:
            law_title: 被修改的法律名称
            article_no: 被修改的条文编号（如"第十八条"）
            recursive: 是否递归追溯
            max_depth: 最大深度（默认 2，上限 5）
            decay_factor: 风险衰减因子（默认 0.7，每深一层乘以该值）
            base_drift_score: 触发节点的漂移分数（用于计算 risk_score；None 时默认 0.1）

        Returns:
            {
                "trigger_node": "《...》第X条",
                "direct_impacts": [...],   # depth=1，含 risk_score
                "indirect_impacts": [...], # depth>=2，含 risk_score / via_articles
            }
        """
        self.load()

        keys = self.find_keys(law_title, article_no)
        trigger_key = keys[0] if keys else self.make_key(law_title, article_no)

        effective_max = max_depth if recursive else 1
        base_drift = base_drift_score if base_drift_score is not None else 0.1

        # 使用 dict 聚合同一 child_key 的多次引用，实现重复引用合并
        # key -> {"impact": dict, "depth": int, "via_articles": list[str], "paths": list[tuple]}
        direct_map: dict[str, dict] = {}
        indirect_map: dict[str, dict] = {}

        # BFS 队列: (node_key, depth, via, path)
        # path 记录从 trigger 到当前节点的完整路径，用于环检测
        queue: deque[tuple[str, int, str | None, tuple[str, ...]]] = deque()
        queue.append((trigger_key, 0, None, (trigger_key,)))

        while queue:
            node_key, depth, via, path = queue.popleft()
            if depth >= effective_max:
                continue

            citing_list = self.by_article.get(node_key, [])
            for cite in citing_list:
                citing_law_raw = cite.get("citing_law", "")
                citing_article = cite.get("citing_article", "")
                # 统一使用 make_key 构造 child_key，消除格式不一致
                child_key = self.make_key(citing_law_raw, citing_article)

                # 环检测：若 child_key 已在当前路径中，说明存在循环引用，跳过
                if child_key in path:
                    continue

                # 风险分数按深度衰减
                risk_score = base_drift * (decay_factor ** (depth + 1))

                citing_law = citing_law_raw if citing_law_raw.startswith("《") else f"《{citing_law_raw}》"

                impact_core = {
                    "citing_law": citing_law,
                    "citing_article": citing_article,
                    "reference_text": cite.get("reference_text", ""),
                    "keyword": cite.get("keyword"),
                    "risk_score": risk_score,
                }

                if depth == 0:
                    # direct: 按 child_key 聚合
                    if child_key not in direct_map:
                        direct_map[child_key] = {
                            "impact": dict(impact_core),
                            "depth": 1,
                            "via_articles": [],
                            "paths": [],
                        }
                    else:
                        # 合并引用文本（保留更长的上下文）
                        existing_text = direct_map[child_key]["impact"]["reference_text"]
                        new_text = impact_core["reference_text"]
                        if len(new_text) > len(existing_text):
                            direct_map[child_key]["impact"]["reference_text"] = new_text
                else:
                    # indirect: 按 child_key 聚合，保留多个 via 和 path
                    if child_key not in indirect_map:
                        indirect_map[child_key] = {
                            "impact": dict(impact_core),
                            "depth": depth + 1,
                            "via_articles": [node_key] if via is None else [node_key],
                            "paths": [path],
                        }
                    else:
                        indirect_map[child_key]["via_articles"].append(node_key)
                        indirect_map[child_key]["paths"].append(path)
                        # 更新 risk_score 取最大值（最短路径风险最高）
                        if risk_score > indirect_map[child_key]["impact"]["risk_score"]:
                            indirect_map[child_key]["impact"]["risk_score"] = risk_score

                if recursive and depth + 1 < effective_max:
                    new_path = path + (child_key,)
                    queue.append((child_key, depth + 1, node_key, new_path))

        # 展开聚合结果为列表
        direct_impacts = []
        for item in direct_map.values():
            impact = item["impact"]
            direct_impacts.append(impact)

        indirect_impacts = []
        for item in indirect_map.values():
            impact = item["impact"]
            # via_articles 去重后保留
            unique_vias = list(dict.fromkeys(item["via_articles"]))
            if len(unique_vias) == 1:
                impact["via_article"] = unique_vias[0]
            else:
                impact["via_articles"] = unique_vias
            indirect_impacts.append(impact)

        return {
            "trigger_node": trigger_key,
            "direct_impacts": direct_impacts,
            "indirect_impacts": indirect_impacts,
        }


# 根据 drift_score 判定风险等级
def risk_level_from_drift(drift_score: float | None) -> str:
    """根据 drift_score 判定风险等级

    阈值与 lineage.py 保持一致：
    - High: drift >= 0.2 (重大修订)
    - Medium: 0.05 <= drift < 0.2 (实质性修订)
    - Low: drift < 0.05 (微调)
    - Unknown: drift_score 缺失
    """
    if drift_score is None:
        return "Unknown"
    if drift_score >= 0.2:
        return "High"
    if drift_score >= 0.05:
        return "Medium"
    return "Low"
