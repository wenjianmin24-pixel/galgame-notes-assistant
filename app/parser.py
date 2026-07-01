"""智能说话人解析器 — 自动嗅探多种 galgame 台词格式 + 编码乱码修复。

每种游戏的 Textractor 输出格式不同，这里按"特异性从高到低"依次尝试匹配：
  1. @name@「text」      — 恋獄～月狂病～ 等
  2. 【name】text         — 中文 galgame 标准
  3. 「name」text         — 说话人在括号内
  4. name「text」         — 短名字 +「」包裹的对话
  5. name「text           — 半截台词（无闭合」，RPG 打字机 / OCR 部分捕获）
  6. name：text / name: text — 冒号分隔
  7. 兜底：整串当正文，说话人 None

编码修复：Textractor 钩子有时用错 codepage 读游戏内存，导致
部分汉字变成生僻字（如"活泼"→"活頷"）。这里用多组编解码对
逆向修复，选中文率最高的结果。
"""

import re
from typing import Optional

# ── 编码修复 ────────────────────────────────────────────
# 常见错误：Textractor 用编码 A 读了游戏用编码 B 存的字节。
# 修复：把错误 Unicode → 用 A 回编码为 bytes → 用 B 重新解码。
_RECOVERY_PAIRS: list[tuple[str, str]] = [
    ("shift_jis",   "utf-8"),
    ("cp932",       "utf-8"),
    ("shift_jis",   "gbk"),
    ("cp932",       "gbk"),
    ("gbk",         "utf-8"),
    ("utf-8",       "shift_jis"),
]

# 判定乱码：如果文本中的"罕见汉字"占比超过阈值，可能被误解码过。
# 罕见汉字 ≈ 不在现代汉语常用范围内的 CJK 字符（生僻字、日文汉字等）。
_RARE_CJK = re.compile(
    r'[㐀-䶿一-鿿豈-﫿]'
)
# 常用汉字集合（用于判断文本是否编码正确）。用 frozenset 做 O(1) 成员测试。
_COMMON_CN = frozenset(
    '的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分'
    '对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十'
    '三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使'
    '点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全'
    '表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变'
    '条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料'
    '象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接'
    '知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任'
    '取据处队南给色光门即保治北造百规热领七海口东导器压志世金增争济阶'
    '油思术极交受联什认六共权收证改清己美再采转更单风切打白教速花带安'
    '场身车例真务具万每目至达走积示议声报斗完类八离华名确才科张信马节'
    '话米整空元况今集温传土许步群广石记需段研界拉林律叫且究观越织装影'
    '算低持音众书布复容儿须际商非验连断深难近矿千周委素技备半办青省列'
    '习响约支般史感劳便团往酸历市克何除消构府称太准精值号率族维划选标'
    '写存候毛亲快效斯院查江型眼王按格养易置派层片始却专状育厂京识适属'
    '圆包火住调满县局照参红细引听该铁价严首底液官德随病苏失尔死讲配女'
    '黄推显谈罪神艺呢席含企望密批营项防举球英氧势告李台落木帮轮破亚师'
    '围注远字材排供河态封另施减树溶怎止案言士均武固叶鱼波视仅费紧爱左'
    '章早朝害续轻服试食充兵源判护司足某练差致板田降黑犯负击范继兴似余'
    '坚曲输修故城夫够送笔船占右财吃富春职觉汉画功巴跟虽杂飞检吸助升阳'
    '互初创抗考投坏策古径换未跑留钢曾端责站简述钱副尽帝射草冲承独令限'
    '阿宣环双请超微让控州良轴找否纪益依优顶础载倒房突坐粉敌略客袁冷胜'
    '绝析块剂测丝协诉念陈仍罗盐友洋错苦夜刑移频逐靠混母短皮终聚汽村云'
    '哪既距卫停烈央察烧迅境若印洲刻括激孔搞甚室待核校散侵吧甲游久菜味'
    '旧模湖货损预阻毫普稳乙妈植息扩银语挥酒守拿序纸医缺雨吗针刘啊急唱'
    '误训愿审附获茶鲜粮斤孩脱硫肥善龙演父渐血欢械掌歌沙著刚攻谓盾讨晚'
    '粒乱燃矛乎杀药宁鲁贵钟煤读班伯香介迫句丰培握兰担弦蛋沉假穿执答乐'
    '准顺帽拿编印痛苏右异汽游够啊戏汽剧戏'
)


def _chinese_ratio(text: str) -> float:
    """文本中常用汉字的占比（越高越可能是正确解码的中文）。"""
    if not text:
        return 0.0
    cjk = len(_RARE_CJK.findall(text))
    if cjk == 0:
        return 0.0
    common = sum(1 for ch in text if ch in _COMMON_CN)
    return common / max(cjk, 1)


def _is_suspicious(text: str) -> bool:
    """检测文本是否有编码乱码嫌疑。"""
    if not text:
        return False
    cjk = _RARE_CJK.findall(text)
    if len(cjk) < 3:  # 太短无法判断
        return False
    ratio = _chinese_ratio(text)
    # 中文文本的常用字占比通常 > 30%；乱码文本罕见字多、常用字少
    return ratio < 0.15 and len(cjk) >= 3


def recover_encoding(text: str) -> str:
    """尝试修复 Textractor 编码乱码。

    始终用多组 (错误编码, 正确编码) 逆向恢复，选中文率最高的结果。
    只有恢复后的得分严格高于原文时才替换，否则原样返回。
    """
    if not text:
        return text

    best_text = text
    best_score = _chinese_ratio(text)

    for wrong_enc, right_enc in _RECOVERY_PAIRS:
        try:
            raw = text.encode(wrong_enc)
            recovered = raw.decode(right_enc)
            score = _chinese_ratio(recovered)
            if score > best_score:
                best_score = score
                best_text = recovered
        except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
            continue

    return best_text

# (正则, 是否剥离「」)
_PATTERNS: list[tuple[re.Pattern, bool]] = [
    # 1. @name@「text」
    (re.compile(r'^@([^@]+)@[「]((?:[^「」]|「[^「」]*」)*)[」]\s*$'), True),
    # 2. @name@text（无括号版）
    (re.compile(r'^@([^@]+)@(.+?)\s*$'), False),
    # 3. 【name】text
    (re.compile(r'^【([^】]+)】(.*)$'), False),
    # 4. 「name」text
    (re.compile(r'^[「]([^」]+)[」]\s*(.+)$'), False),
    # 5. name「text」— 短名字（≤8字符，不含特殊符号）+「」对话
    (re.compile(r'^([^\s「」@【】：:，,。\.！!？?、]{1,8})[「]((?:[^「」]|「[^「」]*」)*)[」]\s*$'), True),
    # 5b. name「text（半截台词：RPG 打字机逐字出现 / OCR 只抓到前半句，无闭合」）
    (re.compile(r'^([^\s「」@【】：:，,。\.！!？?、]{1,8})[「](.+)$'), False),
    # 6. name：text / name: text — 冒号分隔，短名字
    (re.compile(r'^([^\s：:]{1,8})[：:]\s*(.+)$'), False),
]


def parse_speaker(text: str) -> tuple[Optional[str], str]:
    """从台词文本中提取 (说话人, 正文)。

    自动嗅探格式；未识别到说话人时返回 (None, 原始文本)。
    正文中的「」引号会被剥离（仅在明确匹配到括号格式时）。
    """
    text = text.strip()
    if not text:
        return None, text

    for pattern, strip_quotes in _PATTERNS:
        m = pattern.match(text)
        if m:
            speaker = m.group(1).strip()
            body = m.group(2).strip() if pattern.groups >= 2 else text
            # 剥离最外层全角引号
            if strip_quotes:
                body = _strip_outer_quotes(body)
            # 说话人不应为空或太长
            if speaker and len(speaker) <= 16:
                return speaker, body or text
            # 匹配到了但 speaker 不合法 → 降级为无说话人
            return None, text

    return None, text


def _strip_outer_quotes(s: str) -> str:
    """剥离最外层的「」或『』配对引号。"""
    if (s.startswith('「') and s.endswith('」')) or \
       (s.startswith('『') and s.endswith('』')):
        return s[1:-1]
    return s


# ── OCR 文本清洗 ──────────────────────────────────────────

# 控制字符(0x00-1f, 7f-9f) + 零宽字符(U+200b-f) + BOM(U+feff) + ruby 标记(U+fff9-b)
_CONTROL_RE = re.compile('[\x00-\x1f\x7f-\x9f​-‏﻿￹-￻]')
_SPACE_RE = re.compile(r'[\s　]+')  # 普通空白 + 全角空格


def clean_ocr_text(text: str) -> str:
    """清洗 OCR 输出：去控制字符 / ruby 标记 / 折叠空白。"""
    if not text or not text.strip():
        return ""
    # 移除控制字符和 ruby 标记
    t = _CONTROL_RE.sub('', text)
    # 折叠连续空白为单个空格
    t = _SPACE_RE.sub(' ', t)
    return t.strip()


# ── Levenshtein 相似度 ────────────────────────────────────

def levenshtein_ratio(a: str, b: str) -> float:
    """两字符串的 Levenshtein 相似度 (0.0~1.0)，纯 Python。"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    # 让 a 是短串、b 是长串（减少内存分配）
    if len(a) > len(b):
        a, b = b, a
    na, nb = len(a), len(b)
    # 长度保护：OCR 单行不太可能 >500 字符，超长的跳过模糊比对
    if na > 500 or nb > 500:
        return 0.5
    prev = list(range(nb + 1))
    curr = [0] * (nb + 1)
    for i in range(1, na + 1):
        curr[0] = i
        ai = a[i - 1]
        for j in range(1, nb + 1):
            cost = 0 if ai == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev, curr = curr, prev
    return 1.0 - prev[nb] / max(na, nb, 1)
