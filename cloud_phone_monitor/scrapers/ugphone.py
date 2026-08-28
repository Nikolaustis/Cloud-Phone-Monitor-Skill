"""UgPhone purchase-page scraper using a synchronized native DOM matrix sweep.

UgPhone's ``mealList`` endpoint is signed by its Vue client and returns encrypted
business data.  The scraper therefore never replays or mutates that endpoint.
It drives only the visible configuration controls — plan, Android version and
server — then captures the price cards rendered by the authenticated page.
"""

from __future__ import annotations

import json
import re
from typing import Any, List

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from cloud_phone_monitor.schemas import ProductRecord
from cloud_phone_monitor.scrapers.base import BaseScraper
from cloud_phone_monitor.utils.normalize import canonical_android_version
from cloud_phone_monitor.utils.normalize import compact_text, now_pair


class UGPhoneScraper(BaseScraper):
    platform = "UGPhone"

    # The authenticated page is the source of truth.  Coverage is defined by
    # the controls currently visible on that page: plan × optional Android
    # version × server.  ``configList2`` is retained only as metadata because
    # it can expose configurations that have no visible DOM selector.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dom_matrix_snapshots: list[dict[str, Any]] = []
        self._config_index: dict[tuple[str, str], dict[str, Any]] = {}
        self.collection_summary: dict[str, Any] = {
            "platform": self.platform,
            "collection_strategy": "native_dom_matrix_synchronized",
            "config_list_passive_seen": False,
            "config_count": 0,
            "native_meal_list_response_count": 0,
            "native_meal_list_encrypted_count": 0,
            "manual_meal_list_requests": 0,
            "manual_meal_list_disabled_reason": "native endpoint requires signed/encrypted client protocol",
            "dom_ready": False,
            "dom_plan_count": 0,
            "dom_version_count": 0,
            "dom_region_count": 0,
            "dom_price_card_count": 0,
            "dom_matrix_plan_targets": 0,
            "dom_matrix_plan_successes": 0,
            "dom_matrix_variant_targets": 0,
            "dom_matrix_variant_attempts": 0,
            "dom_matrix_variant_successes": 0,
            "dom_matrix_region_attempts": 0,
            "dom_matrix_region_targets": 0,
            "dom_matrix_region_snapshots": 0,
            "dom_matrix_region_resolved": 0,
            "dom_matrix_empty_region_cells": 0,
            "dom_matrix_price_rows": 0,
            "partial_record_count": 0,
            "partial_coverage_returned_record_count": 0,
            "dom_matrix_skipped": [],
            "dom_matrix_selection_trace": [],
            "api_product_rows": 0,
            "dom_product_rows": 0,
            "priced_product_rows": 0,
            "unavailable_priced_rows": 0,
            "subscription_control_found": False,
            "purchase_mode_targets": 0,
            "purchase_mode_successes": 0,
            "purchase_mode_pair_targets": 0,
            "purchase_mode_pair_successes": 0,
            "subscription_snapshot_count": 0,
            "non_subscription_snapshot_count": 0,
            "subscription_control_retry_failures": 0,
            "purchase_mode_api_wait_timeouts": 0,
            "purchase_mode_api_wait_warnings": 0,
            "purchase_mode_toggle_retries": 0,
            "missing_non_subscription_counterparts": [],
            "missing_subscription_counterparts": [],
            "purchase_mode_skipped": [],
            "plan_activation_failures": 0,
            "version_list_failures": 0,
            "version_activation_failures": 0,
            "region_list_failures": 0,
            "price_cards_missing_after_full_selection": 0,
            "returned_record_count": 0,
            "coverage_complete": False,
            "coverage_status": "unknown",
            "coverage_note": None,
            "collection_status": "unknown",
            "failure_reason": None,
            "login_page_detected": False,
        }

    def scrape(self) -> List[ProductRecord]:
        """Return every valid price card observed during the live DOM sweep.

        Collection and downstream merging are intentionally separated.  The
        scraper never erases valid observations merely because some visible
        plan/version/region cells could not be synchronized during the same
        run.  Coverage remains fully recorded in ``ugphone_collection_summary``
        so the merge/quality layer can apply its own policy.

        A row is emitted whenever the authenticated page exposes a duration and
        a numeric price.  Disabled/sold-out cards with an explicit price are
        also emitted and marked ``stock_status='unavailable'``.
        """
        collected = super().scrape()
        matrix_records = self._dedupe_records(
            [record for record in collected if record.extraction_method == "dom_matrix"]
        )
        priced_rows = sum(
            1
            for record in matrix_records
            if record.price not in {None, ""} and record.duration not in {None, ""}
        )
        target_plans = int(self.collection_summary.get("dom_matrix_plan_targets") or 0)
        plan_successes = int(self.collection_summary.get("dom_matrix_plan_successes") or 0)
        target_variants = int(self.collection_summary.get("dom_matrix_variant_targets") or 0)
        variant_successes = int(self.collection_summary.get("dom_matrix_variant_successes") or 0)
        target_regions = int(self.collection_summary.get("dom_matrix_region_targets") or 0)
        region_snapshots = int(self.collection_summary.get("dom_matrix_region_snapshots") or 0)
        region_resolved = int(
            self.collection_summary.get("dom_matrix_region_resolved") or region_snapshots
        )
        coverage_complete = bool(
            target_plans > 0
            and plan_successes >= target_plans
            and target_variants > 0
            and variant_successes >= target_variants
            and target_regions > 0
            and region_resolved >= target_regions
        )
        unavailable_priced_rows = sum(
            1 for record in matrix_records if str(record.stock_status or "").lower() == "unavailable"
        )
        self.collection_summary.update(
            {
                "api_product_rows": 0,
                "dom_product_rows": len(matrix_records),
                "priced_product_rows": priced_rows,
                "unavailable_priced_rows": unavailable_priced_rows,
                "returned_record_count": len(matrix_records),
                "partial_record_count": len(matrix_records) if not coverage_complete else 0,
                "partial_coverage_returned_record_count": len(matrix_records) if not coverage_complete else 0,
                "final_record_count": len(matrix_records),
                "coverage_complete": coverage_complete,
                "coverage_status": "complete" if coverage_complete else "partial",
            }
        )

        if matrix_records:
            # Any real visible price is a valid collection result.  Missing or
            # unresolved matrix cells remain diagnostic metadata only; they do
            # not turn captured prices into an empty platform result.
            records = matrix_records
            # Captured rows remain valid, but partial matrix coverage must not be
            # reported as fully healthy.  Downstream Dashboard status can then
            # distinguish "prices captured" from "all expected plan/version/region
            # cells captured".
            self.collection_summary["collection_status"] = "ok" if coverage_complete else "warning"
            self.collection_summary["failure_reason"] = None
            self.collection_summary["coverage_note"] = (
                "complete_visible_matrix"
                if coverage_complete
                else (
                    "partial_visible_matrix_returned; "
                    f"plans={plan_successes}/{target_plans}; "
                    f"variants={variant_successes}/{target_variants}; "
                    f"priced_regions={region_snapshots}/{target_regions}; "
                    f"resolved_regions={region_resolved}/{target_regions}; "
                    f"priced_rows={priced_rows}"
                )
            )
        else:
            records = []
            self.collection_summary["collection_status"] = "failed"
            self.collection_summary["failure_reason"] = (
                self.collection_summary.get("failure_reason")
                or "native_dom_matrix_empty"
            )
            self.collection_summary["coverage_note"] = "no_visible_price_cards_collected"
            self._write_partial_records(matrix_records)
        self._write_collection_summary()
        return records

    def _collect_interactive_states(self, page: Page, url: str) -> None:
        self._wait_for_purchase_dom(page)
        if self._login_page_visible(page):
            self.collection_summary["login_page_detected"] = True
            self.collection_summary["failure_reason"] = "login_page_detected"
            self._write_collection_summary()
            return

        configs = self._configs_from_api_candidates()
        self.collection_summary["config_list_passive_seen"] = bool(configs)
        self.collection_summary["config_count"] = len(configs)
        # Important: configList2 is a passive backend inventory, not proof that
        # each item is exposed by a visible Android-version selector.  Matrix
        # targets are counted during the DOM sweep from actual controls.
        self.collection_summary["dom_matrix_variant_targets"] = 0
        self.collection_summary["dom_matrix_region_targets"] = 0
        self.collection_summary["dom_matrix_region_resolved"] = 0
        self.collection_summary["dom_matrix_empty_region_cells"] = 0
        self._config_index = {
            (self._normal_key(item.get("plan")), self._normal_key(item.get("version_label"))): item
            for item in configs
            if item.get("plan") and item.get("version_label")
        }
        self._summarize_native_meal_responses()

        self._dom_matrix_snapshots = self._sweep_rendered_price_matrix(page)
        self.collection_summary["dom_matrix_region_snapshots"] = len(self._dom_matrix_snapshots)
        self.collection_summary["dom_matrix_price_rows"] = sum(
            len(snapshot.get("cards") or []) for snapshot in self._dom_matrix_snapshots
        )
        if not self._dom_matrix_snapshots and not self.collection_summary.get("failure_reason"):
            self.collection_summary["failure_reason"] = "native_dom_matrix_empty"
        self._write_collection_summary()

    def _wait_for_purchase_dom(self, page: Page) -> None:
        selectors = {
            "plan": ".purchase-details-container .config-name",
            "region": ".purchase-details-container .room-item",
            "price": ".purchase-details-container .price-item .card-price-num",
        }
        try:
            page.wait_for_selector(selectors["plan"], state="visible", timeout=20_000)
            page.wait_for_selector(selectors["region"], state="visible", timeout=20_000)
            page.wait_for_selector(selectors["price"], state="visible", timeout=20_000)
        except PlaywrightTimeoutError:
            self.logger.warning("[%s] purchase business selectors did not become ready before timeout", self.platform)
            if self._login_page_visible(page):
                self.collection_summary["login_page_detected"] = True
                self.collection_summary["failure_reason"] = "login_page_detected"
        except Exception as exc:
            self.logger.debug("[%s] purchase readiness check skipped: %s", self.platform, exc)
        self._refresh_dom_counts(page)

    def _refresh_dom_counts(self, page: Page) -> None:
        try:
            counts = page.evaluate(
                """
                () => ({
                  plan: document.querySelectorAll('.purchase-details-container .van-tabs [role="tab"]').length,
                  version: document.querySelectorAll('.purchase-details-container .version-item').length,
                  region: document.querySelectorAll('.purchase-details-container .meal-data-item .room-item').length,
                  price: document.querySelectorAll('.purchase-details-container .meal-data-item .price-item .card-price-num').length
                })
                """
            ) or {}
        except Exception:
            counts = {}
        self.collection_summary.update(
            {
                "dom_plan_count": int(counts.get("plan") or 0),
                "dom_version_count": int(counts.get("version") or 0),
                "dom_region_count": int(counts.get("region") or 0),
                "dom_price_card_count": int(counts.get("price") or 0),
                "dom_ready": bool(counts.get("plan") and counts.get("region") and counts.get("price")),
            }
        )

    def _login_page_visible(self, page: Page) -> bool:
        try:
            text = (page.locator("body").inner_text(timeout=3_000) or "").lower()
        except Exception:
            return False
        markers = [
            "通过google登录", "通过apple登录", "通过facebook登录", "手机号登录",
            "login with google", "login with apple", "login with facebook", "phone login",
            "sign up with google", "sign up with apple", "sign up with facebook",
        ]
        return any(marker in text for marker in markers)

    def _summarize_native_meal_responses(self) -> None:
        meal_items = [item for item in self.api_candidates if "meallist" in (item.get("url") or "").lower()]
        encrypted = 0
        for item in meal_items:
            payload = item.get("response_json")
            if isinstance(payload, dict) and int(payload.get("code") or 0) in {2001, 2002}:
                encrypted += 1
        self.collection_summary.update(
            {
                "native_meal_list_response_count": len(meal_items),
                "native_meal_list_encrypted_count": encrypted,
            }
        )

    def _sweep_rendered_price_matrix(self, page: Page) -> list[dict[str, Any]]:
        """Synchronize every plan → Android version → server matrix cell.

        Only the bounded configuration controls are interacted with: plan,
        optional Android version, server region, and the purchase page's
        Subscribe/auto-renew checkbox. Buy, duration cards and quantity controls
        are never targeted. Both subscription and one-time prices are captured
        when the checkbox is available; subscription is restored afterwards.
        """
        plan_entries = self._plan_entries(page)
        self.collection_summary.update(
            {
                "dom_matrix_plan_targets": len(plan_entries),
                "dom_matrix_plan_successes": 0,
                "dom_matrix_variant_targets": 0,
                "dom_matrix_variant_attempts": 0,
                "dom_matrix_variant_successes": 0,
                "dom_matrix_region_attempts": 0,
                "dom_matrix_region_targets": 0,
                "dom_matrix_region_snapshots": 0,
                "dom_matrix_region_resolved": 0,
                "dom_matrix_empty_region_cells": 0,
                "dom_matrix_price_rows": 0,
                "purchase_mode_targets": 0,
                "purchase_mode_successes": 0,
                "purchase_mode_pair_targets": 0,
                "purchase_mode_pair_successes": 0,
                "subscription_snapshot_count": 0,
                "non_subscription_snapshot_count": 0,
                "subscription_control_retry_failures": 0,
                "purchase_mode_api_wait_timeouts": 0,
                "purchase_mode_api_wait_warnings": 0,
                "purchase_mode_toggle_retries": 0,
                "missing_non_subscription_counterparts": [],
                "missing_subscription_counterparts": [],
                "purchase_mode_skipped": [],
                "plan_activation_failures": 0,
                "version_list_failures": 0,
                "version_activation_failures": 0,
                "region_list_failures": 0,
                "price_cards_missing_after_full_selection": 0,
            }
        )
        snapshots: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []

        for plan_index, plan_entry in enumerate(plan_entries):
            # Plan activation and price rendering are separate states on UgPhone.
            # A plan with multiple Android variants can legitimately have no price
            # cards immediately after the plan tab is selected because the Vue
            # component is still carrying the previous plan's region/version.
            # Therefore never require plan-level cards before entering the
            # Android -> region matrix.
            target_plan = str(
                plan_entry.get("name") or plan_entry.get("label") or f"plan_{plan_index}"
            )
            api_versions = self._api_version_entries_for_plan(target_plan)

            plan_state: dict[str, Any] = {}
            for plan_attempt in range(3):
                if not self._click_selector(
                    page, ".purchase-details-container .van-tabs [role='tab']", plan_index
                ):
                    if plan_attempt == 2:
                        skipped.append({"plan": target_plan, "reason": "plan_click_failed"})
                    page.wait_for_timeout(600)
                    continue
                plan_state = self._wait_for_rendered_state(
                    page,
                    expected_plan=target_plan,
                    timeout_ms=8_000,
                    allow_empty_cards=True,
                    stable_frames_required=2,
                )
                if plan_state and self._matches_selection(plan_state.get("active_plan"), target_plan):
                    break
                page.wait_for_timeout(700)

            if not plan_state or not self._matches_selection(plan_state.get("active_plan"), target_plan):
                self.collection_summary["plan_activation_failures"] = int(
                    self.collection_summary.get("plan_activation_failures") or 0
                ) + 1
                skipped.append(
                    {
                        "plan": target_plan,
                        "reason": "plan_activation_failed",
                        "observed_plan": (plan_state or {}).get("active_plan"),
                        "observed_version": (plan_state or {}).get("active_version"),
                        "observed_region": (plan_state or {}).get("active_region"),
                        "cards": len((plan_state or {}).get("cards") or []),
                    }
                )
                continue

            active_plan = str(plan_state.get("active_plan") or target_plan)
            versions, plan_state = self._resolve_plan_versions(
                page, target_plan=target_plan, initial_state=plan_state, api_versions=api_versions
            )
            if not versions:
                self.collection_summary["version_list_failures"] = int(
                    self.collection_summary.get("version_list_failures") or 0
                ) + 1
                skipped.append(
                    {
                        "plan": active_plan,
                        "reason": "version_list_missing_after_plan_activation",
                        "expected_versions": [item.get("name") for item in api_versions],
                        "cards": len((plan_state or {}).get("cards") or []),
                    }
                )
                continue

            self.collection_summary["dom_matrix_variant_targets"] = int(
                self.collection_summary.get("dom_matrix_variant_targets") or 0
            ) + len(versions)

            plan_variant_successes = 0
            for version_index, version in enumerate(versions):
                version_name = str(version.get("name") or f"version_{version_index}")
                selectorless_version = bool(version.get("selectorless"))
                self.collection_summary["dom_matrix_variant_attempts"] = int(
                    self.collection_summary.get("dom_matrix_variant_attempts") or 0
                ) + 1

                # If there is an actual version control, click the requested
                # Android variant explicitly even if it appears active. This
                # forces UgPhone to rebuild its signed request context and avoids
                # inheriting the previous plan's region state. Selector-less
                # UVIP/SVIP-style plans use their sole API config as metadata.
                if not selectorless_version:
                    if not self._click_selector(page, ".purchase-details-container .version-item", version_index):
                        skipped.append(
                            {"plan": active_plan, "version": version_name, "reason": "version_click_failed"}
                        )
                        continue

                expected_version = None if selectorless_version else version_name
                variant_state = self._wait_for_rendered_state(
                    page,
                    expected_plan=target_plan,
                    expected_version=expected_version,
                    timeout_ms=8_000,
                    allow_empty_cards=True,
                    stable_frames_required=2,
                )
                if not variant_state:
                    page.wait_for_timeout(700)
                    if not selectorless_version:
                        self._click_selector(page, ".purchase-details-container .version-item", version_index)
                    variant_state = self._wait_for_rendered_state(
                        page,
                        expected_plan=target_plan,
                        expected_version=expected_version,
                        timeout_ms=8_000,
                        allow_empty_cards=True,
                        stable_frames_required=2,
                    )
                if not variant_state:
                    self.collection_summary["version_activation_failures"] = int(
                        self.collection_summary.get("version_activation_failures") or 0
                    ) + 1
                    skipped.append(
                        {
                            "plan": active_plan,
                            "version": version_name,
                            "reason": "version_activation_failed",
                        }
                    )
                    continue

                active_version = str(variant_state.get("active_version") or version_name)
                variant_state = self._wait_for_regions_for_selection(
                    page,
                    expected_plan=target_plan,
                    expected_version=expected_version,
                    timeout_ms=8_000,
                )
                regions = variant_state.get("regions") or []
                if not regions:
                    self.collection_summary["region_list_failures"] = int(
                        self.collection_summary.get("region_list_failures") or 0
                    ) + 1
                    skipped.append(
                        {
                            "plan": active_plan,
                            "version": active_version,
                            "reason": "regions_missing_after_full_variant_activation",
                        }
                    )
                    continue
                self.collection_summary["dom_matrix_region_targets"] = int(
                    self.collection_summary.get("dom_matrix_region_targets") or 0
                ) + len(regions)

                variant_snapshot_count = 0
                for region_index, region in enumerate(regions):
                    region_name = str(region.get("name") or "").strip()
                    if not region_name:
                        continue
                    self.collection_summary["dom_matrix_region_attempts"] = int(
                        self.collection_summary.get("dom_matrix_region_attempts") or 0
                    ) + 1

                    if not self._click_selector(
                        page, ".purchase-details-container .meal-data-item .room-item", region_index
                    ):
                        skipped.append(
                            {
                                "plan": active_plan,
                                "version": active_version,
                                "region": region_name,
                                "reason": "region_click_failed",
                            }
                        )
                        continue

                    snapshot = self._wait_for_rendered_state(
                        page,
                        expected_plan=target_plan,
                        expected_version=expected_version,
                        expected_region=region_name,
                        timeout_ms=10_000,
                        allow_empty_cards=True,
                    )
                    if not snapshot:
                        page.wait_for_timeout(900)
                        self._click_selector(
                            page, ".purchase-details-container .meal-data-item .room-item", region_index
                        )
                        snapshot = self._wait_for_rendered_state(
                            page,
                            expected_plan=target_plan,
                            expected_version=expected_version,
                            expected_region=region_name,
                            timeout_ms=10_000,
                            allow_empty_cards=True,
                        )

                    if not snapshot:
                        skipped.append(
                            {
                                "plan": active_plan,
                                "version": active_version,
                                "region": region_name,
                                "reason": "region_state_not_confirmed_after_sync",
                            }
                        )
                        continue

                    self.collection_summary["dom_matrix_region_resolved"] = int(
                        self.collection_summary.get("dom_matrix_region_resolved") or 0
                    ) + 1

                    mode_snapshots, mode_failures = self._capture_purchase_mode_states(
                        page,
                        expected_plan=target_plan,
                        expected_version=expected_version,
                        expected_region=region_name,
                    )
                    skipped.extend(mode_failures)
                    if not mode_snapshots:
                        self.collection_summary["dom_matrix_empty_region_cells"] = int(
                            self.collection_summary.get("dom_matrix_empty_region_cells") or 0
                        ) + 1
                        self.collection_summary["price_cards_missing_after_full_selection"] = int(
                            self.collection_summary.get("price_cards_missing_after_full_selection") or 0
                        ) + 1
                        skipped.append(
                            {
                                "plan": active_plan,
                                "version": active_version,
                                "region": region_name,
                                "reason": "price_cards_missing_after_full_selection",
                            }
                        )
                        if len(trace) < 250:
                            trace.append(
                                {
                                    "plan": snapshot.get("active_plan") or active_plan,
                                    "version": snapshot.get("active_version") or active_version,
                                    "region": snapshot.get("active_region") or region_name,
                                    "cards": 0,
                                    "availability": "no_priced_purchase_mode",
                                }
                            )
                        continue

                    for mode_snapshot in mode_snapshots:
                        mode_snapshot["active_plan"] = mode_snapshot.get("active_plan") or active_plan
                        mode_snapshot["active_version"] = mode_snapshot.get("active_version") or active_version
                        mode_snapshot["active_region"] = mode_snapshot.get("active_region") or region_name
                        mode_snapshot["plan_index"] = plan_index
                        mode_snapshot["version_index"] = version_index
                        mode_snapshot["region_index"] = region_index
                        cfg = self._config_index.get(
                            (
                                self._normal_key(mode_snapshot["active_plan"]),
                                self._normal_key(mode_snapshot["active_version"]),
                            )
                        )
                        if cfg:
                            mode_snapshot["config_id"] = cfg.get("config_id")
                        snapshots.append(mode_snapshot)
                        if len(trace) < 250:
                            trace.append(
                                {
                                    "plan": mode_snapshot["active_plan"],
                                    "version": mode_snapshot["active_version"],
                                    "region": mode_snapshot["active_region"],
                                    "purchase_mode": mode_snapshot.get("purchase_mode"),
                                    "cards": len(mode_snapshot.get("cards") or []),
                                }
                            )
                    variant_snapshot_count += 1

                if variant_snapshot_count:
                    plan_variant_successes += 1
                    self.collection_summary["dom_matrix_variant_successes"] = int(
                        self.collection_summary.get("dom_matrix_variant_successes") or 0
                    ) + 1
                else:
                    skipped.append(
                        {"plan": active_plan, "version": active_version, "reason": "no_region_snapshot_captured"}
                    )

            if plan_variant_successes:
                self.collection_summary["dom_matrix_plan_successes"] = int(
                    self.collection_summary.get("dom_matrix_plan_successes") or 0
                ) + 1
            else:
                skipped.append({"plan": active_plan, "reason": "no_variant_snapshot_captured"})

        self.collection_summary["dom_matrix_skipped"] = skipped
        self.collection_summary["dom_matrix_selection_trace"] = trace
        self._summarize_native_meal_responses()
        self._refresh_dom_counts(page)
        self.logger.info(
            "[%s] synchronized native DOM matrix: %s/%s plans, %s/%s visible variants, %s price snapshots; %s/%s resolved regions",
            self.platform,
            self.collection_summary.get("dom_matrix_plan_successes"),
            self.collection_summary.get("dom_matrix_plan_targets"),
            self.collection_summary.get("dom_matrix_variant_successes"),
            self.collection_summary.get("dom_matrix_variant_targets"),
            len(snapshots),
            self.collection_summary.get("dom_matrix_region_resolved"),
            self.collection_summary.get("dom_matrix_region_targets"),
        )
        return snapshots

    def _subscription_control_state(self, page: Page) -> dict[str, Any]:
        """Return the visible purchase-page Subscribe/auto-renew checkbox state."""
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
                  const text = (node) => String(node?.innerText || node?.textContent || '').replace(/\s+/g, ' ').trim();
                  const matches = (value) => /subscribe|subscription|auto[\s-]*renew|自动续费|自動續費|订阅|訂閱/i.test(String(value || ''));
                  const scope = document.body;
                  const candidates = Array.from(scope.querySelectorAll(
                    'input[type="checkbox"], [role="checkbox"], label, .van-checkbox, .el-checkbox, .checkbox, [class*="subscribe"], [class*="renew"]'
                  )).filter(visible);
                  const checkedOf = (node) => {
                    const input = node.matches?.('input[type="checkbox"]') ? node : node.querySelector?.('input[type="checkbox"]');
                    if (input) return Boolean(input.checked);
                    const aria = node.getAttribute?.('aria-checked');
                    if (aria === 'true' || aria === 'false') return aria === 'true';
                    const classes = String(node.className || '').toLowerCase();
                    return /(^|\s)(is-checked|checked|active|selected)(\s|$)/.test(classes) || Boolean(node.querySelector?.('.van-icon-success, .is-checked, .checked'));
                  };
                  let chosen = candidates.find((node) => matches(text(node.closest?.('label') || node.parentElement || node)));
                  if (!chosen) chosen = candidates.find((node) => matches(text(node.parentElement)));
                  if (!chosen) return { found: false, checked: null, text: '' };
                  const container = chosen.closest?.('label, .van-checkbox, .el-checkbox, .checkbox, [class*="subscribe"], [class*="renew"]') || chosen;
                  return { found: true, checked: checkedOf(container), text: text(container) };
                }
                """
            )
            return state if isinstance(state, dict) else {"found": False, "checked": None, "text": ""}
        except Exception as exc:
            self.logger.debug("[%s] subscription state probe failed: %s", self.platform, exc)
            return {"found": False, "checked": None, "text": ""}

    def _scroll_subscription_control_into_view(self, page: Page) -> None:
        """Bring the fixed Subscribe footer into a detectable viewport state."""
        try:
            page.evaluate(
                r"""
                () => {
                  const text = (node) => String(node?.innerText || node?.textContent || '').replace(/\s+/g, ' ').trim();
                  const matches = (value) => /subscribe|subscription|auto[\s-]*renew|自动续费|自動續費|订阅|訂閱/i.test(String(value || ''));
                  const candidates = Array.from(document.querySelectorAll(
                    'input[type="checkbox"], [role="checkbox"], label, .van-checkbox, .el-checkbox, .checkbox, [class*="subscribe"], [class*="renew"]'
                  ));
                  const chosen = candidates.find((node) => matches(text(node.closest?.('label') || node.parentElement || node)))
                    || candidates.find((node) => matches(text(node.parentElement)));
                  if (chosen) {
                    const container = chosen.closest?.('label, .van-checkbox, .el-checkbox, .checkbox, [class*="subscribe"], [class*="renew"]') || chosen;
                    container.scrollIntoView({ block: 'center', inline: 'nearest' });
                    return true;
                  }
                  window.scrollTo(0, document.documentElement.scrollHeight);
                  return false;
                }
                """
            )
        except Exception as exc:
            self.logger.debug("[%s] subscription control scroll assist failed: %s", self.platform, exc)

    def _wait_for_subscription_control(self, page: Page, timeout_ms: int = 8_000) -> dict[str, Any]:
        """Retry the Subscribe control instead of silently dropping one-time capture."""
        waited = 0
        while waited < timeout_ms:
            state = self._subscription_control_state(page)
            if state.get("found"):
                return state
            if waited == 0 or waited % 1_600 == 0:
                self._scroll_subscription_control_into_view(page)
            page.wait_for_timeout(400)
            waited += 400
        self.collection_summary["subscription_control_retry_failures"] = int(
            self.collection_summary.get("subscription_control_retry_failures") or 0
        ) + 1
        return {"found": False, "checked": None, "text": ""}

    def _meal_response_count_for_mode(self, enabled: bool) -> int:
        """Count native mealList responses carrying the requested subscription flag."""
        target = 1 if enabled else 0
        count = 0
        for item in self.api_candidates:
            if "meallist" not in str(item.get("url") or "").lower():
                continue
            payload = item.get("request_payload")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = None
            if not isinstance(payload, dict):
                continue
            try:
                value = int(payload.get("subscription"))
            except (TypeError, ValueError):
                continue
            if value == target:
                count += 1
        return count

    def _wait_for_new_meal_response(
        self,
        page: Page,
        *,
        enabled: bool,
        previous_count: int,
        timeout_ms: int = 12_000,
    ) -> bool:
        """Wait until the Vue client finishes a native signed request for this mode."""
        waited = 0
        while waited < timeout_ms:
            if self._meal_response_count_for_mode(enabled) > previous_count:
                page.wait_for_timeout(900)
                return True
            page.wait_for_timeout(250)
            waited += 250
        self.collection_summary["purchase_mode_api_wait_timeouts"] = int(
            self.collection_summary.get("purchase_mode_api_wait_timeouts") or 0
        ) + 1
        return False

    def _set_subscription_mode(self, page: Page, enabled: bool, timeout_ms: int = 6_000) -> bool:
        """Set Subscribe without touching Buy, quantity or duration controls."""
        state = self._subscription_control_state(page)
        if not state.get("found"):
            return False
        if bool(state.get("checked")) == bool(enabled):
            return True
        try:
            clicked = page.evaluate(
                r"""
                (enabled) => {
                  const visible = (node) => {
                    if (!node) return false;
                    const style = window.getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                  };
                  const text = (node) => String(node?.innerText || node?.textContent || '').replace(/\s+/g, ' ').trim();
                  const matches = (value) => /subscribe|subscription|auto[\s-]*renew|自动续费|自動續費|订阅|訂閱/i.test(String(value || ''));
                  const checkedOf = (node) => {
                    const input = node.matches?.('input[type="checkbox"]') ? node : node.querySelector?.('input[type="checkbox"]');
                    if (input) return Boolean(input.checked);
                    const aria = node.getAttribute?.('aria-checked');
                    if (aria === 'true' || aria === 'false') return aria === 'true';
                    const classes = String(node.className || '').toLowerCase();
                    return /(^|\s)(is-checked|checked|active|selected)(\s|$)/.test(classes) || Boolean(node.querySelector?.('.van-icon-success, .is-checked, .checked'));
                  };
                  const scope = document.body;
                  const candidates = Array.from(scope.querySelectorAll(
                    'input[type="checkbox"], [role="checkbox"], label, .van-checkbox, .el-checkbox, .checkbox, [class*="subscribe"], [class*="renew"]'
                  )).filter(visible);
                  let chosen = candidates.find((node) => matches(text(node.closest?.('label') || node.parentElement || node)));
                  if (!chosen) chosen = candidates.find((node) => matches(text(node.parentElement)));
                  if (!chosen) return false;
                  const container = chosen.closest?.('label, .van-checkbox, .el-checkbox, .checkbox, [class*="subscribe"], [class*="renew"]') || chosen;
                  if (checkedOf(container) === Boolean(enabled)) return true;
                  const input = container.matches?.('input[type="checkbox"]') ? container : container.querySelector?.('input[type="checkbox"]');
                  const target = input && !input.disabled ? input : container;
                  target.click();
                  return true;
                }
                """,
                bool(enabled),
            )
            if not clicked:
                return False
        except Exception as exc:
            self.logger.debug("[%s] subscription toggle click failed: %s", self.platform, exc)
            return False

        waited = 0
        while waited < timeout_ms:
            page.wait_for_timeout(250)
            waited += 250
            state = self._subscription_control_state(page)
            if state.get("found") and bool(state.get("checked")) == bool(enabled):
                # UgPhone refreshes signed meal data asynchronously after the
                # checkbox state changes. Give Vue one short settling window.
                page.wait_for_timeout(700)
                return True
        return False

    def _capture_purchase_mode_states(
        self,
        page: Page,
        *,
        expected_plan: str,
        expected_version: str | None,
        expected_region: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Capture Subscribe on/off prices for one selected matrix cell.

        The checkbox state and the rendered price cards are the source of truth.
        A native ``mealList`` request is useful diagnostic evidence, but it is
        not a publication gate: Playwright's response listener can miss or delay
        a signed/encrypted request even after Vue has already rendered the new
        prices.  The previous hard API gate caused most one-time prices to be
        discarded despite a successful checkbox switch.
        """
        control = self._wait_for_subscription_control(page, timeout_ms=12_000)
        self.collection_summary["subscription_control_found"] = bool(
            self.collection_summary.get("subscription_control_found") or control.get("found")
        )
        self.collection_summary["purchase_mode_targets"] = int(
            self.collection_summary.get("purchase_mode_targets") or 0
        ) + 2

        captured: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        captured_by_mode: dict[str, dict[str, Any]] = {}

        if not control.get("found"):
            failures.extend([
                {
                    "plan": expected_plan,
                    "version": expected_version,
                    "region": expected_region,
                    "purchase_mode": "subscription",
                    "reason": "subscription_control_missing_after_retry",
                },
                {
                    "plan": expected_plan,
                    "version": expected_version,
                    "region": expected_region,
                    "purchase_mode": "non_subscription",
                    "reason": "subscription_control_missing_after_retry",
                },
            ])
        else:
            for mode, desired in (("subscription", True), ("non_subscription", False)):
                snapshot: dict[str, Any] = {}
                last_reason = "purchase_mode_capture_failed"

                for attempt in range(3):
                    current = self._wait_for_subscription_control(page, timeout_ms=6_000)
                    if not current.get("found"):
                        last_reason = "subscription_control_missing_before_mode_switch"
                        self._scroll_subscription_control_into_view(page)
                        page.wait_for_timeout(700)
                        continue

                    changed = bool(current.get("checked")) != bool(desired)
                    previous_response_count = self._meal_response_count_for_mode(desired)
                    if not self._set_subscription_mode(page, desired, timeout_ms=10_000):
                        last_reason = "subscription_toggle_failed"
                        continue

                    # The page often renders correctly even when the passive API
                    # listener misses the signed request.  Wait briefly for the
                    # request as evidence, but always continue to the DOM gate.
                    api_seen = True
                    if changed:
                        api_seen = self._wait_for_new_meal_response(
                            page,
                            enabled=desired,
                            previous_count=previous_response_count,
                            timeout_ms=3_500,
                        )
                        if not api_seen:
                            self.collection_summary["purchase_mode_api_wait_warnings"] = int(
                                self.collection_summary.get("purchase_mode_api_wait_warnings") or 0
                            ) + 1

                    # Give the encrypted response / Vue render one guaranteed
                    # settling window, then require non-empty cards stable across
                    # three frames.  Equal Subscribe/on-off prices are legitimate,
                    # so a changed price fingerprint is deliberately not required.
                    page.wait_for_timeout(1_300 if api_seen else 1_900)
                    snapshot = self._wait_for_rendered_state(
                        page,
                        expected_plan=expected_plan,
                        expected_version=expected_version,
                        expected_region=expected_region,
                        timeout_ms=18_000,
                        allow_empty_cards=False,
                        stable_frames_required=3,
                    )
                    final_control = self._wait_for_subscription_control(page, timeout_ms=3_000)
                    mode_confirmed = bool(
                        final_control.get("found")
                        and bool(final_control.get("checked")) == bool(desired)
                    )
                    if mode_confirmed and snapshot and snapshot.get("cards"):
                        break

                    last_reason = (
                        "purchase_mode_state_not_confirmed_after_sync"
                        if not mode_confirmed
                        else "price_cards_missing_after_purchase_mode_sync"
                    )
                    snapshot = {}
                    if attempt < 2:
                        self.collection_summary["purchase_mode_toggle_retries"] = int(
                            self.collection_summary.get("purchase_mode_toggle_retries") or 0
                        ) + 1
                        # Re-arm the Vue watcher.  This is still only the visible
                        # Subscribe checkbox; Buy/quantity/duration are untouched.
                        if self._set_subscription_mode(page, not desired, timeout_ms=8_000):
                            page.wait_for_timeout(900)
                        self._scroll_subscription_control_into_view(page)

                if not snapshot or not snapshot.get("cards"):
                    failures.append({
                        "plan": expected_plan,
                        "version": expected_version,
                        "region": expected_region,
                        "purchase_mode": mode,
                        "reason": last_reason,
                    })
                    continue

                snapshot["purchase_mode"] = mode
                snapshot["subscription_enabled"] = mode == "subscription"
                captured.append(snapshot)
                captured_by_mode[mode] = snapshot
                self.collection_summary["purchase_mode_successes"] = int(
                    self.collection_summary.get("purchase_mode_successes") or 0
                ) + 1
                counter = "subscription_snapshot_count" if mode == "subscription" else "non_subscription_snapshot_count"
                self.collection_summary[counter] = int(self.collection_summary.get(counter) or 0) + 1

        if "subscription" in captured_by_mode:
            self.collection_summary["purchase_mode_pair_targets"] = int(
                self.collection_summary.get("purchase_mode_pair_targets") or 0
            ) + 1
        if "subscription" in captured_by_mode and "non_subscription" in captured_by_mode:
            self.collection_summary["purchase_mode_pair_successes"] = int(
                self.collection_summary.get("purchase_mode_pair_successes") or 0
            ) + 1
        elif "subscription" in captured_by_mode and "non_subscription" not in captured_by_mode:
            missing = list(self.collection_summary.get("missing_non_subscription_counterparts") or [])
            missing.append({"plan": expected_plan, "version": expected_version, "region": expected_region})
            self.collection_summary["missing_non_subscription_counterparts"] = missing[:500]
        elif "non_subscription" in captured_by_mode and "subscription" not in captured_by_mode:
            missing = list(self.collection_summary.get("missing_subscription_counterparts") or [])
            missing.append({"plan": expected_plan, "version": expected_version, "region": expected_region})
            self.collection_summary["missing_subscription_counterparts"] = missing[:500]

        # Keep the next matrix cell deterministic: always leave Subscribe on.
        restore_state = self._wait_for_subscription_control(page, timeout_ms=5_000)
        if restore_state.get("found") and not bool(restore_state.get("checked")):
            self._set_subscription_mode(page, True, timeout_ms=10_000)
            page.wait_for_timeout(900)

        if failures:
            existing = list(self.collection_summary.get("purchase_mode_skipped") or [])
            self.collection_summary["purchase_mode_skipped"] = (existing + failures)[:500]
        return captured, failures

    def _plan_entries(self, page: Page) -> list[dict[str, Any]]:
        return self._entries(page, ".purchase-details-container .van-tabs [role='tab']", ".config-name")

    def _version_entries(self, page: Page) -> list[dict[str, Any]]:
        return self._entries(page, ".purchase-details-container .version-item")

    def _api_version_entries_for_plan(self, plan: str) -> list[dict[str, Any]]:
        """Return passive configList2 Android variants for one visible plan.

        These entries are metadata/fallback only. They do not prove that a
        selector is visible, but they let the state machine know whether a
        multi-version plan such as GVIP is still waiting for its version
        controls instead of misclassifying a temporary card-less state as a
        whole-plan failure.
        """
        plan_key = self._normal_key(plan)
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for (candidate_plan, _), cfg in self._config_index.items():
            if candidate_plan != plan_key:
                continue
            name = str(cfg.get("version_label") or cfg.get("android_version") or "").strip()
            key = self._normal_key(name)
            if not name or key in seen:
                continue
            seen.add(key)
            rows.append({"name": name, "active": False, "source": "configList2"})

        def sort_key(item: dict[str, Any]) -> tuple[float, str]:
            canonical = canonical_android_version(item.get("name"))
            match = re.search(r"(\d+(?:\.\d+)?)", str(canonical or item.get("name") or ""))
            return (float(match.group(1)) if match else 9999.0, self._normal_key(item.get("name")))

        rows.sort(key=sort_key)
        for index, row in enumerate(rows):
            row["index"] = index
        return rows

    def _resolve_plan_versions(
        self,
        page: Page,
        *,
        target_plan: str,
        initial_state: dict[str, Any],
        api_versions: list[dict[str, Any]],
        timeout_ms: int = 8_000,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Wait for Android controls after plan activation without requiring cards."""
        attempts = max(1, int(timeout_ms / 250))
        best = initial_state or {}
        expected_api = {self._normal_key(item.get("name")) for item in api_versions if item.get("name")}
        for _ in range(attempts):
            state = self._current_purchase_state(page) or best
            if state:
                best = state
            if self._matches_selection(state.get("active_plan"), target_plan):
                versions = state.get("versions") or self._version_entries(page)
                if versions:
                    observed = {self._normal_key(item.get("name")) for item in versions if item.get("name")}
                    # For multi-version plans, do not accept a stale/incomplete
                    # version tree carried over from the previous plan.
                    if len(api_versions) <= 1 or not expected_api or expected_api.issubset(observed):
                        return versions, state
                elif len(api_versions) == 1:
                    item = dict(api_versions[0])
                    item.update({"index": 0, "active": True, "selectorless": True})
                    return [item], state
                elif not api_versions:
                    return [
                        {
                            "index": 0,
                            "name": state.get("active_version") or "default",
                            "active": True,
                            "selectorless": True,
                        }
                    ], state
            page.wait_for_timeout(250)
        return [], best

    def _wait_for_regions_for_selection(
        self,
        page: Page,
        *,
        expected_plan: str,
        expected_version: str | None,
        timeout_ms: int = 8_000,
    ) -> dict[str, Any]:
        """Wait until the selected plan/version exposes its server list.

        Price cards are deliberately not part of this gate. A stale region from
        the previous plan may have no price under the newly selected plan; the
        scraper must first enumerate and explicitly click the new plan's regions.
        """
        attempts = max(1, int(timeout_ms / 250))
        best: dict[str, Any] = {}
        for _ in range(attempts):
            state = self._current_purchase_state(page)
            if state:
                best = state
            if (
                self._matches_selection(state.get("active_plan"), expected_plan)
                and self._matches_selection(state.get("active_version"), expected_version)
                and bool(state.get("regions") or [])
            ):
                return state
            page.wait_for_timeout(250)
        return best if (
            self._matches_selection(best.get("active_plan"), expected_plan)
            and self._matches_selection(best.get("active_version"), expected_version)
            and bool(best.get("regions") or [])
        ) else {}

    def _entries(self, page: Page, selector: str, text_selector: str | None = None) -> list[dict[str, Any]]:
        try:
            result = page.evaluate(
                """
                ({selector, textSelector}) => {
                  const text = (node) => (node?.innerText || node?.textContent || '')
                    .replace(/\\s+/g, ' ').trim();
                  return Array.from(document.querySelectorAll(selector))
                    .map((node, index) => ({
                      index,
                      name: textSelector ? text(node.querySelector(textSelector)) || text(node) : text(node),
                      active: node.classList.contains('active-btn') ||
                        node.classList.contains('active') ||
                        node.classList.contains('van-tab--active') ||
                        node.getAttribute('aria-selected') === 'true'
                    }))
                    .filter((item) => item.name);
                }
                """,
                {"selector": selector, "textSelector": text_selector},
            )
            return result if isinstance(result, list) else []
        except Exception as exc:
            self.logger.debug("[%s] unable to enumerate %s: %s", self.platform, selector, exc)
            return []

    def _click_selector(self, page: Page, selector: str, index: int) -> bool:
        """Use a real Playwright click first; replay only native pointer events on fallback."""
        try:
            locator = page.locator(selector).nth(index)
            locator.scroll_into_view_if_needed(timeout=4_000)
            locator.click(timeout=5_000, force=True)
            return True
        except Exception as primary_exc:
            self.logger.debug("[%s] locator click failed (%s #%s): %s", self.platform, selector, index, primary_exc)
        try:
            return bool(
                page.evaluate(
                    """
                    ({selector, index}) => {
                      const node = Array.from(document.querySelectorAll(selector))[index];
                      if (!node) return false;
                      node.scrollIntoView({block: 'nearest', inline: 'center'});
                      for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup']) {
                        node.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
                      }
                      node.click();
                      return true;
                    }
                    """,
                    {"selector": selector, "index": index},
                )
            )
        except Exception as fallback_exc:
            self.logger.debug("[%s] fallback click failed (%s #%s): %s", self.platform, selector, index, fallback_exc)
            return False

    def _wait_for_rendered_state(
        self,
        page: Page,
        *,
        expected_plan: str | None = None,
        expected_version: str | None = None,
        expected_region: str | None = None,
        timeout_ms: int = 8_000,
        allow_empty_cards: bool = False,
        stable_frames_required: int = 2,
    ) -> dict[str, Any]:
        """Wait for a stable selected state, optionally accepting an empty price list.

        The old implementation slept for a fixed 650–700 ms.  On this site that
        often captured the old component tree while the encrypted response was
        still being decoded.  A stable pair of frames is a much safer boundary.
        For server-region transitions, ``allow_empty_cards`` distinguishes a
        confirmed no-offer state from a transition that never settled.
        """
        attempts = max(1, int(timeout_ms / 300))
        previous_signature: str | None = None
        stable_frames = 0
        best: dict[str, Any] = {}

        for _ in range(attempts):
            state = self._current_purchase_state(page)
            if state:
                best = state
            matches = (
                self._matches_selection(state.get("active_plan"), expected_plan)
                and self._matches_selection(state.get("active_version"), expected_version)
                and self._matches_selection(state.get("active_region"), expected_region)
            )
            cards = state.get("cards") or []
            state_is_acceptable = bool(cards) or allow_empty_cards
            if matches and state_is_acceptable:
                signature = self._state_signature(state)
                if signature == previous_signature:
                    stable_frames += 1
                else:
                    previous_signature = signature
                    stable_frames = 1
                if stable_frames >= max(1, int(stable_frames_required)):
                    return state
            else:
                previous_signature = None
                stable_frames = 0
            page.wait_for_timeout(300)

        return best if (
            (bool(best.get("cards") or []) or allow_empty_cards)
            and self._matches_selection(best.get("active_plan"), expected_plan)
            and self._matches_selection(best.get("active_version"), expected_version)
            and self._matches_selection(best.get("active_region"), expected_region)
        ) else {}

    def _current_purchase_state(self, page: Page) -> dict[str, Any]:
        try:
            snapshot = page.evaluate(
                """
                () => {
                  const text = (node) => (node?.innerText || node?.textContent || '')
                    .replace(/\\s+/g, ' ').trim();
                  const cleanRegion = (node) => {
                    if (!node) return '';
                    const clone = node.cloneNode(true);
                    clone.querySelectorAll('.room-ping').forEach((ping) => ping.remove());
                    return text(clone);
                  };
                  const activePlanNode = document.querySelector(
                    '.purchase-details-container .van-tab--active .config-name, ' +
                    '.purchase-details-container .active-tab-item .config-name, ' +
                    '.purchase-details-container [role="tab"][aria-selected="true"] .config-name'
                  );
                  const activePlan = text(activePlanNode);
                  const activeVersionNode = document.querySelector(
                    '.purchase-details-container .version-item.active-btn, .purchase-details-container .version-item.active'
                  );
                  const activeRegionNode = document.querySelector(
                    '.purchase-details-container .meal-data-item .room-item.active-btn, .purchase-details-container .meal-data-item .room-item.active'
                  );
                  const specs = {};
                  document.querySelectorAll('.purchase-details-container .network-config-item').forEach((node) => {
                    const label = text(node.querySelector('.text')).toLowerCase();
                    const value = text(node.querySelector('.value'));
                    if (label.includes('core') || label.includes('cpu')) specs.cpu = value;
                    else if (label.includes('android')) specs.android_version = value;
                    else if (label.includes('ram') || label.includes('memory')) specs.ram = value;
                    else if (label.includes('rom') || label.includes('storage')) specs.rom = value;
                  });
                  const versions = Array.from(document.querySelectorAll(
                    '.purchase-details-container .version-item'
                  )).map((node, index) => ({
                    index,
                    name: text(node),
                    active: node.classList.contains('active-btn') || node.classList.contains('active')
                  })).filter((item) => item.name);
                  const regions = Array.from(document.querySelectorAll(
                    '.purchase-details-container .meal-data-item .room-item'
                  )).map((node, index) => ({
                    index,
                    name: cleanRegion(node),
                    active: node.classList.contains('active-btn') || node.classList.contains('active')
                  })).filter((item) => item.name);
                  const cards = Array.from(document.querySelectorAll(
                    '.purchase-details-container .meal-data-item .price-box .price-item'
                  )).map((node, index) => ({
                    index,
                    duration: text(node.querySelector('.time-text')),
                    price: text(node.querySelector('.card-price-num')),
                    original_price: text(node.querySelector('.origin-price-num')),
                    promotion: text(node.querySelector('.discount-text')) || text(node.querySelector('.discount-half-off')),
                    active: node.classList.contains('active-card') || node.id === 'active-card',
                    unavailable: (() => {
                      const className = String(node.className || '').toLowerCase();
                      const textValue = text(node).toLowerCase();
                      return node.classList.contains('disabled') ||
                        node.classList.contains('sold-out') ||
                        node.classList.contains('is-disabled') ||
                        node.classList.contains('unavailable') ||
                        node.getAttribute('aria-disabled') === 'true' ||
                        Boolean(node.querySelector('[disabled], [aria-disabled="true"]')) ||
                        /sold\\s*out|out\\s*of\\s*stock|unavailable|not\\s*available|售罄|缺货|暂不可用/.test(className + ' ' + textValue);
                    })()
                  })).filter((item) => item.duration && item.price);
                  return {
                    active_plan: activePlan,
                    active_version: text(activeVersionNode),
                    active_region: cleanRegion(activeRegionNode),
                    specs,
                    versions,
                    regions,
                    cards
                  };
                }
                """
            )
            return snapshot if isinstance(snapshot, dict) else {}
        except Exception as exc:
            self.logger.debug("[%s] purchase state snapshot failed: %s", self.platform, exc)
            return {}

    def _records_from_api(
        self, source_url: str, screenshot_path: str | None, html_path: str | None
    ) -> List[ProductRecord]:
        # Native mealList responses are encrypted by the site and intentionally
        # not replayed or parsed outside the live client.
        return []

    def _records_from_dom(
        self,
        page: Page,
        source_url: str,
        screenshot_path: str | None,
        html_path: str | None,
        extraction_method: str = "dom",
    ) -> List[ProductRecord]:
        crawl_utc, crawl_local = now_pair(self.config.timezone)
        records: list[ProductRecord] = []
        for snapshot in self._dom_matrix_snapshots:
            specs = snapshot.get("specs") or {}
            plan = self._clean_plan_name(snapshot.get("active_plan"))
            version = str(snapshot.get("active_version") or "").strip()
            version_for_record = version
            if self._normal_key(version_for_record) in {"", "default", "na", "none", "unknown"}:
                version_for_record = str(specs.get("android_version") or "").strip()
            region = str(snapshot.get("active_region") or "").strip() or None
            if not plan or not region:
                continue
            purchase_mode = str(snapshot.get("purchase_mode") or "subscription").strip().lower()
            if purchase_mode not in {"subscription", "non_subscription"}:
                purchase_mode = "subscription"
            for card in snapshot.get("cards") or []:
                duration, billing_period = self._duration_from_text(card.get("duration"))
                price = self._price(card.get("price"))
                if not duration or not price:
                    continue
                raw = {"dom_matrix": snapshot, "card": card}
                records.append(
                    ProductRecord(
                        platform=self.platform,
                        source_url=source_url,
                        crawl_time_utc=crawl_utc,
                        crawl_time_local=crawl_local,
                        region_selected=region,
                        server_region=region,
                        currency=self._currency(card.get("price")) or "$",
                        product_category="cloud_phone",
                        product_name="Cloud Phone",
                        product_model=plan,
                        device_model=plan,
                        android_version=self._android_version(version_for_record),
                        cpu=self._cpu(specs.get("cpu")),
                        ram=self._gb(specs.get("ram")),
                        storage=self._gb(specs.get("rom")),
                        price=price,
                        original_price=self._price(card.get("original_price")),
                        billing_period=billing_period,
                        duration=duration,
                        purchase_mode=purchase_mode,
                        stock_status="unavailable" if card.get("unavailable") else "available",
                        promotion_text=card.get("promotion") or None,
                        raw_text=compact_text(json.dumps(raw, ensure_ascii=False, default=str), 4000),
                        extraction_method="dom_matrix",
                        confidence="high",
                        screenshot_path=screenshot_path,
                        html_path=html_path,
                        notes=(
                            "native_dom_matrix_synchronized; controlled_plan_android_server_purchase_mode_sweep; "
                            + ("subscription_price; " if purchase_mode == "subscription" else "non_subscription_price; ")
                            + (
                                "visible_price_card_unavailable"
                                if card.get("unavailable")
                                else "visible_price_card_available"
                            )
                        ),
                    )
                )
        return self._dedupe_records(records)

    def _safe_probe_interactions(self, page: Page, url: str) -> None:
        # The generic base probe could alter the final selected state after the
        # controlled sweep.  UgPhone uses only the explicitly bounded safe clicks.
        return None

    def _configs_from_api_candidates(self) -> list[dict[str, Any]]:
        configs: list[dict[str, Any]] = []
        for item in self.api_candidates:
            if "configlist2" not in (item.get("url") or "").lower():
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
                            "version_label": str(android.get("name") or ""),
                            "config_id": config_id,
                            "android_version": self._android_version(
                                cfg.get("android_version") or android.get("name")
                            ),
                            "cpu": cfg.get("cpu"),
                            "ram": cfg.get("ram"),
                            "rom": cfg.get("rom"),
                        }
                    )
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for cfg in configs:
            key = str(cfg.get("config_id") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(cfg)
        return out

    def _write_collection_summary(self) -> None:
        path = self.artifact_dir / "ugphone_collection_summary.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self.collection_summary, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            self.logger.warning("[%s] collection summary save failed: %s", self.platform, exc)

    def _write_partial_records(self, records: list[ProductRecord]) -> None:
        """Persist an empty-run diagnostic when no visible price card was collected."""
        path = self.artifact_dir / "ugphone_partial_records.json"
        try:
            rows = []
            for record in records:
                record.finalize()
                rows.append(record.as_dict())
            payload = {
                "platform": self.platform,
                "collection_status": "failed",
                "failure_reason": self.collection_summary.get("failure_reason"),
                "coverage": {
                    "plans": [
                        self.collection_summary.get("dom_matrix_plan_successes"),
                        self.collection_summary.get("dom_matrix_plan_targets"),
                    ],
                    "visible_variants": [
                        self.collection_summary.get("dom_matrix_variant_successes"),
                        self.collection_summary.get("dom_matrix_variant_targets"),
                    ],
                    "regions_with_prices": [
                        self.collection_summary.get("dom_matrix_region_snapshots"),
                        self.collection_summary.get("dom_matrix_region_targets"),
                    ],
                    "resolved_regions": [
                        self.collection_summary.get("dom_matrix_region_resolved"),
                        self.collection_summary.get("dom_matrix_region_targets"),
                    ],
                    "empty_region_cells": self.collection_summary.get("dom_matrix_empty_region_cells"),
                },
                "records": rows,
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            self.logger.warning("[%s] partial record save failed: %s", self.platform, exc)

    @classmethod
    def _matches_selection(cls, observed: Any, expected: Any) -> bool:
        if not expected:
            return True
        return cls._normal_key(observed) == cls._normal_key(expected)

    @staticmethod
    def _normal_key(value: Any) -> str:
        return re.sub(r"[\s🔥]+", "", str(value or "")).lower()

    @staticmethod
    def _state_signature(state: dict[str, Any]) -> str:
        cards = [
            (
                str(item.get("duration") or ""),
                str(item.get("price") or ""),
                str(item.get("original_price") or ""),
            )
            for item in (state.get("cards") or [])
        ]
        return json.dumps(
            {
                "plan": UGPhoneScraper._normal_key(state.get("active_plan")),
                "version": UGPhoneScraper._normal_key(state.get("active_version")),
                "region": UGPhoneScraper._normal_key(state.get("active_region")),
                "purchase_mode": str(state.get("purchase_mode") or ""),
                "cards": cards,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def _duration_from_text(value: Any) -> tuple[str | None, str | None]:
        text = str(value or "")
        match = re.search(
            r"(\d+(?:\.\d+)?)\s*(天|日|小时|小時|hour|hours|day|days|month|months|year|years)",
            text,
            re.I,
        )
        if not match:
            return None, None
        count, unit = match.group(1), match.group(2).lower()
        if unit in {"天", "日", "day", "days"}:
            return f"{count} day", "day"
        if unit in {"小时", "小時", "hour", "hours"}:
            return f"{count} hour", "hour"
        if unit in {"month", "months"}:
            return f"{count} month", "month"
        if unit in {"year", "years"}:
            return f"{count} year", "year"
        return f"{count} {unit}", unit

    @staticmethod
    def _clean_plan_name(value: Any) -> str | None:
        text = str(value or "").strip().replace("🔥", "").strip()
        return text or None

    @staticmethod
    def _android_version(value: Any) -> str | None:
        return canonical_android_version(value)

    @staticmethod
    def _cpu(value: Any) -> str | None:
        match = re.search(r"(\d+(?:\.\d+)?)", str(value or ""))
        if not match:
            return None
        return f"{float(match.group(1)):g} cores"

    @staticmethod
    def _gb(value: Any) -> str | None:
        match = re.search(r"(\d+(?:\.\d+)?)", str(value or ""))
        if not match:
            return None
        return f"{float(match.group(1)):g}GB"

    @staticmethod
    def _price(value: Any) -> str | None:
        match = re.search(r"(\d+(?:\.\d+)?)", str(value or "").replace(",", ""))
        return match.group(1) if match else None

    @staticmethod
    def _currency(value: Any) -> str | None:
        text = str(value or "").strip()
        match = re.search(r"([^\d\s.,-]+)", text)
        return match.group(1) if match else None
