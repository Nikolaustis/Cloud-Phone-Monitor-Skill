import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  Clock,
  GitCompareArrows,
  HelpCircle,
  LineChart as LineChartIcon,
  RefreshCw,
  Search,
  ShoppingBasket,
  Tags,
} from "lucide-react";
import {
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { loadDashboardData, loadTrendDetailChunks } from "./lib/api.js";
import { translations } from "./lib/i18n.js";
import { alertClass, formatDateTime, indexValue, labelFromMap, levelClass, money, pct, positionClass } from "./lib/formatters.js";

const pages = [
  ["price-overview", "价格概览", GitCompareArrows],
  ["duration-prices", "分天数价格对比", Clock],
  ["trends", "价格趋势", LineChartIcon],
  ["price-changes", "价格变化追踪", RefreshCw],
  ["pairing", "配置配对", ShoppingBasket],
  ["product-text", "商品文本", Tags],
  ["metrics", "指标说明", BookOpen],
];

const coreBuckets = [1, 3, 7, 15, 30, 60, 90, 180, 365];
const allPlatforms = ["UgPhone", "VSPhone", "Redfinger", "LDCloud"];
const competitorPlatforms = ["VSPhone", "Redfinger", "LDCloud"];
const productModels = ["UVIP", "GVIP", "KVIP", "MVIP", "SVIP"];
const positionOptions = ["below_market", "competitive", "slightly_high", "high", "unknown"];
const levelOptions = ["strong_match", "adjusted_match", "weak_match", "not_comparable"];
const reasonOptions = [
  "price_unchanged",
  "price_up",
  "price_down",
  "promotion_text_changed",
  "abnormal_price_change",
  "short_duration_excluded",
  "duration_missing_current_used_baseline",
  "baseline_structure_mismatch",
];
const alertOptions = ["critical", "warning", "info", "none"];
const platformColors = {
  UgPhone: "#dc2626",
  VSPhone: "#111827",
  Redfinger: "#2563eb",
  LDCloud: "#eab308",
};
const pageSize = 50;

function pageFromHash() {
  const raw = window.location.hash.replace(/^#\/?/, "") || "price-overview";
  return pages.some(([page]) => page === raw) ? raw : "price-overview";
}

function textOf(...values) {
  return values
    .flat()
    .filter((value) => value !== null && value !== undefined)
    .map((value) => String(value).toLowerCase())
    .join(" ");
}

function stableArray(value) {
  return Array.isArray(value) ? value : [];
}

function bucketLabel(value) {
  return value === "other" ? "其他" : `${value}天`;
}

function formatDurationDays(days) {
  return `${Number.isInteger(days) ? days : Number(days).toFixed(2).replace(/\.00$/, "")}天`;
}

function canonicalDurationFromValue(value) {
  if (value === null || value === undefined || value === "" || value === "other" || value === "其他" || value === "unknown") return null;
  let days = null;
  if (typeof value === "number" && Number.isFinite(value)) {
    days = value;
  } else {
    const text = String(value).trim().toLowerCase();
    if (/^\d+(?:\.\d+)?$/.test(text)) {
      days = Number(text);
    } else {
      const match = text.match(/(^|[^\d.])(\d+(?:\.\d+)?)\s*[- ]?\s*(hours?|hrs?|小时|h|days?|天|日|weeks?|周|months?|月|years?|年)(?=$|\s|[^a-z])/);
      if (!match) return null;
      const number = Number(match[2]);
      const unit = match[3];
      if (!Number.isFinite(number)) return null;
      if (["hour", "hours", "hr", "hrs", "小时", "h"].includes(unit)) days = number / 24;
      else if (["day", "days", "天", "日"].includes(unit)) days = number;
      else if (["week", "weeks", "周"].includes(unit)) days = number * 7;
      else if (["month", "months", "月"].includes(unit)) days = number * 30;
      else days = number * 365;
    }
  }
  if (!Number.isFinite(days)) return null;
  const nearest = Math.round(days);
  if (Math.abs(days - nearest) < 1e-9 && coreBuckets.includes(nearest)) {
    return { bucket: nearest, display: formatDurationDays(nearest), days: nearest };
  }
  return null;
}

function migrateDurationFields(row) {
  if (!row || typeof row !== "object") return row;
  const parsed = canonicalDurationFromValue(row.actual_duration_days)
    || canonicalDurationFromValue(row.duration_days)
    || canonicalDurationFromValue(row.actual_duration_display)
    || canonicalDurationFromValue(row.duration_display);
  if (!parsed) return row;
  if (String(row.duration_bucket) === String(parsed.bucket) && row.duration_display) return row;
  return {
    ...row,
    duration_bucket: parsed.bucket,
    duration_display: row.duration_display || parsed.display,
    actual_duration_days: row.actual_duration_days ?? parsed.days,
    actual_duration_display: row.actual_duration_display || parsed.display,
    migrated_duration_bucket: String(row.duration_bucket || ""),
  };
}

function alertRank(value) {
  return { critical: 0, warning: 1, info: 2, none: 3 }[value] ?? 4;
}

function compareAbsPct(a, b) {
  return Math.abs(Number(b?.price_change_pct || 0)) - Math.abs(Number(a?.price_change_pct || 0));
}

function usePagination(rows, size = pageSize) {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(rows.length / size));
  useEffect(() => setPage(1), [rows.length, size]);
  const safePage = Math.min(page, totalPages);
  const visible = rows.slice((safePage - 1) * size, safePage * size);
  return { page: safePage, totalPages, visible, setPage };
}

function InfoCard({ title, children }) {
  return (
    <section className="panel border-blue-200 bg-blue-50 p-4 text-sm leading-6 text-blue-900">
      <div className="mb-1 flex items-center gap-2 font-bold">
        <HelpCircle size={16} />
        {title}
      </div>
      <div>{children}</div>
    </section>
  );
}

function FieldTip({ label, tip }) {
  return (
    <span className="inline-flex items-center gap-1" title={tip}>
      {label}
      <HelpCircle size={13} className="text-muted" />
    </span>
  );
}

function StatCard({ label, value, detail }) {
  return (
    <article className="panel p-4">
      <div className="text-xs font-bold uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-2 text-2xl font-bold text-ink">{value}</div>
      {detail ? <p className="mt-1 text-xs text-muted">{detail}</p> : null}
    </article>
  );
}

function SelectFilter({ label, value, onChange, children }) {
  return (
    <label className="grid gap-1 text-xs font-semibold text-muted">
      {label}
      <select className="rounded-md border border-line bg-white px-3 py-2 text-sm font-medium text-ink" value={value} onChange={(event) => onChange(event.target.value)}>
        {children}
      </select>
    </label>
  );
}

function SearchFilter({ label, value, onChange, placeholder = "搜索" }) {
  return (
    <label className="grid gap-1 text-xs font-semibold text-muted md:col-span-2">
      {label}
      <div className="flex items-center rounded-md border border-line bg-white px-3 py-2">
        <Search size={16} className="text-muted" />
        <input className="ml-2 w-full border-none bg-transparent text-sm outline-none" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
      </div>
    </label>
  );
}

function ToggleFilter({ checked, onChange, label }) {
  return (
    <label className="flex items-center gap-2 rounded-md border border-line bg-white px-3 py-2 text-sm font-medium text-ink">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      {label}
    </label>
  );
}

function Pagination({ page, totalPages, total, shown, setPage }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-slate-50 px-4 py-3 text-sm text-muted">
      <span>当前显示 {shown} / {total} 条</span>
      <div className="flex items-center gap-2">
        <button className="rounded-md border border-line bg-white px-3 py-1.5 disabled:opacity-40" disabled={page <= 1} onClick={() => setPage(page - 1)} type="button">上一页</button>
        <span>{page} / {totalPages}</span>
        <button className="rounded-md border border-line bg-white px-3 py-1.5 disabled:opacity-40" disabled={page >= totalPages} onClick={() => setPage(page + 1)} type="button">下一页</button>
      </div>
    </div>
  );
}

function AppShell({ page, setPage, lang, setLang, onReload, isReloading, children }) {
  return (
    <div className="min-h-screen bg-surface">
      <aside className="fixed left-0 top-0 z-40 hidden h-screen w-64 flex-col bg-slate-950 px-4 py-6 text-white shadow-xl lg:flex">
        <div className="mb-8 px-2">
          <div className="text-base font-bold">Cloud Phone Monitor</div>
          <div className="text-xs text-slate-400">业务价格监测看板</div>
        </div>
        <nav className="flex-1 space-y-1">
          {pages.map(([key, label, Icon]) => (
            <a
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                page === key ? "border-r-2 border-blue-400 bg-blue-500/10 text-blue-300" : "text-slate-400 hover:bg-slate-900 hover:text-slate-100"
              }`}
              href={`#/${key}`}
              key={key}
              onClick={(event) => {
                event.preventDefault();
                window.location.hash = `/${key}`;
                setPage(key);
              }}
            >
              <Icon size={18} />
              {label}
            </a>
          ))}
        </nav>
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-3 text-xs text-slate-300">
          前台只展示价格、配置、趋势和商品文本。采集诊断只写入后台 JSON 与日志。
        </div>
      </aside>
      <div className="lg:ml-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-line bg-white/90 px-4 backdrop-blur lg:px-8">
          <div className="flex items-center gap-4">
            <div className="hidden rounded-full border border-line bg-slate-50 px-3 py-1.5 lg:flex">
              <Search className="text-muted" size={17} />
              <input className="ml-2 w-56 border-none bg-transparent text-sm outline-none" placeholder="搜索配置、平台、商品文本..." />
            </div>
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-muted">当前页面</div>
              <h1 className="text-base font-bold text-ink">{pages.find(([key]) => key === page)?.[1]}</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <select className="rounded-md border border-line bg-white px-2 py-1.5 text-sm" onChange={(event) => setLang(event.target.value)} value={lang}>
              <option value="zh">简体中文</option>
              <option value="en">English</option>
            </select>
            <button className="inline-flex items-center gap-1.5 rounded-md border border-line bg-white px-3 py-1.5 text-sm font-semibold" disabled={isReloading} onClick={onReload} type="button">
              <RefreshCw className={isReloading ? "animate-spin" : ""} size={16} />
              重新加载看板数据
            </button>
          </div>
        </header>
        <main className="space-y-6 p-4 lg:p-6">{children}</main>
      </div>
    </div>
  );
}

function PriceOverview({ data, go }) {
  const overview = data.frontendPriceOverview || {};
  const counts = overview.market_position_counts || {};
  const distribution = Object.entries(counts).map(([name, value]) => ({ name, value }));
  const colors = { below_market: "#059669", competitive: "#2563eb", slightly_high: "#d97706", high: "#dc2626", unknown: "#94a3b8" };
  return (
    <div className="space-y-6">
      <InfoCard title="本页怎么看">
        本页只看业务价格结论：UgPhone 在核心购买天数 1/3/7/15/30/60/90/180/365 天下，相对竞品是低于市场、有竞争力、略高还是明显偏高。后台采集诊断不会出现在前台看板。
      </InfoCard>
      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
        <StatCard label="更新时间" value={formatDateTime(overview.updated_at, "zh")} />
        <StatCard label="基准配置数量" value={overview.baseline_config_count || 0} />
        <StatCard label="参与购买天数" value="1 / 3 / 7 / 15 / 30 / 60 / 90 / 180 / 365" />
        <StatCard label="高于竞品配置" value={overview.above_market_count || 0} detail="略高 + 明显偏高" />
        <StatCard label="低于竞品配置" value={overview.below_market_count || 0} />
      </section>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section className="panel p-5">
          <h2 className="text-lg font-bold">价格位置分布</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-[240px_1fr]">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={distribution} dataKey="value" innerRadius={54} outerRadius={88} paddingAngle={2}>
                    {distribution.map((entry) => <Cell key={entry.name} fill={colors[entry.name] || colors.unknown} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="grid content-center gap-2">
              {distribution.map((item) => (
                <div className="flex items-center justify-between rounded-lg border border-line bg-slate-50 px-3 py-2" key={item.name}>
                  <span className={`chip border ${positionClass(item.name)}`}>{labelFromMap(translations.zh.positionLabels, item.name)}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          </div>
        </section>
        <section className="panel overflow-hidden">
          <div className="border-b border-line bg-slate-50 px-5 py-4">
            <h2 className="text-lg font-bold">今日需要关注的价格变化</h2>
          </div>
          <div className="divide-y divide-line">
            {stableArray(overview.attention_items).slice(0, 8).map((row) => (
              <button className="grid w-full gap-3 p-4 text-left hover:bg-slate-50 md:grid-cols-[1fr_auto]" key={`${row.ug_config_id}-${row.duration_bucket}`} onClick={() => go("duration-prices")} type="button">
                <div>
                  <div className="font-semibold">{row.ug_config}</div>
                  <div className="text-xs text-muted">{row.duration_bucket_label} · UgPhone 指数 {indexValue(row.ugphone_relative_index)}</div>
                </div>
                <span className={`chip border ${positionClass(row.market_position_label)}`}>{labelFromMap(translations.zh.positionLabels, row.market_position_label)}</span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function PairingPage({ data }) {
  return (
    <div className="space-y-6">
      <InfoCard title="本页怎么看">
        本页不是比较价格，而是说明配置如何配对。套餐名不作为主要依据，主要依据是 Android、CPU、内存、存储、服务器地区和购买天数。strong_match 和 adjusted_match 才会进入核心价格判断。
      </InfoCard>
      <section className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table w-full min-w-[1120px] text-left text-sm">
            <thead className="bg-slate-50 text-xs text-muted">
              <tr>
                <th>UgPhone 配置</th>
                <th>VSPhone 配对配置</th>
                <th>Redfinger 配对配置</th>
                <th>LDCloud 配对配置</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {stableArray(data.pairingMatrix).map((row) => (
                <tr className="hover:bg-slate-50" key={row.ug_config_id}>
                  <td className="font-semibold">{row.ug_config}</td>
                  {competitorPlatforms.map((platform) => {
                    const item = row.pairings?.[platform];
                    return (
                      <td key={platform}>
                        {item ? (
                          <div>
                            <div className="font-semibold">{item.competitor_config}</div>
                            <div className="mt-1 flex flex-wrap gap-2">
                              <span className="chip border-slate-200 bg-slate-50 text-slate-700" title="配置相似度：综合 Android、CPU、内存、存储、服务器地区和购买天数。">{item.config_similarity_score ?? "-"}</span>
                              <span className={`chip border ${levelClass(item.comparability_level)}`}>{labelFromMap(translations.zh.levelLabels, item.comparability_level)}</span>
                              {!item.included_in_core_median ? <span className="chip border-slate-200 bg-slate-50 text-slate-600">未进入核心中位数</span> : null}
                            </div>
                            <p className="mt-1 text-xs text-muted">{item.pairing_notes || "-"}</p>
                          </div>
                        ) : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function CompetitorPriceCell({ item, highlighted }) {
  if (!item) return <span className="text-muted">—</span>;
  return (
    <div className={`rounded-lg border p-3 ${highlighted ? "border-primary bg-blue-50" : "border-line bg-white"}`}>
      <div className="text-base font-bold">{money(item.current_price)}</div>
      <div className="mt-1 text-xs text-muted">配置相似度：{item.config_similarity_score ?? "-"}</div>
      <div className="mt-1">
        <span className={`chip border ${levelClass(item.comparability_level)}`}>{labelFromMap(translations.zh.levelLabels, item.comparability_level)}</span>
      </div>
      <div className="mt-2 text-xs leading-5 text-slate-700">配置：{item.config || "-"}</div>
      {!item.included_in_core_median ? <div className="mt-2 chip border-slate-200 bg-slate-50 text-slate-600">未进入核心中位数</div> : null}
    </div>
  );
}

function DurationPricesPage({ data }) {
  const [bucket, setBucket] = useState("30");
  const [product, setProduct] = useState("all");
  const [position, setPosition] = useState("all");
  const [level, setLevel] = useState("all");
  const [competitor, setCompetitor] = useState("all");
  const [search, setSearch] = useState("");
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [changedOnly, setChangedOnly] = useState(false);
  const [textChangedOnly, setTextChangedOnly] = useState(false);
  const rows = stableArray(data.durationPriceComparison?.buckets?.[bucket]);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((row) => {
      const competitors = Object.values(row.competitors || {}).filter(Boolean);
      if (product !== "all" && row.ug_product_model !== product) return false;
      if (position !== "all" && row.market_position_label !== position) return false;
      if (level !== "all" && !competitors.some((item) => item.comparability_level === level)) return false;
      if (competitor !== "all" && !row.competitors?.[competitor]) return false;
      if (attentionOnly && !["slightly_high", "high"].includes(row.market_position_label)) return false;
      if (changedOnly && !row.has_price_change) return false;
      if (textChangedOnly && !row.promotion_text_changed) return false;
      if (!q) return true;
      return textOf(row.ug_product_model, row.ug_config, row.promotion_text, competitors.map((item) => [item.product_model, item.config, item.promotion_text])).includes(q);
    });
  }, [rows, product, position, level, competitor, search, attentionOnly, changedOnly, textChangedOnly]);
  const pager = usePagination(filtered);

  return (
    <div className="space-y-6">
      <InfoCard title="本页怎么看">
        本页按购买天数比较四个平台价格。默认比较 1天、3天、7天、15天、30天、60天、90天、180天、365天这些核心天数；没有对应购买天数的平台会自然缺席，不用其他周期补位。小时包、45天、120天、组合活动包等非核心价格不会进入核心价格判断。
      </InfoCard>
      <div className="panel flex flex-wrap gap-2 p-3">
        {coreBuckets.map((item) => (
          <button className={`rounded-md px-4 py-2 text-sm font-semibold ${bucket === String(item) ? "bg-primary text-white" : "border border-line bg-white"}`} key={item} onClick={() => setBucket(String(item))} type="button">
            {item}天
          </button>
        ))}
      </div>
      <section className="panel grid gap-3 p-4 md:grid-cols-4">
        <SelectFilter label="UgPhone 产品" value={product} onChange={setProduct}><option value="all">全部</option>{productModels.map((item) => <option key={item} value={item}>{item}</option>)}</SelectFilter>
        <SelectFilter label="价格位置" value={position} onChange={setPosition}><option value="all">全部</option>{positionOptions.map((item) => <option key={item} value={item}>{labelFromMap(translations.zh.positionLabels, item)} {item}</option>)}</SelectFilter>
        <SelectFilter label="配对等级" value={level} onChange={setLevel}><option value="all">全部</option>{levelOptions.map((item) => <option key={item} value={item}>{item}</option>)}</SelectFilter>
        <SelectFilter label="竞品平台" value={competitor} onChange={setCompetitor}><option value="all">全部竞品</option>{competitorPlatforms.map((item) => <option key={item} value={item}>{item}</option>)}</SelectFilter>
        <SearchFilter label="搜索" value={search} onChange={setSearch} placeholder="搜索产品、配置、竞品、商品文案" />
        <div className="flex flex-wrap items-end gap-2 md:col-span-2">
          <ToggleFilter checked={attentionOnly} onChange={setAttentionOnly} label="只看略高/明显偏高" />
          <ToggleFilter checked={changedOnly} onChange={setChangedOnly} label="只看有价格变化" />
          <ToggleFilter checked={textChangedOnly} onChange={setTextChangedOnly} label="只看商品文案变化" />
        </div>
      </section>
      <section className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table w-full min-w-[1480px] text-left text-sm">
            <thead className="bg-slate-50 text-xs text-muted">
              <tr>
                <th>UgPhone 配置</th>
                <th><FieldTip label="UgPhone 当前价" tip="同购买天数下的当前成交价，不是30天等效价。" /></th>
                <th>VSPhone 价格 / 相似度 / 配对</th>
                <th>Redfinger 价格 / 相似度 / 配对</th>
                <th>LDCloud 价格 / 相似度 / 配对</th>
                <th><FieldTip label="竞品中位价" tip="只使用 strong_match / adjusted_match 的竞品当前价。" /></th>
                <th><FieldTip label="UgPhone 相对竞品指数" tip="UgPhone 当前价 / 竞品中位价 × 100。" /></th>
                <th>价格位置</th>
                <th>商品文案</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {pager.visible.map((row) => (
                <tr className="align-top hover:bg-slate-50" key={`${row.ug_config_id}-${bucket}`}>
                  <td>
                    <div className="font-bold">{row.ug_product_model || "-"}</div>
                    <div className="mt-1 text-xs leading-5 text-muted">
                      Android {row.ug_android_version || "-"} / {row.ug_cpu || "-"} / {row.ug_ram || "-"} / {row.ug_storage || "-"}
                    </div>
                    <div className="mt-1 text-xs text-muted">{row.ug_config}</div>
                  </td>
                  <td className="font-bold">{money(row.ugphone_price)}</td>
                  {competitorPlatforms.map((platform) => (
                    <td key={platform}><CompetitorPriceCell item={row.competitors?.[platform]} highlighted={competitor === platform} /></td>
                  ))}
                  <td className="font-bold">{money(row.competitor_median_price)}</td>
                  <td>{indexValue(row.ugphone_relative_index)}</td>
                  <td><span className={`chip border ${positionClass(row.market_position_label)}`}>{labelFromMap(translations.zh.positionLabels, row.market_position_label)}</span></td>
                  <td className="max-w-sm text-xs text-muted">{Object.values(row.competitors || {}).map((item) => item?.promotion_text).filter(Boolean)[0] || row.promotion_text || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!filtered.length ? <div className="p-6 text-sm text-muted">没有符合筛选条件的数据。</div> : null}
        <Pagination page={pager.page} totalPages={pager.totalPages} total={filtered.length} shown={pager.visible.length} setPage={pager.setPage} />
      </section>
    </div>
  );
}

function isRealDateLabel(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(value || ""));
}

function cleanTrendPoints(points) {
  const normalized = stableArray(points).map((point) => ({
    ...point,
    date: point.date ?? point.time,
    price: point.price,
    price_source: point.price_source || (point.time === "previous" ? "previous" : "current"),
  }));
  const hasDailyHistory = normalized.some((point) => isRealDateLabel(point.date));
  return hasDailyHistory ? normalized.filter((point) => point.date !== "previous") : normalized;
}

const REGION_MERGED_VALUE = "__merged_all_regions__";

const regionAliases = {
  us: "United States",
  usa: "United States",
  "u.s.": "United States",
  "u.s.a.": "United States",
  america: "United States",
  "united states of america": "United States",
  "美国": "United States",
  hongkong: "Hong Kong",
  "hong kong": "Hong Kong",
  hongkong2: "Hong Kong 2",
  "hong kong 2": "Hong Kong 2",
  hk2: "Hong Kong 2",
  hk: "Hong Kong",
  "香港": "Hong Kong",
  singapore: "Singapore",
  sg: "Singapore",
  "新加坡": "Singapore",
  thailand: "Thailand",
  thai: "Thailand",
  "泰国": "Thailand",
  japan: "Japan",
  jp: "Japan",
  "日本": "Japan",
  germany: "Germany",
  de: "Germany",
  netherlands: "Netherlands",
  nl: "Netherlands",
  "德国": "Germany",
  indonesia: "Indonesia",
  id: "Indonesia",
  "印尼": "Indonesia",
  vietnam: "Vietnam",
  vn: "Vietnam",
  "越南": "Vietnam",
  brazil: "Brazil",
  br: "Brazil",
  "巴西": "Brazil",
  taiwan: "Taiwan",
  tw: "Taiwan",
  "台湾": "Taiwan",
  italy: "Italy",
  it: "Italy",
  "意大利": "Italy",
  korea: "South Korea",
  "south korea": "South Korea",
  kr: "South Korea",
  "韩国": "South Korea",
};

function normalizeRegionLabel(value) {
  const text = String(value ?? "").trim();
  if (!text || ["nan", "none", "null", "undefined", "-", "—"].includes(text.toLowerCase())) return "";
  const key = text.replace(/\s+/g, " ").toLowerCase();
  return regionAliases[key] || text;
}

function splitRegionText(value) {
  if (Array.isArray(value)) return value.map(normalizeRegionLabel).filter(Boolean);
  const text = String(value ?? "").trim();
  if (!text) return [];
  const result = [];
  text.split(/[;,，、\/\n]+/).forEach((part) => {
    const label = normalizeRegionLabel(part);
    if (label && !result.includes(label)) result.push(label);
  });
  return result;
}

function cleanRegionalPoints(regionalPoints) {
  const result = {};
  Object.entries(regionalPoints || {}).forEach(([region, points]) => {
    const label = normalizeRegionLabel(region);
    if (!label) return;
    const cleaned = cleanTrendPoints(points);
    if (cleaned.some((point) => point.price !== null && point.price !== undefined && point.price !== "")) {
      result[label] = cleaned;
    }
  });
  return result;
}

function cleanTrendSeriesItem(series) {
  const regionalPoints = cleanRegionalPoints(series?.regional_points);
  const androidBreakdownSeries = stableArray(series?.android_breakdown_series).map((child) => {
    const childRegionalPoints = cleanRegionalPoints(child?.regional_points);
    return migrateDurationFields({
      ...child,
      points: cleanTrendPoints(child?.points),
      regional_points: childRegionalPoints,
      available_regions: Object.keys(childRegionalPoints),
    });
  });
  return migrateDurationFields({
    ...series,
    points: cleanTrendPoints(series?.points),
    regional_points: regionalPoints,
    available_regions: Object.keys(regionalPoints),
    android_breakdown_series: androidBreakdownSeries,
  });
}

function normalizeTrendsPayload(payload) {
  if (Array.isArray(payload)) {
    return {
      updated_at: null,
      available_duration_buckets: [1, 3, 7, 15, 30, 60, 90, 180, 365, "other"],
      other_paid_prices: [],
      series: payload.map((row, index) => ({
        series_id: `legacy_${index}`,
        platform: row.platform,
        product_model: row.config?.split("/")?.[0]?.trim(),
        config: row.config,
        ug_config_id: row.config,
        duration_bucket: row.duration_bucket,
        duration_display: row.duration_display,
        comparability_level: row.platform === "UgPhone" ? "base" : "unknown",
        config_similarity_score: row.platform === "UgPhone" ? 100 : null,
        line_name: `${row.platform} ${row.config} ${row.duration_display}`,
        color: platformColors[row.platform] || "#64748b",
        current_price: row.current_price,
        previous_price: row.previous_price,
        seven_day_avg_price: row.seven_day_avg_price,
        seven_day_sample_count: row.seven_day_sample_count,
        thirty_day_avg_price: row.thirty_day_avg_price,
        thirty_day_sample_count: row.thirty_day_sample_count,
        price_change_pct: row.price_change_pct,
        price_source: row.current_price == null && row.previous_price != null ? "baseline_fallback" : "current",
        points: cleanTrendPoints(row.series),
      })).map((series) => migrateDurationFields({ ...series, regional_points: cleanRegionalPoints(series.regional_points) })),
    };
  }
  const normalized = payload || { updated_at: null, available_duration_buckets: [], series: [] };
  const series = stableArray(normalized.series).map(cleanTrendSeriesItem);
  const otherPaidPrices = stableArray(normalized.other_paid_prices).map(migrateDurationFields);
  return {
    ...normalized,
    available_duration_buckets: normalized.available_duration_buckets?.length ? normalized.available_duration_buckets : [1, 3, 7, 15, 30, 60, 90, 180, 365, "other"],
    series,
    other_paid_prices: otherPaidPrices,
  };
}


function normalizeTrendDetailFile(value) {
  return String(value || "").replace(/^\/+/, "");
}

function buildTrendDetailMap(detailChunkCache) {
  const map = new Map();
  Object.values(detailChunkCache || {}).forEach((payload) => {
    stableArray(payload?.entries).forEach((entry) => {
      const id = String(entry?.series_id || "");
      if (!id) return;
      map.set(id, entry);
    });
  });
  return map;
}

function applyTrendDetailToSeries(series, detailMap) {
  const id = String(series?.series_id || "");
  const detail = detailMap.get(id);
  if (!detail) return series;
  return cleanTrendSeriesItem({
    ...series,
    regional_points: detail.regional_points || series.regional_points,
    android_breakdown_series: detail.android_breakdown_series || series.android_breakdown_series,
  });
}

const platformPalettes = {
  UgPhone: ["#dc2626", "#ef4444", "#b91c1c", "#f87171", "#991b1b", "#fca5a5"],
  VSPhone: ["#111827", "#374151", "#6b7280", "#030712", "#4b5563", "#9ca3af"],
  Redfinger: ["#2563eb", "#3b82f6", "#1d4ed8", "#60a5fa", "#1e40af", "#93c5fd"],
  LDCloud: ["#eab308", "#ca8a04", "#facc15", "#a16207", "#fde047", "#854d0e"],
};

function sortDateLabel(value) {
  if (value === "previous") return "0000-00-00";
  return String(value || "");
}

function platformSeriesColor(platform, index = 0) {
  const palette = platformPalettes[platform] || [platformColors[platform] || "#64748b"];
  return palette[index % palette.length];
}

function getSeriesKey(series) {
  return series.series_id || `${series.platform}-${series.line_name}-${series.duration_bucket}`;
}

function getSeriesChartKey(series) {
  return `series__${getSeriesKey(series)}`.replace(/[^a-zA-Z0-9_一-龥-]/g, "_");
}

function getSeriesDisplayName(series) {
  return series.display_name || series.line_name || `${series.platform} ${series.product_model || ""} ${series.duration_display || bucketLabel(series.duration_bucket)}`.trim();
}

function normalizeAndroidVersionLabel(value) {
  const text = String(value ?? "").trim();
  if (!text || ["nan", "none", "null", "undefined", "-", "未识别"].includes(text.toLowerCase())) return null;
  const match = text.match(/^\s*(\d+(?:\.\d+)?)\s*$/);
  if (!match) return null;
  const numeric = Number(match[1]);
  // Do not treat CPU cores, purchase duration, device counts, or tab indexes as
  // Android versions. In this market data, real Android major versions should
  // not be below 8, while values such as 1/3/4/6/30 usually come from parsing
  // "1 device", "3 cores", "30 days", or mixed tab text.
  if (!Number.isFinite(numeric) || numeric < 8 || numeric > 20) return null;
  return Number.isInteger(numeric) ? String(numeric) : String(numeric);
}

function splitAndroidVersionText(value) {
  if (Array.isArray(value)) return value;
  if (value === undefined || value === null) return [];
  return String(value).split(/[\/;,，、\s]+/).filter(Boolean);
}

function extractAndroidVersionsFromDisplayText(text) {
  const source = String(text || "");
  if (!source) return [];
  const matched = [];
  // Config text normally looks like: "KVIP / Android 10/12/13 / 6 cores ...".
  // Stop at the spaced slash delimiter so CPU cores are not parsed as Android.
  const configMatch = source.match(/Android\s+(.+?)(?:\s+\/\s+|\s+\d+\s*天|$)/i);
  if (configMatch) matched.push(...splitAndroidVersionText(configMatch[1]));
  return matched;
}

function seriesAndroidVersions(series) {
  // Prefer the cleaned backend field. Do not use selected_android_versions as a
  // primary source because it can represent all selectable Android tabs/filters,
  // not the Android version of the actual product row. This was the cause of
  // labels such as Android 1/8/10/12/15/30 and Android 4/10/12/13.
  const sourceGroups = [
    stableArray(series.merged_android_versions),
    stableArray(series.android_versions),
    splitAndroidVersionText(series.android_version),
  ];
  for (const group of sourceGroups) {
    const cleaned = [...new Set(group.map(normalizeAndroidVersionLabel).filter(Boolean))];
    if (cleaned.length) return cleaned.sort((a, b) => Number(a) - Number(b) || String(a).localeCompare(String(b)));
  }

  // Fallback only when no structured Android field exists. This keeps legacy
  // rows usable while preventing product configs like "Android 10 / 3 cores"
  // from becoming "Android 3/10".
  const fallback = [series.config, series.line_name].flatMap(extractAndroidVersionsFromDisplayText);
  const cleaned = [...new Set(fallback.map(normalizeAndroidVersionLabel).filter(Boolean))];
  return cleaned.sort((a, b) => Number(a) - Number(b) || String(a).localeCompare(String(b)));
}

function androidVersionText(series) {
  const versions = seriesAndroidVersions(series);
  return versions.length ? versions.join("/") : "";
}

function expandedTrendSeriesName(series) {
  const platform = series.platform || "";
  const product = series.product_model || series.ug_product_model || "";
  const android = androidVersionText(series);
  const duration = series.duration_display || bucketLabel(series.duration_bucket);
  // Products with no Android distinction, such as VSPhone 游戏挂机专用机, should
  // not be forced to show a noisy "Android 未识别" suffix.
  const androidPart = android ? `Android ${android}` : "";
  return `${platform} ${product} ${androidPart} ${duration}`.replace(/\s+/g, " ").trim();
}

function mergedTrendSeriesName(series) {
  const platform = series.platform || "";
  const product = series.product_model || series.ug_product_model || "";
  const duration = series.duration_display || bucketLabel(series.duration_bucket);
  return `${platform} ${product} ${duration}`.replace(/\s+/g, " ").trim();
}

function seriesPointWeight(series) {
  const mergedCount = Number(series.merged_series_count);
  if (Number.isFinite(mergedCount) && mergedCount > 0) return mergedCount;
  const androidCount = seriesAndroidVersions(series).length;
  return androidCount > 0 ? androidCount : 1;
}

function trendPriceKey(price) {
  const value = Number(price);
  return Number.isFinite(value) ? value.toFixed(6) : String(price ?? "");
}

function pickWeightedPoint(items) {
  const byPrice = new Map();
  items.forEach(({ point, series }) => {
    const price = Number(point.price);
    if (!Number.isFinite(price)) return;
    const key = trendPriceKey(price);
    const current = byPrice.get(key) || { price, weight: 0, items: [] };
    current.weight += seriesPointWeight(series);
    current.items.push({ point, series });
    byPrice.set(key, current);
  });
  const candidates = [...byPrice.values()].sort((a, b) => b.weight - a.weight || a.price - b.price);
  const chosen = candidates[0];
  if (!chosen) return null;
  const sourceRank = { current: 0, carry_forward: 1, baseline_fallback: 2, previous: 3 };
  const representative = chosen.items.slice().sort((a, b) => (sourceRank[a.point.price_source] ?? 9) - (sourceRank[b.point.price_source] ?? 9))[0]?.point;
  return representative ? { ...representative, price: chosen.price, android_merge_weight: chosen.weight } : null;
}

function buildTrendStatsFromPoints(points) {
  const valid = stableArray(points)
    .filter((point) => isRealDateLabel(point.date) && point.price !== null && point.price !== undefined && point.price !== "")
    .sort((a, b) => sortDateLabel(a.date).localeCompare(sortDateLabel(b.date)));
  if (!valid.length) return {};
  const prices = valid.map((point) => Number(point.price)).filter((price) => Number.isFinite(price));
  const collection = valid.filter((point) => point.price_source !== "carry_forward");
  const collectionPoints = collection.length ? collection : valid;
  const collectionPrices = collectionPoints.map((point) => Number(point.price)).filter((price) => Number.isFinite(price));
  const distinct = [...new Set(collectionPrices.map((price) => price.toFixed(6)))];
  const changedDates = [];
  let lastPrice = null;
  collectionPoints.forEach((point) => {
    const price = Number(point.price);
    if (!Number.isFinite(price)) return;
    if (lastPrice !== null && price.toFixed(6) !== lastPrice.toFixed(6)) changedDates.push(point.date);
    lastPrice = price;
  });
  const firstCollection = collectionPoints[0] || valid[0];
  const lastCollection = collectionPoints[collectionPoints.length - 1] || valid[valid.length - 1];
  const firstPrice = Number(firstCollection?.price);
  const lastCollectionPrice = Number(lastCollection?.price);
  const latest = valid[valid.length - 1];
  const previous = valid.length >= 2 ? valid[valid.length - 2] : null;
  return {
    current_price: Number(latest?.price),
    previous_price: previous ? Number(previous.price) : null,
    first_valid_date: firstCollection?.date,
    first_valid_price: Number.isFinite(firstPrice) ? firstPrice : null,
    last_valid_date: lastCollection?.date,
    last_valid_price: Number.isFinite(lastCollectionPrice) ? lastCollectionPrice : null,
    min_price: prices.length ? Math.min(...prices) : null,
    max_price: prices.length ? Math.max(...prices) : null,
    distinct_price_count: distinct.length,
    has_price_change: distinct.length > 1,
    price_changed_dates: changedDates,
    price_change_summary: changedDates.length ? `采集日价格发生变化：${changedDates.join(", ")}` : "采集日价格未变化",
    collection_price_change_pct: Number.isFinite(firstPrice) && firstPrice > 0 && Number.isFinite(lastCollectionPrice) ? (lastCollectionPrice - firstPrice) / firstPrice : null,
    price_change_pct: previous && Number(previous.price) ? (Number(latest.price) - Number(previous.price)) / Number(previous.price) : null,
    price_source: latest?.price_source,
  };
}

function bestComparabilityLevel(seriesList) {
  const rank = { base: 0, strong_match: 1, adjusted_match: 2, weak_match: 3, unknown: 4, missing_competitor: 5 };
  return seriesList.slice().sort((a, b) => (rank[a.comparability_level] ?? 9) - (rank[b.comparability_level] ?? 9))[0]?.comparability_level || "unknown";
}

function mergeRegionalPointsForDisplay(items) {
  const grouped = new Map();
  stableArray(items).forEach((series) => {
    Object.entries(series.regional_points || {}).forEach(([region, points]) => {
      const regionLabel = normalizeRegionLabel(region);
      if (!regionLabel) return;
      stableArray(points).forEach((point) => {
        if (!isRealDateLabel(point.date) || point.price === null || point.price === undefined || point.price === "") return;
        const regionMap = grouped.get(regionLabel) || new Map();
        const list = regionMap.get(point.date) || [];
        list.push({ point, series });
        regionMap.set(point.date, list);
        grouped.set(regionLabel, regionMap);
      });
    });
  });

  const result = {};
  grouped.forEach((dateMap, region) => {
    const points = [...dateMap.entries()]
      .sort((a, b) => sortDateLabel(a[0]).localeCompare(sortDateLabel(b[0])))
      .map(([date, entries]) => ({ date, ...pickWeightedPoint(entries) }))
      .filter((point) => point.price !== null && point.price !== undefined);
    if (points.length) result[region] = points;
  });
  return result;
}

function buildSelectedRegionPoints(series, regions) {
  const regionalPoints = series.regional_points || {};
  const byDate = new Map();
  stableArray(regions).forEach((region) => {
    stableArray(regionalPoints[region]).forEach((point) => {
      if (!isRealDateLabel(point.date) || point.price === null || point.price === undefined || point.price === "") return;
      const list = byDate.get(point.date) || [];
      list.push({ point: { ...point, selected_region: region }, series });
      byDate.set(point.date, list);
    });
  });
  return [...byDate.entries()]
    .sort((a, b) => sortDateLabel(a[0]).localeCompare(sortDateLabel(b[0])))
    .map(([date, entries]) => {
      const chosen = pickWeightedPoint(entries);
      if (!chosen) return null;
      return {
        ...chosen,
        date,
        price_source: chosen.price_source || "selected_region_majority_price",
        selected_regions: stableArray(regions).join("; "),
        selected_region_count: stableArray(regions).length,
        region_display_mode: "selected_regions_merged",
      };
    })
    .filter((point) => point && point.price !== null && point.price !== undefined && point.price !== "");
}

function makeRegionDisplayTrendSeries(seriesList, selectedRegions, regionDisplayMode = "merged") {
  if (regionDisplayMode !== "regional") return seriesList;
  const regions = [...selectedRegions].map(normalizeRegionLabel).filter(Boolean).sort((a, b) => a.localeCompare(b));
  if (!regions.length) return [];
  return stableArray(seriesList).map((series) => {
    const regionalPoints = series.regional_points || {};
    const points = buildSelectedRegionPoints(series, regions);
    if (!points.some((point) => point.price !== null && point.price !== undefined && point.price !== "")) return null;
    const stats = buildTrendStatsFromPoints(points);
    const baseName = getSeriesDisplayName(series);
    return {
      ...series,
      ...stats,
      series_id: `${getSeriesKey(series)}::selected_regions::${regions.join("|")}`,
      points,
      display_name: baseName,
      line_name: baseName,
      machine_room_region: regions.join(" / "),
      region_display_mode: "selected_regions_merged",
      selected_region_count: regions.length,
      active_selected_regions: regions,
      available_regions: Object.keys(regionalPoints || {}).sort(),
    };
  }).filter(Boolean);
}

function makeRegionExpandedTrendSeries(seriesList, selectedRegions, regionDisplayMode = "merged") {
  if (regionDisplayMode !== "regional") return stableArray(seriesList);
  const regions = [...selectedRegions].map(normalizeRegionLabel).filter(Boolean).sort((a, b) => a.localeCompare(b));
  if (!regions.length) return [];
  const expanded = [];
  stableArray(seriesList).forEach((series) => {
    const regionalPoints = series.regional_points || {};
    const baseName = getSeriesDisplayName(series);
    regions.forEach((region) => {
      const points = stableArray(regionalPoints[region])
        .filter((point) => isRealDateLabel(point.date) && point.price !== null && point.price !== undefined && point.price !== "")
        .map((point) => ({
          ...point,
          selected_region: region,
          selected_regions: region,
          selected_region_count: 1,
          region_display_mode: "single_region",
          price_source: point.price_source || "selected_region_price",
        }));
      if (!points.length) return;
      const stats = buildTrendStatsFromPoints(points);
      expanded.push({
        ...series,
        ...stats,
        series_id: `${getSeriesKey(series)}::region::${region}`,
        points,
        display_name: `${baseName} · ${region}`,
        line_name: `${baseName} · ${region}`,
        product_line_display_name: baseName,
        machine_room_region: region,
        region_display_mode: "single_region",
        selected_region_count: 1,
        active_selected_regions: [region],
        available_regions: Object.keys(regionalPoints || {}).sort(),
      });
    });
  });
  return expanded;
}

function collectRegionOptionsFromSeries(seriesList) {
  const values = new Set();
  stableArray(seriesList).forEach((series) => {
    const regions = series.available_regions && series.available_regions.length ? series.available_regions : Object.keys(series.regional_points || {});
    stableArray(regions).forEach((region) => {
      const label = normalizeRegionLabel(region);
      if (label) values.add(label);
    });
  });
  return [...values].sort((a, b) => a.localeCompare(b));
}

function cleanProductModelForProductLine(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  // Product-line controls must never expose machine-room labels.
  // Defensive cleanup for legacy/generated labels such as "UVIP 30天 · Hong Kong".
  return text
    .split(/\s*[·•]\s*/)[0]
    .replace(/\s+\d+\s*天\s*$/u, "")
    .trim();
}

function productLineDisplayName(series) {
  const platform = series.platform || "";
  const product = cleanProductModelForProductLine(series.product_model || series.ug_product_model || "");
  const duration = series.duration_display || bucketLabel(series.duration_bucket);
  const android = series.android_display_mode === "expanded" ? androidVersionText(series) : "";
  const androidPart = android ? `Android ${android}` : "";
  return `${platform} ${product} ${androidPart} ${duration}`.replace(/\s+/g, " ").trim();
}

function productLineGroupKey(series) {
  const android = series.android_display_mode === "expanded" ? androidVersionText(series) : "";
  return [
    series.platform || "",
    cleanProductModelForProductLine(series.product_model || series.ug_product_model || ""),
    series.duration_bucket ?? "",
    android,
  ].join("||");
}

function mergeSeriesForProductLineDisplay(items, groupIndex = 0) {
  const sourceItems = stableArray(items).filter(Boolean);
  const base = sourceItems[0] || {};
  const pointsByDate = new Map();
  sourceItems.forEach((series) => {
    stableArray(series.points).forEach((point) => {
      if (!isRealDateLabel(point.date) || point.price === null || point.price === undefined || point.price === "") return;
      const list = pointsByDate.get(point.date) || [];
      list.push({ point, series });
      pointsByDate.set(point.date, list);
    });
  });
  const points = [...pointsByDate.entries()]
    .sort((a, b) => sortDateLabel(a[0]).localeCompare(sortDateLabel(b[0])))
    .map(([date, entries]) => ({ date, ...pickWeightedPoint(entries) }))
    .filter((point) => point.price !== null && point.price !== undefined);
  const stats = buildTrendStatsFromPoints(points);
  const displayName = productLineDisplayName(base);
  const regions = collectRegionOptionsFromSeries(sourceItems);
  const androidVersions = [...new Set(sourceItems.flatMap(seriesAndroidVersions))].sort((a, b) => Number(a) - Number(b) || String(a).localeCompare(String(b)));
  return {
    ...base,
    ...stats,
    series_id: `product_line::${productLineGroupKey(base)}::${groupIndex}`.replace(/[^a-zA-Z0-9_一-龥|:-]/g, "_"),
    points,
    display_name: displayName,
    line_name: displayName,
    config: base.config,
    machine_room_region: null,
    active_selected_regions: regions,
    available_regions: regions,
    regional_points: mergeRegionalPointsForDisplay(sourceItems),
    comparability_level: bestComparabilityLevel(sourceItems),
    config_similarity_score: Math.max(...sourceItems.map((series) => Number(series.config_similarity_score)).filter(Number.isFinite), Number(base.config_similarity_score) || 0) || base.config_similarity_score,
    source_series_count: sourceItems.length,
    display_android_versions: base.android_display_mode === "expanded" ? seriesAndroidVersions(base) : [],
    merged_android_versions: base.android_display_mode === "expanded" ? seriesAndroidVersions(base) : androidVersions,
    product_line_grouped: true,
    children_line_names: sourceItems.map(getSeriesDisplayName),
  };
}

function makeProductLineCandidateSeries(seriesList) {
  const groups = new Map();
  stableArray(seriesList).forEach((series) => {
    const key = productLineGroupKey(series);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(series);
  });
  return [...groups.values()]
    .map((items, index) => mergeSeriesForProductLineDisplay(items, index))
    .filter((series) => stableArray(series.points).some((point) => point.price !== null && point.price !== undefined && point.price !== ""))
    .sort(sortSeriesForDecision);
}

function makeDisplayTrendSeries(seriesList, androidDisplayMode = "merged") {
  const raw = stableArray(seriesList);
  if (androidDisplayMode === "expanded") {
    return raw.flatMap((series) => {
      const children = stableArray(series.android_breakdown_series)
        .filter((child) => stableArray(child.points).some((point) => point.price !== null && point.price !== undefined && point.price !== ""));
      if (children.length) {
        return children.map((child) => {
          const versions = seriesAndroidVersions(child);
          const displayName = expandedTrendSeriesName({ ...series, ...child, display_android_versions: versions });
          return {
            ...series,
            ...child,
            parent_series_id: getSeriesKey(series),
            product_model: child.product_model || series.product_model,
            ug_product_model: child.ug_product_model || series.ug_product_model,
            display_name: displayName,
            line_name: displayName,
            android_display_mode: "expanded",
            display_android_versions: versions,
            merged_android_versions: versions,
            android_versions: versions,
          };
        });
      }
      return [{
        ...series,
        display_name: expandedTrendSeriesName(series),
        android_display_mode: "expanded",
        display_android_versions: seriesAndroidVersions(series),
      }];
    }).sort(sortSeriesForDecision);
  }

  const groups = new Map();
  raw.forEach((series) => {
    const key = [
      series.platform || "",
      series.product_model || series.ug_product_model || "",
      series.duration_bucket ?? "",
      series.ug_product_model || "",
    ].join("||");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(series);
  });

  return [...groups.values()].map((items, groupIndex) => {
    if (items.length === 1) {
      const single = items[0];
      return {
        ...single,
        display_name: mergedTrendSeriesName(single),
        android_display_mode: "merged",
        display_android_versions: seriesAndroidVersions(single),
        source_series_count: 1,
        available_regions: Object.keys(single.regional_points || {}).sort(),
      };
    }
    const base = items[0];
    const pointsByDate = new Map();
    items.forEach((series) => {
      stableArray(series.points).forEach((point) => {
        if (!isRealDateLabel(point.date) || point.price === null || point.price === undefined || point.price === "") return;
        const list = pointsByDate.get(point.date) || [];
        list.push({ point, series });
        pointsByDate.set(point.date, list);
      });
    });
    const points = [...pointsByDate.entries()]
      .sort((a, b) => sortDateLabel(a[0]).localeCompare(sortDateLabel(b[0])))
      .map(([date, entries]) => ({ date, ...pickWeightedPoint(entries) }))
      .filter((point) => point.price !== null && point.price !== undefined);
    const versions = [...new Set(items.flatMap(seriesAndroidVersions))].sort((a, b) => Number(a) - Number(b) || String(a).localeCompare(String(b)));
    const ugConfigIds = [...new Set(items.flatMap((series) => [series.ug_config_id, ...stableArray(series.ug_config_ids)].filter(Boolean)))];
    const stats = buildTrendStatsFromPoints(points);
    return {
      ...base,
      ...stats,
      series_id: `merged_android::${base.platform || ""}::${base.product_model || base.ug_product_model || ""}::${base.duration_bucket ?? ""}::${base.ug_product_model || ""}::${groupIndex}`,
      display_name: mergedTrendSeriesName(base),
      line_name: mergedTrendSeriesName(base),
      config: `合并 Android ${versions.length ? versions.join("/") : "未识别"}`,
      points,
      comparability_level: bestComparabilityLevel(items),
      config_similarity_score: Math.max(...items.map((series) => Number(series.config_similarity_score)).filter(Number.isFinite), Number(base.config_similarity_score) || 0) || base.config_similarity_score,
      merged_series_count: items.reduce((sum, series) => sum + seriesPointWeight(series), 0),
      source_series_count: items.length,
      merged_android_versions: versions,
      display_android_versions: versions,
      ug_config_ids: ugConfigIds,
      android_display_mode: "merged",
      regional_points: mergeRegionalPointsForDisplay(items),
      available_regions: Object.keys(mergeRegionalPointsForDisplay(items)).sort(),
      children_line_names: items.map(getSeriesDisplayName),
    };
  }).sort(sortSeriesForDecision);
}

function makeWideChartRows(seriesList) {
  const byDate = new Map();
  seriesList.forEach((series) => {
    stableArray(series.points).forEach((point) => {
      const row = byDate.get(point.date) || { date: point.date };
      const key = getSeriesChartKey(series);
      row[key] = point.price;
      row[`${key}__source`] = point.price_source;
      row[`${key}__label`] = getSeriesDisplayName(series);
      row[`${key}__carried_from_date`] = point.carried_from_date;
      row[`${key}__source_collection_date`] = point.source_collection_date;
      byDate.set(point.date, row);
    });
  });
  return [...byDate.values()].sort((a, b) => sortDateLabel(a.date).localeCompare(sortDateLabel(b.date)));
}

function latestPoint(series) {
  const points = stableArray(series.points).filter((point) => point.price !== null && point.price !== undefined && point.price !== "");
  return points[points.length - 1];
}

function buildCompositeIndexRows(seriesList) {
  const indexRows = [];
  const platformDateValues = new Map();
  const ugBaseCandidates = [];
  const allBaseCandidates = [];

  seriesList.forEach((series) => {
    stableArray(series.points).forEach((point) => {
      const price = Number(point.price);
      if (!Number.isFinite(price) || price <= 0 || !isRealDateLabel(point.date)) return;
      allBaseCandidates.push({ date: point.date, price, platform: series.platform });
      if (series.platform === "UgPhone") {
        ugBaseCandidates.push({ date: point.date, price, platform: series.platform });
      }
    });
  });

  const chooseBase = (candidates, preferredDate) => {
    if (!candidates.length) return { date: null, prices: [] };
    const candidateDates = [...new Set(candidates.map((point) => point.date))].sort((a, b) => sortDateLabel(a).localeCompare(sortDateLabel(b)));
    const baseDate = preferredDate && candidateDates.includes(preferredDate) ? preferredDate : candidateDates[0];
    return { date: baseDate, prices: candidates.filter((point) => point.date === baseDate).map((point) => point.price) };
  };

  let base = chooseBase(ugBaseCandidates, "2026-04-28");
  let baseMode = "UgPhone均价";
  if (!base.prices.length) {
    base = chooseBase(allBaseCandidates, null);
    baseMode = "该档位首个可用采集日的全部可用平台均价";
  }
  const baseAverage = base.prices.length ? base.prices.reduce((sum, value) => sum + value, 0) / base.prices.length : null;

  if (!Number.isFinite(baseAverage) || baseAverage <= 0) return indexRows;

  seriesList.forEach((series) => {
    stableArray(series.points).forEach((point) => {
      const price = Number(point.price);
      if (!Number.isFinite(price) || price <= 0 || !isRealDateLabel(point.date)) return;
      const key = `${series.platform}__${point.date}`;
      const values = platformDateValues.get(key) || [];
      values.push((price / baseAverage) * 100);
      platformDateValues.set(key, values);
    });
  });

  const dates = new Set();
  platformDateValues.forEach((_, key) => dates.add(key.split("__")[1]));
  [...dates].sort((a, b) => sortDateLabel(a).localeCompare(sortDateLabel(b))).forEach((date) => {
    const row = { date, __index_base_date: base.date, __index_base_price: baseAverage, __index_base_mode: baseMode };
    allPlatforms.forEach((platform) => {
      const values = platformDateValues.get(`${platform}__${date}`) || [];
      row[platform] = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
      row[`${platform}__count`] = values.length;
    });
    indexRows.push(row);
  });
  return indexRows;
}

function platformOrderValue(platform) {
  const order = { UgPhone: 0, VSPhone: 1, Redfinger: 2, LDCloud: 3 };
  return order[platform] ?? 99;
}

function productSortValue(model) {
  const order = { UVIP: 0, GVIP: 1, KVIP: 2, VIP: 3, XVIP: 4, MVIP: 5, SVIP: 6, Basic: 7 };
  return order[String(model || "")] ?? 50;
}

function seriesPriceForSort(series) {
  const point = latestPoint(series);
  const price = Number(point?.price ?? series.current_price);
  return Number.isFinite(price) ? price : Number.POSITIVE_INFINITY;
}

function sortSeriesForDecision(a, b) {
  return platformOrderValue(a.platform) - platformOrderValue(b.platform)
    || productSortValue(a.product_model) - productSortValue(b.product_model)
    || seriesPriceForSort(a) - seriesPriceForSort(b)
    || String(a.product_model || "").localeCompare(String(b.product_model || ""))
    || String(a.config || "").localeCompare(String(b.config || ""));
}

function TrendsTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="relative z-[9999] rounded-lg border border-line bg-white p-3 text-xs shadow-2xl">
      <div className="mb-2 font-bold">日期：{label}</div>
      <div className="grid gap-2">
        {payload.map((item) => {
          const source = item.payload?.[`${item.dataKey}__source`];
          const carriedFromDate = item.payload?.[`${item.dataKey}__carried_from_date`];
          const sourceCollectionDate = item.payload?.[`${item.dataKey}__source_collection_date`];
          const count = item.payload?.[`${item.dataKey}__count`];
          return (
            <div key={item.dataKey} style={{ color: item.color }}>
              <div className="font-semibold">{item.name || item.payload?.[`${item.dataKey}__label`] || item.dataKey}</div>
              <div>{String(item.name || item.dataKey).includes("综合指数") || allPlatforms.includes(item.dataKey) ? `指数：${indexValue(item.value)}` : `价格：${money(item.value)}`}</div>
              {item.payload?.__index_base_date ? <div>指数基准：{item.payload.__index_base_date} {item.payload.__index_base_mode || "UgPhone均价"}=100</div> : null}
              {count !== undefined ? <div>纳入产品线：{count} 条</div> : null}
              {source ? <div>price_source：{source}</div> : null}
              {source === "carry_forward" ? <div className="text-slate-600">当天未采集，沿用上一采集日价格{carriedFromDate ? `（${carriedFromDate}）` : ""}</div> : null}
              {source !== "carry_forward" && sourceCollectionDate && sourceCollectionDate !== label ? <div className="text-slate-600">来源采集日：{sourceCollectionDate}</div> : null}
              {source === "baseline_fallback" ? <div className="text-slate-600">当日缺失，沿用 baseline</div> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ScrollableChartLegend({ payload }) {
  const items = stableArray(payload);
  if (!items.length) return null;
  return (
    <div className="mx-auto mt-2 max-h-20 overflow-y-auto rounded-md border border-line bg-white/90 px-3 py-2 text-xs shadow-sm">
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {items.map((item, index) => (
          <span
            className="inline-flex max-w-[260px] items-center gap-1.5 truncate"
            key={`${item.value || item.dataKey || "legend"}-${index}`}
            title={item.value}
          >
            <span className="h-2 w-4 shrink-0 rounded-full" style={{ backgroundColor: item.color || "#94a3b8" }} />
            <span className="truncate text-slate-700">{item.value}</span>
          </span>
        ))}
      </div>
    </div>
  );
}


function CheckboxChip({ checked, onChange, label, color }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-line bg-white px-3 py-1.5 text-xs font-semibold text-ink hover:bg-slate-50">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color || "#94a3b8" }} />
      {label}
    </label>
  );
}


function seriesMatchesConfig(series, configId) {
  if (configId === "all") return true;
  const target = String(configId);
  if (target.startsWith("ug_product_model::")) {
    const expected = target.replace("ug_product_model::", "");
    return String(series.ug_product_model || series.product_model || "") === expected;
  }
  if (String(series.ug_config_id) === target) return true;
  if (Array.isArray(series.ug_config_ids) && series.ug_config_ids.map(String).includes(target)) return true;
  return false;
}

function TrendsPage({ data }) {
  const payload = normalizeTrendsPayload(data.priceTrends);
  const [indexBucket, setIndexBucket] = useState("30");
  const [detailBucket, setDetailBucket] = useState("30");
  const [configId, setConfigId] = useState("");
  const [brandFocus, setBrandFocus] = useState("paired");
  const [platformFilter, setPlatformFilter] = useState(() => new Set(allPlatforms));
  const [levelMode, setLevelMode] = useState("all");
  const [changeMode, setChangeMode] = useState("all");
  const [androidDisplayMode, setAndroidDisplayMode] = useState("merged");
  const [regionDisplayMode, setRegionDisplayMode] = useState("merged");
  const [selectedRegions, setSelectedRegions] = useState(() => new Set());
  const [search, setSearch] = useState("");
  const [selectedSeriesIds, setSelectedSeriesIds] = useState(null);
  const [trendDetailCache, setTrendDetailCache] = useState({});
  const [trendDetailLoading, setTrendDetailLoading] = useState(false);
  const [trendDetailError, setTrendDetailError] = useState("");
  const platformFilterKey = [...platformFilter].sort().join("||");

  const configOptions = useMemo(() => {
    const map = new Map();
    stableArray(payload.series).forEach((series) => {
      if (series.platform !== "UgPhone") return;
      const product = series.ug_product_model || series.product_model;
      if (!product) return;
      map.set(`ug_product_model::${product}`, `UgPhone ${product}`);
    });
    return [...map.entries()].sort((a, b) => {
      const aProduct = String(a[1] || "").replace("UgPhone ", "");
      const bProduct = String(b[1] || "").replace("UgPhone ", "");
      const aIsUvip = String(a[1] || "").includes("UVIP") ? -1 : 0;
      const bIsUvip = String(b[1] || "").includes("UVIP") ? -1 : 0;
      return aIsUvip - bIsUvip || productSortValue(aProduct) - productSortValue(bProduct) || String(a[1]).localeCompare(String(b[1]));
    });
  }, [payload.series]);

  const defaultConfigId = useMemo(() => configOptions.find(([, label]) => String(label || "").includes("UVIP"))?.[0] || configOptions[0]?.[0] || "all", [configOptions]);
  const effectiveConfigId = configId || defaultConfigId;

  const indexSeries = useMemo(() => {
    return stableArray(payload.series).filter((series) => {
      if (String(series.duration_bucket) !== String(indexBucket)) return false;
      return ["base", "strong_match", "adjusted_match", "historical_unmatched"].includes(series.comparability_level);
    });
  }, [payload.series, indexBucket]);
  const compositeRows = useMemo(() => buildCompositeIndexRows(indexSeries), [indexSeries]);

  const baseRawDetailSeries = useMemo(() => {
    const focusedBrand = brandFocus !== "paired" ? brandFocus : null;
    const filterRawSeries = (ignorePairedConfig = false) => stableArray(payload.series).filter((series) => {
      if (String(series.duration_bucket) !== String(detailBucket)) return false;
      if (focusedBrand) {
        if (series.platform !== focusedBrand) return false;
      } else {
        if (!ignorePairedConfig && !seriesMatchesConfig(series, effectiveConfigId)) return false;
        if (!platformFilter.has(series.platform)) return false;
        if (levelMode === "strong" && !["base", "strong_match"].includes(series.comparability_level)) return false;
        if (levelMode === "core" && !["base", "strong_match", "adjusted_match"].includes(series.comparability_level)) return false;
        if (levelMode === "weak" && !["base", "strong_match", "adjusted_match", "weak_match", "historical_unmatched"].includes(series.comparability_level)) return false;
      }
      return true;
    });
    const rawSeries = filterRawSeries(false);
    // Some short/medium competitor durations (for example 3天或60天) may not have
    // an UgPhone paired line.  In paired mode, fall back to all product lines for
    // the selected bucket instead of showing an empty chart.
    if (!focusedBrand && rawSeries.length === 0) return filterRawSeries(true);
    return rawSeries;
  }, [payload.series, detailBucket, effectiveConfigId, platformFilter, levelMode, brandFocus]);

  const neededTrendDetailFiles = useMemo(() => {
    const files = new Set();
    stableArray(baseRawDetailSeries).forEach((series) => {
      const file = normalizeTrendDetailFile(series.trend_detail_chunk);
      if (file) files.add(file);
    });
    return [...files].sort();
  }, [baseRawDetailSeries]);
  const neededTrendDetailKey = neededTrendDetailFiles.join("||");

  useEffect(() => {
    let cancelled = false;
    const missingFiles = neededTrendDetailFiles.filter((file) => !trendDetailCache[file]);
    if (!missingFiles.length) {
      setTrendDetailLoading(false);
      return () => { cancelled = true; };
    }
    setTrendDetailLoading(true);
    setTrendDetailError("");
    loadTrendDetailChunks(missingFiles)
      .then((chunks) => {
        if (cancelled) return;
        setTrendDetailCache((prev) => ({ ...prev, ...chunks }));
        setTrendDetailLoading(false);
      })
      .catch((error) => {
        if (cancelled) return;
        setTrendDetailError(error?.message || String(error));
        setTrendDetailLoading(false);
      });
    return () => { cancelled = true; };
  }, [neededTrendDetailKey]);

  const trendDetailMap = useMemo(() => buildTrendDetailMap(trendDetailCache), [trendDetailCache]);
  const enhancedRawDetailSeries = useMemo(
    () => baseRawDetailSeries.map((series) => applyTrendDetailToSeries(series, trendDetailMap)),
    [baseRawDetailSeries, trendDetailMap],
  );

  const baseDisplaySeries = useMemo(() => makeDisplayTrendSeries(enhancedRawDetailSeries, androidDisplayMode), [enhancedRawDetailSeries, androidDisplayMode]);

  const regionControlLocked = brandFocus === "paired";
  const regionOptionSourceSeries = useMemo(() => {
    if (regionControlLocked) return [];
    if (brandFocus === "paired") {
      const ugSeries = baseDisplaySeries.filter((series) => series.platform === "UgPhone");
      return ugSeries.length ? ugSeries : baseDisplaySeries;
    }
    return baseDisplaySeries;
  }, [baseDisplaySeries, brandFocus, regionControlLocked]);
  const regionOptions = useMemo(() => {
    if (regionControlLocked) return [];
    return collectRegionOptionsFromSeries(regionOptionSourceSeries);
  }, [regionOptionSourceSeries, regionControlLocked]);
  const regionOptionsKey = regionOptions.join("||");
  const regionScopeKey = [brandFocus, detailBucket, effectiveConfigId, platformFilterKey, levelMode, androidDisplayMode].join("||");
  const activeRegionDisplayMode = regionControlLocked ? "merged" : regionDisplayMode;
  const activeSelectedRegions = activeRegionDisplayMode === "regional" ? selectedRegions : new Set();
  const selectedRegionKey = `${activeRegionDisplayMode}::${[...activeSelectedRegions].sort().join("||")}`;
  const regionStatusLabel = activeRegionDisplayMode === "regional"
    ? (activeSelectedRegions.size ? `（按 ${activeSelectedRegions.size} 个机房分别展开）` : "（机房未选择）")
    : "（合并所有机房）";

  const resetRegionDisplayToMerged = () => {
    setRegionDisplayMode("merged");
    setSelectedRegions(new Set());
  };

  const changeAndroidDisplayMode = (value) => {
    setAndroidDisplayMode(value);
    resetRegionDisplayToMerged();
    setSelectedSeriesIds(null);
  };

  useEffect(() => {
    resetRegionDisplayToMerged();
  }, [regionScopeKey]);

  useEffect(() => {
    setSelectedRegions((prev) => {
      const valid = new Set(regionOptions);
      const next = new Set([...prev].filter((region) => valid.has(region)));
      if (next.size === prev.size) return prev;
      return next;
    });
  }, [regionOptionsKey]);

  const selectMergedRegionDisplay = () => {
    if (regionControlLocked) return;
    setRegionDisplayMode("merged");
    setSelectedRegions(new Set());
  };

  const selectAllRegions = () => {
    if (regionControlLocked) return;
    setRegionDisplayMode("regional");
    setSelectedRegions(new Set(regionOptions));
  };

  const clearRegions = () => {
    if (regionControlLocked) return;
    setRegionDisplayMode("regional");
    setSelectedRegions(new Set());
  };

  const toggleRegion = (region, checked) => {
    if (regionControlLocked) return;
    const label = normalizeRegionLabel(region);
    if (!label) return;
    setRegionDisplayMode("regional");
    setSelectedRegions((prev) => {
      const next = new Set(prev);
      if (checked) next.add(label);
      else next.delete(label);
      return next;
    });
  };

  const androidBreakdownSeriesCount = useMemo(() => {
    return enhancedRawDetailSeries.reduce((sum, series) => sum + stableArray(series.android_breakdown_series).length, 0);
  }, [enhancedRawDetailSeries]);
  const expandedAndroidDataMissing = androidDisplayMode === "expanded"
    && !trendDetailLoading
    && androidBreakdownSeriesCount === 0
    && enhancedRawDetailSeries.some((series) => seriesAndroidVersions(series).length > 1);

  const candidateSeries = useMemo(() => {
    const q = search.trim().toLowerCase();
    const displaySeries = makeProductLineCandidateSeries(baseDisplaySeries);
    return displaySeries.filter((series) => {
      if (changeMode === "changed" && !series.has_price_change) return false;
      if (changeMode === "unchanged" && series.has_price_change) return false;
      if (!q) return true;
      return textOf(
        series.platform,
        series.product_model,
        series.config,
        series.line_name,
        series.display_name,
        series.ug_product_model,
        series.price_change_summary,
        series.machine_room_region,
        stableArray(series.display_android_versions).join("/"),
      ).includes(q);
    }).sort(sortSeriesForDecision);
  }, [baseDisplaySeries, changeMode, search]);

  useEffect(() => {
    setSelectedSeriesIds(null);
  }, [detailBucket, effectiveConfigId, platformFilter, levelMode, changeMode, androidDisplayMode, selectedRegionKey, search, brandFocus]);

  const seriesColorMap = useMemo(() => {
    const counts = {};
    const map = new Map();
    candidateSeries.forEach((series) => {
      const index = counts[series.platform] || 0;
      counts[series.platform] = index + 1;
      map.set(getSeriesKey(series), platformSeriesColor(series.platform, index));
    });
    return map;
  }, [candidateSeries]);


  const defaultDetailSeries = useMemo(() => {
    if (brandFocus !== "paired") return candidateSeries;
    const byPlatform = new Map();
    candidateSeries.forEach((series) => {
      if (!byPlatform.has(series.platform)) byPlatform.set(series.platform, series);
    });
    return allPlatforms.map((platform) => byPlatform.get(platform)).filter(Boolean);
  }, [candidateSeries, brandFocus]);

  const detailSeries = useMemo(() => {
    if (selectedSeriesIds === null) return defaultDetailSeries;
    return candidateSeries.filter((series) => selectedSeriesIds.has(getSeriesKey(series)));
  }, [candidateSeries, selectedSeriesIds, defaultDetailSeries]);
  const chartSeries = useMemo(() => makeRegionExpandedTrendSeries(detailSeries, activeSelectedRegions, activeRegionDisplayMode), [detailSeries, activeRegionDisplayMode, selectedRegionKey]);
  const detailRows = useMemo(() => makeWideChartRows(chartSeries), [chartSeries]);

  const chartSeriesColorMap = useMemo(() => {
    const counts = {};
    const map = new Map();
    chartSeries.forEach((series) => {
      const index = counts[series.platform] || 0;
      counts[series.platform] = index + 1;
      map.set(getSeriesKey(series), platformSeriesColor(series.platform, index));
    });
    return map;
  }, [chartSeries]);

  const platformToggle = (platform, checked) => {
    setPlatformFilter((prev) => {
      const next = new Set(prev);
      if (checked) next.add(platform);
      else next.delete(platform);
      return next;
    });
  };

  const selectedCount = detailSeries.length;
  const chartLineCount = chartSeries.length;
  const usingDefaultSelection = selectedSeriesIds === null;
  const otherPaidPrices = useMemo(() => {
    const q = search.trim().toLowerCase();
    const focusedBrand = brandFocus !== "paired" ? brandFocus : null;
    const filteredRows = stableArray(payload.other_paid_prices).filter((row) => {
      if (String(row.duration_bucket) !== String(detailBucket)) return false;
      if (focusedBrand) {
        if (row.platform !== focusedBrand) return false;
      } else if (!platformFilter.has(row.platform)) return false;
      if (activeRegionDisplayMode === "regional") {
        if (!activeSelectedRegions.size) return false;
        const rowRegions = splitRegionText(row.selected_regions || row.supported_server_regions || row.server_region);
        if (!rowRegions.some((region) => activeSelectedRegions.has(region))) return false;
      }
      if (!q) return true;
      return textOf(row.platform, row.product_model, row.promotion_text, row.price_variant_label, row.selected_regions).includes(q);
    });
    const latestDate = filteredRows
      .map((row) => row.date)
      .filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(String(date || "")))
      .sort()
      .pop();
    const latestRows = latestDate ? filteredRows.filter((row) => row.date === latestDate) : filteredRows;
    const deduped = new Map();
    latestRows.forEach((row) => {
      const key = [
        row.platform,
        row.product_model,
        row.duration_bucket,
        row.duration_display,
        row.price_variant,
        row.raw_price,
        row.unit_device_price,
        row.device_count,
        row.promotion_text,
      ].map((value) => String(value ?? "").trim()).join("||");
      if (!deduped.has(key)) deduped.set(key, row);
    });
    return [...deduped.values()]
      .sort((a, b) => platformOrderValue(a.platform) - platformOrderValue(b.platform) || Number(a.unit_device_price || 0) - Number(b.unit_device_price || 0))
      .slice(0, 60);
  }, [payload.other_paid_prices, detailBucket, platformFilter, selectedRegionKey, search, brandFocus, activeRegionDisplayMode]);

  return (
    <div className="space-y-6">
      <InfoCard title="本页怎么看">
        本页分成两个图：图一用“2026-04-28 UgPhone均价=100”作为全局基准，观察四个平台的整体价格水平和变化方向；图二既可以按 UgPhone 配对组查看四家对应产品，也可以直接选择某个品牌展示该品牌全部产品线，并可用“机房展示方式”在“合并所有机房”和具体机房多选之间切换。图表横轴按自然日连续展示，但数据按采集日处理：没有采集的自然日会沿用上一采集日价格，并在鼠标悬停小弹窗中标记 carry_forward。核心趋势默认排除新客价、试用价、渠道秒杀价和多设备组合包；同产品多机房价格按“多数机房价格优先，数量持平选低价”。注意：7天档中 LDCloud 使用8天套餐参与比较，因为 LDCloud 无7天购买时限。
      </InfoCard>

      <section className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold">图一：四家综合价格指数变化</h2>
            <p className="mt-1 text-sm text-muted">价格指数定义：选定消费时长下，以 2026-04-28 的 UgPhone 产品均价作为 100；其他平台/日期的指数 = 当日该平台纳入产品线均价 ÷ 4月28日 UgPhone基准均价 × 100。横轴按自然日展示，5月1日至5月5日这类未采集日期会显示上一采集日价格，并在 tooltip 中标记 carry_forward。7天档中，LDCloud 使用8天套餐参与比较；1天、3天、15天、60天等真实购买天数会作为独立档位展示，不再并入其他。指数越高，代表相对该基准越贵。</p>
          </div>
          <SelectFilter label="消费时长" value={indexBucket} onChange={setIndexBucket}>{[...coreBuckets, "other"].map((item) => <option key={item} value={item}>{bucketLabel(item)}</option>)}</SelectFilter>
        </div>
        <div className="mt-4 h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={compositeRows}>
              <CartesianGrid stroke="#dfe5f0" strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis domain={["auto", "auto"]} />
              <Tooltip content={<TrendsTooltip />} wrapperStyle={{ zIndex: 9999, pointerEvents: "none" }} />
              <Legend />
              {allPlatforms.map((platform) => (
                <Line
                  key={platform}
                  type="monotone"
                  dataKey={platform}
                  name={`${platform} 综合指数`}
                  stroke={platformColors[platform]}
                  strokeWidth={platform === "UgPhone" ? 3 : 2.5}
                  dot
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="panel p-5">
        <h2 className="text-lg font-bold">图二：具体产品价格趋势</h2>
        <p className="mt-1 text-sm text-muted">默认展示 “UgPhone UVIP” 配对组下四个平台各一条核心产品线；你也可以切换为某个品牌全集，直接查看该品牌所有产品线。机房展示方式会随当前查看范围变化：切换“查看方式”后默认回到“合并所有机房”；只有手动勾选具体机房或点击“全选”时，才会按“产品线 × 机房”分别绘制折线。按 UgPhone 配对组会锁定为合并所有机房。清空后不会自动重新勾选产品线。</p>
        <div className="mt-4 grid gap-3 md:grid-cols-7">
          <SelectFilter label="购买天数" value={detailBucket} onChange={setDetailBucket}>{[...coreBuckets, "other"].map((item) => <option key={item} value={item}>{bucketLabel(item)}</option>)}</SelectFilter>
          <SelectFilter label="查看方式" value={brandFocus} onChange={(value) => { setBrandFocus(value); resetRegionDisplayToMerged(); }}>
            <option value="paired">按 UgPhone 配对组</option>
            {allPlatforms.map((platform) => <option key={platform} value={platform}>{platform} 全部产品</option>)}
          </SelectFilter>
          <label className="grid gap-1 text-xs font-semibold text-muted">
            UgPhone 配对配置
            <select className="rounded-md border border-line bg-white px-3 py-2 text-sm font-medium text-ink disabled:bg-slate-100 disabled:text-slate-400" value={effectiveConfigId} onChange={(event) => setConfigId(event.target.value)} disabled={brandFocus !== "paired"}>
            <option value="all">全部配对组（自由筛选）</option>
            {configOptions.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
          </label>
          <label className="grid gap-1 text-xs font-semibold text-muted">
            竞品配对等级
            <select className="rounded-md border border-line bg-white px-3 py-2 text-sm font-medium text-ink disabled:bg-slate-100 disabled:text-slate-400" value={levelMode} onChange={(event) => setLevelMode(event.target.value)} disabled={brandFocus !== "paired"}><option value="all">全部</option><option value="strong">只看 strong_match</option><option value="core">strong_match + adjusted_match</option><option value="weak">包含 weak_match</option></select>
          </label>
          <SelectFilter label="价格变化" value={changeMode} onChange={setChangeMode}><option value="all">全部</option><option value="changed">只看有变化</option><option value="unchanged">只看未变化</option></SelectFilter>
          <SelectFilter label="安卓版本展示方式" value={androidDisplayMode} onChange={changeAndroidDisplayMode}><option value="merged">合并安卓版本（默认）</option><option value="expanded">展开安卓版本</option></SelectFilter>
          <div className="grid gap-1 text-xs font-semibold text-muted md:col-span-2">
            机房展示方式
            <div className={`rounded-md border border-line bg-white px-3 py-2 ${regionControlLocked ? "bg-slate-100 text-slate-400" : ""}`}>
              <div className="mb-2 flex flex-wrap items-center justify-end gap-2">
                <button
                  className="rounded border border-line bg-white px-2 py-1 text-[11px] font-semibold disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                  disabled={regionControlLocked || !regionOptions.length}
                  onClick={selectAllRegions}
                  type="button"
                >全选</button>
                <button
                  className="rounded border border-line bg-white px-2 py-1 text-[11px] font-semibold disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                  disabled={regionControlLocked || !regionOptions.length}
                  onClick={clearRegions}
                  type="button"
                >清空</button>
              </div>
              <div className="max-h-24 overflow-auto rounded border border-slate-100 bg-slate-50 px-2 py-1.5">
                <div className="flex flex-wrap gap-2">
                  <label className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-2 py-1 text-xs font-semibold ${activeRegionDisplayMode === "merged" ? "border-red-200 bg-red-50 text-red-700" : "border-line bg-white text-ink"}`}>
                    <input
                      type="checkbox"
                      checked={activeRegionDisplayMode === "merged"}
                      disabled={regionControlLocked}
                      onChange={(event) => {
                        if (event.target.checked) selectMergedRegionDisplay();
                        else clearRegions();
                      }}
                      style={{ accentColor: "#dc2626" }}
                    />
                    合并所有机房
                  </label>
                  {regionControlLocked ? (
                    <span className="self-center text-xs font-normal text-muted">按 UgPhone 配对组锁定为合并所有机房。</span>
                  ) : regionOptions.length ? (
                    regionOptions.map((region) => (
                      <label className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-2 py-1 text-xs ${activeRegionDisplayMode === "regional" && selectedRegions.has(region) ? "border-blue-200 bg-blue-50 text-blue-700" : "border-line bg-white text-ink"}`} key={region}>
                        <input
                          type="checkbox"
                          checked={activeRegionDisplayMode === "regional" && selectedRegions.has(region)}
                          onChange={(event) => toggleRegion(region, event.target.checked)}
                          style={{ accentColor: "#2563eb" }}
                        />
                        {region}
                      </label>
                    ))
                  ) : (
                    <span className="self-center text-xs font-normal text-muted">当前查看方式没有可拆分的机房历史数据。</span>
                  )}
                </div>
              </div>
            </div>
            <span className="text-[11px] font-normal text-muted">“合并所有机房”为红色选项；具体机房为蓝色多选。选择任一具体机房时会自动取消合并所有机房。</span>
          </div>
          <SearchFilter label="搜索" value={search} onChange={setSearch} placeholder="搜索平台、产品、配置、机房" />
          <div className="grid gap-1 text-xs font-semibold text-muted">
            平台
            <div className="flex flex-wrap gap-2 rounded-md border border-line bg-white px-3 py-2">
              {allPlatforms.map((platform) => (
                <label className="inline-flex items-center gap-1.5 text-sm text-ink" key={platform}>
                  <input checked={platformFilter.has(platform)} onChange={(event) => platformToggle(platform, event.target.checked)} type="checkbox" />
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: platformColors[platform] }} />
                  {platform}
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4 rounded-xl border border-line bg-slate-50 p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-semibold text-ink">可选产品线：{candidateSeries.length} 条；当前选择 {selectedCount} 条产品线；当前绘制 {chartLineCount} 条折线{regionStatusLabel}{usingDefaultSelection ? (brandFocus === "paired" ? "（默认四平台配对组）" : `（${brandFocus} 全部产品）`) : ""}</div>
            <div className="flex flex-wrap gap-2">
              <button className="rounded-md border border-line bg-white px-3 py-1.5 text-xs font-semibold" onClick={() => setSelectedSeriesIds(null)} type="button">恢复默认展示</button>
              <button className="rounded-md border border-line bg-white px-3 py-1.5 text-xs font-semibold" onClick={() => setSelectedSeriesIds(new Set(candidateSeries.map(getSeriesKey)))} type="button">全选当前筛选</button>
              <button className="rounded-md border border-line bg-white px-3 py-1.5 text-xs font-semibold" onClick={() => setSelectedSeriesIds(new Set())} type="button">清空</button>
            </div>
          </div>
          <p className="mb-3 text-xs text-muted">{activeRegionDisplayMode === "regional" ? (activeSelectedRegions.size ? `当前按上方选中的 ${activeSelectedRegions.size} 个机房分别绘制折线；产品线筛选项只显示套餐，不显示机房。` : "当前为按机房展示，但未选择任何机房；请点击上方全选或勾选具体机房。") : (androidDisplayMode === "merged" ? "已合并 Android 版本和所有机房；少数机房价、新客价、小时包和其他非核心价见下方其他实付价。" : "当前按 Android 版本展开，并合并所有机房；只有真实识别到 Android 版本的产品才会在名称中标明版本，无 Android 区分的产品不强行添加后缀。")}</p>
          {trendDetailLoading ? <p className="mb-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-semibold text-blue-800">正在按需加载当前视图的机房 / Android 细分趋势数据。</p> : null}
          {trendDetailError ? <p className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-800">趋势细分数据加载失败：{trendDetailError}</p> : null}
          {expandedAndroidDataMissing ? <p className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">当前加载的数据没有 Android 细分趋势。请确认已覆盖新版 Skill，并重新运行 python rebuild_dashboard_history.py 后再点击右上角“重新加载看板数据”。</p> : null}
          {candidateSeries.length > 20 ? <p className="mb-3 text-xs text-amber-700">当前候选较多，默认仍只展示四平台配对组。请继续筛选或手动勾选需要的产品线。</p> : null}
          <div className="max-h-44 overflow-auto">
            <div className="flex flex-wrap gap-2">
              {candidateSeries.map((series) => {
                const key = getSeriesKey(series);
                const checked = selectedSeriesIds === null ? detailSeries.some((item) => getSeriesKey(item) === key) : selectedSeriesIds.has(key);
                return (
                  <CheckboxChip
                    key={key}
                    checked={checked}
                    onChange={(isChecked) => {
                      setSelectedSeriesIds((prev) => {
                        const next = new Set(prev === null ? detailSeries.map(getSeriesKey) : prev);
                        if (isChecked) next.add(key);
                        else next.delete(key);
                        return next;
                      });
                    }}
                    color={seriesColorMap.get(key)}
                    label={getSeriesDisplayName(series)}
                  />
                );
              })}
            </div>
          </div>
        </div>

        {chartSeries.length === 0 ? <div className="mt-4 rounded-lg border border-dashed border-line p-6 text-center text-sm text-muted">当前没有可绘制折线。请勾选产品线，或在“机房展示方式”中选择有历史价格的机房。</div> : null}
        <div className="mt-4 h-[30rem]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={detailRows} margin={{ top: 12, right: 24, left: 8, bottom: 12 }}>
              <CartesianGrid stroke="#dfe5f0" strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis />
              <Tooltip content={<TrendsTooltip />} wrapperStyle={{ zIndex: 9999, pointerEvents: "none" }} />
              <Legend verticalAlign="bottom" align="center" height={92} content={<ScrollableChartLegend />} />
              {chartSeries.map((series, index) => {
                const key = getSeriesKey(series);
                const color = chartSeriesColorMap.get(key) || platformSeriesColor(series.platform, index);
                return (
                  <Line
                    key={key}
                    type="monotone"
                    dataKey={getSeriesChartKey(series)}
                    name={getSeriesDisplayName(series)}
                    stroke={color}
                    strokeWidth={series.platform === "UgPhone" ? 3 : 2}
                    strokeDasharray={index % 3 === 1 ? "6 4" : index % 3 === 2 ? "2 4" : undefined}
                    dot
                    connectNulls
                  />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="panel overflow-hidden">
        <div className="border-b border-line bg-slate-50 px-5 py-4"><h2 className="text-lg font-bold">图二产品线明细</h2></div>
        <div className="overflow-x-auto">
          <table className="data-table w-full min-w-[1580px] text-left text-sm">
            <thead className="bg-slate-50 text-xs text-muted">
              <tr><th>平台</th><th>产品</th><th>配置</th><th>购买天数</th><th>配对等级</th><th>相似度</th><th>首个有效价</th><th>最新有效价</th><th>历史涨跌</th><th>最低/最高</th><th>变化日期</th><th>当前价</th><th>上次价</th><th>7日均价</th><th>30日均价</th><th>自然日变化</th><th>price_source</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {chartSeries.map((series, index) => {
                const key = getSeriesKey(series);
                return (
                  <tr key={key}>
                    <td className="font-semibold" style={{ color: chartSeriesColorMap.get(key) || platformSeriesColor(series.platform, index) }}>{series.platform}</td>
                    <td>{series.product_model || "-"}</td>
                    <td>
                      {series.config}
                      {stableArray(series.display_android_versions || series.merged_android_versions).length ? <div className="text-xs text-muted">Android：{stableArray(series.display_android_versions || series.merged_android_versions).join("/")}</div> : null}
                      {series.machine_room_region ? <div className="text-xs text-muted">机房：{series.machine_room_region}</div> : null}
                      {series.android_display_mode === "merged" ? <div className="text-xs text-muted">合并源线：{series.source_series_count || series.merged_series_count || 1} 条</div> : null}
                    </td>
                    <td>{series.duration_display || bucketLabel(series.duration_bucket)}{series.comparison_duration_note ? <div className="text-xs text-amber-700">{series.comparison_duration_note}</div> : null}</td>
                    <td>{series.comparability_level === "base" ? "基准" : labelFromMap(translations.zh.levelLabels, series.comparability_level)}</td>
                    <td>{series.config_similarity_score ?? "-"}</td>
                    <td>{money(series.first_valid_price)}<div className="text-xs text-muted">{series.first_valid_date || "-"}</div></td>
                    <td>{money(series.last_valid_price ?? series.current_price)}<div className="text-xs text-muted">{series.last_valid_date || "-"}</div></td>
                    <td><span className={`chip border ${series.has_price_change ? "border-amber-200 bg-amber-50 text-amber-700" : "border-slate-200 bg-slate-50 text-slate-600"}`}>{series.has_price_change ? "有变化" : "未变化"}</span><div className="text-xs text-muted">{pct(series.collection_price_change_pct)}</div></td>
                    <td>{money(series.min_price)} / {money(series.max_price)}<div className="text-xs text-muted">不同价：{series.distinct_price_count || 0}</div></td>
                    <td className="max-w-[180px] text-xs text-muted">{stableArray(series.price_changed_dates).length ? stableArray(series.price_changed_dates).join(", ") : "—"}</td>
                    <td>{money(series.current_price)}</td>
                    <td>{money(series.previous_price)}</td>
                    <td>{money(series.seven_day_avg_price)} <span className="text-xs text-muted">n={series.seven_day_sample_count || 0}</span></td>
                    <td>{money(series.thirty_day_avg_price)} <span className="text-xs text-muted">n={series.thirty_day_sample_count || 0}</span></td>
                    <td>{pct(series.price_change_pct)}</td>
                    <td>{series.price_source}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel overflow-hidden">
        <div className="border-b border-line bg-slate-50 px-5 py-4">
          <h2 className="text-lg font-bold">其他实付价（不参与核心趋势）</h2>
          <p className="mt-1 text-sm text-muted">这里仅展示当前筛选条件下最新日期的其他实付价，并对相同内容去重。1天、3天、15天、60天已作为核心购买天数进入图一/图二；小时包、45天、120天、新客价、试用价、渠道秒杀价、多设备组合包等真实可支付价格保留在这里，避免喧宾夺主。</p>
        </div>
        <div className="overflow-x-auto">
          <table className="data-table w-full min-w-[1000px] text-left text-sm">
            <thead className="bg-slate-50 text-xs text-muted"><tr><th>日期</th><th>平台</th><th>产品</th><th>购买天数</th><th>价格类型</th><th>总价</th><th>单设备价</th><th>设备数</th><th>商品文本</th></tr></thead>
            <tbody className="divide-y divide-line">
              {otherPaidPrices.length ? otherPaidPrices.map((row, index) => (
                <tr key={`${row.date}-${row.platform}-${row.product_model}-${index}`}>
                  <td>{row.date}</td><td className="font-semibold">{row.platform}</td><td>{row.product_model}</td><td>{row.duration_display || bucketLabel(row.duration_bucket)}</td><td>{row.price_variant_label}</td><td>{money(row.raw_price)}</td><td>{money(row.unit_device_price)}</td><td>{row.device_count}</td><td className="max-w-md truncate" title={row.promotion_text}>{row.promotion_text || "-"}</td>
                </tr>
              )) : <tr><td colSpan="9" className="py-6 text-center text-muted">当前筛选下没有其他实付价。</td></tr>}
            </tbody>
          </table>
        </div>
      </section>


    </div>
  );
}

function PriceChangesPage({ data }) {
  const rows = stableArray(data.priceChangeTracking).sort((a, b) => alertRank(a.alert_level) - alertRank(b.alert_level) || compareAbsPct(a, b) || Number(Boolean(b.promotion_text_changed)) - Number(Boolean(a.promotion_text_changed)));
  const [platform, setPlatform] = useState("all");
  const [product, setProduct] = useState("all");
  const [productSearch, setProductSearch] = useState("");
  const [bucket, setBucket] = useState("all");
  const [reason, setReason] = useState("all");
  const [alert, setAlert] = useState("all");
  const [textChanged, setTextChanged] = useState("all");
  const [search, setSearch] = useState("");
  const productOptions = useMemo(() => [...new Set(rows.map((row) => row.product_model || row.config).filter(Boolean))].sort(), [rows]);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const pq = productSearch.trim().toLowerCase();
    return rows.filter((row) => {
      if (platform !== "all" && row.platform !== platform) return false;
      if (product !== "all" && (row.product_model || row.config) !== product) return false;
      if (bucket !== "all" && String(row.duration_bucket) !== String(bucket)) return false;
      if (reason !== "all" && row.reason_code !== reason) return false;
      if (alert !== "all" && row.alert_level !== alert) return false;
      if (textChanged === "changed" && !row.promotion_text_changed) return false;
      if (textChanged === "unchanged" && row.promotion_text_changed) return false;
      if (pq && !textOf(row.product_model, row.config).includes(pq)) return false;
      if (!q) return true;
      return textOf(row.platform, row.product_model, row.config, row.current_promotion_text, row.previous_promotion_text, row.reason_code).includes(q);
    });
  }, [rows, platform, product, productSearch, bucket, reason, alert, textChanged, search]);
  const pager = usePagination(filtered);
  return (
    <div className="space-y-6">
      <InfoCard title="本页怎么看">
        本页只追踪现价变化，不使用原价或折扣率。是否有活动，请结合商品文本页查看。
      </InfoCard>
      <section className="panel grid gap-3 p-4 md:grid-cols-4">
        <SelectFilter label="平台" value={platform} onChange={setPlatform}><option value="all">全部</option>{allPlatforms.map((item) => <option key={item} value={item}>{item}</option>)}</SelectFilter>
        <SelectFilter label="产品/配置" value={product} onChange={setProduct}><option value="all">全部</option>{productOptions.map((item) => <option key={item} value={item}>{item}</option>)}</SelectFilter>
        <SearchFilter label="产品搜索" value={productSearch} onChange={setProductSearch} placeholder="搜索产品或配置" />
        <SelectFilter label="购买天数" value={bucket} onChange={setBucket}><option value="all">全部</option>{[...coreBuckets, "other"].map((item) => <option key={item} value={item}>{bucketLabel(item)}</option>)}</SelectFilter>
        <SelectFilter label="变化类型" value={reason} onChange={setReason}><option value="all">全部</option>{reasonOptions.map((item) => <option key={item} value={item}>{labelFromMap(translations.zh.reasonLabels, item)} {item}</option>)}</SelectFilter>
        <SelectFilter label="警告等级" value={alert} onChange={setAlert}><option value="all">全部</option>{alertOptions.map((item) => <option key={item} value={item}>{labelFromMap(translations.zh.alertLabels, item)} {item}</option>)}</SelectFilter>
        <SelectFilter label="商品文本变化" value={textChanged} onChange={setTextChanged}><option value="all">全部</option><option value="changed">仅看文本变化</option><option value="unchanged">仅看文本未变化</option></SelectFilter>
        <SearchFilter label="搜索" value={search} onChange={setSearch} placeholder="搜索配置、平台、商品文本、reason_code" />
      </section>
      <section className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table w-full min-w-[1240px] text-left text-sm">
            <thead className="bg-slate-50 text-xs text-muted">
              <tr><th>平台</th><th>配置</th><th>购买天数</th><th>baseline 价格</th><th>上次价格</th><th>当前价格</th><th>变化金额</th><th>变化比例</th><th>商品文本变化</th><th>reason_code</th><th>alert_level</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {pager.visible.map((row, index) => (
                <tr className="hover:bg-slate-50" key={`${row.platform}-${row.config}-${row.duration_display}-${index}`}>
                  <td>{row.platform}</td>
                  <td className="font-semibold">{row.config}</td>
                  <td>{row.duration_display}</td>
                  <td>{money(row.baseline_price)}</td>
                  <td>{money(row.previous_price)}</td>
                  <td className="font-bold">{money(row.current_price)}</td>
                  <td>{money(row.price_change_abs)}</td>
                  <td>{pct(row.price_change_pct)}</td>
                  <td>{row.promotion_text_changed ? "是" : "否"}</td>
                  <td><div>{labelFromMap(translations.zh.reasonLabels, row.reason_code)}</div><code className="text-xs text-muted">{row.reason_code}</code></td>
                  <td><span className={`chip border ${alertClass(row.alert_level)}`}>{labelFromMap(translations.zh.alertLabels, row.alert_level)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={pager.page} totalPages={pager.totalPages} total={filtered.length} shown={pager.visible.length} setPage={pager.setPage} />
      </section>
    </div>
  );
}

function ProductTextPage({ data }) {
  const rows = stableArray(data.productTextChanges);
  const [platform, setPlatform] = useState("all");
  const [product, setProduct] = useState("all");
  const [productSearch, setProductSearch] = useState("");
  const [bucket, setBucket] = useState("core");
  const [textChanged, setTextChanged] = useState("all");
  const [keyword, setKeyword] = useState("");
  const [reason, setReason] = useState("all");
  const productOptions = useMemo(() => [...new Set(rows.map((row) => row.product_model || row.config).filter(Boolean))].sort(), [rows]);
  const filtered = useMemo(() => {
    const pq = productSearch.trim().toLowerCase();
    const kq = keyword.trim().toLowerCase();
    return rows.filter((row) => {
      if (platform !== "all" && row.platform !== platform) return false;
      if (product !== "all" && (row.product_model || row.config) !== product) return false;
      if (bucket === "core" && !coreBuckets.includes(Number(row.duration_bucket))) return false;
      if (bucket !== "core" && bucket !== "all" && String(row.duration_bucket) !== String(bucket)) return false;
      if (textChanged === "changed" && !row.promotion_text_changed) return false;
      if (textChanged === "unchanged" && row.promotion_text_changed) return false;
      if (reason !== "all" && row.reason_code !== reason) return false;
      if (pq && !textOf(row.product_model, row.config).includes(pq)) return false;
      if (kq && !textOf(row.current_promotion_text, row.previous_promotion_text).includes(kq)) return false;
      return true;
    });
  }, [rows, platform, product, productSearch, bucket, textChanged, keyword, reason]);
  const pager = usePagination(filtered);
  return (
    <div className="space-y-6">
      <InfoCard title="本页怎么看">
        本页用于人工判断是不是活动、限时、首购、组合包或秒杀。这里展示商品文本变化，不用原价推断活动。
      </InfoCard>
      <section className="panel grid gap-3 p-4 md:grid-cols-4">
        <SelectFilter label="平台" value={platform} onChange={setPlatform}><option value="all">全部</option>{allPlatforms.map((item) => <option key={item} value={item}>{item}</option>)}</SelectFilter>
        <SelectFilter label="产品/配置" value={product} onChange={setProduct}><option value="all">全部</option>{productOptions.map((item) => <option key={item} value={item}>{item}</option>)}</SelectFilter>
        <SearchFilter label="产品搜索" value={productSearch} onChange={setProductSearch} placeholder="搜索产品或配置" />
        <SelectFilter label="购买天数" value={bucket} onChange={setBucket}><option value="core">默认核心天数</option><option value="all">全部</option>{[...coreBuckets, "other"].map((item) => <option key={item} value={item}>{bucketLabel(item)}</option>)}</SelectFilter>
        <SelectFilter label="文本变化" value={textChanged} onChange={setTextChanged}><option value="all">全部</option><option value="changed">仅看文本变化</option><option value="unchanged">仅看文本未变化</option></SelectFilter>
        <SearchFilter label="文案关键词" value={keyword} onChange={setKeyword} placeholder="Limited Time Offer / 五一 / Get 2 Devices" />
        <SelectFilter label="reason_code" value={reason} onChange={setReason}><option value="all">全部</option>{reasonOptions.map((item) => <option key={item} value={item}>{item}</option>)}</SelectFilter>
      </section>
      <section className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table w-full min-w-[1080px] text-left text-sm">
            <thead className="bg-slate-50 text-xs text-muted">
              <tr><th>平台</th><th>商品</th><th>购买天数</th><th>当前价格</th><th>当前商品文本</th><th>上次商品文本</th><th>文本变化</th><th>reason_code</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {pager.visible.map((row, index) => (
                <tr className="hover:bg-slate-50" key={`${row.platform}-${row.config}-${index}`}>
                  <td>{row.platform}</td>
                  <td className="font-semibold">{row.config}</td>
                  <td>{row.duration_display}</td>
                  <td>{money(row.current_price)}</td>
                  <td className="max-w-md">{row.current_promotion_text || "—"}</td>
                  <td className="max-w-md text-muted">{row.previous_promotion_text || "—"}</td>
                  <td>{row.promotion_text_changed ? "是" : "否"}</td>
                  <td><code className="text-xs">{row.reason_code}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={pager.page} totalPages={pager.totalPages} total={filtered.length} shown={pager.visible.length} setPage={pager.setPage} />
      </section>
    </div>
  );
}

function MetricsPage({ data }) {
  return (
    <div className="space-y-6">
      <InfoCard title="本页怎么看">
        本页解释价格看板中的核心指标。重点：前台只看成交价、同购买天数、配置相似度、竞品中位价和商品文本变化，不用原价或折扣率做判断。
      </InfoCard>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {stableArray(data.metricDefinitions).map((item) => (
          <section className="panel p-5" key={item.field}>
            <h2 className="text-lg font-bold">{item.name_zh}</h2>
            <code className="text-xs text-muted">{item.field}</code>
            <dl className="mt-3 grid gap-2 text-sm">
              <div><dt className="font-semibold">它是什么意思</dt><dd className="text-muted">{item.meaning}</dd></div>
              <div><dt className="font-semibold">数据从哪里来</dt><dd className="text-muted">{item.source}</dd></div>
              <div><dt className="font-semibold">怎么算</dt><dd className="text-muted">{item.calculation}</dd></div>
              <div><dt className="font-semibold">怎么解读</dt><dd className="text-muted">{item.interpretation}</dd></div>
              <div><dt className="font-semibold">常见误区</dt><dd className="text-muted">{item.pitfall}</dd></div>
            </dl>
          </section>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [lang, setLang] = useState("zh");
  const [page, setPage] = useState(pageFromHash);
  const [loadState, setLoadState] = useState({ data: null, source: "real_data", isMockData: false, error: null });
  const [isReloading, setIsReloading] = useState(false);

  const loadData = useCallback(async () => {
    setIsReloading(true);
    const result = await loadDashboardData();
    setLoadState(result);
    setIsReloading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => {
    const onHashChange = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHashChange);
    if (!window.location.hash) window.location.hash = "/price-overview";
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const go = (target) => {
    window.location.hash = `/${target}`;
    setPage(target);
  };

  const data = loadState.data;
  if (!data) return <div className="flex min-h-screen items-center justify-center bg-surface text-muted">正在加载价格看板...</div>;

  const content = {
    "price-overview": <PriceOverview data={data} go={go} />,
    pairing: <PairingPage data={data} />,
    "duration-prices": <DurationPricesPage data={data} />,
    trends: <TrendsPage data={data} />,
    "price-changes": <PriceChangesPage data={data} />,
    "product-text": <ProductTextPage data={data} />,
    metrics: <MetricsPage data={data} />,
  }[page];

  return (
    <AppShell page={page} setPage={setPage} lang={lang} setLang={setLang} onReload={loadData} isReloading={isReloading}>
      {content}
    </AppShell>
  );
}
