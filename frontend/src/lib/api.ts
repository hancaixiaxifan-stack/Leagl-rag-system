import type {
  AskResponse,
  CounterfactualResponse,
  DirectionInfo,
  DominoImpact,
  DriftReport,
  KnowledgeGraphResponse,
  LawArticlesResponse,
} from "@/types";

export type {
  AskResponse,
  ChapterData,
  Citation,
  CounterfactualImpactItem,
  CounterfactualResponse,
  DirectionInfo,
  DominoImpact,
  DominoImpactItem,
  DriftReport,
  DriftReportSummary,
  HighDriftDetail,
  HotspotItem,
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
  KnowledgeGraphResponse,
  KnowledgeGraphStats,
  LawArticleItem,
  LawArticlesResponse,
  LineageStep,
} from "@/types";

const API_BASE = "/api/proxy";

export function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

interface ApiErrorBody {
  detail?: string;
  error?: string;
}

async function readErrorMessage(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch((): ApiErrorBody => ({}));
  if (isApiErrorBody(body)) return body.detail ?? body.error ?? fallback;
  return fallback;
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null) return false;
  const body = value as ApiErrorBody;
  return (
    (body.detail === undefined || typeof body.detail === "string") &&
    (body.error === undefined || typeof body.error === "string")
  );
}

export async function fetchLawList(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/drift_report/laws`);
  if (!res.ok) throw new Error(`Failed to fetch law list: ${res.status}`);
  const data = await res.json();
  return data.laws || [];
}

export async function fetchDriftReport(lawTitle: string): Promise<DriftReport> {
  const res = await fetch(`${API_BASE}/drift_report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ law_title: lawTitle }),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, `Failed to fetch drift report: ${res.status}`));
  }
  return res.json();
}

export async function fetchDominoImpact(
  lawTitle: string,
  articleNo: string,
  recursive = false,
  maxDepth = 2
): Promise<DominoImpact> {
  const res = await fetch(`${API_BASE}/domino_impact`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      law_title: lawTitle,
      article_no: articleNo,
      recursive,
      max_depth: maxDepth,
    }),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, `Failed to fetch domino impact: ${res.status}`));
  }
  return res.json();
}

export async function fetchKnowledgeGraph(maxNodes = 1200): Promise<KnowledgeGraphResponse> {
  const params = new URLSearchParams({ max_nodes: String(maxNodes) });
  const res = await fetch(`${API_BASE}/knowledge_graph?${params.toString()}`);
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, `Failed to fetch knowledge graph: ${res.status}`));
  }
  return res.json();
}

export async function fetchKnowledgeGraphOverview(): Promise<KnowledgeGraphResponse> {
  const res = await fetch(`${API_BASE}/knowledge_graph/overview`);
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, `Failed to fetch knowledge graph overview: ${res.status}`));
  }
  return res.json();
}

export async function fetchKnowledgeGraphSubgraph(
  lawTitle: string,
  articleNo?: string,
  maxHops = 1,
  maxNeighbors = 220
): Promise<KnowledgeGraphResponse> {
  const params = new URLSearchParams({
    law_title: lawTitle,
    max_hops: String(maxHops),
    max_neighbors: String(maxNeighbors),
  });
  if (articleNo) params.set("article_no", articleNo);
  const res = await fetch(`${API_BASE}/knowledge_graph/subgraph?${params.toString()}`);
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, `Failed to fetch knowledge graph subgraph: ${res.status}`));
  }
  return res.json();
}

export async function askQuestion(question: string, currentDate?: string): Promise<AskResponse> {
  const res = await fetch(`${API_BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, current_date: currentDate }),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, `Ask failed: ${res.status}`));
  }
  return res.json();
}

export async function fetchCounterfactual(
  lawTitle: string,
  articleNo: string,
  direction: string,
  magnitude?: string,
  includeIndirect = true,
  maxDepth = 2
): Promise<CounterfactualResponse> {
  const res = await fetch(`${API_BASE}/counterfactual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      law_title: lawTitle,
      article_no: articleNo,
      direction,
      magnitude,
      include_indirect: includeIndirect,
      max_depth: maxDepth,
    }),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, `Counterfactual failed: ${res.status}`));
  }
  return res.json();
}

export async function fetchCounterfactualDirections(): Promise<DirectionInfo[]> {
  const res = await fetch(`${API_BASE}/counterfactual/directions`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.directions || [];
}

export async function fetchLawArticles(
  lawTitle: string,
  currentDate?: string
): Promise<LawArticlesResponse> {
  const params = new URLSearchParams();
  if (currentDate) params.set("current_date", currentDate);
  const qs = params.toString();
  const res = await fetch(`${API_BASE}/law_articles/${encodeURIComponent(lawTitle)}${qs ? `?${qs}` : ""}`);
  if (!res.ok) {
    throw new Error(await readErrorMessage(res, `Failed to fetch law articles: ${res.status}`));
  }
  return res.json();
}
