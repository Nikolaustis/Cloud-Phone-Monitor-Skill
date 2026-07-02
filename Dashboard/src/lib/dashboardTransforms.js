export const defaultFilters = {
  platform: "all",
  duration: "all",
  region: "all",
  comparabilityLevel: "all",
  marketPosition: "all",
  alertLevel: "all",
  confidenceLevel: "all",
  ugModel: "all",
  includedCore: "all",
  pairingSource: "all",
  reasonCode: "all",
  dateRange: "latest",
};

const alertRank = { critical: 0, warning: 1, info: 2, none: 3, unknown: 4 };
const positionRank = { high: 0, slightly_high: 1, unknown: 2, competitive: 3, below_market: 4 };
const confidenceRank = { insufficient: 0, low: 1, medium: 2, high: 3 };

export function buildPriceDecisionOverview(raw) {
  return raw?.priceDecisionOverview ?? [];
}

export function buildUgConfigPriceMatrix(raw) {
  return raw?.ugConfigPriceMatrix ?? [];
}

export function buildCompetitorBasket(raw, selectedUgConfig) {
  const rows = raw?.competitorBasket ?? [];
  if (!selectedUgConfig) return rows;
  return rows.filter((row) => row.ug_config_id === selectedUgConfig);
}

export function buildMarketPositionDistribution(matrix) {
  const counts = matrix.reduce((acc, row) => {
    const key = row.market_position_label || "unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  return Object.entries(counts).map(([name, value]) => ({ name, value }));
}

export function sortPriceDecisionRows(rows) {
  return [...(rows ?? [])].sort((a, b) => {
    const alertDelta = (alertRank[a.alert_level] ?? 4) - (alertRank[b.alert_level] ?? 4);
    if (alertDelta) return alertDelta;
    const positionDelta = (positionRank[a.market_position_label] ?? 2) - (positionRank[b.market_position_label] ?? 2);
    if (positionDelta) return positionDelta;
    const confidenceDelta = (confidenceRank[a.confidence_level] ?? 2) - (confidenceRank[b.confidence_level] ?? 2);
    if (confidenceDelta) return confidenceDelta;
    return (b.relative_index || b.ugphone_relative_index || 0) - (a.relative_index || a.ugphone_relative_index || 0);
  });
}

export function buildAlertPriorityBoard(matrix) {
  const alertRank = { critical: 0, warning: 1, info: 2, none: 3 };
  return matrix
    .filter((row) => ["critical", "warning"].includes(row.alert_level))
    .sort((a, b) => {
      const alertDelta = (alertRank[a.alert_level] ?? 9) - (alertRank[b.alert_level] ?? 9);
      if (alertDelta) return alertDelta;
      return (b.relative_index || 0) - (a.relative_index || 0);
    })
    .slice(0, 20);
}

export function applyDashboardFilters(data, filters) {
  const matrix = sortPriceDecisionRows((data.ugConfigPriceMatrix ?? []).filter((row) => {
    if (filters.duration !== "all" && String(row.duration_days) !== String(filters.duration)) return false;
    if (filters.marketPosition !== "all" && row.market_position_label !== filters.marketPosition) return false;
    if (filters.alertLevel !== "all" && row.alert_level !== filters.alertLevel) return false;
    if (filters.confidenceLevel !== "all" && row.confidence_level !== filters.confidenceLevel) return false;
    if (filters.ugModel !== "all" && !String(row.ug_config || "").toLowerCase().includes(String(filters.ugModel).toLowerCase())) return false;
    return true;
  }));
  const visibleIds = new Set(matrix.map((row) => row.ug_config_id));
  const competitorBasket = (data.competitorBasket ?? []).filter((row) => {
    if (!visibleIds.has(row.ug_config_id)) return false;
    if (filters.platform !== "all" && row.competitor_platform !== filters.platform) return false;
    if (filters.comparabilityLevel !== "all" && row.comparability_level !== filters.comparabilityLevel) return false;
    if (filters.includedCore !== "all" && String(Boolean(row.included_in_core_median)) !== String(filters.includedCore)) return false;
    if (filters.region !== "all") {
      const text = `${row.supported_server_regions || ""} ${row.pairing_notes || ""}`.toLowerCase();
      if (!text.includes(filters.region.toLowerCase())) return false;
    }
    return true;
  });
  const pairingEvidence = (data.pairingEvidence ?? []).filter((row) => {
    if (filters.platform !== "all" && row.competitor_platform !== filters.platform) return false;
    if (filters.comparabilityLevel !== "all" && row.comparability_level !== filters.comparabilityLevel) return false;
    if (filters.pairingSource !== "all" && row.pairing_source !== filters.pairingSource) return false;
    return true;
  });
  const qualityPriceDetails = (data.qualityPriceDetails ?? []).filter((row) => {
    if (!visibleIds.has(row.ug_config_id)) return false;
    if (filters.platform !== "all" && row.competitor_platform !== filters.platform) return false;
    if (filters.comparabilityLevel !== "all" && row.comparability_level !== filters.comparabilityLevel) return false;
    return true;
  });
  const alertPriorityBoard = buildAlertPriorityBoard(matrix).filter((row) => {
    if (filters.alertLevel !== "all" && row.alert_level !== filters.alertLevel) return false;
    if (filters.confidenceLevel !== "all" && row.confidence_level !== filters.confidenceLevel) return false;
    return true;
  });
  return {
    ...data,
    ugConfigPriceMatrix: matrix,
    priceDecisionOverview: (data.priceDecisionOverview ?? []).filter((row) => visibleIds.has(row.ug_config_id)),
    competitorBasket,
    pairingEvidence,
    qualityPriceDetails,
    alertPriorityBoard,
    marketPositionDistribution: buildMarketPositionDistribution(matrix),
  };
}

export function firstMatrixId(matrix) {
  return sortPriceDecisionRows(matrix)?.[0]?.ug_config_id ?? null;
}

export function uniqueValues(rows, key) {
  return [...new Set((rows ?? []).map((row) => row?.[key]).filter((value) => value != null && value !== ""))];
}

export function selectedDecision(data, selectedId) {
  return (
    (data?.priceDecisionOverview ?? []).find((row) => row.ug_config_id === selectedId) ||
    (data?.ugConfigPriceMatrix ?? []).find((row) => row.ug_config_id === selectedId) ||
    null
  );
}
