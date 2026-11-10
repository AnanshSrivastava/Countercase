"use server";

import { revalidatePath } from "next/cache";

import { agentMutation, SELLER_ID } from "./data";

// The seller stays in control (principle 5): any memory or belief can be deleted or rejected.

export async function deleteMemory(formData: FormData) {
  const id = String(formData.get("id") ?? "");
  if (!id) return;
  await agentMutation(`/memory/${encodeURIComponent(id)}?seller_id=${SELLER_ID}`, "DELETE");
  revalidatePath("/", "layout");
}

export async function dismissBelief(formData: FormData) {
  const key = String(formData.get("key") ?? "");
  if (!key) return;
  await agentMutation(`/beliefs/${key}?seller_id=${SELLER_ID}`, "DELETE");
  revalidatePath("/", "layout");
}

export async function saveDirective(formData: FormData) {
  const text = String(formData.get("text") ?? "").trim();
  if (!text) return;
  await agentMutation("/directives", "POST", { text, seller_id: SELLER_ID });
  revalidatePath("/", "layout");
}
