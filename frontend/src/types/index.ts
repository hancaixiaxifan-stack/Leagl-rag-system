/**
 * 法律 RAG 可视化前端 — 核心类型定义
 * 严格类型检查，禁止使用 any
 */

// ─────────────────────────────────────────────
// Direction 1: 血缘链（Lineage）
// ─────────────────────────────────────────────

export interface SensitiveDelta {
  word: string;
  old_category?: string;
  new_category?: string;
  category_shifted: boolean;
  polarity_flipped: boolean;
}

export interface LineageStep {
  version_label: string;
  derived_from_article?: string;
  similarity_with_prev?: number;
  drift_score?: number;
  change_type: string;
  is_split: boolean;
  is_merge: boolean;
  sensitive_deltas: SensitiveDelta[];
  has_critical_change: boolean;
}

/** 漂移节点 — 时间轴展示的基本单元 */
export interface DriftNode {
  /** 法条唯一标识 */
  id: string;
  /** 法条编号，如 "第一条" */
  article_no: string;
  /** 所属法律名称 */
  law_title: string;
  /** 完整条文内容 */
  text: string;
  /** 条文内容预览（截断） */
  text_preview: string;
  /** 敏感词差异列表 */
  sensitive_deltas: SensitiveDelta[];
  /** 当前版本生效起始日 */
  effective_start?: string;
  /** 当前版本失效日 */
  effective_end?: string;
  /** 效力状态 */
  status: "有效" | "尚未实施" | "已修改" | "已废止" | string;
  /** 语义漂移分数 (0~1) */
  drift_score?: number;
  /** 与前版本的相似度 */
  similarity_with_prev?: number;
  /** 完整血缘链 */
  lineage_chain: LineageStep[];
  /** 变更类型 */
  change_type: string;
}

// ─────────────────────────────────────────────
// Direction 2: 法律漂移报告
// ─────────────────────────────────────────────

export interface DriftReportSummary {
  avg_drift: number;
  avg_law_logic_drift: number;
  major_changes_count: number;
  relocated_count: number;
  reassigned_count: number;
  version_count: number;
  total_chunks: number;
}

export interface HotspotItem {
  range: string;
  intensity: string;
  reason: string;
}

export interface HighDriftDetail {
  article_no: string;
  status: string;
  old_content_trace?: string;
  similarity?: number;
  drift_score?: number;
  text_preview?: string;
}

export interface ChapterData {
  chapter_label: string;
  article_range: string;
  avg_drift: number;
  major_revision_count: number;
  relocated_count: number;
  reassigned_count: number;
}

export interface DriftReport {
  law_title: string;
  summary: DriftReportSummary;
  hotspots: HotspotItem[];
  high_drift_details: HighDriftDetail[];
  chapters: ChapterData[];
}

// ─────────────────────────────────────────────
// Direction 3: 多米诺效应（Domino）
// ─────────────────────────────────────────────

export type RiskLevel = "High" | "Medium" | "Low" | "Potential" | "Unknown";

export interface DominoImpactItem {
  citing_law: string;
  citing_article: string;
  reference_text: string;
  keyword?: string;
  risk_level: RiskLevel | string;
  risk_score?: number;
  via_article?: string;
}

/** 拓扑图节点 */
export interface DominoNode {
  id: string;
  label: string;
  law_title: string;
  article_no: string;
  risk_level: RiskLevel | string;
  risk_score?: number;
  /** 节点层级: trigger / direct / indirect */
  level: "trigger" | "direct" | "indirect";
  drift_score?: number;
  reference_text?: string;
  keyword?: string;
}

/** 拓扑图边 */
export interface DominoEdge {
  from: string;
  to: string;
  label?: string;
  risk_level: RiskLevel | string;
  /** true 表示间接引用（虚线） */
  is_indirect: boolean;
}

export interface DominoImpact {
  trigger_node: string;
  trigger_law_title: string;
  trigger_article_no: string;
  effective_status?: string;
  drift_score?: number;
  direct_impacts: DominoImpactItem[];
  indirect_impacts: DominoImpactItem[];
  total_affected_articles: number;
}

/** 引用图全局统计 */
export interface DominoStats {
  node_count: number;
  edge_count: number;
  law_count: number;
}

// ─────────────────────────────────────────────
// Direction 4: 反事实模拟（Counterfactual）
// ─────────────────────────────────────────────

export interface CounterfactualImpactItem {
  law_title: string;
  article_no: string;
  risk_level: string;
  llm_reasoning: string;
}

export interface CounterfactualResponse {
  target_law: string;
  target_article: string;
  target_text?: string;
  original_direction: string;
  interpreted_direction: string;
  affected_categories: string[];
  direct_impacts: CounterfactualImpactItem[];
  indirect_impacts: CounterfactualImpactItem[];
  llm_summary: string;
  total_affected: number;
}

export interface DirectionInfo {
  key: string;
  desc: string;
  affected: string[];
}

// ─────────────────────────────────────────────
// Ask / 法律咨询
// ─────────────────────────────────────────────

export interface Citation {
  label: string;
  doc_title: string;
  doc_type?: string;
  jurisdiction?: string;
  publish_date?: string;
  effective_start?: string;
  effective_end?: string;
  change_type?: string;
  law_category?: string;
  status: string;
  article_no?: string;
  clause_no?: string;
  item_no?: string;
  para_start: number;
  para_end: number;
  snippet: string;
  lineage_chain: LineageStep[];
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  current_date: string;
}

// ─────────────────────────────────────────────
// 法律条文列表
// ─────────────────────────────────────────────

export interface LawArticleItem {
  article_no: string;
  text_preview: string;
  effective_start?: string;
  effective_end?: string;
  status: string;
}

export interface LawArticlesResponse {
  law_title: string;
  articles: LawArticleItem[];
  current_date: string;
}

// ─────────────────────────────────────────────
// 检索配置
// ─────────────────────────────────────────────

export interface SearchConfig {
  /** 向量检索权重 (0~1) */
  vectorWeight: number;
  /** BM25 权重 (0~1) */
  bm25Weight: number;
  /** 返回条数 */
  topN: number;
  /** 混合检索最终返回条数 */
  finalTopN: number;
  /**
   * Hybrid-on-Demand confidence threshold (0~1).
   * BM25 re-ranking activates only when top-1 vector cosine similarity
   * falls below this value. Set to 0 to always use BM25; 1 for vector-only.
   */
  hybridConfidenceThreshold: number;
}

// ─────────────────────────────────────────────
// 详情面板 Metadata
// ─────────────────────────────────────────────

export interface ArticleMetadata {
  law_title: string;
  article_no: string;
  text: string;
  effective_start?: string;
  effective_end?: string;
  status: string;
  law_category?: string;
  publish_date?: string;
  drift_score?: number;
  lineage_chain: LineageStep[];
}
