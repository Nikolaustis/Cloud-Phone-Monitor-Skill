import { useEffect, useMemo, useState } from "react";
import { Bot, Calculator, ChevronDown, ChevronUp, MessageSquareText, SearchCheck, Send, Sparkles, X } from "lucide-react";
import { aiMode, askPricingCopilot, explainConfig, getMarketBrief, loadAIContext, simulatePrice } from "../lib/aiClient.js";
import {
  dataOriginLabel,
  durationLabel,
  formatIndex,
  formatPercentRatio,
  formatPrice,
  marketPositionLabel,
  modeLabel,
  renderWhatIfNarrative,
  toolLabel,
} from "../lib/aiPresentation.js";

function safeMarkdownHref(value) {
  const text = String(value || "").trim();
  try {
    const parsed = new URL(text, window.location.href);
    return ["http:", "https:", "mailto:"].includes(parsed.protocol) ? parsed.toString() : null;
  } catch {
    return null;
  }
}

function renderInlineMarkdown(value, keyPrefix = "md") {
  const text = String(value ?? "");
  const pattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[[^\]\n]+\]\([^\)\n]+\))/g;
  const parts = [];
  let cursor = 0;
  let index = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > cursor) parts.push(text.slice(cursor, start));
    const token = match[0];
    const key = `${keyPrefix}-${index++}`;
    if (token.startsWith("**") && token.endsWith("**")) {
      parts.push(<strong className="font-semibold text-slate-900" key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("*") && token.endsWith("*")) {
      parts.push(<em key={key}>{token.slice(1, -1)}</em>);
    } else if (token.startsWith("`") && token.endsWith("`")) {
      parts.push(<code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[0.92em] text-slate-800" key={key}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("[")) {
      const parsed = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      const href = parsed ? safeMarkdownHref(parsed[2]) : null;
      parts.push(href
        ? <a className="font-medium text-indigo-700 underline decoration-indigo-200 underline-offset-2 hover:text-indigo-900" href={href} key={key} rel="noreferrer" target="_blank">{parsed[1]}</a>
        : token);
    } else {
      parts.push(token);
    }
    cursor = start + token.length;
  }
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts;
}

function isTableSeparator(line) {
  const cells = String(line || "").trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function splitTableRow(line) {
  return String(line || "").trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
}

function MarkdownContent({ children, className = "" }) {
  const lines = String(children ?? "").replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }

    if (/^```/.test(line.trim())) {
      const language = line.trim().slice(3).trim();
      const body = [];
      index += 1;
      while (index < lines.length && !/^```/.test(lines[index].trim())) body.push(lines[index++]);
      if (index < lines.length) index += 1;
      blocks.push(
        <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3 text-xs leading-5 text-slate-100" key={`code-${index}`}>
          <code data-language={language || undefined}>{body.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    if (line.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = splitTableRow(line);
      const rows = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) rows.push(splitTableRow(lines[index++]));
      blocks.push(
        <div className="overflow-x-auto rounded-lg border border-slate-200" key={`table-${index}`}>
          <table className="min-w-full border-collapse text-left text-xs">
            <thead className="bg-slate-50 text-slate-700"><tr>{headers.map((cell, i) => <th className="border-b border-slate-200 px-3 py-2 font-semibold" key={i}>{renderInlineMarkdown(cell, `th-${i}`)}</th>)}</tr></thead>
            <tbody>{rows.map((row, r) => <tr className="border-b border-slate-100 last:border-0" key={r}>{headers.map((_, c) => <td className="px-3 py-2 align-top text-slate-600" key={c}>{renderInlineMarkdown(row[c] || "", `td-${r}-${c}`)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const classes = ["text-base font-bold text-slate-950", "text-sm font-bold text-slate-900", "text-sm font-semibold text-slate-900", "text-xs font-semibold uppercase tracking-wide text-slate-600"];
      blocks.push(<div className={classes[level - 1]} key={`h-${index}`}>{renderInlineMarkdown(heading[2], `h-${index}`)}</div>);
      index += 1;
      continue;
    }

    if (/^[-*+]\s+/.test(line.trim())) {
      const items = [];
      while (index < lines.length && /^[-*+]\s+/.test(lines[index].trim())) items.push(lines[index++].trim().replace(/^[-*+]\s+/, ""));
      blocks.push(<ul className="list-disc space-y-1 pl-5 text-sm leading-6 text-slate-700" key={`ul-${index}`}>{items.map((item, i) => <li key={i}>{renderInlineMarkdown(item, `ul-${i}`)}</li>)}</ul>);
      continue;
    }

    if (/^\d+\.\s+/.test(line.trim())) {
      const items = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) items.push(lines[index++].trim().replace(/^\d+\.\s+/, ""));
      blocks.push(<ol className="list-decimal space-y-1 pl-5 text-sm leading-6 text-slate-700" key={`ol-${index}`}>{items.map((item, i) => <li key={i}>{renderInlineMarkdown(item, `ol-${i}`)}</li>)}</ol>);
      continue;
    }

    if (/^>\s?/.test(line.trim())) {
      const quote = [];
      while (index < lines.length && /^>\s?/.test(lines[index].trim())) quote.push(lines[index++].trim().replace(/^>\s?/, ""));
      blocks.push(<blockquote className="border-l-4 border-indigo-200 bg-indigo-50/60 px-3 py-2 text-sm leading-6 text-slate-700" key={`quote-${index}`}>{quote.map((item, i) => <div key={i}>{renderInlineMarkdown(item, `quote-${i}`)}</div>)}</blockquote>);
      continue;
    }

    if (/^(-{3,}|_{3,}|\*{3,})$/.test(line.trim())) {
      blocks.push(<hr className="border-slate-200" key={`hr-${index}`} />);
      index += 1;
      continue;
    }

    const paragraph = [line.trim()];
    index += 1;
    while (index < lines.length && lines[index].trim() && !/^(#{1,4})\s+/.test(lines[index]) && !/^```/.test(lines[index].trim()) && !/^[-*+]\s+/.test(lines[index].trim()) && !/^\d+\.\s+/.test(lines[index].trim()) && !/^>\s?/.test(lines[index].trim())) {
      if (lines[index].includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) break;
      paragraph.push(lines[index++].trim());
    }
    blocks.push(<p className="text-sm leading-6 text-slate-700" key={`p-${index}`}>{paragraph.map((item, i) => <span key={i}>{i ? <br /> : null}{renderInlineMarkdown(item, `p-${index}-${i}`)}</span>)}</p>);
  }
  return <div className={`space-y-2 ${className}`.trim()}>{blocks}</div>;
}

function EvidenceList({ rows = [] }) {
  const [open, setOpen] = useState(false);
  if (!rows.length) return null;
  return (
    <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50">
      <button className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold text-slate-700" onClick={() => setOpen((value) => !value)} type="button">
        <span>查看依据 · {rows.length}</span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {open ? (
        <div className="space-y-2 border-t border-slate-200 p-3">
          <div className="text-[10px] leading-4 text-slate-400">以下为审计用技术证据，保留字段名、事实 ID 与数据文件信息。</div>
          {rows.slice(0, 12).map((row, index) => (
            <div className="rounded-md bg-white p-2 text-[11px] leading-5 text-slate-600" key={`${row.evidence_id || index}-${row.fact_id || row.record_id || index}`}>
              <div className="font-semibold text-slate-800">[{row.evidence_id || `E${index + 1}`}] {row.source_file}</div>
              <div>{row.record_id || row.fact_id || "-"} · {row.field || "record"} = {typeof row.value === "object" ? JSON.stringify(row.value) : String(row.value ?? "-")}</div>
              {row.fact_id ? <div className="text-slate-400">fact {row.fact_id}</div> : null}
              {row.note ? <div className="text-slate-500">{row.note}</div> : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function AnswerCard({ title, payload }) {
  if (!payload) return null;
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-sm font-bold text-slate-900">{title}</div>
        <div className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-600">{modeLabel(payload.mode)}</div>
      </div>
      <MarkdownContent>{payload.answer}</MarkdownContent>
      {payload.tool_calls?.length ? (
        <div className="mt-2 text-[10px] text-slate-400">分析依据：{payload.tool_calls.map(toolLabel).join(" · ")}</div>
      ) : null}
      <EvidenceList rows={payload.evidence} />
      {(payload.data_date || payload.data_revision) ? (
        <div className="mt-3 text-[10px] text-slate-400">数据日期 {payload.data_date || "-"} · 数据版本 {String(payload.data_revision || "-").slice(0, 10)}</div>
      ) : null}
    </section>
  );
}

function BriefTab({ context }) {
  const [brief, setBrief] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    getMarketBrief(context).then((payload) => active && setBrief(payload)).catch((err) => active && setError(err.message));
    return () => { active = false; };
  }, [context]);
  return (
    <div className="space-y-3">
      <div className="rounded-lg bg-indigo-50 p-3 text-xs leading-5 text-indigo-900">
        市场简报先由确定性价格工具计算事实，再转换为面向业务阅读的摘要；数值和市场判断不会由模型自行估算。
      </div>
      {error ? <div className="rounded-lg bg-rose-50 p-3 text-xs text-rose-700">{error}</div> : null}
      {brief ? <AnswerCard payload={brief} title="市场简报" /> : <div className="text-sm text-slate-500">正在生成市场简报…</div>}
    </div>
  );
}

function AskTab({ context }) {
  const examples = context?.examples || [];
  const [question, setQuestion] = useState(examples[0] || "今天哪些 UgPhone 配置高于市场？");
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(value = question) {
    const text = String(value || "").trim();
    if (!text) return;
    setQuestion(text);
    setLoading(true);
    setError("");
    try {
      setAnswer(await askPricingCopilot(text, context));
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {examples.slice(0, 6).map((item) => (
          <button className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-600 hover:border-indigo-300 hover:text-indigo-700" key={item} onClick={() => submit(item)} type="button">{item}</button>
        ))}
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-3">
        <textarea className="min-h-24 w-full resize-none border-none text-sm leading-6 outline-none" maxLength={1000} onChange={(event) => setQuestion(event.target.value)} placeholder="例如：为什么 KVIP 30天明显高于市场？" value={question} />
        <div className="flex justify-end border-t border-slate-100 pt-2">
          <button className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-bold text-white disabled:opacity-50" disabled={loading || !question.trim()} onClick={() => submit()} type="button">
            <Send size={14} /> {loading ? "分析中…" : "开始分析"}
          </button>
        </div>
      </div>
      {error ? <div className="rounded-lg bg-rose-50 p-3 text-xs text-rose-700">{error}</div> : null}
      <AnswerCard payload={answer} title="分析结果" />
    </div>
  );
}

function rowKey(row) {
  return `${row?.config_id || ""}@@${row?.duration_days ?? ""}`;
}

function hardwareKey(row) {
  return `${row?.cpu || ""}@@${row?.ram || ""}@@${row?.storage || ""}`;
}

function hardwareLabel(row) {
  return [row?.cpu || "CPU未标注", row?.ram || "内存未标注", row?.storage || "存储未标注"].join(" / ");
}

function unique(values) {
  return [...new Set(values.filter((value) => value !== null && value !== undefined && String(value) !== ""))];
}

function isSelectableConfig(row) {
  const duration = Number(row?.duration_days);
  return Boolean(row?.config_id) && Number.isFinite(duration) && duration > 0;
}

function chooseBest(rows, current, fixed = {}) {
  const candidates = rows.filter((row) => Object.entries(fixed).every(([key, value]) => {
    if (key === "hardware") return hardwareKey(row) === value;
    if (key === "duration_days") return Number(row.duration_days) === Number(value);
    return String(row[key] ?? "") === String(value ?? "");
  }));
  if (!candidates.length) return rows[0] || null;
  return [...candidates].sort((a, b) => {
    const score = (row) => (
      (String(row.android_version || "") === String(current?.android_version || "") ? 8 : 0)
      + (hardwareKey(row) === hardwareKey(current) ? 4 : 0)
      + (Number(row.duration_days) === Number(current?.duration_days) ? 2 : 0)
      + (String(row.product_model || "") === String(current?.product_model || "") ? 1 : 0)
    );
    return score(b) - score(a);
  })[0];
}

function ConfigurationSelector({ configs = [], selectedKey, onChange }) {
  const availableConfigs = useMemo(() => configs.filter(isSelectableConfig), [configs]);
  const selected = availableConfigs.find((row) => rowKey(row) === selectedKey) || availableConfigs[0] || null;
  const models = useMemo(() => unique(availableConfigs.map((row) => row.product_model)).sort(), [availableConfigs]);
  const modelRows = availableConfigs.filter((row) => String(row.product_model || "") === String(selected?.product_model || ""));
  const androids = unique(modelRows.map((row) => row.android_version)).sort((a, b) => Number(a) - Number(b));
  const androidRows = modelRows.filter((row) => String(row.android_version || "") === String(selected?.android_version || ""));
  const hardwareRows = [];
  const seenHardware = new Set();
  androidRows.forEach((row) => {
    const key = hardwareKey(row);
    if (!seenHardware.has(key)) {
      seenHardware.add(key);
      hardwareRows.push(row);
    }
  });
  const durationRows = androidRows.filter((row) => hardwareKey(row) === hardwareKey(selected));
  const durations = unique(durationRows.map((row) => row.duration_days)).sort((a, b) => Number(a) - Number(b));

  function pick(fixed) {
    const next = chooseBest(availableConfigs, selected, fixed);
    if (next) onChange(rowKey(next));
  }

  if (!selected) {
    return <div className="rounded-lg bg-slate-100 p-3 text-xs text-slate-500">当前没有带有效购买周期的配置；请先重新生成 AI Context。</div>;
  }

  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-3">
      <div className="text-xs font-bold text-slate-800">选择分析对象</div>
      <div className="grid grid-cols-2 gap-3">
        <label className="grid gap-1 text-[11px] font-semibold text-slate-600">
          产品系列
          <select className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-xs" onChange={(event) => pick({ product_model: event.target.value })} value={selected.product_model || ""}>
            {models.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-[11px] font-semibold text-slate-600">
          Android 版本
          <select className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-xs" onChange={(event) => pick({ product_model: selected.product_model, android_version: event.target.value })} value={selected.android_version || ""}>
            {androids.map((value) => <option key={value} value={value}>Android {value}</option>)}
          </select>
        </label>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_8rem] gap-3">
        <label className="grid gap-1 text-[11px] font-semibold text-slate-600">
          硬件配置
          <select className="min-w-0 rounded-lg border border-slate-200 bg-white px-2 py-2 text-xs" onChange={(event) => pick({ product_model: selected.product_model, android_version: selected.android_version, hardware: event.target.value })} value={hardwareKey(selected)}>
            {hardwareRows.map((row) => <option key={hardwareKey(row)} value={hardwareKey(row)}>{hardwareLabel(row)}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-[11px] font-semibold text-slate-600">
          购买周期
          <select className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-xs" onChange={(event) => pick({ product_model: selected.product_model, android_version: selected.android_version, hardware: hardwareKey(selected), duration_days: Number(event.target.value) })} value={selected.duration_days ?? ""}>
            {durations.map((value) => <option key={value} value={value}>{durationLabel(value)}</option>)}
          </select>
        </label>
      </div>
      <div className="grid grid-cols-3 gap-2 rounded-lg bg-slate-50 p-2 text-[10px] text-slate-500">
        <div>当前价格<br /><strong className="text-xs text-slate-800">{formatPrice(selected.ugphone_price)}</strong></div>
        <div>市场位置<br /><strong className="text-xs text-slate-800">{marketPositionLabel(selected.market_position)}</strong></div>
        <div>数据状态<br /><strong className="text-xs text-slate-800">{dataOriginLabel(selected.data_origin || selected.analysis_status)}</strong></div>
      </div>
    </div>
  );
}

function ExplainTab({ context }) {
  const configs = useMemo(() => (context?.configs || []).filter(isSelectableConfig), [context]);
  const [selectedKey, setSelectedKey] = useState("");
  const selected = configs.find((row) => rowKey(row) === selectedKey) || configs[0];
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (configs.length && !selectedKey) setSelectedKey(rowKey(configs[0]));
  }, [configs, selectedKey]);
  useEffect(() => { setResult(null); }, [selectedKey]);

  async function run() {
    setError("");
    try {
      if (!selected) throw new Error("当前没有可比较的配置");
      setResult(await explainConfig(selected.config_id, selected.duration_days, context));
    } catch (err) {
      setError(err.message || String(err));
    }
  }

  return (
    <div className="space-y-3">
      <div className="rounded-lg bg-sky-50 p-3 text-xs leading-5 text-sky-900">
        Explain 会说明价格为什么落入当前市场区间、哪些竞品进入核心比较，以及当前价格是否来自本次真实采集。
      </div>
      <ConfigurationSelector configs={configs} onChange={setSelectedKey} selectedKey={selectedKey} />
      <button className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white" onClick={run} type="button"><SearchCheck size={14} />解释当前判断</button>
      {error ? <div className="rounded-lg bg-rose-50 p-3 text-xs text-rose-700">{error}</div> : null}
      <AnswerCard payload={result} title="判断说明" />
    </div>
  );
}

function WhatIfTab({ context }) {
  // Purchase-period availability comes from the complete UgPhone duration inventory.
  // A valid period remains selectable even when its current competitor median is missing.
  const configs = useMemo(() => (context?.configs || []).filter(isSelectableConfig), [context]);
  const [selectedKey, setSelectedKey] = useState("");
  const selected = configs.find((row) => rowKey(row) === selectedKey) || configs[0];
  const [price, setPrice] = useState(selected?.ugphone_price || "");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (configs.length && !selectedKey) setSelectedKey(rowKey(configs[0]));
  }, [configs, selectedKey]);
  useEffect(() => {
    if (selected?.ugphone_price !== undefined && selected?.ugphone_price !== null) setPrice(selected.ugphone_price);
    setResult(null);
  }, [selectedKey]);

  const hasComparableMedian = Number.isFinite(Number(selected?.competitor_median_price)) && Number(selected?.competitor_median_price) > 0;
  const hasValidPrice = Number.isFinite(Number(price)) && Number(price) > 0;

  async function run() {
    setError("");
    try {
      if (!selected) throw new Error("当前没有可比较的配置");
      if (!hasComparableMedian) throw new Error("该购买周期当前没有足够的可比竞品价格，暂时无法计算模拟后的市场位置。");
      if (!hasValidPrice) throw new Error("请输入有效的假设价格。");
      setResult(await simulatePrice(selected.config_id, Number(price), selected.duration_days, context));
    } catch (err) {
      setError(err.message || String(err));
    }
  }

  return (
    <div className="space-y-3">
      <div className="rounded-lg bg-amber-50 p-3 text-xs leading-5 text-amber-900">
        What-if 只改变假设价格，竞品中位价和配置可比关系固定在当前数据版本；所有数值由确定性代码重新计算。
      </div>
      <ConfigurationSelector configs={configs} onChange={setSelectedKey} selectedKey={selectedKey} />
      <label className="grid gap-1 text-xs font-semibold text-slate-600">
        假设新价格
        <input className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" min="0.01" onChange={(event) => setPrice(event.target.value)} step="0.01" type="number" value={price} />
      </label>
      {!hasComparableMedian && selected ? (
        <div className="rounded-lg bg-amber-50 p-3 text-xs leading-5 text-amber-800">
          该购买周期已存在于 UgPhone 价格数据中，但当前没有足够的可比竞品价格，因此可以选择和查看，暂不能计算模拟后的市场位置。
        </div>
      ) : null}
      <button className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-40" disabled={!selected || !hasComparableMedian || !hasValidPrice} onClick={run} type="button"><Calculator size={14} />运行模拟</button>
      {error ? <div className="rounded-lg bg-rose-50 p-3 text-xs text-rose-700">{error}</div> : null}
      {result ? (
        <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-700">
          <div className="font-bold text-slate-900">模拟结果</div>
          <MarkdownContent className="mt-2">{result.answer || renderWhatIfNarrative(result)}</MarkdownContent>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg bg-slate-50 p-2">当前相对价格指数<br /><strong>{formatIndex(result.old_relative_index)}</strong></div>
            <div className="rounded-lg bg-slate-50 p-2">模拟后相对价格指数<br /><strong>{formatIndex(result.new_relative_index)}</strong></div>
            <div className="rounded-lg bg-slate-50 p-2">当前市场位置<br /><strong>{marketPositionLabel(result.old_market_position)}</strong></div>
            <div className="rounded-lg bg-slate-50 p-2">模拟后市场位置<br /><strong>{marketPositionLabel(result.new_market_position)}</strong></div>
          </div>
          {Number.isFinite(result.price_change_from_current_pct) ? <div className="mt-3 text-xs">相对当前价格调整 <strong>{formatPercentRatio(result.price_change_from_current_pct)}</strong></div> : null}
          {Number.isFinite(result.price_to_competitive_ceiling) ? <div className="mt-1 text-xs">进入“与市场基本持平”区间的价格上限约为 <strong>{formatPrice(result.price_to_competitive_ceiling)}</strong></div> : null}
          <EvidenceList rows={result.evidence} />
        </section>
      ) : null}
    </div>
  );
}

export default function AICopilot() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("brief");
  const [context, setContext] = useState(null);
  const [contextError, setContextError] = useState("");

  useEffect(() => {
    let active = true;
    loadAIContext().then((payload) => active && setContext(payload)).catch((err) => active && setContextError(err.message));
    return () => { active = false; };
  }, []);

  const mode = aiMode();
  const tabs = [["brief", "市场简报", Sparkles], ["ask", "提问", MessageSquareText], ["explain", "解释", SearchCheck], ["what-if", "模拟", Calculator]];
  return (
    <>
      <button aria-label="Open AI Pricing Copilot" className="fixed bottom-5 right-5 z-[80] inline-flex items-center gap-2 rounded-full bg-indigo-600 px-4 py-3 text-sm font-bold text-white shadow-xl shadow-indigo-200 transition hover:-translate-y-0.5 hover:bg-indigo-700" onClick={() => setOpen(true)} type="button">
        <Sparkles size={18} /> AI Pricing Copilot
      </button>
      {open ? (
        <div className="fixed inset-0 z-[90] bg-slate-950/30 backdrop-blur-[1px]" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
          <aside className="absolute bottom-0 right-0 top-0 flex w-full max-w-xl flex-col bg-slate-50 shadow-2xl">
            <header className="border-b border-slate-200 bg-white px-5 py-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 text-base font-bold text-slate-950"><Bot size={20} />Cloud Phone Pricing Intelligence Copilot</div>
                  <div className="mt-1 text-xs text-slate-500">结构化价格分析 · 可追溯依据 · 可解释定价模拟</div>
                </div>
                <button className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50" onClick={() => setOpen(false)} type="button"><X size={17} /></button>
              </div>
              <div className="mt-3 flex items-center gap-2 text-[10px] font-semibold">
                <span className={`rounded-full px-2 py-1 ${mode === "llm_backend" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{mode === "llm_backend" ? "AI增强已连接" : "规则分析模式"}</span>
                {context?.manifest?.data_date ? <span className="text-slate-400">数据 {context.manifest.data_date} · 版本 {String(context.manifest.data_revision || "-").slice(0, 8)}</span> : null}
              </div>
            </header>
            <div className="grid grid-cols-4 border-b border-slate-200 bg-white px-2 pt-2">
              {tabs.map(([key, label, Icon]) => (
                <button className={`flex items-center justify-center gap-1 border-b-2 px-1 py-3 text-[11px] font-bold ${tab === key ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500"}`} key={key} onClick={() => setTab(key)} type="button"><Icon size={13} />{label}</button>
              ))}
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {contextError ? <div className="mb-3 rounded-lg bg-rose-50 p-3 text-xs leading-5 text-rose-700">AI 分析数据尚未生成：{contextError}<br />请先运行 <code>python build_ai_context.py</code>，再构建 Dashboard。</div> : null}
              {tab === "brief" ? <BriefTab context={context} /> : null}
              {tab === "ask" ? <AskTab context={context} /> : null}
              {tab === "explain" ? <ExplainTab context={context} /> : null}
              {tab === "what-if" ? <WhatIfTab context={context} /> : null}
            </div>
          </aside>
        </div>
      ) : null}
    </>
  );
}
