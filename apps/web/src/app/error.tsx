"use client";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
      <h1 className="text-xl font-semibold">Something went wrong</h1>
      <p className="mt-1 text-sm">Nothing was submitted or changed by this error. {error.message}</p>
      <button
        type="button"
        onClick={reset}
        className="mt-3 rounded-md bg-red-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-red-200 dark:text-red-950"
      >
        Try again
      </button>
    </div>
  );
}
