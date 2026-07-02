import json
import re
from typing import List

from playwright.sync_api import Page

from cloud_phone_monitor.schemas import ProductRecord
from cloud_phone_monitor.scrapers.base import BaseScraper
from cloud_phone_monitor.utils.normalize import compact_text, now_pair, parse_duration


class VSPhoneScraper(BaseScraper):
    platform = "VSPhone"
    device_model_labels = [
        (["High-end Real Machine", "High-end Real Device"], "高端真机"),
        (["Game AFK Dedicated Phone", "Game AFK Dedicated Machine", "Game AFK"], "游戏挂机专用机"),
    ]
    android_labels = ["Android 10", "Android 13", "Android 14", "Android 15", "Android 16"]
    server_aliases = {
        "Hong Kong": ["Hong Kong", "Hongkong", "HK", "香港"],
        "Indonesia": ["Indonesia", "ID", "印尼", "印度尼西亚", "印度尼西亞"],
        "Thailand": ["Thailand", "TH", "泰国", "泰國"],
        "Philippines": ["Philippines", "PH", "菲律宾", "菲律賓"],
        "Singapore": ["Singapore", "SG", "新加坡"],
        "Vietnam": ["Vietnam", "VN", "越南"],
        "United States": ["United States", "USA", "U.S.", "America", "美国", "美國"],
        "Brazil": ["Brazil", "BR", "巴西"],
        "Japan": ["Japan", "JP", "日本"],
        "Germany": ["Germany", "DE", "德国", "德國"],
        "Taiwan": ["Taiwan", "TW", "台湾", "台灣"],
        "Italy": ["Italy", "IT", "意大利", "義大利"],
        "South Korea": ["South Korea", "Korea", "KR", "韩国", "韓國"],
    }

    def _collect_interactive_states(self, page: Page, url: str) -> None:
        self.selection_contexts = []
        self.context_artifacts = {}
        for visible_labels, normalized_label in self.device_model_labels:
            before_device = len(self.api_candidates)
            clicked_device = self._click_any_label(page, visible_labels)
            if not clicked_device and normalized_label == "游戏挂机专用机":
                self.logger.info("[%s] device tab not found: %s", self.platform, normalized_label)
                continue
            page.wait_for_timeout(1200)
            self._close_obstructive_popups(page)
            if normalized_label == "游戏挂机专用机":
                server_regions = self._visible_server_regions(page)
                if not server_regions:
                    server_regions = [None]
                contexts = []
                for server_region in server_regions:
                    if server_region:
                        self._click_server_region(page, server_region)
                        page.wait_for_timeout(900)
                        self._close_obstructive_popups(page)
                    context = {
                        "device_model": normalized_label,
                        "android_version": None,
                        "server_region": server_region,
                    }
                    contexts.append(context)
                    self._save_context_snapshot(page, url, context)
                for item in self.api_candidates[before_device:]:
                    item["interactive_context"] = contexts[0] if contexts else {
                        "device_model": normalized_label,
                        "android_version": None,
                        "server_region": None,
                    }
                continue

            for android_label in self.android_labels:
                version = android_label.replace("Android", "").strip()
                before = len(self.api_candidates)
                clicked_android = self._click_any_label(page, [android_label, version])
                if not clicked_android and not clicked_device:
                    continue
                page.wait_for_timeout(1800)
                self._close_obstructive_popups(page)
                server_regions = self._visible_server_regions(page)
                if not server_regions:
                    server_regions = [None]
                contexts = []
                for server_region in server_regions:
                    if server_region:
                        self._click_server_region(page, server_region)
                        page.wait_for_timeout(900)
                        self._close_obstructive_popups(page)
                    context = {
                        "device_model": normalized_label,
                        "android_version": version,
                        "server_region": server_region,
                    }
                    contexts.append(context)
                    self._save_context_snapshot(page, url, context)
                for item in self.api_candidates[before:]:
                    item["interactive_context"] = contexts[0] if contexts else {
                        "device_model": normalized_label,
                        "android_version": version,
                        "server_region": None,
                    }

    def _records_from_api(self, source_url: str, screenshot_path: str, html_path: str) -> List[ProductRecord]:
        records: List[ProductRecord] = []
        crawl_utc, crawl_local = now_pair(self.config.timezone)

        for item in self.api_candidates:
            payload = item.get("response_json") or {}
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict) or not isinstance(data.get("configs"), list):
                continue
            context = item.get("interactive_context") or {}

            for config in data["configs"]:
                if not isinstance(config, dict):
                    continue
                config_device_model = self._device_model(config)
                if context.get("device_model") and config_device_model != context.get("device_model"):
                    continue
                device_model = context.get("device_model") or config_device_model
                android_versions = self._android_versions(config, context.get("android_version"), device_model)
                specs = self._specs_from_icons(config.get("icons") or [])
                times = config.get("goodTimes") or []
                if not isinstance(times, list):
                    times = []
                for android_version in android_versions:
                    server_regions = self._server_regions_for(device_model, android_version, context.get("server_region") or specs.get("region"))
                    for good_time in times or [None]:
                        if good_time is not None and not isinstance(good_time, dict):
                            continue
                        show_content = (good_time or {}).get("showContent")
                        duration, billing_period = parse_duration(show_content or "")
                        current_price = (good_time or {}).get("currentPrice") or (good_time or {}).get("goodPrice")
                        old_price = (good_time or {}).get("oldGoodPrice")
                        recommend = (good_time or {}).get("recommendContent") or None
                        raw = {"config": config, "goodTime": good_time, "interactive_context": context}
                        notes = f"api_config_good_time; source_config_name={config.get('configName')}"
                        if not any(server_regions):
                            notes += "; server_not_exposed_by_api"
                        if self.blocked_reason:
                            notes += f"; blocked_reason={self.blocked_reason}"
                        for server_region in server_regions:
                            artifact = self._context_artifact(device_model, android_version, server_region)
                            records.append(
                                ProductRecord(
                                    platform=self.platform,
                                    source_url=source_url,
                                    crawl_time_utc=crawl_utc,
                                    crawl_time_local=crawl_local,
                                    server_region=server_region,
                                    currency="US$" if current_price is not None else None,
                                    product_category="cloud_phone",
                                    product_name="Cloud Phone",
                                    product_model=self._product_model(config, device_model),
                                    device_model=device_model,
                                    android_version=android_version,
                                    cpu=specs.get("cpu"),
                                    ram=specs.get("ram"),
                                    storage=specs.get("storage"),
                                    price=self._cents_to_price(current_price),
                                    original_price=self._cents_to_price(old_price),
                                    billing_period=billing_period,
                                    duration=duration or show_content,
                                    stock_status="sold_out" if config.get("sellOutFlag") else "available",
                                    promotion_text=recommend,
                                    raw_text=compact_text(json.dumps(raw, ensure_ascii=False, default=str), 4000),
                                    extraction_method="api",
                                    confidence="high" if current_price is not None else "medium",
                                    screenshot_path=(artifact or {}).get("screenshot_path") or screenshot_path,
                                    html_path=(artifact or {}).get("html_path") or html_path,
                                    api_response_path=item.get("api_response_path"),
                                    notes=notes,
                                )
                            )

        return self._dedupe_records(records) if records else super()._records_from_api(source_url, screenshot_path, html_path)

    def _device_model(self, config: dict) -> str:
        return "游戏挂机专用机" if config.get("custom") else "高端真机"

    def _product_model(self, config: dict, device_model: str) -> str | None:
        if device_model == "游戏挂机专用机":
            return "游戏挂机专用机"
        return config.get("configName")

    def _android_versions(self, config: dict, context_version: str | None, device_model: str) -> list[str | None]:
        if device_model == "游戏挂机专用机":
            return [None]
        if context_version:
            return [str(context_version)]
        versions = set()
        if config.get("androidVersion") not in [None, ""]:
            versions.add(str(config.get("androidVersion")))
        for icon in config.get("gameIcons") or []:
            if not isinstance(icon, dict):
                continue
            for version in icon.get("androidVersionList") or []:
                if version not in [None, ""]:
                    versions.add(str(version))
        for label in self.android_labels:
            versions.add(label.replace("Android", "").strip())
        return sorted(versions, key=lambda value: float(value))

    def _click_any_label(self, page: Page, labels: list[str]) -> bool:
        for label in labels:
            if self._click_exact_visible_text(page, label):
                return True
            if self._click_visible_text_contains(page, label, max_text_len=80):
                return True
        return False

    def _save_context_snapshot(self, page: Page, url: str, context: dict) -> None:
        suffix = f"vsphone_{context.get('device_model')}"
        if context.get("android_version"):
            suffix += f"_{context.get('android_version')}"
        if context.get("server_region"):
            suffix += f"_{context.get('server_region')}"
        artifact = {
            "device_model": context.get("device_model"),
            "android_version": context.get("android_version"),
            "server_region": context.get("server_region"),
            "screenshot_path": self._save_screenshot(page, suffix=suffix),
            "html_path": self._save_html(page, suffix=suffix),
        }
        key = (
            artifact["device_model"],
            artifact["android_version"],
            artifact["server_region"],
        )
        self.selection_contexts.append(artifact)
        self.context_artifacts[key] = artifact

    def _context_artifact(self, device_model: str, android_version: str | None, server_region: str | None) -> dict | None:
        artifacts = getattr(self, "context_artifacts", {})
        key = (device_model, android_version, server_region)
        if key in artifacts:
            return artifacts[key]
        key = (device_model, android_version, None)
        if key in artifacts:
            return artifacts[key]
        key = (device_model, None, server_region)
        if key in artifacts:
            return artifacts[key]
        return artifacts.get((device_model, None, None))

    def _server_regions_for(
        self,
        device_model: str,
        android_version: str | None,
        known_region: str | None,
    ) -> list[str | None]:
        if known_region:
            return [known_region]
        regions = []
        for context in getattr(self, "selection_contexts", []):
            if context.get("device_model") != device_model:
                continue
            if context.get("android_version") != android_version:
                continue
            region = context.get("server_region")
            if region and region not in regions:
                regions.append(region)
        return regions or [None]

    def _visible_server_regions(self, page: Page) -> list[str]:
        try:
            texts = page.evaluate(
                """
                () => {
                  const selector = 'button, [role=button], label, .el-radio, .el-radio-button, .el-select-dropdown__item, .item, .option, span, div';
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 &&
                      style.visibility !== 'hidden' && style.display !== 'none';
                  };
                  return Array.from(document.querySelectorAll(selector))
                    .filter(visible)
                    .map((el) => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim())
                    .filter((text) => text && text.length <= 50);
                }
                """
            )
        except Exception:
            return []
        regions = []
        for text in texts or []:
            normalized = self._normalize_server_region(text)
            if normalized and normalized not in regions:
                regions.append(normalized)
        return regions

    def _normalize_server_region(self, text: str) -> str | None:
        lowered = (text or "").lower()
        for region, aliases in self.server_aliases.items():
            for alias in aliases:
                alias_l = alias.lower()
                if len(alias_l) <= 3:
                    if lowered == alias_l:
                        return region
                    continue
                if re.search(rf"(?<![a-z0-9]){re.escape(alias_l)}(?![a-z0-9])", lowered):
                    return region
        return None

    def _click_server_region(self, page: Page, server_region: str) -> bool:
        for alias in self.server_aliases.get(server_region, [server_region]):
            if self._click_exact_visible_text(page, alias):
                return True
            if self._click_visible_text_contains(page, alias, max_text_len=80):
                return True
        return False

    def _close_obstructive_popups(self, page: Page) -> None:
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
        except Exception:
            pass
        try:
            page.evaluate(
                """
                () => {
                  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 &&
                      style.visibility !== 'hidden' && style.display !== 'none';
                  };
                  const selectors = [
                    '[aria-label="Close"]', '[aria-label="close"]',
                    '.el-dialog__close', '.close', '.modal-close',
                    '[class*="close"]', '[class*="Close"]',
                    'button', 'span', 'div'
                  ].join(',');
                  const nodes = Array.from(document.querySelectorAll(selectors));
                  for (const el of nodes) {
                    if (!visible(el)) continue;
                    const rect = el.getBoundingClientRect();
                    const text = norm(el.innerText || el.textContent);
                    const className = String(el.className || '').toLowerCase();
                    const looksClose = ['×', 'x', 'close'].includes(text.toLowerCase()) ||
                      className.includes('close');
                    if (!looksClose || rect.width > 90 || rect.height > 90) continue;
                    el.click();
                    return true;
                  }
                  return false;
                }
                """
            )
            page.wait_for_timeout(300)
        except Exception:
            return

    def _specs_from_icons(self, icons: list) -> dict:
        specs = {}
        for icon in icons:
            if not isinstance(icon, dict):
                continue
            name = str(icon.get("name") or "")
            ram = re.search(r"\b(\d+(?:\.\d+)?)\s*G(?:B)?\s*RAM\b", name, re.I)
            storage = re.search(r"\b(\d+(?:\.\d+)?)\s*G(?:B)?\s*Storage\b", name, re.I)
            cpu = re.search(r"\b(\d+\s*cores?)\b", name, re.I)
            if ram:
                specs["ram"] = f"{ram.group(1)}GB"
            if storage:
                specs["storage"] = f"{storage.group(1)}GB"
            if cpu:
                specs["cpu"] = cpu.group(1)
        return specs

    def _cents_to_price(self, value) -> str | None:
        if value in [None, ""]:
            return None
        try:
            return f"{float(value) / 100:.2f}".rstrip("0").rstrip(".")
        except Exception:
            return str(value)

    def _records_from_dom(
        self,
        page: Page,
        source_url: str,
        screenshot_path: str,
        html_path: str,
        extraction_method: str = "dom",
    ) -> List[ProductRecord]:
        for item in self.api_candidates:
            payload = item.get("response_json") or {}
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict) and isinstance(data.get("configs"), list):
                return []
        return super()._records_from_dom(page, source_url, screenshot_path, html_path, extraction_method)

    def scrape_fallbacks(self, page: Page) -> List[ProductRecord]:
        records: List[ProductRecord] = []
        for url in self.target.fallback_urls:
            self.logger.info("[VSPhone] no purchase-page records; trying fallback doc %s", url)
            records.extend(self._scrape_url(page, url, extraction_method="fallback_doc"))
        for record in records:
            note = record.notes or ""
            record.notes = (note + "; " if note else "") + "fallback from official billing documentation, not purchase page"
            record.confidence = "medium" if record.price else "low"
        return records
