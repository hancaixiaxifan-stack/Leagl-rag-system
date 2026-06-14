"use client";

import { useState, useCallback } from "react";
import type { DriftNode, SensitiveDelta } from "@/types";
import { AlertTriangle, ArrowRight, GitMerge, Split } from "lucide-react";

const STATUS_COLOR_MAP: Record<string, string> = {
  有效: "bg-emerald-600",
  已修改: "bg-amber-600",
  已废止: "bg-red-600",
  尚未实施: "bg-sky-600",
};

const DRIFT_THRESHOLDS = {
  major: 0.7,
  moderate: 0.3,
  minor: 0.05,
};

function driftLabel(score?: number): { text: string; color: string } {
  if (score === undefined) return { text: "新增", color: "text-[#7c735f]" };
  if (score >= DRIFT_THRESHOLDS.major) return { text: "重大变更", color: "text-red-700" };
  if (score >= DRIFT_THRESHOLDS.moderate) return { text: "较大修订", color: "text-amber-700" };
  if (score >= DRIFT_THRESHOLDS.minor) return { text: "小幅调整", color: "text-yellow-700" };
  return { text: "几乎无变化", color: "text-emerald-700" };
}

function SensitiveWordDiff({ deltas }: { deltas: SensitiveDelta[] }) {
  if (deltas.length === 0) return null;

  return (
    <div className="mt-2 space-y-1.5">
      <div className="text-[11px] font-medium text-[#8a7f6c]">敏感词差异</div>
      <div className="flex flex-wrap gap-1.5">
        {deltas.map((delta, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 rounded-full border border-[#d8d0c1] bg-[#f8f6f1] px-2 py-0.5 text-[11px] text-[#5f574a]"
          >
            {delta.polarity_flipped ? (
              <>
                <span className="text-red-700 line-through decoration-red-400">{delta.word}</span>
                <ArrowRight className="h-3 w-3 text-[#8a7f6c]" />
                <span className="font-semibold text-emerald-700">{delta.word}</span>
                <span className="ml-0.5 rounded-full bg-red-50 px-1.5 py-px text-[10px] text-red-700">
                  极性翻转
                </span>
              </>
            ) : delta.category_shifted ? (
              <>
                <span className="line-through decoration-[#b8ad9a]">{delta.old_category}</span>
                <ArrowRight className="h-3 w-3 text-[#8a7f6c]" />
                <span className="font-semibold text-emerald-700">{delta.new_category}</span>
                <span className="ml-0.5">「{delta.word}」</span>
              </>
            ) : (
              <span>{delta.word}</span>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}

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
  const statusDot = STATUS_COLOR_MAP[node.status] ?? "bg-[#8a7f6c]";

  return (
    <div className="relative flex gap-4">
      {!isFirst && <div className="absolute left-[11px] top-0 h-full w-px -translate-y-1/2 bg-[#ded7ca]" />}
      {!isLast && <div className="absolute left-[11px] top-1/2 h-full w-px bg-[#ded7ca]" />}

      <div className="relative z-10 flex shrink-0 flex-col items-center pt-1">
        <button
          onClick={() => onSelect(node)}
          className={`h-6 w-6 rounded-full border-2 transition-all ${
            isSelected
              ? "border-[#1f3a5f] bg-[#fffefa] shadow-[0_0_0_4px_rgba(31,58,95,0.12)]"
              : "border-[#cfc5b5] bg-[#fffefa] hover:border-[#1f3a5f]"
          }`}
          aria-label={`选择 ${node.effective_start ?? node.change_type}`}
        >
          <div className={`mx-auto mt-1.5 h-2 w-2 rounded-full ${statusDot}`} />
        </button>
      </div>

      <button
        onClick={() => onSelect(node)}
        className={`mb-4 flex-1 rounded-md border p-3 text-left transition-[border-color,box-shadow,transform] duration-200 ${
          isSelected
            ? "border-[#1f3a5f] bg-[#fffefa] shadow-sm"
            : "border-[#e4ded3] bg-[#fffefa] hover:border-[#cfc5b5] hover:shadow-sm"
        }`}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-[#d8d0c1] bg-[#f7f3eb] px-2 py-px text-[11px] font-medium text-[#5f574a]">
            {node.change_type}
          </span>
          {node.effective_start && (
            <span className="text-[11px] text-[#8a7f6c]">{node.effective_start}</span>
          )}
          {node.drift_score !== undefined && (
            <span className={`text-[11px] font-medium ${drift.color}`}>
              漂移 {node.drift_score.toFixed(3)}
            </span>
          )}
          {node.similarity_with_prev !== undefined && (
            <span className="text-[11px] text-[#8a7f6c]">
              相似度 {(node.similarity_with_prev * 100).toFixed(1)}%
            </span>
          )}
        </div>

        <div className="mt-2 text-xs leading-relaxed text-[#5f574a]">{node.text_preview}</div>

        {(node.lineage_chain[0]?.is_split || node.lineage_chain[0]?.is_merge) && (
          <div className="mt-2 flex items-center gap-1 text-[11px] text-[#7c735f]">
            {node.lineage_chain[0].is_split && (
              <span className="inline-flex items-center gap-0.5 rounded-full border border-indigo-200 bg-indigo-50 px-2 py-px text-indigo-700">
                <Split className="h-3 w-3" />
                拆分
              </span>
            )}
            {node.lineage_chain[0].is_merge && (
              <span className="inline-flex items-center gap-0.5 rounded-full border border-sky-200 bg-sky-50 px-2 py-px text-sky-700">
                <GitMerge className="h-3 w-3" />
                合并
              </span>
            )}
          </div>
        )}

        <SensitiveWordDiff deltas={node.sensitive_deltas} />

        {node.lineage_chain[0]?.has_critical_change && (
          <div className="mt-2 flex items-center gap-1 text-[11px] text-red-700">
            <AlertTriangle className="h-3 w-3" />
            检测到关键性变更
          </div>
        )}
      </button>
    </div>
  );
}

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
    return <div className="flex h-64 items-center justify-center text-sm text-[#7c735f]">暂无血缘数据</div>;
  }

  return (
    <div className="space-y-1 py-2">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[#1f2933]">立法变迁血缘链</h3>
        <span className="text-[11px] text-[#8a7f6c]">{nodes.length} 个版本</span>
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
