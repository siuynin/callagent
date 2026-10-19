import type { Tone } from "@/components/ui/primitives";
import type { Contact } from "@/lib/api";

// Shared by server and client components (must not live in a "use client" module).
export const PHONE_STATUS: Record<Contact["phone_status"], { label: string; tone: Tone }> = {
  valid: { label: "Hợp lệ", tone: "green" },
  uncertain: { label: "Cần kiểm tra", tone: "amber" },
  invalid: { label: "Sai số", tone: "red" },
};
