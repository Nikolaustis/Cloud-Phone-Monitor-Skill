import { Table2 } from "lucide-react";

export default function DailyChangesMiniTables({ rows, t }) {
  return (
    <section className="panel p-5">
      <h2 className="mb-4 text-lg font-bold">{t.dailyChanges}</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {rows.map((row) => (
          <div className="rounded-lg border border-line bg-slate-50 p-4" key={row.sheet}>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 font-semibold">
                <Table2 size={17} className="text-primary" />
                {row.sheet}
              </div>
              <span className="chip border-slate-200 bg-white text-slate-700">{row.rows} {t.rows}</span>
            </div>
            <p className="mt-2 text-sm text-muted">{row.description || `${row.columns?.length ?? 0} ${t.columnUnit}`}</p>
            {row.sample?.length ? (
              <div className="mt-3 rounded-md bg-white p-2 text-xs text-muted">
                {t.showingRows}: {row.sample.length}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}
