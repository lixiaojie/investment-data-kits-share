"""Symbol normalization — converts any format to standard {MARKET}.{CODE}.

Standard format: HK.00700, CN.600519, US.AAPL, IDX.000300
- HK codes are always 5-digit zero-padded
- CN exchange derived from code: 6/5/9→SH, 0/3→SZ
- US codes are uppercase alpha (may contain dots like BRK.B)
- IDX codes are index symbols (must be explicitly prefixed)
"""

from __future__ import annotations

__all__ = [
    "normalize",
    "market",
    "exchange",
    "to_futu",
    "to_tushare",
    "to_yfinance",
    "to_wind",
    "from_wind",
    "to_push2_secid",
    "to_akshare",
    "SymbolError",
]


class SymbolError(ValueError):
    """Raised when a symbol cannot be parsed or is invalid."""


_CN_SH_PREFIXES = ("6", "5", "9")
_CN_SZ_PREFIXES = ("0", "1", "3")  # 1xxxxx = 深交所 ETF/基金
_CN_BJ_PREFIXES = ("4", "8")  # 北交所: 4xxxxx, 8xxxxx


def _cn_exchange(code: str) -> str:
    if code[0] in _CN_SH_PREFIXES:
        return "SH"
    if code[0] in _CN_SZ_PREFIXES:
        return "SZ"
    if code[0] in _CN_BJ_PREFIXES:
        return "BJ"
    raise SymbolError(f"Cannot determine CN exchange for code: {code}")


def _extract_code(symbol: str) -> str:
    dot_idx = symbol.index(".")
    return symbol[dot_idx + 1:]


def normalize(raw: str) -> str:
    if not isinstance(raw, str):
        raise SymbolError(f"Expected string, got {type(raw).__name__}")
    s = raw.strip()
    if not s:
        raise SymbolError("Empty symbol string")

    parts = s.split(".", 1)

    if len(parts) == 1:
        token = parts[0]
        return _normalize_no_dot(token)

    left, right = parts[0].upper(), parts[1].upper()

    # Already standard: HK.xxxxx, CN.xxxxxx, US.xxxx
    if left == "HK":
        return f"HK.{right.zfill(5)}"
    if left == "CN":
        return f"CN.{right}"
    if left == "US":
        # Handle US.BRK.B — right might contain another dot
        return f"US.{right}"
    if left == "IDX":
        return f"IDX.{right}"

    # Futu CN format: SH.600519, SZ.000001, BJ.832317
    if left in ("SH", "SZ", "BJ"):
        return f"CN.{right}"

    # Tushare/yfinance suffix: 600519.SH, 000001.SZ, 600519.SS, 0700.HK
    if right == "HK":
        return f"HK.{left.zfill(5)}"
    if right == "SH":
        return f"CN.{left}"
    if right == "SZ":
        return f"CN.{left}"
    if right == "SS":
        return f"CN.{left}"
    if right == "BJ":
        return f"CN.{left}"

    # US stock with dot in ticker: BRK.B
    if left.isalpha() and right.isalpha() and len(right) == 1:
        return f"US.{left}.{right}"

    raise SymbolError(f"Cannot parse symbol: {raw!r}")


def _normalize_no_dot(token: str) -> str:
    upper = token.upper()
    if upper.isalpha():
        return f"US.{upper}"
    if upper.isdigit():
        length = len(upper)
        if length == 6:
            return f"CN.{upper}"
        if 1 <= length <= 5:
            return f"HK.{upper.zfill(5)}"
        raise SymbolError(f"Pure numeric symbol has unexpected length {length}: {token!r}")
    raise SymbolError(f"Cannot parse symbol: {token!r}")


def market(symbol: str) -> str:
    prefix = symbol.split(".")[0].upper()
    if prefix in ("HK", "CN", "US", "IDX"):
        return prefix
    raise SymbolError(f"Unknown market in symbol: {symbol!r}")


def exchange(symbol: str) -> str:
    mkt = market(symbol)
    code = _extract_code(symbol)
    if mkt == "HK":
        return "HKEX"
    if mkt == "CN":
        return _cn_exchange(code)
    if mkt == "US":
        return "NYSE"
    if mkt == "IDX":
        return "INDEX"
    raise SymbolError(f"Unknown market: {mkt}")


def to_futu(symbol: str) -> str:
    mkt = market(symbol)
    code = _extract_code(symbol)
    if mkt == "HK":
        return f"HK.{code}"
    if mkt == "CN":
        exch = _cn_exchange(code)
        return f"{exch}.{code}"
    if mkt == "US":
        return f"US.{code}"
    if mkt == "IDX":
        _IDX_FUTU_MAP = {
            "HSI": "HK.800000",
            "HSCEI": "HK.800100",
            "SPX": "US.SPX",
            "IXIC": "US.IXIC",
            "DJI": "US.DJI",
            "RUT": "US.RUT",
            "VIX": "US.VIX",
        }
        futu = _IDX_FUTU_MAP.get(code)
        if futu:
            return futu
        if code.isdigit():
            # For CN indices, derive exchange from Wind map (stock rules don't apply)
            wind = _IDX_WIND_MAP.get(code)
            if wind:
                exch = wind.split(".")[1]  # "000300.SH" → "SH"
                return f"{exch}.{code}"
            exch = _cn_exchange(code)
            return f"{exch}.{code}"
        raise SymbolError(f"No Futu mapping for IDX: {symbol}")
    raise SymbolError(f"Cannot convert to Futu format: {symbol!r}")


def to_tushare(symbol: str) -> str:
    mkt = market(symbol)
    code = _extract_code(symbol)
    if mkt == "CN":
        exch = _cn_exchange(code)
        return f"{code}.{exch}"
    if mkt == "HK":
        return f"{code}.HK"
    if mkt == "US":
        return f"{code}.US"
    raise SymbolError(f"Cannot convert to Tushare format: {symbol!r}")


def to_yfinance(symbol: str) -> str:
    mkt = market(symbol)
    code = _extract_code(symbol)
    if mkt == "HK":
        return f"{code.lstrip('0').zfill(4)}.HK"
    if mkt == "CN":
        exch = _cn_exchange(code)
        suffix = "SS" if exch == "SH" else "SZ"
        return f"{code}.{suffix}"
    if mkt == "US":
        return code.replace(".", "-")
    if mkt == "IDX":
        _IDX_YFINANCE_MAP = {
            "000300": "000300.SS",
            "000001": "000001.SS",
            "000016": "000016.SS",
            "000905": "000905.SS",
            "399001": "399001.SZ",
            "399006": "399006.SZ",
            "HSI": "^HSI",
            "HSCEI": "^HSCE",
            "HSTECH": "^HSTECH",
            "SPX": "^GSPC",
            "IXIC": "^IXIC",
            "DJI": "^DJI",
            "RUT": "^RUT",
            "VIX": "^VIX",
        }
        yf = _IDX_YFINANCE_MAP.get(code)
        if yf:
            return yf
        if code.isdigit():
            exch = _cn_exchange(code)
            suffix = "SS" if exch == "SH" else "SZ"
            return f"{code}.{suffix}"
        return f"^{code}"
    raise SymbolError(f"Cannot convert to yfinance format: {symbol!r}")


def to_push2_secid(symbol: str) -> str:
    mkt = market(symbol)
    code = _extract_code(symbol)
    if mkt == "HK":
        return f"116.{code}"
    if mkt == "CN":
        exch = _cn_exchange(code)
        prefix = "1" if exch == "SH" else "0"
        return f"{prefix}.{code}"
    if mkt == "US":
        return f"105.{code}"
    if mkt == "IDX":
        if code.isdigit():
            # For CN indices, derive exchange from Wind map (stock rules don't apply)
            wind = _IDX_WIND_MAP.get(code)
            if wind:
                exch = wind.split(".")[1]  # "000300.SH" → "SH"
            else:
                exch = _cn_exchange(code)
            prefix = "1" if exch == "SH" else "0"
            return f"{prefix}.{code}"
        raise SymbolError(f"push2 does not support non-CN index: {symbol}")
    raise SymbolError(f"Cannot convert to push2 secid: {symbol!r}")


def to_akshare(symbol: str) -> str:
    return _extract_code(symbol)


# IDX symbol → Wind format mapping
_IDX_WIND_MAP = {
    "000300": "000300.SH",
    "000001": "000001.SH",  # 上证指数
    "000016": "000016.SH",  # 上证50
    "000905": "000905.SH",  # 中证500
    "399001": "399001.SZ",  # 深证成指
    "399006": "399006.SZ",  # 创业板指
    "HSI": "HSI.HI",
    "HSCEI": "HSCEI.HI",
    "HSTECH": "HSTECH.HI",
    "SPX": "SPX.GI",
    "IXIC": "IXIC.GI",
    "DJI": "DJI.GI",
    "RUT": "RUT.GI",
    "VIX": "VIX.GI",
}


def to_wind(symbol: str) -> str:
    """Convert kit symbol to Wind format."""
    mkt = market(symbol)
    code = _extract_code(symbol)
    if mkt == "IDX":
        wind = _IDX_WIND_MAP.get(code)
        if wind:
            return wind
        # Fallback: assume CN index if numeric
        if code.isdigit():
            if code[0] in _CN_SH_PREFIXES:
                return f"{code}.SH"
            return f"{code}.SZ"
        raise SymbolError(f"No Wind mapping for IDX symbol: {symbol}")
    if mkt == "HK":
        # Wind uses 4-digit HK codes (e.g. 0700.HK), MDK stores 5-digit (00700)
        hk_code = code.lstrip("0") or "0"
        if len(hk_code) < 4:
            hk_code = hk_code.zfill(4)
        return f"{hk_code}.HK"
    if mkt == "CN":
        exch = _cn_exchange(code)
        return f"{code}.{exch}"
    if mkt == "US":
        return f"{code}.O"  # Default to NASDAQ; caller may override
    raise SymbolError(f"Cannot convert to Wind format: {symbol!r}")


# Reverse map: Wind suffix → IDX code (built from _IDX_WIND_MAP)
_WIND_IDX_REVERSE: dict[str, str] = {v: f"IDX.{k}" for k, v in _IDX_WIND_MAP.items()}

# Wind suffix → conversion logic
_WIND_SUFFIX_MAP = {
    "HK": "HK",
    "SH": "CN",
    "SZ": "CN",
    "BJ": "CN",
    "O": "US",   # NASDAQ
    "N": "US",   # NYSE
    "HI": "IDX", # HK index
    "GI": "IDX", # Global index
}


def from_wind(wind_symbol: str) -> str:
    """Convert Wind-format symbol to kit standard format.

    Examples:
        00700.HK → HK.00700
        600519.SH → CN.600519
        AAPL.O → US.AAPL
        BRK_B.N → US.BRK.B
        HSI.HI → IDX.HSI
    """
    if not isinstance(wind_symbol, str):
        raise SymbolError(f"Expected string, got {type(wind_symbol).__name__}")
    s = wind_symbol.strip()
    if not s:
        raise SymbolError("Empty symbol string")

    dot_idx = s.rfind(".")
    if dot_idx < 0:
        raise SymbolError(f"Wind symbol must contain a dot: {wind_symbol!r}")

    code = s[:dot_idx]
    suffix = s[dot_idx + 1:].upper()

    # Check IDX reverse map first — CN indices (000905.SH) share suffix with CN stocks
    idx_sym = _WIND_IDX_REVERSE.get(s.upper())
    if idx_sym:
        return idx_sym

    mkt = _WIND_SUFFIX_MAP.get(suffix)
    if mkt is None:
        raise SymbolError(f"Unknown Wind suffix '.{suffix}' in: {wind_symbol!r}")

    if mkt == "HK":
        return f"HK.{code.zfill(5)}"
    if mkt == "CN":
        return f"CN.{code}"
    if mkt == "US":
        # Wind uses underscore for dots in US tickers: BRK_B → BRK.B
        return f"US.{code.replace('_', '.')}"
    if mkt == "IDX":
        return f"IDX.{code}"

    raise SymbolError(f"Cannot convert Wind symbol: {wind_symbol!r}")
