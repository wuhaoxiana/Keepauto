# 代理列表

## 项目简介

发现一个在线代理网页挺好玩，代理更新比较快，我就爬来了，代理基本都是可用的，不是那种1万个代理，只有几个可以使用的垃圾。

网页 https://tomcat1235.nyc.mn/ 上比较全，有兴趣自己去爬爬看

## 功能特点

- ⚡ 自动抓取最新代理列表
- 🔄 定时更新（每天两次：北京时间早上7点 / 晚上7点）
- 📝 标准格式输出：`协议://ip:port [地址位置]`
- 🌍 包含地理位置信息
- 📊 支持多种代理协议（HTTP、SOCKS5等）
- 🎯 **地区筛选**：只保留香港、新加坡、中国的代理
- 🔑 **自动写变量**：筛选出的 SOCKS5 代理自动更新到 GitHub Actions 的 `SOCKS5_PROXY` 变量

## 使用方法

### 手动运行

```bash
python generate_proxy_list.py
```

### 查看结果

代理列表会保存在 `proxy.txt` 文件中，格式如下：

```
socks5://37.18.73.60:5566 [美国 加州 圣何塞]
http://123.143.162.221:6388 [韩国 首尔特别市]
socks5://35.183.59.99:5080 [加拿大 魁北克省 蒙特利尔]
```

## 自动更新

本项目使用 GitHub Actions 实现自动化更新：

- 🕐 每天两次自动运行（北京时间 07:00 / 19:00）
- 📝 自动提交更新的代理列表（`proxy.txt` 全部地区筛选后 / `socks5_proxy.txt` 纯 SOCKS5）
- 🔄 保持代理信息实时更新
- 🔑 筛选出的 SOCKS5 代理自动写入仓库 Variables 的 `SOCKS5_PROXY`

### 写入 SOCKS5_PROXY 变量

Workflow 需要 PAT 令牌（`GITHUB_TOKEN` 无权限写 Variables）：

1. 在 GitHub 生成 fine-grained PAT，权限勾选 **Actions: Read and write**
2. 在仓库 **Settings → Secrets and variables → Actions** 添加 Secret：
   - 名称：`PAT_TOKEN`
   - 值：上面生成的 PAT

之后每次抓取完成，仓库 Variables 里的 `SOCKS5_PROXY` 会被自动更新为筛选结果（多个代理按换行分隔；当天没有港/新/中 SOCKS5 代理时跳过更新）。

## 依赖项

- requests
- beautifulsoup4

## 免责声明

本项目仅用于学习和研究目的，请遵守相关法律法规和网站使用条款。