#!/usr/bin/env python3
"""
TG 频道 socks5 节点抓取脚本（GitHub Actions 专用）— 免 API 版

从公开频道 @otcfxq（OTC分享群）抓取最近 N 天的 socks5/http 代理节点：
1. 通过公开网页 https://t.me/s/<频道名> 抓取（无需 TG_API_ID / 无需登录 / 无需 Session）
2. 正则提取 socks5:// 与 http(s):// 节点
3. 剔除 #标签、@otcfxq、说明文字等后缀
4. 以 ip:port 去重
5. 输出到 socks5.txt

需要的配置（环境变量）：
  CHANNEL       频道用户名（不带 @），默认 otcfxq
  FETCH_DAYS    抓取最近 N 天，默认 3
  MAX_PAGES     最多翻页数，默认 10（每页约 20 条消息）
  OUTPUT_FILE   输出文件名，默认 socks5.txt

说明：
- 公开频道（有 @用户名）的 t.me/s 网页无需任何 Telegram API 凭证即可访问
- 仅在频道为公开频道时适用；如频道转为私有，此方法失效
"""

import os
import re
import sys
import logging
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

# ================= 配置区域 =================
CHANNEL = os.getenv("CHANNEL") or "otcfxq"
FETCH_DAYS = int(os.getenv("FETCH_DAYS") or "3")
MAX_PAGES = int(os.getenv("MAX_PAGES") or "10")
OUTPUT_FILE = os.getenv("OUTPUT_FILE") or "socks5.txt"
# ============================================

# 浏览器 UA，避免被 t.me 拒绝
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# 匹配 socks5/http/https 节点 URL（user:pass@ip:port 或 ip:port）
# 示例: socks5://root:123456@59.36.149.183:1080#CN Wancheng... @otcfxq
# [^\s#@]+ 在 # 前停止 → match.group(0) 即纯净 URL（不含 #标签/@otcfxq）
NODE_RE = re.compile(
    r"(socks5|http|https)://[^\s#@]+@(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("tg-fetch")


def extract_nodes(text: str) -> list:
    """从消息文本中提取纯净节点 URL 列表（去重由调用方完成）"""
    return [m.group(0) for m in NODE_RE.finditer(text)]


def parse_page(html_text: str) -> list:
    """解析 t.me/s 页面，返回 [(datetime, text, message_id), ...]（按页面顺序）"""
    soup = BeautifulSoup(html_text, "html.parser")
    items = []
    for wrap in soup.select("div.tgme_widget_message_wrap"):
        # 消息时间
        dt = None
        time_el = wrap.select_one("time.time")
        if time_el and time_el.get("datetime"):
            try:
                dt = datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
            except ValueError:
                pass
        # 消息文本
        text_el = wrap.select_one("div.tgme_widget_message_text")
        text = text_el.get_text("\n", strip=True) if text_el else ""
        # 消息 ID（用于翻页）
        mid = None
        link_el = wrap.select_one("a.tgme_widget_message_date")
        if link_el and link_el.get("href"):
            m = re.search(r"/(\d+)$", link_el["href"])
            if m:
                mid = int(m.group(1))
        items.append((dt, text, mid))
    return items


def fetch_messages(channel: str, cutoff: datetime) -> list:
    """通过 t.me/s 网页抓取频道消息，返回 [(datetime, text), ...]（仅保留 cutoff 之后）"""
    all_msgs = []
    before_id = None
    for _ in range(MAX_PAGES):
        url = f"https://t.me/s/{channel}"
        if before_id:
            url += f"?before={before_id}"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=25)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.error("抓取 %s 失败: %s", url, e)
            break

        page_items = parse_page(resp.text)
        if not page_items:
            log.info("页面无消息，停止翻页")
            break

        for dt, text, _mid in page_items:
            if text and extract_nodes(text):
                if dt is None or dt >= cutoff:
                    all_msgs.append((dt, text))

        # 判断是否继续翻页
        ids = [mid for _, _, mid in page_items if mid]
        dates = [dt for dt, _, _ in page_items if dt]
        if not ids:
            log.info("无消息 ID，停止翻页")
            break
        oldest_id = min(ids)
        if before_id is not None and oldest_id >= before_id:
            log.info("翻页无新内容，停止")
            break
        before_id = oldest_id

        # 如果本页最早的消息已早于 cutoff，下一页只会更早，可以停止
        if dates and min(dates) < cutoff:
            log.info("已到达 cutoff 时间范围内更早的消息，停止翻页")
            break

        # 每页最多约 20 条，少于 20 说明到底了
        if len(page_items) < 20:
            log.info("已到达频道消息底部，停止翻页")
            break

    return all_msgs


def main():
    log.info("=" * 48)
    log.info("TG 节点抓取启动（免 API 网页版）")
    log.info("目标频道: @%s", CHANNEL)
    log.info("抓取范围: 最近 %d 天 | 最多翻页 %d 页", FETCH_DAYS, MAX_PAGES)

    cutoff = datetime.now(timezone.utc) - timedelta(days=FETCH_DAYS)
    messages = fetch_messages(CHANNEL, cutoff)
    log.info("获取含节点消息数: %d", len(messages))

    seen = {}
    for _dt, text in messages:
        for node in extract_nodes(text):
            # 去重: 以 ip:port 为 key（保留首次出现的完整 URL）
            ip_port = NODE_RE.match(node)
            key = f"{ip_port.group(2)}:{ip_port.group(3)}" if ip_port else node
            seen.setdefault(key, node)

    log.info("提取节点数: %d", len(seen))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for node in seen.values():
            f.write(node + "\n")

    log.info("已写入 %s (%d 个节点)", OUTPUT_FILE, len(seen))
    log.info("=" * 48)

    # 输出抓取结果到 GitHub Actions（供 workflow 判断是否跳过后续步骤）
    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"has_nodes={'true' if seen else 'false'}\n")

    if not seen:
        log.warning("未抓取到节点：工作流将跳过后续同步步骤并发送 TG 通知")
        # 不再判定为失败（exit 0），由 workflow 根据 has_nodes 分支处理：
        # 未抓取到节点 -> 跳过 9router 同步 / 只发 TG 通知
        sys.exit(0)


if __name__ == "__main__":
    main()