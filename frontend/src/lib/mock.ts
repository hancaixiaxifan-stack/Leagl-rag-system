/**
 * Mock 数据生成器 — 后端接口未就绪前使用
 * 数据规模参考：约 53,705 条 chunk 记录结构
 */

import type {
  DominoImpact,
  DominoNode,
  DominoEdge,
  DriftNode,
  LineageStep,
  SensitiveDelta,
  RiskLevel,
  LawArticleItem,
} from "@/types";

// ─────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────

const LAWS = [
  "中华人民共和国民法典",
  "中华人民共和国公司法",
  "中华人民共和国专利法",
  "中华人民共和国劳动合同法",
  "中华人民共和国著作权法",
];

/** 基于字符串哈希的确定性种子生成器 — 解决 SSR/CSR hydration mismatch */
function createSeededRng(seed: string) {
  let state = 0;
  for (let i = 0; i < seed.length; i++) {
    state = (state * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return {
    next() {
      state = (state * 1664525 + 1013904223) >>> 0;
      return state / 4294967296;
    },
    nextInt(min: number, max: number) {
      return Math.floor(this.next() * (max - min + 1)) + min;
    },
    pick<T>(arr: T[]): T {
      return arr[this.nextInt(0, arr.length - 1)];
    },
  };
}

/** 当前 RNG 实例（由调用方设置种子） */
let _rng = createSeededRng("default");

function setSeed(seed: string) {
  _rng = createSeededRng(seed);
}

function randomPick<T>(arr: T[]): T {
  return _rng.pick(arr);
}

function randomInt(min: number, max: number): number {
  return _rng.nextInt(min, max);
}

function makeArticleNo(index: number): string {
  const num = index + 1;
  if (num <= 10) return `第${["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"][num - 1]}条`;
  if (num < 20) return `第十${["一", "二", "三", "四", "五", "六", "七", "八", "九"][num - 11]}条`;
  if (num === 20) return "第二十条";
  return `第${num}条`;
}

// ─────────────────────────────────────────────
// Mock: 敏感词差异
// ─────────────────────────────────────────────

export function mockSensitiveDeltas(count = 3): SensitiveDelta[] {
  const words = ["应当", "必须", "可以", "不得", "禁止", "限制", "保护", "赔偿", "处罚", "许可"];
  const categories = ["义务性", "授权性", "禁止性", "保护性", "惩罚性"];
  return Array.from({ length: count }, () => {
    const word = randomPick(words);
    const oldCat = randomPick(categories);
    let newCat = randomPick(categories);
    while (newCat === oldCat) newCat = randomPick(categories);
    return {
      word,
      old_category: oldCat,
      new_category: newCat,
      category_shifted: oldCat !== newCat,
      polarity_flipped: _rng.next() > 0.7,
    };
  });
}

// ─────────────────────────────────────────────
// Mock: 血缘步骤
// ─────────────────────────────────────────────

export function mockLineageSteps(versionCount = 3): LineageStep[] {
  const versions = ["initial", "2008修正", "2012修正", "2020修正"];
  const changeTypes = ["新增", "微调", "实质性修订", "重大变更", "迁址", "重分配"];
  return Array.from({ length: versionCount }, (_, i) => {
    const driftScore = i === 0 ? undefined : _rng.next() * 0.8;
    const similarity = i === 0 ? undefined : Math.max(0.2, 1 - (driftScore ?? 0));
    return {
      version_label: versions[i] ?? `版本${i + 1}`,
      derived_from_article: i === 0 ? undefined : makeArticleNo(randomInt(0, 50)),
      similarity_with_prev: similarity,
      drift_score: driftScore,
      change_type: i === 0 ? "新增" : randomPick(changeTypes.slice(1)),
      is_split: _rng.next() > 0.9,
      is_merge: _rng.next() > 0.9,
      sensitive_deltas: i === 0 ? [] : mockSensitiveDeltas(randomInt(0, 4)),
      has_critical_change: (driftScore ?? 0) > 0.3,
    };
  });
}

// ─────────────────────────────────────────────
// Mock: 漂移节点（时间轴）
// ─────────────────────────────────────────────

export function mockDriftNodes(articleNo: string, lawTitle: string, count = 4): DriftNode[] {
  setSeed(`${lawTitle}:${articleNo}:drift`);
  const texts = [
    "为了保护民事主体的合法权益，调整民事关系，维护社会和经济秩序，适应中国特色社会主义发展要求，弘扬社会主义核心价值观，根据宪法，制定本法。",
    "为了保护专利权人的合法权益，鼓励发明创造，推动发明创造的应用，提高创新能力，促进科学技术进步和经济社会发展，制定本法。",
    "为了保护劳动者的合法权益，调整劳动关系，建立和维护适应社会主义市场经济的劳动制度，促进经济发展和社会进步，根据宪法，制定本法。",
    "为了保护文学、艺术和科学作品作者的著作权，以及与著作权有关的权益，鼓励有益于社会主义精神文明、物质文明建设的作品的创作和传播，促进社会主义文化和科学事业的发展与繁荣，根据宪法制定本法。",
  ];
  const statuses: DriftNode["status"][] = ["有效", "已修改", "已废止", "尚未实施"];

  return Array.from({ length: count }, (_, i) => {
    const year = 2000 + i * 5;
    const text = randomPick(texts);
    const driftScore = i === 0 ? undefined : _rng.next() * 0.8;
    return {
      id: `${lawTitle}_${articleNo}_v${i}`,
      article_no: articleNo,
      law_title: lawTitle,
      text,
      text_preview: text.slice(0, 80) + "...",
      sensitive_deltas: i === 0 ? [] : mockSensitiveDeltas(randomInt(1, 4)),
      effective_start: `${year}-01-01`,
      effective_end: i < count - 1 ? `${year + 5}-01-01` : undefined,
      status: randomPick(statuses),
      drift_score: driftScore,
      similarity_with_prev: driftScore !== undefined ? Math.max(0.2, 1 - driftScore) : undefined,
      lineage_chain: mockLineageSteps(count),
      change_type: i === 0 ? "新增" : randomPick(["微调", "实质性修订", "重大变更"]),
    };
  });
}

// ─────────────────────────────────────────────
// Mock: 多米诺效应
// ─────────────────────────────────────────────

export function mockDominoImpact(
  lawTitle: string,
  articleNo: string
): DominoImpact {
  setSeed(`${lawTitle}:${articleNo}`);
  const directCount = randomInt(3, 8);
  const indirectCount = randomInt(2, 6);

  const baseDrift = _rng.next() * 0.5;
  const decayFactor = 0.7;
  const directRiskScore = baseDrift * decayFactor;
  const indirectRiskScore = baseDrift * decayFactor * decayFactor;

  const directImpacts = Array.from({ length: directCount }, () => {
    const citingLaw = randomPick(LAWS.filter((l) => l !== lawTitle));
    return {
      citing_law: citingLaw,
      citing_article: makeArticleNo(randomInt(0, 100)),
      reference_text: `根据${lawTitle}${articleNo}的规定，${citingLaw}中相关条文需要相应调整...`,
      keyword: randomPick(["依照", "根据", "参照", "按照"]),
      risk_level: randomPick(["High", "Medium", "Low"]),
      risk_score: directRiskScore,
    };
  });

  const indirectImpacts = Array.from({ length: indirectCount }, (_, i) => {
    const citingLaw = randomPick(LAWS);
    const via = directImpacts[i % directCount];
    return {
      citing_law: citingLaw,
      citing_article: makeArticleNo(randomInt(0, 100)),
      reference_text: `通过${via?.citing_law ?? ""}${via?.citing_article ?? ""}间接引用...`,
      keyword: randomPick(["间接", "传导", "波及"]),
      risk_level: "Potential" as RiskLevel,
      risk_score: indirectRiskScore,
      via_article: via ? `${via.citing_law}${via.citing_article}` : undefined,
    };
  });

  return {
    trigger_node: `${lawTitle}${articleNo}`,
    trigger_law_title: lawTitle,
    trigger_article_no: articleNo,
    effective_status: "有效",
    drift_score: baseDrift,
    direct_impacts: directImpacts,
    indirect_impacts: indirectImpacts,
    total_affected_articles: directCount + indirectCount,
  };
}

/** 将 DominoImpact 转换为 vis-network 所需的 nodes + edges */
export function convertDominoToGraph(impact: DominoImpact): {
  nodes: DominoNode[];
  edges: DominoEdge[];
} {
  const nodes: DominoNode[] = [];
  const edges: DominoEdge[] = [];
  const nodeSet = new Set<string>();

  const triggerKey = impact.trigger_node;
  nodeSet.add(triggerKey);
  nodes.push({
    id: triggerKey,
    label: `${impact.trigger_law_title}\n${impact.trigger_article_no}`,
    law_title: impact.trigger_law_title,
    article_no: impact.trigger_article_no,
    risk_level: impact.drift_score && impact.drift_score >= 0.2 ? "High" : "Medium",
    level: "trigger",
    drift_score: impact.drift_score,
  });

  impact.direct_impacts.forEach((imp) => {
    const key = `${imp.citing_law}${imp.citing_article}`;
    if (!nodeSet.has(key)) {
      nodeSet.add(key);
      nodes.push({
        id: key,
        label: `${imp.citing_law}\n${imp.citing_article}`,
        law_title: imp.citing_law,
        article_no: imp.citing_article,
        risk_level: imp.risk_level as RiskLevel,
        risk_score: imp.risk_score,
        level: "direct",
        reference_text: imp.reference_text,
        keyword: imp.keyword,
      });
    }
    edges.push({
      from: triggerKey,
      to: key,
      risk_level: imp.risk_level as RiskLevel,
      is_indirect: false,
    });
  });

  impact.indirect_impacts.forEach((imp) => {
    const key = `${imp.citing_law}${imp.citing_article}`;
    const viaKey = imp.via_article || triggerKey;
    if (!nodeSet.has(key)) {
      nodeSet.add(key);
      nodes.push({
        id: key,
        label: `${imp.citing_law}\n${imp.citing_article}`,
        law_title: imp.citing_law,
        article_no: imp.citing_article,
        risk_level: "Potential",
        risk_score: imp.risk_score,
        level: "indirect",
        reference_text: imp.reference_text,
        keyword: imp.keyword,
      });
    }
    edges.push({
      from: viaKey,
      to: key,
      risk_level: "Potential",
      is_indirect: true,
    });
  });

  return { nodes, edges };
}

// ─────────────────────────────────────────────
// Mock: 法律条文列表
// ─────────────────────────────────────────────

export function mockLawArticles(lawTitle: string, count = 20): LawArticleItem[] {
  const statuses = ["有效", "已修改", "已废止"];
  return Array.from({ length: count }, (_, i) => {
    const articleNo = makeArticleNo(i);
    return {
      article_no: articleNo,
      text_preview: `【${lawTitle}】${articleNo} 示例条文内容：为了保护相关主体的合法权益...`,
      effective_start: `20${randomInt(0, 24)}-01-01`,
      status: randomPick(statuses),
    };
  });
}

// ─────────────────────────────────────────────
// Mock: 法律列表
// ─────────────────────────────────────────────

export function mockLawList(): string[] {
  return [...LAWS];
}
