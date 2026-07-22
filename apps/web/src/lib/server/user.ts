// Aktif kullanıcı çözümleme (sunucu tarafı) — cookie'deki token ile /auth/me.

import { redirect } from "next/navigation";

import { serverFetch } from "@/lib/server/backend";

export type Role = "owner" | "compliance_officer" | "analyst" | "auditor";

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string | null;
  tenant_id: string;
  role: Role;
}

export const ROLE_LABELS: Record<Role, string> = {
  owner: "Sahip",
  compliance_officer: "Uyum Uzmanı",
  analyst: "Analist",
  auditor: "Denetçi (salt-okunur)",
};

/** /auth/me çağırır; kimlik yoksa /login'e yönlendirir. */
export async function getCurrentUser(): Promise<CurrentUser> {
  const res = await serverFetch("/auth/me");
  if (!res.ok) redirect("/login");
  return (await res.json()) as CurrentUser;
}
