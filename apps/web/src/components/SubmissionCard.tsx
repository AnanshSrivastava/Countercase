import { dateTime } from "@/lib/format";
import type { Submission } from "@/lib/types";

const HEADING: Record<Submission["status"], string> = {
  submitted: "Your response was sent",
  exported: "Your response was approved and exported as a PDF (not sent)",
  failed: "Your response was approved but sending failed",
  pending: "Your response is being sent",
};

/** Read-only record of the response the seller approved. */
export function SubmissionCard({ submission, apiUrl }: { submission: Submission; apiUrl: string }) {
  const failed = submission.status === "failed";
  return (
    <section
      className={`rounded-lg border p-4 ${
        failed
          ? "border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40"
          : "border-emerald-300 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/40"
      }`}
    >
      <h2 className="font-semibold">{HEADING[submission.status]}</h2>
      <p className="text-xs text-zinc-600 dark:text-zinc-400">
        Approved {dateTime(submission.approved_at)}
        {submission.submitted_at ? ` · sent ${dateTime(submission.submitted_at)}` : ""}
      </p>
      {submission.note && <p className="mt-1 text-sm">{submission.note}</p>}
      {submission.error && <p className="mt-1 font-mono text-xs">{submission.error}</p>}
      {submission.pdf_uri && (
        <a
          href={`${apiUrl}/core/submissions/${submission.id}/pdf`}
          className="mt-2 inline-block text-sm font-medium text-sky-700 hover:underline dark:text-sky-400"
        >
          Download the PDF packet
        </a>
      )}
      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-medium">The letter that was approved</summary>
        <pre className="mt-2 whitespace-pre-wrap rounded-md bg-white/70 p-3 font-sans text-sm leading-6 dark:bg-black/30">
          {submission.letter_md}
        </pre>
      </details>
    </section>
  );
}
