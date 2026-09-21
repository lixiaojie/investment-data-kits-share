# market-data-kit — 分享版

面向个人研究工作台的 Python 行情工具。Python 3.11+；本次验收环境见交付记录。
这是独立分享版本 `0.5.2+share.1`，保留导入名，但不是原运行栈的原位升级包。
请在独立虚拟环境安装。

## 安装

在本目录运行 `python -m pip install '.[yfinance]'`。
A 股可选 `.[akshare]`；使用自有 OpenD 账户可选 `.[futu]`。
Tushare 可选 `.[tushare]`，token 由接收方通过 `MDK_TUSHARE_TOKEN` 配置。
从交付 wheel 安装参见顶层 GETTING_STARTED.md。

## 快速开始

```python
import market_data_kit as kit

kit.init(providers=("yfinance",), data_root="./local-market-data")
df = kit.load_klines("US.AAPL", days=120)
print(df.attrs)  # 来源、截至日期、获取时间、过期、缓存、覆盖不足和模拟标记
enriched = kit.indicators.compute_all(df, preset="default")
print(enriched[["date", "close", "rsi_14", "ma_20"]].tail())
```

行情请求会访问公开数据源。无网络的结构演示需明确 `kit.init(use_stubs=True)`，
输出会标 `simulated=True`，模拟行情不会写进价格缓存。

## 接口

- `normalize("00700.HK")` → `HK.00700`；`market()` / `exchange()`。
- `load_klines(symbol, days=120, end_date=None, adjust="none", *, refresh=False, allow_stale=False, max_age_days=None)`。
- `load_klines_batch(symbols, ...)`：逐个加载；某个失败会抛错，不返回看似完整的部分结果。
- `snapshot(symbols)`：每条有 `provider`、`fetched_at`、`simulated`；无上游时点则 `as_of=None`。
- `fundamentals`、`income_statement`、`balance_sheet`、`cash_flow_statement`。
- `capital_flow`、`plates`、`earnings_calendar`：按 provider 可用范围支持。
- `load_macro`：显式启用 `fred` 或 `china_macro`；FRED 需要 `FRED_API_KEY`。
- `load_commodity`：显式启用 `commodity`，依赖 yfinance。
- `load_northbound_flow`：启用 akshare，覆盖取决于上游发布。
- `name` / `names`：通过启用的公开快照源尽力查名称，可能返回 None；无隐藏名称服务。
- `run_doctor()` / `mdk doctor`：只检查本机依赖和配置，`live_verified=False`。
- `mdk klines US.AAPL --days 30`：输出带元数据的 JSON；取数失败退出码为 2。

## Provider 与复权

| Provider | 启用方法 | 日线复权支持 |
|---|---|---|
| yfinance | 安装 extra，`providers=("yfinance",)` | `none`：Yahoo 的非额外复权输出；Yahoo 历史本身含拆股调整 |
| akshare | 安装 extra，`providers=("akshare",)` | 股票 `none/qfq/hfq`，数字指数仅 `none` |
| push2 | 核心内置，`providers=("push2",)` | A 股 `none/qfq/hfq` |
| Futu OpenD | 安装 extra、运行并登录 OpenD，显式启用 `futu` | 显式映射 AuType.NONE/QFQ/HFQ，权限由接收方账户决定 |
| Tushare | 安装 extra、自备 token，显式启用 `tushare` | 当前适配器只支持 `none` |

`qfq`/`hfq` 分别是前/后复权。Yahoo 口径不冒充这两种口径；不支持的源会被跳过，
全部不支持时抛出 `ProviderUnavailableError`。跨源原始价、复权算法和成交量单位
仍须结合供应方定义使用；本版不宣称可跨源拼接严谨回测数据。

返回 `volume_unit`：已确认的股票股数标为 shares，其余保留 source_native。
CN 的 Akshare/东方财富/Tushare 日线从手转换为股；指数及未核实的源量纲不猜测。
日线可能包含正在交易的当日 bar，`bar_finality` 明确为未知，不代表正式收盘价。

财报带 `period_type` 与 `period_end`：Yahoo 利润/现金流为 annual，
Akshare 利润/现金流为 year_to_date，资产负债表为 point_in_time。
`period=2025Q4` 只标识截止季度，不能忽略 period_type 当成单季数据。
Akshare 基本面缺乏可确认口径的市值时保留 NaN，不用总资产替代。
商品的 fast_info 没有核实报价时间时 `date/as_of=None`；fetched_at 仅为本次获取时间。

默认源顺序是 `yfinance,akshare,push2`，可用 `MDK_PROVIDERS` 或 `init(providers=...)`
改变。OpenD 不会自动连接。未安装的可选源跳过。不改变进程的代理设置。

## 缓存与新鲜度

默认目录是 `~/.cache/market-data-kit-share`，可用 `MDK_DATA_ROOT` 或 `data_root` 覆盖。
按股票、请求行数、截止日、复权和源配置分别缓存完整响应，不将不同源、不同复权
或不同获取批次的价格序列拼接。缓存保留 provider/fetched_at/adjust/simulated 列。

默认最多 3 个**自然日**的日期差，缓存 TTL 为 1 小时。该规则不是交易所节假日日历；
长假应显式传 `max_age_days` 或设置过去的 `end_date`。`days` 是最多返回行数，
不足时 `complete=False`，调用方必须检查；新股和停牌可能合法地不足。

没有可用新数据时默认抛错；只有显式 `allow_stale=True` 才返回候选缓存/旧行情，
同时给出警告、`refresh_failed=True` 与尝试摘要。`stale` 专指数据日期，
`refresh_failed` 专指本次刷新失败；两者应分别展示。

快照接口的获取时间不是交易所报价时间，`realtime_verified=False`，不要据此承诺实时。
若所有源为空或失败，会抛错，错误摘要不包含 token 或原始响应。

## 与原版差异

本版不包含历史数据、内部服务、Wind、scheduler、消费者登记、catalog、全市场回填、
数据包导入、原版 Store API 或 MCP。需要定时更新时，由工作台调用 API。
NDK 是独立可选包。指标默认组合为 RSI、MA、布林带、ATR、量比、52 周高低；
MACD 可使用 `preset="backtest"` 或直接调用对应指标函数。

## 验证

`python -m pip install '.[dev]'` 后运行 `python -m pytest tests`。
默认排除真实网络标记；单元测试阻断 socket 网络访问。
账户权限、各市场实时性与目标设备仍需单独实测。代码许可见 LICENSE；数据使用条件见 NOTICE.md。
