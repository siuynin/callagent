import { connection } from "next/server";

import { Header, HeaderPlaceholder } from "@/components/shell/Header";
import { Sidebar, SidebarView, type Viewer } from "@/components/shell/Sidebar";
import { api, type Health, type Me } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/labels";
import { oidcEnabled } from "@/lib/session";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const letters = parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : name.slice(0, 2);
  return letters.toUpperCase();
}

/** Sidebar + header with the signed-in viewer. Streams in; the fallback renders the same chrome empty. */
export async function Chrome() {
  await connection();
  const [me, health] = await Promise.all([
    api.me().catch((): Me | null => null),
    api.health().catch((): Health | null => null),
  ]);
  const viewer: Viewer = me
    ? {
        name: me.display_name || "Người dùng",
        roleLabel: ROLE_LABEL[me.role],
        workspace: me.tenant.name,
        initials: initials(me.display_name || "?"),
        canSignOut: oidcEnabled(),
      }
    : null;
  const envLabel = health && health.env !== "production" ? "BẢN THỬ NGHIỆM" : null;
  return (
    <>
      <Sidebar viewer={viewer} />
      <Header initials={viewer?.initials ?? "?"} envLabel={envLabel} />
    </>
  );
}

export function ChromeFallback() {
  return (
    <>
      <SidebarView viewer={null} />
      <HeaderPlaceholder />
    </>
  );
}
