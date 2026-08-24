import {
  dailyTables,
  latestRun,
  pairingSuggestions,
  platformCards,
  qualityRows,
  rationalityRows,
  relativeIndexData,
} from "../data/mockData.js";

const DASHBOARD_FILES = {
  frontendPriceOverview: "frontend_price_overview.json",
  pairingMatrix: "pairing_matrix.json",
  durationPriceComparison: "duration_price_comparison.json",
  priceTrends: "price_trends.json",
  priceChangeTracking: "price_change_tracking.json",
  productTextChanges: "product_text_changes.json",
  metricDefinitions: "metric_definitions.json",
  scheduleStatus: "schedule_status.json",
  meta: "meta.json",
};

const DATA_BASE_URL = new URL("./dashboard_data/", window.location.href).toString();

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return response.json();
}

async function loadStaticDashboardData() {
  const entries = await Promise.all(
    Object.entries(DASHBOARD_FILES).map(async ([key, file]) => [key, await fetchJson(`${DATA_BASE_URL}${file}?v=${Date.now()}`)]),
  );
  return Object.fromEntries(entries);
}

async function loadApiDashboardData() {
  return fetchJson("/api/dashboard");
}

function mockDashboardData() {
  const matrix = relativeIndexData.map((row, index) => {
    const median = row.index ? 100 / row.index * (10 + index * 2) : null;
    const ug = median ? (row.index / 100) * median : null;
    const position =
      row.index < 90 ? "below_market" : row.index <= 105 ? "competitive" : row.index <= 115 ? "slightly_high" : "high";
    return {
      ug_config_id: `mock_${row.tier}`,
      ug_config: `${row.tier} mock config`,
      duration_days: 30,
      ug_effective_price_30d: ug,
      competitor_median_quality_adjusted_price_30d: median,
      best_competitor: "VSPhone",
      best_competitor_adjusted_price: median ? median * 0.92 : null,
      worst_competitor: "Redfinger",
      relative_index: row.index,
      adjusted_gap_pct: row.index ? row.index / 100 - 1 : null,
      market_position_label: position,
      core_matches: row.core,
      weak_matches: row.weak,
      confidence_level: row.core >= 2 ? "high" : "medium",
      alert_level: position === "high" ? "critical" : position === "slightly_high" ? "warning" : "none",
      reason_code: position === "high" ? "abnormal_unexplained" : "unchanged",
      recommendation: position === "high" ? "需要复盘定价或促销策略。" : "价格健康，保持监测。",
    };
  });
  return {
    meta: { is_mock_data: true, source: "mockData.js", generated_at_utc: new Date().toISOString() },
    kpis: {},
    files: latestRun.outputFiles.map((file) => ({ ...file, exists: false, safe_to_open: true })),
    platformStatus: platformCards.map((row) => ({
      platform: row.platform,
      status: row.status,
      product_rows: row.productRows,
      baseline_rows: row.baselineRows,
      missing_vs_baseline: Math.max(row.baselineRows - row.productRows, 0),
    })),
    priceDecisionOverview: matrix.map((row) => ({
      ...row,
      ug_product_model: row.ug_config.split(" ")[0],
      ug_android_version: "10",
      ug_cpu: "8 cores",
      ug_ram: "8GB",
      ug_storage: "128GB",
      adjusted_price_gap: row.competitor_median_quality_adjusted_price_30d
        ? row.ug_effective_price_30d - row.competitor_median_quality_adjusted_price_30d
        : null,
      adjusted_price_gap_pct: row.adjusted_gap_pct,
      ugphone_relative_index: row.relative_index,
      market_position_label: row.market_position_label,
      pairing_coverage_score: 80,
      confidence_notes: "mock data",
      reason_explanation: "Mock explanation",
      best_competitor: { platform: row.best_competitor, quality_adjusted_price_30d: row.best_competitor_adjusted_price },
    })),
    ugConfigPriceMatrix: matrix,
    competitorBasket: pairingSuggestions.map((row) => ({
      ug_config_id: "mock_UVIP",
      ug_config: row.ug,
      duration_days: 30,
      competitor_platform: row.platform,
      competitor_product_model: row.competitor,
      competitor_config: row.competitor,
      raw_effective_price_30d: 10,
      quality_adjustment_factor: 0.95,
      quality_adjusted_price_30d: 9.5,
      config_similarity_score: row.score,
      comparability_level: row.level,
      included_in_core_median: ["strong_match", "adjusted_match"].includes(row.level),
      exclusion_reason: row.level === "weak_match" ? "weak_match_not_in_core_median" : "",
      pairing_source: row.source,
      pairing_notes: row.note,
    })),
    pairingEvidence: pairingSuggestions,
    qualityPriceDetails: qualityRows,
    relativeIndexSeries: {
      rows: relativeIndexData,
      market_position_distribution: [],
      alert_priority_board: matrix.filter((row) => row.alert_level !== "none"),
    },
    priceRationality: { rows: rationalityRows, reason_explanations: {} },
    dailyChanges: dailyTables,
    runSummaryView: latestRun,
    frontendPriceOverview: {
      updated_at: latestRun.generatedAt,
      baseline_config_count: 5,
      core_duration_buckets: [1, 3, 7, 15, 30, 60, 90, 180, 365],
      rows_compared: matrix.length,
      market_position_counts: { below_market: 1, competitive: 2, slightly_high: 1, high: 1 },
      above_market_count: 2,
      below_market_count: 1,
      attention_items: matrix,
    },
    pairingMatrix: [],
    durationPriceComparison: { core_buckets: [1, 3, 7, 15, 30, 60, 90, 180, 365], buckets: {}, other_rows: [] },
    priceTrends: [],
    priceChangeTracking: [],
    productTextChanges: [],
    metricDefinitions: [],
    scheduleStatus: {
      scheduler_enabled: false,
      scheduler_type: "manual",
      schedule_time_local: "10:00",
      last_run_time: latestRun.generatedAt,
      last_run_status: "success",
      next_run_time_estimated: null,
      last_run_duration_seconds: null,
      data_freshness_status: "unknown",
      stale_after_hours: 30,
      logs_path: "output/scheduler_logs",
    },
  };
}


export async function loadTrendDetailChunks(files = []) {
  const uniqueFiles = [...new Set(files.filter(Boolean))];
  const entries = await Promise.all(
    uniqueFiles.map(async (file) => {
      const normalized = String(file).replace(/^\/+/, "");
      const payload = await fetchJson(`${DATA_BASE_URL}${normalized}?v=${Date.now()}`);
      return [normalized, payload];
    }),
  );
  return Object.fromEntries(entries);
}

export async function loadDashboardData() {
  try {
    return { data: await loadStaticDashboardData(), source: "real_data", isMockData: false, error: null };
  } catch (staticError) {
    try {
      return { data: await loadApiDashboardData(), source: "local_api", isMockData: false, error: null };
    } catch (apiError) {
      return {
        data: mockDashboardData(),
        source: "mock_data",
        isMockData: true,
        error: `${staticError.message}; ${apiError.message}`,
      };
    }
  }
}
