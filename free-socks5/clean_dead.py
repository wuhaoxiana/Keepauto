#!/usr/bin/env python3
"""
清理失效 SOCKS5 代理：读取合并后的代理列表（旧变量 + 本次新增），
并发实测可用性，剔除失效节点，只保留仍可用的节点。

用法:
    python3 clean_dead.py <input_file> <output_file>
"""
import sys
import subprocess
import concurrent.futures

# 单节点测活超时（秒）
TIMEOUT = 5
# 并发测活线程数（合并后的节点可能较多，适当调高）
MAX_WORKERS = 30


def test_proxy(proxy: str) -> bool:
    """测试代理是否可用：能否通过它访问 ipify.org。"""
    try:
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
        print("用法: python3 clean_dead.py <input_file> <output_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    with open(input_file, "r", encoding="utf-8") as f:
        proxies = [line.strip() for line in f if line.strip().startswith("socks5://")]

    print(f"待测节点数: {len(proxies)}")

    available = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(test_proxy, p): p for p in proxies}
        for fut in concurrent.futures.as_completed(futures):
            p = futures[fut]
            try:
                if fut.result():
                    available.append(p)
            except Exception:
                pass

    # 排序后输出（保证多次运行结果稳定，方便 diff）
    available.sort()
    with open(output_file, "w", encoding="utf-8") as f:
        if available:
            f.write("\n".join(available) + "\n")

    print(f"可用节点数: {len(available)}")
    print(f"失效节点已剔除: {len(proxies) - len(available)}")
    print(f"已写入: {output_file}")


if __name__ == "__main__":
    main()