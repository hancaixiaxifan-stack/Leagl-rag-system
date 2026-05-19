"use client";

import { useState, useRef, useEffect } from "react";
import { askQuestion, type AskResponse, type Citation, type LineageStep } from "@/lib/api";
import { Send, AlertCircle, BookOpen, ChevronDown, ChevronUp, GitCompare } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

export default function AskPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [currentDate, setCurrentDate] = useState(new Date().toISOString().split("T")[0]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const question = input.trim();
    setInput("");
    setError("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    try {
      const data = await askQuestion(question, currentDate);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.answer, citations: data.citations },
      ]);
    } catch (e: any) {
      setError(e.message);
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-slate-100">法律咨询</h1>
        <p className="mt-1 text-xs text-slate-400">
          基于向量检索 + BM25 的智能法律问答，回答含引用来源
        </p>
      </div>

      {messages.length === 0 && !loading && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <div className="rounded-full border border-slate-800 bg-slate-900/50 p-4">
            <BookOpen className="h-8 w-8 text-emerald-400" />
          </div>
          <p className="text-sm text-slate-500">输入法律问题，获取基于知识库的精准回答</p>
          <div className="flex flex-wrap justify-center gap-2">
            {[
              "有限公司小股东想查公司账目，法律是怎么规定的？",
              "公司拖欠工资，劳动者可以直接走人吗？",
              "企业把用户数据发到境外服务器，需要满足什么条件？",
            ].map((q) => (
              <button
                key={q}
                onClick={() => {
                  setInput(q);
                }}
                className="rounded-full border border-slate-800 bg-slate-900/50 px-3 py-1.5 text-xs text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-auto pr-2">
        {messages.map((msg, i) => (
          <div key={i} className={msg.role === "user" ? "flex justify-end" : ""}>
            <div
              className={`max-w-[85%] space-y-2 rounded-lg px-4 py-3 ${
                msg.role === "user"
                  ? "bg-emerald-500/10 border border-emerald-500/20"
                  : "bg-slate-900/50 border border-slate-800"
              }`}
            >
              <div
                className={`whitespace-pre-wrap text-sm leading-relaxed ${
                  msg.role === "user" ? "text-emerald-100" : "text-slate-200"
                }`}
              >
                {msg.content}
              </div>
              {msg.citations && msg.citations.length > 0 && (
                <div className="space-y-2 border-t border-slate-800 pt-2">
                  <div className="text-[11px] font-medium text-slate-500">引用来源</div>
                  <div className="space-y-2">
                    {msg.citations.map((c, ci) => (
                      <CitationCard key={ci} citation={c} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex items-center gap-2 py-2 text-sm text-slate-500">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-slate-300" />
            正在检索知识库并生成回答...
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-red-900/30 bg-red-950/30 px-4 py-3 text-sm text-red-400">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="mt-4 flex gap-2">
        <input
          type="date"
          value={currentDate}
          onChange={(e) => setCurrentDate(e.target.value)}
          className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-200 focus:border-emerald-500/50 focus:outline-none"
        />
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入法律问题..."
          className="flex-1 rounded-md border border-slate-700 bg-slate-900 px-4 py-2.5 text-sm text-slate-200 placeholder:text-slate-600 focus:border-emerald-500/50 focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="flex items-center gap-1.5 rounded-md bg-emerald-500/10 px-4 py-2.5 text-sm font-medium text-emerald-400 transition-colors hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send className="h-4 w-4" />
          提问
        </button>
      </form>
    </div>
  );
}

function CitationCard({ citation }: { citation: Citation }) {
  const [expanded, setExpanded] = useState(false);
  const [lineageExpanded, setLineageExpanded] = useState(false);

  const statusColor: Record<string, string> = {
    有效: "text-emerald-400",
    已修改: "text-amber-400",
    尚未生效: "text-sky-400",
    已废止: "text-red-400",
  };

  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/50 p-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs">
            <span className="font-medium text-slate-300">{citation.label}</span>
            <span className={statusColor[citation.status] || "text-slate-500"}>
              {citation.status}
            </span>
          </div>
          <div className="mt-1 text-[11px] text-slate-500">
            {citation.article_no}
            {citation.effective_start && ` · 施行 ${citation.effective_start}`}
            {citation.law_category && ` · ${citation.law_category}`}
          </div>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="shrink-0 text-slate-500 hover:text-slate-300"
        >
          {expanded ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )}
        </button>
      </div>

      {expanded && (
        <div className="mt-2 space-y-2 border-t border-slate-800 pt-2">
          <div className="text-xs leading-relaxed text-slate-400">{citation.snippet}</div>

          {citation.lineage_chain.length > 0 && (
            <div>
              <button
                onClick={() => setLineageExpanded(!lineageExpanded)}
                className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-300"
              >
                <GitCompare className="h-3 w-3" />
                版本对比 ({citation.lineage_chain.length} 个版本)
                {lineageExpanded ? (
                  <ChevronUp className="h-3 w-3" />
                ) : (
                  <ChevronDown className="h-3 w-3" />
                )}
              </button>

              {lineageExpanded && (
                <div className="mt-2 space-y-2">
                  {citation.lineage_chain.map((step, si) => (
                    <LineageStepCard key={si} step={step} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function LineageStepCard({ step }: { step: LineageStep }) {
  const driftColor =
    step.drift_score === undefined
      ? "text-slate-500"
      : step.drift_score >= 0.3
      ? "text-red-400"
      : step.drift_score >= 0.1
      ? "text-amber-400"
      : "text-emerald-400";

  return (
    <div className="rounded border border-slate-800/60 bg-slate-900/30 p-2">
      <div className="flex items-center gap-2 text-[11px]">
        <span className="font-medium text-slate-300">{step.version_label}</span>
        <span className="text-slate-600">·</span>
        <span className="text-slate-400">{step.change_type}</span>
        {step.drift_score !== undefined && (
          <>
            <span className="text-slate-600">·</span>
            <span className={driftColor}>漂移 {(step.drift_score * 100).toFixed(1)}%</span>
          </>
        )}
        {step.has_critical_change && (
          <span className="rounded bg-red-500/20 px-1 text-[10px] text-red-400">
            关键变化
          </span>
        )}
      </div>
      {step.derived_from_article && step.derived_from_article !== "" && (
        <div className="mt-1 text-[10px] text-slate-500">
          源自: {step.derived_from_article}
        </div>
      )}
      {step.sensitive_deltas.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {step.sensitive_deltas.map((delta, di) => (
            <span
              key={di}
              className={`rounded px-1 py-0.5 text-[10px] ${
                delta.polarity_flipped
                  ? "bg-red-500/15 text-red-400"
                  : delta.category_shifted
                  ? "bg-amber-500/15 text-amber-400"
                  : "bg-slate-800 text-slate-400"
              }`}
            >
              {delta.word}
              {delta.old_category && delta.new_category && (
                <span className="ml-0.5 text-slate-500">
                  ({delta.old_category} → {delta.new_category})
                </span>
              )}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
