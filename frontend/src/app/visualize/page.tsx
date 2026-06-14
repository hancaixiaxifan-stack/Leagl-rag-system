"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import DriftTimeline from "@/components/visualizer/DriftTimeline";
import {
  fetchDominoImpact,
  fetchKnowledgeGraphOverview,
  fetchKnowledgeGraphSubgraph,
  getErrorMessage,
} from "@/lib/api";
import { mockDriftNodes } from "@/lib/mock";
import type {
  DominoImpact,
  DominoImpactItem,
  DriftNode,
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
  KnowledgeGraphResponse,
} from "@/types";
import {
  AlertCircle,
  CircleDot,
  GitBranch,
  Network,
  RotateCcw,
  Search,
} from "lucide-react";

const DominoGraph = dynamic(() => import("@/components/visualizer/DominoGraph"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-sm text-[#7c735f]">
      <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-[#d8d0c1] border-t-[#1f3a5f]" />
      加载知识图谱...
    </div>
  ),
});

type GraphFilter = "all" | "law" | "article";

const WHOLE_LAW = "整部法律";
const EMPTY_GRAPH: KnowledgeGraphResponse = {
  nodes: [],
  edges: [],
  stats: {
    mode: "overview",
    total_nodes: 0,
    total_edges: 0,
    returned_nodes: 0,
    returned_edges: 0,
    law_count: 0,
    article_count: 0,
    truncated: false,
  },
};

function unwrapLawTitle(title: string): string {
  const trimmed = title.trim();
  if (trimmed.startsWith("《") && trimmed.includes("》")) {
    return trimmed.slice(1, trimmed.indexOf("》"));
  }
  return trimmed;
}

function articleNodeId(lawTitle: string, articleNo: string): string {
  const law = unwrapLawTitle(lawTitle);
  return articleNo === WHOLE_LAW ? `law::${law}` : `article::${law}::${articleNo}`;
}

function filterGraph(
  nodes: KnowledgeGraphNode[],
  edges: KnowledgeGraphEdge[],
  query: string,
  filter: GraphFilter,
  impact?: { direct: Set<string>; indirect: Set<string>; trigger?: string }
) {
  const normalized = query.trim();
  let filteredNodes = nodes;

  if (filter === "law") {
    filteredNodes = filteredNodes.filter((node) => node.node_type === "law");
  } else if (filter === "article") {
    filteredNodes = filteredNodes.filter((node) => node.node_type === "article");
  }

  if (normalized) {
    filteredNodes = filteredNodes.filter(
      (node) =>
        node.law_title.includes(normalized) ||
        node.article_no.includes(normalized) ||
        node.label.includes(normalized) ||
        node.keyword?.includes(normalized)
    );
  }

  const visibleIds = new Set(filteredNodes.map((node) => node.id));
  const highlightedNodes = filteredNodes.map((node) => {
    if (!impact) return node;
    if (node.id === impact.trigger) {
      return { ...node, level: "trigger" as const, risk_level: "High" };
    }
    if (impact.direct.has(node.id)) {
      return { ...node, level: "direct" as const, risk_level: "High" };
    }
    if (impact.indirect.has(node.id)) {
      return { ...node, level: "indirect" as const, risk_level: "Potential" };
    }
    return node;
  });

  const filteredEdges = edges
    .filter((edge) => visibleIds.has(edge.from) && visibleIds.has(edge.to))
    .map((edge) => {
      if (!impact) return edge;
      const hot =
        (edge.from === impact.trigger && impact.direct.has(edge.to)) ||
        (impact.direct.has(edge.from) && impact.indirect.has(edge.to));
      return hot ? { ...edge, risk_level: "High", is_indirect: false } : edge;
    });

  return { nodes: highlightedNodes, edges: filteredEdges };
}

export default function VisualizePage() {
  const [graph, setGraph] = useState<KnowledgeGraphResponse>(EMPTY_GRAPH);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<GraphFilter>("all");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [selectedLineageNode, setSelectedLineageNode] = useState<DriftNode | null>(null);
  const [dominoResult, setDominoResult] = useState<DominoImpact | null>(null);
  const [dominoLoading, setDominoLoading] = useState(false);
  const [dominoError, setDominoError] = useState("");

  useEffect(() => {
    let mounted = true;
    fetchKnowledgeGraphOverview()
      .then((data) => {
        if (!mounted) return;
        setGraph(data);
        setSelectedNodeId(data.nodes[0]?.id ?? "");
        setError("");
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        setError(getErrorMessage(err));
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, []);

  const selectedNode =
    graph.nodes.find((node) => node.id === selectedNodeId) ?? graph.nodes[0] ?? null;

  const viewMode = graph.stats.mode === "subgraph" ? "subgraph" : "overview";

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError("");
    setQuery("");
    setFilter("all");
    setDominoResult(null);
    setDominoError("");
    setSelectedLineageNode(null);
    try {
      const data = await fetchKnowledgeGraphOverview();
      setGraph(data);
      setSelectedNodeId(data.nodes[0]?.id ?? "");
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSubgraph = useCallback(async (node: KnowledgeGraphNode) => {
    setLoading(true);
    setError("");
    setQuery("");
    setFilter("all");
    setDominoResult(null);
    setDominoError("");
    setSelectedLineageNode(null);
    try {
      const articleNo = node.node_type === "article" ? node.article_no : undefined;
      const data = await fetchKnowledgeGraphSubgraph(node.law_title, articleNo, 1, 220);
      setGraph(data);
      setSelectedNodeId(node.id);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const impact = useMemo(() => {
    if (!dominoResult || !selectedNode) return undefined;
    const direct = new Set(
      dominoResult.direct_impacts.map((item) => articleNodeId(item.citing_law, item.citing_article))
    );
    const indirect = new Set(
      dominoResult.indirect_impacts.map((item) => articleNodeId(item.citing_law, item.citing_article))
    );
    return { direct, indirect, trigger: selectedNode.id };
  }, [dominoResult, selectedNode]);

  const visibleGraph = useMemo(
    () => filterGraph(graph.nodes, graph.edges, query, filter, impact),
    [graph, query, filter, impact]
  );

  const selectedLineage = useMemo(() => {
    if (!selectedNode || selectedNode.node_type === "law") return [];
    return mockDriftNodes(selectedNode.article_no, selectedNode.law_title, 5);
  }, [selectedNode]);

  const resetLocalView = () => {
    setQuery("");
    setFilter("all");
    setSelectedNodeId(graph.nodes[0]?.id ?? "");
    setSelectedLineageNode(null);
    setDominoResult(null);
    setDominoError("");
  };

  const loadDominoForNode = useCallback(async (node: KnowledgeGraphNode) => {
    if (node.node_type !== "article") return;
    setDominoLoading(true);
    setDominoError("");
    setDominoResult(null);

    try {
      const result = await fetchDominoImpact(node.law_title, node.article_no, true, 2);
      setDominoResult(result);
    } catch (err: unknown) {
      setDominoError(getErrorMessage(err));
    } finally {
      setDominoLoading(false);
    }
  }, []);

  const handleNodeClick = useCallback(
    (nodeId: string) => {
      const node = graph.nodes.find((item) => item.id === nodeId);
      if (!node) return;
      setSelectedNodeId(nodeId);
      setSelectedLineageNode(null);
      setDominoResult(null);
      setDominoError("");
      if (
        node.node_type === "law" &&
        (viewMode === "overview" || graph.stats.target_law !== node.law_title)
      ) {
        setDominoLoading(false);
        void loadSubgraph(node);
        return;
      }
      if (node.node_type === "article") {
        void loadDominoForNode(node);
      }
    },
    [graph.nodes, graph.stats.target_law, loadDominoForNode, loadSubgraph, viewMode]
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <section className="legal-card flex shrink-0 flex-wrap items-center justify-between gap-3 px-4 py-2.5">
        <div className="flex min-w-[240px] items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-md bg-[#1f3a5f] text-[#fffefa]">
            <Network className="h-4 w-4" />
          </span>
          <div>
            <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-[#8a7f6c]">
              {viewMode === "overview" ? "法律层聚合图" : "按需展开子图"}
            </div>
            <h1 className="text-base font-semibold tracking-tight text-[#1f2933]">法律知识图谱</h1>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <StatCard label="节点" value={graph.stats.returned_nodes} />
          <StatCard label="边" value={graph.stats.returned_edges} />
          <StatCard label="法律" value={graph.stats.law_count} />
        </div>
      </section>

      <section className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="legal-card flex min-h-0 flex-col overflow-hidden">
          <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-[#e4ded3] p-3">
            <div className="relative min-w-[260px] flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a7f6c]" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="在当前视图搜索法律、条文或关键词..."
                className="legal-input w-full py-2.5 pl-9 pr-3 text-[#1f2933] placeholder:text-[#a09684]"
              />
            </div>
            <SegmentedFilter value={filter} onChange={setFilter} />
            {viewMode === "subgraph" && (
              <button
                onClick={loadOverview}
                className="inline-flex items-center gap-2 rounded-md border border-[#1f3a5f] bg-[#1f3a5f] px-3 py-2 text-sm font-medium text-[#fffefa] transition-all hover:bg-[#172d4b] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f3a5f]"
              >
                返回总览
              </button>
            )}
            <button
              onClick={resetLocalView}
              className="inline-flex items-center gap-2 rounded-md border border-[#d8d0c1] bg-[#fffefa] px-3 py-2 text-sm font-medium text-[#5f574a] transition-all hover:border-[#1f3a5f] hover:text-[#1f3a5f] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f3a5f]"
            >
              <RotateCcw className="h-4 w-4" />
              重置
            </button>
          </div>

          <div className="flex shrink-0 items-center justify-between border-b border-[#e4ded3] px-4 py-2 text-xs text-[#7c735f]">
            <div className="flex flex-wrap items-center gap-3">
              <LegendDot color="#1f3a5f" label="法律节点" />
              <LegendDot color="#b42318" label="高连接" />
              <LegendDot color="#b45309" label="中连接" />
              <LegendDot color="#047857" label="低连接" />
              <LegendDot color="#4338ca" label="多米诺链路" />
            </div>
            <span>
              当前视图：{visibleGraph.nodes.length.toLocaleString()} 节点 /{" "}
              {visibleGraph.edges.length.toLocaleString()} 边
            </span>
          </div>

          <div className="relative flex-1 bg-[#fbfaf6]">
            {loading ? (
              <GraphState text="正在读取图谱视图..." />
            ) : error ? (
              <GraphState text={error} tone="error" />
            ) : visibleGraph.nodes.length > 0 ? (
              <DominoGraph
                nodes={visibleGraph.nodes}
                edges={visibleGraph.edges}
                onNodeClick={handleNodeClick}
              />
            ) : (
              <GraphState text="没有匹配的图谱节点" />
            )}
          </div>
        </div>

        <aside className="legal-card flex min-h-0 flex-col overflow-hidden">
          <NodeDetailPanel
            node={selectedNode}
            viewMode={viewMode}
            dominoLoading={dominoLoading}
          />

          <section className="flex min-h-0 flex-[1.35] flex-col border-t border-[#e4ded3] p-3">
            <div className="mb-2 flex shrink-0 items-center justify-between border-b border-[#e4ded3] pb-2">
              <div>
                <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.16em] text-[#8a7f6c]">
                  <GitBranch className="h-3.5 w-3.5" />
                  法律血缘轴
                </div>
                <h2 className="mt-1 text-sm font-semibold text-[#1f2933]">
                  {selectedNode?.node_type === "article" ? selectedNode.article_no : "选择条文节点"}
                </h2>
              </div>
            </div>
            {selectedNode?.node_type === "article" ? (
              <div className="min-h-0 flex-1 overflow-auto pr-1">
                <DriftTimeline nodes={selectedLineage} onSelectNode={setSelectedLineageNode} />
              </div>
            ) : (
              <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-dashed border-[#d8d0c1] bg-[#f8f6f1] px-6 text-center text-sm leading-6 text-[#7c735f]">
                点击法律节点会展开局部条文子图。选择具体条文后，这里展示该条文的版本血缘轴。
              </div>
            )}
            {selectedLineageNode && (
              <div className="mt-3 rounded-md border border-[#e4ded3] bg-[#f8f6f1] p-3 text-xs leading-6 text-[#5f574a]">
                <div className="font-semibold text-[#1f2933]">{selectedLineageNode.change_type}</div>
                <div className="mt-1">{selectedLineageNode.text_preview}</div>
              </div>
            )}
          </section>

          <DominoResultPanel
            result={dominoResult}
            loading={dominoLoading}
            error={dominoError}
            selectedNode={selectedNode}
          />
        </aside>
      </section>
    </div>
  );
}

function GraphState({ text, tone = "normal" }: { text: string; tone?: "normal" | "error" }) {
  return (
    <div className="flex h-full items-center justify-center px-6 text-center text-sm text-[#7c735f]">
      {tone === "error" && <AlertCircle className="mr-2 h-4 w-4 text-[#b42318]" />}
      {text}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="min-w-20 rounded-md border border-[#e4ded3] bg-[#f8f6f1] px-3 py-2 text-right">
      <div className="text-[10px] font-medium text-[#8a7f6c]">{label}</div>
      <div className="text-lg font-semibold leading-5 text-[#1f2933]">{value.toLocaleString()}</div>
    </div>
  );
}

function SegmentedFilter({
  value,
  onChange,
}: {
  value: GraphFilter;
  onChange: (value: GraphFilter) => void;
}) {
  const options: { value: GraphFilter; label: string }[] = [
    { value: "all", label: "全部" },
    { value: "law", label: "法律" },
    { value: "article", label: "条文" },
  ];
  return (
    <div className="inline-flex rounded-md border border-[#d8d0c1] bg-[#fffefa] p-1">
      {options.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={`rounded px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f3a5f] ${
            value === option.value
              ? "bg-[#1f3a5f] text-[#fffefa]"
              : "text-[#6f6658] hover:bg-[#f3eee5] hover:text-[#1f2933]"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

function NodeDetailPanel({
  node,
  viewMode,
  dominoLoading,
}: {
  node: KnowledgeGraphNode | null;
  viewMode: "overview" | "subgraph";
  dominoLoading: boolean;
}) {
  if (!node) {
    return (
      <section className="p-4">
        <div className="flex h-44 flex-col items-center justify-center text-center text-sm text-[#7c735f]">
          <CircleDot className="mb-2 h-8 w-8 opacity-40" />
          点击图谱节点查看内容
        </div>
      </section>
    );
  }

  const isLaw = node.node_type === "law";
  return (
    <section className="shrink-0 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-[0.16em] text-[#8a7f6c]">
            {isLaw ? "法律节点" : "条文节点"}
          </div>
          <h2 className="mt-1 line-clamp-2 text-base font-semibold leading-5 text-[#1f2933]">
            {isLaw ? node.law_title : `《${node.law_title}》${node.article_no}`}
          </h2>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <MiniMetric label="入边" value={node.inbound_count} />
        <MiniMetric label="出边" value={node.outbound_count} />
        <MiniMetric label="度数" value={node.degree} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs leading-5 text-[#5f574a]">
        <InfoLine label="法律" value={node.law_title} />
        <InfoLine label="条文" value={node.article_no} />
        <InfoLine
          label="类型"
          value={isLaw ? (viewMode === "overview" ? "法律聚合节点" : "局部法律节点") : node.keyword ?? "引用条文"}
        />
        {node.reference_text && (
          <div className="col-span-2">
            <div className="text-[11px] font-medium text-[#8a7f6c]">
              {isLaw ? "节点说明" : "引用片段"}
            </div>
            <div className="mt-1 line-clamp-2 rounded-md border border-[#e4ded3] bg-[#f8f6f1] p-2 text-xs leading-5">
              {node.reference_text}
            </div>
          </div>
        )}
      </div>
      {!isLaw && (
        <div className="mt-2 rounded-md border border-[#e4ded3] bg-[#f8f6f1] px-3 py-1.5 text-xs text-[#7c735f]">
          {dominoLoading ? "正在自动加载多米诺影响链..." : "多米诺影响链已自动展示在下方。"}
        </div>
      )}
    </section>
  );
}

function DominoResultPanel({
  result,
  loading,
  error,
  selectedNode,
}: {
  result: DominoImpact | null;
  loading: boolean;
  error: string;
  selectedNode: KnowledgeGraphNode | null;
}) {
  const impacts = result ? [...result.direct_impacts, ...result.indirect_impacts] : [];
  return (
    <section className="h-48 shrink-0 border-t border-[#e4ded3] p-3">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <div className="text-xs font-medium uppercase tracking-[0.16em] text-[#8a7f6c]">
            多米诺影响链
          </div>
          <div className="mt-1 text-sm text-[#5f574a]">
            {result ? `影响 ${result.total_affected_articles} 个下游条文` : "选择条文后自动加载"}
          </div>
        </div>
      </div>
      <div className="h-[116px] overflow-auto pr-1">
        {loading ? (
          <div className="rounded-md border border-[#e4ded3] bg-[#f8f6f1] p-3 text-sm text-[#7c735f]">
            正在沿引用链计算影响路径...
          </div>
        ) : error ? (
          <div className="rounded-md border border-[#f3b4ad] bg-[#fff1f0] p-3 text-sm text-[#9f1f17]">
            {error}
          </div>
        ) : impacts.length > 0 ? (
          <div className="space-y-2">
            {impacts.slice(0, 20).map((item, index) => (
              <ImpactRow key={`${item.citing_law}-${item.citing_article}-${index}`} item={item} />
            ))}
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-[#d8d0c1] bg-[#f8f6f1] p-3 text-sm leading-6 text-[#7c735f]">
            {selectedNode?.node_type === "article"
              ? "正在准备该条文的直接和间接影响链。"
              : "法律节点只负责展开局部图，请先选择具体条文。"}
          </div>
        )}
      </div>
    </section>
  );
}

function ImpactRow({ item }: { item: DominoImpactItem }) {
  return (
    <div className="rounded-md border border-[#e4ded3] bg-[#fffefa] p-3 text-xs leading-5">
      <div className="font-medium text-[#1f2933]">
        {item.citing_law}
        <span className="ml-1 text-[#8a7f6c]">{item.citing_article}</span>
      </div>
      <div className="mt-1 line-clamp-2 text-[#6f6658]">{item.reference_text || "暂无引用片段"}</div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-[#e4ded3] bg-[#f8f6f1] p-2">
      <div className="text-[10px] text-[#8a7f6c]">{label}</div>
      <div className="text-base font-semibold leading-5 text-[#1f2933]">{value.toLocaleString()}</div>
    </div>
  );
}

function InfoLine({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] font-medium text-[#8a7f6c]">{label}</div>
      <div className="mt-0.5 text-sm text-[#394453]">{value}</div>
    </div>
  );
}
