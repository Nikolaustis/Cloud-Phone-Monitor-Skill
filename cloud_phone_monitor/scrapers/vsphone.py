import json
import re
from typing import Any, List

from playwright.sync_api import Page

from cloud_phone_monitor.schemas import ProductRecord
from cloud_phone_monitor.scrapers.base import BaseScraper
from cloud_phone_monitor.utils.normalize import compact_text, now_pair, parse_duration


class VSPhoneScraper(BaseScraper):
    platform = "VSPhone"
    device_model_labels = [
        (["High-end Real Machine", "High-end Real Device", "高端真机"], "高端真机"),
        (["Game AFK Dedicated Phone", "Game AFK Dedicated Machine", "Game AFK", "游戏挂机专用机"], "游戏挂机专用机"),
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

    non_subscription_duration_days = {1, 3, 7, 30, 90, 365}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selection_contexts: list[dict[str, Any]] = []
        self.context_artifacts: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
        self.purchase_mode_artifacts: dict[tuple[Any, Any, Any, str], dict[str, Any]] = {}
        self.purchase_mode_evidence: dict[tuple[Any, Any, Any, str], dict[str, Any]] = {}
        self.collection_summary: dict[str, Any] = {
            "subscription_control_found": False,
            "quantity_one_targets": 0,
            "quantity_one_successes": 0,
            "purchase_mode_context_targets": 0,
            "purchase_mode_context_successes": 0,
            "subscription_snapshot_count": 0,
            "non_subscription_snapshot_count": 0,
            "auto_renew_confirmation_targets": 0,
            "auto_renew_confirmation_successes": 0,
            "purchase_mode_failures": [],
            "returned_record_count": 0,
            "subscription_record_count": 0,
            "non_subscription_record_count": 0,
            "non_subscription_duration_days": sorted(self.non_subscription_duration_days),
            "pricing_source": "visible duration card; other plans inherit the API field verified against the selected live card",
            "subscription_api_price_field_counts": {"currentPrice": 0, "goodPrice": 0, "unresolved": 0},
            "subscription_api_price_field_evidence": [],
        }

    def scrape(self) -> List[ProductRecord]:
        records = super().scrape()
        self.collection_summary["returned_record_count"] = len(records)
        self.collection_summary["subscription_record_count"] = sum(
            1 for record in records if record.purchase_mode == "subscription"
        )
        self.collection_summary["non_subscription_record_count"] = sum(
            1 for record in records if record.purchase_mode == "non_subscription"
        )
        self._write_collection_summary()
        return records

    def _collect_interactive_states(self, page: Page, url: str) -> None:
        self.selection_contexts = []
        self.context_artifacts = {}
        self.purchase_mode_artifacts = {}
        self.purchase_mode_evidence = {}
        self._ensure_quantity_one(page)

        for visible_labels, normalized_label in self.device_model_labels:
            before_device = len(self.api_candidates)
            clicked_device = self._click_any_label(page, visible_labels)
            if not clicked_device and normalized_label == "游戏挂机专用机":
                self.logger.info("[%s] device tab not found: %s", self.platform, normalized_label)
                continue
            page.wait_for_timeout(1200)
            self._close_obstructive_popups(page)
            if normalized_label == "游戏挂机专用机":
                server_regions = self._visible_server_regions(page) or [None]
                contexts = []
                for server_region in server_regions:
                    if server_region:
                        self._click_server_region(page, server_region)
                        page.wait_for_timeout(700)
                        self._close_obstructive_popups(page)
                    context = {
                        "device_model": normalized_label,
                        "android_version": None,
                        "server_region": server_region,
                    }
                    contexts.append(context)
                    self._capture_purchase_mode_states(page, url, context)
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
                page.wait_for_timeout(1400)
                self._close_obstructive_popups(page)
                server_regions = self._visible_server_regions(page) or [None]
                contexts = []
                for server_region in server_regions:
                    if server_region:
                        self._click_server_region(page, server_region)
                        page.wait_for_timeout(700)
                        self._close_obstructive_popups(page)
                    context = {
                        "device_model": normalized_label,
                        "android_version": version,
                        "server_region": server_region,
                    }
                    contexts.append(context)
                    self._capture_purchase_mode_states(page, url, context)
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
            subscription_api_price_field, subscription_field_evidence = self._infer_subscription_api_price_field(
                data.get("configs") or [],
                context,
            )
            field_counts = self.collection_summary.setdefault(
                "subscription_api_price_field_counts",
                {"currentPrice": 0, "goodPrice": 0, "unresolved": 0},
            )
            field_counts[subscription_api_price_field or "unresolved"] = int(
                field_counts.get(subscription_api_price_field or "unresolved") or 0
            ) + 1
            evidence_rows = list(self.collection_summary.get("subscription_api_price_field_evidence") or [])
            evidence_rows.append({
                "context": context,
                "selected_field": subscription_api_price_field,
                **subscription_field_evidence,
            })
            self.collection_summary["subscription_api_price_field_evidence"] = evidence_rows[-200:]

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
                product_model = self._product_model(config, device_model)

                for android_version in android_versions:
                    server_regions = self._server_regions_for(
                        device_model,
                        android_version,
                        context.get("server_region") or specs.get("region"),
                    )
                    for good_time in times or [None]:
                        if good_time is not None and not isinstance(good_time, dict):
                            continue
                        show_content = (good_time or {}).get("showContent")
                        duration, billing_period = parse_duration(show_content or "")
                        duration_days = self._duration_days(duration or show_content)
                        api_current_price = (good_time or {}).get("currentPrice")
                        api_good_price = (good_time or {}).get("goodPrice")
                        if subscription_api_price_field == "goodPrice":
                            subscription_price = api_good_price
                            subscription_fallback_price = api_current_price
                        else:
                            subscription_price = api_current_price
                            subscription_fallback_price = api_good_price
                        if subscription_price in [None, ""]:
                            subscription_price = subscription_fallback_price
                        one_time_price = (good_time or {}).get("oldGoodPrice")
                        recommend = (good_time or {}).get("recommendContent") or None

                        for server_region in server_regions:
                            for purchase_mode in ("subscription", "non_subscription"):
                                if purchase_mode == "non_subscription":
                                    if duration_days not in self.non_subscription_duration_days:
                                        continue
                                    if one_time_price in [None, ""]:
                                        continue
                                    if not self._purchase_mode_verified(
                                        device_model,
                                        android_version,
                                        server_region,
                                        purchase_mode,
                                    ):
                                        continue
                                    raw_price = one_time_price
                                    raw_original_price = one_time_price
                                else:
                                    raw_price = subscription_price
                                    raw_original_price = one_time_price

                                dom_card = self._dom_card_evidence(
                                    device_model=device_model,
                                    android_version=android_version,
                                    server_region=server_region,
                                    purchase_mode=purchase_mode,
                                    product_model=product_model,
                                    duration=duration or show_content,
                                )
                                if dom_card and dom_card.get("price") not in [None, ""]:
                                    price = dom_card.get("price")
                                    original_price = dom_card.get("original_price")
                                    price_source_note = "visible_duration_card_price"
                                else:
                                    price = self._cents_to_price(raw_price)
                                    original_price = self._cents_to_price(raw_original_price)
                                    price_source_note = (
                                        f"api_{subscription_api_price_field or 'currentPrice'}_verified_by_selected_subscription_card"
                                        if purchase_mode == "subscription"
                                        else "api_oldGoodPrice_matching_auto_renew_off_card"
                                    )

                                raw = {
                                    "config": config,
                                    "goodTime": good_time,
                                    "interactive_context": context,
                                    "purchase_mode": purchase_mode,
                                    "dom_card_evidence": dom_card,
                                    "subscription_api_price_field": subscription_api_price_field,
                                    "api_price_fields": {
                                        "currentPrice": api_current_price,
                                        "goodPrice": api_good_price,
                                        "oldGoodPrice": one_time_price,
                                    },
                                }
                                notes = (
                                    f"api_config_good_time; source_config_name={config.get('configName')}; "
                                    f"purchase_mode={purchase_mode}; quantity=1; {price_source_note}; "
                                    "footer_order_total_excluded"
                                )
                                if purchase_mode == "subscription":
                                    notes += f"; subscription_api_price_field={subscription_api_price_field or 'unresolved'}"
                                    if (
                                        api_current_price not in [None, ""]
                                        and api_good_price not in [None, ""]
                                        and str(api_current_price) != str(api_good_price)
                                    ):
                                        notes += (
                                            f"; api_currentPrice={api_current_price}"
                                            f"; api_goodPrice={api_good_price}"
                                        )
                                if purchase_mode == "non_subscription":
                                    notes += "; auto_renew_switch_off_verified"
                                if not any(server_regions):
                                    notes += "; server_not_exposed_by_api"
                                if self.blocked_reason:
                                    notes += f"; blocked_reason={self.blocked_reason}"
                                artifact = self._context_artifact(
                                    device_model,
                                    android_version,
                                    server_region,
                                    purchase_mode=purchase_mode,
                                )
                                records.append(
                                    ProductRecord(
                                        platform=self.platform,
                                        source_url=source_url,
                                        crawl_time_utc=crawl_utc,
                                        crawl_time_local=crawl_local,
                                        server_region=server_region,
                                        currency="US$" if price not in [None, ""] else None,
                                        product_category="cloud_phone",
                                        product_name="Cloud Phone",
                                        product_model=product_model,
                                        device_model=device_model,
                                        android_version=android_version,
                                        cpu=specs.get("cpu"),
                                        ram=specs.get("ram"),
                                        storage=specs.get("storage"),
                                        price=price,
                                        original_price=original_price,
                                        billing_period=billing_period,
                                        duration=duration or show_content,
                                        purchase_mode=purchase_mode,
                                        stock_status="sold_out" if config.get("sellOutFlag") else "available",
                                        promotion_text=recommend,
                                        raw_text=compact_text(json.dumps(raw, ensure_ascii=False, default=str), 4000),
                                        extraction_method="api+verified_dom_purchase_mode",
                                        confidence="high" if price not in [None, ""] else "medium",
                                        screenshot_path=(artifact or {}).get("screenshot_path") or screenshot_path,
                                        html_path=(artifact or {}).get("html_path") or html_path,
                                        api_response_path=item.get("api_response_path"),
                                        notes=notes,
                                    )
                                )

        return self._dedupe_records(records) if records else super()._records_from_api(source_url, screenshot_path, html_path)

    def _subscription_control_state(self, page: Page) -> dict[str, Any]:
        try:
            state = page.evaluate(
                r"""
                () => {
                  const visible = (node) => {
                    if (!node) return false;
                    const style = window.getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                  };
                  const inputs = Array.from(document.querySelectorAll(
                    '.auto-renew-item input.el-switch__input[role="switch"], input.el-switch__input[role="switch"]'
                  ));
                  const input = inputs.find((node) => visible(node.closest('.el-switch') || node));
                  if (!input) return { found: false, checked: null, text: '' };
                  const wrapper = input.closest('.auto-renew-item') || input.closest('.el-form-item') || input.parentElement;
                  const checked = input.getAttribute('aria-checked') === 'true' || Boolean(input.checked);
                  return {
                    found: true,
                    checked,
                    text: String(wrapper?.innerText || wrapper?.textContent || '').replace(/\s+/g, ' ').trim(),
                  };
                }
                """
            )
            return state if isinstance(state, dict) else {"found": False, "checked": None, "text": ""}
        except Exception as exc:
            self.logger.debug("[%s] auto-renew state probe failed: %s", self.platform, exc)
            return {"found": False, "checked": None, "text": ""}

    def _wait_for_subscription_control(self, page: Page, timeout_ms: int = 8_000) -> dict[str, Any]:
        waited = 0
        while waited < timeout_ms:
            state = self._subscription_control_state(page)
            if state.get("found"):
                self.collection_summary["subscription_control_found"] = True
                return state
            try:
                page.locator('.auto-renew-item').scroll_into_view_if_needed(timeout=800)
            except Exception:
                pass
            page.wait_for_timeout(250)
            waited += 250
        return {"found": False, "checked": None, "text": ""}

    def _card_signature(self, page: Page) -> str:
        cards = self._visible_price_cards(page)
        return json.dumps(cards, ensure_ascii=False, sort_keys=True, default=str)

    def _resolve_auto_renew_confirmation_dialog(
        self,
        page: Page,
        *,
        desired_enabled: bool,
        timeout_ms: int = 4_000,
    ) -> bool:
        """Resolve VSPhone's confirmation message box after toggling auto-renew.

        When auto-renew is turned off, VSPhone opens a modal whose left button is
        "Keep closed" (localized equivalents may vary).  Merely clicking the
        switch leaves the model enabled until that button is accepted.
        """
        waited = 0
        counted = False
        while waited < timeout_ms:
            try:
                result = page.evaluate(
                    r"""
                    ({ desiredEnabled }) => {
                      const visible = (node) => {
                        if (!node) return false;
                        const style = window.getComputedStyle(node);
                        const rect = node.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                      };
                      const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
                      const dialogs = Array.from(document.querySelectorAll(
                        '.el-overlay.is-message-box, .el-message-box, [role="dialog"]'
                      )).filter(visible);
                      const dialog = dialogs.find((node) => {
                        const text = clean(node.innerText || node.textContent).toLowerCase();
                        return /auto[- ]?renew|自动续费|自動續費|confirm close|关闭|關閉/.test(text);
                      });
                      if (!dialog) return { found: false, clicked: false, buttonText: '' };
                      const buttons = Array.from(dialog.querySelectorAll('button')).filter(visible);
                      if (!buttons.length) return { found: true, clicked: false, buttonText: '' };
                      const textOf = (button) => clean(button.innerText || button.textContent);
                      const lower = (button) => textOf(button).toLowerCase();
                      let target = null;
                      if (desiredEnabled) {
                        target = buttons.find((button) =>
                          /continue enabling|enable|turn on|开启|開啟|继续开启|繼續開啟/.test(lower(button))
                        );
                        target = target || buttons.find((button) => button.classList.contains('el-button--primary'));
                        target = target || buttons[buttons.length - 1];
                      } else {
                        target = buttons.find((button) =>
                          /keep closed|confirm close|stay off|turn off|disable|保持关闭|保持關閉|确认关闭|確認關閉|继续关闭|繼續關閉|仍要关闭|仍要關閉/.test(lower(button))
                        );
                        target = target || buttons.find((button) => !button.classList.contains('el-button--primary'));
                        target = target || buttons[0];
                      }
                      if (!target) return { found: true, clicked: false, buttonText: '' };
                      const buttonText = textOf(target);
                      target.click();
                      return { found: true, clicked: true, buttonText };
                    }
                    """,
                    {"desiredEnabled": bool(desired_enabled)},
                )
            except Exception as exc:
                self.logger.debug("[%s] auto-renew confirmation probe failed: %s", self.platform, exc)
                result = {"found": False, "clicked": False, "buttonText": ""}

            if isinstance(result, dict) and result.get("found"):
                if not counted:
                    self.collection_summary["auto_renew_confirmation_targets"] = int(
                        self.collection_summary.get("auto_renew_confirmation_targets") or 0
                    ) + 1
                    counted = True
                if result.get("clicked"):
                    page.wait_for_timeout(300)
                state = self._subscription_control_state(page)
                if state.get("found") and bool(state.get("checked")) == bool(desired_enabled):
                    self.collection_summary["auto_renew_confirmation_successes"] = int(
                        self.collection_summary.get("auto_renew_confirmation_successes") or 0
                    ) + 1
                    return True
            else:
                # No message box is also a valid outcome when the state already changed.
                state = self._subscription_control_state(page)
                if state.get("found") and bool(state.get("checked")) == bool(desired_enabled):
                    return True
            page.wait_for_timeout(200)
            waited += 200
        return False

    def _click_visible_subscription_switch(self, page: Page) -> bool:
        """Click the same visible switch input used by the state probe."""
        try:
            return bool(
                page.evaluate(
                    r"""
                    () => {
                      const visible = (node) => {
                        if (!node) return false;
                        const style = window.getComputedStyle(node);
                        const rect = node.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                      };
                      const inputs = Array.from(document.querySelectorAll(
                        '.auto-renew-item input.el-switch__input[role="switch"], input.el-switch__input[role="switch"]'
                      ));
                      const input = inputs.find((node) => visible(node.closest('.el-switch') || node));
                      if (!input || input.getAttribute('aria-disabled') === 'true' || input.disabled) return false;
                      input.click();
                      return true;
                    }
                    """
                )
            )
        except Exception as exc:
            self.logger.debug("[%s] direct auto-renew input click failed: %s", self.platform, exc)
            return False

    def _set_subscription_mode(self, page: Page, enabled: bool, timeout_ms: int = 8_000) -> bool:
        # Resolve a confirmation dialog left over by an interrupted previous context.
        self._resolve_auto_renew_confirmation_dialog(
            page,
            desired_enabled=enabled,
            timeout_ms=min(1_000, timeout_ms),
        )
        state = self._wait_for_subscription_control(page, timeout_ms=timeout_ms)
        if not state.get("found"):
            return False
        if bool(state.get("checked")) == bool(enabled):
            return True

        before_signature = self._card_signature(page)
        clicked = self._click_visible_subscription_switch(page)
        if not clicked:
            try:
                switch = page.locator('.auto-renew-item .el-switch').first
                switch.scroll_into_view_if_needed(timeout=1_500)
                switch.click(force=True, timeout=2_500)
                clicked = True
            except Exception:
                clicked = False
        if not clicked:
            return False

        # Turning auto-renew off requires accepting VSPhone's "Keep closed"
        # confirmation dialog.  Without this step aria-checked remains true.
        if not enabled:
            self._resolve_auto_renew_confirmation_dialog(
                page,
                desired_enabled=False,
                timeout_ms=min(5_000, timeout_ms),
            )

        waited = 0
        while waited < timeout_ms:
            page.wait_for_timeout(250)
            waited += 250
            current = self._subscription_control_state(page)
            if current.get("found") and bool(current.get("checked")) == bool(enabled):
                after_signature = self._card_signature(page)
                if after_signature and (after_signature != before_signature or waited >= 750):
                    return True
            # A delayed message box can appear after the first polling cycle.
            if not enabled and waited <= 5_000:
                self._resolve_auto_renew_confirmation_dialog(
                    page,
                    desired_enabled=False,
                    timeout_ms=400,
                )
        return False

    def _ensure_quantity_one(self, page: Page) -> bool:
        self.collection_summary["quantity_one_targets"] = int(
            self.collection_summary.get("quantity_one_targets") or 0
        ) + 1
        selector = '.buy-footer .el-input-number input, .buy-nums .el-input-number input'
        try:
            locator = page.locator(selector).first
            if not locator.is_visible(timeout=1200):
                return False
            value = str(locator.input_value(timeout=1000)).strip()
            if value != "1":
                locator.fill("1", timeout=1800)
                locator.press("Enter", timeout=1200)
                locator.press("Tab", timeout=1200)
                page.wait_for_timeout(350)
            value = str(locator.input_value(timeout=1000)).strip()
            if value != "1":
                decrease = page.locator('.buy-footer .el-input-number__decrease, .buy-nums .el-input-number__decrease').first
                for _ in range(20):
                    value = str(locator.input_value(timeout=800)).strip()
                    if value == "1":
                        break
                    if not decrease.is_visible(timeout=500):
                        break
                    decrease.click(force=True, timeout=1000)
                    page.wait_for_timeout(120)
            success = str(locator.input_value(timeout=1000)).strip() == "1"
            if success:
                self.collection_summary["quantity_one_successes"] = int(
                    self.collection_summary.get("quantity_one_successes") or 0
                ) + 1
            return success
        except Exception as exc:
            self.logger.debug("[%s] quantity=1 verification failed: %s", self.platform, exc)
            return False

    def _visible_price_cards(self, page: Page) -> list[dict[str, Any]]:
        try:
            cards = page.evaluate(
                r"""
                () => {
                  const visible = (node) => {
                    if (!node) return false;
                    const style = window.getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                  };
                  const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
                  const money = (value) => {
                    const match = clean(value).replace(/,/g, '').match(/(?:US\$|USD\s*)?(-?\d+(?:\.\d+)?)/i);
                    return match ? match[1] : null;
                  };
                  const selectedModel = clean(
                    document.querySelector('.config-list .el-radio.is-checked .label')?.textContent
                    || document.querySelector('.config-list .el-radio__input.is-checked')?.closest('.el-radio')?.textContent
                  );
                  return Array.from(document.querySelectorAll('.goods-list .combo-item'))
                    .filter(visible)
                    .map((card) => {
                      const durationNode = card.querySelector('.title > label:first-child, .title label, .title');
                      const priceNodes = Array.from(card.querySelectorAll('.total-price .price .money, .price-info .price .money'));
                      const currentNode = priceNodes.find((node) => !node.classList.contains('old-price'));
                      const oldNode = priceNodes.find((node) => node.classList.contains('old-price'));
                      return {
                        product_model: selectedModel || null,
                        duration: clean(durationNode?.textContent),
                        price: money(currentNode?.textContent),
                        original_price: money(oldNode?.textContent),
                        selected: card.classList.contains('active') || Boolean(card.querySelector('.is-checked')),
                        raw_text: clean(card.textContent),
                      };
                    })
                    .filter((item) => item.duration && item.price !== null);
                }
                """
            )
            return cards if isinstance(cards, list) else []
        except Exception as exc:
            self.logger.debug("[%s] visible price card probe failed: %s", self.platform, exc)
            return []

    def _wait_for_price_cards(self, page: Page, timeout_ms: int = 6_000) -> list[dict[str, Any]]:
        waited = 0
        while waited < timeout_ms:
            cards = self._visible_price_cards(page)
            if cards:
                return cards
            page.wait_for_timeout(250)
            waited += 250
        return []

    def _capture_purchase_mode_states(self, page: Page, url: str, context: dict[str, Any]) -> None:
        self.collection_summary["purchase_mode_context_targets"] = int(
            self.collection_summary.get("purchase_mode_context_targets") or 0
        ) + 1
        captured: set[str] = set()
        failures: list[dict[str, Any]] = []
        for purchase_mode, enabled in (("subscription", True), ("non_subscription", False)):
            if not self._ensure_quantity_one(page):
                failures.append({**context, "purchase_mode": purchase_mode, "reason": "quantity_one_not_confirmed_before_mode_switch"})
                continue
            if not self._set_subscription_mode(page, enabled, timeout_ms=8_000):
                failures.append({**context, "purchase_mode": purchase_mode, "reason": "auto_renew_toggle_failed"})
                continue
            final_state = self._subscription_control_state(page)
            if not final_state.get("found") or bool(final_state.get("checked")) != bool(enabled):
                failures.append({**context, "purchase_mode": purchase_mode, "reason": "auto_renew_state_not_confirmed"})
                continue
            quantity_ok = self._ensure_quantity_one(page)
            if not quantity_ok:
                failures.append({**context, "purchase_mode": purchase_mode, "reason": "quantity_one_not_confirmed_after_mode_switch"})
                continue
            cards = self._wait_for_price_cards(page, timeout_ms=6_000)
            if not cards:
                failures.append({**context, "purchase_mode": purchase_mode, "reason": "visible_duration_cards_missing"})
                continue
            suffix = self._context_suffix(context, purchase_mode)
            artifact = {
                **context,
                "purchase_mode": purchase_mode,
                "quantity_one": quantity_ok,
                "screenshot_path": self._save_screenshot(page, suffix=suffix),
                "html_path": self._save_html(page, suffix=suffix),
            }
            key = (
                context.get("device_model"),
                context.get("android_version"),
                context.get("server_region"),
                purchase_mode,
            )
            self.purchase_mode_artifacts[key] = artifact
            self.purchase_mode_evidence[key] = {
                **artifact,
                "switch_checked": bool(final_state.get("checked")),
                "switch_text": final_state.get("text"),
                "cards": cards,
            }
            captured.add(purchase_mode)
            counter = "subscription_snapshot_count" if purchase_mode == "subscription" else "non_subscription_snapshot_count"
            self.collection_summary[counter] = int(self.collection_summary.get(counter) or 0) + 1

        if captured == {"subscription", "non_subscription"}:
            self.collection_summary["purchase_mode_context_successes"] = int(
                self.collection_summary.get("purchase_mode_context_successes") or 0
            ) + 1
        if failures:
            existing = list(self.collection_summary.get("purchase_mode_failures") or [])
            self.collection_summary["purchase_mode_failures"] = (existing + failures)[:500]

        restore = self._subscription_control_state(page)
        if restore.get("found") and not bool(restore.get("checked")):
            self._set_subscription_mode(page, True, timeout_ms=8_000)
        self._ensure_quantity_one(page)

    def _context_suffix(self, context: dict[str, Any], purchase_mode: str | None = None) -> str:
        suffix = f"vsphone_{context.get('device_model')}"
        if context.get("android_version"):
            suffix += f"_{context.get('android_version')}"
        if context.get("server_region"):
            suffix += f"_{context.get('server_region')}"
        if purchase_mode:
            suffix += f"_{purchase_mode}"
        return suffix

    def _infer_subscription_api_price_field(
        self,
        configs: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Infer which VSPhone API field represents the live payable price.

        VSPhone can leave a former promotion in ``currentPrice`` after the
        visible card has reverted to ``goodPrice``. During an active promotion
        the reverse is true: the visible card matches ``currentPrice``. The
        selected plan's verified DOM cards therefore decide the field used for
        all plans in the same API response/context.
        """
        votes = {"currentPrice": 0, "goodPrice": 0}
        comparisons: list[dict[str, Any]] = []
        for config in configs or []:
            if not isinstance(config, dict):
                continue
            device_model = self._device_model(config)
            if context.get("device_model") and device_model != context.get("device_model"):
                continue
            product_model = self._product_model(config, device_model)
            android_version = context.get("android_version")
            server_region = context.get("server_region")
            for good_time in config.get("goodTimes") or []:
                if not isinstance(good_time, dict):
                    continue
                duration = good_time.get("showContent")
                card = self._dom_card_evidence(
                    device_model=device_model,
                    android_version=android_version,
                    server_region=server_region,
                    purchase_mode="subscription",
                    product_model=product_model,
                    duration=duration,
                )
                if not card or card.get("price") in [None, ""]:
                    continue
                try:
                    dom_cents = round(float(card.get("price")) * 100)
                except Exception:
                    continue
                current = good_time.get("currentPrice")
                good = good_time.get("goodPrice")
                matched = None
                try:
                    if current not in [None, ""] and abs(float(current) - dom_cents) < 0.5:
                        votes["currentPrice"] += 1
                        matched = "currentPrice"
                    if good not in [None, ""] and abs(float(good) - dom_cents) < 0.5:
                        votes["goodPrice"] += 1
                        matched = "goodPrice" if matched is None else "both"
                except Exception:
                    continue
                comparisons.append({
                    "product_model": product_model,
                    "duration": duration,
                    "dom_price": card.get("price"),
                    "currentPrice": current,
                    "goodPrice": good,
                    "matched": matched,
                })

        if votes["goodPrice"] > votes["currentPrice"]:
            selected = "goodPrice"
        elif votes["currentPrice"] > votes["goodPrice"]:
            selected = "currentPrice"
        elif votes["goodPrice"] > 0:
            # Both fields are equal, so either is safe. Prefer goodPrice because
            # it is the stable non-stale field after campaign transitions.
            selected = "goodPrice"
        else:
            # Keep legacy behaviour only when no live-card comparison exists.
            selected = "currentPrice"
        return selected, {"votes": votes, "comparisons": comparisons[:40]}

    def _duration_days(self, value: Any) -> int | None:
        match = re.search(r"(\d+(?:\.\d+)?)", str(value or ""))
        if not match:
            return None
        try:
            return int(float(match.group(1)))
        except Exception:
            return None

    def _purchase_mode_verified(
        self,
        device_model: str,
        android_version: str | None,
        server_region: str | None,
        purchase_mode: str,
    ) -> bool:
        key = (device_model, android_version, server_region, purchase_mode)
        return key in self.purchase_mode_evidence

    def _dom_card_evidence(
        self,
        *,
        device_model: str,
        android_version: str | None,
        server_region: str | None,
        purchase_mode: str,
        product_model: str | None,
        duration: Any,
    ) -> dict[str, Any] | None:
        evidence = self.purchase_mode_evidence.get(
            (device_model, android_version, server_region, purchase_mode)
        ) or {}
        duration_days = self._duration_days(duration)
        target_model = str(product_model or "").strip().lower()
        for card in evidence.get("cards") or []:
            card_model = str(card.get("product_model") or "").strip().lower()
            if target_model and card_model and target_model != card_model:
                continue
            if self._duration_days(card.get("duration")) != duration_days:
                continue
            return card
        return None

    def _write_collection_summary(self) -> None:
        path = self.artifact_dir / "vsphone_collection_summary.json"
        try:
            path.write_text(
                json.dumps(self.collection_summary, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            self.logger.debug("[%s] failed to write collection summary: %s", self.platform, exc)

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
        suffix = self._context_suffix(context)
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

    def _context_artifact(
        self,
        device_model: str,
        android_version: str | None,
        server_region: str | None,
        purchase_mode: str | None = None,
    ) -> dict | None:
        if purchase_mode:
            mode_artifact = getattr(self, "purchase_mode_artifacts", {}).get(
                (device_model, android_version, server_region, purchase_mode)
            )
            if mode_artifact:
                return mode_artifact
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
