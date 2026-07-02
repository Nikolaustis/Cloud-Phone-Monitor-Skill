import json
import re
from typing import Any, List

from playwright.sync_api import Page

from cloud_phone_monitor.schemas import ProductRecord
from cloud_phone_monitor.scrapers.base import BaseScraper
from cloud_phone_monitor.scrapers.plan_cards import (
    parse_duration,
    price_tokens,
    records_from_plan_snapshots,
)
from cloud_phone_monitor.utils.normalize import compact_text, now_pair, redact_payload, safe_filename


class LDCloudScraper(BaseScraper):
    platform = "LDCloud"
    plan_labels = ["VIP", "KVIP", "SVIP", "XVIP", "MVIP"]
    price_list_url = "https://ldq.ldcloud.net/api/en/cph/price/list"
    area_name_map = {
        "tw": "Taiwan",
        "sg": "Singapore",
        "us": "United States",
        "th": "Thailand",
        "hk": "Hong Kong",
        "kr": "Korea",
        "nl": "Netherlands",
    }
    area_label_map = {
        "tw": ["Taiwan", "台湾", "台灣", "TW"],
        "sg": ["Singapore", "新加坡", "SG"],
        "us": ["United States", "USA", "美国", "美國", "US"],
        "th": ["Thailand", "泰国", "泰國", "TH"],
        "hk": ["Hong Kong", "香港", "HK"],
        "kr": ["Korea", "韩国", "韓國", "KR"],
        "nl": ["Netherlands", "荷兰", "荷蘭", "NL"],
    }

    def _collect_interactive_states(self, page: Page, url: str) -> None:
        for label in ["Cloud Phone", "云手机"]:
            if self._click_exact_visible_text(page, label):
                page.wait_for_timeout(1500)
                break
        self.plan_snapshots = []
        options_by_plan = self._options_by_plan_from_api()
        self._collect_price_lists_from_api(page, options_by_plan)
        for plan_label in self.plan_labels:
            if plan_label not in options_by_plan:
                continue
            if not self._click_plan_tab(page, plan_label):
                self.logger.info("[%s] plan tab not found: %s", self.platform, plan_label)
                continue
            page.wait_for_timeout(1200)
            self.plan_snapshots.append(self._snapshot(page, url, plan_label, None, None))

    def _records_from_api(self, source_url: str, screenshot_path: str, html_path: str) -> List[ProductRecord]:
        crawl_utc, crawl_local = now_pair(self.config.timezone)
        price_records = self._records_from_price_lists(source_url, screenshot_path, html_path, crawl_utc, crawl_local)
        if price_records:
            return self._dedupe_records(price_records)

        configs_by_type: dict[int, dict] = {}
        config_path_by_type: dict[int, str | None] = {}
        order_items: list[tuple[dict, str | None]] = []

        for item in self.api_candidates:
            payload = item.get("response_json") or {}
            data = payload.get("data") if isinstance(payload, dict) else None
            url = item.get("url") or ""
            if "cardTypeConfig/list" in url and isinstance(data, list):
                for cfg in data:
                    if isinstance(cfg, dict) and cfg.get("cardType") is not None:
                        configs_by_type[int(cfg["cardType"])] = cfg
                        config_path_by_type[int(cfg["cardType"])] = item.get("api_response_path")
            elif "price/order" in url and isinstance(data, list):
                order_items.append((payload, item.get("api_response_path")))

        records: List[ProductRecord] = []
        seen_keys = set()
        for payload, api_path in order_items:
            for group in payload.get("data", []):
                if not isinstance(group, dict):
                    continue
                for area in group.get("areas") or []:
                    if not isinstance(area, dict):
                        continue
                    area_code = str(area.get("area") or "")
                    server_region = self._server_region(area_code)
                    for typ in area.get("types") or []:
                        if not isinstance(typ, dict):
                            continue
                        card_type = typ.get("cardType")
                        key = (area.get("area"), card_type)
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        cfg = configs_by_type.get(int(card_type)) if card_type is not None else {}
                        raw = {"order": typ, "area": area, "config": cfg}
                        price = self._first_by_key(raw, {"price", "currentprice", "saleprice", "payprice", "amount"})
                        original_price = self._first_by_key(raw, {"originalprice", "originprice", "oldprice", "listprice"})
                        duration = self._first_by_key(raw, {"duration", "durationtext", "validdays", "days", "month"})
                        currency = self._first_by_key(raw, {"currency", "currencycode", "currencydisplaycode"})
                        api_response_path = api_path
                        if not api_response_path and card_type is not None:
                            api_response_path = config_path_by_type.get(int(card_type))
                        notes = "api_price_order_with_card_type_config"
                        if not price:
                            notes += "; price requires logged-in page/API"
                        if self.blocked_reason:
                            notes += f"; blocked_reason={self.blocked_reason}"
                        records.append(
                            ProductRecord(
                                platform=self.platform,
                                source_url=source_url,
                                crawl_time_utc=crawl_utc,
                                crawl_time_local=crawl_local,
                                region_selected=server_region,
                                server_region=server_region,
                                currency="US$",
                                product_category="cloud_phone",
                                product_name="Cloud Phone",
                                product_model=group.get("name"),
                                device_model=typ.get("cardName") or cfg.get("cardName"),
                                android_version=self._android_version(typ.get("os") or cfg.get("os")),
                                cpu=f"{cfg.get('core')} cores" if cfg.get("core") else None,
                                ram=f"{cfg.get('ramM')}GB" if cfg.get("ramM") else None,
                                storage=f"{cfg.get('rom')}GB" if cfg.get("rom") else None,
                                price=self._cents_to_price(price),
                                original_price=self._cents_to_price(original_price),
                                duration=self._format_scalar(duration),
                                stock_status="sold_out" if typ.get("sellout") or area.get("sellout") else "available",
                                raw_text=compact_text(json.dumps(raw, ensure_ascii=False, default=str), 4000),
                                extraction_method="api",
                                confidence="high" if price else "medium",
                                screenshot_path=screenshot_path,
                                html_path=html_path,
                                api_response_path=api_response_path,
                                notes=notes,
                            )
                        )

        if records:
            return self._dedupe_records(records)

        return super()._records_from_api(source_url, screenshot_path, html_path)

    def _snapshot(self, page: Page, url: str, plan_label: str, android_version: str | None, server_label: str | None) -> dict:
        suffix = f"{safe_filename(url.split('//')[-1])}_plan_{safe_filename(plan_label)}"
        if android_version:
            suffix += f"_android_{safe_filename(str(android_version))}"
        if server_label:
            suffix += f"_server_{safe_filename(str(server_label))}"
        return {
            "plan": plan_label,
            "body_text": self._visible_body_text(page),
            "active_texts": self._visible_active_texts(page),
            "cards": self._visible_plan_cards(page),
            "screenshot_path": self._save_screenshot(page, suffix=suffix),
            "html_path": self._save_html(page, suffix=suffix),
        }

    def _options_by_plan_from_api(self) -> dict[str, list[dict]]:
        options: dict[str, list[dict]] = {}
        configs_by_type = self._configs_by_type()
        for item in self.api_candidates:
            url = item.get("url") or ""
            payload = item.get("response_json") or {}
            data = payload.get("data") if isinstance(payload, dict) else None
            if "price/order" not in url or not isinstance(data, list):
                continue
            for group in data:
                if not isinstance(group, dict):
                    continue
                plan = group.get("name")
                if not plan:
                    continue
                seen = set()
                for area in group.get("areas") or []:
                    if not isinstance(area, dict):
                        continue
                    area_code = str(area.get("area") or "")
                    server_labels = self.area_label_map.get(area_code.lower(), [area_code])
                    server_region = self._server_region(area_code)
                    for typ in area.get("types") or []:
                        if not isinstance(typ, dict):
                            continue
                        card_type = typ.get("cardType")
                        cfg = configs_by_type.get(int(card_type)) if card_type is not None else {}
                        android_version = self._android_version(typ.get("os"))
                        marker = (card_type, area_code)
                        if marker in seen:
                            continue
                        seen.add(marker)
                        options.setdefault(str(plan), []).append(
                            {
                                "plan": str(plan),
                                "area_code": area_code,
                                "server_region": server_region,
                                "card_name": typ.get("cardName"),
                                "card_type": card_type,
                                "android_version": android_version,
                                "server_labels": server_labels,
                                "cpu": f"{cfg.get('core')} cores" if cfg.get("core") else None,
                                "ram": f"{cfg.get('ramM')}GB" if cfg.get("ramM") else None,
                                "storage": f"{cfg.get('rom')}GB" if cfg.get("rom") else None,
                                "sellout": bool(typ.get("sellout") or area.get("sellout")),
                            }
                        )
        return options

    def _records_from_dom(
        self,
        page: Page,
        source_url: str,
        screenshot_path: str,
        html_path: str,
        extraction_method: str = "dom",
    ) -> List[ProductRecord]:
        if self._has_price_list_api():
            return []
        records = records_from_plan_snapshots(
            self.platform,
            source_url,
            getattr(self, "plan_snapshots", []),
            self.config.timezone,
        )
        if records:
            return self._dedupe_records(records)
        return super()._records_from_dom(page, source_url, screenshot_path, html_path, extraction_method)

    def _android_version(self, value) -> str | None:
        if not value:
            return None
        text = str(value)
        return text.replace("Android", "").strip() or text

    def _first_by_key(self, value: Any, keys: set[str]) -> Any:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in keys and item not in [None, ""]:
                    return item
            for item in value.values():
                found = self._first_by_key(item, keys)
                if found not in [None, ""]:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = self._first_by_key(item, keys)
                if found not in [None, ""]:
                    return found
        return None

    def _format_scalar(self, value: Any) -> str | None:
        if value in [None, ""]:
            return None
        return str(value)

    def _click_plan_tab(self, page: Page, plan_label: str) -> bool:
        try:
            clicked = page.evaluate(
                """
                (planLabel) => {
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 &&
                      style.visibility !== 'hidden' && style.display !== 'none';
                  };
                  const nodes = Array.from(document.querySelectorAll('.series-item'));
                  const el = nodes.find((node) => node.classList.contains(planLabel) && visible(node));
                  if (!el) return false;
                  el.scrollIntoView({block: 'center', inline: 'center'});
                  el.click();
                  return true;
                }
                """,
                plan_label,
            )
            if clicked:
                return True
        except Exception as exc:
            self.logger.debug("[%s] class-based plan tab click skipped for %s: %s", self.platform, plan_label, exc)
        return self._click_exact_visible_text(page, plan_label) or self._click_visible_text_contains(
            page,
            plan_label,
            max_text_len=24,
        )

    def _collect_price_lists_from_api(self, page: Page, options_by_plan: dict[str, list[dict]]) -> None:
        requests = self._price_list_requests(options_by_plan)
        if not requests:
            return
        self.logger.info("[%s] collecting price/list combinations: %s", self.platform, len(requests))
        try:
            results = page.evaluate(
                """
                async ([url, requests]) => {
                  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
                  const out = [];
                  for (const request of requests) {
                    const body = new URLSearchParams(request.payload).toString();
                    try {
                      const response = await fetch(url, {
                        method: 'POST',
                        headers: {'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'},
                        body
                      });
                      const text = await response.text();
                      let json = null;
                      try {
                        json = JSON.parse(text);
                      } catch (error) {
                        json = null;
                      }
                      out.push({
                        status: response.status,
                        request_payload: request.payload,
                        response_json: json,
                        response_text: json ? null : text.slice(0, 200000)
                      });
                    } catch (error) {
                      out.push({
                        status: 0,
                        request_payload: request.payload,
                        response_json: null,
                        response_text: String(error)
                      });
                    }
                    await sleep(120);
                  }
                  return out;
                }
                """,
                [self.price_list_url, requests],
            )
        except Exception as exc:
            self.logger.warning("[%s] direct price/list collection failed: %s", self.platform, exc)
            return

        for result in results or []:
            payload = result.get("response_json")
            if payload is None and not result.get("response_text"):
                continue
            self._store_manual_api_candidate(
                self.price_list_url,
                int(result.get("status") or 0),
                payload,
                result.get("request_payload") or {},
                result.get("response_text"),
            )

    def _price_list_requests(self, options_by_plan: dict[str, list[dict]]) -> list[dict]:
        template = self._price_list_template()
        existing = self._existing_price_list_keys()
        requests = []
        seen = set(existing)
        for options in options_by_plan.values():
            for option in options:
                area_code = option.get("area_code")
                card_type = option.get("card_type")
                if area_code in [None, ""] or card_type in [None, ""]:
                    continue
                key = (str(area_code), str(card_type))
                if key in seen:
                    continue
                seen.add(key)
                payload = dict(template)
                payload.update(
                    {
                        "cardType": str(card_type),
                        "area": str(area_code),
                        "priceType": str(payload.get("priceType") or "20"),
                        "payType": str(payload.get("payType") or "3"),
                        "category": str(payload.get("category") or "0"),
                        "minNum": str(payload.get("minNum") or "1"),
                    }
                )
                requests.append({"payload": payload})
        return requests

    def _price_list_template(self) -> dict[str, str]:
        for item in self.api_candidates:
            if "price/list" not in (item.get("url") or ""):
                continue
            payload = item.get("request_payload")
            if isinstance(payload, dict):
                return {str(key): str(value) for key, value in payload.items() if value not in [None, ""]}
        return {
            "priceType": "20",
            "payType": "3",
            "category": "0",
            "minNum": "1",
            "channelId": "10400",
            "pchannelId": "10401",
        }

    def _existing_price_list_keys(self) -> set[tuple[str, str]]:
        keys = set()
        for item in self.api_candidates:
            if "price/list" not in (item.get("url") or ""):
                continue
            payload = item.get("request_payload")
            if not isinstance(payload, dict):
                continue
            area_code = payload.get("area")
            card_type = payload.get("cardType")
            if area_code not in [None, ""] and card_type not in [None, ""]:
                keys.add((str(area_code), str(card_type)))
        return keys

    def _records_from_price_lists(
        self,
        source_url: str,
        screenshot_path: str,
        html_path: str,
        crawl_utc: str,
        crawl_local: str,
    ) -> List[ProductRecord]:
        context_by_key = self._price_context_by_key()
        records: List[ProductRecord] = []
        for item in self.api_candidates:
            if "price/list" not in (item.get("url") or ""):
                continue
            payload = item.get("response_json") or {}
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list):
                continue
            request_payload = item.get("request_payload") if isinstance(item.get("request_payload"), dict) else {}
            card_type = self._format_scalar(request_payload.get("cardType"))
            area_code = self._format_scalar(request_payload.get("area"))
            if not card_type:
                card_type = self._format_scalar((data[0] or {}).get("cardType")) if data else None
            context = context_by_key.get((str(area_code or ""), str(card_type or "")), {})
            for price_item in data:
                if not isinstance(price_item, dict):
                    continue
                duration, billing_period = self._duration_from_price_item(price_item)
                raw = {
                    "request": request_payload,
                    "context": context,
                    "price_item": price_item,
                }
                records.append(
                    ProductRecord(
                        platform=self.platform,
                        source_url=source_url,
                        crawl_time_utc=crawl_utc,
                        crawl_time_local=crawl_local,
                        region_selected=context.get("server_region") or self._server_region(area_code),
                        server_region=context.get("server_region") or self._server_region(area_code),
                        currency="US$",
                        product_category="cloud_phone",
                        product_name="Cloud Phone",
                        product_model=context.get("plan") or self._plan_from_card_type_desc(price_item.get("cardTypeDesc")),
                        device_model=context.get("card_name") or self._format_scalar(price_item.get("cardTypeDesc")),
                        android_version=context.get("android_version") or self._android_version(price_item.get("cardTypeDesc")),
                        cpu=context.get("cpu"),
                        ram=context.get("ram"),
                        storage=context.get("storage"),
                        price=self._cents_to_price(price_item.get("price")),
                        original_price=self._cents_to_price(price_item.get("originalPrice")),
                        billing_period=billing_period,
                        duration=duration,
                        stock_status="sold_out" if context.get("sellout") or price_item.get("offline") else "available",
                        promotion_text=self._promotion_text(price_item),
                        raw_text=compact_text(json.dumps(raw, ensure_ascii=False, default=str), 4000),
                        extraction_method="api",
                        confidence="high",
                        screenshot_path=screenshot_path,
                        html_path=html_path,
                        api_response_path=item.get("api_response_path"),
                        notes=self._price_list_notes(request_payload, price_item, context),
                    )
                )
        return records

    def _price_context_by_key(self) -> dict[tuple[str, str], dict]:
        contexts: dict[tuple[str, str], dict] = {}
        for options in self._options_by_plan_from_api().values():
            for option in options:
                area_code = option.get("area_code")
                card_type = option.get("card_type")
                if area_code in [None, ""] or card_type in [None, ""]:
                    continue
                contexts[(str(area_code), str(card_type))] = option
        return contexts

    def _configs_by_type(self) -> dict[int, dict]:
        configs: dict[int, dict] = {}
        for item in self.api_candidates:
            payload = item.get("response_json") or {}
            data = payload.get("data") if isinstance(payload, dict) else None
            if "cardTypeConfig/list" not in (item.get("url") or "") or not isinstance(data, list):
                continue
            for cfg in data:
                if isinstance(cfg, dict) and cfg.get("cardType") is not None:
                    configs[int(cfg["cardType"])] = cfg
        return configs

    def _store_manual_api_candidate(
        self,
        url: str,
        status: int,
        payload: Any,
        request_payload: dict,
        response_text: str | None = None,
    ) -> None:
        filename = f"{len(self.api_candidates)+1:04d}_{safe_filename(url)}.json"
        path = self.api_dir / filename
        item = {
            "platform": self.platform,
            "url": url,
            "method": "POST",
            "status": status,
            "resource_type": "manual_fetch",
            "request_headers": {},
            "response_headers": {},
            "request_payload": redact_payload(request_payload),
            "response_json": redact_payload(payload) if payload is not None else None,
            "response_text": response_text if payload is None else None,
            "api_response_path": str(path),
        }
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        self.api_candidates.append(item)

    def _duration_from_price_item(self, price_item: dict) -> tuple[str | None, str | None]:
        duration, billing_period = parse_duration(str(price_item.get("name") or ""))
        if duration:
            return duration, billing_period
        hours = price_item.get("duration")
        if hours in [None, ""]:
            return None, None
        try:
            hour_value = float(hours)
            if hour_value.is_integer():
                hour_text = str(int(hour_value))
            else:
                hour_text = str(hour_value)
            if hour_value % 24 == 0:
                return f"{int(hour_value // 24)} day", "day"
            return f"{hour_text} hour", "hour"
        except Exception:
            return str(hours), None

    def _server_region(self, area_code: Any) -> str | None:
        if area_code in [None, ""]:
            return None
        code = str(area_code).lower()
        return self.area_name_map.get(code, str(area_code))

    def _plan_from_card_type_desc(self, value: Any) -> str | None:
        if value in [None, ""]:
            return None
        match = re.match(r"([A-Z]+)", str(value).upper())
        return match.group(1) if match else str(value)

    def _promotion_text(self, price_item: dict) -> str | None:
        parts = []
        for key in ["name", "cornerMarker", "description"]:
            value = price_item.get(key)
            if value not in [None, ""]:
                parts.append(str(value))
        return "; ".join(parts) or None

    def _price_list_notes(self, request_payload: dict, price_item: dict, context: dict) -> str:
        parts = [
            "api_price_list",
            f"area_code={request_payload.get('area')}",
            f"cardType={request_payload.get('cardType')}",
        ]
        if context.get("sellout"):
            parts.append("sellout=true")
        if price_item.get("productId") not in [None, ""]:
            parts.append(f"productId={price_item.get('productId')}")
        if self.blocked_reason:
            parts.append(f"blocked_reason={self.blocked_reason}")
        return "; ".join(parts)

    def _cents_to_price(self, value: Any) -> str | None:
        if value in [None, ""]:
            return None
        try:
            return f"{float(value) / 100:.2f}".rstrip("0").rstrip(".")
        except Exception:
            return str(value)

    def _has_price_list_api(self) -> bool:
        for item in self.api_candidates:
            if "price/list" not in (item.get("url") or ""):
                continue
            payload = item.get("response_json") or {}
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, list) and data:
                return True
        return False

    def _has_plan_price_snapshots(self) -> bool:
        for snapshot in getattr(self, "plan_snapshots", []):
            texts = [snapshot.get("body_text") or ""]
            texts.extend((card.get("text") or "") for card in snapshot.get("cards") or [])
            if any(price_tokens(text) and parse_duration(text)[0] for text in texts):
                return True
        return False
