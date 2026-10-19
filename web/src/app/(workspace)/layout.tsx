import { Suspense } from "react";

import { ModeBanner } from "@/components/ModeBanner";
import { Sidebar } from "@/components/Sidebar";

export default function WorkspaceLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="shell">
      <Sidebar />
      <main className="main">
        <Suspense fallback={null}>
          <ModeBanner />
        </Suspense>
        {children}
      </main>
    </div>
  );
}
