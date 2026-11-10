import Link from "next/link";

export default function NotFound() {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
      <h1 className="text-xl font-semibold">We couldn&apos;t find that</h1>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        The dispute or page doesn&apos;t exist, or it belongs to another seller.
      </p>
      <Link href="/" className="mt-3 inline-block text-sm text-sky-700 hover:underline dark:text-sky-400">
        ← Back to the inbox
      </Link>
    </div>
  );
}
