import { getProcessorStatus } from "@/lib/data";

/** Shown whenever demo tools are on, so a simulated result can never pass for a real bank decision. */
export async function DemoBadge() {
  let on = false;
  try {
    on = Boolean((await getProcessorStatus()).demo_tools);
  } catch {
    // The badge is informational: never break the page if the API is down.
  }
  if (!on) return null;
  return (
    <span
      className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-800 dark:bg-violet-950 dark:text-violet-200"
      title="Demo tools are on: outcomes can be simulated. Turn off with DEMO_TOOLS=0."
    >
      Demo tools on
    </span>
  );
}
