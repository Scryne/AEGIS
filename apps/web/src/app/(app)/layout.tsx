import type { ReactNode } from "react";

import { LogoutButton } from "@/components/logout-button";
import { NavLinks } from "@/components/nav-links";
import { getCurrentUser, ROLE_LABELS } from "@/lib/server/user";
import type { Role } from "@/lib/server/user";

// Rol-kapılı gezinme. Taramalar E1.3'te, varlık kütüğü E1.4'te, denetim izi
// görüntüleyicisi E1.5'te açıldı.
//
// Denetçi (auditor) taramaları GÖRÜR ama çalıştıramaz; menü görünürlüğü okuma
// yetkisine göredir, yazma yetkisi sayfa içinde ayrıca kapılıdır. Denetim izi
// analiste kapalıdır (backend'deki RequireAuditRead ile aynı rol kümesi).
const NAV: { label: string; href: string; roles: Role[]; enabled: boolean }[] = [
  {
    label: "Panel",
    href: "/dashboard",
    roles: ["owner", "compliance_officer", "analyst", "auditor"],
    enabled: true,
  },
  {
    label: "Taramalar",
    href: "/screenings",
    roles: ["owner", "compliance_officer", "analyst", "auditor"],
    enabled: true,
  },
  {
    label: "Varlıklar",
    href: "/entities",
    roles: ["owner", "compliance_officer", "analyst", "auditor"],
    enabled: true,
  },
  {
    label: "Denetim İzi",
    href: "/audit",
    roles: ["owner", "compliance_officer", "auditor"],
    enabled: true,
  },
];

export default async function AppLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();
  const visibleNav = NAV.filter((item) => item.roles.includes(user.role));

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="flex flex-col gap-3 border-b border-border bg-surface p-3 md:w-60 md:shrink-0 md:gap-0 md:border-r md:border-b-0 md:p-4">
        <div className="font-mono text-sm tracking-widest text-muted uppercase md:mb-6">AEGIS</div>
        <NavLinks
          items={visibleNav
            .filter((item) => item.enabled)
            .map(({ label, href }) => ({ label, href }))}
        />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-border bg-surface px-4 py-3 md:px-6">
          <div className="min-w-0 truncate text-sm text-muted">
            <span className="text-fg">{user.email}</span>
            <span className="mx-2">·</span>
            {ROLE_LABELS[user.role]}
          </div>
          <LogoutButton />
        </header>
        <main className="min-w-0 flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
