# Investment Data Kits — 分享版

面向个人投资工作台的 Python 数据工具，提供行情、技术指标和可选新闻采集。
本仓库是采用 MIT 许可公开的独立试用版；数据在使用者自己的设备上获取，账号与数据权限由使用者提供。

| 包 | 能力 | 本版优先验证范围 |
| --- | --- | --- |
| market-data-kit | 港/美/A 股日线、快照、技术指标、来源与缓存状态 | 日线、快照；财报/宏观等扩展需要按数据源另行验收 |
| news-data-kit | RSS、清洗、标签、去重、本地新闻查询 | 默认 RSS；其他新闻源按需启用 |

## 开始使用

Python 3.11+；请在独立虚拟环境中安装。当前实测平台见 [VERIFICATION.md](VERIFICATION.md)。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install './packages/market-data-kit[yfinance]' ./packages/news-data-kit
python examples/workbench.py --demo
```

Windows 激活命令为 `.venv\Scripts\activate`。`--demo` 使用醒目标记的合成数据。
取得真实行情：

```bash
python examples/workbench.py --symbol US.AAPL --provider yfinance
```

完整说明：[接入指南](GETTING_STARTED.md)、[行情接口](packages/market-data-kit/README.md)、
[新闻接口](packages/news-data-kit/README.md)、[项目概览](docs/PROJECT_SPEC.md)。
Releases 提供包含 wheel、源码和校验和的完整试用包；仓库克隆可直接按上述源码安装。

## 使用边界

结果带来源、截至日期、获取时间、缓存过期与模拟标记；当日数据可能尚未收盘。
这些标记帮助工作台识别数据状态，不承诺实时性、完整性或交易用途适用性。
本版不提供交易、分钟线、托管行情 API 或统一数据再分发授权。

分享包不含真实账号、内网适配器、个人环境、历史数据或原项目 Git 历史。
参见 [配置与安全边界](SECURITY.md)、[数据与代码许可边界](SHARING.md)。
代码采用 [MIT 许可](LICENSE)，包内声明分别见 [MDK LICENSE](packages/market-data-kit/LICENSE) 和
[NDK LICENSE](packages/news-data-kit/LICENSE)。

仓库可公开浏览、克隆和下载，不承诺长期维护周期或服务等级；使用中遇到问题请附最小合成示例，
不要提交真实账户、完整环境变量或私人运行日志。
