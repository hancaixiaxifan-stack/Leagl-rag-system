"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import * as echarts from "echarts";
import {
  fetchDriftReport,
  fetchLawList,
  getErrorMessage,
  type DriftReport,
  type HighDriftDetail,
  type ChapterData,
} from "@/lib/api";
import {
  AlertCircle,
  ArrowDownRight,
  ArrowRight,
  ChevronDown,
  FileText,
  Search,
} from "lucide-react";

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
    <div className="legal-card p-4">
      <div className="text-xs font-medium tracking-wide text-[#7c735f]">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${color}`}>{value}</div>
      {sub && <div className="mt-1 text-[11px] text-[#8a7f6c]">{sub}</div>}
    </div>
  );
}

function DriftBadge({ score }: { score?: number }) {
  if (score === undefined) return <span className="text-[#9a907d]">—</span>;
  if (score >= 0.3)
    return (
      <span className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-700">
        重大修订
      </span>
    );
  if (score >= 0.1)
    return (
      <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">
        实质性修订
      </span>
    );
  return (
    <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
      微调
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    Relocated: "border-sky-200 bg-sky-50 text-sky-700",
    Reassigned: "border-indigo-200 bg-indigo-50 text-indigo-700",
    Modified: "border-amber-200 bg-amber-50 text-amber-700",
  };
  const cls = map[status] || "border-[#d8d0c1] bg-[#f7f3eb] text-[#6f6658]";
  const labels: Record<string, string> = {
    Relocated: "迁址",
    Reassigned: "重分配",
    Modified: "修改",
  };
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {labels[status] || status}
    </span>
  );
}

function driftColor(avgDrift: number): string {
  if (avgDrift >= 0.2) return "#b42318";
  if (avgDrift >= 0.1) return "#b45309";
  if (avgDrift >= 0.05) return "#a16207";
  return "#047857";
}

function getHeatmapData(params: unknown): [number, number, number] | null {
  if (
    typeof params === "object" &&
    params !== null &&
    "data" in params &&
    Array.isArray((params as { data?: unknown }).data)
  ) {
    const data = (params as { data: unknown[] }).data;
    if (
      data.length >= 3 &&
      typeof data[0] === "number" &&
      typeof data[1] === "number" &&
      typeof data[2] === "number"
    ) {
      return [data[0], data[1], data[2]];
    }
  }
  return null;
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
    } catch (e: unknown) {
      setError(getErrorMessage(e));
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
        backgroundColor: "rgba(255, 254, 250, 0.98)",
        borderColor: "#d8d0c1",
        extraCssText: "box-shadow: 0 12px 30px rgba(31, 41, 51, 0.12); border-radius: 8px;",
        textStyle: { color: "#1f2933", fontSize: 12 },
        formatter: (params: unknown) => {
          const heatmapData = getHeatmapData(params);
          if (!heatmapData) return "";
          const ch = chapters[heatmapData[1]];
          return `
            <div style="font-weight:600;margin-bottom:4px">${ch.chapter_label}</div>
            <div>平均漂移: <span style="color:${driftColor(ch.avg_drift)};font-weight:600">${ch.avg_drift.toFixed(4)}</span></div>
            <div>重大修订: ${ch.major_revision_count} 条</div>
            <div>迁址: ${ch.relocated_count} 条</div>
            <div>重分配: ${ch.reassigned_count} 条</div>
          `;
        },
      },
      grid: { left: "14%", right: "6%", top: "6%", bottom: "8%" },
      xAxis: {
        type: "category",
        data: xData,
        axisLine: { lineStyle: { color: "#d8d0c1" } },
        axisTick: { show: false },
        axisLabel: { color: "#7c735f", fontSize: 11 },
        splitArea: { show: false },
      },
      yAxis: {
        type: "category",
        data: yData,
        axisLine: { lineStyle: { color: "#d8d0c1" } },
        axisTick: { show: false },
        axisLabel: { color: "#6f6658", fontSize: 11 },
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
          color: ["#a7d8bd", "#e8d27b", "#d49b50", "#c65f4d"],
        },
      },
      series: [
        {
          type: "heatmap",
          data,
          label: {
            show: true,
            formatter: (p: unknown) => getHeatmapData(p)?.[2].toFixed(3) ?? "",
            color: "#1f2933",
            fontSize: 11,
            fontWeight: "bold",
          },
          itemStyle: {
            borderColor: "#fffefa",
            borderWidth: 2,
            borderRadius: 4,
          },
          emphasis: {
            itemStyle: {
              borderColor: "#1f3a5f",
              shadowBlur: 12,
              shadowColor: "rgba(31,58,95,0.22)",
            },
          },
        },
      ],
    };

    chart.setOption(option);

    chart.on("click", (params: unknown) => {
      const heatmapData = getHeatmapData(params);
      if (!heatmapData) return;
      const ch = chapters[heatmapData[1]];
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
      <section className="legal-card relative z-20 overflow-visible">
        <div className="legal-rule h-1" />
        <div className="grid gap-6 p-6 lg:grid-cols-[1fr_360px]">
          <div>
            <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-[#8a7f6c]">
              <FileText className="h-3.5 w-3.5" />
              版本体检报告
            </div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[#1f2933]">
              法律漂移分析
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-[#6f6658]">
              可视化展示法律条文在不同版本间的语义漂移量。选择法律后生成报告，点击章节热力图可钻取高漂移条文。
            </p>
          </div>

          <div className="relative">
            <label className="mb-2 block text-xs font-medium text-[#7c735f]">选择法律</label>
            <button
              onClick={() => setLawDropdownOpen(!lawDropdownOpen)}
              data-open={lawDropdownOpen}
              className="legal-input flex w-full items-center justify-between px-3 py-2.5 text-left text-[#1f2933]"
            >
              <span className="flex min-w-0 items-center gap-2">
                <Search className="h-4 w-4 shrink-0 text-[#8a7f6c]" />
                <span className="truncate">{selectedLaw || "选择法律..."}</span>
              </span>
              <ChevronDown className="h-4 w-4 shrink-0 text-[#8a7f6c]" />
            </button>
            {lawDropdownOpen && (
              <div className="absolute z-50 mt-2 max-h-72 w-full overflow-auto rounded-md border border-[#d8d0c1] bg-[#fffefa] py-1 shadow-xl">
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
                        ? "bg-[#1f3a5f] text-[#fffefa]"
                        : "text-[#5f574a] hover:bg-[#f3eee5] hover:text-[#1f2933]"
                    }`}
                  >
                    {law}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {loading && (
        <div className="legal-card flex items-center gap-3 px-4 py-4 text-sm text-[#6f6658]">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#d8d0c1] border-t-[#1f3a5f]" />
          正在生成版本体检报告...
        </div>
      )}

      {!report && !loading && (
        <div className="legal-card p-8 text-center">
          <p className="text-sm font-medium text-[#1f2933]">请选择一部法律开始分析</p>
          <p className="mt-2 text-xs text-[#7c735f]">
            当前页面会展示平均漂移、章节热力图和高漂移条文详情。
          </p>
        </div>
      )}

      {report && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <SummaryCard
              label="平均漂移"
              value={report.summary.avg_drift.toFixed(4)}
              color={report.summary.avg_drift >= 0.1 ? "text-[#b45309]" : "text-[#047857]"}
            />
            <SummaryCard
              label="逻辑漂移"
              value={report.summary.avg_law_logic_drift.toFixed(4)}
              color="text-[#1f2933]"
            />
            <SummaryCard
              label="重大变更"
              value={report.summary.major_changes_count}
              color="text-[#b42318]"
            />
            <SummaryCard
              label="迁址条文"
              value={report.summary.relocated_count}
              color="text-[#0369a1]"
            />
            <SummaryCard
              label="重分配"
              value={report.summary.reassigned_count}
              color="text-[#4338ca]"
            />
            <SummaryCard
              label="版本数"
              value={report.summary.version_count}
              sub={`${report.summary.total_chunks} 个 chunk`}
              color="text-[#1f2933]"
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
            <section className="legal-card p-5">
              <div className="mb-4 flex items-start justify-between gap-4 border-b border-[#e4ded3] pb-4">
                <div>
                  <h2 className="text-base font-semibold text-[#1f2933]">章节热力图</h2>
                  <p className="mt-1 text-xs text-[#7c735f]">
                    {selectedChapter
                      ? `已筛选：${selectedChapter.chapter_label}`
                      : "点击热力图章节查看对应条文详情"}
                  </p>
                </div>
                {selectedChapter && (
                  <button
                    onClick={() => setSelectedChapter(null)}
                    className="text-xs font-medium text-[#1f3a5f] hover:text-[#162c49]"
                  >
                    清除筛选
                  </button>
                )}
              </div>
              <div ref={heatmapRef} className="h-[500px] w-full" />
              <div className="mt-4 flex flex-wrap items-center justify-center gap-3 border-t border-[#e4ded3] pt-3 text-[11px] text-[#7c735f]">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#a7d8bd]" />
                  稳定 (&lt;0.05)
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#e8d27b]" />
                  微调 (0.05-0.1)
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#d49b50]" />
                  修改 (0.1-0.2)
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#c65f4d]" />
                  重大修订 (&gt;0.2)
                </span>
              </div>
            </section>

            <aside className="space-y-4">
              <section className="legal-card p-4">
                <h2 className="text-base font-semibold text-[#1f2933]">漂移类型说明</h2>
                <div className="mt-3 space-y-2 text-xs leading-5 text-[#6f6658]">
                  <p>
                    <span className="font-medium text-[#b42318]">重大修订</span>
                    ：语义漂移分数较高，条文内容发生明显变化。
                  </p>
                  <p>
                    <span className="font-medium text-[#0369a1]">迁址</span>
                    ：条文编号变化，但内容保持较高相似度。
                  </p>
                  <p>
                    <span className="font-medium text-[#4338ca]">重分配</span>
                    ：同一条文号下内容发生实质替换。
                  </p>
                  <p>
                    <span className="font-medium text-[#b45309]">修改</span>
                    ：条文存在一般性内容修订。
                  </p>
                </div>
              </section>

              <section className="legal-card p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-base font-semibold text-[#1f2933]">高漂移条文</h2>
                    {filteredDetails.length > 0 && (
                      <p className="mt-1 text-xs text-[#7c735f]">{filteredDetails.length} 条</p>
                    )}
                  </div>
                </div>
                <div className="max-h-[460px] space-y-2 overflow-auto pr-1">
                  {filteredDetails.length === 0 ? (
                    <div className="rounded-md border border-[#e4ded3] bg-[#f8f6f1] p-4 text-center text-xs text-[#7c735f]">
                      {selectedChapter ? "该章节无高漂移条文" : "暂无数据"}
                    </div>
                  ) : (
                    filteredDetails.map((d, i) => <DriftDetailCard key={i} detail={d} />)
                  )}
                </div>
              </section>
            </aside>
          </div>
        </div>
      )}
    </div>
  );
}

function DriftDetailCard({ detail }: { detail: HighDriftDetail }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-md border border-[#e4ded3] bg-[#fffefa] p-3 transition-[border-color,box-shadow,transform] duration-200 hover:border-[#cfc5b5] hover:shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-[#1f2933]">{detail.article_no}</span>
            <StatusBadge status={detail.status} />
            <DriftBadge score={detail.drift_score} />
          </div>
          {detail.similarity !== undefined && (
            <div className="mt-1 text-[11px] text-[#8a7f6c]">
              相似度: {(detail.similarity * 100).toFixed(1)}%
            </div>
          )}
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="group shrink-0 rounded-full border border-[#d8d0c1] p-1 text-[#7c735f] transition-colors hover:border-[#1f3a5f] hover:text-[#1f3a5f]"
          aria-label={expanded ? "收起条文详情" : "展开条文详情"}
        >
          {expanded ? (
            <ArrowDownRight className="h-3.5 w-3.5" />
          ) : (
            <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
          )}
        </button>
      </div>
      {expanded && detail.text_preview && (
        <div className="mt-3 border-t border-[#e4ded3] pt-3 text-xs leading-relaxed text-[#5f574a]">
          {detail.text_preview}
          {detail.old_content_trace && (
            <div className="mt-2 text-[11px] text-[#8a7f6c]">源自: {detail.old_content_trace}</div>
          )}
        </div>
      )}
    </div>
  );
}
