import json
import re
from typing import Any, List

from playwright.sync_api import Page

from cloud_phone_monitor.schemas import ProductRecord
from cloud_phone_monitor.scrapers.base import BaseScraper
from cloud_phone_monitor.utils.normalize import compact_text, now_pair, redact_payload, safe_filename


class UGPhoneScraper(BaseScraper):
    platform = "UGPhone"
    meal_list_url = "https://www.ugphone.com/api/apiv1/info/mealList"

    def _collect_interactive_states(self, page: Page, url: str) -> None:
        configs = self._configs_from_api_candidates()
        if not configs:
            self.logger.info("[%s] configList2 not found before meal collection", self.platform)
            return

        results = page.evaluate(
            """
            async ([url, configs]) => {
              const out = [];
              const fingerprint = localStorage.getItem('ugBrowserId') || '';
              const headers = {
                'content-type': 'application/json;charset=UTF-8',
                'lang': localStorage.getItem('ugPhoneLang') || 'cn',
                'terminal': 'web',
                'access-token': localStorage.getItem('UGPHONE-Token') || '',
                'login-id': localStorage.getItem('UGPHONE-ID') || '',
                'web-fingerprint': fingerprint ? btoa(fingerprint) : '',
                'update-date': '20250218'
              };
              for (const cfg of configs) {
                try {
                  const response = await fetch(url, {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({config_id: cfg.config_id})
                  });
                  let json = null;
                  let text = null;
                  try { json = await response.json(); } catch (error) { text = await response.text(); }
                  out.push({status: response.status, config: cfg, response_json: json, response_text: text});
                } catch (error) {
                  out.push({status: 0, config: cfg, response_json: null, response_text: String(error)});
                }
              }
              return out;
            }
            """,
            [self.meal_list_url, configs],
        )
        for result in results or []:
            self._store_manual_api_candidate(
                self.meal_list_url,
                int(result.get("status") or 0),
                result.get("response_json"),
                result.get("response_text"),
                {"config_id": (result.get("config") or {}).get("config_id")},
                {"interactive_context": result.get("config") or {}},
            )

    def _records_from_api(self, source_url: str, screenshot_path: str, html_path: str) -> List[ProductRecord]:
        crawl_utc, crawl_local = now_pair(self.config.timezone)
        records: List[ProductRecord] = []

        for item in self.api_candidates:
            if "mealList" not in (item.get("url") or ""):
                continue
            context = item.get("extra", {}).get("interactive_context", {})
            if not context.get("config_id"):
                continue
            payload = item.get("response_json") or {}
            data = payload.get("data") if isinstance(payload, dict) else None
            meal_groups = (data or {}).get("list") if isinstance(data, dict) else None
            if not isinstance(meal_groups, dict):
                continue
            for group_name, networks in meal_groups.items():
                if not isinstance(networks, list):
                    continue
                for network in networks:
                    if not isinstance(network, dict):
                        continue
                    network_config = network.get("network_config") or {}
                    for buy_time in network.get("buy_time") or []:
                        if not isinstance(buy_time, dict) or not buy_time.get("show", 1):
                            continue
                        if buy_time.get("pay_channel") == "free":
                            continue
                        duration, billing_period = self._duration_from_buy_time(buy_time)
                        if not duration:
                            continue
                        promotion_text = self._promotion_text(buy_time)
                        raw = {"config": context, "network": network, "buy_time": buy_time, "group": group_name}
                        records.append(
                            ProductRecord(
                                platform=self.platform,
                                source_url=source_url,
                                crawl_time_utc=crawl_utc,
                                crawl_time_local=crawl_local,
                                region_selected=network.get("network_name"),
                                server_region=network.get("network_name"),
                                currency="$",
                                product_category="cloud_phone",
                                product_name="Cloud Phone",
                                product_model=self._clean_plan_name(context.get("plan")),
                                device_model=self._clean_plan_name(context.get("plan")),
                                android_version=self._android_version(
                                    context.get("android_version")
                                    or network_config.get("android_version")
                                    or (context.get("config") or {}).get("android_version")
                                ),
                                cpu=self._cpu(context.get("cpu") or network_config.get("cpu") or (context.get("config") or {}).get("cpu")),
                                ram=self._gb(context.get("ram") or network_config.get("ram") or (context.get("config") or {}).get("ram"), "RAM"),
                                storage=self._gb(context.get("rom") or network_config.get("rom") or (context.get("config") or {}).get("rom"), "ROM"),
                                price=self._price(buy_time.get("price_str") or buy_time.get("price")),
                                original_price=self._price(buy_time.get("ori_price_str") or buy_time.get("ori_price")),
                                billing_period=billing_period,
                                duration=duration,
                                stock_status="sold_out" if network.get("appointment_id") else "available",
                                promotion_text=promotion_text,
                                raw_text=compact_text(json.dumps(raw, ensure_ascii=False, default=str), 4000),
                                extraction_method="api",
                                confidence="high",
                                screenshot_path=screenshot_path,
                                html_path=html_path,
                                api_response_path=item.get("api_response_path"),
                                notes=f"mealList_api; config_id={context.get('config_id')}; group={group_name}",
                            )
                        )
        if records:
            return self._dedupe_records(records)
        return super()._records_from_api(source_url, screenshot_path, html_path)

    def _records_from_dom(self, *args, **kwargs) -> List[ProductRecord]:
        return []

    def _configs_from_api_candidates(self) -> list[dict]:
        configs = []
        for item in self.api_candidates:
            if "configList2" not in (item.get("url") or ""):
                continue
            payload = item.get("response_json") or {}
            data = payload.get("data") if isinstance(payload, dict) else None
            for plan in (data or {}).get("list") or []:
                if not isinstance(plan, dict):
                    continue
                plan_name = self._clean_plan_name(plan.get("config_name"))
                for android in plan.get("android_version") or []:
                    if not isinstance(android, dict):
                        continue
                    cfg = android.get("config") or {}
                    config_id = android.get("config_id")
                    if not config_id:
                        continue
                    configs.append(
                        {
                            "plan": plan_name,
                            "config_id": config_id,
                            "android_version": self._android_version(cfg.get("android_version") or android.get("name")),
                            "cpu": cfg.get("cpu"),
                            "ram": cfg.get("ram"),
                            "rom": cfg.get("rom"),
                            "config": cfg,
                        }
                    )
        seen = set()
        out = []
        for cfg in configs:
            if cfg["config_id"] in seen:
                continue
            seen.add(cfg["config_id"])
            out.append(cfg)
        return out

    def _store_manual_api_candidate(
        self,
        url: str,
        status: int,
        payload: Any,
        response_text: str | None,
        request_payload: dict | None,
        extra: dict | None = None,
    ) -> None:
        filename = f"{len(self.api_candidates)+1:04d}_{safe_filename(url)}.json"
        path = self.api_dir / filename
        item = {
            "platform": self.platform,
            "url": url,
            "method": "POST",
            "status": status,
            "resource_type": "fetch",
            "request_headers": {},
            "response_headers": {},
            "request_payload": redact_payload(request_payload),
            "response_json": redact_payload(payload) if payload is not None else None,
            "response_text": response_text if payload is None else None,
            "api_response_path": str(path),
            "extra": extra or {},
        }
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        self.api_candidates.append(item)

    def _duration_from_buy_time(self, buy_time: dict) -> tuple[str | None, str | None]:
        unit = str(buy_time.get("unit") or "").lower()
        period_time = buy_time.get("period_time")
        if period_time in [None, ""]:
            text = str(buy_time.get("time_str") or "")
            match = re.search(r"(\d+)\s*(天|日|小时|hour|day|month|year)", text, re.I)
            if not match:
                return None, None
            period_time = match.group(1)
            unit = match.group(2).lower()
        if unit in {"天", "日", "day", "days"}:
            return f"{period_time} day", "day"
        if unit in {"小时", "hour", "hours"}:
            return f"{period_time} hour", "hour"
        if unit in {"month", "months"}:
            return f"{period_time} month", "month"
        if unit in {"year", "years"}:
            return f"{period_time} year", "year"
        return f"{period_time} {unit}", unit or None

    def _promotion_text(self, buy_time: dict) -> str | None:
        values = []
        for key in ["discount_str", "points_deduction_max_str", "sub_desc", "show_str", "price_type"]:
            value = buy_time.get(key)
            if value not in [None, ""]:
                values.append(str(value))
        return "; ".join(dict.fromkeys(values)) or None

    def _clean_plan_name(self, value: Any) -> str | None:
        text = str(value or "").strip()
        text = text.replace("🔥", "").strip()
        return text or None

    def _android_version(self, value: Any) -> str | None:
        match = re.search(r"(\d+(?:\.\d+)?)", str(value or ""))
        return match.group(1) if match else None

    def _cpu(self, value: Any) -> str | None:
        match = re.search(r"(\d+(?:\.\d+)?)", str(value or ""))
        if not match:
            return None
        number = float(match.group(1))
        return f"{number:g} cores"

    def _gb(self, value: Any, suffix: str) -> str | None:
        match = re.search(r"(\d+(?:\.\d+)?)", str(value or ""))
        if not match:
            return None
        number = float(match.group(1))
        return f"{number:g}GB"

    def _price(self, value: Any) -> str | None:
        match = re.search(r"(\d+(?:\.\d+)?)", str(value or "").replace(",", ""))
        return match.group(1) if match else None
