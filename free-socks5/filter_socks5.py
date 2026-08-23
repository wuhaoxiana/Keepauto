#!/usr/bin/env python3
"""
从 proxifly/free-proxy-list 的 socks5 data.txt 中筛选出香港(HK)、新加坡(SG)、中国(CN)的可用节点。
输出格式：每行一个 socks5://ip:port，供 GitHub Actions 写入环境变量。

筛选策略（三层粗筛，尽量少调 ip-api 免费接口）:
  0. 端口粗筛: 剔除 EXCLUDE_PORTS 中的端口
  1. IP段粗筛: 命中内置 CIDR 段表 -> 直接确定国家，零 API 请求
  2. 批量兜底: 未命中段的 IP 走 ip-api.com/batch 批量查询（每批最多 100 个）

用法:
    python3 filter_socks5.py <input_file> <output_file>
"""
import sys
import subprocess
import concurrent.futures
import re
import os
import json
import ipaddress

# 需要筛选的国家（ISO 3166-1 alpha-2）
TARGET_COUNTRIES = {"HK", "SG", "CN"}
# 输出优先级顺序（越靠前越先保留）
COUNTRY_ORDER = ["HK", "SG", "CN"]
# 最大保留节点数
MAX_PROXIES = 10
# 每个代理测试超时（秒）
TIMEOUT = 5
# 端口粗筛：先剔除这些端口的节点，再查询归属地（减少 ip-api 免费版每分钟 45 次限制的压力）
EXCLUDE_PORTS = {1080}

# IP 段粗筛表：常见云厂商/ISP 的香港、新加坡、中国网段（CIDR -> 国家）
# 命中直接判国，不消耗 ip-api 请求；未命中的会走批量兜底查询。
IP_SEGMENTS = {
    "HK": [
        # 阿里云香港
        "47.74.0.0/16", "47.75.0.0/16", "47.91.0.0/16", "47.92.0.0/16",
        "47.98.0.0/16", "47.244.0.0/16", "47.238.0.0/16",
        "8.210.0.0/16", "8.211.0.0/16", "8.212.0.0/16", "8.213.0.0/16",
        "8.214.0.0/16", "8.215.0.0/16",
        # 腾讯云香港
        "119.28.0.0/16", "123.58.0.0/16", "129.226.0.0/16",
        "43.131.0.0/16", "43.132.0.0/16", "43.134.0.0/16", "43.136.0.0/16",
        "43.137.0.0/16", "43.138.0.0/16", "43.139.0.0/16", "43.140.0.0/16",
        "43.141.0.0/16", "43.142.0.0/16", "43.143.0.0/16", "43.144.0.0/16",
        "43.145.0.0/16", "43.146.0.0/16", "43.147.0.0/16", "43.148.0.0/16",
        "43.149.0.0/16", "43.150.0.0/16", "43.151.0.0/16", "43.152.0.0/16",
        "43.153.0.0/16", "43.154.0.0/16", "43.155.0.0/16",
        # 其他香港常见段
        "157.254.0.0/16", "45.194.0.0/16", "45.64.0.0/16", "103.20.0.0/16",
        "103.144.0.0/16", "27.124.0.0/16", "116.48.0.0/16", "203.80.0.0/16",
    ],
    "SG": [
        # 阿里云新加坡
        "47.236.0.0/16", "47.237.0.0/16",
        "8.219.0.0/16", "8.220.0.0/16", "8.221.0.0/16",
        # 腾讯云新加坡
        "43.156.0.0/16", "43.163.0.0/16",
        # Oracle 新加坡
        "140.245.0.0/16",
        # DigitalOcean / Vultr / GCP 新加坡
        "159.65.0.0/16", "128.199.0.0/16", "178.128.0.0/16",
        "45.32.0.0/16", "139.180.0.0/16", "34.124.0.0/16",
    ],
    "CN": [
        # 注意：CN 不能再用 /8 大段粗筛（121/203/210/211 等段混有韩国、日本、
        # 台湾、澳洲地址，实测 121.169.x.x 是 Korea Telecom 韩国节点被误判）。
        # 这里只保留实测确认的中国 /16 段，其余 CN 节点靠 ip-api batch 兜底。
        "59.38.0.0/16", "59.46.0.0/16", "175.27.0.0/16", "203.25.0.0/16",
        # 腾讯云国内段（确认在中国大陆）
        "43.142.0.0/16", "43.143.0.0/16",
        # 阿里云国内段
        "47.92.0.0/16", "47.93.0.0/16", "47.94.0.0/16", "47.95.0.0/16",
        "47.96.0.0/16", "47.97.0.0/16", "47.98.0.0/16", "47.99.0.0/16",
        "47.100.0.0/16", "47.101.0.0/16", "47.102.0.0/16", "47.103.0.0/16",
        "47.104.0.0/16", "47.105.0.0/16", "47.106.0.0/16", "47.107.0.0/16",
        "47.108.0.0/16", "47.109.0.0/16", "47.110.0.0/16", "47.111.0.0/16",
        "47.112.0.0/16", "47.113.0.0/16", "47.114.0.0/16", "47.115.0.0/16",
        "47.116.0.0/16", "47.117.0.0/16", "47.118.0.0/16", "47.119.0.0/16",
        "47.120.0.0/16", "47.121.0.0/16", "47.122.0.0/16", "47.123.0.0/16",
        "47.124.0.0/16", "47.125.0.0/16", "47.126.0.0/16", "47.127.0.0/16",
    ],
}

# 预编译 CIDR 网络对象
_IP_NETWORKS = {
    cc: [ipaddress.ip_network(cidr) for cidr in cidrs]
    for cc, cidrs in IP_SEGMENTS.items()
}


def get_country_by_segment(ip: str):
    """IP 段粗筛：命中内置段表返回国家代码，未命中返回 None。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    for cc, nets in _IP_NETWORKS.items():
        for net in nets:
            if addr in net:
                return cc
    return None


def get_ip_geo_batch(ips):
    """批量查询 IP 归属地（ip-api.com/batch，每批最多 100 个）。
    返回 {ip: countryCode}；失败时返回 {}（调用方自行兜底）。
    """
    if not ips:
        return {}
    result = {}
    try:
        body = json.dumps([{"query": ip} for ip in ips])
        out = subprocess.run(
            ["curl", "-s", "--max-time", "15", "-X", "POST",
             "http://ip-api.com/batch",
             "-H", "Content-Type: application/json",
             "-d", body],
            capture_output=True, text=True, timeout=20
        )
        data = json.loads(out.stdout)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("status") == "success":
                    ip = item.get("query", "")
                    cc = item.get("countryCode", "")
                    if ip and cc:
                        result[ip] = cc
    except Exception:
        pass
    return result


def get_ip_geo_single(ip: str) -> str:
    """单个 IP 归属地查询（批量失败时的兜底；仅少量 IP 时会用到）。"""
    try:
        out = subprocess.run(
            ["curl", "-s", "--max-time", "4", f"http://ip-api.com/json/{ip}"],
            capture_output=True, text=True, timeout=6
        )
        data = json.loads(out.stdout)
        if data.get("status") == "success":
            return data.get("countryCode", "")
    except Exception:
        pass
    return ""


def test_proxy(proxy: str) -> bool:
    """测试代理是否可用：能否通过它访问 ipify.org。"""
    try:
        # 去掉 socks5:// 前缀
        host = proxy.split("//")[1]
        out = subprocess.run(
            ["curl", "-s", "--max-time", str(TIMEOUT), "--socks5-hostname", host, "https://api.ipify.org"],
            capture_output=True, text=True, timeout=TIMEOUT + 2
        )
        ip = out.stdout.strip()
        return bool(ip and ip != "null")
    except Exception:
        return False


def main():
    if len(sys.argv) < 3:
        print("用法: python3 filter_socks5.py <input_file> <output_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    with open(input_file, "r", encoding="utf-8") as f:
        proxies = [line.strip() for line in f if line.strip().startswith("socks5://")]

    print(f"原始节点数: {len(proxies)}")

    # 0. 端口粗筛
    proxy_pattern = re.compile(r"socks5://([\d.]+):(\d+)")
    before = len(proxies)
    proxies = [
        p for p in proxies
        if (m := proxy_pattern.match(p)) and int(m.group(2)) not in EXCLUDE_PORTS
    ]
    print(f"端口粗筛(剔除 {sorted(EXCLUDE_PORTS)}): {before} -> {len(proxies)}")

    # 1. IP 段粗筛：命中直接判国；未命中的收集起来走批量查询
    country_map = {}      # ip -> cc
    segment_hit = 0       # 段表命中数（零 API）
    batch_ips = set()     # 需要批量查询的 IP
    ip_to_proxy = {}      # ip -> 该 ip 的所有代理（去重保留）
    for p in proxies:
        m = proxy_pattern.match(p)
        if not m:
            continue
        ip = m.group(1)
        ip_to_proxy.setdefault(ip, p)
        cc = get_country_by_segment(ip)
        if cc:
            country_map[ip] = cc
            segment_hit += 1
        else:
            batch_ips.add(ip)

    print(f"IP段粗筛命中: {segment_hit} 个 IP（零 API 请求）")

    # 2. 批量兜底查询（ip-api batch，每批 ≤100）
    batch_list = list(batch_ips)
    batch_map = {}
    if batch_list:
        print(f"批量查询归属地: {len(batch_list)} 个 IP（ip-api batch）")
        for i in range(0, len(batch_list), 100):
            chunk = batch_list[i:i+100]
            batch_map.update(get_ip_geo_batch(chunk))
        # 批量失败的少量剩余 IP 用单查兜底（通常不会走到这）
        leftover = [ip for ip in batch_list if ip not in batch_map]
        if leftover and len(leftover) <= 20:
            print(f"批量未命中，单查兜底: {len(leftover)} 个 IP")
            for ip in leftover:
                cc = get_ip_geo_single(ip)
                if cc:
                    batch_map[ip] = cc
    for ip, cc in batch_map.items():
        if cc in TARGET_COUNTRIES:
            country_map[ip] = cc

    # 3. 过滤出目标国家的代理
    filtered = []
    for p in proxies:
        m = proxy_pattern.match(p)
        if m and m.group(1) in country_map:
            filtered.append((p, country_map[m.group(1)]))

    print(f"香港/新加坡/中国节点: {len(filtered)}")

    # 4. 并发测试可用性
    available = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(test_proxy, p): (p, cc) for p, cc in filtered}
        for fut in concurrent.futures.as_completed(futures):
            p, cc = futures[fut]
            try:
                if fut.result():
                    available.append((p, cc))
            except Exception:
                pass

    print(f"可用节点数: {len(available)}")

    # 5. 按国家优先级排序，同国家内按 IP 排序
    order_map = {cc: i for i, cc in enumerate(COUNTRY_ORDER)}
    available.sort(key=lambda x: (order_map.get(x[1], 999), x[0]))

    # 6. 截断到 MAX_PROXIES
    final = [p for p, _ in available[:MAX_PROXIES]]

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(final) + "\n")

    print(f"最终写入: {len(final)} 个节点 -> {output_file}")
    print("写入内容预览:")
    for p in final[:10]:
        print(f"  {p}")
    if len(final) > 10:
        print(f"  ... 共 {len(final)} 条")


if __name__ == "__main__":
    main()
