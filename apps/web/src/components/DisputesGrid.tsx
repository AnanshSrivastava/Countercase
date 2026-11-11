"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type ICellRendererParams,
} from "ag-grid-community";

import { Countdown, urgency, useNowSeconds } from "@/components/Countdown";
import { CATEGORY_LABEL, STATUS_LABEL, isOpen, money } from "@/lib/format";
import type { Dispute } from "@/lib/types";

ModuleRegistry.registerModules([AllCommunityModule]);

const gridTheme = themeQuartz.withParams({
  accentColor: "#1d4ed8",
  backgroundColor: "#ffffff",
  borderColor: "#eef0f3",
  browserColorScheme: "light",
  cellHorizontalPadding: 16,
  fontFamily: "var(--font-geist-sans), Arial, sans-serif",
  headerBackgroundColor: "#f8fafc",
  headerFontWeight: 600,
  headerTextColor: "#71717a",
  rowHoverColor: "#f8fafc",
  wrapperBorderRadius: 10,
});

function ActionCell({ data }: ICellRendererParams<Dispute>) {
  if (!data) return null;
  const action = nextAction(data);
  return (
    <Link
      href={`/disputes/${data.id}`}
      className="inline-flex items-center gap-1 rounded-md bg-blue-700 px-3 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
    >
      {action}
      <span aria-hidden>›</span>
    </Link>
  );
}

function DeadlineCell({ data }: ICellRendererParams<Dispute>) {
  const now = useNowSeconds();
  if (!data) return null;
  const open = isOpen(data.status);
  const left = now === null ? null : Date.parse(data.deadline_at) - now * 1000;
  const level = left === null ? "ok" : urgency(left);
  const emphasis = open && (level === "critical" || level === "urgent" || level === "overdue");
  return (
    <div className={emphasis ? "font-semibold text-red-700" : ""}>
      <Countdown deadline={data.deadline_at} open={open} />
      {open && <div className="mt-1 text-[11px] text-zinc-500">{new Date(data.deadline_at).toLocaleDateString()}</div>}
    </div>
  );
}

function StatusCell({ data }: ICellRendererParams<Dispute>) {
  if (!data) return null;
  const style = isOpen(data.status) ? "bg-blue-50 text-blue-700 ring-blue-200" : "bg-zinc-100 text-zinc-600 ring-zinc-200";
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${style}`}>{STATUS_LABEL[data.status]}</span>;
}

function DraftCell({ data }: ICellRendererParams<Dispute>) {
  if (!data) return null;
  const ready = data.status !== "needs_response";
  return ready ? (
    <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />Ready</span>
  ) : (
    <span className="text-xs text-zinc-400">Not started</span>
  );
}

function nextAction(dispute: Dispute): string {
  switch (dispute.status) {
    case "needs_response": return "Review case";
    case "drafted": return "Review draft";
    case "approved": return "Submit response";
    case "submitted": return "View submission";
    default: return "View outcome";
  }
}

export function DisputesGrid({ disputes }: { disputes: Dispute[] }) {
  const [quickFilter, setQuickFilter] = useState("");
  const columnDefs = useMemo<ColDef<Dispute>[]>(
    () => [
      { headerName: "Status", field: "status", minWidth: 142, cellRenderer: StatusCell },
      {
        headerName: "Amount",
        field: "amount",
        minWidth: 116,
        valueFormatter: ({ data }) => data ? money(data.amount, data.currency) : "",
        cellClass: "font-semibold tabular-nums",
      },
      {
        headerName: "Reason",
        field: "category",
        flex: 1.4,
        minWidth: 180,
        valueGetter: ({ data }) => data ? CATEGORY_LABEL[data.category ?? "other"] : "",
        tooltipValueGetter: ({ data }) => data?.category_explanation ?? data?.reason_raw ?? "",
        cellRenderer: ({ data }: ICellRendererParams<Dispute>) => data ? (
          <div className="leading-tight"><div className="font-medium">{CATEGORY_LABEL[data.category ?? "other"]}</div><div className="mt-1 truncate text-xs text-zinc-500">{data.category_explanation ?? data.reason_raw}</div></div>
        ) : null,
      },
      { headerName: "Response deadline", field: "deadline_at", minWidth: 168, sort: "asc", cellRenderer: DeadlineCell },
      { headerName: "Draft", minWidth: 116, cellRenderer: DraftCell },
      { headerName: "Next action", minWidth: 158, cellRenderer: ActionCell, sortable: false, filter: false },
    ],
    [],
  );

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-100 px-5 py-4">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-zinc-900">Priority queue</p>
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-600">{disputes.length} {disputes.length === 1 ? "case" : "cases"}</span>
          </div>
          <p className="mt-0.5 text-xs text-zinc-500">Open cases are ordered by response deadline</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-zinc-500">
          <span className="sr-only">Search disputes</span>
          <span aria-hidden className="text-zinc-400">⌕</span>
          <input value={quickFilter} onChange={(event) => setQuickFilter(event.target.value)} placeholder="Search cases…" className="h-9 w-52 rounded-lg border border-zinc-200 bg-zinc-50 px-3 text-sm text-zinc-900 outline-none placeholder:text-zinc-400 focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-100" />
        </label>
      </div>
      <div className="ag-theme-quartz w-full" style={{ height: 540 }}>
        <AgGridReact<Dispute>
          theme={gridTheme}
          rowData={disputes}
          columnDefs={columnDefs}
          quickFilterText={quickFilter}
          animateRows
          pagination
          paginationPageSize={10}
          paginationPageSizeSelector={[10, 25, 50]}
          defaultColDef={{ sortable: true, filter: true, resizable: true, wrapHeaderText: true, autoHeaderHeight: true }}
          getRowId={({ data }) => data.id}
          rowHeight={76}
        />
      </div>
    </div>
  );
}
