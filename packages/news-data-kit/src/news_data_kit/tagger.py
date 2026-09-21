"""Rule-based news tagger. Deterministic, no LLM dependency.

Populates: language, markets, symbols, category, sentiment, urgency, tags.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .types import NewsItem

logger = logging.getLogger(__name__)

_RULES_DIR = Path(__file__).resolve().parent / "tagger_rules"

# ── Language detection ──

def _detect_language(text: str) -> str:
    """CJK vs Latin character weighted comparison.

    Each CJK char carries ~2x info density vs a Latin char; weight accordingly.
    Treats pure-CJK, pure-Latin, and mixed headlines by character counts rather
    than a flat CJK-ratio threshold (old: cjk > 10% \u2192 zh, over-triggered on
    mixed headlines with a few CJK brand names in otherwise-English text).
    """
    if not text:
        return "en"
    cjk = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if cjk == 0:
        return "en"
    if latin == 0:
        return "zh"
    return "zh" if cjk * 2 >= latin else "en"


# ── Category rules ──

_CATEGORY_RULES: dict[str, dict[str, list[str]]] = {
    "macro": {
        "zh": ["央行", "降息", "加息", "LPR", "MLF", "货币政策", "美联储", "FOMC", "CPI", "PPI", "PMI", "GDP",
               "就业", "失业", "通胀", "利率", "国债", "汇率", "外汇", "贸易战", "关税",
               "贸易摩擦", "地缘政治", "降准", "逆回购", "社融", "M2", "非农", "经济数据",
               "消费者信心", "零售数据", "进出口", "外贸"],
        "en": ["fed ", "fomc", "interest rate", "inflation", "cpi ", "ppi ", " gdp ", "employment", "monetary policy",
               "central bank", "treasury", "mortgage rate", "bond yield", "recession", "economic growth",
               "jobs report", "nonfarm", "unemployment", "tariff", "trade war", "debt ceiling", "fiscal",
               "rate cut", "rate hike", "stimulus", "quantitative", "deficit", "economic data",
               "geopolitic", "trade tension", "consumer confidence", "retail sales"],
    },
    "earnings": {
        "zh": ["财报", "业绩", "净利润", "营收", "季报", "年报", "中报", "盈利", "预告", "快报", "分红", "派息",
               "同比", "环比", "毛利率", "净利率", "营业收入", "归母净利", "业绩预增", "业绩预减",
               "业绩快报", "利润表", "收入增长", "毛利", "费用率", "经营利润"],
        "en": ["earnings", "revenue", "profit", "quarterly result", "annual report", "guidance", " eps ",
               "dividend", "beat expectations", "missed estimates", "sales growth", "margin",
               "delivery report", "deliveries", "shipments",
               "year-over-year", "quarter-over-quarter", "gross margin", "operating income", "net income",
               "revenue growth", "profit margin"],
    },
    "policy": {
        "zh": ["政策", "监管", "证监会", "银保监", "发改委", "国务院", "法规", "禁令", "制裁", "反垄断",
               "央行行长", "财政部", "工信部", "自然资源部", "碳中和", "环保", "双碳",
               "退市新规", "注册制", "科创板规则"],
        "en": ["regulation", " sec ", "policy", "sanction", " ban ", "compliance", "antitrust",
               "legislation", "congress", "white house", "executive order", "lawsuit", "probe",
               "investigation", "fine ", "penalty", "ruling",
               "carbon neutral", "climate policy", "regulatory"],
    },
    "commodity": {
        "zh": ["原油", "黄金", "白银", "铜价", "天然气", "大宗商品", "OPEC", "库存", "铁矿", "煤价", "油价",
               "有色金属", "稀土", "锂价", "钢铁", "期货", "农产品"],
        "en": ["crude oil", "gold ", "silver ", "copper ", "natural gas", "commodity", "opec", "oil price",
               "oil inventory", "brent ", " wti ", "iron ore", "coal ", "energy price", "fuel price",
               "metals ", "wheat ", "soybean",
               "lithium", "rare earth", "steel ", "futures "],
    },
    "sector": {
        "zh": ["板块", "行业", "半导体", "新能源", "医药", "消费", "科技股", "金融股", "地产", "军工", "芯片",
               "AI", "大模型", "机器人", "无人驾驶", "光伏", "储能", "CXO", "创新药",
               "人工智能", "智能驾驶", "新能源车", "算力", "数据中心"],
        "en": ["sector", "semiconductor", " ev ", "pharma", "tech stock", "fintech", "real estate",
               "biotech", "clean energy", "solar", "crypto", "blockchain", "banking sector",
               "chip ", "ai stock", "artificial intelligence", "cloud computing", "data center",
               "robotics", "autonomous driv", "large language model", " llm ", "generative ai"],
    },
    "company": {
        "zh": ["公司", "集团", "股份", "控股", "涨停", "跌停", "回购", "增持", "减持", "配股", "IPO", "上市",
               "研发", "产能", "扩产", "出海", "供应链", "订单"],
        "en": ["stock ", "shares ", "company", "corporation", "ipo ", "buyback", "acquisition",
               "merger", "takeover", "stake", "listing", "valuation", "market cap",
               " ceo ", "management", "restructur", "layoff", "hire",
               "supply chain", "production capacity", "expansion"],
    },
}

# ── Sentiment rules ──
# Weights: high-signal terms get weight 2, standard terms get weight 1.
# Neutral-context terms (e.g. 下跌 in a factual context) stay weight 1 to avoid
# over-triggering negative on routine price-move headlines.

_SENTIMENT_POSITIVE_ZH = [
    # High-signal (weight 2) — strong directional language
    ("利好", 2), ("大涨", 2), ("涨停", 2), ("超预期", 2), ("创新高", 2),
    ("暴涨", 2), ("大幅增长", 2), ("业绩超", 2), ("业绩大增", 2), ("净利润大增", 2),
    ("净利大增", 2), ("扭亏", 2), ("重大突破", 2), ("历史新高", 2),
    # Standard (weight 1) — positive but could appear in neutral context
    ("上涨", 1), ("增长", 1), ("突破", 1), ("反弹", 1), ("回暖", 1),
    ("利润增长", 1), ("营收增长", 1), ("同比增长", 1), ("环比增长", 1),
    ("回购", 1), ("增持", 1), ("战略合作", 1), ("签署协议", 1), ("达成合作", 1),
    ("开源", 1), ("发布新品", 1), ("推出新", 1), ("获批", 1), ("获得批准", 1),
    ("融资", 1), ("上市", 1), ("IPO", 1), ("获投", 1), ("获得融资", 1),
    ("订单", 1), ("中标", 1), ("获得订单", 1), ("新订单", 1),
    ("派息", 1), ("分红", 1), ("特别股息", 1),
    ("技术突破", 1), ("研发突破", 1), ("新技术", 1), ("重磅", 1),
    ("股价大涨", 1), ("股价飙升", 1), ("领涨", 1),
    ("目标价上调", 1), ("评级上调", 1), ("给予买入", 1), ("买入评级", 1),
    ("看好", 1), ("积极", 1), ("强劲", 1),
]

_SENTIMENT_NEGATIVE_ZH = [
    # High-signal (weight 2) — strong directional language
    ("利空", 2), ("暴跌", 2), ("跌停", 2), ("闪崩", 2), ("爆雷", 2),
    ("踩雷", 2), ("大幅亏损", 2), ("净亏损", 2), ("巨亏", 2),
    ("不及预期", 2), ("业绩大降", 2), ("业绩下滑", 2), ("业绩暴跌", 2),
    ("大幅下调", 2), ("评级下调", 2), ("目标价下调", 2),
    # Standard (weight 1) — negative but context-dependent
    ("下跌", 1), ("亏损", 1), ("违规", 1), ("退市", 1), ("暂停", 1),
    ("净卖出", 1), ("减持", 1), ("抛售", 1), ("做空", 1),
    ("裁员", 1), ("裁减", 1), ("大幅裁员", 1),
    ("处罚", 1), ("罚款", 1), ("被罚", 1), ("监管处罚", 1),
    ("调查", 1), ("涉嫌", 1), ("违规操作", 1),
    ("下调目标价", 1), ("下调评级", 1), ("给予卖出", 1), ("卖出评级", 1),
    ("看空", 1), ("风险", 1), ("警告", 1), ("危机", 1),
    ("股价大跌", 1), ("股价下跌", 1), ("跌幅", 1),
    ("业绩不佳", 1), ("收入下滑", 1), ("利润下降", 1),
]

_SENTIMENT_POSITIVE: dict[str, list[str]] = {
    "zh": [kw for kw, _ in _SENTIMENT_POSITIVE_ZH],
    "en": [
        "surge", "rally", "beat", "upgrade", "bullish", "growth", "outperform", "soar", "record high",
        "jump", "climb", "gain", "rise", "boost", "strong", "optimis", "recover", "breakthrough",
        "buyback", "buy rating", "overweight", "strong buy", "raised target", "partnership",
        "collaboration", "open source", "launch", "acquisition approved", "dividend",
        "exceed expectations", "exceeds expectations", "beat expectations", "beat estimates",
        "top estimates", "topped estimates", "all-time high", "fresh high", "new high",
        "advance", "advanced", "gains ", "rebound", "rebounded", "momentum", "accelerate",
        "robust", "solid", "stellar", "blowout", "upbeat", "upside", "upgrade to buy",
        "positive outlook", "raised guidance", "guidance raised", "raises guidance",
        "raised forecast", "record profit", "record revenue", "record sales",
        "expansion", "growth driver", "tailwind", "tailwinds", "breakout",
        "profitable", "well-positioned", "wins ", "winning", "approval granted",
        "fda approval", "milestone", "signed deal", "secured contract", "contract win",
        "strategic win", "leadership position", "market share gain", "share buyback",
    ],
}

_SENTIMENT_NEGATIVE: dict[str, list[str]] = {
    "zh": [kw for kw, _ in _SENTIMENT_NEGATIVE_ZH],
    "en": [
        "crash", "plunge", "downgrade", "bearish", "miss", "decline", "loss", "halt", "default",
        "drop", "fall", "sink", "tumble", "slump", "weak", "fear", "risk", "warning", "trouble",
        "layoff", "cut ", "slash", "sell rating", "underweight", "lowered target",
        "net sell", "investigation", "fine ", "penalty", "suspended",
        "missed expectations", "missed estimates", "fell short", "below estimates", "disappoint",
        "disappointing", "disappointed", "worst ", "lowest ", "record low", "52-week low",
        "bankruptcy", "bankrupt", "chapter 11", "restructur", "wind down", "shut down", "shutdown",
        "headwind", "headwinds", "concern", "concerned", "concerns", "uncertainty", "pressured",
        "under pressure", "struggle", "struggled", "struggling", "decelerate", "deceleration",
        "slowdown", "slowing", "contract", "contracted", "contraction",
        "lawsuit", "sued ", "probe ", "probed", "raid", "raided", "antitrust", "settlement",
        "recall", "recalled", "guidance cut", "cut guidance", "cuts guidance", "lowered guidance",
        "lowered forecast", "profit warning", "warn ", "warned", "warns ",
        "delist", "delisted", "halted trading", "trading halt", "crash landing",
        "oust", "ousted", "resign", "resigned", "departure", "fired ", "dismissed",
        "write-down", "writedown", "impairment", "goodwill impairment", "missed targets",
    ],
}


# ── Compound pair rules (both terms must appear in text, order-independent) ──
# Each entry: (term_a, term_b, sentiment, weight)
# Used for analyst actions where verb and object may not be adjacent.
_COMPOUND_PAIRS_ZH: list[tuple[str, str, str, int]] = [
    ("下调", "目标价", "negative", 2),
    ("下调", "评级", "negative", 2),
    ("上调", "目标价", "positive", 2),
    ("上调", "评级", "positive", 2),
    ("给予", "买入", "positive", 2),
    ("给予", "卖出", "negative", 2),
    ("净卖出", "亿", "negative", 1),
    ("净买入", "亿", "positive", 1),
]

_COMPOUND_PAIRS_EN: list[tuple[str, str, str, int]] = [
    ("raised", "target", "positive", 2),
    ("raised", "guidance", "positive", 2),
    ("raised", "forecast", "positive", 2),
    ("lowered", "target", "negative", 2),
    ("lowered", "guidance", "negative", 2),
    ("lowered", "forecast", "negative", 2),
    ("cut", "target", "negative", 2),
    ("cut", "guidance", "negative", 2),
    ("cut", "rating", "negative", 2),
    ("upgrade", "buy", "positive", 2),
    ("upgrade", "overweight", "positive", 2),
    ("downgrade", "sell", "negative", 2),
    ("downgrade", "underweight", "negative", 2),
    ("beat", "estimates", "positive", 2),
    ("beat", "expectations", "positive", 2),
    ("miss", "estimates", "negative", 2),
    ("miss", "expectations", "negative", 2),
    ("below", "estimates", "negative", 1),
    ("above", "estimates", "positive", 1),
    ("record", "high", "positive", 1),
    ("record", "low", "negative", 1),
    ("record", "profit", "positive", 2),
    ("record", "revenue", "positive", 2),
    ("announce", "buyback", "positive", 2),
    ("approved", "dividend", "positive", 1),
    ("warn", "profit", "negative", 2),
    ("profit", "warning", "negative", 2),
]


def _score_sentiment(text: str, lang: str) -> tuple[int, int]:
    """Return (positive_score, negative_score) using weighted keyword matching."""
    text_lower = text.lower()

    pos_score = 0
    neg_score = 0

    if lang == "zh":
        for kw, weight in _SENTIMENT_POSITIVE_ZH:
            if kw.lower() in text_lower:
                pos_score += weight
        for kw, weight in _SENTIMENT_NEGATIVE_ZH:
            if kw.lower() in text_lower:
                neg_score += weight
        # Compound pair scoring
        for term_a, term_b, sentiment, weight in _COMPOUND_PAIRS_ZH:
            if term_a in text_lower and term_b in text_lower:
                if sentiment == "positive":
                    pos_score += weight
                else:
                    neg_score += weight
    else:
        for kw in _SENTIMENT_POSITIVE.get("en", []):
            if kw.lower() in text_lower:
                pos_score += 1
        for kw in _SENTIMENT_NEGATIVE.get("en", []):
            if kw.lower() in text_lower:
                neg_score += 1
        for term_a, term_b, sentiment, weight in _COMPOUND_PAIRS_EN:
            if term_a in text_lower and term_b in text_lower:
                if sentiment == "positive":
                    pos_score += weight
                else:
                    neg_score += weight

    return pos_score, neg_score

# ── Urgency rules ──

_URGENCY_BREAKING: dict[str, list[str]] = {
    "zh": ["突发", "暴跌", "熔断", "暂停交易", "紧急", "重大", "闪崩", "爆雷"],
    "en": ["breaking", "halt", "circuit breaker", "flash crash", "emergency", "suspended"],
}

# ── Market inference from source ──

_SOURCE_MARKET_MAP: dict[str, list[str]] = {
    "BBC Business": ["US", "HK"],
    "Reuters Business": ["US", "HK"],
    "Financial Times": ["US", "HK"],
    "SCMP Business": ["HK"],
    "Nikkei Asia": ["HK"],
    "MarketWatch": ["US"],
    "WSJ Markets": ["US"],
    "CNBC": ["US"],
    "CNBC World": ["US", "HK"],
    "Investing.com": ["US", "HK"],
    "港府新闻": ["HK"],
    "HKEX": ["HK"],
    "财联社深度": ["CN"],
    "东方财富研报": ["CN"],
    "东方财富": ["CN"],
    "同花顺": ["CN"],
    "富途研报": ["HK", "CN"],
}

# ── Symbol patterns ──

_CN_SYMBOL_RE = re.compile(r'(\d{6})\.(SH|SZ|BJ)')
# HK codes: match "00700.HK", "0700.HK", "HK.00700", "HK0700" patterns
_HK_CODE_RE = re.compile(r'(?:(\d{4,5})\.HK|HK[.\s]?(\d{4,5}))', re.IGNORECASE)
# US ticker: candidate-then-filter approach.
# Step 1: bare 2-5 uppercase alpha word. 1-letter tickers (V/F/T/C/A) would
#         flood on common English words ("I", "A"); we rely on _COMPANY_SYMBOL_MAP
#         name entries for those cases.
# Step 2 (in tag_item): filter via _US_TICKER_UNIVERSE set (populated by init_tagger).
# Step 3: reject candidates in _US_TICKER_BLACKLIST even if universe-present.
_US_TICKER_RE = re.compile(r'\b([A-Z]{2,5})\b')

# Common uppercase acronyms that collide with real US tickers. Filtered regardless
# of universe membership to keep precision high (plan §3.2 reverse-cases).
_US_TICKER_BLACKLIST: frozenset[str] = frozenset({
    # Role titles
    "CEO", "CFO", "COO", "CTO", "CMO", "CIO", "CRO", "CHRO",
    "VP", "SVP", "EVP",
    # Econ indicators / finance jargon
    "CPI", "PPI", "GDP", "IPO", "SPAC", "LBO", "IRR", "NPV",
    "EPS", "ROE", "ROI", "ROIC", "YOY", "QOQ", "YTD", "ARR", "MRR",
    "EBITDA", "CAGR", "NAV", "AUM", "FCF",
    # Technology / AI
    "AI", "ML", "AR", "VR", "API", "IOT", "SAAS", "PAAS", "IAAS",
    "LLM", "GPT", "GPU", "CPU", "RAM", "SSD", "USB", "HTTP",
    # Regulatory / orgs / geos
    "US", "UK", "EU", "UN", "UAE", "NYSE", "SEC", "FTC", "DOJ",
    "FDA", "FAA", "OPEC", "NATO", "FED", "ECB", "BOJ", "BOE",
    "PBOC", "USDA", "DOD", "DOT", "CDC", "NIH", "IRS",
    # Market / country codes (may appear in "HK.00700" — the HK token boundary-matches)
    "HK", "CN", "JP", "KR", "SG", "TW", "IN",
    # Currencies / tokens
    "USD", "EUR", "JPY", "CNY", "HKD", "GBP", "RMB", "CHF", "CAD",
    "AUD", "NZD", "SGD", "INR", "KRW", "BTC", "ETH",
    # Time / period
    "FY", "H1", "H2",
    # Product / industry generic
    "ETF", "REIT", "ESG", "EV",
    # Common English words that the regex would catch
    "THE", "AND", "NEW", "TOP", "BIG", "FOR", "ALL", "OUT",
    "NOT", "WIN", "BID", "ASK", "BUY", "OLD", "GET", "SEE",
    "WAY", "DAY", "NOW", "TWO", "END", "OWN", "YOU", "HAS",
    "CAN", "HIS", "HER", "BUT", "ARE", "WAS", "WHO", "HOW",
    "ITS", "OUR", "ANY", "MAY", "JUN", "JUL", "AUG", "SEP",
    "OCT", "NOV", "DEC", "JAN", "FEB", "APR",
    # Broad business verbs / nouns (avoid false positives)
    "MD", "PM", "AM",
    # Ambiguous tickers — real US symbols but the acronym is used far more
    # often in news as non-company (political party, question word, common
    # noun). v0.5.1 tradeoff: drop from ticker path; consumers tracking
    # these specific companies should query by ticker directly.
    "KMT",   # Kennametal — collides with 国民党/Kuomintang political party
    "WAT",   # Waters Corp — too close to "what"
    "POST",  # Post Holdings — common noun
    "BILL",  # Bill.com — common noun / person name
    "TGT",   # Target Corp — common noun "target"
    "MARK",  # Remark Holdings — common name
    "HOPE",  # Hope Bancorp — common noun
    "GOOD",  # Gladstone Commercial — common adjective
    "FOUR",  # Shift4 Payments — common number word
    "SAVE",  # Spirit Airlines — common verb
    "PLAY",  # Dave & Buster's — common verb
    "LAKE",  # Lakeland Industries — common noun
    "FUN",   # Cedar Fair — common adjective
    "OPEN",  # Opendoor — common adjective
    "PATH",  # UiPath — common noun
    "WELL",  # Welltower — common word
    "SPOT",  # Spotify (SPOT variant) — common noun
    "GRAB",  # Grab Holdings — common verb
})

# ── Company name → symbol mapping (top ~80 names across markets) ──

_COMPANY_SYMBOL_MAP: dict[str, str] = {
    # US — English names
    "apple": "US.AAPL", "microsoft": "US.MSFT", "google": "US.GOOGL", "alphabet": "US.GOOGL",
    "amazon": "US.AMZN", "meta": "US.META", "facebook": "US.META",
    "nvidia": "US.NVDA", "tesla": "US.TSLA", "netflix": "US.NFLX",
    "amd": "US.AMD", "intel": "US.INTC", "broadcom": "US.AVGO",
    "salesforce": "US.CRM", "adobe": "US.ADBE", "oracle": "US.ORCL",
    "paypal": "US.PYPL", "uber": "US.UBER", "airbnb": "US.ABNB",
    "costco": "US.COST", "walmart": "US.WMT", "nike": "US.NKE",
    "coca-cola": "US.KO", "pepsi": "US.PEP", "mcdonald": "US.MCD",
    "boeing": "US.BA", "jpmorgan": "US.JPM", "goldman sachs": "US.GS",
    "berkshire": "US.BRK-B", "visa": "US.V", "mastercard": "US.MA",
    "disney": "US.DIS", "spotify": "US.SPOT", "snap": "US.SNAP",
    "palantir": "US.PLTR", "crowdstrike": "US.CRWD", "snowflake": "US.SNOW",
    "sam's club": "US.WMT",
    # US — Chinese names for cross-reference
    "苹果": "US.AAPL", "微软": "US.MSFT", "谷歌": "US.GOOGL",
    "亚马逊": "US.AMZN", "英伟达": "US.NVDA", "特斯拉": "US.TSLA",
    "英特尔": "US.INTC", "博通": "US.AVGO", "奈飞": "US.NFLX",
    # HK — Chinese names
    "腾讯": "HK.00700", "阿里巴巴": "HK.09988", "美团": "HK.03690",
    "小米": "HK.01810", "京东": "HK.09618", "百度": "HK.09888",
    "网易": "HK.09999", "快手": "HK.01024", "哔哩哔哩": "HK.09626",
    "中芯国际": "HK.00981", "比亚迪": "HK.01211", "理想汽车": "HK.02015",
    "蔚来": "HK.09866", "小鹏": "HK.09868", "吉利": "HK.00175",
    "安踏": "HK.02020", "李宁": "HK.02331", "海底捞": "HK.06862",
    "中国海洋石油": "HK.00883", "中国平安": "HK.02318", "汇丰": "HK.00005",
    "友邦保险": "HK.01299", "舜宇光学": "HK.02382", "翰森制药": "HK.03692",
    # HK — English names
    "tencent": "HK.00700", "alibaba": "HK.09988", "meituan": "HK.03690",
    "xiaomi": "HK.01810", "jd.com": "HK.09618", "baidu": "HK.09888",
    "netease": "HK.09999", "byd": "HK.01211", "hsbc": "HK.00005",
    "aia": "HK.01299", "li auto": "HK.02015", "nio": "HK.09866",
    "xpeng": "HK.09868", "geely": "HK.00175",
    # CN — Chinese names (top A-share)
    "贵州茅台": "CN.600519", "五粮液": "CN.000858", "宁德时代": "CN.300750",
    "中国平安": "CN.601318", "招商银行": "CN.600036", "工商银行": "CN.601398",
    "隆基绿能": "CN.601012", "比亚迪": "CN.002594", "中国中免": "CN.601888",
    "紫金矿业": "CN.601899", "中国神华": "CN.601088",
    # CN — English (for cross-language articles)
    "kweichow moutai": "CN.600519", "catl": "CN.300750",
    # Softbank / Japan
    "softbank": "US.SFTBY",
}


# ── Extended company name map + US ticker universe (populated via init_tagger) ──
# _extended_map: CJK names → symbol, matched via plain substring (no word
#   boundary concept in CJK). Safe because zh names are typically brand-unique
#   and not embedded in unrelated running text.
# _extended_map_en: Latin/lowercase names → symbol. Matched via a single
#   compiled \b-anchored alternation regex to avoid substring collisions
#   (e.g. "apa" inside "Japan", "dow" inside "slowdown" — plan §3.2).
_extended_map: dict[str, str] = {}
_extended_map_en: dict[str, str] = {}
_extended_map_en_regex: re.Pattern | None = None
_US_TICKER_UNIVERSE: set[str] = set()

# En names that collide with common English words and would produce false
# positives even with word-boundary matching. Extend as live eval surfaces
# issues. Kept lowercase to match the query path.
_EN_NAME_BLACKLIST: frozenset[str] = frozenset({
    # Generic single-word names that would FP on plain English text
    "strategy", "post", "target", "match", "tower", "service", "express",
    "central", "standard", "general", "plus", "global", "direct", "prime",
    "united", "american", "international", "continental", "pacific",
    "pro", "power", "premier", "world", "universal", "digital", "focus",
    "square", "vision", "nextgen", "nexgen", "signal", "summit", "horizon",
    # Surfaced by eval 2026-05-08
    "insight", "popular", "bullish", "driven", "kirby", "hope", "good",
    "play", "save", "well", "spot", "open", "path", "fun",
    "bill", "lake",
    # Short non-brand tokens that appear as nasdaq screener "name" after
    # normalization (often holding cos / shell tickers)
    "waters",  # too close to common noun
})


def _is_cjk(s: str) -> bool:
    return any('一' <= ch <= '鿿' for ch in s)


def init_tagger(
    hk_names: dict[str, str] | None = None,
    cn_names: dict[str, str] | None = None,
    us_names: dict[str, dict[str, str]] | None = None,
) -> int:
    """Load extended company name → symbol mappings at runtime.

    Args:
        hk_names: {code: name} e.g. {"00700": "腾讯控股"} — CJK, substring match
        cn_names: {code: name} e.g. {"600519": "贵州茅台"} — CJK, substring match
        us_names: {ticker_sym: {"en": str, "zh": str}} from MDK
                  us_universe.get_names(), e.g. {"US.AAPL": {"en": "apple", "zh": "苹果"}}.
                  Populates the US ticker universe (regex candidate filter),
                  CJK names (substring match), and Latin en names
                  (\\b-anchored regex).

    Returns:
        Total names loaded into the CJK extended map + Latin en map.
    """
    global _extended_map, _extended_map_en, _extended_map_en_regex, _US_TICKER_UNIVERSE
    new_cjk: dict[str, str] = {}
    new_en: dict[str, str] = {}
    new_universe: set[str] = set()

    if hk_names:
        for code, name in hk_names.items():
            name_lower = name.lower().strip()
            if len(name_lower) <= 1:
                continue
            symbol = f"HK.{str(code).zfill(5)}"
            if name_lower in _COMPANY_SYMBOL_MAP:
                continue
            if _is_cjk(name_lower):
                new_cjk[name_lower] = symbol
            # HK names are predominantly CJK; Latin entries (if any) skipped here
            # to avoid adding low-signal matches without a US universe context.

    if cn_names:
        for code, name in cn_names.items():
            name_lower = name.lower().strip()
            if len(name_lower) <= 1:
                continue
            symbol = f"CN.{code}"
            if name_lower in _COMPANY_SYMBOL_MAP:
                continue
            if _is_cjk(name_lower):
                new_cjk[name_lower] = symbol

    if us_names:
        for sym, names in us_names.items():
            if not isinstance(sym, str) or not sym.startswith("US."):
                continue
            ticker = sym[3:]
            if not ticker or not ticker.isalpha():
                continue
            new_universe.add(ticker.upper())
            if not isinstance(names, dict):
                continue
            for key in ("zh", "en"):
                name = str(names.get(key, "")).strip().lower()
                if len(name) < 2:
                    continue
                if name in _COMPANY_SYMBOL_MAP:
                    continue
                if _is_cjk(name):
                    # CJK zh name → substring match
                    new_cjk[name] = sym
                else:
                    # Latin en name — filter aggressively to minimize FP
                    if len(name) < 4:
                        continue  # "apa", "dow", "uts" too short
                    if name == ticker.lower():
                        continue  # en name = ticker; regex path handles it
                    if name in _EN_NAME_BLACKLIST:
                        continue  # common English word collision
                    new_en[name] = sym

    # Compile one \b-anchored alternation regex for all en names.
    # Sort by length desc so longest name wins on overlap
    # (e.g. "american airlines" preferred over "american").
    en_regex: re.Pattern | None = None
    if new_en:
        escaped = sorted((re.escape(n) for n in new_en), key=len, reverse=True)
        # Use non-capturing group; matching on lowercase text.
        en_regex = re.compile(r'\b(?:' + '|'.join(escaped) + r')\b')

    _extended_map = new_cjk
    _extended_map_en = new_en
    _extended_map_en_regex = en_regex
    _US_TICKER_UNIVERSE = new_universe
    logger.info(
        "init_tagger: %d CJK names, %d en names, %d US ticker universe",
        len(_extended_map), len(_extended_map_en), len(_US_TICKER_UNIVERSE),
    )
    return len(_extended_map) + len(_extended_map_en)


def _match_keywords(text: str, keywords: list[str]) -> list[str]:
    """Case-insensitive keyword matching. Returns matched keywords."""
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def tag_item(item: NewsItem) -> NewsItem:
    """Apply all tagging rules to a NewsItem. Modifies in place and returns it."""
    text = f"{item.title} {item.summary}"
    text_lower = text.lower()

    # Language
    item.language = _detect_language(text)
    lang = item.language

    # ── Symbols first (needed for market inference) ──
    symbols = set(item.symbols)
    for m in _CN_SYMBOL_RE.finditer(text):
        symbols.add(f"CN.{m.group(1)}")
    for m in _HK_CODE_RE.finditer(text):
        raw = m.group(1) or m.group(2)
        code = raw.zfill(5)
        symbols.add(f"HK.{code}")
    for name, sym in _COMPANY_SYMBOL_MAP.items():
        if name.lower() in text_lower:
            symbols.add(sym)
    # CJK extended map (substring match OK — no word boundaries in CJK)
    for name, sym in _extended_map.items():
        if name in text_lower:
            symbols.add(sym)
    # Latin en extended map (\b-anchored regex to avoid substring collisions)
    if _extended_map_en_regex is not None:
        for m in _extended_map_en_regex.finditer(text_lower):
            sym = _extended_map_en.get(m.group(0))
            if sym:
                symbols.add(sym)
    # US ticker: regex candidate → universe set lookup → blacklist rejection.
    # Requires init_tagger(us_names=...) to have populated _US_TICKER_UNIVERSE;
    # empty universe = feature-disabled, no matches are added.
    if _US_TICKER_UNIVERSE:
        for m in _US_TICKER_RE.finditer(text):
            candidate = m.group(1)
            if candidate in _US_TICKER_BLACKLIST:
                continue
            if candidate in _US_TICKER_UNIVERSE:
                symbols.add(f"US.{candidate}")
    item.symbols = sorted(symbols)

    # ── Markets (from symbols + source name + content keywords) ──
    markets = set(item.markets)
    # Infer from extracted symbols (highest signal)
    for sym in item.symbols:
        prefix = sym.split(".")[0]
        if prefix in ("HK", "CN", "US"):
            markets.add(prefix)
    # Source name mapping
    source_markets = _SOURCE_MARKET_MAP.get(item.source_name, [])
    if len(source_markets) <= 2:  # skip overly broad mappings like [HK,CN,US]
        markets.update(source_markets)
    # Content-based market inference
    if any(kw in text for kw in ["A股", "沪深", "创业板", "科创板", "上证", "深证",
                                  "A股市场", "两市", "北向资金", "沪指", "深指", "北交所"]):
        markets.add("CN")
    if any(kw in text for kw in ["港股", "恒生", "恒指", "HKEX",
                                  "港交所", "南向资金", "恒生科技", "中概股"]):
        markets.add("HK")
    if any(kw in text_lower for kw in ["wall street", "nasdaq", "s&p", "dow jones", "nyse",
                                        "federal reserve", "us stock", "american",
                                        "美股市场", "纳斯达克", "标普", "道指", "美债"]):
        markets.add("US")
    item.markets = sorted(markets)

    # Pin category tie-break order explicitly — decouple from dict insertion order.
    _CATEGORY_PRIORITY = ("macro", "earnings", "policy", "commodity", "sector", "company")
    best_cat = "general"
    best_count = 0
    for cat in _CATEGORY_PRIORITY:
        rules = _CATEGORY_RULES.get(cat, {})
        kws = rules.get(lang, []) + rules.get("zh" if lang == "en" else "en", [])
        matched = _match_keywords(text, kws)
        if len(matched) > best_count:
            best_count = len(matched)
            best_cat = cat
    item.category = best_cat

    # Sentiment (weighted scoring)
    pos_score, neg_score = _score_sentiment(text, lang)
    if pos_score > neg_score:
        item.sentiment = "positive"
    elif neg_score > pos_score:
        item.sentiment = "negative"
    else:
        item.sentiment = "neutral"

    # Urgency
    breaking_kws = _URGENCY_BREAKING.get(lang, [])
    if _match_keywords(text, breaking_kws):
        item.urgency = "breaking"

    # Tags (collect all matched category keywords as free tags)
    all_tags = set(item.tags)
    for rules in _CATEGORY_RULES.values():
        kws = rules.get(lang, [])
        all_tags.update(_match_keywords(text, kws))
    item.tags = sorted(all_tags)

    return item


def tag_batch(items: list[NewsItem]) -> list[NewsItem]:
    """Tag a batch of items."""
    return [tag_item(item) for item in items]
