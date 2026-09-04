export const MARKET_POSITION_LABELS = {
  high: "明显高于市场",
  slightly_high: "略高于市场",
  competitive: "与市场基本持平",
  below_market: "低于市场",
  excluded: "暂不纳入市场比较",
  unknown: "暂无法判断",
};

export const DATA_ORIGIN_LABELS = {
  current_observed: "本次已采集",
  carry_forward: "沿用最近一次有效价格",
  carry_forward_last_observed: "沿用最近一次有效价格",
  subscription_mode_unavailable: "当前暂无该计费方式报价",
  missing_collection: "本次未采集到",
  unknown: "数据状态待确认",
};

export const COMPARABILITY_LABELS = {
  strong_match: "高可比配置",
  adjusted_match: "近似可比配置",
  weak_match: "可比性较弱",
  unknown: "可比性待确认",
};

export const TOOL_LABELS = {
  get_market_overview: "市场概览",
  search_configs: "配置检索",
  compare_configuration: "配置价格比较",
  get_pairing_evidence: "竞品可比依据",
  get_price_changes: "价格变化",
  get_price_history: "价格趋势",
  get_metric_definition: "指标说明",
  simulate_price: "定价模拟",
};

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function cleanNumber(value, digits = 2) {
  return Number(value).toFixed(digits).replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1");
}

export function formatPrice(value) {
  const number = numberOrNull(value);
  return number === null ? "暂无" : cleanNumber(number, 3);
}

export function formatIndex(value) {
  const number = numberOrNull(value);
  return number === null ? "暂无" : cleanNumber(number, 1);
}

export function formatPercentRatio(value, { signed = true } = {}) {
  const number = numberOrNull(value);
  if (number === null) return "暂无";
  const pct = number * 100;
  const prefix = signed && pct > 0 ? "+" : "";
  return `${prefix}${cleanNumber(pct, 1)}%`;
}

export function durationLabel(value) {
  const number = numberOrNull(value);
  if (number === null) return "购买周期未标注";
  if (Math.abs(number - Math.round(number)) < 1e-9) return `${Math.round(number)}天`;
  return `${cleanNumber(number, 3)}天`;
}

export function marketPositionLabel(value) {
  return MARKET_POSITION_LABELS[String(value || "unknown")] || MARKET_POSITION_LABELS.unknown;
}

export function dataOriginLabel(value) {
  return DATA_ORIGIN_LABELS[String(value || "unknown")] || DATA_ORIGIN_LABELS.unknown;
}

export function comparabilityLabel(value) {
  return COMPARABILITY_LABELS[String(value || "unknown")] || COMPARABILITY_LABELS.unknown;
}

export function toolLabel(value) {
  return TOOL_LABELS[String(value || "")] || "分析工具";
}

export function modeLabel(value) {
  if (value === "llm" || value === "llm_backend") return "AI增强";
  if (value === "evidence" || value === "evidence_mode") return "规则分析";
  return "分析结果";
}

export function dataCaveat(row = {}) {
  const origin = String(row.data_origin || row.analysis_status || row.price_source || "unknown");
  if (["carry_forward", "carry_forward_last_observed"].includes(origin)) {
    return "本次未采集到该报价，当前展示的是最近一次有效采集价格；建议等待下一次真实采集后再做高风险调价决策。";
  }
  if (origin === "subscription_mode_unavailable") {
    return "当前未获得该计费方式的有效报价，因此不应把该状态当作零价或正常在售价格。";
  }
  if (origin === "missing_collection") {
    return "本次采集未获得该报价，当前信息不足以支持新的价格判断。";
  }
  if (origin === "current_observed") {
    return "该价格来自本次有效采集，可作为当前市场比较的直接依据。";
  }
  if (String(row.analysis_note || "").trim()) return String(row.analysis_note).trim();
  return "当前数据状态未完全确认，建议结合证据明细判断。";
}

export function relativeDifferenceText(index) {
  const number = numberOrNull(index);
  if (number === null) return "与市场中位水平的差异暂无法计算";
  const delta = number - 100;
  if (Math.abs(delta) < 0.05) return "与可比竞品中位水平基本一致";
  if (delta > 0) return `约高出可比竞品中位水平 ${cleanNumber(delta, 1)}%`;
  return `约低于可比竞品中位水平 ${cleanNumber(Math.abs(delta), 1)}%`;
}

function configName(row = {}) {
  if (String(row.label || "").trim()) return String(row.label).trim();
  return [
    row.product_model,
    row.android_version ? `Android ${row.android_version}` : "",
    row.cpu,
    row.ram,
    row.storage,
  ].filter(Boolean).join(" / ") || "当前配置";
}

export function renderMarketBrief(summary = {}) {
  const counts = summary.market_position_counts || {};
  const high = Number(counts.high || 0);
  const slightlyHigh = Number(counts.slightly_high || 0);
  const competitive = Number(counts.competitive || 0);
  const below = Number(counts.below_market || 0);
  const above = high + slightlyHigh;
  const rows = Number(summary.rows_compared || (above + competitive + below));

  let overview = "当前没有足够的可比价格组合，暂时无法形成可靠的整体市场判断。";
  if (rows > 0) {
    overview = `当前共有 ${rows} 个可比价格组合：${above} 个高于市场水平（其中 ${high} 个明显偏高、${slightlyHigh} 个略高），${competitive} 个与市场基本持平，${below} 个低于市场。`;
    if (below > above) overview += " 整体分布更偏向低于市场的一侧，但不同产品与购买周期之间仍存在明显分化。";
    else if (above > below) overview += " 整体分布更偏向高于市场的一侧，建议优先检查高价配置。";
    else overview += " 高于与低于市场的配置数量接近，整体呈分化状态。";
  }

  const top = (summary.top_attention || [])[0];
  let focus = "暂未发现需要优先处理的高价配置。";
  let caveat = "当前简报仅使用已进入可比价格体系的数据。";
  if (top) {
    focus = `优先关注 ${configName(top)}（${durationLabel(top.duration_days)}）。当前价格 ${formatPrice(top.ugphone_price)}，可比竞品中位价 ${formatPrice(top.competitor_median_price)}，${relativeDifferenceText(top.relative_index)}，因此当前判断为“${marketPositionLabel(top.market_position)}”。`;
    caveat = dataCaveat(top);
  }

  let recommendation = "建议先补充有效采集和可比配置，再进行定价判断。";
  if (above > 0) recommendation = "建议先查看明显高于或略高于市场的配置，再结合购买周期、配置可比度和最新采集状态判断是否需要调价。";
  else if (rows > 0) recommendation = "当前没有明显的高价集中风险；可以继续观察价格变化，并结合促销策略判断低于市场的配置是否符合预期。";

  return `市场概况\n${overview}\n\n重点关注\n${focus}\n\n数据提示\n${caveat}\n\n建议\n${recommendation}`;
}

export function renderPriceChange(row = {}) {
  const subject = `${row.platform || "该平台"} ${row.product_model || ""}`.trim();
  const pct = numberOrNull(row.price_change_pct);
  let movement = "发生了价格变化";
  if (pct !== null && pct > 0) movement = `上涨 ${formatPercentRatio(Math.abs(pct), { signed: false })}`;
  else if (pct !== null && pct < 0) movement = `下降 ${formatPercentRatio(Math.abs(pct), { signed: false })}`;
  else if (pct === 0) movement = "价格与上次一致";
  return `变化最明显的是 ${subject}：价格由 ${formatPrice(row.previous_price)} 变为 ${formatPrice(row.current_price)}，${movement}。${dataCaveat({ data_origin: row.price_source })}`;
}

export function renderConfigSummary(row = {}) {
  return `${configName(row)}（${durationLabel(row.duration_days)}）当前价格为 ${formatPrice(row.ugphone_price)}，可比竞品中位价为 ${formatPrice(row.competitor_median_price)}；${relativeDifferenceText(row.relative_index)}，当前处于“${marketPositionLabel(row.market_position)}”区间。 ${dataCaveat(row)}`;
}

function pairingSentence(pairings = []) {
  const included = [];
  const excluded = [];
  pairings.forEach((item) => {
    const text = `${item.platform || "竞品"} ${formatPrice(item.price)}（${comparabilityLabel(item.comparability_level)}）`;
    if (item.included_in_core_median === false) excluded.push(text);
    else included.push(text);
  });
  const pieces = [];
  if (included.length) pieces.push(`纳入核心比较的竞品包括 ${included.slice(0, 4).join("、")}。`);
  if (excluded.length) pieces.push(`另有 ${excluded.slice(0, 3).join("、")} 未进入核心中位价计算。`);
  return pieces.join("") || "当前没有足够的竞品配对记录可供解释。";
}

export function renderConfigExplanation(row = {}, pairings = []) {
  const position = marketPositionLabel(row.market_position);
  return `为什么是“${position}”\n${configName(row)}（${durationLabel(row.duration_days)}）当前价格为 ${formatPrice(row.ugphone_price)}，可比竞品中位价约为 ${formatPrice(row.competitor_median_price)}，${relativeDifferenceText(row.relative_index)}。因此，按照当前价格区间规则，该配置被判断为“${position}”。\n\n比较依据\n${pairingSentence(pairings)}\n\n数据提示\n${dataCaveat(row)}`;
}

export function renderWhatIfNarrative(result = {}) {
  const oldPosition = marketPositionLabel(result.old_market_position);
  const newPosition = marketPositionLabel(result.new_market_position);
  const transition = oldPosition === newPosition ? `市场位置仍为“${newPosition}”` : `市场位置将从“${oldPosition}”变为“${newPosition}”`;
  const parts = [
    `如果将价格调整为 ${formatPrice(result.proposed_price)}，${transition}。`,
    `模拟后的价格${relativeDifferenceText(result.new_relative_index)}；当前可比竞品中位价为 ${formatPrice(result.competitor_median_price)}。`,
  ];
  const change = formatPercentRatio(result.price_change_from_current_pct);
  if (change !== "暂无") parts.push(`相对当前价格的调整幅度为 ${change}。`);
  if (numberOrNull(result.price_to_competitive_ceiling) !== null) {
    parts.push(`按照当前规则，进入“与市场基本持平”区间的价格上限约为 ${formatPrice(result.price_to_competitive_ceiling)}。`);
  }
  return parts.join(" ");
}
