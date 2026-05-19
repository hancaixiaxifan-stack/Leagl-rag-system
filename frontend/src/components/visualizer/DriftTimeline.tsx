"use client";

import { useState, useCallback } from "react";
import type { DriftNode, SensitiveDelta } from "@/types";
import { ArrowRight, AlertTriangle, GitMerge, Split } from "lucide-react";

// ─────────────────────────────────────────────
// 常量
// ─────────────────────────────────────────────

const STATUS_COLOR_MAP: Record<string, string> = {
  有效: "bg-emerald-500",
  已修改: "bg-amber-500",
  已废止: "bg-red-500",
  尚未实施: "bg-sky-500",
};

const DRIFT_THRESHOLDS = {
  major: 0.7,
  moderate: 0.3,
  minor: 0.05,
};

function driftLabel(score?: number): { text: string; color: string } {
  if (score === undefined) return { text: "新增", color: "text-slate-400" };
  if (score >= DRIFT_THRESHOLDS.major) return { text: "重大变更", color: "text-red-400" };
  if (score >= DRIFT_THRESHOLDS.moderate) return { text: "较大修订", color: "text-amber-400" };
  if (score >= DRIFT_THRESHOLDS.minor) return { text: "小幅调整", color: "text-yellow-400" };
  return { text: "几乎无变化", color: "text-emerald-400" };
}

// ─────────────────────────────────────────────
// 子组件：敏感词差异渲染
// ─────────────────────────────────────────────

function SensitiveWordDiff({ deltas }: { deltas: SensitiveDelta[] }) {
  if (deltas.length === 0) return null;

  return (
    <div className="mt-2 space-y-1.5">
      <div className="text-[11px] font-medium text-slate-500">敏感词差异</div>
      <div className="flex flex-wrap gap-1.5">
        {deltas.map((delta, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 rounded-md border border-slate-700/50 bg-slate-900/60 px-2 py-0.5 text-[11px]"
          >
            {delta.polarity_flipped ? (
              <>
                <span className="text-red-400 line-through decoration-red-500/60">{delta.word}</span>
                <ArrowRight className="h-3 w-3 text-slate-500" />
                <span className="font-semibold text-emerald-400">{delta.word}</span>
                <span className="ml-0.5 rounded bg-red-500/15 px-1 py-px text-[10px] text-red-400">
                  极性翻转
                </span>
              </>
            ) : delta.category_shifted ? (
              <>
                <span className="text-slate-400 line-through decoration-slate-500/40">
                  {delta.old_category}
                </span>
                <ArrowRight className="h-3 w-3 text-slate-500" />
                <span className="font-semibold text-emerald-400">{delta.new_category}</span>
                <span className="ml-0.5 text-slate-400">「{delta.word}」</span>
              </>
            ) : (
              <span className="text-slate-300">{delta.word}</span>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// 子组件：时间点卡片
// ─────────────────────────────────────────────

interface TimelineItemProps {
  node: DriftNode;
  index: number;
  total: number;
  isSelected: boolean;
  onSelect: (node: DriftNode) => void;
}

function TimelineItem({ node, index, total, isSelected, onSelect }: TimelineItemProps) {
  const isLast = index === total - 1;
  const isFirst = index === 0;
  const drift = driftLabel(node.drift_score);
  const statusDot = STATUS_COLOR_MAP[node.status] ?? "bg-slate-500";

  return (
    <div className="relative flex gap-4">
      {/* 时间轴竖线 */}
      {!isFirst && (
        <div className="absolute left-[11px] top-0 h-full w-px bg-slate-800 -translate-y-1/2" />
      )}
      {!isLast && (
        <div className="absolute left-[11px] top-1/2 h-full w-px bg-slate-800" />
      )}

      {/* 节点圆点 */}
      <div className="relative z-10 flex shrink-0 flex-col items-center pt-1">
        <button
          onClick={() => onSelect(node)}
          className={`h-6 w-6 rounded-full border-2 transition-all ${
            isSelected
              ? "border-slate-200 bg-slate-200 shadow-[0_0_12px_rgba(226,232,240,0.3)]"
              : "border-slate-700 bg-slate-900 hover:border-slate-500"
          }`}
        >
          <div className={`mx-auto mt-1.5 h-2 w-2 rounded-full ${statusDot}`} />
        </button>
      </div>

      {/* 内容卡片 */}
      <button
        onClick={() => onSelect(node)}
        className={`mb-4 flex-1 rounded-lg border p-3 text-left transition-all ${
          isSelected
            ? "border-slate-500 bg-slate-800/80 shadow-lg shadow-slate-900/50"
            : "border-slate-800/60 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-800/50"
        }`}
      >
        {/* 头部：版本标签 + 日期 + 漂移标识 */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded bg-slate-800 px-1.5 py-px text-[11px] font-medium text-slate-300">
            {node.change_type}
          </span>
          {node.effective_start && (
            <span className="text-[11px] text-slate-500">{node.effective_start}</span>
          )}
          {node.drift_score !== undefined && (
            <span className={`text-[11px] font-medium ${drift.color}`}>
              漂移 {node.drift_score.toFixed(3)}
            </span>
          )}
          {node.similarity_with_prev !== undefined && (
            <span className="text-[11px] text-slate-500">
              相似度 {(node.similarity_with_prev * 100).toFixed(1)}%
            </span>
          )}
          {node.status !== "有效" && (
            <span
              className={`rounded px-1.5 py-px text-[10px] font-medium ${
                node.status === "已废止"
                  ? "bg-red-500/15 text-red-400"
                  : node.status === "已修改"
                    ? "bg-amber-500/15 text-amber-400"
                    : "bg-sky-500/15 text-sky-400"
              }`}
            >
              {node.status}
            </span>
          )}
        </div>

        {/* 内容预览 */}
        <div className="mt-2 text-xs leading-relaxed text-slate-400">
          {node.text_preview}
        </div>

        {/* 特殊标记 */}
        {(node.lineage_chain[0]?.is_split || node.lineage_chain[0]?.is_merge) && (
          <div className="mt-1.5 flex items-center gap-1 text-[11px] text-slate-500">
            {node.lineage_chain[0].is_split && (
              <span className="inline-flex items-center gap-0.5 rounded bg-violet-500/15 px-1.5 py-px text-violet-400">
                <Split className="h-3 w-3" />
                拆分
              </span>
            )}
            {node.lineage_chain[0].is_merge && (
              <span className="inline-flex items-center gap-0.5 rounded bg-sky-500/15 px-1.5 py-px text-sky-400">
                <GitMerge className="h-3 w-3" />
                合并
              </span>
            )}
          </div>
        )}

        {/* 敏感词差异 */}
        <SensitiveWordDiff deltas={node.sensitive_deltas} />

        {/* 重大变更警告 */}
        {node.lineage_chain[0]?.has_critical_change && (
          <div className="mt-2 flex items-center gap-1 text-[11px] text-red-400">
            <AlertTriangle className="h-3 w-3" />
            检测到关键性变更
          </div>
        )}
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────
// 主组件
// ─────────────────────────────────────────────

interface DriftTimelineProps {
  nodes: DriftNode[];
  onSelectNode?: (node: DriftNode) => void;
  selectedNodeId?: string;
}

export default function DriftTimeline({ nodes, onSelectNode, selectedNodeId }: DriftTimelineProps) {
  const [selectedId, setSelectedId] = useState<string | undefined>(selectedNodeId);

  const handleSelect = useCallback(
    (node: DriftNode) => {
      setSelectedId(node.id);
      onSelectNode?.(node);
    },
    [onSelectNode]
  );

  if (nodes.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-slate-500">
        暂无血缘数据
      </div>
    );
  }

  return (
    <div className="space-y-1 py-2">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">立法变迁血缘链</h3>
        <span className="text-[11px] text-slate-500">{nodes.length} 个版本</span>
      </div>
      {nodes.map((node, i) => (
        <TimelineItem
          key={node.id}
          node={node}
          index={i}
          total={nodes.length}
          isSelected={selectedId === node.id}
          onSelect={handleSelect}
        />
      ))}
    </div>
  );
}
