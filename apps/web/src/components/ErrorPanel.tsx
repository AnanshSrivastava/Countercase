import { ApiError } from "@/lib/data";

export function ErrorPanel({ title, error }: { title: string; error: unknown }) {
  const detail =
    error instanceof ApiError
      ? `${error.code}: ${error.message}`
      : error instanceof Error
        ? error.message
        : String(error);
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
    >
      <p className="font-medium">{title}</p>
      <p className="mt-1 font-mono text-xs">{detail}</p>
      <p className="mt-2 text-xs">
        Is the API running (<code>make up</code>)? Or set <code>NEXT_PUBLIC_USE_FIXTURES=1</code> to use fixtures.
      </p>
    </div>
  );
}
