import Link from "next/link";

import { Wordmark } from "@/components/nav-links";

// Tanıtım sayfası. Ürün iddiası tek cümle: AEGIS kararı belgeler ve destekler, vermez.
// Akış numaralı adımlarla, güvenceler CLAUDE.md'deki değişmezlerle (Invariant 1-4) birebir.

const STEPS = [
  {
    title: "Kimlik",
    text: "Unvan, vergi numarası, yöneticiler ve gerçek faydalanıcılar tek kayıtta. İmza sirküleri ve faaliyet belgesinden çıkan bilgiler öneri olarak gelir, onayınız olmadan kütüğe girmez.",
  },
  {
    title: "Tarama",
    text: "Şirket ve bağlı kişiler uluslararası yaptırım/PEP listelerine ve MASAK malvarlığı dondurma kararlarına karşı taranır. Türkçe yazım farkları (A.Ş./Anonim Şirketi, İ/ı, sıra) normalize edilir.",
  },
  {
    title: "Karar",
    text: "Her aday skoru, eşleşme nedenleri ve kaynak bağlantısıyla gelir. Onaylamak ya da elemek sizin kararınızdır; eleme gerekçe ister ve gerekçe izde kalır.",
  },
  {
    title: "Dosya",
    text: "Kimlik, tarama sonuçları, kararlar ve kaynaklar tek bir PDF/Word dosyasında; SHA-256 özetiyle, denetimde sunulan dosyanın bu kayıtla aynı olduğu gösterilebilir.",
  },
];

const GUARANTEES = [
  ["Kiracı izolasyonu", "Veritabanı düzeyinde satır güvenliği (RLS); her uç iki kiracıyla sızıntı testinden geçer."],
  ["Değiştirilemez iz", "Her risk etkileyen eylem hash zincirli, yalnız eklenen bir denetim izine yazılır."],
  ["Kişisel veri içeride", "Tarama motoru kendi ortamınızda çalışır; kimlik bilgisi dış API'ye gönderilmez."],
  ["Kaynaksız bulgu yok", "Ekrandaki ve dosyadaki her bulgu, geldiği listeye ya da belgeye bağlıdır."],
];

export default function LandingPage() {
  return (
    <main>
      <div className="bg-ink text-ink-fg">
      <div className="mx-auto max-w-6xl px-4 pt-6 pb-14 md:px-8 md:pb-20">
      <header className="flex items-center justify-between">
        <Wordmark inverse />
        <Link
          href="/login"
          className="inline-flex min-h-10 items-center rounded-md border border-ink-line px-4 text-sm font-medium text-ink-fg hover:bg-ink-raised"
        >
          Giriş yap
        </Link>
      </header>

      <section className="mt-14 grid items-center gap-10 md:mt-20 md:grid-cols-[1.2fr_1fr]">
        <div>
          <p className="text-sm font-medium text-seal">MASAK yükümlüleri için KYB</p>
          <h1 className="mt-3 text-3xl leading-tight font-semibold tracking-tight text-balance md:text-[2.75rem]">
            Müşteri şirketinizi tanıyın, kararınızı kanıtıyla belgeleyin.
          </h1>
          <p className="mt-4 max-w-xl text-ink-muted">
            AEGIS kurum doğrulama, yaptırım ve PEP taraması ile denetime dayanıklı dosyayı tek
            çalışma alanında toplar. Uyum kararını belgeler ve destekler; kararı vermez.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link
              href="/login"
              className="inline-flex min-h-11 items-center rounded-md bg-seal px-5 text-sm font-semibold text-ink hover:opacity-90"
            >
              Çalışma alanına gir
            </Link>
          </div>
        </div>

        {/* Ürünün ana mesajı: sonuç önce, gerekçe sonra. Örnek veri kurgusaldır. */}
        <figure
          aria-label="Örnek tarama sonucu"
          className="panel p-5 text-sm text-fg"
        >
          <div className="text-xs text-muted">Örnek tarama · kurgusal veri</div>
          <div className="mt-2 font-medium text-fg">ABC Yapı Sanayi A.Ş.</div>
          <div className="mt-3 rounded border border-danger/40 bg-danger-soft px-3 py-2 text-danger">
            Onaylanmış eşleşme var
          </div>
          <dl className="mt-4 space-y-2 text-xs">
            <div className="flex justify-between gap-3">
              <dt className="text-muted">Aday</dt>
              <dd className="text-fg">ABC Yapı · yaptırım</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted">Skor</dt>
              <dd className="font-mono text-fg">1,00</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted">Neden</dt>
              <dd className="text-right text-fg">Ad yalnız hukuki ekte farklı</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted">Karar</dt>
              <dd className="text-right text-fg">Analist onayı · gerekçe kayıtlı</dd>
            </div>
          </dl>
          <figcaption className="mt-4 text-xs text-muted">
            Tarama motora ulaşamazsa sonuç “temiz” değil, “sonuç YOK” olarak gösterilir.
          </figcaption>
        </figure>
      </section>
      </div>
      </div>

      <div className="mx-auto max-w-6xl px-4 pb-14 md:px-8">
      <section className="mt-16">
        <h2 className="eyebrow">Nasıl çalışır</h2>
        <ol className="mt-5 grid gap-6 md:grid-cols-2">
          {STEPS.map((step, index) => (
            <li key={step.title} className="flex gap-4">
              <span className="font-mono text-sm text-primary">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <h3 className="font-medium text-fg">{step.title}</h3>
                <p className="mt-1 text-sm text-muted">{step.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-16 panel p-6">
        <h2 className="eyebrow">
          Pazarlık konusu olmayanlar
        </h2>
        <dl className="mt-4 grid gap-x-8 gap-y-4 md:grid-cols-2">
          {GUARANTEES.map(([title, text]) => (
            <div key={title}>
              <dt className="text-sm font-medium text-fg">{title}</dt>
              <dd className="mt-1 text-sm text-muted">{text}</dd>
            </div>
          ))}
        </dl>
      </section>

      <footer className="mt-16 border-t border-border pt-6 text-xs text-muted">
        AEGIS bir karar destek aracıdır; şüpheli işlem bildirimi ve müşteri kabulü yükümlünün
        sorumluluğundadır.
      </footer>
      </div>
    </main>
  );
}
