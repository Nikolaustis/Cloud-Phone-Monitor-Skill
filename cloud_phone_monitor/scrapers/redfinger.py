import json
import re
import time
from pathlib import Path
from typing import Any, List
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page

from cloud_phone_monitor.schemas import ProductRecord
from cloud_phone_monitor.scrapers.base import BaseScraper
from cloud_phone_monitor.scrapers.plan_cards import records_from_plan_snapshots
from cloud_phone_monitor.utils.normalize import (
    compact_text,
    now_pair,
    redact_payload,
    safe_filename,
)


PUBLIC_RECOMMEND_URL = (
    "https://www.cloudemulator.net/api/v2/osfingerauth/"
    "gameRecommendGoods/configs.json?limit=100&pageSource=buy"
)

PRICE_API_TOKEN = "getgoods"
OPTIONS_API_TOKEN = "newversionpadclassify/goodsoption"
PLAN_CONFIG_API_TOKEN = "getpadconfig"


class RedfingerScraper(BaseScraper):
    """Collect Redfinger price SKUs through the signed purchase-page flow.

    Redfinger does not expose usable price/SKU data until the page has selected a
    plan, Android version, and server. Public game recommendations and generic
    page text are diagnostics only; neither is a valid product-price record.
    """

    platform = "Redfinger"
    fallback_plan_labels = ["VIP", "KVIP", "SVIP", "XVIP"]

    def scrape(self) -> List[ProductRecord]:
        records = super().scrape()
        self._write_collection_summary(records)
        return records

    def _collect_interactive_states(self, page: Page, url: str) -> None:
        for label in ["Cloud Phone", "云手机"]:
            if self._click_exact_visible_text(page, label):
                page.wait_for_timeout(800)
                break

        self.plan_snapshots: list[dict] = []
        self.redfinger_interaction_diagnostics: list[dict] = []
        self.redfinger_artifact_write_failures: list[dict] = []
        self._redfinger_price_api_seen = False

        plan_labels = self._configured_plan_labels()
        if not plan_labels:
            plan_labels = list(self.fallback_plan_labels)
        self.logger.info("[%s] discovered plan labels: %s", self.platform, ", ".join(plan_labels))

        for plan_label in plan_labels:
            plan_start = len(self.api_candidates)
            if not self._click_redfinger_choice(page, plan_label, kind="plan"):
                self.logger.info("[%s] plan tab not found: %s", self.platform, plan_label)
                self._append_interaction_diagnostic(
                    plan=plan_label,
                    stage="plan",
                    result="not_found",
                )
                continue

            if not self._wait_for_api_token(page, plan_start, OPTIONS_API_TOKEN, timeout_ms=8_000):
                self._append_interaction_diagnostic(
                    plan=plan_label,
                    stage="goods_option",
                    result="timeout",
                )
                self._save_plan_snapshot(page, url, plan_label, None, None, "options_timeout")
                continue

            option_attempts = self._option_attempts_from_recent_options(plan_start)
            if not option_attempts:
                self._append_interaction_diagnostic(
                    plan=plan_label,
                    stage="goods_option",
                    result="empty_options",
                )
                self._save_plan_snapshot(page, url, plan_label, None, None, "no_options")
                continue

            # A goodsClassifyId represents one purchase configuration. One server
            # is sufficient to request its price list; server variants are retained
            # in the structured goodsOption evidence and folded into supported regions.
            for attempt in option_attempts:
                self._collect_price_for_option(page, url, plan_label, attempt)

    def _collect_price_for_option(self, page: Page, url: str, plan_label: str, option: dict) -> None:
        android_label = option.get("android_version")
        server_label = option.get("server_region")
        goods_classify_id = option.get("goods_classify_id")

        if android_label and not self._click_redfinger_choice(page, android_label, kind="android"):
            self._append_interaction_diagnostic(
                plan=plan_label,
                stage="android",
                result="not_found",
                goods_classify_id=goods_classify_id,
                android_version=android_label,
                server_region=server_label,
            )
            self._save_plan_snapshot(page, url, plan_label, android_label, server_label, "android_not_found")
            return

        page.wait_for_timeout(450)
        before_server = len(self.api_candidates)
        server_clicked = bool(server_label and self._click_redfinger_choice(page, server_label, kind="server"))
        if not server_clicked:
            self._append_interaction_diagnostic(
                plan=plan_label,
                stage="server",
                result="not_found",
                goods_classify_id=goods_classify_id,
                android_version=android_label,
                server_region=server_label,
            )
            self._save_plan_snapshot(page, url, plan_label, android_label, server_label, "server_not_found")
            return

        price_seen = self._wait_for_api_token(page, before_server, PRICE_API_TOKEN, timeout_ms=6_000)
        if price_seen:
            self._redfinger_price_api_seen = True
            result = "price_api_seen"
        else:
            result = "price_api_timeout"
        self._append_interaction_diagnostic(
            plan=plan_label,
            stage="price",
            result=result,
            goods_classify_id=goods_classify_id,
            android_version=android_label,
            server_region=server_label,
            server_code=option.get("server_code"),
        )
        self._annotate_recent_api_context(
            before_server,
            {
                "product_model": plan_label,
                "android_version": android_label,
                "server_region": server_label,
                "server_code": option.get("server_code"),
                "goods_classify_id": goods_classify_id,
            },
        )
        self._save_plan_snapshot(page, url, plan_label, android_label, server_label, result)

    def scrape_fallbacks(self, page: Page) -> List[ProductRecord]:
        """Persist public recommendations as evidence only, never as SKU records."""
        try:
            response = self.context.request.get(PUBLIC_RECOMMEND_URL, timeout=self.config.browser_timeout_ms)
            payload = response.json()
            self._store_manual_api_candidate(PUBLIC_RECOMMEND_URL, response.status, payload, dict(response.headers))
        except Exception as exc:
            self.logger.warning("[Redfinger] public recommendation diagnostic request failed: %s", exc)

        reason = (
            "no_signed_getGoods_price_api_observed"
            if not self._has_signed_getgoods()
            else "signed_getGoods_returned_no_valid_price_duration_sku"
        )
        self._write_price_diagnostic(reason)
        self.logger.warning("[Redfinger] no valid price SKU extracted: %s", reason)
        return []

    def _records_from_api(self, source_url: str, screenshot_path: str, html_path: str) -> List[ProductRecord]:
        crawl_utc, crawl_local = now_pair(self.config.timezone)
        classify_specs = self._classify_specs_by_key()
        signed_records: List[ProductRecord] = []

        for item in self.api_candidates:
            url = (item.get("url") or "").lower()
            if PRICE_API_TOKEN not in url:
                continue
            payload = item.get("response_json") or {}
            signed_records.extend(
                self._records_from_goods(
                    payload,
                    self._query_params(item.get("url") or ""),
                    classify_specs,
                    source_url,
                    screenshot_path,
                    html_path,
                    item.get("api_response_path"),
                    crawl_utc,
                    crawl_local,
                )
            )

        # Do not fall back to recommendation APIs or generic DOM/API parsing.
        # They can produce game metadata, wallet balances, and navigation text
        # that look like product rows but are not purchasable price SKUs.
        return self._dedupe_records(signed_records)

    def _records_from_dom(
        self,
        page: Page,
        source_url: str,
        screenshot_path: str,
        html_path: str,
        extraction_method: str = "dom",
    ) -> List[ProductRecord]:
        if self._has_signed_getgoods():
            return []
        records = records_from_plan_snapshots(
            self.platform,
            source_url,
            getattr(self, "plan_snapshots", []),
            self.config.timezone,
        )
        valid_records = [record for record in records if self._is_valid_price_record(record)]
        return self._dedupe_records(valid_records)

    @staticmethod
    def _is_valid_price_record(record: ProductRecord) -> bool:
        return bool(
            record.product_category == "cloud_phone"
            and record.price not in [None, ""]
            and record.duration not in [None, ""]
        )

    def _records_from_goods(
        self,
        payload: dict,
        query_params: dict[str, str],
        classify_specs: dict[tuple[str | None, str | None], list[dict]],
        source_url: str,
        screenshot_path: str,
        html_path: str,
        api_path: str | None,
        crawl_utc: str,
        crawl_local: str,
    ) -> List[ProductRecord]:
        records: List[ProductRecord] = []
        classify_value = query_params.get("classifyValue")
        goods_classify_id = query_params.get("goodsClassifyId")
        specs_list = (
            classify_specs.get((classify_value, goods_classify_id))
            or classify_specs.get((classify_value, None))
            or [{}]
        )
        for node in self._iter_goods_nodes(payload):
            raw_text = json.dumps(node, ensure_ascii=False, default=str)
            duration, billing_period = self._duration_from_goods(node)
            price = self._cents_to_price(
                self._first_by_key(node, {"goodsprice", "price", "saleprice", "currentprice", "payprice", "amount"})
            )
            if price in [None, ""] or duration in [None, ""]:
                continue
            source_product_name = self._first_by_key(node, {"goodsname", "commodityname", "name", "title"})
            promotion_text = self._promotion_text(node)
            for specs in specs_list:
                product_model = specs.get("product_model") or self._first_by_key(
                    node, {"classname", "classifyname", "configname", "model"}
                )
                notes = f"signed_getGoods_api; classifyValue={classify_value}; goodsClassifyId={goods_classify_id}"
                if source_product_name not in [None, ""]:
                    notes += f"; source_product_name={source_product_name}"
                if specs.get("server_code"):
                    notes += f"; server_code={specs.get('server_code')}"
                records.append(
                    ProductRecord(
                        platform=self.platform,
                        source_url=source_url,
                        crawl_time_utc=crawl_utc,
                        crawl_time_local=crawl_local,
                        region_selected=specs.get("server_region"),
                        server_region=specs.get("server_region"),
                        currency=self._currency(node),
                        product_category="cloud_phone",
                        product_name="Cloud Phone",
                        product_model=self._format_scalar(product_model),
                        android_version=specs.get("android_version"),
                        cpu=specs.get("cpu"),
                        ram=specs.get("ram"),
                        storage=specs.get("storage"),
                        price=price,
                        original_price=self._cents_to_price(
                            self._first_by_key(node, {"originalgoodsprice", "originalprice", "oldprice", "listprice", "marketprice"})
                        ),
                        discount_price=self._cents_to_price(
                            self._first_by_key(node, {"discountgoodsprice", "discountprice"})
                        ),
                        billing_period=self._format_scalar(billing_period),
                        duration=self._format_scalar(duration),
                        stock_status="available",
                        promotion_text=promotion_text,
                        raw_text=compact_text(raw_text, 4000),
                        extraction_method="api_signed",
                        confidence="high",
                        screenshot_path=screenshot_path,
                        html_path=html_path,
                        api_response_path=api_path,
                        notes=notes,
                    )
                )
        return records

    def _configured_plan_labels(self) -> list[str]:
        labels: list[str] = []
        for item in self.api_candidates:
            url = (item.get("url") or "").lower()
            if PLAN_CONFIG_API_TOKEN not in url:
                continue
            payload = item.get("response_json") or {}
            info = payload.get("resultInfo") if isinstance(payload, dict) else None
            plans = info.get("padClassifyIconDtoList") if isinstance(info, dict) else None
            if not isinstance(plans, list):
                continue
            for plan in plans:
                if not isinstance(plan, dict):
                    continue
                # Current web purchase tabs are the version=2 classes. This avoids
                # obsolete V8/S8/S10/K10 labels returned for legacy clients.
                if str(plan.get("version") or "") not in {"2", ""}:
                    continue
                if str(plan.get("status") or "") not in {"1", "2", ""}:
                    continue
                label = self._format_scalar(plan.get("classifyName"))
                if label and label not in labels:
                    labels.append(label)
        return labels

    def _option_attempts_from_recent_options(self, start_index: int) -> list[dict]:
        options: list[dict] = []
        seen: set[tuple[str | None, str | None]] = set()
        for item in self.api_candidates[start_index:]:
            url = item.get("url") or ""
            if OPTIONS_API_TOKEN not in url.lower():
                continue
            payload = item.get("response_json") or {}
            info = payload.get("resultInfo") if isinstance(payload, dict) else None
            attributes = (info or {}).get("attributes") if isinstance(info, dict) else None
            if not isinstance(attributes, list):
                continue
            for attr in attributes:
                if not isinstance(attr, dict):
                    continue
                goods_classify_id = self._format_scalar(attr.get("goodsClassifyId"))
                rom = attr.get("romVersion") if isinstance(attr.get("romVersion"), dict) else {}
                idc = attr.get("idcCode") if isinstance(attr.get("idcCode"), dict) else {}
                android_version = self._format_scalar(rom.get("name") or rom.get("attributeValue"))
                server_region = self._format_scalar(idc.get("name") or idc.get("attributeValue"))
                server_code = self._format_scalar(idc.get("attributeValue"))
                if not goods_classify_id or not android_version or not server_region:
                    continue
                key = (goods_classify_id, android_version)
                # One stable server per purchase configuration is enough to invoke
                # getGoods. Prefer entries marked recommended/default when present.
                candidate = {
                    "goods_classify_id": goods_classify_id,
                    "android_version": android_version,
                    "server_region": server_region,
                    "server_code": server_code,
                    "recommended": int(attr.get("recommendFlag") or 0),
                    "default": int(idc.get("defaultSelectFlag") or 0),
                }
                existing_index = next(
                    (index for index, value in enumerate(options) if (value["goods_classify_id"], value["android_version"]) == key),
                    None,
                )
                if existing_index is None:
                    options.append(candidate)
                    seen.add(key)
                else:
                    existing = options[existing_index]
                    if (candidate["default"], candidate["recommended"]) > (existing["default"], existing["recommended"]):
                        options[existing_index] = candidate
        return options

    def _click_redfinger_choice(self, page: Page, label: str, kind: str) -> bool:
        """Click a compact, visible Redfinger picker option without broad text matching."""
        try:
            return bool(
                page.evaluate(
                    """
                    ([label, kind]) => {
                      const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                      const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0 &&
                          style.visibility !== 'hidden' && style.display !== 'none' &&
                          style.pointerEvents !== 'none';
                      };
                      const candidates = Array.from(document.querySelectorAll(
                        'button,[role=tab],[role=button],li,label,span,div'
                      ));
                      const exact = candidates.filter((el) => {
                        const text = norm(el.innerText || el.textContent);
                        return visible(el) && text === label && text.length <= 80;
                      });
                      const score = (el) => {
                        const klass = String(el.className || '').toLowerCase();
                        const role = String(el.getAttribute('role') || '').toLowerCase();
                        let value = 0;
                        if (el.tagName === 'BUTTON') value += 12;
                        if (role === 'tab' || role === 'button') value += 10;
                        if (/(tab|option|select|choice|item|radio|server|android|version)/.test(klass)) value += 8;
                        if (kind === 'plan' && /(vip|plan|classify)/.test(klass)) value += 5;
                        if (kind === 'server' && /(server|idc|region)/.test(klass)) value += 5;
                        if (kind === 'android' && /(android|rom|version)/.test(klass)) value += 5;
                        return value;
                      };
                      exact.sort((a, b) => score(b) - score(a));
                      const target = exact[0];
                      if (!target) return false;
                      target.scrollIntoView({block: 'center', inline: 'center'});
                      target.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                      target.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
                      target.click();
                      return true;
                    }
                    """,
                    [label, kind],
                )
            )
        except Exception as exc:
            self.logger.debug("[%s] %s choice click skipped for %s: %s", self.platform, kind, label, exc)
            return False

    def _wait_for_api_token(self, page: Page, start_index: int, token: str, timeout_ms: int) -> bool:
        deadline = time.monotonic() + timeout_ms / 1000
        token = token.lower()
        while time.monotonic() < deadline:
            for item in self.api_candidates[start_index:]:
                if token in (item.get("url") or "").lower() and int(item.get("status") or 0) < 400:
                    return True
            page.wait_for_timeout(200)
        return False

    def _annotate_recent_api_context(self, start_index: int, context: dict) -> None:
        for item in self.api_candidates[start_index:]:
            if PRICE_API_TOKEN in (item.get("url") or "").lower():
                item["interactive_context"] = context

    def _save_plan_snapshot(
        self,
        page: Page,
        url: str,
        plan_label: str,
        android_label: str | None,
        server_label: str | None,
        result: str,
    ) -> None:
        # Keep the leaf filename short; the full URL/context is stored in JSON.
        suffix = f"rf_p-{plan_label}_a-{android_label or 'na'}_s-{server_label or 'na'}_{result}"
        screenshot_path = self._save_screenshot(page, suffix=suffix)
        html_path = self._save_html(page, suffix=suffix)
        artifact_context = {
            "source_url": url,
            "plan": plan_label,
            "android_version": android_label,
            "server_region": server_label,
            "result": result,
            "artifact_suffix": suffix,
        }
        if not screenshot_path or not html_path:
            self.redfinger_artifact_write_failures.append(
                {
                    **artifact_context,
                    "screenshot_saved": bool(screenshot_path),
                    "html_saved": bool(html_path),
                }
            )
        self.plan_snapshots.append(
            {
                "plan": plan_label,
                "body_text": self._visible_body_text(page),
                "active_texts": self._visible_active_texts(page),
                "cards": self._visible_plan_cards(page),
                "screenshot_path": screenshot_path,
                "html_path": html_path,
                "artifact_context": artifact_context,
            }
        )

    def _append_interaction_diagnostic(self, **entry: Any) -> None:
        entry["api_candidate_count"] = len(self.api_candidates)
        self.redfinger_interaction_diagnostics.append(entry)

    def _write_price_diagnostic(self, reason: str) -> None:
        """Write failure-only Redfinger evidence without treating it as product data."""
        path = self.artifact_dir / "redfinger_price_diagnostic.json"
        payload = self._collection_summary_payload(records=[], reason=reason)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(redact_payload(payload), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _write_collection_summary(self, records: List[ProductRecord]) -> None:
        """Persist combination-level collection evidence for every Redfinger run."""
        path = self.artifact_dir / "redfinger_collection_summary.json"
        payload = self._collection_summary_payload(records=records, reason=None)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(redact_payload(payload), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _collection_summary_payload(
        self,
        records: List[ProductRecord],
        reason: str | None,
    ) -> dict[str, Any]:
        diagnostics = list(getattr(self, "redfinger_interaction_diagnostics", []) or [])

        def combo_key(entry: dict) -> tuple:
            return (
                entry.get("plan"),
                entry.get("goods_classify_id"),
                entry.get("android_version"),
                entry.get("server_code") or entry.get("server_region"),
            )

        combo_entries = [
            entry for entry in diagnostics
            if entry.get("stage") in {"android", "server", "price"}
        ]
        attempted = {combo_key(entry) for entry in combo_entries if any(combo_key(entry))}
        seen = {
            combo_key(entry) for entry in diagnostics
            if entry.get("stage") == "price" and entry.get("result") == "price_api_seen"
        }
        valid_api_paths = {
            str(record.api_response_path)
            for record in records
            if self._is_valid_price_record(record) and record.api_response_path
        }
        successful = set()
        candidate_summary = []
        for item in self.api_candidates:
            url = item.get("url") or ""
            lowered = url.lower()
            if any(token in lowered for token in [PLAN_CONFIG_API_TOKEN, OPTIONS_API_TOKEN, PRICE_API_TOKEN, "gamerecommendgoods"]):
                candidate_summary.append(
                    {
                        "url": url,
                        "status": item.get("status"),
                        "method": item.get("method"),
                        "api_response_path": item.get("api_response_path"),
                        "interactive_context": item.get("interactive_context"),
                    }
                )
            if PRICE_API_TOKEN in lowered and str(item.get("api_response_path")) in valid_api_paths:
                context = item.get("interactive_context") or {}
                key = (
                    context.get("product_model"),
                    context.get("goods_classify_id"),
                    context.get("android_version"),
                    context.get("server_code") or context.get("server_region"),
                )
                if any(key):
                    successful.add(key)

        attempted_count = len(attempted)
        seen_count = len(seen)
        successful_count = len(successful)
        priced_rows = sum(1 for record in records if self._is_valid_price_record(record))
        coverage_ratio = (seen_count / attempted_count) if attempted_count else None
        if priced_rows <= 0 or seen_count <= 0:
            collection_status = "failed"
        elif coverage_ratio is not None and coverage_ratio < 0.8:
            collection_status = "warning"
        else:
            collection_status = "ok"

        failed_combinations = [
            entry for entry in diagnostics
            if entry.get("stage") in {"android", "server", "price"}
            and entry.get("result") not in {"price_api_seen"}
        ]
        return {
            "platform": self.platform,
            "reason": reason,
            "collection_status": collection_status,
            "signed_getGoods_seen": self._has_signed_getgoods(),
            "price_api_seen_during_interactions": bool(getattr(self, "_redfinger_price_api_seen", False)),
            "discovered_plan_labels": self._configured_plan_labels(),
            "attempted_combinations": attempted_count,
            "price_api_seen_combinations": seen_count,
            "successful_price_combinations": successful_count,
            "priced_product_rows": priced_rows,
            "price_api_coverage_ratio": coverage_ratio,
            "artifact_write_failures": len(getattr(self, "redfinger_artifact_write_failures", []) or []),
            "artifact_write_failure_details": list(getattr(self, "redfinger_artifact_write_failures", []) or []),
            "interaction_attempts": diagnostics,
            "failed_combinations": failed_combinations,
            "candidate_summary": candidate_summary,
        }

    def _classify_specs_by_key(self) -> dict[tuple[str | None, str | None], list[dict]]:
        specs_by_key: dict[tuple[str | None, str | None], list[dict]] = {}
        base_specs_by_key: dict[tuple[str | None, str | None], dict] = {}
        for item in self.api_candidates:
            url = (item.get("url") or "").lower()
            payload = item.get("response_json") or {}
            if "getnewversionclassify" not in url:
                continue
            groups = payload.get("resultInfo") if isinstance(payload, dict) else None
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, dict):
                    continue
                classify_value = self._format_scalar(group.get("classifyValue"))
                classify_name = self._format_scalar(group.get("classifyName"))
                base = {"product_model": classify_name}
                specs_by_key[(classify_value, None)] = [base]
                for attr in group.get("attributes") or []:
                    if not isinstance(attr, dict):
                        continue
                    specs = {**base, **self._specs_from_photo_urls(attr.get("photoUrls") or [])}
                    goods_classify_id = self._format_scalar(attr.get("goodsClassifyId"))
                    base_specs_by_key[(classify_value, goods_classify_id)] = specs
                    specs_by_key[(classify_value, goods_classify_id)] = [specs]

        for item in self.api_candidates:
            url = item.get("url") or ""
            if OPTIONS_API_TOKEN not in url.lower():
                continue
            classify_value = self._query_params(url).get("classifyValue")
            payload = item.get("response_json") or {}
            info = payload.get("resultInfo") if isinstance(payload, dict) else None
            for attr in (info or {}).get("attributes") or []:
                if not isinstance(attr, dict):
                    continue
                goods_classify_id = self._format_scalar(attr.get("goodsClassifyId"))
                key = (classify_value, goods_classify_id)
                base = base_specs_by_key.get(key) or (specs_by_key.get((classify_value, None)) or [{}])[0]
                specs = dict(base)
                rom = attr.get("romVersion") if isinstance(attr.get("romVersion"), dict) else {}
                if rom.get("name"):
                    specs["android_version"] = self._format_scalar(rom.get("name"))
                idc = attr.get("idcCode") if isinstance(attr.get("idcCode"), dict) else {}
                if idc.get("name"):
                    specs["server_region"] = self._format_scalar(idc.get("name"))
                if idc.get("attributeValue"):
                    specs["server_code"] = self._format_scalar(idc.get("attributeValue"))
                self._append_unique_specs(specs_by_key, key, specs)
        return specs_by_key

    def _append_unique_specs(
        self,
        specs_by_key: dict[tuple[str | None, str | None], list[dict]],
        key: tuple[str | None, str | None],
        specs: dict,
    ) -> None:
        items = specs_by_key.setdefault(key, [])
        if specs.get("server_region"):
            items[:] = [item for item in items if item.get("server_region")]
        marker = (
            specs.get("product_model"),
            specs.get("android_version"),
            specs.get("server_region"),
            specs.get("cpu"),
            specs.get("ram"),
            specs.get("storage"),
        )
        for item in items:
            if (
                item.get("product_model"),
                item.get("android_version"),
                item.get("server_region"),
                item.get("cpu"),
                item.get("ram"),
                item.get("storage"),
            ) == marker:
                return
        items.append(specs)

    def _specs_from_photo_urls(self, urls: list[str]) -> dict:
        joined = " ".join(str(url) for url in urls)
        specs = {}
        android = re.search(r"Android(\d+(?:\.\d+)?)", joined, re.I)
        cpu = re.search(r"(\d+)CPU", joined, re.I)
        ram = re.search(r"(\d+(?:\.\d+)?)GRAM", joined, re.I)
        storage = re.search(r"(\d+(?:\.\d+)?)GROM", joined, re.I)
        if android:
            specs["android_version"] = android.group(1)
        if cpu:
            specs["cpu"] = f"{cpu.group(1)} cores"
        if ram:
            specs["ram"] = f"{ram.group(1)}GB"
        if storage:
            specs["storage"] = f"{storage.group(1)}GB"
        return specs

    def _store_manual_api_candidate(self, url: str, status: int, payload: Any, response_headers: dict) -> None:
        filename = f"{len(self.api_candidates)+1:04d}_{safe_filename(url)}.json"
        path = self.api_dir / filename
        item = {
            "platform": self.platform,
            "url": url,
            "method": "GET",
            "status": status,
            "resource_type": "fallback_request",
            "request_headers": {},
            "response_headers": response_headers,
            "request_payload": None,
            "response_json": redact_payload(payload),
            "response_text": None,
            "api_response_path": str(path),
        }
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        self.api_candidates.append(item)

    def _iter_goods_nodes(self, value: Any) -> List[dict]:
        found: List[dict] = []
        if isinstance(value, dict):
            lowered_keys = {str(key).lower() for key in value.keys()}
            if lowered_keys & {"goodsid", "goodsname", "goodsprice", "commodityid", "commodityname"}:
                found.append(value)
            for item in value.values():
                found.extend(self._iter_goods_nodes(item))
        elif isinstance(value, list):
            for item in value:
                found.extend(self._iter_goods_nodes(item))
        return found

    @staticmethod
    def _duration_from_goods(node: dict) -> tuple[str | None, str | None]:
        def first(value: Any, keys: set[str]) -> Any:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key.lower() in keys and item not in [None, ""]:
                        return item
                for item in value.values():
                    found = first(item, keys)
                    if found not in [None, ""]:
                        return found
            elif isinstance(value, list):
                for item in value:
                    found = first(item, keys)
                    if found not in [None, ""]:
                        return found
            return None

        days = first(node, {"onlinetime", "days"})
        if days not in [None, ""]:
            return f"{days} day", "day"
        hours = first(node, {"onlinetimehours", "hours"})
        if hours in [None, ""]:
            return None, None
        try:
            hour_value = int(hours)
            if hour_value % 24 == 0:
                return f"{hour_value // 24} day", "day"
        except Exception:
            pass
        return f"{hours} hour", "hour"

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

    @staticmethod
    def _cents_to_price(value: Any) -> str | None:
        if value in [None, ""]:
            return None
        try:
            return f"{float(value) / 100:.2f}".rstrip("0").rstrip(".")
        except Exception:
            return str(value)

    @staticmethod
    def _format_scalar(value: Any) -> str | None:
        if value in [None, ""]:
            return None
        return str(value)

    def _currency(self, node: dict) -> str | None:
        display = self._first_by_key(node, {"currencydisplaycode"})
        code = self._first_by_key(node, {"currencycode", "currency"})
        if display in {"$", "US$"} or code == "USD":
            return "US$"
        return self._format_scalar(display or code)

    def _promotion_text(self, node: dict) -> str | None:
        parts = []
        for key in ["angleSign", "summary", "discountSign", "dailyUnitPrice"]:
            value = node.get(key)
            if value not in [None, ""]:
                parts.append(str(value))
        return "; ".join(parts) or None

    @staticmethod
    def _query_params(url: str) -> dict[str, str]:
        values = parse_qs(urlparse(url).query)
        return {key: items[0] for key, items in values.items() if items}

    def _has_signed_getgoods(self) -> bool:
        return any(PRICE_API_TOKEN in (item.get("url") or "").lower() for item in self.api_candidates)
