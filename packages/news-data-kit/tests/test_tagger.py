"""Tests for rule-based tagger."""

from datetime import datetime

from news_data_kit.tagger import _detect_language, tag_item
from news_data_kit.types import NewsItem


def _make_item(title: str, summary: str = "", source_name: str = "Test") -> NewsItem:
    return NewsItem(
        item_id="test", source_type="rss", source_name=source_name,
        title=title, url="https://test.com",
        published_at=datetime.now(), fetched_at=datetime.now(),
        summary=summary,
    )


def test_detect_language_chinese():
    assert _detect_language("美联储加息25个基点") == "zh"


def test_detect_language_english():
    assert _detect_language("Fed raises rates by 25 basis points") == "en"


def test_detect_language_mixed():
    # Mostly English with some CJK
    assert _detect_language("The S&P 500 rose 2%") == "en"


def test_category_macro_zh():
    item = tag_item(_make_item("央行宣布降息25个基点，LPR同步下调"))
    assert item.category == "macro"


def test_category_macro_en():
    item = tag_item(_make_item("Fed raises interest rate by 25bp, inflation remains elevated"))
    assert item.category == "macro"


def test_category_earnings():
    item = tag_item(_make_item("腾讯Q3财报净利润超预期增长30%"))
    assert item.category == "earnings"


def test_category_policy():
    item = tag_item(_make_item("证监会发布新规加强监管力度"))
    assert item.category == "policy"


def test_category_commodity():
    item = tag_item(_make_item("国际原油价格突破100美元，OPEC减产协议延长"))
    assert item.category == "commodity"


def test_category_general_fallback():
    item = tag_item(_make_item("Today the weather is nice"))
    assert item.category == "general"


def test_sentiment_positive():
    item = tag_item(_make_item("市场大涨，多只个股涨停，反弹强劲"))
    assert item.sentiment == "positive"


def test_sentiment_negative():
    item = tag_item(_make_item("暴跌！多只股票跌停，市场恐慌"))
    assert item.sentiment == "negative"


def test_sentiment_neutral():
    item = tag_item(_make_item("Today is a regular trading day"))
    assert item.sentiment == "neutral"


def test_urgency_breaking():
    item = tag_item(_make_item("突发：某上市公司暂停交易"))
    assert item.urgency == "breaking"


def test_urgency_normal():
    item = tag_item(_make_item("Weekly market review"))
    assert item.urgency == "normal"


def test_market_from_source():
    item = tag_item(_make_item("Some news", source_name="SCMP Business"))
    assert "HK" in item.markets


def test_market_from_content():
    item = tag_item(_make_item("A股今日大涨，沪深两市成交超万亿"))
    assert "CN" in item.markets


def test_symbol_extraction_cn():
    item = tag_item(_make_item("关注600519.SH贵州茅台最新动态"))
    assert "CN.600519" in item.symbols


def test_symbol_extraction_hk_dot_suffix():
    """00700.HK format"""
    item = tag_item(_make_item("腾讯00700.HK季度业绩超预期"))
    assert "HK.00700" in item.symbols


def test_symbol_extraction_hk_prefix():
    """HK.00700 format"""
    item = tag_item(_make_item("关注HK.00700腾讯控股"))
    assert "HK.00700" in item.symbols


def test_symbol_extraction_hk_4digit():
    """4-digit code zero-padded: 0700.HK → HK.00700"""
    item = tag_item(_make_item("Tencent 0700.HK reported strong earnings"))
    assert "HK.00700" in item.symbols


def test_symbol_extraction_hk_no_bare_digits():
    """Bare 5-digit numbers should NOT match as HK codes (too many false positives)"""
    item = tag_item(_make_item("公司员工12345人，利润50000万"))
    assert not any(s.startswith("HK.") for s in item.symbols)


def test_tags_populated():
    item = tag_item(_make_item("央行降息，LPR下调，货币政策宽松"))
    assert len(item.tags) > 0
    assert "央行" in item.tags or "降息" in item.tags


# ── Symbol → Market inference ──

def test_market_inferred_from_hk_symbol():
    """HK symbol should auto-tag HK market."""
    item = tag_item(_make_item("惠誉降美团(03690.HK)信贷评级展望至负面"))
    assert "HK.03690" in item.symbols
    assert "HK" in item.markets


def test_market_inferred_from_cn_symbol():
    """CN symbol should auto-tag CN market."""
    item = tag_item(_make_item("关注600519.SH贵州茅台最新动态"))
    assert "CN" in item.markets


def test_market_inferred_from_company_name():
    """Company name match should infer both symbol and market."""
    item = tag_item(_make_item("腾讯发布最新季报", source_name="富途资讯"))
    assert "HK.00700" in item.symbols
    assert "HK" in item.markets


def test_futu_source_no_blanket_market():
    """富途资讯 should NOT blindly tag all 3 markets."""
    item = tag_item(_make_item("今天天气不错", source_name="富途资讯"))
    assert item.markets == []  # no market signal at all


def test_extended_market_keywords_cn():
    item = tag_item(_make_item("北向资金大幅流入，两市成交万亿"))
    assert "CN" in item.markets


def test_extended_market_keywords_hk():
    item = tag_item(_make_item("恒生科技指数大涨，港交所交投活跃"))
    assert "HK" in item.markets


def test_extended_market_keywords_us():
    item = tag_item(_make_item("纳斯达克创新高，美债收益率回落"))
    assert "US" in item.markets


# ── Extended name map ──

def test_init_tagger_loads_hk_names():
    from news_data_kit import tagger as tagger_mod
    count = tagger_mod.init_tagger(hk_names={"00388": "香港交易所", "01833": "平安好医生"})
    assert count >= 2
    assert "香港交易所" in tagger_mod._extended_map


def test_extended_map_matches_in_text():
    from news_data_kit.tagger import init_tagger
    init_tagger(hk_names={"00388": "香港交易所"})
    item = tag_item(_make_item("香港交易所宣布新政策"))
    assert "HK.00388" in item.symbols
    assert "HK" in item.markets
    # Clean up
    init_tagger()


def test_init_tagger_loads_cn_names():
    from news_data_kit import tagger as tagger_mod
    count = tagger_mod.init_tagger(cn_names={"600030": "中信证券", "002230": "科大讯飞"})
    assert count >= 2
    assert "中信证券" in tagger_mod._extended_map


def test_cn_extended_map_matches_in_text():
    from news_data_kit.tagger import init_tagger
    init_tagger(cn_names={"600030": "中信证券"})
    item = tag_item(_make_item("中信证券发布年度业绩报告"))
    assert "CN.600030" in item.symbols
    assert "CN" in item.markets
    init_tagger()


def test_init_tagger_loads_both_hk_and_cn():
    from news_data_kit import tagger as tagger_mod
    count = tagger_mod.init_tagger(
        hk_names={"00388": "香港交易所"},
        cn_names={"600030": "中信证券"},
    )
    assert count >= 2
    assert "香港交易所" in tagger_mod._extended_map
    assert "中信证券" in tagger_mod._extended_map
    tagger_mod.init_tagger()


# ── Sentiment: expanded Chinese financial keywords ──

def test_sentiment_open_source_positive():
    """开源宣布类标题应识别为 positive"""
    item = tag_item(_make_item("腾讯云宣布开源OpenAI、Manus同款Agent底座"))
    assert item.sentiment == "positive"


def test_sentiment_net_sell_negative():
    """南向资金净卖出 → negative"""
    item = tag_item(_make_item("南向资金净卖出腾讯逾5亿港元"))
    assert item.sentiment == "negative"


def test_sentiment_earnings_beat_positive():
    """业绩超预期+净利润大增 → positive"""
    item = tag_item(_make_item("腾讯业绩超预期，净利润大增30%"))
    assert item.sentiment == "positive"


def test_sentiment_regulatory_fine_negative():
    """监管处罚+暴跌 → negative"""
    item = tag_item(_make_item("腾讯遭遇监管处罚，股价暴跌8%"))
    assert item.sentiment == "negative"


def test_sentiment_strategic_cooperation_positive():
    """战略合作 → positive"""
    item = tag_item(_make_item("腾讯与字节跳动战略合作，共同开发AI产品"))
    assert item.sentiment == "positive"


def test_sentiment_buyback_positive():
    """回购 → positive"""
    item = tag_item(_make_item("腾讯回购股份，金额达50亿港元"))
    assert item.sentiment == "positive"


def test_sentiment_layoff_negative():
    """裁员 → negative"""
    item = tag_item(_make_item("腾讯宣布裁员，多个部门受影响"))
    assert item.sentiment == "negative"


def test_sentiment_revenue_growth_positive():
    """同比增长 → positive"""
    item = tag_item(_make_item("腾讯Q3财报出炉，收入同比增长11%"))
    assert item.sentiment == "positive"


def test_sentiment_target_price_cut_negative():
    """机构下调XXX目标价 (compound pair) → negative"""
    item = tag_item(_make_item("机构下调腾讯目标价至350港元"))
    assert item.sentiment == "negative"


def test_sentiment_target_price_raise_positive():
    """机构上调XXX目标价 (compound pair) → positive"""
    item = tag_item(_make_item("机构上调腾讯目标价至500港元"))
    assert item.sentiment == "positive"


def test_sentiment_rate_cut_not_negative():
    """央行降息下调LPR — macro news, should be neutral (not stock-negative)"""
    item = tag_item(_make_item("央行宣布降息下调LPR25基点"))
    # Acceptable: neutral or positive (rate cut is positive for stocks), but NOT negative
    assert item.sentiment != "negative"


def test_sentiment_holding_increase_positive():
    """增持 → positive"""
    item = tag_item(_make_item("大股东增持美团200万股，彰显信心"))
    assert item.sentiment == "positive"


def test_sentiment_reduce_holding_negative():
    """减持 → negative"""
    item = tag_item(_make_item("基金公司大幅减持比亚迪，套现约20亿"))
    assert item.sentiment == "negative"


def test_sentiment_dividend_positive():
    """派息/分红 → positive"""
    item = tag_item(_make_item("腾讯宣布派发特别股息，每股0.32港元"))
    assert item.sentiment == "positive"


def test_sentiment_profit_warning_negative():
    """业绩预警/不及预期 → negative"""
    item = tag_item(_make_item("公司发布盈利预警，收入不及预期"))
    assert item.sentiment == "negative"


def test_sentiment_short_sell_negative():
    """做空报告 → negative"""
    item = tag_item(_make_item("沽空机构发布做空报告，股价闪崩15%"))
    assert item.sentiment == "negative"


def test_sentiment_ipo_positive():
    """IPO/上市 → positive"""
    item = tag_item(_make_item("公司宣布在港交所上市，IPO估值200亿"))
    assert item.sentiment == "positive"


def test_sentiment_overall_accuracy():
    """Batch accuracy check: at least 85% of 20 samples correctly classified."""
    cases = [
        ("positive", "腾讯业绩超预期，净利润大增30%"),
        ("negative", "南向资金净卖出腾讯逾5亿港元"),
        ("positive", "腾讯云宣布开源OpenAI同款底座"),
        ("negative", "腾讯遭遇监管处罚，股价暴跌8%"),
        ("positive", "腾讯与字节跳动战略合作"),
        ("positive", "腾讯回购股份，金额达50亿港元"),
        ("negative", "腾讯宣布裁员，多个部门受影响"),
        ("positive", "腾讯Q3财报出炉，收入同比增长11%"),
        ("negative", "机构下调腾讯目标价至350港元"),
        ("positive", "机构上调腾讯目标价至500港元"),
        ("positive", "大股东增持200万股，彰显信心"),
        ("negative", "基金大幅减持，套现约20亿"),
        ("positive", "腾讯宣布派发特别股息"),
        ("negative", "公司发布盈利预警，收入不及预期"),
        ("negative", "沽空机构做空报告，股价闪崩"),
        ("positive", "获批新业务牌照，利好公司"),
        ("negative", "公司遭罚款2亿，违规操作确认"),
        ("positive", "公司宣布IPO，估值200亿"),
        ("positive", "净利润同比大增40%，业绩超市场预期"),
        ("negative", "公司亏损扩大，爆雷风险上升"),
    ]
    correct = sum(
        1 for expected, title in cases
        if tag_item(_make_item(title)).sentiment == expected
    )
    accuracy = correct / len(cases)
    assert accuracy >= 0.85, f"Batch accuracy {accuracy:.0%} < 85% ({correct}/{len(cases)} correct)"


# ── US ticker identification (T2.3 / T2.4) ──

def _load_tiny_us_universe() -> dict[str, dict[str, str]]:
    """Fixture: 10 SP500 majors for deterministic unit tests."""
    return {
        "US.AAPL": {"en": "", "zh": "苹果"},
        "US.MSFT": {"en": "", "zh": "微软"},
        "US.NVDA": {"en": "", "zh": "英伟达"},
        "US.GOOGL": {"en": "", "zh": "谷歌-A"},
        "US.AMZN": {"en": "", "zh": "亚马逊"},
        "US.META": {"en": "", "zh": "Meta"},
        "US.TSLA": {"en": "", "zh": "特斯拉"},
        "US.AMD": {"en": "", "zh": "超威半导体"},
        "US.INTC": {"en": "", "zh": "英特尔"},
        "US.AVGO": {"en": "", "zh": "博通"},
    }


def test_init_tagger_loads_us_universe():
    from news_data_kit import tagger as tagger_mod
    tagger_mod.init_tagger(us_names=_load_tiny_us_universe())
    assert "AAPL" in tagger_mod._US_TICKER_UNIVERSE
    assert "NVDA" in tagger_mod._US_TICKER_UNIVERSE
    assert len(tagger_mod._US_TICKER_UNIVERSE) == 10
    tagger_mod.init_tagger()  # reset


def test_us_ticker_positive_nvda_in_text():
    """Positive: bare ticker in universe → identified."""
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names=_load_tiny_us_universe())
    item = tag_item(_make_item("NVDA reports $XB revenue, beats estimates"))
    assert "US.NVDA" in item.symbols
    init_tagger()


def test_us_ticker_positive_multiple_in_text():
    """Positive: two universe tickers both captured."""
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names=_load_tiny_us_universe())
    item = tag_item(_make_item("AMD gains as NVDA slips on AI chip race"))
    assert "US.AMD" in item.symbols
    assert "US.NVDA" in item.symbols
    init_tagger()


def test_us_ticker_positive_with_context_punctuation():
    """Positive: ticker surrounded by punctuation still matches via \\b."""
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names=_load_tiny_us_universe())
    item = tag_item(_make_item("(TSLA) surges after Q3 delivery beat"))
    assert "US.TSLA" in item.symbols
    init_tagger()


def test_us_ticker_positive_zh_name_match():
    """Positive: zh name in text → maps to US symbol via extended_map."""
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names={"US.INTC": {"en": "", "zh": "英特尔"}})
    item = tag_item(_make_item("英特尔宣布裁员 15%"))
    assert "US.INTC" in item.symbols
    init_tagger()


def test_us_ticker_positive_disabled_when_universe_empty():
    """Positive: when us_names not loaded, US ticker match is disabled
    (no false positives from bare uppercase words like CEO)."""
    from news_data_kit.tagger import init_tagger
    init_tagger()  # empty universe
    item = tag_item(_make_item("AAPL earnings beat estimates"))
    # AAPL matches "apple" in _COMPANY_SYMBOL_MAP? No — "apple" is the key,
    # not "AAPL". So without universe, no US symbol extracted by regex path.
    us_syms_from_regex = [s for s in item.symbols if s.startswith("US.") and s == "US.AAPL"]
    # Apple's static entry in _COMPANY_SYMBOL_MAP is "apple" (lowercase); the
    # bare string "AAPL" in the title does not match "apple", so without universe
    # loaded, US.AAPL is NOT extracted from "AAPL earnings beat estimates".
    assert us_syms_from_regex == []


# ── Blacklist: 10 negative cases ──

def test_us_ticker_blacklist_ceo():
    """Negative: 'CEO' in universe would be false positive → blacklisted."""
    from news_data_kit.tagger import init_tagger
    # Seed universe with a hypothetical CEO ticker to prove blacklist wins
    init_tagger(us_names={
        **_load_tiny_us_universe(),
        "US.CEO": {"en": "", "zh": "CEO Test Co"},
    })
    item = tag_item(_make_item("Apple CEO announces new strategy"))
    assert "US.CEO" not in item.symbols
    init_tagger()


def test_us_ticker_blacklist_cpi():
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names={**_load_tiny_us_universe(), "US.CPI": {"en": "", "zh": ""}})
    item = tag_item(_make_item("CPI comes in hotter than expected"))
    assert "US.CPI" not in item.symbols
    init_tagger()


def test_us_ticker_blacklist_ai():
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names={**_load_tiny_us_universe(), "US.AI": {"en": "", "zh": ""}})
    item = tag_item(_make_item("AI chip demand surges"))
    assert "US.AI" not in item.symbols
    init_tagger()


def test_us_ticker_blacklist_usd():
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names={**_load_tiny_us_universe(), "US.USD": {"en": "", "zh": ""}})
    item = tag_item(_make_item("USD weakens against euro"))
    assert "US.USD" not in item.symbols
    init_tagger()


def test_us_ticker_blacklist_nyse():
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names={**_load_tiny_us_universe(), "US.NYSE": {"en": "", "zh": ""}})
    item = tag_item(_make_item("NYSE halts trading after glitch"))
    assert "US.NYSE" not in item.symbols
    init_tagger()


def test_us_ticker_blacklist_etf():
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names={**_load_tiny_us_universe(), "US.ETF": {"en": "", "zh": ""}})
    item = tag_item(_make_item("New ETF launches tracking semiconductor index"))
    assert "US.ETF" not in item.symbols
    init_tagger()


def test_us_ticker_blacklist_gdp():
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names={**_load_tiny_us_universe(), "US.GDP": {"en": "", "zh": ""}})
    item = tag_item(_make_item("Q3 GDP print shows 2.8% annualized growth"))
    assert "US.GDP" not in item.symbols
    init_tagger()


def test_us_ticker_blacklist_hk_market_code():
    """Negative: 'HK' token from 'HK.00700' should not be extracted as US ticker."""
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names={**_load_tiny_us_universe(), "US.HK": {"en": "", "zh": ""}})
    item = tag_item(_make_item("HK.00700 is up 3% today"))
    assert "US.HK" not in item.symbols
    init_tagger()


def test_us_ticker_blacklist_the():
    """Negative: common English word THE should not trigger even if in universe."""
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names={**_load_tiny_us_universe(), "US.THE": {"en": "", "zh": ""}})
    item = tag_item(_make_item("THE company reports strong quarter"))
    assert "US.THE" not in item.symbols
    init_tagger()


def test_us_ticker_blacklist_ipo():
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names={**_load_tiny_us_universe(), "US.IPO": {"en": "", "zh": ""}})
    item = tag_item(_make_item("Tech startup files for IPO at $5B valuation"))
    assert "US.IPO" not in item.symbols
    init_tagger()


def test_us_ticker_not_in_universe_rejected():
    """Negative: uppercase word not in universe → not identified as ticker."""
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names=_load_tiny_us_universe())  # only 10 tickers
    item = tag_item(_make_item("ZZZZZ launches new product line"))
    us_syms = [s for s in item.symbols if s.startswith("US.")]
    assert "US.ZZZZZ" not in us_syms
    init_tagger()


def test_us_ticker_single_char_not_matched():
    """Regex is [A-Z]{2,5} so single-letter tickers (V, F, T) not captured via regex.

    Single-letter ticker coverage relies on _COMPANY_SYMBOL_MAP (visa → US.V).
    """
    from news_data_kit.tagger import init_tagger
    init_tagger(us_names={**_load_tiny_us_universe(), "US.V": {"en": "", "zh": ""}})
    # "V" appears standalone in this title
    item = tag_item(_make_item("V shares surge 5% on news"))
    # Regex only matches [A-Z]{2,5} so single 'V' is not matched
    assert "US.V" not in item.symbols
    init_tagger()
