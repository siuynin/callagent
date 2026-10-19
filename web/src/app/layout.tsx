import type { Metadata } from "next";

import "@/styles/template.css";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "VoiceOS", template: "%s · VoiceOS" },
  description: "Quản trị tổng đài AI tiếng Việt",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
