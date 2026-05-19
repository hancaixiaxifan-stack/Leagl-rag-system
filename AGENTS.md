# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 项目概述

RAG 法律知识库系统，两个主要工作线：
1. **法律问答**：从 docx 文档构建知识库，向量检索 + BM25 + DeepSeek 大模型回答
2. **Co-Amendment Prediction（论文）**：20部中国法律、122K条文对的立法协调预测 benchmark，发表于 IEEE 格式论文

所有 Python 脚本必须通过项目 `.venv` 运行（`pip install -r requirements.txt` 后使用 `.venv/Scripts/python.exe`）。

## 常用命令

```bash
# 安装依赖
python -m pip install -r requirements.txt

# 构建索引（从 docx 文档重建知识库，含血缘发现）
python -m scripts.ingest

# 仅重建向量索引（已有 chunks.jsonl 时）
python -m scripts.build_vector_index

# 启动 API 服务
python -m scripts.serve

# 检查向量嵌入是否正常
python scripts/probe_embeddings.py

# 检查环境配置
python scripts/inspect_env.py

# 运行测试脚本（项目没有 pytest，所有测试都是直接运行的脚本）
python scripts/test_counterfactual.py        # 反事实模拟单元测试
python scripts/test_sample_ingest.py         # 血缘样本测试（单/双/多版本法律）
python scripts/test_lineage_one_law.py       # 公司法专项血缘测试，输出 Markdown 报告
python scripts/smoke_api.py                  # FastAPI TestClient 冒烟测试（需先构建索引）
python scripts/test_keyword_coverage.py      # 测试 keyword 捕获率提升

# 引用网络提取（生成/更新 reference_graph.json）
python scripts/extract_citations.py

# 全法律漂移分析
python scripts/analyze_all_laws_drift.py

# Prompt 压力测试
python scripts/prompt_stress_test.py

# Co-Amendment Benchmark（20部法律，122K条文对）
python scripts/multi_law_co_amendment_benchmark_v2.py   # 主 benchmark（5种方法 + hard subset）
python scripts/fusion_baseline.py                       # LightGBM LambdaRank 多源融合基线
python scripts/cross_chapter_reasoning_pilot.py         # LLM 推理 pilot（DeepSeek-V4-Pro, 120对）
python scripts/hard_subset_builder.py                   # 构建 3 维 hard subset
python scripts/cross_chapter_eval_builder.py            # 跨章节评估集构建

# 消融与验证
python scripts/ablation_factorial.py                    # 2×2 消融实验（刑法第234条）
python scripts/batch_evaluation.py                      # 批量评估（刑法/民航法/民法典）
python scripts/backtesting_validation.py                # 历史回溯验证

# 人工评估
python scripts/human_eval_4annotator.py                 # 4标注员 Fleiss' κ 分析
python scripts/generate_coamendment_annotation.py       # 生成新标注表（450对盲法设计）

# 论文图表生成
python scripts/generate_paper_figures.py                # 输出论文用 LaTeX 表格和统计数据
```

### 前端开发

```bash
cd frontend
npm install
npm run dev          # 开发服务器（http://localhost:3000）
npm run build        # 生产构建
npm run lint         # ESLint 检查
```

## 环境配置

复制 `.env.example` 为 `.env`，关键配置项：

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | 大模型回答（/ask、/counterfactual 需要） |
| `DEEPSEEK_BASE_URL` | 默认 `https://api.deepseek.com` |
| `DEEPSEEK_CHAT_MODEL` | 如 `deepseek-v4-pro` |
| `LOCAL_EMBED_MODEL` | 本地向量模型，默认 `BAAI/bge-small-zh-v1.5` |

完整配置见 `rag_contract/settings.py`。所有配置均通过 pydantic-settings 从 `.env` 读取（大写+下划线映射）。


**换本地 embedding 模型或重建索引前**：删除 `qdrant_data/` 后全量 `ingest`，避免向量维度不一致。

## 架构

```
law/                     # 原始 docx 文档（519个文件，371部法律）
data/
├── chunks.jsonl         # 分块后的文本（含 lineage_chain，53K chunks）
├── merged.xlsx          # Excel 索引（标题→施行日期/法律分类）
├── reference_graph.json # 跨法律引用网络（extract_citations.py 生成）
├── multi_law_amendments.json  # Co-Amendment GT：20部法律修正案记录
├── embeddings_small_fixed.npz # 预计算向量（bge-small-zh-v1.5, 384维）
├── article_ids_small_fixed.json  # 向量对应的条文 key 列表
├── co_amendment_gt.json  # 刑法 co-amendment 原始 GT
└── *_results.json       # 各类实验结果

experiments/
├── co_amendment/         # Co-Amendment benchmark 结果
├── annotation_final/     # 旧律师标注（4人×200对，验证 graph signal）
├── coamendment_annotation/  # 新律师标注（4人×450对，验证 label quality）
└── annotation/           # Round 1 标注原始数据

rag_contract/           # 核心库
├── docx_parse.py       # 解析 docx 为 paragraphs
├── chunking.py         # 按"第X条"分块，条内按款/项/段细分
├── lineage.py          # 自动语义血缘发现 + SensitiveWordDelta 分类
├── local_embed.py      # fastembed 本地向量生成（ONNX）
├── index.py            # Qdrant 向量库操作
├── retrieval.py        # HybridRetriever：向量检索 + BM25 融合
├── llm_client.py       # DeepSeek OpenAI 兼容 API（仅生成回答）
├── prompting.py        # system / user / counterfactual prompt 构建
├── domino.py           # Direction 3：跨法律引用网络分析（BFS 影响链）
├── counterfactual.py   # Direction 4：反事实模拟 + 方向注册表
└── settings.py         # 配置（.env 驱动）

app/main.py             # FastAPI 应用

frontend/               # Next.js 16 + React 19 前端
├── src/app/            # App Router 页面（ask/counterfactual/domino/drift/visualize）
├── src/components/     # shadcn/ui 组件 + vis-network 可视化 + echarts/recharts 图表
├── src/lib/            # 工具函数
└── AGENTS.md           # Next.js 16 agent 规则（版本有 breaking changes）

scripts/                # 构建脚本和测试脚本
```

## 关键设计

- **向量嵌入始终本地**：使用 fastembed + ONNX，不调用远程 API
- **LLM 仅负责生成**：DeepSeek chat completions，embedding 始终在本地
- **混合检索（Hybrid-On-Demand）**：向量 cosine similarity（权重 0.65）+ BM25 jieba 分词（权重 0.35），min-max 归一化后取 `final_top_n`（默认6条）。当向量检索最高分 ≥ `hybrid_confidence_threshold`（默认 0.75）时跳过 BM25，仅用向量结果
- **向量维度变更需重建**：换 embedding 模型或重建索引前必须删除 `qdrant_data/`
- **引用网络持久化**：`data/reference_graph.json` 由 `extract_citations.py` 生成，被 `DominoAnalyzer` 懒加载（单例模式）。`by_article` 键格式为 `《法名》第X条`，现在也包含 `《法名》整部法律`
- **服务启动预加载**：`@app.on_event("startup")` 初始化 Qdrant、HybridRetriever、DominoAnalyzer

## Co-Amendment Benchmark 设计

**标签**：弱监督（amendment co-occurrence），非严格 GT。两个条文在同一修正案中被修改即构成正例。已知噪声来自政策打包、偶然共修、缺失真阳性。

**评估协议**（`fusion_baseline.py`）：
- **FULL-DATA**：全部修正案训练+评估（与 retrieval characterization 一致，R@20 dense=25.1%）
- **LOAO**（Leave-One-Amendment-Out）：每个修正案轮流作测试集
- **TEMPORAL**（主要协议）：按日期排序，最新修正案作测试，模拟真实预测，防止 process 特征泄露

**Hard Subset**（3维，`hard_subset_builder.py`）：
- Cross-Chapter（CC）：不同章节 block 的条文对，移除结构信号
- Low Lexical Overlap（LO）：Jaccard 低于中位数的对
- Non-Neighbor Graph（NN）：无直接引用连边

**融合特征组**（`fusion_baseline.py` FEATURE_GROUPS）：
- Text: dense_sim, bm25_score, jaccard_sim
- Structure: same_chapter, chapter_dist, article_dist
- Citation: has_citation, shared_citation
- Process: theme_sim（修正案主题 Jaccard）, granularity_match, same_gran_type

**论文文件**：`papers/draft/main_coamendment.tex`（IEEE 格式），Figure 数据在 `docs/figures/`

## API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/ask` | 法律咨询问答（RAG 检索 + LLM 生成） |
| POST | `/drift_report` | 法律漂移报告（指定法律的漂移统计） |
| GET | `/drift_report/laws` | 返回所有法律列表 |
| POST | `/domino_impact` | 跨法律多米诺效应（某条文修订影响的下游法律）。`article_no` 支持传 `"整部法律"` |
| GET | `/domino_impact/stats` | 引用图全局统计（节点数、边数、法律数） |
| POST | `/counterfactual` | 反事实模拟（条文偏移波及的下游条文）。**仅支持具体条文**，`article_no="整部法律"` 会被校验拒绝 |
| GET | `/counterfactual/directions` | 返回支持的结构化方向列表 |
| GET | `/law_articles` | 返回某法律的所有条文号及内容摘要 |

服务启动：`python -m scripts.serve` → `http://127.0.0.1:8000`

## /ask 处理流程

1. `embed_query()` 将问题转为本地向量
2. `search()` Qdrant 向量检索 → `retriever.combine_scores()` BM25 融合排序
3. 按 `current_date` 分离现行有效版本与历史版本
4. `build_user_prompt()` + `chat_answer()` 生成带引用的回答
5. 返回 `answer` + `citations`（含 `lineage_chain`）

## 四个研究方向

| Direction | 功能 | 核心模块 | API |
|-----------|------|---------|-----|
| 1 | 自动语义血缘发现 | `lineage.py` | `/ask`（citation 含 `lineage_chain`） |
| 2 | 法律漂移量化 | `DriftService` in `app/main.py` | `/drift_report` |
| 3 | 跨法律多米诺效应 | `domino.py` | `/domino_impact` |
| 4 | 反事实模拟 | `counterfactual.py` | `/counterfactual` |

**Direction 1 血缘发现**：链式追溯，每个版本只与前一版本对比，`lineage_chain` 保留完整变迁历史（从新到旧）。`drift_score = 1 - similarity`，阈值 `<0.05` 几乎无变化，`0.05-0.3` 小幅，`0.3-0.7` 较大，`>0.7` 重大。

**Direction 2 漂移量化**：`DriftService` 懒加载 `chunks.jsonl` 计算统计。L1 语义漂移（drift_score）、L2 迁址（条文号变了内容几乎没变）、L3 重分配（同条文号内容实质替换）。

**Direction 3 多米诺效应**：`DominoAnalyzer` 加载 `reference_graph.json`，`get_impact_chain()` 执行 BFS（默认 depth=2），支持 `recursive=true`。

**Direction 4 反事实模拟**：`CounterfactualAnalyzer` 提取目标条文敏感词 → 方向解析（11 个结构化方向注册表）→ 沿引用链找含同类敏感词的下游候选 → LLM 深度分析。

## Chunk 结构

```python
@dataclass
class Chunk:
    doc_id: str
    doc_title: str
    article_no: str | None
    text: str
    effective_start: str | None   # 施行日期
    effective_end: str | None     # 失效日期（下一版本-1天）
    status: str                   # 有效/已修改/尚未生效/已废止
    law_category: str | None
    lineage_id: str | None        # 跨版本唯一 UID
    lineage_chain: list           # list[LineageStep]
    embed_model_version: str | None
```

## 法律版本管理

- 根据 `merged.xlsx` 映射（标题+公布日期→施行日期+法律分类）
- 版本按法律分组，组内按 `effective_start` 排序
- 后一版本起始日-1天即为前一版本 `effective_end`
- 状态推断：`effective_start > today` → 尚未生效，`effective_end < today` → 已修改/已废止

