#!/usr/bin/env python3
"""
TG 通知：未抓取到节点（GitHub Actions 专用）

当 tg-fetch.py 未抓取到任何节点时，由 workflow 调用本脚本，
跳过后续同步步骤，仅发送一条"未抓取到节点"的 TG 通知。

需要的配置（环境变量）：
  TG_BOT_TOKEN   TG 通知机器人 Token
  TG_CHAT_ID     TG 通知接收 Chat ID
"""

import os
import logging
from datetime import datetime, timezone, timedelta

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("send-unavailable-notify")


def send_notification():
    token = os.getenv("TG_BOT_TOKEN") or ""
    chat_id = os.getenv("TG_CHAT_ID") or ""
    if not token or not chat_id:
        log.warning("未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过通知")
        return

    bjt = datetime.now(timezone(timedelta(hours=8)))
    date_str = f"{bjt.year}年{bjt.month:02d}月{bjt.day:02d}日"

    message = (
        f"⚠️ <b>9Router 节点同步：未抓取到节点</b>\n"
        f"----------------------\n"
        f"📅 <b>同步日期</b>：{date_str}\n"
        f"📭 <b>节点抓取</b>：未抓取到任何节点\n"
        f"⏭️ <b>跳过步骤</b>：9router 同步与测试\n"
        f"📄 <b>socks5-otc.txt</b> 未更新\n"
        f"\n"
        f"🔄 请检查 @otcfxq 是否正常发布节点"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        result = resp.json()
        if result.get("ok"):
            log.info("TG 通知发送成功")
        else:
            log.warning("TG 通知发送失败: %s", result.get("description", "未知错误"))
    except requests.RequestException as e:
        log.error("TG 通知请求异常: %s", e)


if __name__ == "__main__":
    send_notification()
