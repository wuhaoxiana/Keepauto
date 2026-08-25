# AgentRouter 自动签到脚本

每天自动登录 [AgentRouter](https://agentrouter.org/register?aff=Rm0L) 完成签到，获取每日奖励。

## ⚙️ 功能特性

- ✅ 使用账号密码自动登录（登录即签到）
- ✅ 支持代理配置，绕过 WAF 验证
- ✅ Telegram 通知（可选）
- ✅ GitHub Actions 自动运行（每天北京时间 10:00）

## 🚀 快速开始

### 1. Fork 本仓库

点击右上角 **Fork** 按钮，将仓库复制到你的账号下。

### 2. 配置 Secrets

前往仓库的 **Settings** → **Secrets and variables** → **Actions** → **New repository secret**，添加以下配置：

#### 必须配置：

| Name | Value | 说明 |
|------|-------|------|
| `USERNAME` | 你的邮箱 | AgentRouter 登录邮箱 |
| `PASSWORD` | 你的密码 | AgentRouter 登录密码 |
| `PROXY_CONFIG_URL` | 订阅地址 URL | 代理订阅地址（返回 base64 或明文的节点列表） |

> **代理配置说明**：`PROXY_CONFIG_URL` 填代理订阅地址，脚本会自动拉取、解码并**逐节点测试连通性，自动选择第一个可用节点**。
> 若配置了 `NODE_LINK`（单节点或订阅 URL），则以 `NODE_LINK` 为准，未配置时才使用 `PROXY_CONFIG_URL`。

**`NODE_LINK`（可选）示例**：
```
vmess://ew0KICAidiI6ICIyIiwNCiAgInBzIjogIuWPsOa5vummmue4rzAxIiwNCi...
vless://uuid@host:port?type=ws&security=tls&sni=example.com
trojan://password@host:port?type=ws&sni=example.com
hysteria2://auth@host:port?sni=example.com
socks5://user:pass@host:port
```

**工作原理**：
- 脚本自动下载 [sing-box](https://github.com/SagerNet/sing-box)
- 拉取并解码代理订阅，解析出所有节点
- 逐节点启动本地代理并测试连通性，自动选择可用节点
- 启动本地 SOCKS5 代理（`socks5://127.0.0.1:1080`）
- Playwright 通过本地代理访问 AgentRouter
---
#### Telegram 通知（可选）：

| Name | Value | 说明 |
|------|-------|------|
| `TG_BOT_TOKEN` | Bot Token | 从 [@BotFather](https://t.me/BotFather) 获取 |
| `TG_CHAT_ID` | Chat ID | 你的 Telegram Chat ID |

### 3. 启用 GitHub Actions

1. 前往仓库的 **Actions** 标签页
2. 点击 **I understand my workflows, go ahead and enable them**
3. 脚本将在每天北京时间 10:00 自动运行

### 4. 手动测试运行

前往 **Actions** → 选择 **Ayrouter Daily Check-in** → 点击 **Run workflow**

## 📋 工作原理

1. **登录即签到**：AgentRouter 的签到机制是"登录即完成签到"
2. **浏览器自动化**：使用 Playwright 模拟真实浏览器登录
3. **代理绕过 WAF**：通过住宅代理 IP 避免触发阿里云 WAF 滑块验证
4. **每日自动运行**：GitHub Actions 定时任务

## ⚠️ 关于 WAF 验证

AgentRouter 使用了阿里云 WAF，在以下情况会触发滑块验证：
- GitHub Actions 等云服务 IP
- 数据中心 IP
- 频繁请求的 IP

**解决方案**：
1. ✅ **推荐**：配置住宅代理 IP（稳定可靠）

## 🛠️ 常见问题

### Q: 如何获取 Telegram Chat ID？
A: 
1. 向 [@userinfobot](https://t.me/userinfobot) 发送任意消息
2. Bot 会返回你的 Chat ID

### Q: 脚本运行失败怎么办？
A: 
1. 查看 Actions 运行日志
2. 检查是否配置了代理
3. 确认账号密码是否正确
4. 查看是否有错误截图（`page_error.png`）

## 📜 更新日志

- **2026-08-07**: 添加代理支持，绕过 WAF 验证
- **2026-08-07**: 改为账号密码登录模式
- **2026-08-06**: 初始版本

## 📄 许可证

MIT License
