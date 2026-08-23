# Update SOCKS5 Proxy List

每天 0 点（UTC）自动从 [proxifly/free-proxy-list](https://github.com/proxifly/free-proxy-list) 拉取 SOCKS5 代理列表，
筛选出**香港（HK）**和**新加坡（SG）**的可用节点，并更新到 GitHub Actions 环境变量 `SOCKS5_PROXY`。

## 工作原理

```
cdn.jsdelivr.net 拉取 socks5 全量列表
        ↓
ip-api.com 查询每个 IP 归属地 → 筛选 HK / SG
        ↓
curl 实测连通性（通过代理访问 api.ipify.org）
        ↓
写入 output/socks5_proxy.txt（每行一个）+ output/socks5_proxy.csv（逗号分隔）
        ↓
gh variable set SOCKS5_PROXY（base64 编码多行）→ 仓库变量
```

## 使用步骤

1. **创建仓库**：把这个目录的内容推送到你的 GitHub 仓库（`update-socks5-proxy/` 下的所有文件）

2. **启用 Workflow**：`.github/workflows/update-socks5.yml` 已配置好，推送后 Actions 会自动注册。
   默认触发：每天 0 点 UTC（如需北京时间 0 点，把 cron 改成 `'0 16 * * *'`）

3. **手动触发测试**：仓库 → Actions → Update SOCKS5 Proxy List → **Run workflow**

4. **其他 workflow 读取变量**：在你需要用到代理的 workflow 中：
   ```yaml
   - name: Decode SOCKS5_PROXY
     run: |
       echo "${{ vars.SOCKS5_PROXY }}" | base64 -d > socks5_proxy.txt
       cat socks5_proxy.txt
   ```
   之后即可逐行使用这些代理。

## 文件结构

```
.
├── .github/workflows/update-socks5.yml   # 定时任务（每天0点）
├── scripts/filter_socks5.py              # 筛选 + 测活脚本
└── README.md
```

## 参数说明（可在 workflow 中调整）

| 参数 | 位置 | 说明 |
|------|------|------|
| `MAX_PROXIES` | `scripts/filter_socks5.py` | 最多保留节点数，默认 10 |
| `TIMEOUT` | `scripts/filter_socks5.py` | 单节点测活超时（秒），默认 5 |
| cron | `.github/workflows/update-socks5.yml` | 执行时间，默认 `0 0 * * *`（UTC 0点） |
| 提交历史 | workflow 最后一步 | 默认关闭（`if: false`），如需保留历史改为 `true` |

## ⚠️ 注意事项

- 免费代理时效短，**测活结果是实时的**，每天更新即是意义所在
- 公共代理不可信，**禁止用于传输敏感信息**
- `ip-api.com` 免费版限制每分钟 45 个请求，全量列表几千个 IP 时需注意限流；
  如节点太多，可先按端口/IP 段粗筛再查询
- `gh variable set` 需要仓库变量存在（没有会自动创建），无需额外 Secret 权限
