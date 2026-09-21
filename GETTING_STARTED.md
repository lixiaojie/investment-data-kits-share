# 投资工作台数据工具：开始使用

包内只有工具代码、合成测试和示例。请准备 Python 3.11+、自己的网络和所需数据权限。
本版与同名原版包应安装到不同虚拟环境。

## 安装

解压后进入目录：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install './packages/market-data-kit[yfinance]' ./packages/news-data-kit
```

Windows 激活命令为 `.venv\Scripts\activate`。
也可从 wheels 目录安装离线包本体，但第三方依赖需要联网下载或由接收方事先准备。
可用 `python -m pip install --find-links wheels 'market-data-kit[yfinance]==0.5.2+share.1' 'news-data-kit==0.2.1+share.1'`。

## 先看无网络示例

```bash
python examples/workbench.py --demo
```

该示例使用临时目录，输出醒目标记的合成日线、技术指标与模拟新闻查询。
它验证结构和接入方式，不是行情验收。

## 再取一只股票

```bash
python examples/workbench.py --symbol US.AAPL --provider yfinance
mdk doctor
```

快照与日线的更新时间、权限和返回覆盖由具体数据源决定。界面至少展示
provider、as_of、fetched_at、stale、refresh_failed 和 simulated。
`mdk doctor` 仅检查本机依赖，不会以“安装成功”冒充在线可用。

## 选择数据源

- 美股研究：先安装 yfinance extra，用自己的网络做少量样本验证。
- 港股/A 股：可安装 akshare extra；也可使用自己的 Futu OpenD 与行情权限。
- 使用 OpenD：安装 MDK futu extra，登录网关后显式 `kit.init(providers=("futu",))`。
- 新闻：先用默认 RSS；需要按公司过滤时显式提供 company_names。

详细配置、复权差异、缓存行为和可用接口见两个包的 README。

## 接收方验收

在目标机器、目标网络中，以港/美/A 各一只实际关注标的检查：
安装 → 日线 → 来源和日期 → 快照 → 重启后缓存 → 断网显式报错/旧数据提示。
再验证一组新闻抓取和去重。未购买的行情权限不应以共享作者账号补足。
交易、分钟线和严谨跨源回测不属于本版保证。

数据与内容条款见 SHARING.md。检查 FILE_MANIFEST.json 与 SHA256SUMS 后再使用。
