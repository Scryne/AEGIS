import Link from "next/link";

export default function LandingPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-6 p-8 text-center">
      <div className="font-mono text-sm tracking-widest text-muted uppercase">AEGIS</div>
      <h1 className="text-3xl font-semibold text-fg">
        KYB & kurumsal due diligence
      </h1>
      <p className="max-w-lg text-muted">
        Yaptırım/PEP taraması, kurum doğrulama ve denetime dayanıklı, kaynak-izli dosya.
        AEGIS kararı belgeler ve destekler; kararı vermez.
      </p>
      <Link
        href="/login"
        className="rounded-card bg-primary px-5 py-2.5 text-sm font-medium text-primary-fg"
      >
        Giriş yap
      </Link>
    </main>
  );
}
