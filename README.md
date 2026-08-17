# QQQ ↔ TQQQ 私人提醒

这个项目每天在美股收盘后自动更新 QQQ/TQQQ 数据：

- QQQ 从历史最高收盘价回撤 10% 时记录 `QQQ → TQQQ`。
- QQQ 收盘重新达到触发时保存的前高时记录 `TQQQ → QQQ`。
- 信号只在收盘确认后产生；模型持仓从下一交易日收益开始计算。
- 自动生成自包含的 `docs/index.html` 仪表板。
- 仪表板可切换 1/3/5/10 年或全部区间，对比 QQQ 与 TQQQ 归一化复权走势。
- 并排显示 7%、10% 和浏览器内自定义回撤阈值的年化收益、最大回撤、最终倍数与换仓次数。
- “其他杠杆策略评估”Tab 使用12只ETF的真实复权历史，分别评估 SPY/SSO、SPY/UPRO、QQQ/QLD、XLK/ROM、XLK/TECL、SOXX/USD 与 SOXX/SOXL。
- 新信号出现时可通过 SMTP 发邮件。
- 每个工作日任务成功后，即使没有换仓，也会发送“今日无需操作”的状态邮件；新信号日则发送“需要操作”邮件。
- `data/signals.csv` 保存完整历史信号。

> 这是规则提醒工具，不会自动下单，不构成投资建议。TQQQ 是每日 3 倍杠杆产品，策略历史回撤可能非常大。

## 本地运行

需要 Python 3.10 或更高版本，无第三方依赖：

```powershell
python src/run.py
python -m unittest discover -s tests -v
Start-Process .\docs\index.html
```

调整 `config.json` 可以修改回撤阈值、摩擦成本和图表年限。

## GitHub 设置

1. 创建仓库并 push 本目录。GitHub Free 要使用 Pages 时，将仓库设为 **Public**。
2. 打开仓库的 **Settings → Actions → General**，确认 Workflow permissions 为 `Read and write permissions`。
3. 打开 **Settings → Secrets and variables → Actions**，加入下列 Repository secrets。

| Secret | 示例（Gmail） | 说明 |
|---|---|---|
| `EMAIL_ENABLED` | `true` | 启用邮件 |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP 主机 |
| `SMTP_PORT` | `465` | SSL 端口 |
| `SMTP_USE_STARTTLS` | `false` | 465 使用 SSL；587 时设为 `true` |
| `SMTP_USERNAME` | 你的 Gmail 地址 | SMTP 用户名 |
| `SMTP_PASSWORD` | 16 位 App Password | 不要使用普通登录密码 |
| `ALERT_FROM_EMAIL` | 你的 Gmail 地址 | 发件人 |
| `ALERT_TO_EMAIL` | 你的收件邮箱 | 收件人，可与发件人相同 |

Gmail 需要先开启两步验证，再创建 App Password。所有密钥只能放在 GitHub Secrets，不能写入代码或 `config.json`。

4. 打开 **Actions → Update QQQ alert → Run workflow**，首次手动运行一次。
5. 首次运行用于建立当前状态，默认不会把旧信号当成新信号发送。以后只有最新信号发生变化才发送邮件。
6. 测试 Gmail 时，在 `Run workflow` 面板勾选 `Send a Gmail test alert` 后再运行；这只发送测试邮件，不会写入历史信号。如需发给临时指定的邮箱，在 `Recipient email` 中填写收件地址；留空则使用 `ALERT_TO_EMAIL` Secret。
7. 手动确认状态时，勾选 `Send today's operate / no-operate status email` 后运行。也可通过 `Recipient email` 指定本次收件邮箱。定时任务会自动发送状态邮件，并始终使用 `ALERT_TO_EMAIL` Secret。

## 公开网页

打开 **Settings → Pages**，在 **Build and deployment → Source** 选择 `GitHub Actions`。随后手动运行一次 `Update QQQ alert` 工作流。成功后网页地址为：

`https://justinyuezio.github.io/qqq/`

网页内容和历史信号将公开，但 GitHub Secrets 不会包含在网页产物中。

计划任务在周一至周五 `22:30 UTC` 运行，在美国冬令时和夏令时都晚于美股正常收盘。GitHub Actions 的计划执行可能延迟几分钟。

## 可见性说明

当前方案发布公开网页。代码和历史数据不包含邮箱密码；SMTP 密码只保存在 GitHub Secrets，不会打包进 Pages。若以后需要私人网页，应关闭 Pages，并改用带身份验证的托管服务。

## 文件结构

```text
config.json                  策略配置
src/run.py                   数据、信号、邮件和仪表板生成器
src/template.html            自包含仪表板模板
data/signals.csv             历史信号
data/latest.json             最新状态与指标
data/state.json              防止重复邮件的状态
docs/index.html              生成后的仪表板
.github/workflows/update.yml 定时任务
tests/test_strategy.py       核心规则测试
```
