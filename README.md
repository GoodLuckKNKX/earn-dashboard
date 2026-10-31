# 交易所活期理财收益对比

静态看板：<https://goodluckknkx.github.io/earn-dashboard/>。

GitHub Actions 每小时采集 Binance / OKX / Gate / Bitget / Bybit 利率，写入
`data/rates.json`，再发布到 GitHub Pages。浏览器只加载 HTML、JavaScript 和 JSON，
没有 Python 后端、数据库或 Render 服务依赖。Python 采集器仅使用标准库。

## GitHub 设置

1. **Settings → Pages → Build and deployment → Source：GitHub Actions**。
2. **Settings → Actions → General** 允许运行本仓库的 Actions 和官方 `actions/*`。
   `fetch.yml` 已声明 `permissions: contents: write`，使用自动生成的 `GITHUB_TOKEN`
   提交数据，无需创建个人 token。若组织策略禁止写入，需要管理员放行。
3. 若使用 Bybit 签名请求，在 **Settings → Secrets and variables → Actions →
   New repository secret** 添加 `BYBIT_API_KEY` 和 `BYBIT_API_SECRET`。
   不要将密钥填入 Variables、源文件或 JSON。
   未设置两个 Secret 时，脚本尝试公开接口；只设置其中一个会报告该交易所配置错误。
4. **Actions → Fetch rates → Run workflow** 可立即更新；
   **Actions → Deploy GitHub Pages → Run workflow** 可手动发布。

采集计划是 UTC cron `0 * * * *`，即每小时整点（北京时间也为整点）。
GitHub 排队可能延后任务；公开仓库长期无活动时，GitHub 也可能停用定时任务。
如被停用，可在 Actions 重新启用。

`GITHUB_TOKEN` 提交不会启动普通 `push` 工作流，因此 Pages 额外监听
`Fetch rates` 的 `workflow_run: completed` 成功事件，检出最新 `main` 数据并部署。
发布包仅含 `index.html`、`app.js`、`data/rates.json` 和 `.nojekyll`。

## 本地采集与预览

要求 Python 3.9+；Actions 使用 Python 3.12。

```bash
python3 -m unittest discover -s tests -v
python3 scripts/fetch_rates.py
python3 -m http.server 8787
```

打开 <http://localhost:8787/>。必须通过 HTTP 打开，浏览器不允许 `file://` 直接读取 JSON。
本地需要签名时，通过环境变量传入两个 Bybit 密钥；脚本不加载或打印密钥文件。

## 时间与故障保留

- `updated_at`：最近一次有交易所成功采集的 UTC ISO 8601 时间（`Z` 后缀）。
- `checked_at`：最近一次采集尝试的 UTC 时间，即使全部交易所失败也会更新。
- `status.<exchange>.updated_at`：该交易所上次成功时间；失败时不会变新。
- `status.<exchange>.error`：失败原因；`ok: false`；有历史数据时 `stale: true`。
- 交易所独立抓取和校验，失败只保留该交易所上次成功的产品，其余来源继续更新。
  空结果或无效利率也视为采集失败，防止接口异常清空旧数据。全部失败仍正常写出 JSON。
- 初次运行若无 `data/rates.json`，从原项目 `snapshot.json` 引入历史数据，
  保留它原始时间；历史快照与 `SUMMARY.md` 仅供追溯，不作为实时数据。
- 页面显示“数据更新于 xx 分钟前”，并强制以北京时间展示绝对时间；
  失败来源在状态栏、产品行和顶部比较结果中标出旧数据时间。

## 数据源与限制

沿用原项目的 Binance `simpleEarnProducts`、OKX `lending-rate-summary`、
Gate `earn/uni/rate`、Bitget 网页 `savings/product/list` 逻辑。
Bybit 使用 `/v5/earn/product?category=FlexibleSaving`，解析 `estimateApr` 的百分数。
如配置了两个密钥，按官方 V5 HMAC SHA256 规范在请求头签名；输出仅含产品行情和状态，
不含密钥、签名或账户资产信息。

Bybit 产品接口[支持公开请求](https://bybit-exchange.github.io/docs/v5/finance/earn/easy-onchain/product-info)。
平台奖励未包含在返回 APR 中。API Key 无法解除交易所的地区封锁；
Bybit [明确限制美国、中国大陆 IP](https://bybit-exchange.github.io/docs/v5/guide)。
GitHub 托管 runner 所在地区可能导致 Binance/Bybit 返回 403/451，此时显示旧数据或暂无数据，
不把历史利率伪装成最新利率，也不尝试绕过限制。

利率为年化估计，随市场变化；仅作信息参考。

迁移后若不再使用旧 Render 服务，可在 Render 控制台自行暂停或删除；该操作不会由本仓库执行。
