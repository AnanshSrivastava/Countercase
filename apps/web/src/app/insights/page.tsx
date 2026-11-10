import { Suspense } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { InsightsView } from "@/components/insights/InsightsView";
import { getInsights } from "@/lib/insights-data";

export const metadata = { title: "Insights · Recoup" };

export default function InsightsPage() {
  return (
    <section className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Insights</h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Where your disputes come from and what to change. Computed from your closed disputes; every rate shows how
          many cases are behind it.
        </p>
      </div>
      <Suspense fallback={<InsightsSkeleton />}>
        <InsightsContent />
      </Suspense>
    </section>
  );
}

async function InsightsContent() {
  let data;
  try {
    data = await getInsights();
  } catch (e) {
    return <ErrorPanel title="Could not load insights" error={e} />;
  }
  return <InsightsView data={data} />;
}

function InsightsSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy>
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-24 animate-pulse rounded-lg bg-zinc-200/70 dark:bg-zinc-800" />
      ))}
    </div>
  );
}
