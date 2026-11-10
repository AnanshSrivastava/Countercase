"use server";

import { revalidatePath } from "next/cache";

import { runAlertCheck } from "@/lib/alerts-data";

export async function checkDeadlinesNow() {
  await runAlertCheck();
  revalidatePath("/alerts");
}
