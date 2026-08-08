import Link from "next/link";
import type { ReactNode } from "react";

import { LogoutButton } from "@/components/logout-button";
import { getCurrentUser, ROLE_LABELS } from "@/lib/server/user";
import type { Role } from "@/lib/server/user";

// Rol-kapılı gezinme. Taramalar E1.3'te açıldı; varlık kütüğü (E1.4) ve denetim izi
// görüntüleyicisi (E1.5) sonraki epic'lerde gelir.
//
// Denetçi (auditor) taramaları GÖRÜR ama çalıştıramaz; menü görünürlüğü okuma
// yetkisine göredir, yazma yetkisi sayfa içinde ayrıca kapılıdır.
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
    href: "/dashboard",
    roles: ["owner", "compliance_officer", "analyst"],
    enabled: false,
  },
  {
    label: "Denetim İzi",
    href: "/dashboard",
    roles: ["owner", "compliance_officer", "auditor"],
    enabled: false,
  },
];

export default async function AppLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();
  const visibleNav = NAV.filter((item) => item.roles.includes(user.role));

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 flex-col border-r border-border bg-surface p-4">
        <div className="mb-6 font-mono text-sm tracking-widest text-muted uppercase">AEGIS</div>
        <nav className="flex flex-col gap-1">
          {visibleNav.map((item) =>
            item.enabled ? (
              <Link
                key={item.label}
                href={item.href}
                className="rounded-md px-3 py-2 text-sm font-medium text-fg hover:bg-bg"
              >
                {item.label}
              </Link>
            ) : (
              <span
                key={item.label}
                className="flex items-center justify-between rounded-md px-3 py-2 text-sm text-muted"
              >
                {item.label}
                <span className="rounded bg-bg px-1.5 py-0.5 text-[10px] uppercase">yakında</span>
              </span>
            ),
          )}
        </nav>
      </aside>
      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border bg-surface px-6 py-3">
          <div className="text-sm text-muted">
            <span className="text-fg">{user.email}</span>
            <span className="mx-2">·</span>
            {ROLE_LABELS[user.role]}
          </div>
          <LogoutButton />
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
