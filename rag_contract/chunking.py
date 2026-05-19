from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Iterable

from .docx_parse import ParsedDocx


ARTICLE_RE = re.compile(r"^(第[一二三四五六七八九十百千万0-9]+条)\s*(.*)$")
ITEM_PAREN_RE = re.compile(r"^（([一二三四五六七八九十]+)）\s*(.*)$")
ITEM_CN_RE = re.compile(r"^([一二三四五六七八九十]+)、\s*(.*)$")
ITEM_NUM_RE = re.compile(r"^(\d{1,3})[\.、]\s*(.*)$")
SECTION_RE = re.compile(r"^([一二三四五六七八九十]+、)\s*(.*)$")
BRACKET_RE = re.compile(r"^（(.+?)）$")


@dataclass
class Chunk:
    doc_id: str # 文档ID
    doc_title: str # 文档标题
    doc_type: str | None # 文档类型
    jurisdiction: str | None # 管辖区类型（如：中国、中国-北京）
    publish_date: str | None  # 公布日期（文件名提取）
    source: str # 来源
    status: str  # "有效" | "已修改" | "尚未生效" | "已废止"

    article_no: str | None # 条款编号
    clause_no: str | None # 款号
    item_no: str | None # 项号

    para_start: int # 开始段索引
    para_end: int # 结束段索引
    text: str # 文本内容

    # 新增字段
    effective_start: str | None = None  # 施行日期（真正的生效日期）
    effective_end: str | None = None    # 失效日期（下一版本生效日-1天）（若为最后版本，则为9999-12-31）
    change_type: str | None = None       # "修订" | "修正" | "新编" | None
    law_category: str | None = None      # "法律" | "修正案" | "法律解释" | "有关法律问题和重大问题的决定（部分）"

    # 血缘相关字段（lineage.py 填充）
    lineage_id: str | None = None       # 跨版本唯一 UID
    lineage_chain: list = field(default_factory=list)  # 完整血缘链（list[dict]），从新到旧
    embed_model_version: str | None = None  # 生成向量时的模型版本

    def citation_label(self) -> str:
        base = f"《{self.doc_title}》"
        parts: list[str] = []
        if self.article_no:
            parts.append(self.article_no)
        if self.clause_no:
            parts.append(f"第{self.clause_no}款")
        if self.item_no:
            parts.append(f"（{self.item_no}）项")
        if parts:
            return base + " " + "".join(parts)
        return base + f" 第{self.para_start}段"

    def resolve_status(self, current_date: str) -> str:
        """根据查询日期动态计算 status（而非使用索引构建时的静态值）"""
        es = self.effective_start or ""
        ee = self.effective_end or "9999-12-31"
        if es and es > current_date:
            return "尚未生效"
        if self.effective_end and self.effective_end < current_date:
            return "已修改"
        return "有效"

    def citation_label_with_status(self) -> str:
        label = self.citation_label()
        status_suffix = {"有效": "", "已修改": "（已修改）", "尚未生效": "（尚未生效）", "已废止": "（已废止）"}
        return label + status_suffix.get(self.status, "")


def _doc_id_from_path(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _infer_doc_type_from_title(title: str, filename: str) -> str | None:
    s = title + " " + filename

    doc_types = [
        "条例", "规定", "办法", "解释", "纪要", "通知", "意见", "答复", "批复",
        "指导意见", "规则", "细则", "方案", "决定", "公告", "通报", "函", "报告",
        "请示", "批复", "议案", "命令", "指示", "公报", "章程", "公约", "协议"
    ]

    for key in doc_types:
        if key in s:
            return key

    if "最高人民法院" in s or "最高法" in s:
        return "最高法"
    if "最高人民检察院" in s or "最高检" in s:
        return "最高检"
    if "国务院" in s:
        return "国务院"
    if "全国人大常委会" in s or "全国人大" in s:
        return "全国人大"

    return None


def _infer_publish_date_from_filename(filename: str) -> str | None:
    m = re.search(r"(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])", filename)
    if not m:
        return None
    return m.group(0)


def _infer_change_type_from_bracket(bracket_text: str | None) -> str | None:
    if not bracket_text:
        return None
    if "修订" in bracket_text:
        return "修订"
    if "修正" in bracket_text:
        return "修正"
    if "通过" in bracket_text and "修订" not in bracket_text and "修正" not in bracket_text:
        return "新编"
    return None


def _extract_bracket_header(paragraphs: list) -> str | None:
    for p in paragraphs[:5]:
        m = BRACKET_RE.match(p.text.strip())
        if m:
            return m.group(1)
    return None


def chunk_docx(parsed: ParsedDocx, source: str = "法律法规数据库") -> list[Chunk]:
    filename = os.path.basename(parsed.path)
    doc_id = _doc_id_from_path(parsed.path)
    doc_type = _infer_doc_type_from_title(parsed.title, filename)
    publish_date = _infer_publish_date_from_filename(filename)
    bracket_text = _extract_bracket_header(parsed.paragraphs)
    change_type = _infer_change_type_from_bracket(bracket_text)

    jurisdiction = None
    jurisdictions = [
        "北京", "上海", "天津", "重庆",
        "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建", "江西",
        "山东", "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西",
        "甘肃", "青海", "台湾",
        "内蒙古", "广西", "西藏", "宁夏", "新疆",
        "香港", "澳门"
    ]

    for prov in jurisdictions:
        if prov in filename or prov in parsed.title:
            jurisdiction = prov
            break

    paras = parsed.paragraphs
    if not paras:
        return []

    has_article = any(ARTICLE_RE.match(p.text) for p in paras)
    if not has_article:
        return _chunk_no_article(parsed, doc_id, doc_type, jurisdiction, publish_date, source, change_type)

    return _chunk_by_article(parsed, doc_id, doc_type, jurisdiction, publish_date, source, change_type)


def _chunk_by_article(
    parsed: ParsedDocx,
    doc_id: str,
    doc_type: str | None,
    jurisdiction: str | None,
    publish_date: str | None,
    source: str,
    change_type: str | None,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    current_article: str | None = None
    current_article_title: str | None = None
    article_buf: list[tuple[int, str]] = []

    def flush_article_buf():
        nonlocal article_buf, current_article, current_article_title
        if not current_article or not article_buf:
            article_buf = []
            return
        sub = _split_article_into_items(current_article, current_article_title, article_buf)
        for (para_start, para_end, item_no, clause_no, text) in sub:
            chunks.append(
                Chunk(
                    doc_id=doc_id,
                    doc_title=parsed.title,
                    doc_type=doc_type,
                    jurisdiction=jurisdiction,
                    publish_date=publish_date,
                    source=source,
                    status="有效",
                    article_no=current_article,
                    clause_no=clause_no,
                    item_no=item_no,
                    para_start=para_start,
                    para_end=para_end,
                    text=text,
                    change_type=change_type,
                )
            )
        article_buf = []

    for p in parsed.paragraphs:
        m = ARTICLE_RE.match(p.text)
        if m:
            flush_article_buf()
            current_article = m.group(1)
            current_article_title = (m.group(2) or "").strip() or None
            article_buf.append((p.para_idx, p.text))
        else:
            if current_article:
                article_buf.append((p.para_idx, p.text))

    flush_article_buf()
    return chunks


def _split_article_into_items(
    article_no: str,
    article_title: str | None,
    article_buf: list[tuple[int, str]],
) -> list[tuple[int, int, str | None, str | None, str]]:
    header_prefix = article_no
    if article_title:
        header_prefix += f" {article_title}"

    lines = article_buf

    boundaries: list[tuple[int, str, str]] = []
    for i, (_, t) in enumerate(lines):
        stripped = t.strip()  # 去除前导/尾随空白，确保格式差异不影响匹配
        mm = ITEM_PAREN_RE.match(stripped)
        if mm:
            boundaries.append((i, "paren", mm.group(1)))
            continue
        mm = ITEM_CN_RE.match(stripped)
        if mm:
            boundaries.append((i, "cn", mm.group(1)))
            continue
        mm = ITEM_NUM_RE.match(stripped)
        if mm:
            boundaries.append((i, "num", mm.group(1)))
            continue

    def make_text(sub_lines: list[tuple[int, str]]) -> tuple[int, int, str]:
        para_start = sub_lines[0][0]
        para_end = sub_lines[-1][0]
        body = "\n".join(t for _, t in sub_lines)
        text = f"{header_prefix}\n{body}"
        return para_start, para_end, text

    if not boundaries:
        para_start, para_end, text = make_text(lines)
        return [(para_start, para_end, None, None, text)]

    out: list[tuple[int, int, str | None, str | None, str]] = []
    starts = [b[0] for b in boundaries]
    if starts[0] > 0:
        lead = lines[: starts[0]]
        para_start, para_end, text = make_text(lead)
        out.append((para_start, para_end, None, None, text))

    for bi, (idx, _kind, num) in enumerate(boundaries):
        next_idx = boundaries[bi + 1][0] if bi + 1 < len(boundaries) else len(lines)
        sub_lines = lines[idx:next_idx]
        para_start, para_end, text = make_text(sub_lines)
        out.append((para_start, para_end, num, None, text))

    return out


def _chunk_no_article(
    parsed: ParsedDocx,
    doc_id: str,
    doc_type: str | None,
    jurisdiction: str | None,
    publish_date: str | None,
    source: str,
    change_type: str | None,
) -> list[Chunk]:
    paras = parsed.paragraphs

    sec_starts: list[int] = []
    for i, p in enumerate(paras):
        if SECTION_RE.match(p.text) or ITEM_PAREN_RE.match(p.text) or ITEM_NUM_RE.match(p.text):
            sec_starts.append(i)
    sec_starts = sorted(set(sec_starts))

    chunks: list[Chunk] = []

    def emit(buf: list[tuple[int, str]]):
        if not buf:
            return
        para_start = buf[0][0]
        para_end = buf[-1][0]
        text = "\n".join(t for _, t in buf)
        chunks.append(
            Chunk(
                doc_id=doc_id,
                doc_title=parsed.title,
                doc_type=doc_type,
                jurisdiction=jurisdiction,
                publish_date=publish_date,
                source=source,
                status="有效",
                article_no=None,
                clause_no=None,
                item_no=None,
                para_start=para_start,
                para_end=para_end,
                text=text,
                change_type=change_type,
            )
        )

    if sec_starts:
        for si, start in enumerate(sec_starts):
            end = sec_starts[si + 1] if si + 1 < len(sec_starts) else len(paras)
            buf = [(p.para_idx, p.text) for p in paras[start:end]]
            emit(buf)
        return chunks

    buf: list[tuple[int, str]] = []
    cur_len = 0
    target = 1000
    hard_max = 1400
    for p in paras:
        t = p.text
        if buf and cur_len + len(t) > hard_max:
            emit(buf)
            buf = []
            cur_len = 0
        buf.append((p.para_idx, t))
        cur_len += len(t)
        if cur_len >= target:
            emit(buf)
            buf = []
            cur_len = 0
    emit(buf)
    return chunks
