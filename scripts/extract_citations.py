"""
跨法律引用提取脚本（Direction 3 - 多米诺效应检测的基础）

功能：
- 全量扫描 chunks.jsonl，提取所有跨法律引用
- 双向构建引用图（by_article 入度 + cites 出度）
- 输出 data/reference_graph.json

用法：
    python scripts/extract_citations.py            # 全量构建
    python scripts/extract_citations.py --dry-run  # 仅打印统计，不写文件
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


LAW_REF_RE = re.compile(r'《([^》]+)》')
ARTICLE_NO_RE = re.compile(r'第([一二三四五六七八九十百千零\d]+)条')
BENFA_RE = re.compile(r'本法第([一二三四五六七八九十百千零\d]+)条')
ARTICLE_RANGE_RE = re.compile(r'第([一二三四五六七八九十百千零\d]+)条至第([一二三四五六七八九十百千零\d]+)条')

# 常见法律简称列表（用于无书名号引用识别）
# 这些法律名在条文中可能被直接引用而不加《》
SHORT_LAW_NAMES = [
    '宪法', '刑法', '民法', '商法', '行政法', '诉讼法',
    '劳动法', '合同法', '公司法', '商标法', '专利法', '著作权法',
    '环保法', '税法', '证券法', '保险法', '银行法',
    '建筑法', '交通法', '教育法', '卫生法',
    '食品安全法', '药品管理法', '消费者权益保护法',
    '反垄断法', '反不正当竞争法', '广告法', '价格法',
    '统计法', '会计法', '审计法', '预算法',
    '政府采购法', '招标投标法', '拍卖法', '仲裁法',
    '律师法', '公证法', '监狱法', '警察法',
    '兵役法', '国防法', '国家安全法',
    '反间谍法', '反恐怖主义法', '网络安全法',
    '数据安全法', '个人信息保护法', '电子商务法',
    '道路交通安全法', '海上交通安全法', '铁路法',
    '民用航空法', '港口法', '航道法', '公路法',
    '特种设备安全法', '安全生产法', '矿山安全法',
    '职业病防治法', '消防法', '防震减灾法',
    '防洪法', '水法', '水土保持法', '矿产资源法',
    '煤炭法', '电力法', '石油天然气管道保护法',
    '可再生能源法', '节约能源法', '循环经济促进法',
    '环境影响评价法', '海洋环境保护法',
    '大气污染防治法', '水污染防治法', '土壤污染防治法',
    '固体废物污染环境防治法', '环境噪声污染防治法',
    '放射性污染防治法', '野生动物保护法', '森林法',
    '草原法', '畜牧法', '种子法',
    '进出境动植物检疫法', '动物防疫法',
    '农业法', '农村土地承包法', '农民专业合作社法',
    '渔业法', '海域使用管理法', '海岛保护法',
    '领海及毗连区法', '专属经济区和大陆架法',
    '国籍法', '出入境管理法', '护照法',
    '居民身份证法', '户口登记条例', '居住证暂行条例',
    '婚姻登记条例', '收养法', '继承法',
    '物权法', '担保法', '侵权责任法', '婚姻法',
    '家庭教育促进法', '未成年人保护法',
    '预防未成年人犯罪法', '妇女权益保障法',
    '老年人权益保障法', '残疾人保障法',
    '红十字会法', '慈善法',
    '集会游行示威法', '戒严法', '突发事件应对法',
    '传染病防治法', '疫苗管理法',
    '精神卫生法', '献血法',
    '人口与计划生育法', '母婴保健法',
    '中医药法', '体育法',
    '文物保护法', '非物质文化遗产法',
    '图书馆法', '电影产业促进法',
    '治安管理处罚法', '民事诉讼法', '刑事诉讼法',
    '行政诉讼法', '行政复议法', '国家赔偿法',
    '公务员法', '监察法', '法官法', '检察官法',
    '人民警察法',
]

# 构建无书名号法律引用的正则表达式
# 匹配模式："依据刑法第X条"、"根据民法规定"、"适用公司法"等
# 排除常见假阳性："方法"、"违法"、"司法"、"人民法"等
SHORT_LAW_REF_RE = re.compile(
    r'(?:依照|根据|按照|依据|适用|参照|援引|违反)'
    r'\s*('
    + '|'.join(SHORT_LAW_NAMES)
    + r')'
    r'(?:\s*第[一二三四五六七八九十百千零\d]+条|\s*规定|\s*明确|\s*要求|\s*禁止)?'
)

# 涉外法律冲突规范（国际私法）
CONFLICT_LAW_RE = re.compile(
    r'(?:适用|依照|根据)\s*'
    r'(外国法|法院地法|船旗国法|不动产所在地法|侵权行为地法|'
    r'共同经常居所地法|共同国籍国法|当事人经常居所地法|'
    r'一方当事人经常居所地法|最密切联系地法|受理案件的法院所在地法|'
    r'香港特别行政区法|澳门特别行政区法|台湾地区的法|'
    r'本法域外法|其他法域的法)'
)

# 引用关键词表：表示法律条文间强依赖关系的动词/短语
# 分为两类：
#   1. 规范引用词（明确法律依据关系）
#   2. 事实关联词（行为与条文的绑定关系，也构成强依赖）
CITE_KEYWORDS = [
    # === 规范引用词（核心法律依据）===
    '依照', '适用', '比照', '根据', '按照', '参照', '援引',
    # === 义务/责任绑定词（强依赖：行为被条文约束）===
    '违反', '触犯', '违背',
    # === 合规/符合性词（强依赖：必须符合某条文）===
    '符合', '不符合', '应当符合', '必须符合',
    # === 处置/执行词（强依赖：按某条文处理）===
    '依据', '按照', '遵照', '遵循', '执行',
    # === 权利/程序关联词 ===
    '享有', '行使', '基于', '鉴于',
    # === 常见法律短语 ===
    '规定禁止', '规定应当', '规定可以', '规定的',
    # === 主语关联词（"有本法第X条"、"对本法第X条"）===
    '有', '对', '本法',  # 兜底：至少标记出是本法引用
    # === 程序/行为动词（"办理本法第X条"、"载明本法第X条"）===
    '办理', '载明', '列明', '注明', '载列', '从事', '销售',
    # === 否定/排除关联词（"不受本法第X条"）===
    '不受', '不适用', '除外',
    # === 定义/说明关联词（"是指本法第X条"、"所称本法第X条"）===
    '是指', '指', '所称', '所指',
    # === 范围/包含关联词（"包括本法第X条"）===
    '包括', '包含', '与',
    # === 状态/判断关联词（"是否构成本法第X条"、"属于本法第X条"）===
    '属于', '不属于', '是否', '构成',
    # === 程序/处置动词（"审议本法第X条"、"设定本法第X条"）===
    '审议', '审定', '核定', '设定', '确定', '列入', '纳入',
    # === 连词/介词（"和本法第X条"）===
    '和', '及', '以及',
]

CN_DIGITS = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
             '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def clean_title(title: str) -> str:
    """清理 doc_title 中的所有空白字符"""
    return re.sub(r'\s+', '', title)


def cn_to_arabic(s: str) -> int:
    """中文/阿拉伯数字 → 阿拉伯整数。失败返回 -1"""
    if not s:
        return -1
    if s.isdigit():
        return int(s)

    # 处理"千百十个"结构（仅支持到千位，足够法律条文）
    total = 0
    section = 0  # 当前累积值

    i = 0
    while i < len(s):
        ch = s[i]
        if ch in CN_DIGITS:
            section = CN_DIGITS[ch]
        elif ch == '十':
            section = section * 10 if section else 10
            total += section
            section = 0
        elif ch == '百':
            section = section * 100 if section else 100
            total += section
            section = 0
        elif ch == '千':
            section = section * 1000 if section else 1000
            total += section
            section = 0
        elif ch == '零':
            pass
        else:
            return -1
        i += 1

    total += section
    return total if total > 0 else -1


def arabic_to_cn(num: int) -> str:
    """阿拉伯整数 → 中文数字（支持到千位）

    法律条文写法约定：
    - 10 → "十"，11 → "十一"（百位以下不带"一"前缀）
    - 110 → "一百一十"，115 → "一百一十五"（百位以上需"一十"前缀）
    """
    if num <= 0:
        return str(num)
    if num < 10:
        return '零一二三四五六七八九'[num]
    if num == 10:
        return '十'
    if num < 20:
        return '十' + arabic_to_cn(num - 10)
    if num < 100:
        tens = num // 10
        ones = num % 10
        return arabic_to_cn(tens) + '十' + (arabic_to_cn(ones) if ones else '')
    if num < 1000:
        h = num // 100
        rest = num % 100
        head = arabic_to_cn(h) + '百'
        if rest == 0:
            return head
        if rest < 10:
            return head + '零' + arabic_to_cn(rest)
        if rest < 20:
            # 百位以上 10..19 必须写"一十X"
            return head + '一十' + (arabic_to_cn(rest - 10) if rest > 10 else '')
        return head + arabic_to_cn(rest)
    return str(num)


def normalize_article_no(num_str: str) -> str:
    """归一化条文编号 → '第X条'（X 为中文数字）"""
    arabic = cn_to_arabic(num_str)
    if arabic <= 0:
        return f'第{num_str}条'
    return f'第{arabic_to_cn(arabic)}条'

# 归一化法律名称
def normalize_law_title(citing_text: str, title_lookup: dict) -> str | None:
    """归一化法律名称：
    1. 直接匹配（去空格后）
    2. 加"中华人民共和国"前缀再匹配
    """
    cleaned = clean_title(citing_text)    # 清理法律名称中的空格
    if cleaned in title_lookup:    # 直接匹配
        return title_lookup[cleaned]     # 返回直接匹配结果
    full = '中华人民共和国' + cleaned     # 加"中华人民共和国"前缀
    if full in title_lookup:     # 匹配加前缀的法律名称
        return title_lookup[full]       # 返回加前缀的法律名称
    return None     # 未找到匹配的法律名称

 # 查找引用关键词（如"适用"、"根据"等）
def find_keyword_before(text: str, pos: int, max_len: int = 25) -> str | None:
    """查找引用关键词

    从 pos 往前搜索 max_len 个字符，匹配 CITE_KEYWORDS 中的关键词。
    优先返回最长匹配（如"应当符合"优先于"符合"），避免短词覆盖长词。
    """
    start = max(0, pos - max_len)
    snippet = text[start:pos]

    # 优先匹配最长的关键词，避免短词误匹配
    matched = None
    matched_len = 0
    for kw in CITE_KEYWORDS:
        if kw in snippet and len(kw) > matched_len:
            matched = kw
            matched_len = len(kw)
    return matched

 # 从法律名称后的字符串中提取所有条文编号
def expand_article_list(tail_text: str) -> list[str]:
    """从法律名称后的字符串中提取所有条文编号
    支持：
    - 第X条
    - 第X条、第Y条、第Z条
    - 第X条至第Y条
    """
    range_match = ARTICLE_RANGE_RE.search(tail_text)
    if range_match:
        start = cn_to_arabic(range_match.group(1))
        end = cn_to_arabic(range_match.group(2))
        if start > 0 and end >= start and end - start < 50:
            return [f'第{arabic_to_cn(i)}条' for i in range(start, end + 1)]

    nums = ARTICLE_NO_RE.findall(tail_text)
    if nums:
        return [normalize_article_no(n) for n in nums]
    return []

 # 截断尾部，遇到《、句号等停止
def truncate_tail(text: str, start: int, max_len: int = 80) -> str:
    """从 start 开始截取尾部，遇到《、句号等停止"""
    tail = text[start:start + max_len]
    end_idx = len(tail)
    for stop in ['《', '。', '；', '\n']:
        idx = tail.find(stop)
        if 0 < idx < end_idx:
            end_idx = idx
    return tail[:end_idx]

 # 从单个 chunk 提取所有引用
def extract_from_chunk(chunk: dict, title_lookup: dict, current_full: str | None) -> list[dict]:     
    """从单个 chunk 提取所有引用"""
    text = chunk['text']    # 引用所在文本
    citations = []     # 引用列表

    # 模式一：提取"《XXX法》第X条"格式的引用（跨法律引用）
    for m in LAW_REF_RE.finditer(text):
        ref_name = m.group(1)
        if '法' not in ref_name:
            continue

        full_name = normalize_law_title(ref_name, title_lookup)
        if not full_name:
            continue

        tail = truncate_tail(text, m.end(), 80)
        articles = expand_article_list(tail)
        if not articles:
            continue

        keyword = find_keyword_before(text, m.start())
        # 如果前面没找到，检查条文号后面的文本（如"第十五条规定的人员"）
        if keyword is None:
            tail_snippet = tail[:30]
            for kw in ['规定', '情形', '条件', '所列', '所称', '所指', '适用']:
                if kw in tail_snippet:
                    keyword = f'...{kw}'
                    break
            # 如果后面直接跟顿号、逗号（如"第一百四十六条、第一百四十七条"），
            # 说明是并列引用，也标记出来
            if keyword is None:
                if '、' in tail_snippet[:10] or '，' in tail_snippet[:5]:
                    keyword = '并列引用'
        raw_snippet = (m.group(0) + tail).strip()[:120]

        for art_no in articles:
            citations.append({
                'cited_law': full_name,
                'cited_article': art_no,
                'raw': raw_snippet,
                'keyword': keyword,
            })

    # 模式一（扩展）：提取无书名号的法律简称引用
    # 例如："依据刑法第X条"、"根据民法规定"、"适用公司法"等
    for m in SHORT_LAW_REF_RE.finditer(text):
        ref_name = m.group(1)
        # 尝试归一化法律名称
        full_name = normalize_law_title(ref_name, title_lookup)
        if not full_name:
            # 尝试加"中华人民共和国"前缀
            full_name = normalize_law_title('中华人民共和国' + ref_name, title_lookup)
        if not full_name:
            continue

        # 提取条文编号（如果有"第X条"）
        tail = text[m.end():m.end() + 80]
        articles = expand_article_list(tail)

        keyword = find_keyword_before(text, m.start())
        if keyword is None:
            keyword = m.group(0)[:10]  # 使用匹配到的文本作为关键词

        raw_snippet = text[max(0, m.start() - 10): m.end() + 40]

        if articles:
            # 有具体条文编号
            for art_no in articles:
                citations.append({
                    'cited_law': full_name,
                    'cited_article': art_no,
                    'raw': raw_snippet,
                    'keyword': keyword,
                })
        else:
            # 没有具体条文编号（如"根据刑法规定"）
            # 记录为引用整部法律
            citations.append({
                'cited_law': full_name,
                'cited_article': '整部法律',
                'raw': raw_snippet,
                'keyword': keyword,
            })

    # 模式一（扩展）：涉外法律冲突规范
    # 例如："适用外国法"、"依照船旗国法"等
    for m in CONFLICT_LAW_RE.finditer(text):
        ref_name = m.group(1)
        keyword = find_keyword_before(text, m.start())
        if keyword is None:
            keyword = m.group(0)[:10]

        raw_snippet = text[max(0, m.start() - 10): m.end() + 30]

        citations.append({
            'cited_law': ref_name,
            'cited_article': '冲突规范',
            'raw': raw_snippet,
            'keyword': keyword,
        })

    # 模式二：提取"本法第X条"格式的引用（本法律内部条文引用）
    if current_full:
        for m in BENFA_RE.finditer(text):
            art_no = normalize_article_no(m.group(1))
            # BENFA_RE 匹配"本法第X条"，这里使用更宽松的窗口搜索关键词
            # 原因："本法第X条"通常出现在句中，前面的引用词可能距离较远
            # 例如："销售者销售本法第四十九条至第五十三条规定禁止销售的产品"
            #       这里"销售"距离"本法第四十九条"较远，需要更大的搜索窗口
            keyword = find_keyword_before(text, m.start(), max_len=40)
            # 如果前面没找到，尝试在"本法第X条"之后到句号/分号之间的文本中
            # 查找"规定"、"情形"等后续绑定词
            if keyword is None:
                tail_start = m.end()
                tail_end = min(len(text), tail_start + 30)
                tail_snippet = text[tail_start:tail_end]
                for kw in ['规定', '情形', '条件', '程序', '方式', '标准', '要求']:
                    if kw in tail_snippet:
                        keyword = f'本法...{kw}'
                        break
            # 兜底：如果前面是条文号开头（如"第六十五条 本法第六十一条"），标记为条首引用
            if keyword is None:
                prefix = text[max(0, m.start() - 20):m.start()]
                # 检查前面是否是条文号模式（如"第六十五条 "、"第六十五条\n"）
                if re.search(r'第[一二三四五六七八九十百千零\d]+条[\s\n]', prefix):
                    keyword = '条首引用'
            # 最终兜底：段落开头直接引用（前面是句号+换行或文本开头）
            if keyword is None:
                prefix = text[max(0, m.start() - 5):m.start()]
                if prefix.strip() == '' or prefix.endswith('。') or prefix.endswith('\n'):
                    keyword = '段首引用'
            citations.append({
                'cited_law': current_full,
                'cited_article': art_no,
                'raw': text[max(0, m.start() - 15): m.end() + 20],
                'keyword': keyword,
            })

    return citations    # 返回引用列表

 # 主函数，从 chunks.jsonl 提取引用
def main():
    parser = argparse.ArgumentParser(description='Extract cross-law citations from chunks.jsonl')
    parser.add_argument('--dry-run', action='store_true', help='Print stats only, do not write file')
    parser.add_argument('--chunks', default='data/chunks.jsonl')
    parser.add_argument('--output', default='data/reference_graph.json')
    args = parser.parse_args()

    chunks_path = Path(args.chunks)
    output_path = Path(args.output)

    chunks = []
    with open(chunks_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
    print(f'Loaded {len(chunks)} chunks')

    title_versions = defaultdict(list)
    for c in chunks:
        title = c['doc_title']
        cleaned = clean_title(title)
        title_versions[cleaned].append((c.get('effective_start') or '', title))
    # 去重：优先使用最新的版本号
    title_lookup = {}
    for cleaned, versions in title_versions.items():
        versions.sort(key=lambda x: x[0], reverse=True)
        title_lookup[cleaned] = versions[0][1]
    print(f'Unique laws (after dedup): {len(title_lookup)}')

    total_law_refs = 0
    matched_refs = 0
    unmatched_counter = defaultdict(int)
    short_law_refs = 0  # 无书名号引用计数
    conflict_law_refs = 0  # 冲突规范引用计数

    by_article = defaultdict(list)
    cites = defaultdict(list)
    laws_in_graph = set()
     # 记录所有法律名称
    # 遍历每个 chunk
    for chunk in chunks:
        text = chunk['text']     # 文本内容
        cleaned_chunk_title = clean_title(chunk['doc_title'])    # 清理法律名称
        current_full = title_lookup.get(cleaned_chunk_title)   # 获取法律名称

        # 统计《》书名号引用
        for m in LAW_REF_RE.finditer(text):
            ref_name = m.group(1)
            if '法' not in ref_name:
                continue
            total_law_refs += 1
            if normalize_law_title(ref_name, title_lookup):
                matched_refs += 1
            else:
                unmatched_counter[ref_name] += 1

        # 统计无书名号引用
        for m in SHORT_LAW_REF_RE.finditer(text):
            short_law_refs += 1

        # 统计冲突规范引用
        for m in CONFLICT_LAW_RE.finditer(text):
            conflict_law_refs += 1

        if not chunk.get('article_no'):
            continue

        citations = extract_from_chunk(chunk, title_lookup, current_full)    # 提取引用列表（包含被引用法律名称、文章号、引用文本、引用关键词）
        if not citations:
            continue
        # 生成引用边
        citing_law = chunk['doc_title']     # 引用法律名称
        citing_article = chunk['article_no']     # 引用文章号
        citing_key = f'《{citing_law}》{citing_article}'    # 引用法律名称+文章号
        # 遍历引用列表
        for cite in citations:      # 遍历引用列表
            cited_key = f"《{cite['cited_law']}》{cite['cited_article']}"     # 被引用法律名称+文章号
            # 生成引用边（被引用法律名称+文章号）
            by_article[cited_key].append({                # 生成引用边
                'citing_law': f'《{citing_law}》',     # 引用法律名称
                'citing_article': citing_article,     # 引用文章号
                'reference_text': cite['raw'],     # 引用文本
                'keyword': cite['keyword'],     # 引用关键词
            })
            # 生成引用边（引用法律名称+文章号）
            cites[citing_key].append({                # 生成引用边
                'cited_law': f"《{cite['cited_law']}》",     # 被引用法律名称
                'cited_article': cite['cited_article'],     # 被引用文章号
                'reference_text': cite['raw'],     # 引用文本
                'keyword': cite['keyword'],     # 引用关键词
            })
            laws_in_graph.add(cite['cited_law'])     # 添加被引用法律名称到图中
            laws_in_graph.add(citing_law)     # 添加引用法律名称到图中

    print(f'\n=== 匹配率统计 ===')
    print(f'《》书名号引用: {total_law_refs}')
    print(f'  └─ 匹配成功: {matched_refs}')
    print(f'  └─ 未匹配: {total_law_refs - matched_refs}')
    if total_law_refs:
        print(f'  └─ 匹配率: {matched_refs / total_law_refs * 100:.1f}%')
    print(f'无书名号引用（简称）: {short_law_refs}')
    print(f'涉外冲突规范引用: {conflict_law_refs}')
    print(f'跨法律引用总计: {total_law_refs + short_law_refs + conflict_law_refs}')

    if unmatched_counter:
        print(f'\n=== Top 20 unmatched references ===')
        for name, cnt in sorted(unmatched_counter.items(), key=lambda x: -x[1])[:20]:
            print(f'  {cnt}\t{name}')

    print(f'\n=== Graph stats ===')
    print(f'  Cited articles (by_article keys): {len(by_article)}')
    print(f'  Citing articles (cites keys): {len(cites)}')
    print(f'  Total citation edges: {sum(len(v) for v in by_article.values())}')
    print(f'  Total laws in graph: {len(laws_in_graph)}')

    if args.dry_run:
        print('\n[Dry-run] Skipping file write')
        return

    graph = {
        'by_article': dict(by_article),
        'cites': dict(cites),
        'laws': sorted(laws_in_graph),
        'version': '1.0',
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    print(f'\nReference graph saved to {output_path}')


if __name__ == '__main__':
    main()
