from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import uuid
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from ..core.time import now_ms


def _clear_chrome_profile_lock(profile_dir: str = "/opt/chrome-cdp") -> None:
    try:
        for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            path = Path(profile_dir) / name
            if path.exists():
                path.unlink()
    except Exception:
        pass

def _kill_all_chrome():
    """杀掉所有 Chrome/Chromium 进程，确保只有一个实例"""
    try:
        subprocess.run(["pkill", "-9", "-f", "chromium"], capture_output=True)
        subprocess.run(["pkill", "-9", "-f", "chrome"], capture_output=True)
        time.sleep(0.5)
    except:
        pass


def _count_chrome_processes() -> int:
    """统计当前 Chrome/Chromium 进程数"""
    try:
        result = subprocess.run(
            ["pgrep", "-c", "-f", "chrom"],
            capture_output=True, text=True
        )
        return int(result.stdout.strip() or 0)
    except:
        return 0


class BinanceSession:
    def __init__(
        self,
        cdp_url: str,
        api_base: str,
        auth_mode: str = "cdp",
        cookie_path: str = "cookies.json",
        user_agent: str = "",
        extra_headers: Optional[Dict[str, str]] = None,
        request_timeout_ms: int = 10000,
    ) -> None:
        self.cdp_url = cdp_url
        self.api_base = api_base.rstrip("/")
        self.auth_mode = auth_mode
        self.cookie_path = Path(cookie_path)
        self.user_agent = user_agent
        self.extra_headers = extra_headers or {}
        self.request_timeout_ms = request_timeout_ms
        self._playwright = None
        self._browser = None
        self._context = None
        self._client: Optional[httpx.AsyncClient] = None
        self._cookie_mtime: Optional[float] = None
        self._cookie_cache: Dict[str, str] = {}
        self._header_cache: Dict[str, str] = {}
        self._capture_attached = False
        self.connected = False
        self.last_error: Optional[str] = None
        self.time_offset_ms = 0
        self._last_health_check = 0
        self._health_check_interval = 10000  # 优化：从30秒降到10秒
        self._reconnect_count = 0
        self._keepalive_task = None
        self._keepalive_interval = 5  # 5秒心跳间隔
        self._external_context = False
        self._session_initialized = False  # 标记是否已初始化登录态

    async def connect(self) -> bool:
        if self.connected:
            return True
        # Cleanup old Playwright instances before reconnecting.
        await self._cleanup_resources()
        if self.auth_mode != "cdp":
            try:
                await self._ensure_cookie_client(force=True)
            except Exception as exc:
                self.connected = False
                self.last_error = str(exc)
                return False
            self.connected = True
            self.last_error = None
            return True
        use_external_cdp = self.auth_mode == "cdp" and bool(self.cdp_url)
        if not use_external_cdp:
            _kill_all_chrome()
        try:
            from playwright.async_api import async_playwright
            import asyncio

            self._playwright = await async_playwright().start()
            if use_external_cdp:
                try:
                    browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
                    self._browser = browser
                    if browser.contexts:
                        self._context = browser.contexts[0]
                    else:
                        self._context = await browser.new_context()
                    self._external_context = True
                except Exception as exc:
                    self.last_error = f"CDP connect failed: {exc}"
                    await self._cleanup_resources()
                    self.connected = False
                    return False
            else:
                _kill_all_chrome()
                _clear_chrome_profile_lock()
                self._browser = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir="/opt/chrome-cdp",
                    headless=True,
                    channel="chrome",
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )
                self._context = self._browser
                self._external_context = False

            self._attach_header_capture()
            self.connected = True
            self.last_error = None
            self._last_health_check = now_ms()
            if self._keepalive_task is None or self._keepalive_task.done():
                self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            return True
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            return False

    async def _cleanup_resources(self):
        """清理所有 Playwright 资源"""
        try:
            if self._context and self._context != self._browser and not self._external_context:
                await self._context.close()
        except:
            pass
        try:
            if self._browser and not self._external_context:
                await self._browser.close()
        except:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except:
            pass
        self._playwright = None
        self._browser = None
        self._context = None
        self._capture_attached = False

    async def _check_browser_health(self) -> bool:
        """检查浏览器是否健康"""
        now = now_ms()
        if now - self._last_health_check < self._health_check_interval:
            return True
        self._last_health_check = now

        try:
            if not self._browser or not self._context:
                return False
            # 检查是否有可用页面
            if self._context.pages:
                page = self._context.pages[0]
                await page.evaluate("() => true", timeout=5000)
            return True
        except:
            return False

    async def _ensure_browser_alive(self) -> bool:
        """确保浏览器存活，崩溃时自动重连"""
        if await self._check_browser_health():
            return True

        # 浏览器崩溃，重连
        self._reconnect_count += 1
        self.connected = False
        await self._cleanup_resources()
        return await self.connect()

    async def _keepalive_loop(self) -> None:
        """后台心跳任务，定期检查浏览器健康状态"""
        import asyncio
        while self.connected:
            await asyncio.sleep(self._keepalive_interval)
            try:
                if self._context and self._context.pages:
                    page = self._context.pages[0]
                    await page.evaluate("() => Date.now()", timeout=3000)
                    self._last_health_check = now_ms()
            except Exception:
                # 浏览器可能已崩溃，标记为断开
                self.connected = False
                break

    async def _reconnect(self) -> bool:
        """快速重连"""
        await self._cleanup_resources()
        for attempt in range(3):
            if await self.connect():
                return True
            import asyncio
            await asyncio.sleep(1)
        return False

    async def _load_cookies_to_context(self) -> None:
        """从 cookie 文件加载 cookies 到浏览器上下文"""
        if not self.cookie_path.exists():
            return
        try:
            data = json.loads(self.cookie_path.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and "cookies" in data:
                cookies = data["cookies"]
            elif isinstance(data, list):
                cookies = data
            else:
                return

            playwright_cookies = []
            for cookie in cookies:
                if not isinstance(cookie, dict):
                    continue
                name = cookie.get("name")
                value = cookie.get("value")
                if not name or not value:
                    continue
                domain = cookie.get("domain", ".binance.com")
                if domain and not domain.startswith("."):
                    domain = "." + domain
                pc = {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": cookie.get("path", "/"),
                }
                if cookie.get("expires"):
                    pc["expires"] = cookie["expires"]
                if cookie.get("httpOnly"):
                    pc["httpOnly"] = True
                if cookie.get("secure"):
                    pc["secure"] = True
                playwright_cookies.append(pc)

            if playwright_cookies and self._context:
                await self._context.add_cookies(playwright_cookies)
        except Exception:
            pass

    async def close(self) -> None:
        try:
            if self._client:
                await self._client.aclose()
            if self._playwright:
                await self._playwright.stop()
        finally:
            self.connected = False

    def _cookie_mtime_now(self) -> Optional[float]:
        if not self.cookie_path.exists():
            return None
        return self.cookie_path.stat().st_mtime

    def _load_cookie_jar(self) -> httpx.Cookies:
        if not self.cookie_path.exists():
            raise FileNotFoundError(f"cookie file not found: {self.cookie_path}")
        data = json.loads(self.cookie_path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict) and "cookies" in data:
            cookies = data["cookies"]
        elif isinstance(data, list):
            cookies = data
        else:
            raise ValueError("cookie file must be a list or {'cookies': [...]} JSON")

        jar = httpx.Cookies()
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            name = cookie.get("name")
            value = cookie.get("value")
            if not name:
                continue
            domain = cookie.get("domain")
            path = cookie.get("path") or "/"
            if domain:
                jar.set(name, value, domain=domain, path=path)
            else:
                jar.set(name, value, path=path)
        return jar

    def _load_cookie_map(self) -> Dict[str, str]:
        if not self.cookie_path.exists():
            return {}
        data = json.loads(self.cookie_path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict) and "cookies" in data:
            cookies = data["cookies"]
        elif isinstance(data, list):
            cookies = data
        else:
            return {}
        mapping: Dict[str, str] = {}
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            name = cookie.get("name")
            value = cookie.get("value")
            if not name or value is None:
                continue
            mapping[str(name)] = str(value)
        return mapping

    async def _reset_cookie_client(self, jar: httpx.Cookies) -> None:
        if self._client:
            await self._client.aclose()
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
        }
        if self.user_agent:
            headers["user-agent"] = self.user_agent
        timeout = self.request_timeout_ms / 1000.0
        self._client = httpx.AsyncClient(headers=headers, cookies=jar, timeout=timeout)

    async def _ensure_cookie_client(self, force: bool = False) -> None:
        mtime = self._cookie_mtime_now()
        if mtime is None:
            raise FileNotFoundError(f"cookie file not found: {self.cookie_path}")
        if force or self._client is None or self._cookie_mtime is None or mtime > self._cookie_mtime:
            jar = self._load_cookie_jar()
            await self._reset_cookie_client(jar)
            self._cookie_mtime = mtime

    async def _refresh_cookie_cache(self) -> None:
        if self.auth_mode == "cdp":
            if not self._context:
                return
            cookies = await self._context.cookies()
            self._cookie_cache = {c["name"]: c["value"] for c in cookies if "name" in c}
            return
        if self.auth_mode == "cookie":
            self._cookie_cache = self._load_cookie_map()

    def _attach_header_capture(self) -> None:
        if not self._context or self._capture_attached:
            return

        def _capture(request) -> None:
            if "/bapi/" not in request.url:
                return
            headers = request.headers or {}
            if "fvideo-token" in headers:
                self._header_cache["fvideo-token"] = headers["fvideo-token"]
            for key in (
                "fvideo-id",
                "bnc-uuid",
                "bnc-level",
                "device-info",
                "clienttype",
                "lang",
                "bnc-time-zone",
                "csrftoken",
            ):
                value = headers.get(key)
                if value:
                    self._header_cache[key] = value

        self._context.on("request", _capture)
        self._capture_attached = True

    async def _refresh_storage_headers(self) -> None:
        if self.auth_mode != "cdp" or not self._context:
            return
        if not self._context.pages:
            return
        page = self._context.pages[0]
        try:
            raw = await page.evaluate(
                "() => ({"
                "bncUuid: localStorage.getItem('__bnc_uuid'),"
                "bncLevel: localStorage.getItem('BNC-Level'),"
                "fvKey: localStorage.getItem('BNC_FV_KEY'),"
                "fpInfo: localStorage.getItem('__BNC_FP_INFO__'),"
                "})"
            )
        except Exception:  # pragma: no cover - runtime page access
            return

        bnc_uuid = raw.get("bncUuid")
        if bnc_uuid:
            self._header_cache.setdefault("bnc-uuid", bnc_uuid)

        bnc_level = raw.get("bncLevel")
        if bnc_level:
            self._header_cache.setdefault("bnc-level", bnc_level)

        fv_key_raw = raw.get("fvKey")
        if fv_key_raw:
            try:
                fv_key = json.loads(fv_key_raw).get("value")
            except json.JSONDecodeError:
                fv_key = fv_key_raw
            if fv_key:
                self._header_cache.setdefault("fvideo-id", fv_key)

        fp_raw = raw.get("fpInfo")
        if not fp_raw:
            return
        try:
            fp_info = json.loads(fp_raw).get("value")
            if isinstance(fp_info, str):
                fp_info = json.loads(fp_info)
        except json.JSONDecodeError:
            return
        if not isinstance(fp_info, dict):
            return
        fp_info.setdefault("device_id", "")
        fp_info.setdefault("related_device_ids", "")
        payload = json.dumps(fp_info, separators=(",", ":"), ensure_ascii=True)
        self._header_cache.setdefault(
            "device-info",
            base64.b64encode(payload.encode("utf-8")).decode("ascii"),
        )
        web_tz = fp_info.get("web_timezone")
        if web_tz:
            self._header_cache.setdefault("bnc-time-zone", str(web_tz))

    def _apply_cookie_headers(self, headers: Dict[str, str]) -> None:
        if "bnc-uuid" not in headers:
            bnc_uuid = self._cookie_cache.get("bnc-uuid")
            if bnc_uuid:
                headers["bnc-uuid"] = bnc_uuid
        if "csrftoken" not in headers:
            csrf = self._cookie_cache.get("csrftoken")
            if csrf:
                headers["csrftoken"] = csrf
        if "lang" not in headers:
            lang = self._cookie_cache.get("lang")
            if lang:
                headers["lang"] = lang
        if "bnc-location" not in headers:
            bnc_location = self._cookie_cache.get("BNC-Location") or self._cookie_cache.get("bnc-location")
            if bnc_location:
                headers["bnc-location"] = bnc_location
        if "fvideo-id" not in headers:
            fv_key = self._cookie_cache.get("BNC_FV_KEY")
            if fv_key:
                headers["fvideo-id"] = fv_key
        if "fvideo-token" not in headers:
            fv_token = self._cookie_cache.get("fvideo-token")
            if fv_token:
                headers["fvideo-token"] = fv_token
        if "device-info" not in headers:
            device_info = self._cookie_cache.get("device-info")
            if device_info:
                headers["device-info"] = device_info
        if "clienttype" not in headers:
            headers["clienttype"] = "web"
        if "content-type" not in headers:
            headers["content-type"] = "application/json"
        if "fvideo-token" not in headers:
            fv_token = self._cookie_cache.get("fvideo-token")
            if fv_token:
                headers["fvideo-token"] = fv_token
        if "device-info" not in headers:
            device_info = self._cookie_cache.get("device-info")
            if device_info:
                headers["device-info"] = device_info

    async def _prepare_headers(
        self,
        extra: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
        }
        if self.user_agent:
            headers["user-agent"] = self.user_agent

        if self.auth_mode in {"cdp", "cookie"}:
            await self._refresh_cookie_cache()
        if self.auth_mode == "cdp":
            await self._refresh_storage_headers()

        for key, value in self._header_cache.items():
            if value:
                headers[key] = value

        self._apply_cookie_headers(headers)
        headers.setdefault("clienttype", "web")
        headers.setdefault("x-passthrough-token", "")
        if "accept-language" not in headers:
            lang = self._cookie_cache.get("lang") if self.auth_mode else None
            headers["accept-language"] = lang or "zh-CN,zh;q=0.9"

        trace_id = str(uuid.uuid4())
        headers.setdefault("x-trace-id", trace_id)
        headers.setdefault("x-ui-request-trace", trace_id)

        if self.extra_headers:
            headers.update(self.extra_headers)

        if extra:
            headers.update(extra)
        return headers

    def _update_time_offset(self, headers: Dict[str, str]) -> None:
        if not headers:
            return
        raw_date = headers.get("date") or headers.get("Date")
        if not raw_date:
            return
        try:
            parsed = parsedate_to_datetime(raw_date)
        except (TypeError, ValueError):
            return
        if parsed is None:
            return
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        server_ms = int(parsed.timestamp() * 1000)
        self.time_offset_ms = server_ms - now_ms()

    async def _request_json(
        self,
        method: str,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        if timeout_ms is None:
            timeout_ms = self.request_timeout_ms
        if not self.connected:
            ok = await self.connect()
            if not ok:
                raise RuntimeError(self.last_error or "connect failed")

        headers = await self._prepare_headers(headers)

        if self.auth_mode == "cdp":
            if not self._context:
                raise RuntimeError("Browser context is not available")

            request = self._context.request
            if method == "GET":
                resp = await request.get(url, headers=headers, timeout=timeout_ms)
            else:
                resp = await request.post(url, headers=headers, data=data, timeout=timeout_ms)
            try:
                self._update_time_offset(resp.headers)
            except Exception:
                pass
            return await resp.json()

        if self.auth_mode == "cookie":
            await self._ensure_cookie_client()
            if not self._client:
                raise RuntimeError("HTTP client is not available")
            timeout = timeout_ms / 1000.0
            if method == "GET":
                resp = await self._client.get(url, headers=headers, timeout=timeout)
            else:
                resp = await self._client.post(url, headers=headers, json=data, timeout=timeout)
            try:
                self._update_time_offset(resp.headers)
            except Exception:
                pass
            try:
                return resp.json()
            except json.JSONDecodeError as exc:
                body = resp.text
                raise RuntimeError(
                    f"non-JSON response {resp.status_code}: {body[:200]}"
                ) from exc

        raise RuntimeError(f"unknown auth_mode: {self.auth_mode}")

    async def request_json(
        self,
        method: str,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        return await self._request_json(
            method=method,
            url=url,
            data=data,
            headers=headers,
            timeout_ms=timeout_ms,
        )

    async def fetch_detail(self, portfolio_id: str) -> Dict[str, Any]:
        url = (
            f"{self.api_base}/bapi/futures/v1/friendly/future/"
            "copy-trade/lead-portfolio/detail"
        )
        referer = (
            f"{self.api_base}/zh-CN/copy-trading/lead-details/{portfolio_id}?timeRange=30D"
        )
        return await self._request_json(
            "GET",
            f"{url}?portfolioId={portfolio_id}",
            headers={"referer": referer, "origin": self.api_base},
        )

    async def fetch_order_history(
        self,
        portfolio_id: str,
        start_time: int,
        end_time: int,
        page_size: int,
    ) -> Dict[str, Any]:
        url = (
            f"{self.api_base}/bapi/futures/v1/friendly/future/"
            "copy-trade/lead-portfolio/order-history"
        )
        payload = {
            "portfolioId": portfolio_id,
            "startTime": start_time,
            "endTime": end_time,
            "pageSize": page_size,
        }
        referer = (
            f"{self.api_base}/zh-CN/copy-trading/lead-details/{portfolio_id}?timeRange=30D"
        )
        return await self._request_json(
            "POST",
            url,
            data=payload,
            headers={"referer": referer, "origin": self.api_base},
        )

    async def fetch_position_history(
        self,
        portfolio_id: str,
        page_number: int,
        page_size: int,
    ) -> Dict[str, Any]:
        url = (
            f"{self.api_base}/bapi/futures/v1/friendly/future/"
            "copy-trade/lead-portfolio/position-history"
        )
        payload = {
            "pageNumber": page_number,
            "pageSize": page_size,
            "portfolioId": portfolio_id,
            "sort": "OPENING",
        }
        referer = (
            f"{self.api_base}/zh-CN/copy-trading/lead-details/{portfolio_id}?timeRange=30D"
        )
        return await self._request_json(
            "POST",
            url,
            data=payload,
            headers={"referer": referer, "origin": self.api_base},
        )

    async def fetch_positions(self, portfolio_id: str) -> Dict[str, Any]:
        """获取带单员当前持仓"""
        url = (
            f"{self.api_base}/bapi/futures/v1/friendly/future/"
            "copy-trade/lead-data/positions"
        )
        referer = (
            f"{self.api_base}/zh-CN/copy-trading/lead-details/{portfolio_id}?timeRange=30D"
        )
        try:
            raw_response = await self._request_json(
                "GET",
                f"{url}?portfolioId={portfolio_id}",
                headers={"referer": referer, "origin": self.api_base},
            )

            # Debug logging
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[DEBUG] Raw Binance response: {raw_response}")

            # Check Binance success indicators
            code = raw_response.get("code")
            success = raw_response.get("success", False)

            if code != "000000" and not success:
                # Handle authentication errors
                if code in ["003999", "003998"]:
                    return {"success": False, "error": "login_required"}
                return {"success": False, "error": raw_response.get("message", "Unknown error")}

            # Extract positions from nested structure
            data = raw_response.get("data", {})
            if isinstance(data, dict):
                positions = data.get("positions")
                if positions is None:
                    # Hidden positions case
                    return {"success": True, "data": [], "positions": [], "position_show": False}
                return {"success": True, "data": positions, "positions": positions, "empty_confirmed": len(positions) == 0}

            # Fallback for unexpected structure
            positions_list = data if isinstance(data, list) else []
            return {"success": True, "data": positions_list, "positions": positions_list}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _apply_cookies_to_context(self) -> None:
        if not self._context or not self.cookie_path.exists():
            return
        cookies_data = json.loads(self.cookie_path.read_text(encoding="utf-8-sig"))
        if isinstance(cookies_data, dict) and "cookies" in cookies_data:
            cookies_data = cookies_data["cookies"]
        if not isinstance(cookies_data, list):
            return
        browser_cookies = []
        same_site_map = {
            "strict": "Strict",
            "lax": "Lax",
            "none": "None",
            "no_restriction": "None",
            "unspecified": None,
        }
        for c in cookies_data:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            cookie = {
                "name": c["name"],
                "value": c.get("value", ""),
                "domain": c.get("domain", ".binance.com"),
                "path": c.get("path", "/"),
            }
            if "httpOnly" in c:
                cookie["httpOnly"] = bool(c.get("httpOnly"))
            if "secure" in c:
                cookie["secure"] = bool(c.get("secure"))
            same_site = c.get("sameSite")
            if isinstance(same_site, str):
                same_site_value = same_site_map.get(same_site.lower())
                if same_site_value:
                    cookie["sameSite"] = same_site_value
            expires = c.get("expires")
            if isinstance(expires, (int, float)):
                cookie["expires"] = float(expires)
            expiration = c.get("expirationDate")
            if isinstance(expiration, (int, float)):
                cookie["expires"] = float(expiration)
            browser_cookies.append(cookie)
        if browser_cookies:
            await self._context.add_cookies(browser_cookies)

    async def fetch_position_history_from_page(
        self,
        portfolio_id: str,
        page_number: int,
        page_size: int,
    ) -> Dict[str, Any]:
        if self.auth_mode != "cdp":
            return {"success": False, "error": "DOM scraping requires CDP mode"}
        if not self._context:
            return {"success": False, "error": "Browser context not available"}

        page_url = f"{self.api_base}/zh-CN/copy-trading/lead-details/{portfolio_id}?timeRange=30D"
        payload: Optional[Dict[str, Any]] = None

        try:
            await self._apply_cookies_to_context()

            if self._context.pages:
                page = self._context.pages[0]
            else:
                page = await self._context.new_page()

            current_url = page.url
            if portfolio_id not in current_url or "copy-trading/lead-details" not in current_url:
                await page.goto(page_url, wait_until="networkidle", timeout=30000)

            async def click_history_tab() -> None:
                tab_labels = [
                    "仓位历史记录",
                    "Position History",
                    "Positions History",
                    "Position history",
                ]
                for label in tab_labels:
                    tab = page.locator(".bn-tab", has_text=label)
                    if await tab.count() > 0:
                        await tab.first.click()
                        await page.wait_for_timeout(300)
                        return

            try:
                async with page.expect_response(
                    lambda resp: "copy-trade/lead-portfolio/position-history" in resp.url,
                    timeout=5000,
                ) as response_info:
                    await click_history_tab()
                resp = await response_info.value
                payload = await resp.json()
            except Exception:
                async with page.expect_response(
                    lambda resp: "copy-trade/lead-portfolio/position-history" in resp.url,
                    timeout=5000,
                ) as response_info:
                    await page.reload(wait_until="networkidle", timeout=30000)
                    await click_history_tab()
                resp = await response_info.value
                payload = await resp.json()
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if payload is None:
            return {"success": False, "error": "no_response"}
        return payload

    async def fetch_positions_from_page(self, portfolio_id: str) -> Dict[str, Any]:
        """通过页面 DOM 抓取带单员当前持仓"""
        # 确保浏览器已连接
        if not self.connected or not self._context:
            self.connected = False
            if not await self.connect():
                return {"success": False, "error": f"CDP connect failed: {self.last_error}"}

        page_url = f"{self.api_base}/zh-CN/copy-trading/lead-details/{portfolio_id}?timeRange=30D"

        try:
            await self._apply_cookies_to_context()

            # 获取或创建页面
            if self._context.pages:
                page = self._context.pages[0]
            else:
                page = await self._context.new_page()

            # 导航到带单员页面
            positions_payload = None
            use_api_payload = False
            current_url = page.url

            # 强制初始化登录态（修复币安bug：需要先访问其他页面）
            if not self._session_initialized:
                try:
                    await page.goto(f"{self.api_base}/zh-CN/futures/BTCUSDT", wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(2000)
                    self._session_initialized = True
                except Exception:
                    pass

            # 导航到带单员页面
            need_navigate = portfolio_id not in current_url or "copy-trading/lead-details" not in current_url
            try:
                if need_navigate:
                    await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                else:
                    await page.reload(wait_until="domcontentloaded", timeout=30000)
            except Exception:
                try:
                    await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass

            await page.wait_for_timeout(500)
            try:
                tab_labels = ["持有仓位", "当前仓位", "仓位", "持仓", "Positions", "Current Positions"]
                for label in tab_labels:
                    tab = page.locator(".bn-tab", has_text=label)
                    if await tab.count() > 0:
                        await tab.first.click()
                        await page.wait_for_timeout(800)  # 增加等待时间让数据加载
                        break
            except Exception:
                pass
            try:
                await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(300)
            except Exception:
                pass

            if positions_payload is None and use_api_payload:
                try:
                    async with page.expect_response(
                        lambda resp: "copy-trade/lead-data/positions" in resp.url,
                        timeout=12000,
                    ) as response_info:
                        for label in tab_labels:
                            tab = page.locator(".bn-tab", has_text=label)
                            if await tab.count() > 0:
                                await tab.first.click()
                                await page.wait_for_timeout(150)
                                break
                    resp = await response_info.value
                    positions_payload = await resp.json()
                except Exception:
                    pass

            if positions_payload is None and use_api_payload:
                try:
                    positions_payload = await self.fetch_positions(portfolio_id)
                except Exception:
                    positions_payload = None
                    use_api_payload = False

            def _coerce_json(value: Any) -> Any:
                if isinstance(value, str):
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        return value
                return value

            def _find_positions(value: Any, depth: int = 0) -> list[Dict[str, Any]]:
                if depth > 5:
                    return []
                if isinstance(value, list):
                    items = [item for item in value if isinstance(item, dict)]
                    if items and any("symbol" in item for item in items):
                        return items
                    for item in value:
                        found = _find_positions(_coerce_json(item), depth + 1)
                        if found:
                            return found
                    return []
                if isinstance(value, dict):
                    for key in (
                        "positions",
                        "positionList",
                        "positionData",
                        "openPositions",
                        "holdingPositions",
                        "list",
                        "data",
                        "rows",
                        "items",
                        "result",
                    ):
                        if key in value:
                            found = _find_positions(_coerce_json(value[key]), depth + 1)
                            if found:
                                return found
                    for item in value.values():
                        found = _find_positions(_coerce_json(item), depth + 1)
                        if found:
                            return found
                return []

            def _find_position_show(value: Any, depth: int = 0) -> Optional[bool]:
                if depth > 5:
                    return None
                if isinstance(value, dict):
                    for key in ("positionShow", "position_show"):
                        flag = value.get(key)
                        if isinstance(flag, bool):
                            return flag
                    for item in value.values():
                        flag = _find_position_show(_coerce_json(item), depth + 1)
                        if flag is not None:
                            return flag
                elif isinstance(value, list):
                    for item in value:
                        flag = _find_position_show(_coerce_json(item), depth + 1)
                        if flag is not None:
                            return flag
                return None

            def has_nonzero_positions(items: list[Dict[str, Any]]) -> bool:
                keys = (
                    "positionAmount",
                    "positionAmt",
                    "positionQty",
                    "positionSize",
                    "positionVolume",
                )
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    for key in keys:
                        value = item.get(key)
                        if value is None:
                            continue
                        try:
                            amount = float(value)
                        except (TypeError, ValueError):
                            continue
                        if abs(amount) > 0:
                            return True
                return False

            if use_api_payload and isinstance(positions_payload, dict):
                data = _coerce_json(positions_payload.get("data"))
                # 调试：记录 API 返回的原始数据
                import logging
                _logger = logging.getLogger("copy-sync")
                _logger.info("[API_INTERCEPT] Raw payload keys: %s, data type: %s",
                            list(positions_payload.keys()) if isinstance(positions_payload, dict) else "not_dict",
                            type(data).__name__)
                if isinstance(data, dict):
                    _logger.info("[API_INTERCEPT] Data keys: %s", list(data.keys()))
                    raw = _coerce_json(
                        data.get("positions")
                        or data.get("positionList")
                        or data.get("positionData")
                        or data.get("list")
                        or data.get("data")
                        or []
                    )
                elif isinstance(data, list):
                    # data 直接是 list，说明 positions 就在 data 里
                    raw = data
                    _logger.info("[API_INTERCEPT] Data is list, length: %d, sample: %s",
                                len(data), str(data)[:500] if data else "empty")
                else:
                    raw = data or []
                if not isinstance(raw, list) or not raw:
                    raw = _find_positions(data if data is not None else positions_payload)
                _logger.info("[API_INTERCEPT] Raw positions count: %d, sample: %s",
                            len(raw) if isinstance(raw, list) else 0,
                            str(raw)[:500] if raw else "empty")

                # 如果 API 返回空数据，不要直接返回，继续尝试 DOM 抓取
                if isinstance(raw, list) and len(raw) > 0:
                    api_positions = [item for item in raw if isinstance(item, dict)]
                    success = positions_payload.get("success")
                    if isinstance(success, str):
                        success = success.strip().lower() in {"true", "1", "ok", "success"}
                    code = positions_payload.get("code")
                    ok = True
                    if success is False:
                        ok = False
                    if code is not None and str(code) not in {
                        "0",
                        "000000",
                        "200",
                        "success",
                        "SUCCESS",
                    } and success is not True:
                        ok = False
                    if ok:
                        response: Dict[str, Any] = {
                            "success": True,
                            "position_show": True,
                            "positions": api_positions,
                        }
                        position_show = _find_position_show(
                            data if data is not None else positions_payload
                        )
                        if isinstance(position_show, bool):
                            response["position_show"] = position_show
                            if position_show is False and not api_positions:
                                response["error"] = "position_hidden"
                        return response
            elif use_api_payload and isinstance(positions_payload, list):
                raw = _find_positions(positions_payload)
                if raw:
                    return {
                        "success": True,
                        "position_show": True,
                        "positions": raw,
                    }

            # 执行 DOM 抓取脚本 - 基于页面文本解析仓位数据
            # 先等待页面内容加载
            await page.wait_for_timeout(2000)

            # 尝试等待页面上出现关键元素
            try:
                await page.wait_for_selector("body", timeout=5000)
                # 等待页面内容出现
                await page.wait_for_function("() => document.body.innerText.length > 100", timeout=10000)
            except Exception:
                pass

            # 记录当前页面 URL 用于调试
            import logging
            _dom_logger = logging.getLogger("copy-sync")
            _dom_logger.info("[DOM] Current page URL: %s", page.url)

            # 新版DOM抓取脚本 - 基于实际页面结构（StaticText元素）
            table_extract_script = """
                () => {
                    const result = {
                        success: true,
                        positions: [],
                        leaderMargin: 0,
                        position_show: true
                    };

                    const parseNumber = (value) => {
                        if (value === null || value === undefined) return null;
                        const text = String(value).replace(/,/g, '');
                        const match = text.match(/-?[\\d.]+/);
                        return match ? parseFloat(match[0]) : null;
                    };

                    // 获取页面全部文本
                    const bodyText = document.body.innerText || '';

                    // 检查仓位是否被隐藏
                    if (/已隐藏仓位|跟单后即可查看/.test(bodyText)) {
                        result.position_show = false;
                        result.error = 'position_hidden';
                        return result;
                    }

                    // 检查是否无持仓
                    if (/暂无记录|暂无数据|暂无持仓|No data|No positions/i.test(bodyText)) {
                        result.positions = [];
                        result.empty_confirmed = true;
                        return result;
                    }

                    // 获取带单保证金余额
                    const marginMatch = bodyText.match(/带单保证金余额\\s*([\\d,\\.]+)\\s*USDT/);
                    if (marginMatch) {
                        result.leaderMargin = parseFloat(marginMatch[1].replace(/,/g, ''));
                    }

                    // 方法1: 基于文本模式匹配仓位数据
                    // 格式: XXXUSDT 永续 10x 数量 开仓价 标记价 保证金
                    const positionPattern = /([A-Z0-9]+USDT)\\s*永续\\s*(\\d+)x\\s*(-?[\\d,\\.]+)\\s*[A-Z]+\\s*([\\d,\\.]+)\\s*([\\d,\\.]+)\\s*([\\d,\\.]+)\\s*USDT/gi;
                    let match;
                    const seenSymbols = new Set();

                    while ((match = positionPattern.exec(bodyText)) !== null) {
                        const symbol = match[1].toUpperCase();
                        if (seenSymbols.has(symbol)) continue;
                        seenSymbols.add(symbol);

                        const leverage = parseInt(match[2], 10);
                        const qty = parseFloat(match[3].replace(/,/g, ''));
                        const entryPrice = parseFloat(match[4].replace(/,/g, ''));
                        const markPrice = parseFloat(match[5].replace(/,/g, ''));
                        const margin = parseFloat(match[6].replace(/,/g, ''));

                        // 查找收益额（在保证金后面）
                        const pnlPattern = new RegExp(symbol + '[\\\\s\\\\S]{0,200}?(-?[\\\\d,\\\\.]+)\\\\s*USDT\\\\s*\\\\(\\\\s*(-?[\\\\d,\\\\.]+)%\\\\s*\\\\)', 'i');
                        const pnlMatch = bodyText.match(pnlPattern);
                        const pnl = pnlMatch ? parseFloat(pnlMatch[1].replace(/,/g, '')) : 0;

                        result.positions.push({
                            symbol: symbol,
                            positionSide: qty < 0 ? 'SHORT' : 'LONG',
                            positionAmount: Math.abs(qty),
                            positionAmt: qty,
                            entryPrice: entryPrice,
                            markPrice: markPrice,
                            margin: margin,
                            leverage: leverage,
                            unrealizedProfit: pnl
                        });
                    }

                    // 方法2: 如果方法1没找到，尝试更宽松的匹配
                    if (result.positions.length === 0) {
                        // 查找所有 XXXUSDT 永续 Nx 的模式
                        const symbolPattern = /([A-Z0-9]+USDT)\\s*(?:永续|Perpetual)\\s*(\\d+)x/gi;
                        const symbols = [];
                        while ((match = symbolPattern.exec(bodyText)) !== null) {
                            symbols.push({
                                symbol: match[1].toUpperCase(),
                                leverage: parseInt(match[2], 10),
                                index: match.index
                            });
                        }

                        for (const sym of symbols) {
                            if (seenSymbols.has(sym.symbol)) continue;
                            seenSymbols.add(sym.symbol);

                            // 从该位置向后查找数字
                            const afterText = bodyText.substring(sym.index, sym.index + 500);
                            const numbers = afterText.match(/-?[\\d,]+\\.?\\d*/g) || [];
                            const nums = numbers.map(n => parseFloat(n.replace(/,/g, ''))).filter(n => !isNaN(n) && n !== sym.leverage);

                            if (nums.length >= 4) {
                                const qty = nums[0];
                                const entryPrice = nums[1];
                                const markPrice = nums[2];
                                const margin = nums[3];
                                const pnl = nums.length > 4 ? nums[4] : 0;

                                result.positions.push({
                                    symbol: sym.symbol,
                                    positionSide: qty < 0 ? 'SHORT' : 'LONG',
                                    positionAmount: Math.abs(qty),
                                    positionAmt: qty,
                                    entryPrice: entryPrice,
                                    markPrice: markPrice,
                                    margin: margin,
                                    leverage: sym.leverage,
                                    unrealizedProfit: pnl
                                });
                            }
                        }
                    }

                    if (!result.positions.length) {
                        result.empty_confirmed = true;
                    }

                    result._debug_text_sample = bodyText.substring(0, 2000);
                    return result;
                }
            """


            # 执行DOM抓取
            table_payload = None
            try:
                table_payload = await page.evaluate(table_extract_script)
            except Exception as e:
                _dom_logger.warning("[DOM] Extract script failed: %s", str(e))
                table_payload = None

            if isinstance(table_payload, dict):
                _dom_logger.info("[DOM] Extract result: success=%s, positions=%d, position_show=%s",
                               table_payload.get("success"),
                               len(table_payload.get("positions", [])),
                               table_payload.get("position_show"))
                if table_payload.get("_debug_text_sample"):
                    _dom_logger.debug("[DOM] Text sample: %s", table_payload.get("_debug_text_sample", "")[:500])

                if table_payload.get("success") and (table_payload.get("positions") or table_payload.get("empty_confirmed")):
                    return table_payload

            # 如果主脚本失败，返回错误信息
            return table_payload or {"success": False, "error": "dom_extract_failed"}

        except Exception as e:
            # 浏览器可能已崩溃，重置连接状态以便下次重连
            self.connected = False
            return {"success": False, "error": str(e)}

    def header_status(self) -> Dict[str, object]:
        def _flag(key: str) -> bool:
            return bool(
                self._header_cache.get(key)
                or self._cookie_cache.get(key)
                or self.extra_headers.get(key)
            )

        return {
            "has_fvideo_token": _flag("fvideo-token"),
            "has_fvideo_id": _flag("fvideo-id") or _flag("BNC_FV_KEY"),
            "has_device_info": _flag("device-info"),
            "has_bnc_uuid": _flag("bnc-uuid"),
            "has_bnc_level": _flag("bnc-level") or _flag("BNC-Level"),
            "has_bnc_location": _flag("bnc-location") or _flag("BNC-Location"),
            "has_csrftoken": _flag("csrftoken"),
            "has_lang": _flag("lang"),
            "has_waf_cookie": bool(self._cookie_cache.get("aws-waf-token")),
            "header_keys": sorted(
                {**self._header_cache, **self.extra_headers}.keys()
            ),
        }
