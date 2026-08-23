# Update SOCKS5 Proxy List

每 4 小时自动从 [proxifly/free-proxy-list](https://github.com/proxifly/free-proxy-list) 拉取 SOCKS5 代理列表，
筛选出**香港（HK）**、**新加坡（SG）**、**中国（CN）**的可用节点，并更新到 GitHub Actions 环境变量 `SOCKS5_PROXY`。

## 工作原理

```
cdn.jsdelivr.net 拉取 socks5 全量列表
        ↓
ip-api.com 查询每个 IP 归属地 → 筛选 HK / SG / CN
        ↓
curl 实测连通性（通过代理访问 api.ipify.org）→ 仅保留可用节点
        ↓
合并现有变量 + 本次可用节点（去重，只增不减，不覆盖）
        ↓
全部节点统一再测活一次 → 剔除失效旧节点（clean_dead.py）
        ↓
gh variable set SOCKS5_PROXY（多行）→ 仓库变量
```

## 使用步骤

1. **创建仓库**：把这个目录的内容推送到你的 GitHub 仓库（`update-socks5-proxy/` 下的所有文件）

2. **启用 Workflow**：`.github/workflows/update-socks5.yml` 已配置好，推送后 Actions 会自动注册。
   默认触发：**每 4 小时**（UTC 0/4/8/12/16/20 点，即北京时间 8/12/16/20/0/4 点）

3. **手动触发测试**：仓库 → Actions → Update SOCKS5 Proxy List → **Run workflow**

4. **其他 workflow 读取变量**：在你需要用到代理的 workflow 中：
   ```yaml
   - name: Read SOCKS5_PROXY
     run: |
       echo "${{ vars.SOCKS5_PROXY }}" > socks5_proxy.txt
       cat socks5_proxy.txt
   ```
   之后即可逐行使用这些代理。

## 文件结构

```
.
├── .github/workflows/update-socks5.yml   # 定时任务（每4小时）
├── free-socks5/filter_socks5.py              # 筛选 + 测活脚本
├── free-socks5/clean_dead.py                 # 合并后失效节点清理脚本
└── README.md
```

## 参数说明（可在 workflow 中调整）

| 参数 | 位置 | 说明 |
|------|------|------|
| `MAX_PROXIES` | `free-socks5/filter_socks5.py` | 单次最多保留节点数，默认 10 |
| `TIMEOUT` | `free-socks5/filter_socks5.py` | 单节点测活超时（秒），默认 5 |
| cron | `.github/workflows/update-socks5.yml` | 执行频率，默认 `0 */4 * * *`（每4小时） |
| 提交历史 | workflow 最后一步 | 默认关闭（`if: false`），如需保留历史改为 `true` |

## 变量更新策略（只增不减 + 失效清理）

- 每次运行：先读取仓库变量 `SOCKS5_PROXY` 的现有内容，再合并本次测活成功的节点
- **去重合并**：已有节点不会被覆盖或删除（只增不减），新节点追加进去
- **失效清理**：合并后的全部节点统一再测活一次（`clean_dead.py`），剔除已失效的旧节点，
  只把仍可用的节点写回变量；若清理后全部失效（可能网络抖动），则保留原合并结果以免误删
- 合并结果按 `sort -u` 去重后写回变量

## ⚠️ 注意事项

- 免费代理时效短，**测活结果是实时的**，每 4 小时更新即是意义所在
- 公共代理不可信，**禁止用于传输敏感信息**
- `ip-api.com` 免费版限制每分钟 45 个请求，全量列表几千个 IP 时需注意限流；
  如节点太多，可先按端口/IP 段粗筛再查询
- `gh variable set` 需要 GitHub Token（`GH_TOKEN` Secret）具有 **Actions variables 写入权**（fine-grained PAT 需勾选 `Actions: Read and write`）
