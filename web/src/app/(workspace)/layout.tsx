import { Suspense } from "react";

import { ModeBanner } from "@/components/ModeBanner";
import { Chrome, ChromeFallback } from "@/components/shell/Chrome";
import { ToastProvider } from "@/components/ui/Toast";

// Same top-level structure as plan/template/index.html: aside + header + main.
export default function WorkspaceLayout({ children }: LayoutProps<"/">) {
  return (
    <ToastProvider>
      <Suspense fallback={<ChromeFallback />}>
        <Chrome />
      </Suspense>
      <main id="app">
        <Suspense fallback={null}>
          <ModeBanner />
        </Suspense>
        {children}
        <div className="productfooter">
          <span>VoiceOS · Không gian làm việc của bạn</span>
          <span>M0 · Dữ liệu dev, không phải dữ liệu khách thật</span>
        </div>
      </main>
    </ToastProvider>
  );
}
