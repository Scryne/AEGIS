// ŞİB taslağı düzenleme (E2.2). Veri sunucuda çekilir; düzenleme istemci bileşenindedir.

import { notFound } from "next/navigation";

import { SibEditor } from "@/components/sib-editor";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";
import { SIB_ROLES, type SibDetay, type SibKodlar } from "@/lib/sib";

export const dynamic = "force-dynamic";

export default async function SibDraftPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!(SIB_ROLES as readonly string[]).includes(user.role)) notFound();
  const { id } = await params;
  const [taslakRes, kodlarRes] = await Promise.all([serverFetch(`/sib-drafts/${id}`), serverFetch("/sib/kodlar")]);
  if (taslakRes.status === 404 || taslakRes.status === 422) notFound();
  if (!taslakRes.ok || !kodlarRes.ok) throw new Error("ŞİB taslağı yüklenemedi.");
  const detay = (await taslakRes.json()) as SibDetay;
  const kodlar = (await kodlarRes.json()) as SibKodlar;

  return (
    <div className="mx-auto max-w-4xl">
      <SibEditor key={detay.id} detay={detay} kodlar={kodlar} />
    </div>
  );
}
