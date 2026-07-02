export const latestRun = {
  outputDir: "output/cloud_phone_monitor_20260430_024453",
  generatedAt: "2026-04-30 10:49:58 Asia/Shanghai",
  status: "success",
  currencies: ["$", "US$"],
  recordsByPlatform: {
    UgPhone: 301,
    VSPhone: 2028,
    Redfinger: 173,
    LDCloud: 464,
  },
  aggregatedRowsByPlatform: {
    UgPhone: 107,
    VSPhone: 169,
    Redfinger: 49,
    LDCloud: 161,
  },
  baselineRowsByPlatform: {
    UgPhone: 107,
    VSPhone: 169,
    Redfinger: 70,
    LDCloud: 175,
  },
  platformSessionStatus: {
    VSPhone: "saved session applied",
    Redfinger: "saved session applied",
  },
  internalPages: {},
  baselineMonitor: {
    baselineFound: true,
    updatedBaselinePriceRows: 433,
    comparisonRows: 431,
    alertRows: 232,
    ugConfigComparisonRows: 35,
    priceDownRows: 0,
  },
  qualityPriceMonitor: {
    enabled: true,
    inputBasis: "baseline_with_current_overlay",
    ugConfigCount: 70,
    pairingRows: 963,
    qualityAdjustedRows: 963,
    relativeIndexRows: 70,
    criticalAlerts: 30,
    warningAlerts: 194,
    notComparableRows: 6,
    fallbackBaselineRows: 88,
  },
  outputFiles: [
    { name: "products.xlsx", path: "output/cloud_phone_monitor_20260430_024453/products.xlsx", type: "collection" },
    { name: "daily_changes.xlsx", path: "output/cloud_phone_monitor_20260430_024453/daily_changes.xlsx", type: "monitor" },
    {
      name: "baseline_products_updated.xlsx",
      path: "output/cloud_phone_monitor_20260430_024453/baseline_products_updated.xlsx",
      type: "baseline",
    },
    {
      name: "quality_price_report.xlsx",
      path: "output/cloud_phone_monitor_20260430_024453/quality_price_report.xlsx",
      type: "quality",
    },
    { name: "run_summary.json", path: "output/cloud_phone_monitor_20260430_024453/run_summary.json", type: "summary" },
  ],
};

export const platformCards = [
  { platform: "UgPhone", status: "ok", sourceRows: 301, productRows: 107, baselineRows: 107, trend: [18, 19, 18, 20, 21, 20] },
  { platform: "VSPhone", status: "ok", sourceRows: 2028, productRows: 169, baselineRows: 169, trend: [28, 31, 29, 34, 33, 36] },
  { platform: "Redfinger", status: "ok", sourceRows: 173, productRows: 49, baselineRows: 70, trend: [12, 19, 15, 17, 16, 14] },
  { platform: "LDCloud", status: "ok", sourceRows: 464, productRows: 161, baselineRows: 175, trend: [21, 22, 24, 23, 22, 23] },
];

export const pairingSuggestions = [
  {
    ug: "UgPhone UVIP / Android 10 / 3C / 3GB / 30GB",
    competitor: "LDCloud VIP10/VIP12",
    platform: "LDCloud",
    score: 86,
    level: "adjusted_match",
    source: "manual_mapping",
    note: "Best nearby tier; storage is higher than UG.",
  },
  {
    ug: "UgPhone MVIP / Android 10 / 8C / 8GB / 128GB",
    competitor: "VSPhone XVIP",
    platform: "VSPhone",
    score: 94,
    level: "strong_match",
    source: "manual_mapping",
    note: "Strong pairing for core price judgement.",
  },
  {
    ug: "UgPhone SVIP / Android 12 / 8C / 16GB / 200GB",
    competitor: "Redfinger XVIP",
    platform: "Redfinger",
    score: 91,
    level: "strong_match",
    source: "manual_mapping",
    note: "Storage above UG; quality adjustment lowers competitor price.",
  },
  {
    ug: "UgPhone GVIP / 4C / 4GB / 64GB",
    competitor: "VSPhone KVIP",
    platform: "VSPhone",
    score: 71,
    level: "weak_match",
    source: "manual_mapping",
    note: "CPU is materially higher than UG; context only.",
  },
];

export const qualityRows = [
  { tier: "UG MVIP vs VSPhone XVIP", base: 18.9, factor: 1.0, adjusted: 18.9, delta: -0.6, level: "strong_match" },
  { tier: "UG SVIP vs Redfinger XVIP", base: 28.7, factor: 0.88, adjusted: 25.26, delta: 1.4, level: "strong_match" },
  { tier: "UG UVIP vs LDCloud VIP10", base: 7.4, factor: 1.12, adjusted: 8.29, delta: 0.8, level: "adjusted_match" },
  { tier: "UG GVIP vs VSPhone KVIP", base: 11.2, factor: 0.83, adjusted: 9.3, delta: 2.1, level: "weak_match" },
];

export const relativeIndexData = [
  { tier: "UVIP", index: 88, core: 12, weak: 3 },
  { tier: "GVIP", index: 97, core: 14, weak: 2 },
  { tier: "KVIP", index: 104, core: 16, weak: 1 },
  { tier: "MVIP", index: 112, core: 15, weak: 0 },
  { tier: "SVIP", index: 118, core: 13, weak: 0 },
];

export const rationalityRows = [
  { item: "UgPhone SVIP / 30 day", reason: "abnormal_unexplained", alert: "critical", detail: "relative index above 115" },
  { item: "Redfinger missing current rows", reason: "current_missing_used_baseline", alert: "warning", detail: "baseline fallback used" },
  { item: "LDCloud duration mix", reason: "duration_structure_change", alert: "warning", detail: "current duration coverage changed" },
  { item: "Promotion copy changed", reason: "promo_change", alert: "info", detail: "promotion_text changed" },
];

export const dailyTables = [
  { sheet: "汇总", rows: 4, description: "Platform-level baseline comparison summary." },
  { sheet: "变化明细", rows: 232, description: "Rows with price, availability, or promotion changes." },
  { sheet: "UG同配置价格对比", rows: 35, description: "Exact CPU/RAM/storage/duration comparison retained for compatibility." },
  { sheet: "UG相近配置价格对比", rows: 963, description: "Nearby configuration comparison using similarity and quality adjustment." },
];
