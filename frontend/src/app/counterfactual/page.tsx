"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchCounterfactual,
  fetchCounterfactualDirections,
  fetchLawArticles,
  fetchLawList,
  getErrorMessage,
  type CounterfactualImpactItem,
  type CounterfactualResponse,
  type DirectionInfo,
  type LawArticlesResponse,
} from "@/lib/api";
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  ChevronDown,
  FlaskConical,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";

const RISK_LABELS: Record<string, string> = {
  High: "高风险",
  Medium: "中风险",
  Low: "低风险",
  Potential: "潜在影响",
  Unknown: "未知",
};

const CATEGORY_LABELS: Record<string, string> = {
  obligation: "义务",
  scope: "适用范围",
  threshold: "门槛标准",
  right: "权利",
  procedure: "程序",
  negation: "禁止性规则",
  permission: "授权许可",
  sanction: "责任后果",
  condition: "适用条件",
  time: "期限",
  amount: "数量金额",
};

const DIRECTION_LABELS: Record<string, string> = {
  obligation_increase: "义务加重",
  obligation_decrease: "义务减轻",
  scope_expand: "范围扩大",
  scope_narrow: "范围缩小",
  threshold_raise: "门槛提高",
  threshold_lower: "门槛降低",
  right_strengthen: "权利强化",
  right_weaken: "权利弱化",
  procedure_tighten: "程序收紧",
  procedure_loosen: "程序放宽",
  protection_shift: "保护重心转移",
};

const STRUCTURED_FIELD_LABELS: Record<string, string> = {
  article_key: "条文",
  law_title: "法律",
  article_no: "条文",
  risk_level: "风险等级",
  reasoning: "传导逻辑",
  llm_reasoning: "传导逻辑",
  impact_reasoning: "传导逻辑",
  impact_type: "影响类型",
  affected_category: "影响类别",
  affected_categories: "影响类别",
  confidence: "置信度",
  path: "传导路径",
  directness: "传导类型",
};

const DEFAULT_LAW = "中华人民共和国食品安全法";
const DEFAULT_ARTICLE = "第五十条";
const DEFAULT_DIRECTION_DESC = "义务加重";
const DEFAULT_DIRECTION_KEY = "obligation_increase";

type LawArticle = LawArticlesResponse["articles"][number];

export default function CounterfactualPage() {
  const [laws, setLaws] = useState<string[]>([]);
  const [lawTitle, setLawTitle] = useState("");
  const [articleNo, setArticleNo] = useState("");
  const [articles, setArticles] = useState<LawArticle[]>([]);
  const [selectedArticle, setSelectedArticle] = useState<LawArticle | null>(null);
  const [direction, setDirection] = useState("");
  const [directionKey, setDirectionKey] = useState("");
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

  const selectedDirection = useMemo(
    () => directions.find((item) => item.key === directionKey),
    [directionKey, directions]
  );
  const quickDirections = directions.slice(0, 6);
  const canAnalyze = Boolean(lawTitle && articleNo && directionKey && !loading);

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
          ? data.articles.find((item) => item.article_no === preselectArticle) ?? data.articles[0]
          : data.articles[0];
        setArticleNo(target.article_no);
        setSelectedArticle(target);
      }
    } catch {
      setArticles([]);
    } finally {
      setLawLoading(false);
    }
  }, []);

  useEffect(() => {
    Promise.all([fetchLawList(), fetchCounterfactualDirections()])
      .then(([lawList, directionList]) => {
        setLaws(lawList);
        setDirections(directionList);
        setDirection(DEFAULT_DIRECTION_DESC);
        setDirectionKey(DEFAULT_DIRECTION_KEY);
        if (lawList.includes(DEFAULT_LAW)) {
          setLawTitle(DEFAULT_LAW);
          loadArticles(DEFAULT_LAW, DEFAULT_ARTICLE);
        }
      })
      .catch(() => {
        setError("初始化反事实模拟配置失败，请确认后端服务已启动。");
      });
  }, [loadArticles]);

  const handleLawSelect = (law: string) => {
    setLawTitle(law);
    setLawDropdownOpen(false);
    setResult(null);
    loadArticles(law);
  };

  const handleArticleSelect = (article: LawArticle) => {
    setArticleNo(article.article_no);
    setSelectedArticle(article);
    setArticleDropdownOpen(false);
    setResult(null);
  };

  const handleDirectionSelect = (item: DirectionInfo) => {
    setDirection(item.desc);
    setDirectionKey(item.key);
    setShowDirections(false);
  };

  const handleDirectionInput = (value: string) => {
    setDirection(value);
    const matched = directions.find((item) => item.desc === value || item.key === value);
    setDirectionKey(matched?.key ?? "");
  };

  const analyze = async () => {
    if (!canAnalyze) return;
    setLoading(true);
    setError("");
    try {
      const data = await fetchCounterfactual(
        lawTitle,
        articleNo,
        directionKey,
        magnitude || undefined,
        includeIndirect,
        maxDepth
      );
      setResult(data);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <section className="legal-card flex shrink-0 items-center justify-between gap-3 px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-[#1f3a5f] text-[#fffefa]">
            <FlaskConical className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-[#8a7f6c]">
              COUNTERFACTUAL LAB
            </div>
            <h1 className="truncate text-base font-semibold tracking-tight text-[#1f2933]">
              反事实模拟
            </h1>
          </div>
        </div>
        <div className="hidden min-w-0 max-w-[56%] truncate text-xs text-[#7c735f] lg:block">
          {lawTitle || "未选择法律"} · {articleNo || "未选择条文"} · {direction || "未选择方向"}
        </div>
      </section>

      <section className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[390px_minmax(0,1fr)]">
        <aside className="legal-card relative z-20 flex min-h-0 flex-col overflow-visible">
          <div className="border-b border-[#e4ded3] px-4 py-3">
            <h2 className="text-sm font-semibold text-[#1f2933]">模拟条件</h2>
            <p className="mt-1 text-xs leading-5 text-[#7c735f]">
              选择目标条文和偏移方向，系统会沿引用关系评估下游影响。
            </p>
          </div>

          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-visible p-4">
            <FieldGroup label="法律名称">
              <DropdownButton
                open={lawDropdownOpen}
                disabled={laws.length === 0}
                onClick={() => {
                  setLawDropdownOpen((value) => !value);
                  setArticleDropdownOpen(false);
                }}
                icon={<Search className="h-4 w-4 shrink-0 text-[#8a7f6c]" />}
                text={lawTitle || "选择法律..."}
              />
              {lawDropdownOpen && (
                <DropdownPanel>
                  {laws.map((law) => (
                    <DropdownItem
                      key={law}
                      active={lawTitle === law}
                      label={law}
                      onClick={() => handleLawSelect(law)}
                    />
                  ))}
                </DropdownPanel>
              )}
            </FieldGroup>

            <FieldGroup label="条文编号">
              {lawLoading ? (
                <div className="legal-input flex h-[42px] w-full items-center gap-2 px-3 text-sm text-[#7c735f]">
                  <div className="h-3 w-3 animate-spin rounded-full border border-[#d8d0c1] border-t-[#1f3a5f]" />
                  正在加载条文...
                </div>
              ) : (
                <DropdownButton
                  open={articleDropdownOpen}
                  disabled={articles.length === 0}
                  onClick={() => {
                    setArticleDropdownOpen((value) => !value);
                    setLawDropdownOpen(false);
                  }}
                  text={articleNo || "选择条文..."}
                />
              )}
              {articleDropdownOpen && articles.length > 0 && (
                <DropdownPanel>
                  {articles.map((article) => (
                    <DropdownItem
                      key={article.article_no}
                      active={articleNo === article.article_no}
                      label={article.article_no}
                      onClick={() => handleArticleSelect(article)}
                    />
                  ))}
                </DropdownPanel>
              )}
            </FieldGroup>

            <FieldGroup label="偏移方向">
              <div className="relative">
                <input
                  type="text"
                  value={direction}
                  onChange={(event) => handleDirectionInput(event.target.value)}
                  placeholder="请选择注册表内的模拟方向"
                  className="legal-input w-full px-3 py-2.5 text-[#1f2933] placeholder:text-[#a09684]"
                />
                {!directionKey && direction && (
                  <div className="mt-1 text-[11px] text-amber-700">请选择下方方向标签后运行。</div>
                )}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {quickDirections.map((item) => (
                  <DirectionChip
                    key={item.key}
                    active={item.key === directionKey}
                    label={item.desc}
                    onClick={() => handleDirectionSelect(item)}
                  />
                ))}
                {directions.length > quickDirections.length && (
                  <button
                    type="button"
                    onClick={() => setShowDirections((value) => !value)}
                    className="rounded-full border border-[#d8d0c1] bg-[#fffefa] px-2.5 py-1 text-[11px] text-[#5f574a] hover:border-[#1f3a5f] hover:text-[#1f3a5f]"
                  >
                    {showDirections ? "收起" : "更多方向"}
                  </button>
                )}
              </div>
              {showDirections && (
                <div className="mt-2 max-h-28 overflow-auto rounded-md border border-[#e4ded3] bg-[#f8f6f1] p-2">
                  <div className="flex flex-wrap gap-1.5">
                    {directions.slice(quickDirections.length).map((item) => (
                      <DirectionChip
                        key={item.key}
                        active={item.key === directionKey}
                        label={item.desc}
                        onClick={() => handleDirectionSelect(item)}
                      />
                    ))}
                  </div>
                </div>
              )}
            </FieldGroup>

            <div className="grid grid-cols-2 gap-3">
              <FieldGroup label="偏移幅度">
                <select
                  value={magnitude}
                  onChange={(event) => setMagnitude(event.target.value)}
                  className="legal-input w-full px-3 py-2.5 text-[#1f2933]"
                >
                  <option value="">默认</option>
                  <option value="轻微">轻微</option>
                  <option value="中等">中等</option>
                  <option value="重大">重大</option>
                </select>
              </FieldGroup>
              <FieldGroup label="最大深度">
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={maxDepth}
                  onChange={(event) => setMaxDepth(Number(event.target.value))}
                  className="legal-input w-full px-3 py-2.5 text-[#1f2933]"
                />
              </FieldGroup>
            </div>

            <button
              type="button"
              onClick={() => setIncludeIndirect((value) => !value)}
              className="legal-input flex h-[42px] w-full items-center justify-center gap-2 px-3 text-sm font-medium text-[#1f2933]"
            >
              {includeIndirect ? (
                <ToggleRight className="h-4 w-4 text-[#1f3a5f]" />
              ) : (
                <ToggleLeft className="h-4 w-4 text-[#9a907d]" />
              )}
              {includeIndirect ? "包含间接影响" : "仅直接影响"}
            </button>

            {selectedArticle && (
              <ArticlePreview article={selectedArticle} />
            )}
          </div>

          <div className="border-t border-[#e4ded3] bg-[#fffefa] p-3">
            <button
              type="button"
              onClick={analyze}
              disabled={!canAnalyze}
              className="legal-action h-[42px] w-full justify-center disabled:pointer-events-none disabled:opacity-50"
            >
              <FlaskConical className="legal-action-icon mr-2 h-4 w-4" />
              <span>{loading ? "模拟中..." : "运行模拟"}</span>
            </button>
          </div>
        </aside>

        <main className="legal-card flex min-h-0 flex-col overflow-hidden">
          <ResultHeader result={result} loading={loading} />
          {error && (
            <div className="mx-4 mt-3 flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}
          <div className="min-h-0 flex-1 overflow-auto p-4">
            {loading ? (
              <LoadingState />
            ) : result ? (
              <ResultWorkspace result={result} selectedDirection={selectedDirection} />
            ) : (
              <EmptyState />
            )}
          </div>
        </main>
      </section>
    </div>
  );
}

function FieldGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="relative space-y-1.5">
      <label className="text-[11px] font-medium text-[#7c735f]">{label}</label>
      {children}
    </div>
  );
}

function DropdownButton({
  text,
  open,
  disabled,
  onClick,
  icon,
}: {
  text: string;
  open: boolean;
  disabled?: boolean;
  onClick: () => void;
  icon?: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-open={open}
      disabled={disabled}
      className="legal-input flex w-full items-center justify-between px-3 py-2.5 text-left text-[#1f2933] disabled:cursor-not-allowed disabled:opacity-60"
    >
      <span className="flex min-w-0 items-center gap-2">
        {icon}
        <span className="truncate">{text}</span>
      </span>
      <ChevronDown className="h-4 w-4 shrink-0 text-[#8a7f6c]" />
    </button>
  );
}

function DropdownPanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="absolute z-50 mt-1 max-h-56 w-full overflow-auto rounded-md border border-[#d8d0c1] bg-[#fffefa] py-1 shadow-xl">
      {children}
    </div>
  );
}

function DropdownItem({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`block w-full px-3 py-2 text-left text-xs transition-colors ${
        active
          ? "bg-[#1f3a5f] text-[#fffefa]"
          : "text-[#5f574a] hover:bg-[#f3eee5] hover:text-[#1f2933]"
      }`}
    >
      {label}
    </button>
  );
}

function DirectionChip({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-2.5 py-1 text-[11px] transition-colors ${
        active
          ? "border-[#1f3a5f] bg-[#1f3a5f] text-[#fffefa]"
          : "border-[#d8d0c1] bg-[#fffefa] text-[#5f574a] hover:border-[#1f3a5f] hover:text-[#1f3a5f]"
      }`}
    >
      {label}
    </button>
  );
}

function ArticlePreview({ article }: { article: LawArticle }) {
  return (
    <section className="min-h-0 rounded-md border border-[#e4ded3] bg-[#f8f6f1] p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-[#8a7f6c]">
          <BookOpen className="h-3.5 w-3.5" />
          条文预览
        </div>
        <StatusBadge status={article.status} />
      </div>
      <div className="text-sm font-semibold text-[#1f2933]">{article.article_no}</div>
      {article.effective_start && (
        <div className="mt-1 text-[11px] text-[#8a7f6c]">
          施行于 {article.effective_start}
          {article.effective_end && `，失效于 ${article.effective_end}`}
        </div>
      )}
      <div className="mt-2 max-h-28 overflow-auto pr-1 text-xs leading-6 text-[#5f574a]">
        {article.text_preview}
      </div>
    </section>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    有效: "border-emerald-200 bg-emerald-50 text-emerald-700",
    尚未实施: "border-amber-200 bg-amber-50 text-amber-700",
    已修改: "border-[#d8d0c1] bg-[#f7f3eb] text-[#6f6658]",
    已废止: "border-red-200 bg-red-50 text-red-700",
  };
  const cls = map[status] || "border-[#d8d0c1] bg-[#f7f3eb] text-[#6f6658]";
  return <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${cls}`}>{status}</span>;
}

function ResultHeader({
  result,
  loading,
}: {
  result: CounterfactualResponse | null;
  loading: boolean;
}) {
  return (
    <div className="flex shrink-0 items-center justify-between gap-4 border-b border-[#e4ded3] px-4 py-3">
      <div>
        <h2 className="text-sm font-semibold text-[#1f2933]">分析结果</h2>
        <p className="mt-1 text-xs text-[#7c735f]">
          {result
            ? `共识别 ${result.total_affected} 个可能受影响条文`
            : loading
            ? "正在计算直接与间接影响链"
            : "运行模拟后在这里查看结果"}
        </p>
      </div>
      {result && (
        <div className="hidden gap-2 sm:flex">
          <Metric label="直接" value={result.direct_impacts.length} />
          <Metric label="间接" value={result.indirect_impacts.length} />
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-[#e4ded3] bg-[#f8f6f1] px-3 py-1.5 text-right">
      <div className="text-[10px] text-[#8a7f6c]">{label}</div>
      <div className="text-base font-semibold leading-5 text-[#1f2933]">{value}</div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full min-h-[360px] items-center justify-center rounded-md border border-dashed border-[#d8d0c1] bg-[#f8f6f1] px-8 text-center">
      <div>
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-md bg-[#fffefa] text-[#1f3a5f] shadow-sm">
          <FlaskConical className="h-5 w-5" />
        </div>
        <h3 className="mt-4 text-base font-semibold text-[#1f2933]">等待运行反事实模拟</h3>
        <p className="mt-2 max-w-md text-sm leading-6 text-[#7c735f]">
          左侧选择法律、条文和偏移方向。结果区会集中展示目标解释、LLM 摘要、直接影响和间接传导。
        </p>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex h-full min-h-[360px] items-center justify-center text-sm text-[#7c735f]">
      <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-[#d8d0c1] border-t-[#1f3a5f]" />
      正在沿引用链评估影响范围...
    </div>
  );
}

function ResultWorkspace({
  result,
  selectedDirection,
}: {
  result: CounterfactualResponse;
  selectedDirection?: DirectionInfo;
}) {
  return (
    <div className="space-y-3">
      <section className="rounded-md border border-[#e4ded3] bg-[#fffefa] p-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-[#1f2933]">
          <ArrowRight className="h-4 w-4 text-[#1f3a5f]" />
          模拟目标
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <InfoBlock label="条文" value={`《${result.target_law}》${result.target_article}`} />
          <InfoBlock label="解释方向" value={result.interpreted_direction} highlight />
          <InfoBlock label="原始方向" value={formatDirection(result.original_direction)} />
          {selectedDirection && (
            <InfoBlock label="方向注册表" value={formatCategories(selectedDirection.affected) || "未声明影响类别"} />
          )}
        </div>
        {result.target_text && (
          <div className="mt-3 rounded-md border border-[#e4ded3] bg-[#f8f6f1] p-3 text-xs leading-6 text-[#5f574a]">
            {result.target_text}
          </div>
        )}
        {result.affected_categories.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {result.affected_categories.map((category) => (
              <span
                key={category}
                className="rounded-full border border-[#d8d0c1] bg-[#f7f3eb] px-2.5 py-1 text-[11px] text-[#5f574a]"
              >
                {formatCategory(category)}
              </span>
            ))}
          </div>
        )}
      </section>

      {shouldShowSummary(result.llm_summary) && (
        <section className="rounded-md border border-[#c9d3df] bg-[#fbfdff] p-4">
          <div className="text-xs font-medium uppercase tracking-[0.16em] text-[#1f3a5f]">
            LLM 分析摘要
          </div>
          <FormattedReasoning content={result.llm_summary} />
        </section>
      )}

      <div className="grid gap-3 xl:grid-cols-2">
        <ImpactSection title="直接影响" count={result.direct_impacts.length} tone="amber">
          {result.direct_impacts.length === 0 ? (
            <EmptyImpact label="无直接影响" />
          ) : (
            result.direct_impacts.map((impact, index) => (
              <ImpactCard key={`direct-${impact.law_title}-${impact.article_no}-${index}`} impact={impact} />
            ))
          )}
        </ImpactSection>
        <ImpactSection title="间接传导" count={result.indirect_impacts.length} tone="blue">
          {result.indirect_impacts.length === 0 ? (
            <EmptyImpact label="无间接传导" />
          ) : (
            result.indirect_impacts.map((impact, index) => (
              <ImpactCard key={`indirect-${impact.law_title}-${impact.article_no}-${index}`} impact={impact} />
            ))
          )}
        </ImpactSection>
      </div>
    </div>
  );
}

function InfoBlock({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-md border border-[#e4ded3] bg-[#fffefa] p-3">
      <div className="text-[11px] font-medium text-[#8a7f6c]">{label}</div>
      <div className={`mt-1 text-sm leading-6 ${highlight ? "font-medium text-[#1f3a5f]" : "text-[#394453]"}`}>
        {value}
      </div>
    </div>
  );
}

function FormattedReasoning({ content, compact = false }: { content: string; compact?: boolean }) {
  const parsed = parseStructuredContent(content);

  if (parsed) {
    const items = Array.isArray(parsed) ? parsed : [parsed];
    return (
      <div className={compact ? "space-y-2" : "mt-3 space-y-2"}>
        {items.map((item, index) => (
          <StructuredReasoningCard key={index} item={item} compact={compact} />
        ))}
      </div>
    );
  }

  const blocks = normalizeReasoningText(content)
    .replace(/\r\n/g, "\n")
    .split(/\n{2,}/)
    .map((item) => item.trim())
    .filter(Boolean);

  return (
    <div className={compact ? "space-y-2" : "mt-3 space-y-2 text-sm leading-7 text-[#394453]"}>
      {blocks.map((block, index) => {
        const heading = block.match(/^#{1,6}\s+(.+)$/);
        if (heading) {
          return (
            <div key={index} className="font-semibold text-[#1f2933]">
              {heading[1]}
            </div>
          );
        }
        return (
          <p key={index} className={compact ? "text-xs leading-6 text-[#5f574a]" : undefined}>
            {block.replace(/^[-*]\s+/, "")}
          </p>
        );
      })}
    </div>
  );
}

function StructuredReasoningCard({
  item,
  compact,
}: {
  item: Record<string, unknown>;
  compact: boolean;
}) {
  const entries = Object.entries(item)
    .filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== "")
    .map(([key, value]) => [key, formatStructuredValue(key, value)] as const)
    .filter(([, value]) => value !== "");
  const primary = entries.find(([key]) => ["reasoning", "llm_reasoning", "impact_reasoning"].includes(key));
  const secondary = entries.filter(([key]) => !["reasoning", "llm_reasoning", "impact_reasoning"].includes(key));

  return (
    <div className={compact ? "space-y-2" : "rounded-md border border-[#e4ded3] bg-[#fffefa] p-3"}>
      {primary && (
        <div className={compact ? "text-xs leading-6 text-[#5f574a]" : "text-sm leading-7 text-[#394453]"}>
          {primary[1]}
        </div>
      )}
      {secondary.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {secondary.map(([key, value]) => (
            <span
              key={key}
              className="rounded-full border border-[#d8d0c1] bg-[#f8f6f1] px-2 py-0.5 text-[11px] text-[#5f574a]"
            >
              <span className="text-[#8a7f6c]">{STRUCTURED_FIELD_LABELS[key] ?? toReadableFieldName(key)}：</span>
              {value}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function shouldShowSummary(content: string) {
  const trimmed = stripCodeFence(content.trim());
  if (!trimmed) return false;
  const parsed = parseStructuredContent(content);
  if (Array.isArray(parsed)) return false;
  if (!parsed && looksLikeRawStructuredOutput(trimmed)) return false;
  return true;
}

function parseStructuredContent(content: string): Record<string, unknown> | Record<string, unknown>[] | null {
  const trimmed = stripCodeFence(content.trim());
  if (!trimmed) return null;

  const direct = tryParseJson(trimmed);
  if (direct) return normalizeParsedJson(direct);

  const jsonLike = extractJsonLike(trimmed);
  if (!jsonLike) return null;

  const extracted = tryParseJson(jsonLike);
  return extracted ? normalizeParsedJson(extracted) : null;
}

function normalizeParsedJson(value: unknown): Record<string, unknown> | Record<string, unknown>[] | null {
  if (Array.isArray(value)) {
    const records = value.filter(isRecord);
    return records.length > 0 ? records : null;
  }
  if (isRecord(value)) {
    if (Array.isArray(value.impacts)) {
      const records = value.impacts.filter(isRecord);
      return records.length > 0 ? records : null;
    }
    return value;
  }
  return null;
}

function tryParseJson(value: string): unknown | null {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function stripCodeFence(value: string) {
  return value
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/```$/i, "")
    .trim();
}

function extractJsonLike(value: string) {
  const arrayStart = value.indexOf("[");
  const objectStart = value.indexOf("{");
  const starts = [arrayStart, objectStart].filter((index) => index >= 0);
  if (starts.length === 0) return null;

  const start = Math.min(...starts);
  const endToken = value[start] === "[" ? "]" : "}";
  const end = value.lastIndexOf(endToken);
  return end > start ? value.slice(start, end + 1) : null;
}

function looksLikeRawStructuredOutput(value: string) {
  const trimmed = value.trim();
  if (!trimmed.startsWith("[") && !trimmed.startsWith("{")) return false;
  return (
    trimmed.includes('"risk_level"') ||
    trimmed.includes('"风险等级"') ||
    trimmed.includes('"reasoning"') ||
    trimmed.includes('"传导逻辑"') ||
    trimmed.includes('"article_key"') ||
    trimmed.includes('"条文"')
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatStructuredValue(key: string, value: unknown): string {
  if (Array.isArray(value)) {
    if (key === "affected_categories" || key === "affected") {
      return formatCategories(value.map(String));
    }
    return value.map((item) => formatScalarValue(key, item)).join("、");
  }
  return formatScalarValue(key, value);
}

function formatScalarValue(key: string, value: unknown): string {
  const text = String(value).trim();
  if (!text) return "";
  if (key === "risk_level") return formatRiskLevel(text);
  if (key === "affected_category") return formatCategory(text);
  if (key === "directness") {
    if (text.toLowerCase() === "direct") return "直接影响";
    if (text.toLowerCase() === "indirect") return "间接传导";
  }
  return normalizeReasoningText(text);
}

function normalizeReasoningText(value: string) {
  return value
    .replace(/```(?:json)?/gi, "")
    .replace(/```/g, "")
    .replace(/\brisk_level\b/g, "风险等级")
    .replace(/\breasoning\b/g, "传导逻辑")
    .replace(/\barticle_key\b/g, "条文")
    .replace(/\blaw_title\b/g, "法律")
    .replace(/\barticle_no\b/g, "条文")
    .replace(/\bHigh\b/g, "高风险")
    .replace(/\bMedium\b/g, "中风险")
    .replace(/\bLow\b/g, "低风险")
    .replace(/\bPotential\b/g, "潜在影响")
    .replace(/\bUnknown\b/g, "未知")
    .replace(/\bobligation_increase\b/g, "义务加重")
    .replace(/\bobligation_decrease\b/g, "义务减轻")
    .replace(/\bscope_expand\b/g, "范围扩大")
    .replace(/\bscope_narrow\b/g, "范围缩小")
    .replace(/\bthreshold_raise\b/g, "门槛提高")
    .replace(/\bthreshold_lower\b/g, "门槛降低")
    .replace(/\bright_strengthen\b/g, "权利强化")
    .replace(/\bright_weaken\b/g, "权利弱化")
    .replace(/\bprocedure_tighten\b/g, "程序收紧")
    .replace(/\bprocedure_loosen\b/g, "程序放宽")
    .replace(/\bprotection_shift\b/g, "保护重心转移")
    .replace(/\bobligation\b/g, "义务")
    .replace(/\bscope\b/g, "适用范围")
    .replace(/\bthreshold\b/g, "门槛标准")
    .replace(/\bright\b/g, "权利")
    .replace(/\bprocedure\b/g, "程序")
    .replace(/\bnegation\b/g, "禁止性规则")
    .replace(/\bpermission\b/g, "授权许可")
    .replace(/\bsanction\b/g, "责任后果")
    .replace(/\bcondition\b/g, "适用条件")
    .replace(/\btime\b/g, "期限")
    .replace(/\bamount\b/g, "数量金额")
    .trim();
}

function formatDirection(value: string) {
  return DIRECTION_LABELS[value] || normalizeReasoningText(value);
}

function formatRiskLevel(value: string) {
  return RISK_LABELS[value] || normalizeReasoningText(value);
}

function formatCategory(value: string) {
  return CATEGORY_LABELS[value] || value;
}

function formatCategories(values: string[]) {
  return values.map(formatCategory).join("、");
}

function toReadableFieldName(value: string) {
  return value.replace(/_/g, " ");
}

function ImpactSection({
  title,
  count,
  tone,
  children,
}: {
  title: string;
  count: number;
  tone: "amber" | "blue";
  children: React.ReactNode;
}) {
  const toneClass =
    tone === "amber"
      ? "border-amber-200 bg-amber-50 text-amber-700"
      : "border-sky-200 bg-sky-50 text-sky-700";
  return (
    <section className="rounded-md border border-[#e4ded3] bg-[#fffefa] p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-[#1f2933]">{title}</h2>
        <span className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${toneClass}`}>
          {count} 条
        </span>
      </div>
      <div className="max-h-[420px] space-y-2 overflow-auto pr-1">{children}</div>
    </section>
  );
}

function EmptyImpact({ label }: { label: string }) {
  return (
    <div className="rounded-md border border-[#e4ded3] bg-[#f8f6f1] p-4 text-center text-xs text-[#7c735f]">
      {label}
    </div>
  );
}

function ImpactCard({ impact }: { impact: CounterfactualImpactItem }) {
  const riskColor: Record<string, string> = {
    High: "border-red-200 bg-red-50 text-red-700",
    Medium: "border-amber-200 bg-amber-50 text-amber-700",
    Low: "border-emerald-200 bg-emerald-50 text-emerald-700",
    Potential: "border-sky-200 bg-sky-50 text-sky-700",
    Unknown: "border-[#d8d0c1] bg-[#f7f3eb] text-[#6f6658]",
  };
  const iconColor: Record<string, string> = {
    High: "text-red-700",
    Medium: "text-amber-700",
    Low: "text-emerald-700",
    Potential: "text-sky-700",
    Unknown: "text-[#6f6658]",
  };
  const RiskIcon = impact.risk_level === "High" ? ShieldAlert : impact.risk_level === "Low" ? ShieldCheck : Shield;
  const riskLevelLabel = formatRiskLevel(impact.risk_level);

  return (
    <div className="rounded-md border border-[#e4ded3] bg-[#fffefa] p-3 transition-[border-color,box-shadow] duration-200 hover:border-[#cfc5b5] hover:shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-[#1f2933]">
          《{impact.law_title}》{impact.article_no}
        </span>
        <span
          className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${
            riskColor[impact.risk_level] || riskColor.Unknown
          }`}
        >
          <RiskIcon className={`h-3.5 w-3.5 ${iconColor[impact.risk_level] || iconColor.Unknown}`} />
          {riskLevelLabel}
        </span>
      </div>
      {impact.llm_reasoning && (
        <div className="mt-3 border-t border-[#e4ded3] pt-3 text-xs leading-6 text-[#5f574a]">
          <FormattedReasoning content={impact.llm_reasoning} compact />
        </div>
      )}
    </div>
  );
}
