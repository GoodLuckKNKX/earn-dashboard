# 交易所活期理财收益对比 (earn-dashboard)
实时对比 Binance / OKX / Bitget / Gate（Bybit 视服务器地区）活期理财年化。仅用公开接口，无 API Key，无第三方依赖（Python 3 标准库）。

- 本地运行：`python3 server.py`（默认端口 8787，可用 `PORT` 环境变量覆盖）→ http://localhost:8787
- 数据接口：`/api/data`，后台每 60 秒轮询一次
- 部署 Render：仓库含 `render.yaml`（免费 web service，新加坡区域）。用 `https://render.com/deploy?repo=<你的仓库URL>` 一键 Blueprint 部署，或在 Render 控制台选 “Public Git Repository”。
- 地区说明：Binance 与 Bybit 会屏蔽美国 IP，因此不要选 oregon/ohio/virginia；新加坡首选，若某交易所拦截可改 frankfurt。
- 数据源：Binance bapi simpleEarnProducts（公开网页接口）、OKX /api/v5/finance/savings/lending-rate-summary、Bitget /v1/finance/savings/product/list（公开网页接口）、Gate /api/v4/earn/uni/rate、Bybit /v5/earn/product（多数情况下需 Key / 地区限制，失败时显示不可用）。
- 注意：Render 免费实例闲置 15 分钟会休眠，首次访问需等待约 1 分钟唤醒。仅供参考，不构成投资建议。
