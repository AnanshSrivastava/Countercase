"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type PayPalButtonsOptions = {
  createOrder: () => Promise<string>;
  onApprove: (data: { orderID: string }) => Promise<void>;
  onCancel: () => void;
  onError: (error: unknown) => void;
};

declare global {
  interface Window {
    paypal?: {
      Buttons: (options: PayPalButtonsOptions) => {
        render: (container: HTMLElement) => Promise<void>;
      };
    };
  }
}

type PayPalResponse = {
  id?: string;
  status?: string;
  detail?: string;
  purchase_units?: Array<{
    payments?: { captures?: Array<{ id?: string; status?: string }> };
  }>;
};

type Props = { clientId: string; apiUrl: string };

export function SandboxCheckout({ clientId, apiUrl }: Props) {
  const buttonContainer = useRef<HTMLDivElement>(null);
  const [sdkReady, setSdkReady] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const scriptUrl = new URLSearchParams({
    "client-id": clientId,
    currency: "USD",
    intent: "capture",
    components: "buttons",
  });

  useEffect(() => {
    const container = buttonContainer.current;
    if (!sdkReady || !window.paypal || !container) return;

    const buttons = window.paypal.Buttons({
      createOrder: async () => {
        setError("");
        setMessage("Creating your Sandbox order…");
        const response = await fetch(`${apiUrl}/core/paypal/checkout/orders`, { method: "POST" });
        const body = (await response.json()) as PayPalResponse;
        if (!response.ok || !body.id) {
          throw new Error(body.detail ?? "PayPal could not create the Sandbox order.");
        }
        return body.id;
      },
      onApprove: async ({ orderID }) => {
        setError("");
        setMessage("Payment approved. Capturing the Sandbox payment…");
        const response = await fetch(
          `${apiUrl}/core/paypal/checkout/orders/${encodeURIComponent(orderID)}/capture`,
          { method: "POST" },
        );
        const body = (await response.json()) as PayPalResponse;
        if (!response.ok) {
          throw new Error(body.detail ?? "PayPal could not capture the Sandbox payment.");
        }
        const capture = body.purchase_units?.[0]?.payments?.captures?.[0];
        if (body.status !== "COMPLETED" || capture?.status !== "COMPLETED") {
          throw new Error(`PayPal returned payment status ${capture?.status ?? body.status ?? "unknown"}.`);
        }
        setMessage(`Sandbox payment complete${capture.id ? ` · capture ${capture.id}` : ""}.`);
      },
      onCancel: () => setMessage("Checkout cancelled. No payment was captured."),
      onError: (reason) => {
        setMessage("");
        setError(reason instanceof Error ? reason.message : "PayPal Checkout ran into a problem.");
      },
    });

    void buttons.render(container).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "PayPal Checkout could not load.");
    });

    return () => {
      container.replaceChildren();
    };
  }, [apiUrl, sdkReady]);

  if (!clientId) {
    return (
      <p className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        Add the Sandbox PAYPAL_CLIENT_ID to your local .env, then restart the web container.
      </p>
    );
  }

  return (
    <div>
      <Script
        src={`https://www.paypal.com/sdk/js?${scriptUrl.toString()}`}
        strategy="afterInteractive"
        onLoad={() => setSdkReady(true)}
        onError={() => setError("The PayPal Sandbox Checkout SDK could not be loaded.")}
      />
      <div ref={buttonContainer} />
      <div className="mt-4 min-h-6 text-sm" aria-live="polite">
        {message && <p className="text-emerald-800 dark:text-emerald-300">{message}</p>}
        {error && <p className="text-red-700 dark:text-red-300">{error}</p>}
      </div>
    </div>
  );
}
