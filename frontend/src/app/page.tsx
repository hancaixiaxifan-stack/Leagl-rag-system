import Link from "next/link";
import { Activity, GitBranch, MessageSquare, FlaskConical } from "lucide-react";

const cards = [
  {
    href: "/drift",
    title: "法律漂移分析",
    desc: "可视化展示法律条文在不同版本间的语义漂移量，红-黄-绿色标标识修订烈度",
    icon: Activity,
    color: "text-amber-400",
    bg: "bg-amber-400/10",
    border: "border-amber-400/20",
  },
  {
    href: "/domino",
    title: "多米诺效应",
    desc: "跨法律引用网络分析，追踪条文修订对下游法律的传导影响",
    icon: GitBranch,
    color: "text-sky-400",
    bg: "bg-sky-400/10",
    border: "border-sky-400/20",
  },
  {
    href: "/ask",
    title: "法律咨询",
    desc: "基于向量检索 + BM25 的智能法律问答，含版本对比和血缘解读",
    icon: MessageSquare,
    color: "text-emerald-400",
    bg: "bg-emerald-400/10",
    border: "border-emerald-400/20",
  },
  {
    href: "/counterfactual",
    title: "反事实模拟",
    desc: "立法仿真分析：如果某条文向特定方向偏移，会波及哪些下游条文",
    icon: FlaskConical,
    color: "text-violet-400",
    bg: "bg-violet-400/10",
    border: "border-violet-400/20",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-slate-100">法律分析仪器</h1>
        <p className="text-sm text-slate-400">
          RAG 合同法律系统可视化分析平台 — 四个深度研究方向的可视化呈现
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <Link
              key={card.href}
              href={card.href}
              className={`group flex items-start gap-4 rounded-lg border ${card.border} ${card.bg} p-5 transition-all hover:border-opacity-50`}
            >
              <div className={`shrink-0 rounded-md p-2 ${card.bg}`}>
                <Icon className={`h-5 w-5 ${card.color}`} />
              </div>
              <div className="space-y-1">
                <h2 className="text-sm font-medium text-slate-200 group-hover:text-white">
                  {card.title}
                </h2>
                <p className="text-xs leading-relaxed text-slate-400">
                  {card.desc}
                </p>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
