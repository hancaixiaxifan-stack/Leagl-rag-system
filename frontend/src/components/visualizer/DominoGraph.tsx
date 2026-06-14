"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { Network, type Options, type Node, type Edge } from "vis-network/standalone";
import type { DominoNode, DominoEdge } from "@/types";

// ─────────────────────────────────────────────
// 常量配置
// ─────────────────────────────────────────────

const RISK_COLOR_MAP: Record<string, string> = {
  High: "#b42318",
  Medium: "#b45309",
  Low: "#047857",
  Potential: "#4338ca",
  Unknown: "#1f3a5f",
};

const RISK_BG_MAP: Record<string, string> = {
  High: "#fff1f0",
  Medium: "#fff7e6",
  Low: "#ecfdf3",
  Potential: "#eef2ff",
  Unknown: "#f0f5fb",
};

const NODE_SIZE_MAP: Record<string, number> = {
  trigger: 32,
  direct: 22,
  indirect: 16,
};

const NODE_FONT_SIZE_MAP: Record<string, number> = {
  trigger: 14,
  direct: 11,
  indirect: 9,
};

/** 节点上限保护 */
const MAX_NODES = 1200;

// ─────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────

interface DominoGraphProps {
  nodes: DominoNode[];
  edges: DominoEdge[];
  onNodeClick?: (nodeId: string) => void;
  onNodeDoubleClick?: (nodeId: string) => void;
}

// ─────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────

function buildVisNodes(nodes: DominoNode[]): Node[] {
  return nodes.map((n) => ({
    id: n.id,
    label: n.label,
    shape: n.level === "trigger" ? "box" : "dot",
    size: NODE_SIZE_MAP[n.level] ?? 18,
    color: {
      background: RISK_BG_MAP[n.risk_level] ?? RISK_BG_MAP.Unknown,
      border: RISK_COLOR_MAP[n.risk_level] ?? RISK_COLOR_MAP.Unknown,
      highlight: {
        background: "#fffefa",
        border: "#1f3a5f",
      },
    },
    font: {
      size: NODE_FONT_SIZE_MAP[n.level] ?? 10,
      color: n.level === "trigger" ? "#1f2933" : "#394453",
      face: "system-ui, sans-serif",
      multi: "html",
    },
    borderWidth: n.level === "trigger" ? 3 : 1,
    borderWidthSelected: n.level === "trigger" ? 4 : 2,
    shadow: n.level === "trigger" ? { enabled: true, color: "rgba(31,58,95,0.18)", size: 14 } : { enabled: false },
    margin: n.level === "trigger" ? 10 : 6,
    // 透传原始数据以便事件回调使用
    data: n,
  }));
}

function buildVisEdges(edges: DominoEdge[]): Edge[] {
  return edges.map((e, i) => ({
    id: `edge-${i}`,
    from: e.from,
    to: e.to,
    color: {
      color: e.is_indirect
        ? "rgba(67,56,202,0.32)"
        : (RISK_COLOR_MAP[e.risk_level] ?? RISK_COLOR_MAP.Unknown),
      opacity: e.is_indirect ? 0.45 : 0.68,
    },
    width: e.is_indirect ? 1 : 1.6,
    dashes: e.is_indirect,
    arrows: { to: { enabled: true, scaleFactor: 0.6 } },
    smooth: { type: "continuous", roundness: 0.2 },
  }));
}

// ─────────────────────────────────────────────
// 组件
// ─────────────────────────────────────────────

export default function DominoGraph({ nodes, edges, onNodeClick, onNodeDoubleClick }: DominoGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const clickTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isOverLimit, setIsOverLimit] = useState(false);

  // 防抖的点击处理
  const debouncedClick = useCallback(
    (nodeId: string) => {
      if (clickTimeoutRef.current) {
        clearTimeout(clickTimeoutRef.current);
      }
      clickTimeoutRef.current = setTimeout(() => {
        onNodeClick?.(nodeId);
        clickTimeoutRef.current = null;
      }, 150);
    },
    [onNodeClick]
  );

  useEffect(() => {
    if (!containerRef.current || nodes.length === 0) return;

    // 节点上限保护
    let displayNodes = nodes;
    let displayEdges = edges;
    const overLimit = nodes.length > MAX_NODES;
    setIsOverLimit(overLimit);

    if (overLimit) {
      // 优先保留 trigger 和 direct，裁剪 indirect
      const priorityNodes = nodes.filter((n) => n.level !== "indirect");
      const indirectNodes = nodes.filter((n) => n.level === "indirect");
      const allowedIndirect = MAX_NODES - priorityNodes.length;
      displayNodes = [...priorityNodes, ...indirectNodes.slice(0, Math.max(0, allowedIndirect))];
      const allowedIds = new Set(displayNodes.map((n) => n.id));
      displayEdges = edges.filter((e) => allowedIds.has(e.from) && allowedIds.has(e.to));
    }

    const visNodes = buildVisNodes(displayNodes);
    const visEdges = buildVisEdges(displayEdges);

    const data = { nodes: visNodes, edges: visEdges };

    const options: Options = {
      layout: {
        improvedLayout: true,
      },
      physics: {
        enabled: true,
        solver: "forceAtlas2Based",
        forceAtlas2Based: {
          gravitationalConstant: -72,
          centralGravity: 0.005,
          springLength: 120,
          springConstant: 0.08,
          damping: 0.4,
          avoidOverlap: 0.5,
        },
        stabilization: {
          enabled: true,
          iterations: 800,
          updateInterval: 50,
        },
        adaptiveTimestep: true,
      },
      interaction: {
        hover: true,
        tooltipDelay: 200,
        zoomView: true,
        dragView: true,
        navigationButtons: false,
      },
      nodes: {
        borderWidth: 1,
        borderWidthSelected: 2,
        chosen: true,
      },
      edges: {
        color: { inherit: "from" },
        smooth: { enabled: true, type: "dynamic" },
      },
    };

    const network = new Network(containerRef.current, data, options);
    networkRef.current = network;

    network.on("click", (params) => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        if (typeof nodeId === "string") {
          debouncedClick(nodeId);
        }
      }
    });

    network.on("doubleClick", (params) => {
      // 双击时取消待执行的单击
      if (clickTimeoutRef.current) {
        clearTimeout(clickTimeoutRef.current);
        clickTimeoutRef.current = null;
      }
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        if (typeof nodeId === "string") {
          onNodeDoubleClick?.(nodeId);
        }
      }
    });

    return () => {
      if (clickTimeoutRef.current) {
        clearTimeout(clickTimeoutRef.current);
      }
      network.destroy();
      networkRef.current = null;
    };
  }, [nodes, edges, debouncedClick, onNodeDoubleClick]);

  return (
    <div className="relative h-full w-full">
      {isOverLimit && (
        <div className="absolute left-0 right-0 top-0 z-10 flex items-center justify-center">
          <div className="rounded-b-lg bg-amber-500/90 px-4 py-1.5 text-xs font-medium text-white shadow-lg">
            节点数超过 {MAX_NODES} 上限，已自动裁剪间接引用节点
          </div>
        </div>
      )}
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}
