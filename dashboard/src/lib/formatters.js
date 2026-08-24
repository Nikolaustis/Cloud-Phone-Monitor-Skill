export function money(value) {
  if (value == null || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `$${number.toFixed(2)}`;
}

export function pct(value) {
  if (value == null || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${(number * 100).toFixed(1)}%`;
}

export function indexValue(value) {
  if (value == null || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toFixed(1);
}

export function integer(value) {
  if (value == null || value === "") return "0";
  const number = Number(value);
  if (!Number.isFinite(number)) return "0";
  return number.toLocaleString();
}

export function durationLabel(value, t) {
  if (value == null || value === "") return "-";
  return `${value} ${t.dayUnit}`;
}

export function formatDateTime(value, lang) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(lang === "zh" ? "zh-CN" : "en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatSeconds(value) {
  if (value == null || value === "") return "-";
  const total = Number(value);
  if (!Number.isFinite(total)) return "-";
  const minutes = Math.floor(total / 60);
  const seconds = Math.floor(total % 60);
  if (minutes <= 0) return `${seconds}s`;
  return `${minutes}m ${seconds}s`;
}

export function bytes(value) {
  if (value == null) return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  if (number < 1024) return `${number} B`;
  if (number < 1024 * 1024) return `${(number / 1024).toFixed(1)} KB`;
  return `${(number / 1024 / 1024).toFixed(1)} MB`;
}

export function labelFromMap(map, value) {
  return map?.[value] || value || "-";
}

export function reasonDisplay(reasonCode, t) {
  const codes = String(reasonCode || "unchanged")
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean);
  const visible = codes.length ? codes : ["unchanged"];
  return visible.map((code) => labelFromMap(t.reasonLabels, code)).join("；");
}

export function reasonDescription(reasonCode, t, fallback) {
  const codes = String(reasonCode || "unchanged")
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean);
  const visible = codes.length ? codes : ["unchanged"];
  const descriptions = visible.map((code) => t.reasonDescriptions?.[code]).filter(Boolean);
  return descriptions.join(" ") || fallback || "-";
}

export function positionClass(value) {
  return {
    below_market: "border-emerald-200 bg-emerald-50 text-emerald-700",
    competitive: "border-blue-200 bg-blue-50 text-blue-700",
    slightly_high: "border-amber-200 bg-amber-50 text-amber-700",
    high: "border-red-200 bg-red-50 text-red-700",
    unknown: "border-slate-200 bg-slate-50 text-slate-700",
  }[value || "unknown"];
}

export function alertClass(value) {
  return {
    critical: "border-red-200 bg-red-50 text-red-700",
    warning: "border-amber-200 bg-amber-50 text-amber-700",
    info: "border-blue-200 bg-blue-50 text-blue-700",
    none: "border-slate-200 bg-slate-50 text-slate-700",
    unknown: "border-slate-200 bg-slate-50 text-slate-700",
  }[value || "unknown"];
}

export function confidenceClass(value) {
  return {
    high: "border-emerald-200 bg-emerald-50 text-emerald-700",
    medium: "border-blue-200 bg-blue-50 text-blue-700",
    low: "border-amber-200 bg-amber-50 text-amber-700",
    insufficient: "border-red-200 bg-red-50 text-red-700",
  }[value || "insufficient"];
}

export function levelClass(value) {
  return {
    strong_match: "border-emerald-200 bg-emerald-50 text-emerald-700",
    adjusted_match: "border-blue-200 bg-blue-50 text-blue-700",
    weak_match: "border-amber-200 bg-amber-50 text-amber-700",
    not_comparable: "border-red-200 bg-red-50 text-red-700",
    missing_competitor: "border-slate-200 bg-slate-50 text-slate-700",
  }[value || "missing_competitor"];
}
