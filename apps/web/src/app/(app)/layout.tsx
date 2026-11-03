import type { ReactNode } from "react";

import { LogoutButton } from "@/components/logout-button";
import { AppShell, type NavItem } from "@/components/nav-links";
import { getCurrentUser, ROLE_LABELS } from "@/lib/server/user";
import type { Role } from "@/lib/server/user";

// Rol-kapılı gezinme. Taramalar E1.3'te, varlık kütüğü E1.4'te, denetim izi
// görüntüleyicisi E1.5'te açıldı.
//
// Denetçi (auditor) taramaları GÖRÜR ama çalıştıramaz; menü görünürlüğü okuma
// yetkisine göredir, yazma yetkisi sayfa içinde ayrıca kapılıdır. Denetim izi
// analiste kapalıdır (backend'deki RequireAuditRead ile aynı rol kümesi).
const ALL_ROLES: Role[] = ["owner", "compliance_officer", "analyst", "auditor"];
const OVERSIGHT_ROLES: Role[] = ["owner", "compliance_officer", "auditor"];

const NAV: (NavItem & { roles: Role[] })[] = [
  { label: "Panel", href: "/dashboard", group: "Çalışma", roles: ALL_ROLES },
  { label: "Taramalar", href: "/screenings", group: "Çalışma", roles: ALL_ROLES },
  // E3.3: denetçi sonuçları görür, yükleyemez (sayfa içinde kapılı).
  { label: "Toplu Tarama", href: "/batches", group: "Çalışma", roles: ALL_ROLES },
  { label: "Varlıklar", href: "/entities", group: "Çalışma", roles: ALL_ROLES },
  { label: "İzleme", href: "/monitoring", group: "Çalışma", roles: ALL_ROLES },
  // E3.2: denetçi vaka geçmişini görür, değiştiremez (sayfa içinde kapılı).
  { label: "Vakalar", href: "/cases", group: "Çalışma", roles: ALL_ROLES },
  // E2.2: bildirimin varlığı bile gizli (5549 s.K. m.4/2) → yalnız sahip ve uyum görevlisi.
  { label: "ŞİB Taslakları", href: "/sib", group: "Bildirim ve denetim", roles: ["owner", "compliance_officer"] },
  { label: "Denetim İzi", href: "/audit", group: "Bildirim ve denetim", roles: OVERSIGHT_ROLES },
  // E3.6: insan kararlarından ölçüm; analist göremez (backend ile aynı rol kümesi).
  { label: "Eşleşme Kalitesi", href: "/quality", group: "Bildirim ve denetim", roles: OVERSIGHT_ROLES },
  // E3.4: anahtar/webhook yönetimi; analist göremez (backend ile aynı rol kümesi).
  { label: "Entegrasyonlar", href: "/integrations", group: "Hesap", roles: OVERSIGHT_ROLES },
  { label: "Plan ve Kullanım", href: "/plan", group: "Hesap", roles: OVERSIGHT_ROLES },
];

export default async function AppLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();
  const items = NAV.filter((item) => item.roles.includes(user.role)).map(
    ({ label, href, group }) => ({ label, href, group }),
  );

  return (
    <AppShell
      items={items}
      account={
        <div className="flex min-w-0 items-center gap-3">
          <div className="hidden min-w-0 text-right sm:block">
            <div className="truncate text-sm font-medium text-fg">{user.email}</div>
            <div className="text-xs text-muted">{ROLE_LABELS[user.role]}</div>
          </div>
          <LogoutButton />
        </div>
      }
    >
      {children}
    </AppShell>
  );
}
