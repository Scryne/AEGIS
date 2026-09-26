import Link from "next/link";

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
    <main className="mx-auto max-w-5xl px-4 py-10 md:px-8 md:py-16">
      <header className="flex items-center justify-between">
        <span className="font-mono text-sm tracking-widest text-muted uppercase">AEGIS</span>
        <Link
          href="/login"
          className="rounded-card border border-border bg-surface px-4 py-2 text-sm font-medium text-fg hover:bg-bg"
        >
          Giriş yap
        </Link>
      </header>

      <section className="mt-14 grid items-start gap-10 md:mt-20 md:grid-cols-[1.2fr_1fr]">
        <div>
          <p className="text-sm font-medium text-primary">MASAK yükümlüleri için KYB</p>
          <h1 className="mt-3 text-3xl leading-tight font-semibold text-balance text-fg md:text-4xl">
            Müşteri şirketinizi tanıyın, kararınızı kanıtıyla belgeleyin.
          </h1>
          <p className="mt-4 max-w-xl text-muted">
            AEGIS kurum doğrulama, yaptırım ve PEP taraması ile denetime dayanıklı dosyayı tek
            çalışma alanında toplar. Uyum kararını belgeler ve destekler; kararı vermez.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/login"
              className="rounded-card bg-primary px-5 py-2.5 text-sm font-medium text-primary-fg"
            >
              Çalışma alanına gir
            </Link>
          </div>
        </div>

        {/* Ürünün ana mesajı: sonuç önce, gerekçe sonra. Örnek veri kurgusaldır. */}
        <figure
          aria-label="Örnek tarama sonucu"
          className="rounded-card border border-border bg-surface p-5 text-sm"
        >
          <div className="text-xs text-muted">Örnek tarama · kurgusal veri</div>
          <div className="mt-2 font-medium text-fg">ABC Yapı Sanayi A.Ş.</div>
          <div className="mt-3 rounded border border-danger px-3 py-2 text-danger">
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

      <section className="mt-20">
        <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">Nasıl çalışır</h2>
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

      <section className="mt-16 rounded-card border border-border bg-surface p-6">
        <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">
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
    </main>
  );
}
