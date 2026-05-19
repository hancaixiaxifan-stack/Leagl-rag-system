"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import * as echarts from "echarts";
import {
  fetchDriftReport,
  fetchLawList,
  type DriftReport,
  type HighDriftDetail,
  type ChapterData,
} from "@/lib/api";
import { AlertCircle, ChevronDown, ArrowUpRight, ArrowDownRight } from "lucide-react";

function SummaryCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color: string;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-1 text-xl font-semibold ${color}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-slate-500">{sub}</div>}
    </div>
  );
}

function DriftBadge({ score }: { score?: number }) {
  if (score === undefined) return <span className="text-slate-500">—</span>;
  if (score >= 0.3)
    return (
      <span className="rounded bg-red-500/20 px-1.5 py-0.5 text-[11px] font-medium text-red-400">
        重大修订
      </span>
    );
  if (score >= 0.1)
    return (
      <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[11px] font-medium text-amber-400">
        实质性修订
      </span>
    );
  return (
    <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[11px] font-medium text-emerald-400">
      微调
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    Relocated: "bg-sky-500/20 text-sky-400",
    Reassigned: "bg-violet-500/20 text-violet-400",
    Modified: "bg-amber-500/20 text-amber-400",
  };
  const cls = map[status] || "bg-slate-500/20 text-slate-400";
  const labels: Record<string, string> = {
    Relocated: "迁址",
    Reassigned: "重分配",
    Modified: "修改",
  };
  return (
    <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>
      {labels[status] || status}
    </span>
  );
}

function driftColor(avgDrift: number): string {
  if (avgDrift >= 0.2) return "#ef4444";
  if (avgDrift >= 0.1) return "#f59e0b";
  if (avgDrift >= 0.05) return "#eab308";
  return "#10b981";
}

export default function DriftPage() {
  const [laws, setLaws] = useState<string[]>([]);
  const [selectedLaw, setSelectedLaw] = useState<string>("");
  const [report, setReport] = useState<DriftReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [selectedChapter, setSelectedChapter] = useState<ChapterData | null>(null);
  const [lawDropdownOpen, setLawDropdownOpen] = useState(false);

  const heatmapRef = useRef<HTMLDivElement>(null);
  const heatmapChart = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    fetchLawList()
      .then(setLaws)
      .catch((e) => setError(e.message));
  }, []);

  const loadReport = useCallback(async (lawTitle: string) => {
    if (!lawTitle) return;
    setLoading(true);
    setError("");
    setSelectedChapter(null);
    try {
      const data = await fetchDriftReport(lawTitle);
      setReport(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!report || !heatmapRef.current) return;

    if (heatmapChart.current) {
      heatmapChart.current.dispose();
    }

    const chart = echarts.init(heatmapRef.current, undefined, { renderer: "canvas" });
    heatmapChart.current = chart;

    const chapters = report.chapters;
    const yData = chapters.map((c) => c.chapter_label);
    const xData = ["平均漂移"];
    const data = chapters.map((c, i) => [0, i, c.avg_drift]);

    const option: echarts.EChartsOption = {
      tooltip: {
        position: "top",
        backgroundColor: "rgba(15, 23, 42, 0.95)",
        borderColor: "#1e293b",
        textStyle: { color: "#cbd5e1", fontSize: 12 },
        formatter: (params: any) => {
          const ch = chapters[params.data[1]];
          return `
            <div style="font-weight:600;margin-bottom:4px">${ch.chapter_label}</div>
            <div>平均漂移: <span style="color:${driftColor(ch.avg_drift)};font-weight:600">${ch.avg_drift.toFixed(4)}</span></div>
            <div>重大修订: ${ch.major_revision_count} 条</div>
            <div>迁址: ${ch.relocated_count} 条</div>
            <div>重分配: ${ch.reassigned_count} 条</div>
          `;
        },
      },
      grid: { left: "12%", right: "5%", top: "5%", bottom: "5%" },
      xAxis: {
        type: "category",
        data: xData,
        axisLine: { lineStyle: { color: "#334155" } },
        axisLabel: { color: "#94a3b8", fontSize: 11 },
        splitArea: { show: false },
      },
      yAxis: {
        type: "category",
        data: yData,
        axisLine: { lineStyle: { color: "#334155" } },
        axisLabel: { color: "#94a3b8", fontSize: 11 },
        splitArea: { show: false },
      },
      visualMap: {
        min: 0,
        max: 0.5,
        calculable: true,
        orient: "horizontal",
        left: "center",
        bottom: -5,
        show: false,
        inRange: {
          color: ["#10b981", "#eab308", "#f59e0b", "#ef4444"],
        },
      },
      series: [
        {
          type: "heatmap",
          data,
          label: {
            show: true,
            formatter: (p: any) => p.data[2].toFixed(3),
            color: "#e2e8f0",
            fontSize: 11,
            fontWeight: "bold",
          },
          itemStyle: {
            borderColor: "#0f172a",
            borderWidth: 2,
            borderRadius: 4,
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowColor: "rgba(255,255,255,0.2)",
            },
          },
        },
      ],
    };

    chart.setOption(option);

    chart.on("click", (params: any) => {
      const ch = chapters[params.data[1]];
      setSelectedChapter(ch);
    });

    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.dispose();
    };
  }, [report]);

  const filteredDetails = (() => {
    if (!report) return [];
    if (!selectedChapter) return report.high_drift_details;
    const [lo, hi] = selectedChapter.article_range.split("-").map(Number);
    return report.high_drift_details.filter((d) => {
      const match = d.article_no.match(/第(\d+)条/);
      if (!match) return false;
      const n = parseInt(match[1]);
      return n >= lo && n <= hi;
    });
  })();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">法律漂移分析</h1>
          <p className="mt-1 text-xs text-slate-400">
            可视化展示法律条文在不同版本间的语义漂移量，点击热力图章节可钻取详情
          </p>
        </div>
      </div>

      <div className="relative w-72">
        <button
          onClick={() => setLawDropdownOpen(!lawDropdownOpen)}
          className="flex w-full items-center justify-between rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:border-slate-600"
        >
          <span className="truncate">{selectedLaw || "选择法律..."}</span>
          <ChevronDown className="h-4 w-4 text-slate-500" />
        </button>
        {lawDropdownOpen && (
          <div className="absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-md border border-slate-700 bg-slate-900 shadow-xl">
            {laws.map((law) => (
              <button
                key={law}
                onClick={() => {
                  setSelectedLaw(law);
                  setLawDropdownOpen(false);
                  loadReport(law);
                }}
                className={`block w-full px-3 py-2 text-left text-xs transition-colors ${
                  selectedLaw === law
                    ? "bg-slate-800 text-slate-100"
                    : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                }`}
              >
                {law}
              </button>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-900/30 bg-red-950/30 px-4 py-3 text-sm text-red-400">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 py-8 text-sm text-slate-500">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-slate-300" />
          加载中...
        </div>
      )}

      {report && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
            <SummaryCard
              label="平均漂移"
              value={report.summary.avg_drift.toFixed(4)}
              color={report.summary.avg_drift >= 0.1 ? "text-amber-400" : "text-emerald-400"}
            />
            <SummaryCard
              label="逻辑漂移"
              value={report.summary.avg_law_logic_drift.toFixed(4)}
              color="text-slate-200"
            />
            <SummaryCard
              label="重大变更"
              value={report.summary.major_changes_count}
              color="text-red-400"
            />
            <SummaryCard
              label="迁址条文"
              value={report.summary.relocated_count}
              color="text-sky-400"
            />
            <SummaryCard
              label="重分配"
              value={report.summary.reassigned_count}
              color="text-violet-400"
            />
            <SummaryCard
              label="版本数"
              value={report.summary.version_count}
              sub={`${report.summary.total_chunks} 个 chunk`}
              color="text-slate-200"
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="text-sm font-medium text-slate-300">
                  章节热力图
                  {selectedChapter && (
                    <span className="ml-2 text-xs text-slate-500">
                      已选择: {selectedChapter.chapter_label}
                    </span>
                  )}
                </h2>
                {selectedChapter && (
                  <button
                    onClick={() => setSelectedChapter(null)}
                    className="text-xs text-slate-500 hover:text-slate-300"
                  >
                    清除筛选
                  </button>
                )}
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
                <div ref={heatmapRef} className="h-[500px] w-full" />
                <div className="mt-3 flex items-center justify-center gap-4 text-[11px] text-slate-500">
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2.5 w-2.5 rounded-sm bg-emerald-500" />
                    稳定 (&lt;0.05)
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2.5 w-2.5 rounded-sm bg-yellow-500" />
                    微调 (0.05-0.1)
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-500" />
                    修订 (0.1-0.2)
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2.5 w-2.5 rounded-sm bg-red-500" />
                    重大修订 (&gt;0.2)
                  </span>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <h2 className="text-sm font-medium text-slate-300">
                高漂移详情
                {filteredDetails.length > 0 && (
                  <span className="ml-2 text-xs text-slate-500">({filteredDetails.length} 条)</span>
                )}
              </h2>
              <div className="max-h-[540px] space-y-2 overflow-auto pr-1">
                {filteredDetails.length === 0 ? (
                  <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-4 text-center text-xs text-slate-500">
                    {selectedChapter ? "该章节无高漂移条文" : "暂无数据"}
                  </div>
                ) : (
                  filteredDetails.map((d, i) => <DriftDetailCard key={i} detail={d} />)
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DriftDetailCard({ detail }: { detail: HighDriftDetail }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3 transition-colors hover:border-slate-700">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-200">{detail.article_no}</span>
            <StatusBadge status={detail.status} />
            <DriftBadge score={detail.drift_score} />
          </div>
          {detail.similarity !== undefined && (
            <div className="mt-1 text-[11px] text-slate-500">
              相似度: {(detail.similarity * 100).toFixed(1)}%
            </div>
          )}
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="shrink-0 text-slate-500 hover:text-slate-300"
        >
          {expanded ? (
            <ArrowDownRight className="h-4 w-4" />
          ) : (
            <ArrowUpRight className="h-4 w-4" />
          )}
        </button>
      </div>
      {expanded && detail.text_preview && (
        <div className="mt-2 border-t border-slate-800 pt-2 text-xs leading-relaxed text-slate-400">
          {detail.text_preview}
          {detail.old_content_trace && (
            <div className="mt-1.5 text-[11px] text-slate-500">源自: {detail.old_content_trace}</div>
          )}
        </div>
      )}
    </div>
  );
}
