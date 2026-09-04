from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dashboard_injects_ai_copilot_without_frontend_secret() -> None:
    main = (ROOT / "dashboard/src/main.jsx").read_text(encoding="utf-8")
    client = (ROOT / "dashboard/src/lib/aiClient.js").read_text(encoding="utf-8")
    component = (ROOT / "dashboard/src/components/AICopilot.jsx").read_text(encoding="utf-8")
    assert "<AICopilot />" in main
    assert "VITE_AI_API_BASE_URL" in client
    assert "AI_LLM_API_KEY" not in client
    assert "规则分析模式" in component
    assert "What-if" in component
    assert "Explain" in component


def test_ai_frontend_uses_static_context_as_public_fallback() -> None:
    client = (ROOT / "dashboard/src/lib/aiClient.js").read_text(encoding="utf-8")
    assert 'dashboard_data/ai/' in client
    assert "loadAIContext" in client
    assert "simulatePrice" in client
    assert 'schema_version !== "ai-context-v2"' in client
    assert "safe_data_only !== true" in client


def test_daily_updater_builds_ai_context_before_vite() -> None:
    updater = (ROOT / "deployment/windows/update_cloud_phone_dashboard.ps1").read_text(encoding="utf-8")
    ai_pos = updater.index("build_ai_context.py")
    build_pos = updater.index("npm run build")
    assert ai_pos < build_pos
    assert "dashboard_data\\ai\\manifest.json" in updater


def test_copilot_uses_linked_business_selectors_and_presentation_layer() -> None:
    component = (ROOT / "dashboard/src/components/AICopilot.jsx").read_text(encoding="utf-8")
    client = (ROOT / "dashboard/src/lib/aiClient.js").read_text(encoding="utf-8")
    presentation = (ROOT / "dashboard/src/lib/aiPresentation.js").read_text(encoding="utf-8")
    assert "ConfigurationSelector" in component
    assert "产品系列" in component
    assert "Android 版本" in component
    assert "硬件配置" in component
    assert "购买周期" in component
    assert "ConfigPicker" not in component
    assert "renderMarketBrief" in client
    assert "renderConfigExplanation" in client
    assert "renderWhatIfNarrative" in client
    assert "MARKET_POSITION_LABELS" in presentation
    assert "DATA_ORIGIN_LABELS" in presentation
    assert "isSelectableConfig" in component
    assert "filter((row) => Number(row.competitor_median_price) > 0)" not in component
    assert "有效购买周期" in component
    assert 'duration_price_comparison.json' in client
    assert "mergeDurationInventory" in client
    assert "refreshBackendContext" in client
    assert "falling back to local deterministic evidence" in client


def test_user_facing_templates_do_not_embed_old_machine_copy() -> None:
    component = (ROOT / "dashboard/src/components/AICopilot.jsx").read_text(encoding="utf-8")
    client = (ROOT / "dashboard/src/lib/aiClient.js").read_text(encoding="utf-8")
    assert "当前可比价格中：high" not in client
    assert "市场位置=${" not in client
    assert "数据来源=${" not in client
    assert "carry-forward 数据" not in component
    assert "What-if Result" not in component
    assert "旧位置" not in component
    assert "新位置" not in component


def test_copilot_renders_safe_markdown_without_raw_html() -> None:
    component = (ROOT / "dashboard/src/components/AICopilot.jsx").read_text(encoding="utf-8")
    assert "function MarkdownContent" in component
    assert "renderInlineMarkdown" in component
    assert "isTableSeparator" in component
    assert "<MarkdownContent>{payload.answer}</MarkdownContent>" in component
    assert "dangerouslySetInnerHTML" not in component


def test_ai_backend_autobuilds_local_context_from_dashboard_inventory() -> None:
    app = (ROOT / "ai_backend/app.py").read_text(encoding="utf-8")
    config = (ROOT / "ai_backend/config.py").read_text(encoding="utf-8")
    env_example = (ROOT / "ai.env.example").read_text(encoding="utf-8")
    assert "_auto_build_local_context" in app
    assert 'duration_price_comparison.json' in app
    assert "build_ai_context(data_dir, settings.context_dir)" in app
    assert "_auto_build_local_context()" in app
    assert "AI_AUTO_BUILD_CONTEXT" in config
    assert "AI_AUTO_BUILD_CONTEXT=1" in env_example


def test_verify_v2_refreshes_production_selector_inventory_when_runtime_data_exists() -> None:
    verifier = (ROOT / "VERIFY_V2.ps1").read_text(encoding="utf-8")
    policy = (ROOT / "tools/public_release_policy.py").read_text(encoding="utf-8")
    assert "Refreshing and validating production AI selector inventory" in verifier
    assert "verify_ai_selector_inventory.py" in verifier
    assert "verify_ai_selector_inventory.py" in policy
