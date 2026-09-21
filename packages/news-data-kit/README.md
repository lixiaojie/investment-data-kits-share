# news-data-kit — 分享版

独立新闻采集、清洗、规则标签、去重和 SQLite 查询包。版本 `0.2.1+share.1`。
不依赖 MDK、不读取其他项目目录、不预装新闻数据库。

## 安装与使用

在本目录运行 `python -m pip install .`。默认仅启用 RSS。

```python
import news_data_kit as ndk

ndk.init(data_root="./local-news-data")
new_items = ndk.fetch(markets=["US"], days=1, max_items=20)
print(ndk.run_doctor())
stored_items = ndk.query(ndk.NewsQuery(markets=["US"], limit=20))
matches = ndk.search("semiconductor", limit=10)
```

`fetch()` 只返回本次新入库的文章，重复运行可能返回空；历史结果使用 `query()`。
`refresh()` 返回新增数量。`cleanup()` 删除超过 retention_days 的记录。
空结果不代表数据源正常，必须结合 `run_doctor()` 的最后抓取记录解释。

## 显式配置

- `data_root` 或 `NDK_DATA_ROOT`：默认 `~/.cache/news-data-kit-share`。
- `providers=("rss",)` 或 `NDK_PROVIDERS=rss`：默认只有 RSS。
- 可选 extra 与 provider：`akshare` / `yfinance` / `finviz`；由接收方按需安装启用。
- `feeds_config="./feeds.json"` 或 `NDK_FEEDS_CONFIG`：覆盖 RSS 列表，使用 JSON 数组。
- `company_names={"US.AAPL": ["Apple", "苹果"]}`：明确的 symbol 别名，无隐藏名称查询。
- `retention_days=30`，`request_timeout=10`（每个 RSS 请求秒数）。

默认包内 feed 为 BBC Business 与香港政府新闻。它们是示例来源，
并不代表完整金融新闻覆盖；接收方可替换为获准使用的订阅源。

```json
[
  {"url": "https://feeds.bbci.co.uk/news/business/rss.xml", "name": "BBC Business", "language": "en", "markets": ["US", "HK", "CN"]}
]
```

按股票过滤：

```python
ndk.init(company_names={"US.AAPL": ["Apple", "苹果"]})
items = ndk.fetch(symbols=["US.AAPL"], days=3)
```

英文 ticker 使用单词边界匹配。未配置名称时只按代码或源提供的 symbol 匹配，
可能漏掉只出现公司名的文章。规则情绪标签是辅助信息，不是投资判断。

## 数据与状态

正文不由公共入口持久化；保留来源、标题、链接、摘要、发布时间和抓取时间。
RSS 日期转换为 UTC；缺少日期时 `metadata.published_at_inferred=True`。
Yahoo 保留原始时区；Akshare 无时区发布时间按中国标准时间解释，Finviz 按纽约时间解释。
SQLite 时间采用 UTC 无时区字符串，查询日期请使用 UTC 无时区 datetime。
不自动抓取链接全文，不绕过登录或付费墙。

健康记录区分 not_checked、dependency_missing、ok、partial、no_results、error。
它们是最后一次抓取观察，带检查时间，不是当前在线保证。
可选源可能在其内部吞掉网络错误，因此 no_results 保持未知，不能显示“连接正常”。
RSS 对 HTML 错误页、超大响应和全部 feed 失败会明确记录错误。
无链接的新闻使用条目身份和标题去重，不会因为 URL 为空丢掉其他新闻。

## 验证

`python -m pip install '.[dev]'` 后运行 `python -m pytest tests`。
测试阻断 socket 网络访问。分享版不带原版 manifest/catalog、调度配置或评估脚本。
代码许可见 LICENSE；新闻内容使用条件见 NOTICE.md。
