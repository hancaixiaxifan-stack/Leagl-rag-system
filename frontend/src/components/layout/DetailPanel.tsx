"use client";

import type { DominoNode, DriftNode } from "@/types";
import { FileText, Calendar, AlertTriangle, Shield, Scale, Tag, Hash } from "lucide-react";

// ─────────────────────────────────────────────
// 常量
// ─────────────────────────────────────────────

const RISK_LABELS: Record<string, string> = {
  High: "高风险",
  Medium: "中风险",
  Low: "低风险",
  Potential: "潜在影响",
  Unknown: "未知",
};

const RISK_COLORS: Record<string, string> = {
  High: "text-red-400",
  Medium: "text-amber-400",
  Low: "text-emerald-400",
  Potential: "text-indigo-400",
  Unknown: "text-slate-400",
};

const STATUS_STYLES: Record<string, string> = {
  有效: "bg-emerald-500/15 text-emerald-400",
  已修改: "bg-amber-500/15 text-amber-400",
  已废止: "bg-red-500/15 text-red-400",
  尚未实施: "bg-sky-500/15 text-sky-400",
};

// ─────────────────────────────────────────────
// 子组件：信息行
// ─────────────────────────────────────────────

function InfoRow({
  icon,
  label,
  value,
  valueClass = "text-slate-200",
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="flex items-start gap-2 py-2">
      <div className="mt-0.5 shrink-0 text-slate-500">{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="text-[11px] text-slate-500">{label}</div>
        <div className={`mt-0.5 break-words text-xs ${valueClass}`}>{value}</div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// 子组件：Domino 节点详情
// ─────────────────────────────────────────────

function DominoNodeDetail({ node }: { node: DominoNode }) {
  return (
    <div className="space-y-1">
      <InfoRow
        icon={<Scale className="h-3.5 w-3.5" />}
        label="法律名称"
        value={node.law_title}
      />
      <InfoRow
        icon={<Hash className="h-3.5 w-3.5" />}
        label="条文编号"
        value={node.article_no}
      />
      <InfoRow
        icon={<AlertTriangle className="h-3.5 w-3.5" />}
        label="风险等级"
        value={
          <span className={`font-medium ${RISK_COLORS[node.risk_level] ?? RISK_COLORS.Unknown}`}>
            {RISK_LABELS[node.risk_level] ?? node.risk_level}
          </span>
        }
        valueClass=""
      />
      <InfoRow
        icon={<Tag className="h-3.5 w-3.5" />}
        label="节点类型"
        value={
          node.level === "trigger"
            ? "震中条文"
            : node.level === "direct"
              ? "直接引用"
              : "间接传导"
        }
      />
      {node.drift_score !== undefined && (
        <InfoRow
          icon={<AlertTriangle className="h-3.5 w-3.5" />}
          label="漂移分数"
          value={`${node.drift_score.toFixed(4)}`}
          valueClass={node.drift_score >= 0.2 ? "text-red-400 font-medium" : "text-amber-400 font-medium"}
        />
      )}
      {node.keyword && (
        <InfoRow
          icon={<Tag className="h-3.5 w-3.5" />}
          label="关键词"
          value={node.keyword}
        />
      )}
      {node.reference_text && (
        <InfoRow
          icon={<FileText className="h-3.5 w-3.5" />}
          label="引用内容"
          value={
            <div className="max-h-32 overflow-auto rounded bg-slate-900/60 p-2 text-[11px] leading-relaxed text-slate-400">
              {node.reference_text}
            </div>
          }
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// 子组件：Drift 节点详情
// ─────────────────────────────────────────────

function DriftNodeDetail({ node }: { node: DriftNode }) {
  const statusStyle = STATUS_STYLES[node.status] ?? "bg-slate-500/15 text-slate-400";

  return (
    <div className="space-y-1">
      <InfoRow
        icon={<Scale className="h-3.5 w-3.5" />}
        label="法律名称"
        value={node.law_title}
      />
      <InfoRow
        icon={<Hash className="h-3.5 w-3.5" />}
        label="条文编号"
        value={node.article_no}
      />
      <InfoRow
        icon={<Shield className="h-3.5 w-3.5" />}
        label="效力状态"
        value={
          <span className={`rounded px-1.5 py-px text-[11px] font-medium ${statusStyle}`}>
            {node.status}
          </span>
        }
        valueClass=""
      />
      {node.effective_start && (
        <InfoRow
          icon={<Calendar className="h-3.5 w-3.5" />}
          label="生效日期"
          value={node.effective_start}
        />
      )}
      {node.effective_end && (
        <InfoRow
          icon={<Calendar className="h-3.5 w-3.5" />}
          label="失效日期"
          value={<span className="text-red-400">{node.effective_end}</span>}
        />
      )}
      {node.drift_score !== undefined && (
        <InfoRow
          icon={<AlertTriangle className="h-3.5 w-3.5" />}
          label="漂移分数"
          value={`${node.drift_score.toFixed(4)}`}
          valueClass={node.drift_score >= 0.3 ? "text-red-400 font-medium" : node.drift_score >= 0.05 ? "text-amber-400" : "text-emerald-400"}
        />
      )}
      {node.similarity_with_prev !== undefined && (
        <InfoRow
          icon={<Tag className="h-3.5 w-3.5" />}
          label="前版本相似度"
          value={`${(node.similarity_with_prev * 100).toFixed(1)}%`}
        />
      )}
      <InfoRow
        icon={<FileText className="h-3.5 w-3.5" />}
        label="条文内容"
        value={
          <div className="max-h-48 overflow-auto rounded bg-slate-900/60 p-2 text-xs leading-relaxed text-slate-400">
            {node.text_preview}
          </div>
        }
      />

      {/* 敏感词差异 */}
      {node.sensitive_deltas.length > 0 && (
        <div className="mt-2 space-y-1.5 rounded-lg border border-slate-800 bg-slate-900/30 p-2">
          <div className="text-[11px] font-medium text-slate-500">敏感词差异</div>
          <div className="space-y-1">
            {node.sensitive_deltas.map((delta, i) => (
              <div key={i} className="text-[11px]">
                <span className="text-slate-300">「{delta.word}」</span>
                {delta.category_shifted && (
                  <span className="ml-1 text-slate-500">
                    {delta.old_category} → {" "}
                    <span className="font-medium text-emerald-400">{delta.new_category}</span>
                  </span>
                )}
                {delta.polarity_flipped && (
                  <span className="ml-1 rounded bg-red-500/15 px-1 py-px text-red-400">极性翻转</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// 主组件
// ─────────────────────────────────────────────

export interface DetailPanelData {
  type: "domino" | "drift";
  node: DominoNode | DriftNode;
}

interface DetailPanelProps {
  data?: DetailPanelData | null;
}

export default function DetailPanel({ data }: DetailPanelProps) {
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-slate-800 px-4 py-3">
        <h2 className="text-sm font-medium text-slate-200">详情面板</h2>
        <p className="mt-0.5 text-[11px] text-slate-500">点击图表节点查看详细信息</p>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {!data ? (
          <div className="flex h-48 flex-col items-center justify-center gap-2 text-slate-500">
            <FileText className="h-8 w-8 opacity-30" />
            <span className="text-xs">未选择节点</span>
            <span className="text-[11px] text-slate-600">点击拓扑图或时间轴节点查看详情</span>
          </div>
        ) : data.type === "domino" ? (
          <DominoNodeDetail node={data.node as DominoNode} />
        ) : (
          <DriftNodeDetail node={data.node as DriftNode} />
        )}
      </div>
    </div>
  );
}
