"use client";

import { Wordmark } from "@/components/nav-links";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      // Token httpOnly cookie'ye sunucu tarafında yazılır; JS token görmez.
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        if (response.status === 429) throw new Error("Çok fazla deneme; sonra tekrar deneyin.");
        if (response.status === 401) throw new Error("E-posta veya parola hatalı.");
        throw new Error("Giriş yapılamadı; lütfen sonra tekrar deneyin.");
      }
      const next = searchParams.get("next");
      const isInternal = next !== null && next.startsWith("/") && !next.startsWith("//");
      router.push(isInternal ? next : "/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bilinmeyen hata.");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="grid min-h-dvh md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <section className="flex flex-col justify-between gap-8 bg-ink p-6 text-ink-fg md:p-12">
        <Wordmark inverse />
        <div className="hidden md:block">
          <p className="max-w-md text-2xl leading-snug font-semibold text-balance">
            Kararı siz verirsiniz. AEGIS her kararı kanıtıyla belgeler.
          </p>
          <ul className="mt-6 max-w-md space-y-2.5 text-sm text-ink-muted">
            <li>Sonuç vermeyen tarama hiçbir zaman temiz görünmez.</li>
            <li>Her eşleşme skoru, nedeni ve kaynağıyla gelir.</li>
            <li>Her eylem değiştirilemez denetim izine yazılır.</li>
          </ul>
        </div>
        <p className="hidden text-xs text-ink-muted md:block">
          MASAK yükümlüleri için kurum doğrulama ve tarama çalışma alanı.
        </p>
      </section>
      <div className="flex items-center justify-center p-6 md:p-12">
      <div className="w-full max-w-sm">
        <h1 className="page-title mb-1">Giriş yap</h1>
        <p className="mb-6 text-sm text-muted">Kurum hesabınızla devam edin.</p>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="email" className="text-sm font-medium text-fg">
              E-posta
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="field"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="password" className="text-sm font-medium text-fg">
              Parola
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="field"
            />
          </div>
          {error !== null && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={pending}
            className="btn-primary w-full"
          >
            {pending ? "Giriş yapılıyor…" : "Giriş yap"}
          </button>
        </form>
      </div>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
