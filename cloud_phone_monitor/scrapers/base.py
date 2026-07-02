import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from cloud_phone_monitor.config import MonitorConfig, Target
from cloud_phone_monitor.schemas import ProductRecord
from cloud_phone_monitor.utils.normalize import (
    compact_text,
    iter_product_like_nodes,
    looks_like_product_payload,
    now_pair,
    parse_product_fields,
    redact_headers,
    redact_payload,
    safe_filename,
)


DANGEROUS_CLICK_WORDS = [
    "buy", "purchase", "pay", "checkout", "order", "confirm", "payment",
    "subscribe", "renew", "submit", "立即购买", "购买", "支付", "结算",
    "下单", "确认", "续费", "订阅", "充值"
]

SAFE_CLICK_HINTS = [
    "android", "region", "server", "month", "year", "day", "week", "vip",
    "kvip", "svip", "xvip", "us", "usa", "taiwan", "singapore", "hong kong",
    "japan", "korea", "地区", "区域", "服务器", "安卓", "月", "年", "天"
]


INTERESTING_API_TOKENS = [
    "cardtypeconfig",
    "configs.json",
    "gamerecommendgoods",
    "getpadconfig",
    "getnewversionclassify",
    "newversionpadclassify",
    "goodsoption",
    "getgoods",
    "goodlist",
    "goods/v",
    "price/order",
]

SENSITIVE_API_TOKENS = [
    "/buy.json",
    "/order/buy",
    "/pay/",
    "payment",
]


class BaseScraper:
    platform: str = "Base"

    def __init__(
        self,
        context: BrowserContext,
        target: Target,
        config: MonitorConfig,
        output_dir: Path,
        logger: logging.Logger,
    ):
        self.context = context
        self.target = target
        self.config = config
        self.output_dir = output_dir
        self.logger = logger
        self.artifact_dir = output_dir / "page_artifacts"
        self.screenshot_dir = self.artifact_dir / "screenshots"
        self.html_dir = self.artifact_dir / "html"
        self.api_dir = self.artifact_dir / "api_responses"
        for p in [self.screenshot_dir, self.html_dir, self.api_dir]:
            p.mkdir(parents=True, exist_ok=True)
        self.api_candidates: List[dict] = []
        self.blocked_reason: Optional[str] = None

    def scrape(self) -> List[ProductRecord]:
        page = self.context.new_page()
        page.set_default_timeout(self.config.browser_timeout_ms)
        self._attach_network_listeners(page)

        records: List[ProductRecord] = []
        try:
            records.extend(self._scrape_url(page, self.target.url, extraction_method="dom"))
            if not records:
                records.extend(self.scrape_fallbacks(page))
        except Exception as exc:
            self.blocked_reason = f"exception: {type(exc).__name__}: {exc}"
            self.logger.exception("[%s] scrape failed", self.platform)
        finally:
            page.close()

        for record in records:
            record.finalize()
        return records

    def scrape_fallbacks(self, page: Page) -> List[ProductRecord]:
        return []

    def _collect_interactive_states(self, page: Page, url: str) -> None:
        return None

    def _scrape_url(self, page: Page, url: str, extraction_method: str = "dom") -> List[ProductRecord]:
        self.logger.info("[%s] opening %s", self.platform, url)
        records: List[ProductRecord] = []
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.config.browser_timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeoutError:
                self.logger.info("[%s] networkidle timeout; continuing with visible DOM", self.platform)
            page.wait_for_timeout(self.config.wait_after_load_ms)
            self._accept_safe_dialogs(page)
            self._collect_interactive_states(page, url)
        except Exception as exc:
            self.blocked_reason = f"navigation_failed: {type(exc).__name__}: {exc}"
            self.logger.warning("[%s] navigation failed: %s", self.platform, self.blocked_reason)

        self._detect_blocking(page)
        screenshot_path = self._save_screenshot(page, suffix=safe_filename(url.split("//")[-1]))
        html_path = self._save_html(page, suffix=safe_filename(url.split("//")[-1]))

        if self.config.safe_interactions:
            self._safe_probe_interactions(page, url)

        records.extend(self._records_from_api(url, screenshot_path, html_path))
        dom_records = self._records_from_dom(page, url, screenshot_path, html_path, extraction_method=extraction_method)

        # Prefer API records if they exist but keep DOM records because cards often contain visible discount text.
        records.extend(dom_records)

        return self._dedupe_records(records)

    def _accept_safe_dialogs(self, page: Page) -> None:
        for label in ["Agree", "I agree", "Accept", "OK", "Got it"]:
            try:
                button = page.get_by_text(label, exact=True).first
                if button.is_visible(timeout=1000):
                    button.click(timeout=1500)
                    page.wait_for_timeout(1000)
            except Exception:
                continue

    def _attach_network_listeners(self, page: Page) -> None:
        def on_response(response):
            try:
                req = response.request
                resource_type = req.resource_type
                if resource_type not in {"xhr", "fetch"}:
                    return
                url = response.url
                status = response.status
                content_type = response.headers.get("content-type", "")
                text = ""
                payload: Any = None
                if "json" in content_type.lower():
                    try:
                        payload = response.json()
                        text = json.dumps(payload, ensure_ascii=False, default=str)
                    except Exception:
                        text = response.text()[:200000]
                else:
                    text = response.text()[:200000]

                product_like = False
                try:
                    product_like = looks_like_product_payload(payload if payload is not None else text)
                except Exception:
                    product_like = False
                lowered_url = url.lower()
                interesting_api = (
                    any(token in lowered_url for token in INTERESTING_API_TOKENS)
                    and not any(token in lowered_url for token in SENSITIVE_API_TOKENS)
                )
                if not product_like and not interesting_api:
                    return

                filename = f"{len(self.api_candidates)+1:04d}_{safe_filename(url)}.json"
                path = self.api_dir / filename

                request_payload = None
                try:
                    request_payload = req.post_data_json
                except Exception:
                    try:
                        request_payload = req.post_data
                    except Exception:
                        request_payload = None

                item = {
                    "platform": self.platform,
                    "url": url,
                    "method": req.method,
                    "status": status,
                    "resource_type": resource_type,
                    "request_headers": redact_headers(req.headers),
                    "response_headers": redact_headers(response.headers),
                    "request_payload": redact_payload(request_payload),
                    "response_json": redact_payload(payload) if payload is not None else None,
                    "response_text": None if payload is not None else text[:200000],
                    "api_response_path": str(path),
                }
                path.write_text(json.dumps(item, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                self.api_candidates.append(item)
            except Exception as exc:
                self.logger.debug("[%s] response listener skipped: %s", self.platform, exc)

        page.on("response", on_response)

    def _detect_blocking(self, page: Page) -> None:
        try:
            text = compact_text(page.locator("body").inner_text(timeout=3000), 3000).lower()
        except Exception:
            return
        markers = {
            "login_required": ["login", "sign in", "登录", "请登录"],
            "captcha_or_anti_bot": ["captcha", "verify you are human", "cloudflare", "验证码", "安全验证"],
            "javascript_required": ["enable javascript", "启用 javascript", "requires javascript"],
            "region_blocked": ["not available in your region", "地区不可用", "region restricted"],
        }
        for reason, words in markers.items():
            if any(w in text for w in words):
                self.blocked_reason = reason
                return

    def _artifact_path(self, directory: Path, suffix: str, extension: str) -> Path:
        """Build a Windows-safe artifact path with a bounded filename.

        Redfinger interaction contexts can contain a long purchase URL plus plan,
        Android version, server, and result. Keeping all of that in the filename
        can exceed Windows path limits. The readable prefix is retained while a
        stable hash preserves uniqueness; the full context remains in JSON evidence.
        """
        directory.mkdir(parents=True, exist_ok=True)
        readable = safe_filename(str(suffix), max_len=46)
        digest = hashlib.sha1(
            f"{self.platform}|{suffix}".encode("utf-8", errors="ignore")
        ).hexdigest()[:10]
        timestamp_ms = int(time.time() * 1000)
        ext = str(extension).lstrip(".") or "dat"
        stem = f"{safe_filename(self.platform, max_len=18)}_{readable}_{digest}_{timestamp_ms}"
        # Keep the leaf short enough for the existing deeply nested output path.
        return directory / f"{stem[:92]}.{ext}"

    def _save_screenshot(self, page: Page, suffix: str) -> Optional[str]:
        path = self._artifact_path(self.screenshot_dir, suffix, "png")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path), full_page=True)
            return str(path)
        except Exception as exc:
            self.logger.warning("[%s] screenshot failed: %s", self.platform, exc)
            return None

    def _save_html(self, page: Page, suffix: str) -> Optional[str]:
        path = self._artifact_path(self.html_dir, suffix, "html")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(page.content(), encoding="utf-8")
            return str(path)
        except Exception as exc:
            self.logger.warning("[%s] html save failed: %s", self.platform, exc)
            return None

    def _safe_probe_interactions(self, page: Page, url: str) -> None:
        # Keep this conservative: only click elements whose text looks like a filter/tab,
        # and never click transaction-like text.
        try:
            candidates = page.locator("button, [role=tab], [role=button], .tab, .tabs-item, .el-tabs__item").all()
        except Exception:
            return

        clicked = 0
        seen = set()
        for locator in candidates[:80]:
            if clicked >= 20:
                break
            try:
                txt = compact_text(locator.inner_text(timeout=1000), 120)
                key = txt.lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                if any(word in key for word in DANGEROUS_CLICK_WORDS):
                    continue
                if not any(word in key for word in SAFE_CLICK_HINTS):
                    continue
                if not locator.is_visible():
                    continue
                locator.click(timeout=1500)
                page.wait_for_timeout(1000)
                self._save_screenshot(page, suffix=f"{safe_filename(url.split('//')[-1])}_after_{safe_filename(txt)}")
                self._save_html(page, suffix=f"{safe_filename(url.split('//')[-1])}_after_{safe_filename(txt)}")
                clicked += 1
            except Exception:
                continue

    def _collect_plan_tab_snapshots(self, page: Page, url: str, labels: list[str]) -> list[dict]:
        snapshots = []
        for label in labels:
            if not self._click_exact_visible_text(page, label):
                self.logger.info("[%s] plan tab not found: %s", self.platform, label)
                continue
            page.wait_for_timeout(1800)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except PlaywrightTimeoutError:
                pass
            suffix = f"{safe_filename(url.split('//')[-1])}_plan_{safe_filename(label)}"
            snapshots.append(
                {
                    "plan": label,
                    "body_text": self._visible_body_text(page),
                    "active_texts": self._visible_active_texts(page),
                    "cards": self._visible_plan_cards(page),
                    "screenshot_path": self._save_screenshot(page, suffix=suffix),
                    "html_path": self._save_html(page, suffix=suffix),
                }
            )
        return snapshots

    def _click_exact_visible_text(self, page: Page, label: str) -> bool:
        try:
            return bool(
                page.evaluate(
                    """
                    (label) => {
                      const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                      const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0 &&
                          style.visibility !== 'hidden' && style.display !== 'none' &&
                          style.pointerEvents !== 'none';
                      };
                      const selector = [
                        'button', '[role=tab]', '[role=button]', '[aria-selected]',
                        '.tab', '.tabs-item', '.el-tabs__item', 'li', 'span', 'div'
                      ].join(',');
                      const nodes = Array.from(document.querySelectorAll(selector));
                      for (const el of nodes) {
                        if (!visible(el)) continue;
                        if (norm(el.innerText || el.textContent) !== label) continue;
                        el.scrollIntoView({block: 'center', inline: 'center'});
                        el.click();
                        return true;
                      }
                      return false;
                    }
                    """,
                    label,
                )
            )
        except Exception as exc:
            self.logger.debug("[%s] plan tab click skipped for %s: %s", self.platform, label, exc)
            return False

    def _click_visible_text_contains(self, page: Page, label: str, max_text_len: int = 100) -> bool:
        try:
            return bool(
                page.evaluate(
                    """
                    ([label, maxTextLen]) => {
                      const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                      const needle = norm(label).toLowerCase();
                      const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0 &&
                          style.visibility !== 'hidden' && style.display !== 'none' &&
                          style.pointerEvents !== 'none';
                      };
                      const selector = [
                        'button', '[role=tab]', '[role=button]', '[aria-selected]',
                        '.tab', '.tabs-item', '.el-tabs__item', 'li', 'span', 'div', 'label'
                      ].join(',');
                      const nodes = Array.from(document.querySelectorAll(selector));
                      for (const el of nodes) {
                        if (!visible(el)) continue;
                        const text = norm(el.innerText || el.textContent);
                        if (!text || text.length > maxTextLen) continue;
                        if (!text.toLowerCase().includes(needle)) continue;
                        el.scrollIntoView({block: 'center', inline: 'center'});
                        el.click();
                        return true;
                      }
                      return false;
                    }
                    """,
                    [label, max_text_len],
                )
            )
        except Exception as exc:
            self.logger.debug("[%s] contains-text click skipped for %s: %s", self.platform, label, exc)
            return False

    def _visible_body_text(self, page: Page) -> str:
        try:
            return compact_text(page.locator("body").inner_text(timeout=3000), 12000)
        except Exception:
            return ""

    def _visible_active_texts(self, page: Page) -> list[str]:
        try:
            values = page.evaluate(
                """
                () => {
                  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 &&
                      style.visibility !== 'hidden' && style.display !== 'none';
                  };
                  const selector = [
                    '[aria-selected="true"]', '[class*="active"]', '[class*="selected"]',
                    '.is-active', '.is-selected', '.checked'
                  ].join(',');
                  return Array.from(document.querySelectorAll(selector))
                    .filter(visible)
                    .map(el => norm(el.innerText || el.textContent))
                    .filter(text => text && text.length <= 120)
                    .slice(0, 80);
                }
                """
            )
            return list(dict.fromkeys(values))
        except Exception:
            return []

    def _visible_plan_cards(self, page: Page) -> list[dict]:
        try:
            cards = page.evaluate(
                """
                () => {
                  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 &&
                      style.visibility !== 'hidden' && style.display !== 'none';
                  };
                  const priceRe = /(US\\$|USD|HK\\$|NT\\$|SGD|RMB|CNY|\\$|￥|¥)\\s*\\d+(?:[.,]\\d+)?|\\d+(?:[.,]\\d+)?\\s*(USD|USDT|CNY|RMB)/i;
                  const durationRe = /\\d+\\s*(天|日|小时|小時|分钟|分鐘|分|day|days|week|weeks|month|months|year|years|hour|hours|minute|minutes|min|mins|周|月|年)/i;
                  const rejectRe = /(wallet|balance|top-up|transaction|sign in|login|钱包|余额|充值|交易记录|下一步|continue)/i;
                  const out = [];
                  const seen = new Set();
                  for (const el of Array.from(document.querySelectorAll('body *'))) {
                    if (!visible(el)) continue;
                    const text = norm(el.innerText || el.textContent);
                    if (!text || text.length < 4 || text.length > 900) continue;
                    if (!priceRe.test(text) || !durationRe.test(text)) continue;
                    if (rejectRe.test(text) && text.length < 180) continue;
                    const childHasSameSignal = Array.from(el.children || []).some(child => {
                      const childText = norm(child.innerText || child.textContent);
                      return childText && priceRe.test(childText) && durationRe.test(childText);
                    });
                    if (childHasSameSignal && text.length > 160) continue;
                    if (seen.has(text)) continue;
                    seen.add(text);
                    const rect = el.getBoundingClientRect();
                    out.push({
                      text,
                      tag: el.tagName,
                      className: String(el.className || ''),
                      x: Math.round(rect.x),
                      y: Math.round(rect.y),
                      width: Math.round(rect.width),
                      height: Math.round(rect.height),
                    });
                  }
                  return out.slice(0, 50);
                }
                """
            )
            return cards if isinstance(cards, list) else []
        except Exception:
            return []

    def _records_from_api(self, source_url: str, screenshot_path: str, html_path: str) -> List[ProductRecord]:
        records: List[ProductRecord] = []
        crawl_utc, crawl_local = now_pair(self.config.timezone)
        for item in self.api_candidates:
            payload = item.get("response_json")
            if payload is None:
                text = item.get("response_text") or ""
                payload = {"response_text": text}
            for node_path, node in iter_product_like_nodes(payload):
                raw_text = json.dumps(node, ensure_ascii=False, default=str)
                fields = parse_product_fields(raw_text)
                has_product_signal = any(fields.get(k) for k in ["price", "product_model", "android_version", "device_model", "duration"])
                if not has_product_signal:
                    continue
                notes = f"api_node={node_path}"
                if self.blocked_reason:
                    notes += f"; blocked_reason={self.blocked_reason}"
                record = ProductRecord(
                    platform=self.platform,
                    source_url=source_url,
                    crawl_time_utc=crawl_utc,
                    crawl_time_local=crawl_local,
                    raw_text=compact_text(raw_text, 4000),
                    extraction_method="api",
                    confidence="high" if fields.get("price") else "medium",
                    screenshot_path=screenshot_path,
                    html_path=html_path,
                    api_response_path=item.get("api_response_path"),
                    notes=notes,
                    **fields,
                )
                records.append(record)
        return records

    def _records_from_dom(
        self,
        page: Page,
        source_url: str,
        screenshot_path: str,
        html_path: str,
        extraction_method: str = "dom",
    ) -> List[ProductRecord]:
        crawl_utc, crawl_local = now_pair(self.config.timezone)
        records: List[ProductRecord] = []

        try:
            blocks = page.evaluate(
                """
                () => {
                  const nodes = Array.from(document.querySelectorAll('body *'));
                  const re = /(US\\$|USD|HK\\$|NT\\$|SGD|RMB|CNY|￥|¥|\\$|€|£|Android|VIP|KVIP|SVIP|XVIP|cloud|phone|device|region|month|year|price|云手机|安卓|套餐|价格|地区)/i;
                  const out = [];
                  for (const el of nodes) {
                    const txt = (el.innerText || '').replace(/\\s+/g, ' ').trim();
                    if (!txt || txt.length < 8 || txt.length > 1800) continue;
                    if (!re.test(txt)) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 80 || rect.height < 20) continue;
                    out.push(txt);
                  }
                  return Array.from(new Set(out)).slice(0, 200);
                }
                """
            )
        except Exception as exc:
            self.logger.warning("[%s] DOM extraction failed: %s", self.platform, exc)
            return records

        for text in blocks:
            text = compact_text(text, 1800)
            fields = parse_product_fields(text)
            signal_count = sum(1 for k in ["price", "product_model", "android_version", "device_model", "duration"] if fields.get(k))
            if signal_count < 1:
                continue
            confidence = "medium" if fields.get("price") else "low"
            notes = "visible_dom_text"
            if self.blocked_reason:
                notes += f"; blocked_reason={self.blocked_reason}"
            record = ProductRecord(
                platform=self.platform,
                source_url=source_url,
                crawl_time_utc=crawl_utc,
                crawl_time_local=crawl_local,
                raw_text=text,
                extraction_method=extraction_method,
                confidence=confidence,
                screenshot_path=screenshot_path,
                html_path=html_path,
                notes=notes,
                **fields,
            )
            records.append(record)
        return records

    def _dedupe_records(self, records: List[ProductRecord]) -> List[ProductRecord]:
        out: Dict[str, ProductRecord] = {}
        for record in records:
            record.finalize()
            existing = out.get(record.record_hash)
            if not existing:
                out[record.record_hash] = record
            elif existing.extraction_method != "api" and record.extraction_method == "api":
                out[record.record_hash] = record
        return list(out.values())
