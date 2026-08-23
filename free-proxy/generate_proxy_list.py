#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime

# ========== 地区筛选配置 ==========
# 只保留以下地区的代理（支持中英文关键词）
FILTER_REGIONS = ['香港', '香港特别行政区', 'Hong Kong',
                  '新加坡', 'Singapore',
                  '中国', '中国大陆', 'China']

class ProxyListScraper:
    def __init__(self):
        self.url = "https://tomcat1235.nyc.mn/proxy_list"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    def _match_region(self, location):
        """判断位置信息是否命中筛选地区"""
        if not location:
            return False
        for kw in FILTER_REGIONS:
            if kw.lower() in location.lower():
                return True
        return False
    
    def _normalize_location(self, location):
        """清理位置信息中的多余文本"""
        location = location.replace('复制', '').replace('已复制', '').replace('已', '').strip()
        # 移除多余的空行、换行符和多余的空格
        location = ' '.join(location.split())
        return location
    
    def scrape_proxy_list(self):
        """抓取代理列表（全部）"""
        try:
            print(f"正在抓取代理列表: {self.url}")
            response = requests.get(self.url, headers=self.headers, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找包含代理数据的表格
            table = soup.find('table')
            if not table:
                print("未找到代理数据表格")
                return []
            
            proxies = []
            rows = table.find_all('tr')[1:]  # 跳过表头
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 4:  # 需要至少4列：协议、IP、端口、位置
                    protocol = cells[0].text.strip()
                    ip = cells[1].text.strip()
                    port = cells[2].text.strip()
                    location = cells[3].text.strip() if len(cells) > 3 else "未知"
                    
                    # 清理位置信息
                    location = self._normalize_location(location)
                    
                    if protocol and ip and port:
                        # 使用标准代理格式：协议://ip:port [地址位置]
                        proxy = f"{protocol}://{ip}:{port} [{location}]"
                        proxies.append(proxy)
            
            print(f"成功抓取到 {len(proxies)} 个代理（全部地区）")
            return proxies
            
        except requests.RequestException as e:
            print(f"网络请求错误: {e}")
            return []
        except Exception as e:
            print(f"抓取错误: {e}")
            return []
    
    def filter_by_region(self, proxies):
        """按地区筛选代理：只保留香港、新加坡、中国"""
        filtered = []
        skipped = []
        for proxy in proxies:
            # 去掉 协议://ip:port 前缀，剩余部分视为位置信息（兼容带/不带括号）
            # 例：socks5://1.2.3.4:1080 [机房] 新加坡 新加坡 -> 位置 "[机房] 新加坡 新加坡"
            if '://' in proxy:
                location = proxy.split('://', 1)[1].split(' ', 1)[1] if ' ' in proxy.split('://', 1)[1] else ''
            else:
                location = proxy
            if self._match_region(location):
                filtered.append(proxy)
            else:
                skipped.append(location)
        print(f"地区筛选：命中 {len(filtered)} 个（香港/新加坡/中国），排除 {len(skipped)} 个")
        return filtered
    
    def save_to_file(self, proxies, filename='proxy.txt'):
        """保存代理列表到文件（仅筛选后的地区）"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                # 写入时间戳
                f.write(f"# 代理列表更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 总计: {len(proxies)} 个代理（仅香港/新加坡/中国）\n\n")
                
                # 写入代理列表 (标准格式：协议://ip:port [地址位置])
                for proxy in proxies:
                    f.write(f"{proxy}\n")
            
            print(f"代理列表已保存到 {filename}")
            return True
            
        except Exception as e:
            print(f"保存文件错误: {e}")
            return False
    
    def save_socks5_only(self, proxies, filename='socks5_proxy.txt'):
        """保存仅 socks5 协议的代理纯净列表（用于写入 SOCKS5_PROXY 变量）"""
        try:
            socks5 = []
            for proxy in proxies:
                if proxy.lower().startswith('socks5://'):
                    # 去掉 [位置] 注释，只留 socks5://ip:port
                    clean = proxy.split(' [', 1)[0].strip()
                    socks5.append(clean)
            
            with open(filename, 'w', encoding='utf-8') as f:
                for p in socks5:
                    f.write(f"{p}\n")
            
            print(f"SOCKS5 代理列表已保存到 {filename}（{len(socks5)} 个）")
            return True
        except Exception as e:
            print(f"保存 SOCKS5 文件错误: {e}")
            return False


def main():
    """主函数"""
    scraper = ProxyListScraper()
    
    # 抓取代理列表（全部）
    proxies = scraper.scrape_proxy_list()
    
    if proxies:
        # 地区筛选：只保留香港、新加坡、中国
        filtered = scraper.filter_by_region(proxies)
        
        # 保存筛选后的完整列表
        scraper.save_to_file(filtered)
        
        # 保存纯 socks5 列表（供 SOCKS5_PROXY 变量使用）
        scraper.save_socks5_only(filtered)
        
        print(f"代理列表抓取完成！最终保留 {len(filtered)} 个（仅香港/新加坡/中国）")
    else:
        print("未能获取到代理数据")


if __name__ == "__main__":
    main()