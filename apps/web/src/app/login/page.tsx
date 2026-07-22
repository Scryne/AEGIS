"use client";

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
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-6 p-8">
      <div className="w-full rounded-card border border-border bg-surface p-6 shadow-sm">
        <div className="mb-1 font-mono text-xs tracking-widest text-muted uppercase">AEGIS</div>
        <h1 className="mb-4 text-xl font-semibold text-fg">Giriş yap</h1>
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
              className="h-9 w-full rounded-md border border-border bg-surface px-3 text-sm text-fg outline-none focus:border-primary"
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
              className="h-9 w-full rounded-md border border-border bg-surface px-3 text-sm text-fg outline-none focus:border-primary"
            />
          </div>
          {error !== null && <p className="text-sm text-danger">{error}</p>}
          <button
            type="submit"
            disabled={pending}
            className="h-9 w-full rounded-card bg-primary text-sm font-medium text-primary-fg disabled:opacity-60"
          >
            {pending ? "Giriş yapılıyor…" : "Giriş yap"}
          </button>
        </form>
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
