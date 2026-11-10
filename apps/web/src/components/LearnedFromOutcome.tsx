import { BeliefChanges } from "@/features/memory/MemoryTab";
import { getBeliefChanges } from "@/features/memory/data";

/** What the agent changed its mind about because of THIS dispute's result (server-rendered, persists). */
export async function LearnedFromOutcome({ disputeId }: { disputeId: string }) {
  const { data, unavailable } = await getBeliefChanges();
  const mine = data.filter((c) => c.dispute_id === disputeId);

  if (unavailable) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">{unavailable}</p>;
  }
  if (mine.length === 0) {
    return (
      <p className="rounded-lg border border-zinc-200 bg-white p-4 text-sm text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        This result has not changed any belief yet. The agent needs a few similar cases before it
        trusts a pattern.
      </p>
    );
  }
  return <BeliefChanges changes={mine} />;
}
