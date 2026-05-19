from __future__ import annotations

from .chunking import Chunk


SYSTEM_PROMPT = """你是一个法律检索问答助手。基于给定"检索依据片段"回答用户问题。

约束：
- 只能使用提供的依据片段，不要编造未出现的条文、期限、数字、主体或结论。
- 如果依据不足以得出结论，明确说"依据不足"，并说明缺什么。
- 关键结论后标注引用编号，例如：[1][2]。
- 语气专业、简洁、直接。
- 注意法律状态：[有效]是现行最新版本；[已修改]表示有历史版本；[尚未生效]暂不适用；[已废止]仅在废止前争议行为才可引用。

血缘信息（已附在引用后，仅供辅助理解）：
- drift值越大变化越大；change_type为"平移"表示内容基本不变仅迁移。
- 如果存在实质性变化（敏感词发生变化），结论中简要提醒即可。

输出格式：
## 结论
（直接回答问题，可分点）

## 依据
- 要点... [1][2]

## 补充说明（如有）
...
"""


COUNTERFACTUAL_SYSTEM_PROMPT = """你是一个立法影响分析专家。你的任务是：基于给定的"目标条文原文"和"立法偏移方向"，分析这会波及哪些下游相关条文。

约束：
- 只能从提供的"候选下游条文"列表中选择被波及的条文，不得编造未出现的条文。
- 必须说明传导逻辑：目标条文的哪个敏感词变化（如"应当→可以""不得→可以""门槛提高"等）导致了下游条文的何种风险。
- reasoning 必须简洁，控制在 120 字以内，只说核心传导逻辑，不要展开法理分析。
- 若多个候选均受影响，优先返回风险等级最高的，最多返回 5 个。
- 风险等级判定标准：
  - High：目标条文的偏移直接导致下游条文的适用条件、权利义务或程序要求发生实质性矛盾或失效
  - Medium：目标条文的偏移与下游条文存在逻辑张力，可能需要司法解释或配套修改
  - Low：目标条文的偏移对下游条文影响轻微，或仅涉及表述一致性
- 输出必须是合法的 JSON 数组，每项包含：article_key（条文标识）、risk_level（High/Medium/Low）、reasoning（传导逻辑说明）。
- 如果候选列表中没有任何条文会受波及，返回空数组 []。

输出格式（严格 JSON，不要输出任何其他内容）：
[
  {
    "article_key": "《法律名》第X条",
    "risk_level": "High",
    "reasoning": "目标条文将'应当'改为'可以'，导致下游条文《YYY》第Z条中'依照本法第X条'的引用基础失效，因为原义务性规范变为授权性规范。"
  }
]
"""


def build_user_prompt(question: str, contexts: list[tuple[int, Chunk, list[dict]]]) -> str:
    """
    构建用户提示
    contexts: list of (idx, Chunk, lineage_chain)
    lineage_chain: list of dict，格式为 LineageStep.asdict() 的结果
    """
    lines: list[str] = []
    lines.append(f"用户问题：{question}")
    lines.append("")
    lines.append("检索依据片段：")
    for i, (_idx, c, lineage_chain) in enumerate(contexts, start=1):
        lines.append(f"[{i}] {c.citation_label_with_status()}")

        # 如果有血缘链，追加变迁说明
        if lineage_chain and len(lineage_chain) > 0:
            lineage_desc = _format_lineage_desc(lineage_chain)
            lines.append(f"    血缘信息：{lineage_desc}")

        lines.append(c.text)
        lines.append("")
    return "\n".join(lines).strip()


def _format_lineage_desc(lineage_chain: list[dict]) -> str:
    """
    将 lineage_chain 格式化为可读的中文描述
    lineage_chain 从新到旧：[latest, ..., oldest]
    """
    if not lineage_chain:
        return "无血缘信息（单版本法律）"

    parts = []
    for step in lineage_chain:
        version = step.get("version_label", "未知")
        change_type = step.get("change_type", "未知")
        drift = step.get("drift_score")
        is_split = step.get("is_split", False)
        is_merge = step.get("is_merge", False)
        has_critical = step.get("has_critical_change", False)
        derived = step.get("derived_from_article") or "无"

        # drift 可读化
        if drift is not None:
            if drift < 0.05:
                drift_desc = "几乎无变化"
            elif drift < 0.3:
                drift_desc = f"小幅变化(drift={drift:.3f})"
            elif drift < 0.7:
                drift_desc = f"较大变化(drift={drift:.3f})"
            else:
                drift_desc = f"重大变化(drift={drift:.3f})"
        else:
            drift_desc = ""

        flags = []
        if is_split:
            flags.append("条文拆分")
        if is_merge:
            flags.append("条文合并")
        if has_critical:
            flags.append("!!实质性权利变动")

        change_desc = change_type
        if drift_desc:
            change_desc += f"（{drift_desc}）"
        if flags:
            change_desc += " " + " ".join(flags)

        parts.append(f"{version}版（源自：{derived}，变化：{change_desc}）")

    return " → ".join(parts)
