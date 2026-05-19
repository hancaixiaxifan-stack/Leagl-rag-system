"use client";

import { useState, useCallback } from "react";
import type { SearchConfig } from "@/types";
import { Search, SlidersHorizontal, BookOpen } from "lucide-react";

interface SearchPanelProps {
  laws: string[];
  selectedLaw: string;
  onLawSelect: (law: string) => void;
  onSearch: (query: string, config: SearchConfig) => void;
  loading?: boolean;
}

export default function SearchPanel({
  laws,
  selectedLaw,
  onLawSelect,
  onSearch,
  loading = false,
}: SearchPanelProps) {
  const [query, setQuery] = useState("");
  const [config, setConfig] = useState<SearchConfig>({
    vectorWeight: 0.65,
    bm25Weight: 0.35,
    topN: 10,
    finalTopN: 6,
    hybridConfidenceThreshold: 0.75,
  });
  const [showAdvanced, setShowAdvanced] = useState(false);

  const handleSearch = useCallback(() => {
    if (!query.trim()) return;
    onSearch(query.trim(), config);
  }, [query, config, onSearch]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") handleSearch();
    },
    [handleSearch]
  );

  const updateWeight = useCallback(
    (field: "vectorWeight" | "bm25Weight", value: number) => {
      setConfig((prev) => {
        const other = field === "vectorWeight" ? "bm25Weight" : "vectorWeight";
        return { ...prev, [field]: value, [other]: parseFloat((1 - value).toFixed(2)) };
      });
    },
    []
  );

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4">
      {/* 标题 */}
      <div>
        <h2 className="text-sm font-medium text-slate-200">检索配置</h2>
        <p className="mt-0.5 text-[11px] text-slate-500">混合检索参数与法律选择</p>
      </div>

      {/* 法律选择 */}
      <div className="space-y-1.5">
        <label className="flex items-center gap-1.5 text-[11px] font-medium text-slate-400">
          <BookOpen className="h-3.5 w-3.5" />
          目标法律
        </label>
        <select
          value={selectedLaw}
          onChange={(e) => onLawSelect(e.target.value)}
          className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-slate-500 focus:outline-none"
        >
          <option value="">全部法律</option>
          {laws.map((law) => (
            <option key={law} value={law}>
              {law}
            </option>
          ))}
        </select>
      </div>

      {/* 检索输入 */}
      <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-slate-400">检索语句</label>
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入法律问题或关键词..."
            className="w-full rounded-md border border-slate-700 bg-slate-900 py-2 pl-3 pr-10 text-xs text-slate-200 placeholder:text-slate-600 focus:border-slate-500 focus:outline-none"
          />
          <button
            onClick={handleSearch}
            disabled={loading || !query.trim()}
            className="absolute right-1 top-1/2 -translate-y-1/2 rounded p-1.5 text-slate-400 hover:text-slate-200 disabled:opacity-40"
          >
            <Search className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* 高级设置开关 */}
      <button
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-1.5 text-[11px] text-slate-500 hover:text-slate-300"
      >
        <SlidersHorizontal className="h-3 w-3" />
        {showAdvanced ? "收起高级设置" : "展开高级设置"}
      </button>

      {/* 高级设置面板 */}
      {showAdvanced && (
        <div className="space-y-4 rounded-lg border border-slate-800 bg-slate-900/40 p-3"
        >
          {/* 向量权重 */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-[11px] text-slate-400">向量检索权重</label>
              <span className="text-[11px] font-mono text-slate-300">
                {(config.vectorWeight * 100).toFixed(0)}%
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={config.vectorWeight}
              onChange={(e) => updateWeight("vectorWeight", parseFloat(e.target.value))}
              className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-slate-300"
            />
            <div className="text-[10px] text-slate-600">语义相似度（cosine）</div>
          </div>

          {/* BM25 权重 */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-[11px] text-slate-400">BM25 权重</label>
              <span className="text-[11px] font-mono text-slate-300">
                {(config.bm25Weight * 100).toFixed(0)}%
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={config.bm25Weight}
              onChange={(e) => updateWeight("bm25Weight", parseFloat(e.target.value))}
              className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-slate-300"
            />
            <div className="text-[10px] text-slate-600">关键词匹配（jieba 分词）</div>
          </div>

          {/* Top N */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-[11px] text-slate-400">返回条数</label>
              <span className="text-[11px] font-mono text-slate-300">{config.finalTopN}</span>
            </div>
            <input
              type="range"
              min={1}
              max={20}
              step={1}
              value={config.finalTopN}
              onChange={(e) =>
                setConfig((prev) => ({ ...prev, finalTopN: parseInt(e.target.value) }))
              }
              className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-slate-300"
            />
          </div>
        </div>
      )}

      {/* 搜索按钮 */}
      <button
        onClick={handleSearch}
        disabled={loading || !query.trim()}
        className="mt-auto flex items-center justify-center gap-2 rounded-md bg-slate-100 px-4 py-2.5 text-xs font-medium text-slate-900 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? (
          <>
            <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-400 border-t-slate-700" />
            检索中...
          </>
        ) : (
          <>
            <Search className="h-3.5 w-3.5" />
            开始检索
          </>
        )}
      </button>
    </div>
  );
}
