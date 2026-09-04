import {
  renderConfigExplanation,
  renderConfigSummary,
  renderMarketBrief,
  renderPriceChange,
  renderWhatIfNarrative,
} from "./aiPresentation.js";

const RAW_API_BASE = String(import.meta.env.VITE_AI_API_BASE_URL || "").trim();
const API_BASE = RAW_API_BASE.replace(/\/+$/, "");
const DASHBOARD_DATA_BASE = new URL("./dashboard_data/", window.location.href).toString();
const LOCAL_BASE = new URL("./dashboard_data/ai/", window.location.href).toString();

async function fetchJson(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body?.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return response.json();
}

async function localAsset(name, fallback = null) {
  try {
    return await fetchJson(`${LOCAL_BASE}${name}?v=${Date.now()}`);
  } catch (error) {
    if (fallback !== null) return fallback;
    throw error;
  }
}

async function dashboardAsset(name, fallback = null) {
  try {
    return await fetchJson(`${DASHBOARD_DATA_BASE}${name}?v=${Date.now()}`);
  } catch (error) {
    if (fallback !== null) return fallback;
    throw error;
  }
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function durationInventoryRows(payload) {
  const rows = [];
  if (Array.isArray(payload)) rows.push(...payload);
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const buckets = payload.buckets;
    if (buckets && typeof buckets === "object") {
      Object.values(buckets).forEach((items) => {
        if (Array.isArray(items)) rows.push(...items);
      });
    }
    if (Array.isArray(payload.other_rows)) rows.push(...payload.other_rows);
  }
  return rows.filter((row) => row && typeof row === "object" && (row.ug_config_id || String(row.platform || "").toLowerCase() === "ugphone"));
}

function normalizeInventoryCompetitors(row) {
  const raw = row?.competitors;
  const values = raw && typeof raw === "object" && !Array.isArray(raw) ? Object.values(raw) : Array.isArray(raw) ? raw : [];
  return values.filter(Boolean).map((item) => ({
    config_id: row.ug_config_id || row.config_id || "",
    duration_days: finiteNumber(row.duration_days ?? row.duration_bucket ?? row.actual_duration_days),
    platform: item.platform || item.competitor_platform || "unknown",
    product_model: item.product_model || item.competitor_product_model || "",
    config: item.config || item.competitor_config || "",
    price: finiteNumber(item.quality_adjusted_price ?? item.quality_adjusted_price_30d ?? item.raw_effective_price_30d ?? item.current_price ?? item.price),
    similarity_score: finiteNumber(item.config_similarity_score),
    comparability_level: item.comparability_level || "unknown",
    included_in_core_median: Boolean(item.included_in_core_median),
    pairing_source: item.pairing_source || "",
    exclusion_reason: item.exclusion_reason || "",
  }));
}

function normalizeInventoryConfig(row) {
  const duration = finiteNumber(row.duration_days ?? row.duration_bucket ?? row.actual_duration_days);
  const configId = String(row.ug_config_id || row.config_id || row.canonical_product_key || row.id || "");
  if (!configId || !Number.isFinite(duration) || duration <= 0) return null;
  const competitors = normalizeInventoryCompetitors(row);
  const corePrices = competitors.filter((item) => item.included_in_core_median && Number.isFinite(item.price)).map((item) => item.price).sort((a, b) => a - b);
  let derivedMedian = null;
  if (corePrices.length) {
    const middle = Math.floor(corePrices.length / 2);
    derivedMedian = corePrices.length % 2 ? corePrices[middle] : (corePrices[middle - 1] + corePrices[middle]) / 2;
  }
  const median = finiteNumber(row.competitor_median_price ?? row.competitor_median_quality_adjusted_price ?? row.competitor_median_quality_adjusted_price_30d) ?? derivedMedian;
  const ugPrice = finiteNumber(row.ugphone_price ?? row.ug_effective_price ?? row.ug_effective_price_30d ?? row.current_price);
  const relativeIndex = finiteNumber(row.ugphone_relative_index ?? row.relative_index) ?? (Number.isFinite(ugPrice) && Number.isFinite(median) && median !== 0 ? (ugPrice / median) * 100 : null);
  const productModel = String(row.ug_product_model || row.product_model || "");
  const android = String(row.ug_android_version || row.android_version || "");
  const cpu = String(row.ug_cpu || row.cpu || "");
  const ram = String(row.ug_ram || row.ram || "");
  const storage = String(row.ug_storage || row.storage || "");
  const label = String(row.ug_config || row.config || [productModel, android ? `Android ${android}` : "", cpu, ram, storage].filter(Boolean).join(" / "));
  return {
    config_id: configId,
    label,
    product_model: productModel,
    android_version: android,
    cpu,
    ram,
    storage,
    duration_days: duration,
    ugphone_price: ugPrice,
    competitor_median_price: median,
    relative_index: relativeIndex,
    market_position: row.market_position_label || row.market_position || positionFromIndex(relativeIndex),
    confidence_level: row.confidence_level || "unknown",
    analysis_status: row.analysis_status || "unknown",
    data_origin: row.data_origin || row.price_source || row.ugphone_price_source || "unknown",
    availability_status: row.availability_status || "unknown",
    analysis_note: row.analysis_note || row.confidence_notes || "",
    exclude_from_market_position: Boolean(row.exclude_from_market_position),
    competitors,
    source_inventory: "duration_price_comparison.json",
  };
}

function mergeDurationInventory(configs, pairings, payload) {
  const mergedConfigs = new Map();
  (configs || []).forEach((row) => mergedConfigs.set(`${row?.config_id || ""}@@${finiteNumber(row?.duration_days) ?? ""}`, row));
  const inventoryRows = durationInventoryRows(payload);
  inventoryRows.forEach((raw) => {
    const row = normalizeInventoryConfig(raw);
    if (!row) return;
    const key = `${row.config_id}@@${row.duration_days}`;
    const existing = mergedConfigs.get(key);
    if (!existing) {
      mergedConfigs.set(key, row);
      return;
    }
    const merged = { ...row, ...existing };
    ["ugphone_price", "competitor_median_price", "relative_index"].forEach((field) => {
      if (!Number.isFinite(finiteNumber(existing[field])) && Number.isFinite(finiteNumber(row[field]))) merged[field] = row[field];
    });
    if ((!existing.competitors || !existing.competitors.length) && row.competitors.length) merged.competitors = row.competitors;
    mergedConfigs.set(key, merged);
  });

  const mergedPairings = new Map();
  (pairings || []).forEach((row) => mergedPairings.set(`${row?.config_id || ""}@@${finiteNumber(row?.duration_days) ?? ""}@@${row?.platform || ""}@@${row?.config || ""}`, row));
  inventoryRows.forEach((raw) => {
    normalizeInventoryCompetitors(raw).forEach((row) => {
      const key = `${row.config_id}@@${row.duration_days ?? ""}@@${row.platform || ""}@@${row.config || ""}`;
      if (!mergedPairings.has(key)) mergedPairings.set(key, row);
    });
  });

  const configRows = [...mergedConfigs.values()].sort((a, b) =>
    String(a.product_model || "").localeCompare(String(b.product_model || ""))
    || Number(a.android_version || 0) - Number(b.android_version || 0)
    || String(a.cpu || "").localeCompare(String(b.cpu || ""))
    || String(a.ram || "").localeCompare(String(b.ram || ""))
    || String(a.storage || "").localeCompare(String(b.storage || ""))
    || Number(a.duration_days || 0) - Number(b.duration_days || 0)
  );
  return { configs: configRows, pairings: [...mergedPairings.values()] };
}

function positionFromIndex(index, manifest = null) {
  if (!Number.isFinite(index)) return "unknown";
  const thresholds = manifest?.market_position_thresholds || {};
  const belowMarketLt = Number(thresholds.below_market_lt ?? 90);
  const competitiveLte = Number(thresholds.competitive_lte ?? 105);
  const slightlyHighLte = Number(thresholds.slightly_high_lte ?? 115);
  if (index < belowMarketLt) return "below_market";
  if (index <= competitiveLte) return "competitive";
  if (index <= slightlyHighLte) return "slightly_high";
  return "high";
}

function evidence(sourceFile, row, field, value, note = "", number = 1) {
  return {
    evidence_id: `E${number}`,
    fact_id: row?.fact_id || "",
    source_file: sourceFile,
    record_id: row?.config_id || row?.field || row?.fact_id || "",
    field,
    value,
    note,
  };
}

export function aiMode() {
  return API_BASE ? "llm_backend" : "evidence_mode";
}

async function refreshBackendContext() {
  if (!API_BASE) return null;
  try {
    return await fetchJson(`${API_BASE}/api/ai/refresh`, { method: "POST" });
  } catch (error) {
    console.warn("AI backend context refresh failed; local evidence context remains available.", error);
    return null;
  }
}

export async function loadAIContext() {
  await refreshBackendContext();
  const [manifest, summary, configs, changes, pairings, trends, metrics, examples, durationInventory] = await Promise.all([
    localAsset("manifest.json"),
    localAsset("market_summary.json"),
    localAsset("config_index.json"),
    localAsset("price_events.json", []),
    localAsset("pairing_index.json", []),
    localAsset("trend_index.json", []),
    localAsset("metric_dictionary.json", []),
    localAsset("question_examples.json", []),
    dashboardAsset("duration_price_comparison.json", {}),
  ]);
  if (manifest?.schema_version !== "ai-context-v2") throw new Error(`Unsupported AI context schema: ${manifest?.schema_version || "missing"}`);
  if (manifest?.safe_data_only !== true) throw new Error("AI context is not marked safe_data_only=true");
  // The selector must never inherit a stale/sparse AI index.  Reconcile it at
  // runtime against the canonical Dashboard duration inventory as a second
  // safety net.  The backend independently auto-refreshes its local context.
  const merged = mergeDurationInventory(configs, pairings, durationInventory);
  return { manifest, summary, configs: merged.configs, changes, pairings: merged.pairings, trends, metrics, examples, durationInventory };
}

export async function getMarketBrief(context = null) {
  if (API_BASE) return fetchJson(`${API_BASE}/api/ai/brief`);
  const ctx = context || await loadAIContext();
  const counts = ctx.summary?.market_position_counts || {};
  const top = ctx.summary?.top_attention?.[0];
  return {
    answer: renderMarketBrief(ctx.summary || {}),
    mode: "evidence",
    intent: "get_market_overview",
    confidence: "high",
    tool_calls: ["get_market_overview"],
    evidence: [
      evidence("market_summary.json", { config_id: "market" }, "market_position_counts", counts, "结构化市场统计", 1),
      ...(top ? [evidence("market_summary.json", top, "relative_index", top.relative_index, top.label, 2)] : []),
    ],
    data_date: ctx.manifest?.data_date || "unknown",
    data_revision: ctx.manifest?.data_revision || "unknown",
  };
}

function parseDuration(question) {
  const match = String(question).match(/(\d+(?:\.\d+)?)\s*(?:天|day|days|d)/i);
  return match ? Number(match[1]) : null;
}

function findModel(question) {
  const match = String(question).match(/\b(UVIP|GVIP|KVIP|MVIP|SVIP|XVIP)\b/i);
  return match?.[1]?.toUpperCase() || "";
}

function localAsk(context, question) {
  const low = String(question).toLowerCase();
  const duration = parseDuration(question);
  const model = findModel(question);

  if (["市场", "概览", "整体", "summary", "brief"].some((key) => low.includes(key)) && !model) {
    return getMarketBrief(context);
  }

  if (["涨价", "降价", "价格变化", "price change", "increase", "decrease"].some((key) => low.includes(key))) {
    const direction = low.includes("降") || low.includes("decrease") ? -1 : low.includes("涨") || low.includes("increase") ? 1 : 0;
    const rows = [...(context.changes || [])]
      .filter((row) => {
        const pct = Number(row.price_change_pct);
        if (!Number.isFinite(pct)) return false;
        return direction === 0 || Math.sign(pct) === direction;
      })
      .sort((a, b) => Math.abs(Number(b.price_change_pct || 0)) - Math.abs(Number(a.price_change_pct || 0)))
      .slice(0, 5);
    if (!rows.length) {
      return { answer: "当前数据中没有符合条件的价格变化记录。", mode: "evidence", intent: "get_price_changes", confidence: "low", tool_calls: ["get_price_changes"], evidence: [] };
    }
    const row = rows[0];
    return {
      answer: renderPriceChange(row),
      mode: "evidence",
      intent: "get_price_changes",
      confidence: "high",
      tool_calls: ["get_price_changes"],
      evidence: rows.map((item, index) => evidence("price_events.json", item, "price_change_pct", item.price_change_pct, item.platform, index + 1)),
      data_date: context.manifest?.data_date,
      data_revision: context.manifest?.data_revision,
    };
  }

  if (["怎么计算", "指标", "relative index", "相对竞品指数", "相似度", "formula"].some((key) => low.includes(key))) {
    const metric = (context.metrics || []).find((row) => {
      const haystack = Object.values(row || {}).join(" ").toLowerCase();
      return (low.includes("相似度") && haystack.includes("相似度")) || haystack.includes("ugphone_relative_index");
    });
    if (metric) {
      return {
        answer: `${metric.name_zh || metric.field}：${metric.meaning || ""} 计算方法：${metric.calculation || ""}`,
        mode: "evidence",
        intent: "get_metric_definition",
        confidence: "high",
        tool_calls: ["get_metric_definition"],
        evidence: [evidence("metric_dictionary.json", metric, "definition", metric.meaning, metric.calculation, 1)],
        data_date: context.manifest?.data_date,
        data_revision: context.manifest?.data_revision,
      };
    }
  }

  let rows = context.configs || [];
  if (model) rows = rows.filter((row) => String(row.product_model || "").toUpperCase() === model);
  if (duration !== null) rows = rows.filter((row) => Number(row.duration_days) === duration);
  rows = rows.slice(0, 8);
  if (!rows.length) {
    return {
      answer: "没有在当前结构化数据中找到匹配配置。为避免误导，我不会根据不存在的数据猜测价格。",
      mode: "evidence",
      intent: "abstain",
      confidence: "high",
      tool_calls: ["search_configs"],
      evidence: [],
      data_date: context.manifest?.data_date,
      data_revision: context.manifest?.data_revision,
    };
  }
  const row = rows[0];

  if (["为什么", "解释", "why", "证据", "可比"].some((key) => low.includes(key))) {
    const pairings = (context.pairings || []).filter((item) => String(item.config_id) === String(row.config_id) && (duration === null || Number(item.duration_days) === duration));
    return {
      answer: renderConfigExplanation(row, pairings),
      mode: "evidence",
      intent: "explain_configuration",
      confidence: "high",
      tool_calls: ["search_configs", "compare_configuration", "get_pairing_evidence"],
      evidence: [
        evidence("config_index.json", row, "relative_index", row.relative_index, `origin=${row.data_origin}`, 1),
        ...pairings.slice(0, 6).map((item, index) => evidence("pairing_index.json", item, "comparability_level", item.comparability_level, `${item.platform}; price=${item.price}`, index + 2)),
      ],
      data_date: context.manifest?.data_date,
      data_revision: context.manifest?.data_revision,
    };
  }

  if (["趋势", "历史", "trend", "history"].some((key) => low.includes(key))) {
    const trendRows = (context.trends || []).filter((item) => String(item.config_id) === String(row.config_id) && (duration === null || Number(item.duration_days) === duration));
    if (trendRows.length) {
      return {
        answer: `已找到 ${row.label}（${row.duration_days ?? "-"}天）的历史价格序列。具体时间点可在“查看依据”中核对。`,
        mode: "evidence",
        intent: "get_price_history",
        confidence: "high",
        tool_calls: ["search_configs", "get_price_history"],
        evidence: trendRows.slice(0, 5).map((item, index) => evidence("trend_index.json", item, "points", item.points, `history for ${item.config_id}`, index + 1)),
        data_date: context.manifest?.data_date,
        data_revision: context.manifest?.data_revision,
      };
    }
  }

  return {
    answer: renderConfigSummary(row),
    mode: "evidence",
    intent: "search_configs",
    confidence: "high",
    tool_calls: ["search_configs"],
    evidence: rows.map((item, index) => evidence("config_index.json", item, "relative_index", item.relative_index, `${item.label}; origin=${item.data_origin}`, index + 1)),
    data_date: context.manifest?.data_date,
    data_revision: context.manifest?.data_revision,
  };
}

export async function askPricingCopilot(question, context = null) {
  if (API_BASE) {
    return fetchJson(`${API_BASE}/api/ai/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  }
  const ctx = context || await loadAIContext();
  return localAsk(ctx, question);
}

export async function explainConfig(configId, durationDays = null, context = null) {
  if (API_BASE) {
    try {
      return await fetchJson(`${API_BASE}/api/ai/explain`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config_id: configId, duration_days: durationDays === null ? null : Number(durationDays) }),
      });
    } catch (error) {
      if (!context) throw error;
      console.warn("AI backend explain missed the selected duration; falling back to local deterministic evidence.", error);
    }
  }
  const ctx = context || await loadAIContext();
  const row = (ctx.configs || []).find((item) => String(item.config_id) === String(configId) && (durationDays === null || Number(item.duration_days) === Number(durationDays)));
  if (!row) throw new Error("Configuration not found");
  const pairings = (ctx.pairings || []).filter((item) => String(item.config_id) === String(configId) && (durationDays === null || Number(item.duration_days) === Number(durationDays)));
  return {
    answer: renderConfigExplanation(row, pairings),
    mode: "evidence",
    intent: "explain_configuration",
    confidence: "high",
    tool_calls: ["compare_configuration", "get_pairing_evidence"],
    evidence: [
      evidence("config_index.json", row, "relative_index", row.relative_index, `origin=${row.data_origin}`, 1),
      ...pairings.slice(0, 6).map((item, index) => evidence("pairing_index.json", item, "comparability_level", item.comparability_level, `${item.platform}; price=${item.price}`, index + 2)),
    ],
    data_date: ctx.manifest?.data_date,
    data_revision: ctx.manifest?.data_revision,
  };
}

export async function simulatePrice(configId, proposedPrice, durationDays = null, context = null) {
  if (API_BASE) {
    try {
      return await fetchJson(`${API_BASE}/api/ai/what-if`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config_id: configId, duration_days: durationDays === null ? null : Number(durationDays), proposed_price: Number(proposedPrice) }),
      });
    } catch (error) {
      if (!context) throw error;
      console.warn("AI backend what-if missed the selected duration; falling back to local deterministic evidence.", error);
    }
  }
  const ctx = context || await loadAIContext();
  const row = (ctx.configs || []).find((item) => String(item.config_id) === String(configId) && (durationDays === null || Number(item.duration_days) === Number(durationDays)));
  if (!row) throw new Error("Configuration not found");
  const median = Number(row.competitor_median_price);
  const price = Number(proposedPrice);
  const current = Number(row.ugphone_price);
  const newIndex = Number.isFinite(median) && median > 0 ? price / median * 100 : null;
  const competitiveLte = Number(ctx.manifest?.market_position_thresholds?.competitive_lte ?? 105);
  const result = {
    config_id: configId,
    proposed_price: price,
    competitor_median_price: Number.isFinite(median) ? median : null,
    old_relative_index: row.relative_index,
    new_relative_index: newIndex,
    old_market_position: row.market_position || positionFromIndex(Number(row.relative_index), ctx.manifest),
    new_market_position: positionFromIndex(newIndex, ctx.manifest),
    price_to_competitive_ceiling: Number.isFinite(median) ? median * competitiveLte / 100 : null,
    price_change_from_current_pct: Number.isFinite(current) && current !== 0 ? price / current - 1 : null,
    evidence: [
      evidence("config_index.json", row, "competitor_median_price", row.competitor_median_price, row.label, 1),
      evidence("config_index.json", row, "ugphone_price", row.ugphone_price, `origin=${row.data_origin}`, 2),
    ],
    data_date: ctx.manifest?.data_date,
    data_revision: ctx.manifest?.data_revision,
  };
  return { ...result, answer: renderWhatIfNarrative(result) };
}
