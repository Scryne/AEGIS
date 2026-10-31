// Plan ve kullanım (E2.6, ADR-0012): bu ayın tarama sorguları ve izleme kapasitesi.
//
// Plan elle atanır; ekran yalnız gösterir. Aşım izni olmayan planda kota dolunca yeni tarama
// reddedilir, bu yüzden "kalan" sayısı ve durum en üstte, sade dille durur.

import { AdverseMediaBetaToggle } from "@/components/adverse-media-beta-toggle";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";

export const dynamic = "force-dynamic";

interface Usage {
  plan: {
    code: string;
    name: string;
    included_queries: number;
    monitored_entity_limit: number;
    overage_allowed: boolean;
  };
  period_start: string;
  period_end: string;
  used_queries: number;
  remaining_queries: number;
  overage_queries: number;
  monitored_entities: number;
  blocked: boolean;
}

const sayi = (n: number) => n.toLocaleString("tr-TR");
const gun = (iso: string) =>
  new Date(iso).toLocaleDateString("tr-TR", { day: "numeric", month: "long", timeZone: "Europe/Istanbul" });

function Cubuk({ deger, sinir, label }: { deger: number; sinir: number; label: string }) {
  const oran = sinir > 0 ? Math.min(deger / sinir, 1) : 0;
  const ton = oran >= 1 ? "bg-danger" : oran >= 0.8 ? "bg-warning" : "bg-primary";
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={sinir}
      aria-valuenow={Math.min(deger, sinir)}
      className="h-2 w-full overflow-hidden rounded-full bg-border"
    >
      <div className={`h-full ${ton}`} style={{ width: `${Math.round(oran * 100)}%` }} />
    </div>
  );
}

export default async function PlanPage() {
  const [user, res, betaRes] = await Promise.all([
    getCurrentUser(),
    serverFetch("/billing/usage"),
    serverFetch("/adverse-media/beta"),
  ]);
  const u = res.ok ? ((await res.json()) as Usage) : null;
  const beta = betaRes.ok ? ((await betaRes.json()) as { enabled: boolean }).enabled : false;

  if (u === null) {
    return (
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-semibold text-fg">Plan ve kullanım</h1>
        <p className="mt-4 rounded-card border border-danger bg-surface p-4 text-sm text-danger">
          Kullanım bilgisi yüklenemedi. Sayfayı yenileyin; sorun sürerse API&apos;nin çalıştığını
          kontrol edin.
        </p>
      </div>
    );
  }

  // Bitiş anı bir sonraki ayın ilk günü (hariç); kullanıcıya ayın son günü gösterilir.
  const sonGun = new Date(new Date(u.period_end).getTime() - 1).toISOString();
  const izlemeDolu = u.monitored_entities >= u.plan.monitored_entity_limit;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Plan ve kullanım</h1>
        <p className="mt-1 max-w-prose text-sm text-muted">
          Kota taranan özne başına sayılır: bir şirket ve iki yöneticisi üç sorgudur. Gece izlemesinin
          kendi koşuları kotadan düşmez. Dönem {gun(u.period_start)} – {gun(sonGun)} (Türkiye saati).
        </p>
      </div>

      {u.blocked && (
        <p role="alert" className="rounded-card border border-danger bg-surface p-4 text-sm text-danger">
          Bu ayın sorgu hakkı doldu; yeni tarama başlatılamıyor. Planınızı yükseltmek için hesap
          yöneticinizle görüşün. Mevcut kayıtlar ve raporlar erişilebilir kalır.
        </p>
      )}

      <section className="rounded-card border border-border bg-surface p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-base font-medium text-fg">{u.plan.name} planı</h2>
          <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">
            {u.plan.overage_allowed ? "Aşım ayrıca faturalanır" : "Kota dolunca tarama durur"}
          </span>
        </div>

        <div className="mt-5 space-y-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
            <span className="text-fg">Tarama sorgusu</span>
            <span className="font-mono text-fg">
              {sayi(u.used_queries)} <span className="text-muted">/ {sayi(u.plan.included_queries)}</span>
            </span>
          </div>
          <Cubuk deger={u.used_queries} sinir={u.plan.included_queries} label="Tarama sorgusu kullanımı" />
          <p className="text-xs text-muted">
            {u.overage_queries > 0
              ? `Dahil kota ${sayi(u.overage_queries)} sorgu aşıldı.`
              : `Bu ay ${sayi(u.remaining_queries)} sorgu kaldı.`}
          </p>
        </div>

        <div className="mt-6 space-y-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
            <span className="text-fg">İzlenen varlık</span>
            <span className="font-mono text-fg">
              {sayi(u.monitored_entities)}{" "}
              <span className="text-muted">/ {sayi(u.plan.monitored_entity_limit)}</span>
            </span>
          </div>
          <Cubuk
            deger={u.monitored_entities}
            sinir={u.plan.monitored_entity_limit}
            label="İzleme kapasitesi kullanımı"
          />
          <p className="text-xs text-muted">
            {izlemeDolu
              ? "İzleme kapasitesi dolu. Yeni varlık eklemek için önce birini izlemeden çıkarın."
              : "Varlıkları izlemeye varlık sayfasından alırsınız."}
          </p>
        </div>
      </section>

      {user.role === "owner" && (
        <section aria-label="Beta özellikler" className="rounded-card border border-border bg-surface p-5">
          <AdverseMediaBetaToggle enabled={beta} />
        </section>
      )}
    </div>
  );
}
