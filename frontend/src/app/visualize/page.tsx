"use client";

import { useState, useCallback } from "react";
import dynamic from "next/dynamic";
import SearchPanel from "@/components/layout/SearchPanel";
import DetailPanel, { type DetailPanelData } from "@/components/layout/DetailPanel";
import DriftTimeline from "@/components/visualizer/DriftTimeline";
import {
  mockLawList,
  mockDominoImpact,
  mockDriftNodes,
  convertDominoToGraph,
} from "@/lib/mock";
import type {
  DominoNode,
  DominoEdge,
  DriftNode,
  SearchConfig,
} from "@/types";
import { GitBranch, Activity, AlertCircle } from "lucide-react";

// vis-network 需要客户端渲染，使用 dynamic import
const DominoGraph = dynamic(() => import("@/components/visualizer/DominoGraph"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-sm text-slate-500">
      <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-slate-300" />
      加载拓扑图...
    </div>
  ),
});

type TabKey = "domino" | "drift";

export default function VisualizePage() {
  // ── 初始化 ──
  const initialLaws = mockLawList();
  const initialLaw = initialLaws[0] ?? "";

  // ── 状态 ──
  const [laws] = useState<string[]>(initialLaws);
  const [selectedLaw, setSelectedLaw] = useState(initialLaw);
  const [activeTab, setActiveTab] = useState<TabKey>("domino");

  // Domino 状态（初始值同步生成 mock 数据）
  const [dominoNodes, setDominoNodes] = useState<DominoNode[]>(() => {
    if (!initialLaw) return [];
    const impact = mockDominoImpact(initialLaw, "第一条");
    return convertDominoToGraph(impact).nodes;
  });
  const [dominoEdges, setDominoEdges] = useState<DominoEdge[]>(() => {
    if (!initialLaw) return [];
    const impact = mockDominoImpact(initialLaw, "第一条");
    return convertDominoToGraph(impact).edges;
  });
  const [dominoLoading, setDominoLoading] = useState(false);
  const [dominoError, setDominoError] = useState("");

  // Drift 状态（初始值同步生成 mock 数据）
  const [driftNodes, setDriftNodes] = useState<DriftNode[]>(() => {
    if (!initialLaw) return [];
    return mockDriftNodes("第一条", initialLaw, 5);
  });
  const [driftLoading, setDriftLoading] = useState(false);
  const [driftError, setDriftError] = useState("");

  // 详情面板
  const [detailData, setDetailData] = useState<DetailPanelData | null>(null);

  // ── Mock 数据加载 ──
  const loadDominoMock = useCallback((law: string, article: string) => {
    setDominoLoading(true);
    setDominoError("");
    setTimeout(() => {
      try {
        const impact = mockDominoImpact(law, article);
        const { nodes, edges } = convertDominoToGraph(impact);
        setDominoNodes(nodes);
        setDominoEdges(edges);
      } catch {
        setDominoError("加载拓扑数据失败");
      } finally {
        setDominoLoading(false);
      }
    }, 400);
  }, []);

  const loadDriftMock = useCallback((law: string, article: string) => {
    setDriftLoading(true);
    setDriftError("");
    setTimeout(() => {
      try {
        const nodes = mockDriftNodes(article, law, 5);
        setDriftNodes(nodes);
      } catch {
        setDriftError("加载血缘数据失败");
      } finally {
        setDriftLoading(false);
      }
    }, 300);
  }, []);

  // ── 事件处理 ──
  const handleLawSelect = useCallback(
    (law: string) => {
      setSelectedLaw(law);
      if (law) {
        loadDominoMock(law, "第一条");
        loadDriftMock(law, "第一条");
      }
    },
    [loadDominoMock, loadDriftMock]
  );

  const handleSearch = useCallback(
    (query: string, config: SearchConfig) => {
      // Mock 模式下搜索只是重新加载当前法律的数据
      // query 和 config 保留供真实 API 接入时使用
      void query;
      void config;
      if (selectedLaw) {
        loadDominoMock(selectedLaw, "第一条");
        loadDriftMock(selectedLaw, "第一条");
      }
    },
    [selectedLaw, loadDominoMock, loadDriftMock]
  );

  const handleDominoNodeClick = useCallback(
    (nodeId: string) => {
      const node = dominoNodes.find((n) => n.id === nodeId);
      if (node) {
        setDetailData({ type: "domino", node });
        // 如果是直接引用节点，模拟加载其下游影响
        if (node.level === "direct") {
          loadDominoMock(node.law_title, node.article_no);
        }
      }
    },
    [dominoNodes, loadDominoMock]
  );

  const handleDriftNodeSelect = useCallback((node: DriftNode) => {
    setDetailData({ type: "drift", node });
  }, []);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] gap-0"
    >
      {/* 左侧：检索面板 */}
      <aside className="w-72 shrink-0 border-r border-slate-800 bg-slate-900/30"
      >
        <SearchPanel
          laws={laws}
          selectedLaw={selectedLaw}
          onLawSelect={handleLawSelect}
          onSearch={handleSearch}
          loading={dominoLoading || driftLoading}
        />
      </aside>

      {/* 中间主区域 */}
      <main className="flex min-w-0 flex-1 flex-col"
      >
        {/* Tabs */}
        <div className="flex border-b border-slate-800"
        >
          <button
            onClick={() => setActiveTab("domino")}
            className={`flex items-center gap-2 px-5 py-3 text-sm font-medium transition-colors ${
              activeTab === "domino"
                ? "border-b-2 border-sky-400 text-sky-400"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            <GitBranch className="h-4 w-4" />
            多米诺拓扑图
          </button>
          <button
            onClick={() => setActiveTab("drift")}
            className={`flex items-center gap-2 px-5 py-3 text-sm font-medium transition-colors ${
              activeTab === "drift"
                ? "border-b-2 border-amber-400 text-amber-400"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            <Activity className="h-4 w-4" />
            法律血缘轴
          </button>
        </div>

        {/* 错误提示 */}
        {(dominoError || driftError) && (
          <div className="flex items-center gap-2 border-b border-red-900/30 bg-red-950/30 px-4 py-2 text-xs text-red-400"
          >
            <AlertCircle className="h-3.5 w-3.5" />
            {dominoError || driftError}
          </div>
        )}

        {/* 内容区 */}
        <div className="flex-1 overflow-hidden p-4"
        >
          {activeTab === "domino" ? (
            <div className="flex h-full flex-col"
            >
              <div className="mb-2 flex items-center justify-between"
              >
                <h2 className="text-sm font-medium text-slate-300"
                >
                  法条引用传导网络
                  {dominoNodes.length > 0 && (
                    <span className="ml-2 text-xs text-slate-500"
                    >
                      {dominoNodes.length} 节点 / {dominoEdges.length} 边
                    </span>
                  )}
                </h2>
                <div className="flex items-center gap-3 text-[11px] text-slate-500"
                >
                  <span className="flex items-center gap-1"
                  >
                    <span className="inline-block h-2.5 w-2.5 rounded-full bg-red-500" />
                    高风险
                  </span>
                  <span className="flex items-center gap-1"
                  >
                    <span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />
                    中风险
                  </span>
                  <span className="flex items-center gap-1"
                  >
                    <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />
                    低风险
                  </span>
                </div>
              </div>
              <div className="flex-1 rounded-lg border border-slate-800 bg-slate-900/30"
              >
                {dominoLoading ? (
                  <div className="flex h-full items-center justify-center text-sm text-slate-500"
                  >
                    <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-slate-300" />
                    加载拓扑图...
                  </div>
                ) : dominoNodes.length > 0 ? (
                  <DominoGraph
                    nodes={dominoNodes}
                    edges={dominoEdges}
                    onNodeClick={handleDominoNodeClick}
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-slate-500"
                  >
                    暂无拓扑数据，请选择法律后搜索
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="h-full overflow-auto rounded-lg border border-slate-800 bg-slate-900/30 p-4"
            >
              {driftLoading ? (
                <div className="flex h-full items-center justify-center text-sm text-slate-500"
                >
                  <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-slate-300" />
                  加载血缘数据...
                </div>
              ) : driftNodes.length > 0 ? (
                <DriftTimeline
                  nodes={driftNodes}
                  onSelectNode={handleDriftNodeSelect}
                />
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-500"
                >
                  暂无血缘数据，请选择法律后搜索
                </div>
              )}
            </div>
          )}
        </div>
      </main>

      {/* 右侧：详情面板 */}
      <aside className="w-80 shrink-0 border-l border-slate-800 bg-slate-900/30"
      >
        <DetailPanel data={detailData} />
      </aside>
    </div>
  );
}
