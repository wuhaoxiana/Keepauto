#!/usr/bin/env python3

import os
import sys
import time
import traceback
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# 环境变量配置
AGENTROUTER_USERNAME = os.getenv("AGENTROUTER_USERNAME") or ""
AGENTROUTER_PASSWORD = os.getenv("AGENTROUTER_PASSWORD") or ""
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN") or ""
TG_CHAT_ID = os.getenv("TG_CHAT_ID") or ""

# 代理配置（可选）
PROXY_SERVER = os.getenv("PROXY_SERVER") or ""  # 格式: http://host:port 或 socks5://host:port
PROXY_AGENTROUTER_USERNAME = os.getenv("PROXY_AGENTROUTER_USERNAME") or ""  # 代理用户名（如果需要）
PROXY_AGENTROUTER_PASSWORD = os.getenv("PROXY_AGENTROUTER_PASSWORD") or ""  # 代理密码（如果需要）

SITE_URL = "https://agentrouter.org"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

def log(level: str, msg: str):
    """带时间戳的日志输出"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)

def send_telegram(message: str) -> bool:
    """发送 Telegram 消息"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log("WARN", "Telegram 配置不完整，跳过发送")
        print(f"--- 消息内容 ---\n{message}\n---------------")
        return False

    try:
        import requests
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TG_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }
        resp = requests.post(url, json=data, timeout=30)
        resp.raise_for_status()
        log("INFO", "Telegram 消息发送成功")
        return True
    except Exception as e:
        log("ERROR", f"Telegram 发送失败: {e}")
        return False

def wait_for_waf_ready(page, context=None, timeout_ms: int = 45000) -> bool:
    """
    等待 WAF / 人机验证自动通过，直到出现真实登录界面。
    阿里云 WAF（acw_sc__v2 等）会在挑战页运行 JS 生成验证 Cookie，
    一旦 Cookie 生成而页面未自动跳转，则主动刷新进入真实页面。
    """
    WAF_COOKIE_NAMES = ("acw_tc", "cdn_sec_tc", "acw_sc__v2", "__jsluid_s", "__cf_bm")
    log("INFO", "检测 WAF / 人机验证状态...")
    deadline = time.time() + timeout_ms / 1000.0
    start_time = time.time()
    challenge_logged = False
    reload_count = 0
    last_reload_time = 0.0
    last_progress_log = 0

    while time.time() < deadline:
        try:
            state = page.evaluate("""
                () => {
                    const bodyText = (document.body && document.body.innerText) || '';
                    const hasInputs = document.querySelectorAll('input').length > 0;
                    const hasLoginButton = /Sign in with Email|Log In|登录/.test(bodyText);
                    const challengeSelectors = [
                        '#challenge-form', '.cf-challenge', '#cf-challenge-running',
                        'iframe[src*="challenges.cloudflare.com"]',
                        '[class*="turnstile"]', '[class*="captcha"]'
                    ];
                    const isChallenge = challengeSelectors.some(sel => !!document.querySelector(sel))
                        || /challenge|verify you are human|attention required|verification/i.test(bodyText.slice(0, 300))
                        || document.title.toLowerCase().includes('verification');
                    return {
                        hasInputs,
                        hasLoginButton,
                        isChallenge,
                        readyState: document.readyState,
                        url: location.href
                    };
                }
            """)
        except Exception:
            page.wait_for_timeout(1000)
            continue

        if state.get("hasInputs") or state.get("hasLoginButton"):
            log("INFO", "WAF 验证通过，登录界面已就绪")
            return True

        if state.get("isChallenge"):
            if not challenge_logged:
                log("WARN", "检测到人机验证/挑战页，等待其自动通过...")
                challenge_logged = True

            elapsed = int(time.time() - start_time)

            # WAF Cookie 已生成但页面仍停留在挑战页时，主动刷新进入真实页面
            if context is not None and reload_count < 3 and (time.time() - last_reload_time) >= 10:
                try:
                    cookie_names = {c.get("name") for c in context.cookies()}
                    if any(name in cookie_names for name in WAF_COOKIE_NAMES):
                        log("INFO", "WAF Cookie 已生成，刷新页面进入登录界面...")
                        page.reload(wait_until="domcontentloaded", timeout=30000)
                        reload_count += 1
                        last_reload_time = time.time()
                except Exception:
                    pass

            # 每 10 秒汇报一次进度，避免刷屏
            if elapsed >= 10 and elapsed - last_progress_log >= 10:
                log("INFO", f"  仍在等待 WAF 验证通过（已等待 {elapsed}s）...")
                last_progress_log = elapsed

        page.wait_for_timeout(1000)

    log("WARN", "等待 WAF 验证超时，继续尝试登录...")
    return False


def click_email_login_button(page, timeout_ms: int = 15000) -> bool:
    """
    点击 "Sign in with Email or Username" 切换按钮，
    点击后页面才会出现用户名/密码输入框。
    """
    log("INFO", "切换邮箱/用户名登录方式...")

    # 优先使用 Playwright 文本定位
    try:
        target = page.get_by_text("Sign in with Email or Username")
        target.first.wait_for(state="visible", timeout=timeout_ms)
        target.first.click(timeout=10000)
        log("INFO", "  ✓ 已点击邮箱/用户名登录按钮")
        return True
    except Exception:
        pass

    # 回退：通过 JS 在按钮/选项卡中查找并点击
    try:
        clicked = page.evaluate("""
            () => {
                const candidates = Array.from(
                    document.querySelectorAll('button, [role="tab"], a, span, div')
                );
                const target = candidates.find(el => {
                    const text = (el.innerText || '').trim();
                    return text === 'Sign in with Email or Username'
                        || text.includes('Email or Username')
                        || text === 'Sign in with Email';
                });
                if (target) {
                    target.click();
                    return true;
                }
                return false;
            }
        """)
        if clicked:
            log("INFO", "  ✓ 已通过脚本点击邮箱/用户名登录按钮")
            return True
    except Exception:
        pass

    log("WARN", "未找到邮箱/用户名登录按钮，可能表单已直接显示")
    return False


def browser_login_complete() -> dict | None:
    """
    使用 Playwright 完成整个登录流程。
    支持代理配置绕过 WAF 检测。
    """
    log("INFO", f"使用浏览器自动化登录 {SITE_URL}...")

    # 配置代理
    proxy_config = None
    if PROXY_SERVER:
        proxy_config = {
            "server": PROXY_SERVER,
        }
        if PROXY_AGENTROUTER_USERNAME and PROXY_AGENTROUTER_PASSWORD:
            proxy_config["username"] = PROXY_AGENTROUTER_USERNAME
            proxy_config["password"] = PROXY_AGENTROUTER_PASSWORD
        log("INFO", f"使用代理: {PROXY_SERVER}")

    result = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ],
            proxy=proxy_config,  # 设置代理
        )

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=USER_AGENT,
        )

        page = context.new_page()

        try:
            # Step 1: 访问登录页面
            log("INFO", "Step 1: 访问登录页面...")
            page.goto(f"{SITE_URL}/login", wait_until="domcontentloaded", timeout=45000)

            # Step 2: 等待 WAF / 人机验证自动通过，直到登录界面渲染完成
            log("INFO", "Step 2: 等待页面渲染及 WAF 验证通过...")
            wait_for_waf_ready(page, context=context, timeout_ms=45000)

            # 检查页面状态
            page_info = page.evaluate("""
                () => {
                    return {
                        url: window.location.href,
                        title: document.title,
                        readyState: document.readyState,
                        bodyText: document.body?.innerText?.substring(0, 300) || '',
                        hasInputs: document.querySelectorAll('input').length,
                        hasButtons: document.querySelectorAll('button').length,
                        hasForm: !!document.querySelector('form'),
                        htmlPreview: document.documentElement.outerHTML.substring(0, 500)
                    };
                }
            """)

            log("INFO", f"  当前 URL: {page_info.get('url')}")
            log("INFO", f"  页面标题: {page_info.get('title')}")
            log("INFO", f"  输入框数量: {page_info.get('hasInputs')}")
            log("INFO", f"  按钮数量: {page_info.get('hasButtons')}")

            # 如果页面没有输入框，尝试点击 "Sign in with Email or Username" 切换登录方式
            if page_info.get('hasInputs') == 0:
                if not click_email_login_button(page):
                    log("ERROR", f"页面没有输入框且未找到登录切换按钮！")
                    log("ERROR", f"页面文本预览: {page_info.get('bodyText')}")
                    log("ERROR", f"HTML 预览: {page_info.get('htmlPreview')}")

                    try:
                        screenshot_path = "page_error.png"
                        page.screenshot(path=screenshot_path, full_page=True)
                        log("INFO", f"已保存页面截图: {screenshot_path}")
                    except:
                        pass

                    raise Exception(f"登录页面加载异常，没有找到表单元素")

                # 点击切换后等待表单出现
                page.wait_for_timeout(1500)

            # Step 3: 填写表单（使用更宽松的等待策略）
            log("INFO", "Step 3: 填写登录表单...")

            # 使用 page.evaluate 等待元素真正可见
            wait_result = page.evaluate("""
                async () => {
                    let attempts = 0;
                    const maxAttempts = 30; // 最多等待 15 秒

                    while (attempts < maxAttempts) {
                        const username = document.querySelector('input#username');
                        const password = document.querySelector('input#password');
                        const submit = document.querySelector('button[type="submit"]');

                        if (username && password && submit &&
                            username.offsetParent !== null &&
                            password.offsetParent !== null &&
                            submit.offsetParent !== null) {
                            return {
                                success: true,
                                waitTime: attempts * 500
                            };
                        }

                        await new Promise(resolve => setTimeout(resolve, 500));
                        attempts++;
                    }

                    return {
                        success: false,
                        hasUsername: !!document.querySelector('input#username'),
                        hasPassword: !!document.querySelector('input#password'),
                        hasSubmit: !!document.querySelector('button[type="submit"]')
                    };
                }
            """)

            if not wait_result.get("success"):
                raise Exception(f"表单元素未出现: {wait_result}")

            log("INFO", f"  表单元素已就绪（等待 {wait_result.get('waitTime')}ms）")

            # 填写用户名（使用 locator 并等待）
            try:
                username_locator = page.locator('input#username')
                username_locator.wait_for(state="visible", timeout=5000)
                username_locator.click(timeout=5000)
                username_locator.fill(AGENTROUTER_USERNAME, timeout=5000)
                log("INFO", "  ✓ 已填写用户名")
            except Exception as e:
                raise Exception(f"填写用户名失败: {e}")

            # 等待一下
            page.wait_for_timeout(500)

            # 填写密码
            try:
                password_locator = page.locator('input#password')
                password_locator.wait_for(state="visible", timeout=5000)
                password_locator.click(timeout=5000)
                password_locator.fill(AGENTROUTER_PASSWORD, timeout=5000)
                log("INFO", "  ✓ 已填写密码")
            except Exception as e:
                raise Exception(f"填写密码失败: {e}")

            # 等待一下
            page.wait_for_timeout(1000)

            # Step 4: 点击提交按钮
            log("INFO", "Step 4: 点击提交按钮...")
            try:
                submit_locator = page.locator('button[type="submit"]')
                submit_locator.wait_for(state="visible", timeout=5000)
                submit_locator.click(timeout=5000)
                log("INFO", "  ✓ 已点击提交按钮")
            except Exception as e:
                raise Exception(f"点击提交按钮失败: {e}")

            # Step 5: 等待登录完成
            log("INFO", "Step 5: 等待登录响应...")
            page.wait_for_timeout(3000)

            # 检查是否有滑块验证
            has_captcha = page.evaluate("""
                () => !!document.querySelector('#nc_1_n1z, .nc-container, [class*="captcha"]')
            """)

            if has_captcha:
                log("WARN", "检测到滑块验证码，等待处理...")
                page.wait_for_timeout(5000)

            current_url = page.url
            log("INFO", f"  当前 URL: {current_url}")

            # Step 6: 使用登录后的浏览器会话调用用户信息接口
            log("INFO", "Step 6: 获取用户信息...")

            api_result = page.evaluate("""
                async () => {
                    try {
                        let userStr = null;
                        for (let attempt = 0; attempt < 10; attempt++) {
                            userStr = localStorage.getItem('user');
                            if (userStr) break;
                            await new Promise(resolve => setTimeout(resolve, 500));
                        }

                        if (!userStr) {
                            return { success: false, error: '登录后未找到用户 ID' };
                        }

                        const localUser = JSON.parse(userStr);
                        if (!localUser.id) {
                            return { success: false, error: '登录用户 ID 无效' };
                        }

                        const response = await fetch('/api/user/self', {
                            method: 'GET',
                            headers: {
                                'Accept': 'application/json, text/plain, */*',
                                'New-API-User': String(localUser.id)
                            },
                            credentials: 'include',
                            cache: 'no-store'
                        });

                        let payload;
                        try {
                            payload = await response.json();
                        } catch (err) {
                            return {
                                success: false,
                                status: response.status,
                                error: '用户信息接口未返回 JSON'
                            };
                        }

                        return {
                            success: response.ok,
                            status: response.status,
                            payload
                        };
                    } catch (err) {
                        return {
                            success: false,
                            error: err.toString()
                        };
                    }
                }
            """)

            if not api_result.get("success"):
                status = api_result.get("status")
                error = api_result.get("error") or "请求失败"
                if status:
                    raise Exception(f"获取用户信息失败（HTTP {status}）: {error}")
                raise Exception(f"获取用户信息失败: {error}")

            payload = api_result.get("payload")
            if not isinstance(payload, dict) or payload.get("success") is not True:
                message = payload.get("message") if isinstance(payload, dict) else "响应格式错误"
                raise Exception(f"获取用户信息失败: {message or '接口返回失败'}")

            user_data = payload.get("data")
            if not isinstance(user_data, dict):
                raise Exception("获取用户信息失败: 响应中缺少 data")

            quota = user_data.get("quota")
            if isinstance(quota, bool) or not isinstance(quota, (int, float)):
                raise Exception("获取用户信息失败: data.quota 不是有效数字")

            result = {
                "user_id": user_data.get("id", 0),
                "username": user_data.get("username") or AGENTROUTER_USERNAME,
                "quota": quota,
                "checked_in": None,
            }
            log("INFO", "  ✓ 已从 /api/user/self 获取用户信息")
            log("INFO", f"  ✓ 用户 ID: {result['user_id']}")
            log("INFO", f"  ✓ 用户名: {result['username']}")
            log("INFO", f"  ✓ quota: {result['quota']}")

        except PlaywrightTimeoutError as e:
            log("ERROR", f"页面操作超时: {e}")
            log("ERROR", f"当前 URL: {page.url}")
            # 截图用于调试
            try:
                screenshot_path = "error_screenshot.png"
                page.screenshot(path=screenshot_path)
                log("INFO", f"已保存错误截图: {screenshot_path}")
            except:
                pass

        except Exception as e:
            log("ERROR", f"浏览器自动化登录失败: {e}")
            log("ERROR", traceback.format_exc())

        finally:
            browser.close()

    return result

def format_balance(quota: int) -> str:
    """将 quota 转换为美元显示（假设 500000 = $1）"""
    if quota is None:
        return "N/A"
    balance = quota / 500000
    return f"{balance:.2f}$"

def run_checkin():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log("INFO", "=" * 50)
    log("INFO", "AgentRouter 登录签到脚本启动")
    log("INFO", f"时间: {now_str}")
    log("INFO", f"用户名: {AGENTROUTER_USERNAME}")
    log("INFO", "=" * 50)

    if not AGENTROUTER_USERNAME or not AGENTROUTER_PASSWORD:
        log("ERROR", "AGENTROUTER_USERNAME 或 AGENTROUTER_PASSWORD 未配置，请设置环境变量")
        sys.exit(1)

    # ---------- Step 1: 使用浏览器自动化登录（登录即签到）----------
    login_result = browser_login_complete()

    if not login_result:
        log("ERROR", "浏览器自动化登录失败")
        send_telegram(
            f"❌ <b>AgentRouter 登录失败</b>\n"
            f"👤 账户: {AGENTROUTER_USERNAME}\n"
            f"⏱️ 时间: {now_str}\n"
            f"📝 原因: 浏览器自动化登录失败"
        )
        sys.exit(1)

    user_id = login_result.get("user_id", 0)
    username = login_result.get("username", AGENTROUTER_USERNAME)
    balance = format_balance(login_result.get("quota", 0))

    log("INFO", f"✅ 登录成功！")
    log("INFO", f"用户 ID: {user_id}")
    log("INFO", f"用户名: {username}")
    log("INFO", f"当前余额: {balance}")
    log("INFO", f"🎁 通过登录完成签到")

    # ---------- Step 2: 发送 Telegram 通知 ----------
    message = (
        f"🎁 <b>AgentRouter 签到通知</b>\n\n"
        f"👤 登录账户: {AGENTROUTER_USERNAME}\n"
        f"💰 当前余额: {balance}\n"
        f"📋 状态: 通过登录完成签到\n"
        f"⏱️ 时间: {now_str}"
    )

    send_telegram(message)

    log("INFO", "=== 脚本执行完毕 ===")

def main():
    try:
        run_checkin()
    except KeyboardInterrupt:
        log("WARN", "用户中断")
        sys.exit(130)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        log("ERROR", f"脚本执行出错: {error_msg}")
        log("ERROR", traceback.format_exc())
        send_telegram(
            f"❌ <b>AgentRouter 脚本异常</b>\n"
            f"👤 账户: {AGENTROUTER_USERNAME}\n"
            f"⏱️ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📝 错误: {error_msg}"
        )
        sys.exit(1)

if __name__ == "__main__":
    main()
