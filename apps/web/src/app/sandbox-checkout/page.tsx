import { SandboxCheckout } from "@/components/SandboxCheckout";

export const metadata = { title: "Sandbox checkout · Countercase" };

export default function SandboxCheckoutPage() {
  const clientId = process.env.PAYPAL_CLIENT_ID ?? "";
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  return (
    <section className="mx-auto flex max-w-2xl flex-col gap-6">
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-blue-700 dark:text-blue-300">
          PayPal test flow
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-950 dark:text-white">
          Sandbox checkout
        </h1>
        <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
          Create a single $10.00 USD test purchase. The amount is fixed on the server and this page
          only uses PayPal Sandbox credentials.
        </p>
      </div>

      <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mb-5 flex items-center justify-between gap-4 border-b border-zinc-100 pb-4 dark:border-zinc-800">
          <div>
            <p className="font-medium text-zinc-950 dark:text-white">Countercase test purchase</p>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">One-time Sandbox order</p>
          </div>
          <p className="text-xl font-semibold text-zinc-950 dark:text-white">$10.00 USD</p>
        </div>
        <SandboxCheckout clientId={clientId} apiUrl={apiUrl} />
      </div>

      <aside className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
        Use the Personal Sandbox account as buyer and the Business Sandbox account linked to this
        REST app as seller. Your screenshot says domestic INR payments are unavailable; use a
        supported cross-border Sandbox account pair for this USD goods/services test. Changing USD
        alone does not make a domestic payment international.
      </aside>
      <p className="text-xs leading-5 text-zinc-500 dark:text-zinc-400">
        Local test page only. Do not expose this unauthenticated app publicly with real customer or
        PayPal data. The Client Secret stays on the API server and is never sent to the browser.
      </p>
    </section>
  );
}
