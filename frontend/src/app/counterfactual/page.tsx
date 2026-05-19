"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchCounterfactual,
  fetchCounterfactualDirections,
  fetchLawList,
  fetchLawArticles,
  type CounterfactualResponse,
  type DirectionInfo,
  type LawArticlesResponse,
} from "@/lib/api";
import {
  AlertCircle,
  FlaskConical,
  Search,
  ToggleLeft,
  ToggleRight,
  ArrowRight,
  ShieldAlert,
  ShieldCheck,
  Shield,
  ChevronDown,
} from "lucide-react";

const RISK_LABELS: Record<string, string> = {
  High: "高风险",
  Medium: "中风险",
  Low: "低风险",
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

export default function CounterfactualPage() {
  const [laws, setLaws] = useState<string[]>([]);
  const [lawTitle, setLawTitle] = useState("");
  const [articleNo, setArticleNo] = useState("");
  const [articles, setArticles] = useState<LawArticlesResponse["articles"]>([]);
  const [selectedArticle, setSelectedArticle] = useState<LawArticlesResponse["articles"][number] | null>(null);
  const [direction, setDirection] = useState("");   // 中文描述，展示用
  const [directionKey, setDirectionKey] = useState(""); // 英文 key，API 用
  const [magnitude, setMagnitude] = useState("");
  const [includeIndirect, setIncludeIndirect] = useState(true);
  const [maxDepth, setMaxDepth] = useState(2);
  const [result, setResult] = useState<CounterfactualResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [lawLoading, setLawLoading] = useState(false);
  const [error, setError] = useState("");
  const [directions, setDirections] = useState<DirectionInfo[]>([]);
  const [showDirections, setShowDirections] = useState(false);
  const [lawDropdownOpen, setLawDropdownOpen] = useState(false);
  const [articleDropdownOpen, setArticleDropdownOpen] = useState(false);

  // 预置演示选项：食品安全法第五十条 + 义务加重方向（40条下游引用，含"应当"义务词，LLM可分析）
  const DEFAULT_LAW = "中华人民共和国食品安全法";
  const DEFAULT_ARTICLE = "第五十条";
  const DEFAULT_DIRECTION_DESC = "义务加重";
  const DEFAULT_DIRECTION_KEY = "obligation_increase";

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

  useEffect(() => {
    Promise.all([fetchLawList(), fetchCounterfactualDirections()])
      .then(([lawList, dirList]) => {
        setLaws(lawList);
        setDirections(dirList);
        // 预选默认法律和条文
        if (lawList.includes(DEFAULT_LAW)) {
          setLawTitle(DEFAULT_LAW);
          setDirection(DEFAULT_DIRECTION_DESC);
          setDirectionKey(DEFAULT_DIRECTION_KEY);
          loadArticles(DEFAULT_LAW, DEFAULT_ARTICLE);
        }
      })
      .catch(() => {});
  }, [loadArticles]);

  const handleLawSelect = (law: string) => {
    setLawTitle(law);
    setLawDropdownOpen(false);
    setResult(null);
    loadArticles(law);
  };

  const handleArticleSelect = (art: LawArticlesResponse["articles"][number]) => {
    setArticleNo(art.article_no);
    setSelectedArticle(art);
    setArticleDropdownOpen(false);
  };

  const analyze = async () => {
    if (!lawTitle || !articleNo || !directionKey) return;
    setLoading(true);
    setError("");
    try {
      const data = await fetchCounterfactual(
        lawTitle, articleNo, directionKey,
        magnitude || undefined, includeIndirect, maxDepth
      );
      setResult(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">反事实模拟</h1>
        <p className="mt-1 text-xs text-slate-400">立法仿真分析：如果某条文向特定方向偏移，会波及哪些下游条文</p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        {/* 法律名称下拉 */}
        <div className="relative space-y-1">
          <label className="text-[11px] text-slate-500">法律名称</label>
          <button
            onClick={() => setLawDropdownOpen(!lawDropdownOpen)}
            className="flex w-full items-center justify-between rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:border-slate-600"
          >
            <span className="truncate">{lawTitle || "选择法律..."}</span>
            <ChevronDown className="h-4 w-4 text-slate-500" />
          </button>
          {lawDropdownOpen && (
            <div className="absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-md border border-slate-700 bg-slate-900 shadow-xl">
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
            <div className="flex h-9 w-full items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 text-sm text-slate-500">
              <div className="h-3 w-3 animate-spin rounded-full border border-slate-600 border-t-slate-300" />
              加载中...
            </div>
          ) : (
            <button
              onClick={() => setArticleDropdownOpen(!articleDropdownOpen)}
              disabled={articles.length === 0}
              className="flex w-full items-center justify-between rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:border-slate-600 disabled:opacity-50"
            >
              <span className="truncate">{articleNo || "选择条文..."}</span>
              <ChevronDown className="h-4 w-4 text-slate-500" />
            </button>
          )}
          {articleDropdownOpen && articles.length > 0 && (
            <div className="absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-md border border-slate-700 bg-slate-900 shadow-xl">
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

        {/* 偏移方向 */}
        <div className="space-y-1 lg:col-span-2">
          <div className="flex items-center justify-between">
            <label className="text-[11px] text-slate-500">偏移方向</label>
            <button
              onClick={() => setShowDirections(!showDirections)}
              className="text-[11px] text-violet-400 hover:text-violet-300"
            >
              {showDirections ? "隐藏" : "查看"}方向列表
            </button>
          </div>
          <input
            type="text" value={direction} onChange={(e) => setDirection(e.target.value)}
            placeholder="例如: 义务加重 / 范围扩大 / 门槛提高"
            className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-violet-500/50 focus:outline-none"
          />
          {showDirections && directions.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {directions.map((d) => (
                <button
                  key={d.key}
                  onClick={() => { setDirection(d.desc); setDirectionKey(d.key); setShowDirections(false); }}
                  className="rounded border border-slate-800 bg-slate-900/50 px-2 py-1 text-[11px] text-slate-400 transition-colors hover:border-violet-500/30 hover:text-violet-300"
                >
                  {d.desc}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 偏移幅度 */}
        <div className="space-y-1">
          <label className="text-[11px] text-slate-500">偏移幅度（可选）</label>
          <select
            value={magnitude} onChange={(e) => setMagnitude(e.target.value)}
            className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-violet-500/50 focus:outline-none"
          >
            <option value="">默认</option>
            <option value="轻微">轻微</option>
            <option value="中等">中等</option>
            <option value="重大">重大</option>
          </select>
        </div>

        {/* 最大深度 */}
        <div className="space-y-1">
          <label className="text-[11px] text-slate-500">最大深度</label>
          <input
            type="number" min={1} max={5} value={maxDepth}
            onChange={(e) => setMaxDepth(Number(e.target.value))}
            className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-violet-500/50 focus:outline-none"
          />
        </div>

        {/* 间接影响开关 */}
        <div className="flex items-end">
          <button
            onClick={() => setIncludeIndirect(!includeIndirect)}
            className="flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-300 hover:border-slate-600"
          >
            {includeIndirect ? <ToggleRight className="h-4 w-4 text-violet-400" /> : <ToggleLeft className="h-4 w-4 text-slate-600" />}
            包含间接影响
          </button>
        </div>

        {/* 运行按钮 */}
        <div className="flex items-end">
          <button
            onClick={analyze}
            disabled={loading || !lawTitle || !articleNo || !directionKey}
            className="flex w-full items-center justify-center gap-1.5 rounded-md bg-violet-500/10 px-4 py-2 text-sm font-medium text-violet-400 transition-colors hover:bg-violet-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <FlaskConical className="h-4 w-4" />
            {loading ? "模拟中..." : "运行模拟"}
          </button>
        </div>
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
          <div className="mb-2 text-[11px] text-slate-500">条文内容预览（选择偏移方向时可参考）</div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-slate-200">{selectedArticle.article_no}</span>
              <StatusBadge status={selectedArticle.status} />
            </div>
            {selectedArticle.effective_start && (
              <div className="text-[11px] text-slate-500 mb-2">
                施行于 {selectedArticle.effective_start}
                {selectedArticle.effective_end && ` → 失效于 ${selectedArticle.effective_end}`}
              </div>
            )}
            <div className="text-xs leading-relaxed text-slate-400">{selectedArticle.text_preview}</div>
          </div>
        </div>
      )}

      {result && (
        <div className="space-y-6">
          {/* Target Info */}
          <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
              <ArrowRight className="h-4 w-4 text-violet-400" />
              模拟目标
            </div>
            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <div className="text-[11px] text-slate-500">条文</div>
                <div className="mt-0.5 text-sm text-slate-200">《{result.target_law}》{result.target_article}</div>
              </div>
              {result.target_text && (
                <div>
                  <div className="text-[11px] text-slate-500">原文</div>
                  <div className="mt-0.5 text-sm leading-relaxed text-slate-400">{result.target_text}</div>
                </div>
              )}
              <div>
                <div className="text-[11px] text-slate-500">原始方向</div>
                <div className="mt-0.5 text-sm text-slate-300">{result.original_direction}</div>
              </div>
              <div>
                <div className="text-[11px] text-slate-500">解读方向</div>
                <div className="mt-0.5 text-sm text-violet-300">{result.interpreted_direction}</div>
              </div>
            </div>
            {result.affected_categories.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1">
                {result.affected_categories.map((cat) => (
                  <span key={cat} className="rounded bg-violet-500/10 px-2 py-0.5 text-[11px] text-violet-400">{cat}</span>
                ))}
              </div>
            )}
          </div>

          {/* LLM Summary */}
          {result.llm_summary && (
            <div className="rounded-lg border border-violet-500/10 bg-violet-950/10 p-4">
              <div className="text-[11px] font-medium text-violet-400">LLM 分析摘要</div>
              <div className="mt-2 text-sm leading-relaxed text-slate-300">{result.llm_summary}</div>
            </div>
          )}

          {/* Impacts */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-medium text-slate-300">直接影响</h2>
                <span className="rounded bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-400">{result.direct_impacts.length} 条</span>
              </div>
              {result.direct_impacts.length === 0 ? (
                <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-4 text-center text-xs text-slate-500">无直接影响</div>
              ) : (
                <div className="space-y-2">
                  {result.direct_impacts.map((imp, i) => <ImpactCard key={`d-${i}`} impact={imp} />)}
                </div>
              )}
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-medium text-slate-300">间接传导</h2>
                <span className="rounded bg-indigo-500/10 px-2 py-0.5 text-[11px] text-indigo-400">{result.indirect_impacts.length} 条</span>
              </div>
              {result.indirect_impacts.length === 0 ? (
                <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-4 text-center text-xs text-slate-500">无间接传导</div>
              ) : (
                <div className="space-y-2">
                  {result.indirect_impacts.map((imp, i) => <ImpactCard key={`id-${i}`} impact={imp} />)}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ImpactCard({ impact }: { impact: { law_title: string; article_no: string; risk_level: string; llm_reasoning: string } }) {
  const riskColor: Record<string, string> = {
    High: "text-red-400", Medium: "text-amber-400", Low: "text-emerald-400", Unknown: "text-slate-400",
  };
  const RiskIcon = impact.risk_level === "High" ? ShieldAlert : impact.risk_level === "Low" ? ShieldCheck : Shield;
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3 transition-colors hover:border-slate-700">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-200">《{impact.law_title}》{impact.article_no}</span>
            <span className="flex items-center gap-1 rounded bg-slate-800 px-1.5 py-0.5 text-[11px]">
              <RiskIcon className={`h-3.5 w-3.5 ${riskColor[impact.risk_level] || "text-slate-400"}`} />
              <span className={riskColor[impact.risk_level] || "text-slate-400"}>{RISK_LABELS[impact.risk_level] || impact.risk_level}</span>
            </span>
          </div>
        </div>
      </div>
      {impact.llm_reasoning && (
        <div className="mt-2 border-t border-slate-800 pt-2 text-xs leading-relaxed text-slate-400">{impact.llm_reasoning}</div>
      )}
    </div>
  );
}
