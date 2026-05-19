"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import * as echarts from "echarts";
import {
  fetchDominoImpact,
  fetchLawList,
  fetchLawArticles,
  type DominoImpact,
  type LawArticlesResponse,
} from "@/lib/api";
import { AlertCircle, Search, ToggleLeft, ToggleRight, ChevronDown } from "lucide-react";

const RISK_COLORS: Record<string, string> = {
  High: "#ef4444",
  Medium: "#f59e0b",
  Low: "#10b981",
  Potential: "#6366f1",
  Unknown: "#94a3b8",
};

const RISK_LABELS: Record<string, string> = {
  High: "高风险",
  Medium: "中风险",
  Low: "低风险",
  Potential: "潜在影响",
  Unknown: "未知",
};

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    有效: "text-emerald-400 bg-emerald-500/15",
    尚未实施: "text-amber-400 bg-amber-500/15",
    已修改: "text-slate-400 bg-slate-500/15",
    已废止: "text-red-400 bg-red-500/15",
  };
  const cls = map[status] || "text-slate-400 bg-slate-500/15";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>
      {status}
    </span>
  );
}

function ArticlePreview({ article, lawTitle }: { article: NonNullable<LawArticlesResponse["articles"][number]>; lawTitle: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-slate-200">{article.article_no}</span>
        <StatusBadge status={article.status} />
      </div>
      {article.effective_start && (
        <div className="text-[11px] text-slate-500 mb-2">
          施行于 {article.effective_start}
          {article.effective_end && ` → 失效于 ${article.effective_end}`}
        </div>
      )}
      <div className="text-xs leading-relaxed text-slate-400">{article.text_preview}</div>
    </div>
  );
}

export default function DominoPage() {
  const [laws, setLaws] = useState<string[]>([]);
  const [lawTitle, setLawTitle] = useState("");
  const [articleNo, setArticleNo] = useState("");
  const [articles, setArticles] = useState<LawArticlesResponse["articles"]>([]);
  const [selectedArticle, setSelectedArticle] = useState<LawArticlesResponse["articles"][number] | null>(null);
  const [recursive, setRecursive] = useState(false);
  const [maxDepth, setMaxDepth] = useState(2);
  const [impact, setImpact] = useState<DominoImpact | null>(null);
  const [loading, setLoading] = useState(false);
  const [lawLoading, setLawLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [lawDropdownOpen, setLawDropdownOpen] = useState(false);
  const [articleDropdownOpen, setArticleDropdownOpen] = useState(false);

  const graphRef = useRef<HTMLDivElement>(null);
  const graphChart = useRef<echarts.ECharts | null>(null);

  // 预置演示选项：民法典第五百一十条（46条下游引用，引用网络丰富）
  const DEFAULT_LAW = "中华人民共和国民法典";
  const DEFAULT_ARTICLE = "第五百一十条";

  // 加载法律列表
  useEffect(() => {
    fetchLawList()
      .then((list) => {
        setLaws(list);
        // 预选默认法律
        if (list.includes(DEFAULT_LAW)) {
          setLawTitle(DEFAULT_LAW);
          loadArticles(DEFAULT_LAW, DEFAULT_ARTICLE);
        }
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // 加载条文列表
  const loadArticles = useCallback(async (law: string, preselectArticle?: string) => {
    if (!law) return;
    setLawLoading(true);
    setArticles([]);
    setSelectedArticle(null);
    setArticleNo("");
    try {
      const currentDate = new Date().toISOString().split("T")[0];
      const data = await fetchLawArticles(law, currentDate);
      setArticles(data.articles);
      if (data.articles.length > 0) {
        // 优先使用预选条文号，否则默认选第一条
        const target = preselectArticle
          ? data.articles.find((a) => a.article_no === preselectArticle) ?? data.articles[0]
          : data.articles[0];
        setArticleNo(target.article_no);
        setSelectedArticle(target);
      }
    } catch {
      // ignore
    } finally {
      setLawLoading(false);
    }
  }, []);

  // 切换法律时重新加载条文
  const handleLawSelect = (law: string) => {
    setLawTitle(law);
    setLawDropdownOpen(false);
    setImpact(null);
    loadArticles(law);
  };

  // 切换条文时更新预览
  const handleArticleSelect = (art: LawArticlesResponse["articles"][number]) => {
    setArticleNo(art.article_no);
    setSelectedArticle(art);
    setArticleDropdownOpen(false);
  };

  const search = useCallback(async () => {
    if (!lawTitle || !articleNo) return;
    setLoading(true);
    setError("");
    setSelectedNode(null);
    try {
      const data = await fetchDominoImpact(lawTitle, articleNo, recursive, maxDepth);
      setImpact(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [lawTitle, articleNo, recursive, maxDepth]);

  useEffect(() => {
    if (!impact || !graphRef.current) return;

    if (graphChart.current) {
      graphChart.current.dispose();
    }

    const chart = echarts.init(graphRef.current, undefined, { renderer: "canvas" });
    graphChart.current = chart;

    const nodes: any[] = [];
    const edges: any[] = [];
    const nodeSet = new Set<string>();

    const triggerKey = impact.trigger_node;
    nodeSet.add(triggerKey);
    nodes.push({
      id: triggerKey,
      name: triggerKey,
      symbolSize: 60,
      itemStyle: {
        color: (impact.drift_score ?? 0) >= 0.2 ? "#ef4444" : "#f59e0b",
        borderColor: "#e2e8f0",
        borderWidth: 2,
        shadowBlur: 20,
        shadowColor: (impact.drift_score ?? 0) >= 0.2 ? "rgba(239,68,68,0.4)" : "rgba(245,158,11,0.3)",
      },
      label: { show: true, color: "#e2e8f0", fontSize: 12, fontWeight: "bold" },
      x: 0, y: 0, fixed: true, category: "trigger",
    });

    impact.direct_impacts.forEach((imp) => {
      const key = `${imp.citing_law}${imp.citing_article}`;
      if (!nodeSet.has(key)) {
        nodeSet.add(key);
        nodes.push({
          id: key,
          name: `${imp.citing_law}\n${imp.citing_article}`,
          symbolSize: Math.max(30, 20 + (imp.reference_text?.length || 0) / 10),
          itemStyle: { color: RISK_COLORS[imp.risk_level] || RISK_COLORS.Unknown, borderColor: "#1e293b", borderWidth: 1 },
          label: { show: true, color: "#cbd5e1", fontSize: 10 },
          category: "direct", data: imp,
        });
      }
      edges.push({
        source: triggerKey, target: key,
        lineStyle: { color: RISK_COLORS[imp.risk_level] || RISK_COLORS.Unknown, width: 2, curveness: 0.1 },
      });
    });

    impact.indirect_impacts.forEach((imp) => {
      const key = `${imp.citing_law}${imp.citing_article}`;
      const viaKey = imp.via_article || triggerKey;
      if (!nodeSet.has(key)) {
        nodeSet.add(key);
        nodes.push({
          id: key, name: `${imp.citing_law}\n${imp.citing_article}`, symbolSize: 24,
          itemStyle: { color: RISK_COLORS.Potential, borderColor: "#1e293b", borderWidth: 1, opacity: 0.7 },
          label: { show: true, color: "#94a3b8", fontSize: 9 },
          category: "indirect", data: imp,
        });
      }
      edges.push({
        source: viaKey, target: key,
        lineStyle: { color: RISK_COLORS.Potential, width: 1, type: "dashed", curveness: 0.2, opacity: 0.6 },
      });
    });

    const option: echarts.EChartsOption = {
      tooltip: {
        backgroundColor: "rgba(15, 23, 42, 0.95)",
        borderColor: "#1e293b",
        textStyle: { color: "#cbd5e1", fontSize: 12 },
        formatter: (params: any) => {
          if (params.dataType !== "node") return "";
          const d = params.data;
          if (d.category === "trigger") {
            return `
              <div style="font-weight:600;color:#e2e8f0;margin-bottom:4px">震中条文</div>
              <div>${impact.trigger_node}</div>
              ${impact.drift_score != null ? `<div style="margin-top:4px">漂移分数: <span style="color:${(impact.drift_score ?? 0) >= 0.2 ? "#ef4444" : "#f59e0b"};font-weight:600">${(impact.drift_score ?? 0).toFixed(4)}</span></div>` : ""}
              ${impact.effective_status ? `<div>状态: ${impact.effective_status}</div>` : ""}
            `;
          }
          const impData = d.data;
          return `
            <div style="font-weight:600;color:#e2e8f0;margin-bottom:4px">${impData.citing_law}</div>
            <div>${impData.citing_article}</div>
            ${impData.reference_text ? `<div style="margin-top:4px;color:#94a3b8;max-width:240px;white-space:normal">${impData.reference_text.slice(0, 80)}${impData.reference_text.length > 80 ? "..." : ""}</div>` : ""}
            ${impData.keyword ? `<div style="margin-top:4px;color:#6366f1">关键词: ${impData.keyword}</div>` : ""}
          `;
        },
      },
      series: [{
        type: "graph", layout: "force", data: nodes, links: edges,
        roam: true, draggable: true,
        label: { show: true, position: "bottom", distance: 5 },
        force: { repulsion: 400, gravity: 0.05, edgeLength: [80, 180], layoutAnimation: true },
        emphasis: { focus: "adjacency", lineStyle: { width: 3 }, itemStyle: { shadowBlur: 15, shadowColor: "rgba(255,255,255,0.3)" } },
        lineStyle: { color: "source", curveness: 0.1 },
        edgeSymbol: ["none", "arrow"], edgeSymbolSize: [0, 8],
      }],
    };

    chart.setOption(option);
    chart.on("click", (params: any) => {
      if (params.dataType === "node") setSelectedNode(params.data.id);
    });

    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.dispose();
    };
  }, [impact]);

  const selectedItem = (() => {
    if (!selectedNode || !impact) return null;
    if (selectedNode === impact.trigger_node) {
      return { type: "trigger" as const, law_title: impact.trigger_law_title, article_no: impact.trigger_article_no, drift_score: impact.drift_score, effective_status: impact.effective_status };
    }
    const direct = impact.direct_impacts.find((d) => `${d.citing_law}${d.citing_article}` === selectedNode);
    if (direct) return { type: "direct" as const, ...direct };
    const indirect = impact.indirect_impacts.find((d) => `${d.citing_law}${d.citing_article}` === selectedNode);
    if (indirect) return { type: "indirect" as const, ...indirect };
    return null;
  })();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">多米诺效应</h1>
        <p className="mt-1 text-xs text-slate-400">跨法律引用网络分析，追踪条文修订对下游法律的传导影响</p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        {/* 法律名称下拉 */}
        <div className="relative space-y-1">
          <label className="text-[11px] text-slate-500">法律名称</label>
          <button
            onClick={() => setLawDropdownOpen(!lawDropdownOpen)}
            className="flex w-72 items-center justify-between rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:border-slate-600"
          >
            <span className="truncate">{lawTitle || "选择法律..."}</span>
            <ChevronDown className="h-4 w-4 text-slate-500" />
          </button>
          {lawDropdownOpen && (
            <div className="absolute z-50 mt-1 max-h-64 w-72 overflow-auto rounded-md border border-slate-700 bg-slate-900 shadow-xl">
              {laws.map((law) => (
                <button
                  key={law}
                  onClick={() => handleLawSelect(law)}
                  className={`block w-full px-3 py-2 text-left text-xs transition-colors ${lawTitle === law ? "bg-slate-800 text-slate-100" : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"}`}
                >
                  {law}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 条文号下拉 */}
        <div className="relative space-y-1">
          <label className="text-[11px] text-slate-500">条文编号</label>
          {lawLoading ? (
            <div className="flex h-9 w-40 items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 text-sm text-slate-500">
              <div className="h-3 w-3 animate-spin rounded-full border border-slate-600 border-t-slate-300" />
              加载中...
            </div>
          ) : (
            <button
              onClick={() => setArticleDropdownOpen(!articleDropdownOpen)}
              disabled={articles.length === 0}
              className="flex w-40 items-center justify-between rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:border-slate-600 disabled:opacity-50"
            >
              <span className="truncate">{articleNo || "选择条文..."}</span>
              <ChevronDown className="h-4 w-4 text-slate-500" />
            </button>
          )}
          {articleDropdownOpen && articles.length > 0 && (
            <div className="absolute z-50 mt-1 max-h-64 w-40 overflow-auto rounded-md border border-slate-700 bg-slate-900 shadow-xl">
              {articles.map((art) => (
                <button
                  key={art.article_no}
                  onClick={() => handleArticleSelect(art)}
                  className={`block w-full px-3 py-2 text-left text-xs transition-colors ${articleNo === art.article_no ? "bg-slate-800 text-slate-100" : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"}`}
                >
                  {art.article_no}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 最大深度 */}
        <div className="space-y-1">
          <label className="text-[11px] text-slate-500">最大深度</label>
          <input
            type="number" min={1} max={5} value={maxDepth}
            onChange={(e) => setMaxDepth(Number(e.target.value))}
            className="w-20 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-slate-500 focus:outline-none"
          />
        </div>

        {/* 递归追溯 */}
        <button
          onClick={() => setRecursive(!recursive)}
          className="flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-300 hover:border-slate-600"
        >
          {recursive ? <ToggleRight className="h-4 w-4 text-emerald-400" /> : <ToggleLeft className="h-4 w-4 text-slate-600" />}
          递归追溯
        </button>

        {/* 分析按钮 */}
        <button
          onClick={search}
          disabled={loading || !lawTitle || !articleNo}
          className="flex items-center gap-1.5 rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-900 hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Search className="h-4 w-4" />
          {loading ? "分析中..." : "分析影响链"}
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-900/30 bg-red-950/30 px-4 py-3 text-sm text-red-400">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* 条文预览 */}
      {selectedArticle && (
        <div>
          <div className="mb-2 text-[11px] text-slate-500">条文内容预览</div>
          <ArticlePreview article={selectedArticle} lawTitle={lawTitle} />
        </div>
      )}

      {impact && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
          <div className="lg:col-span-3">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-medium text-slate-300">
                引用传导网络
                <span className="ml-2 text-xs text-slate-500">{impact.total_affected_articles} 个受影响条文</span>
              </h2>
              <div className="flex items-center gap-3 text-[11px] text-slate-500">
                <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full bg-red-500" />震中</span>
                <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />直接引用</span>
                <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full bg-indigo-400 opacity-70" />间接传导</span>
              </div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
              <div ref={graphRef} className="h-[600px] w-full" />
            </div>
          </div>

          <div className="space-y-4">
            <h2 className="text-sm font-medium text-slate-300">{selectedNode ? "节点详情" : "影响统计"}</h2>
            {selectedItem ? (
              <div className="space-y-3">
                <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                  <div className="text-[11px] text-slate-500">类型</div>
                  <div className="mt-0.5 text-sm font-medium text-slate-200">
                    {selectedItem.type === "trigger" ? "震中条文" : selectedItem.type === "direct" ? "直接引用" : "间接传导"}
                  </div>
                </div>
                {"citing_law" in selectedItem && (
                  <>
                    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                      <div className="text-[11px] text-slate-500">法律</div>
                      <div className="mt-0.5 text-sm text-slate-200">{selectedItem.citing_law}</div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                      <div className="text-[11px] text-slate-500">条文</div>
                      <div className="mt-0.5 text-sm text-slate-200">{selectedItem.citing_article}</div>
                    </div>
                    {"risk_level" in selectedItem && (
                      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                        <div className="text-[11px] text-slate-500">风险等级</div>
                        <div className="mt-1 text-sm font-medium" style={{ color: RISK_COLORS[selectedItem.risk_level] || RISK_COLORS.Unknown }}>{RISK_LABELS[selectedItem.risk_level] || selectedItem.risk_level}</div>
                      </div>
                    )}
                    {"reference_text" in selectedItem && selectedItem.reference_text && (
                      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                        <div className="text-[11px] text-slate-500">引用内容</div>
                        <div className="mt-1 text-xs leading-relaxed text-slate-400">{selectedItem.reference_text}</div>
                      </div>
                    )}
                  </>
                )}
                {selectedItem.type === "trigger" && (
                  <>
                    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                      <div className="text-[11px] text-slate-500">法律</div>
                      <div className="mt-0.5 text-sm text-slate-200">{selectedItem.law_title}</div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                      <div className="text-[11px] text-slate-500">条文</div>
                      <div className="mt-0.5 text-sm text-slate-200">{selectedItem.article_no}</div>
                    </div>
                    {selectedItem.drift_score !== undefined && (
                      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                        <div className="text-[11px] text-slate-500">漂移分数</div>
                        <div className={`mt-0.5 text-lg font-semibold ${(selectedItem.drift_score ?? 0) >= 0.2 ? "text-red-400" : "text-amber-400"}`}>{(selectedItem.drift_score ?? 0).toFixed(4)}</div>
                      </div>
                    )}
                    {selectedItem.effective_status && (
                      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                        <div className="text-[11px] text-slate-500">生效状态</div>
                        <div className="mt-0.5 text-sm text-slate-200">{selectedItem.effective_status}</div>
                      </div>
                    )}
                  </>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <StatCard label="直接引用" value={impact.direct_impacts.length} color="text-amber-400" />
                <StatCard label="间接传导" value={impact.indirect_impacts.length} color="text-indigo-400" />
                <StatCard label="总计影响" value={impact.total_affected_articles} color="text-slate-200" />
                <div className="mt-4 rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                  <div className="text-[11px] text-slate-500">震中条文</div>
                  <div className="mt-1 text-sm font-medium text-slate-200">{impact.trigger_node}</div>
                  {impact.drift_score !== undefined && (
                    <div className="mt-1 text-xs text-slate-500">
                      漂移: <span className={(impact.drift_score ?? 0) >= 0.2 ? "text-red-400" : "text-amber-400"}>{(impact.drift_score ?? 0).toFixed(4)}</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${color}`}>{value}</div>
    </div>
  );
}
