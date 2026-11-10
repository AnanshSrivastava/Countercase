import { dateTime, EVIDENCE_LABEL } from "@/lib/format";
import type { EvidenceItem } from "@/lib/types";

export function EvidenceList({ evidence, apiUrl }: { evidence: EvidenceItem[]; apiUrl: string }) {
  const system = evidence.filter((e) => e.verified);
  const seller = evidence.filter((e) => !e.verified);

  return (
    <div className="flex flex-col gap-5">
      <Group
        title="From your shop and courier"
        hint="Pulled from your systems. Only these can back a claim in your response."
        empty="Nothing collected yet. Evidence is gathered automatically when a dispute arrives, if the order can be matched with certainty."
        items={system}
        apiUrl={apiUrl}
      />
      <Group
        title="Added by you"
        hint="Notes are private and never sent. Files can be attached when you approve the response, but are never used as proof."
        empty="Nothing added yet."
        items={seller}
        apiUrl={apiUrl}
      />
    </div>
  );
}

function Group({
  title,
  hint,
  empty,
  items,
  apiUrl,
}: {
  title: string;
  hint: string;
  empty: string;
  items: EvidenceItem[];
  apiUrl: string;
}) {
  return (
    <section>
      <h2 className="font-semibold">{title}</h2>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">{hint}</p>
      {items.length === 0 ? (
        <p className="mt-2 rounded-lg border border-dashed border-zinc-300 p-4 text-sm text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
          {empty}
        </p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2">
          {items.map((e) => (
            <EvidenceCard key={e.id} item={e} apiUrl={apiUrl} />
          ))}
        </ul>
      )}
    </section>
  );
}

function EvidenceCard({ item: e, apiUrl }: { item: EvidenceItem; apiUrl: string }) {
  return (
    <li
      id={e.id}
      className="rounded-lg border border-zinc-200 bg-white p-3 target:ring-2 target:ring-sky-400 dark:border-zinc-800 dark:bg-zinc-900"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{EVIDENCE_LABEL[e.type]}</span>
        <VerifiedBadge verified={e.verified} />
        <span className="font-mono text-xs text-zinc-500">{e.id}</span>
      </div>
      <p className="mt-1 whitespace-pre-wrap text-sm">{e.summary}</p>
      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
        Source: {e.source} · captured {dateTime(e.captured_at)}
      </p>
      <Preview item={e} apiUrl={apiUrl} />
    </li>
  );
}

/** Only files the seller uploaded to our API can be previewed; other `uri`s are references. */
function Preview({ item, apiUrl }: { item: EvidenceItem; apiUrl: string }) {
  if (item.source !== "seller_upload" || !item.uri?.startsWith("files/")) return null;
  const href = `${apiUrl}/core/${item.uri}`;
  if (/\.(png|jpe?g)$/.test(item.uri)) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className="mt-2 inline-block">
        {/* eslint-disable-next-line @next/next/no-img-element -- served by the API origin, not optimizable */}
        <img
          src={href}
          alt={item.summary}
          className="max-h-40 rounded-md border border-zinc-200 dark:border-zinc-700"
        />
      </a>
    );
  }
  return (
    <a href={href} className="mt-2 inline-block text-sm text-sky-700 hover:underline dark:text-sky-400">
      Download PDF
    </a>
  );
}

export function VerifiedBadge({ verified }: { verified: boolean }) {
  return verified ? (
    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">
      Verified
    </span>
  ) : (
    <span
      className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-200"
      title="Supplied by you: shown for context, never used as proof"
    >
      Your note / upload
    </span>
  );
}
