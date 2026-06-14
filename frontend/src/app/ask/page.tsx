"use client";

import { useEffect, useRef, useState } from "react";
import { askQuestion, getErrorMessage, type Citation, type LineageStep } from "@/lib/api";
import {
  AlertCircle,
  BookOpen,
  ChevronDown,
  ChevronUp,
  GitCompare,
  Send,
} from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

const sampleQuestions = [
  "有限责任公司小股东想查公司账目，法律是怎么规定的？",
  "公司拖欠工资，劳动者可以直接离职吗？",
  "企业把用户数据发到境外服务器，需要满足什么条件？",
];

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

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
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
    } catch (err: unknown) {
      setError(getErrorMessage(err));
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <section className="legal-card flex shrink-0 flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="flex min-w-[240px] items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-md bg-[#1f3a5f] text-[#fffefa]">
            <BookOpen className="h-4 w-4" />
          </span>
          <div>
            <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-[#8a7f6c]">
              RAG LEGAL ASK
            </div>
            <h1 className="text-base font-semibold tracking-tight text-[#1f2933]">法律咨询</h1>
          </div>
        </div>
        <label className="flex items-center gap-2 text-xs text-[#7c735f]">
          查询日期
          <input
            type="date"
            value={currentDate}
            onChange={(event) => setCurrentDate(event.target.value)}
            className="legal-input px-3 py-2 text-[#1f2933]"
          />
        </label>
      </section>

      <section className="legal-card flex min-h-0 flex-1 flex-col overflow-hidden">
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto px-4 py-4">
          {messages.length === 0 && !loading ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <div className="rounded-2xl border border-[#e4ded3] bg-[#f8f6f1] p-4">
                <BookOpen className="h-8 w-8 text-[#1f3a5f]" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-[#1f2933]">输入问题，查看带引用的法律回答</h2>
                <p className="mt-1 text-sm text-[#7c735f]">
                  回答会附带检索来源和条文血缘，历史消息只在聊天容器内滚动。
                </p>
              </div>
              <div className="flex max-w-3xl flex-wrap justify-center gap-2">
                {sampleQuestions.map((question) => (
                  <button
                    key={question}
                    onClick={() => setInput(question)}
                    className="rounded-full border border-[#d8d0c1] bg-[#fffefa] px-3 py-1.5 text-xs text-[#5f574a] transition-colors hover:border-[#1f3a5f] hover:text-[#1f3a5f]"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((message, index) => (
                <MessageBubble key={index} message={message} />
              ))}
              {loading && (
                <div className="flex items-center gap-2 rounded-md border border-[#e4ded3] bg-[#f8f6f1] px-3 py-2 text-sm text-[#7c735f]">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#d8d0c1] border-t-[#1f3a5f]" />
                  正在检索知识库并生成回答...
                </div>
              )}
              {error && (
                <div className="flex items-center gap-2 rounded-md border border-[#f3b4ad] bg-[#fff1f0] px-3 py-2 text-sm text-[#9f1f17]">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  {error}
                </div>
              )}
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="shrink-0 border-t border-[#e4ded3] bg-[#fffefa] p-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="输入法律问题..."
              className="legal-input flex-1 px-4 py-3 text-[#1f2933] placeholder:text-[#a09684]"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="inline-flex items-center gap-2 rounded-md border border-[#1f3a5f] bg-[#1f3a5f] px-4 py-3 text-sm font-medium text-[#fffefa] transition-colors hover:bg-[#172d4b] disabled:cursor-not-allowed disabled:border-[#d8d0c1] disabled:bg-[#ede7dc] disabled:text-[#8a7f6c]"
            >
              <Send className="h-4 w-4" />
              提问
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={`max-w-[84%] space-y-3 rounded-lg border px-4 py-3 ${
          isUser
            ? "border-[#1f3a5f] bg-[#1f3a5f] text-[#fffefa]"
            : "border-[#e4ded3] bg-[#fffefa] text-[#1f2933]"
        }`}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap text-sm leading-7">{message.content}</div>
        ) : (
          <MarkdownAnswer content={message.content} />
        )}
        {message.citations && message.citations.length > 0 && (
          <div className="space-y-2 border-t border-[#e4ded3] pt-3">
            <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-[#8a7f6c]">
              引用来源
            </div>
            {message.citations.map((citation, index) => (
              <CitationCard key={index} citation={citation} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

type MarkdownBlock =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "quote"; text: string }
  | { type: "list"; ordered: boolean; items: string[] };

function MarkdownAnswer({ content }: { content: string }) {
  const blocks = parseMarkdownBlocks(content);

  return (
    <div className="space-y-3 text-sm leading-7 text-[#1f2933]">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          const className =
            block.level <= 2
              ? "border-b border-[#e4ded3] pb-1 text-base font-semibold leading-7 text-[#1f2933]"
              : "text-sm font-semibold leading-7 text-[#1f2933]";
          return (
            <div key={index} className={className}>
              {renderInlineMarkdown(block.text)}
            </div>
          );
        }

        if (block.type === "quote") {
          return (
            <blockquote
              key={index}
              className="rounded-md border-l-2 border-[#1f3a5f] bg-[#f8f6f1] px-3 py-2 text-xs leading-6 text-[#5f574a]"
            >
              {renderInlineMarkdown(block.text)}
            </blockquote>
          );
        }

        if (block.type === "list") {
          const ListTag = block.ordered ? "ol" : "ul";
          return (
            <ListTag
              key={index}
              className={`space-y-1 pl-5 text-[#394453] ${
                block.ordered ? "list-decimal" : "list-disc"
              }`}
            >
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
              ))}
            </ListTag>
          );
        }

        return (
          <p key={index} className="text-[#394453]">
            {renderInlineMarkdown(block.text)}
          </p>
        );
      })}
    </div>
  );
}

function parseMarkdownBlocks(content: string): MarkdownBlock[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    blocks.push({ type: "paragraph", text: paragraph.join(" ") });
    paragraph = [];
  };

  const flushList = () => {
    if (!list) return;
    blocks.push({ type: "list", ordered: list.ordered, items: list.items });
    list = null;
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        text: headingMatch[2],
      });
      continue;
    }

    const quoteMatch = line.match(/^>\s?(.+)$/);
    if (quoteMatch) {
      flushParagraph();
      flushList();
      blocks.push({ type: "quote", text: quoteMatch[1] });
      continue;
    }

    const unorderedMatch = line.match(/^[-*]\s+(.+)$/);
    const orderedMatch = line.match(/^\d+[.)]\s+(.+)$/);
    if (unorderedMatch || orderedMatch) {
      flushParagraph();
      const ordered = Boolean(orderedMatch);
      const item = unorderedMatch?.[1] ?? orderedMatch?.[1] ?? "";
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push(item);
      continue;
    }

    flushList();
    paragraph.push(line);
  }

  flushParagraph();
  flushList();
  return blocks;
}

function renderInlineMarkdown(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);

  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={index} className="font-semibold text-[#1f2933]">
          {part.slice(2, -2)}
        </strong>
      );
    }

    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={index}
          className="rounded border border-[#e4ded3] bg-[#f8f6f1] px-1 py-0.5 text-[0.92em] text-[#1f3a5f]"
        >
          {part.slice(1, -1)}
        </code>
      );
    }

    return part;
  });
}

function CitationCard({ citation }: { citation: Citation }) {
  const [expanded, setExpanded] = useState(false);
  const [lineageExpanded, setLineageExpanded] = useState(false);

  const statusColor: Record<string, string> = {
    有效: "text-emerald-700",
    已修改: "text-amber-700",
    尚未生效: "text-sky-700",
    已废止: "text-red-700",
  };

  return (
    <div className="rounded-md border border-[#e4ded3] bg-[#f8f6f1] p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-medium text-[#1f2933]">{citation.label}</span>
            <span className={statusColor[citation.status] || "text-[#7c735f]"}>
              {citation.status}
            </span>
          </div>
          <div className="mt-1 text-[11px] text-[#7c735f]">
            {citation.article_no}
            {citation.effective_start && ` · 施行 ${citation.effective_start}`}
            {citation.law_category && ` · ${citation.law_category}`}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="shrink-0 rounded p-1 text-[#7c735f] hover:bg-[#ede7dc] hover:text-[#1f2933]"
        >
          {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 space-y-3 border-t border-[#e4ded3] pt-3">
          <div className="text-xs leading-6 text-[#5f574a]">{citation.snippet}</div>
          {citation.lineage_chain.length > 0 && (
            <div>
              <button
                type="button"
                onClick={() => setLineageExpanded((value) => !value)}
                className="flex items-center gap-1 text-[11px] text-[#7c735f] hover:text-[#1f2933]"
              >
                <GitCompare className="h-3 w-3" />
                版本对比（{citation.lineage_chain.length} 个版本）
                {lineageExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              </button>
              {lineageExpanded && (
                <div className="mt-2 space-y-2">
                  {citation.lineage_chain.map((step, index) => (
                    <LineageStepCard key={index} step={step} />
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
      ? "text-[#7c735f]"
      : step.drift_score >= 0.3
      ? "text-red-700"
      : step.drift_score >= 0.1
      ? "text-amber-700"
      : "text-emerald-700";

  return (
    <div className="rounded-md border border-[#e4ded3] bg-[#fffefa] p-2">
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span className="font-medium text-[#1f2933]">{step.version_label}</span>
        <span className="text-[#9a907d]">·</span>
        <span className="text-[#5f574a]">{step.change_type}</span>
        {step.drift_score !== undefined && (
          <>
            <span className="text-[#9a907d]">·</span>
            <span className={driftColor}>漂移 {(step.drift_score * 100).toFixed(1)}%</span>
          </>
        )}
        {step.has_critical_change && (
          <span className="rounded-full border border-red-200 bg-red-50 px-1.5 py-0.5 text-[10px] text-red-700">
            关键变化
          </span>
        )}
      </div>
      {step.derived_from_article && (
        <div className="mt-1 text-[10px] text-[#7c735f]">源自：{step.derived_from_article}</div>
      )}
    </div>
  );
}
