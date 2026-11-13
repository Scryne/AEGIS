"use client";

// Parola belirleme: hem parola sıfırlama e-postasındaki hem de kiracı açma davetindeki
// (scripts/kiraci_ac.py) bağlantı buraya gelir. Jeton tarayıcıda saklanmaz; doğrudan
// same-origin proxy üzerinden /auth/password-reset/confirm'e gönderilir.

import { Wordmark } from "@/components/nav-links";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

const MIN_LENGTH = 8;

/**
 * Jetonsuz açılış: parola sıfırlama bağlantısı istenir. Sunucu adres kayıtlı olsun olmasın aynı
 * cevabı verir (hesap varlığı sızdırılmaz); arayüz de aynı nötr cümleyi gösterir.
 */
function RequestLink() {
  const [email, setEmail] = useState("");
  const [pending, setPending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const response = await fetch("/api/v1/auth/password-reset/request", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      if (response.status === 429) {
        setError("Çok fazla deneme yapıldı. Birkaç dakika sonra yeniden deneyin.");
        return;
      }
      if (!response.ok) {
        setError("İstek alınamadı. E-posta adresini denetleyip yeniden deneyin.");
        return;
      }
      setSent(true);
    } catch {
      setError("Sunucuya ulaşılamadı; bağlantınızı denetleyip yeniden deneyin.");
    } finally {
      setPending(false);
    }
  }

  if (sent) {
    return (
      <div className="space-y-4">
        <p role="status" className="text-sm text-fg">
          Bu adres bir AEGIS hesabına kayıtlıysa parola belirleme bağlantısı birkaç dakika içinde gelir.
          Bağlantı sınırlı süre geçerlidir.
        </p>
        <Link href="/login" className="btn-quiet inline-flex w-full justify-center">
          Giriş sayfasına dön
        </Link>
      </div>
    );
  }

  return (
    <>
      <p className="mb-6 text-sm text-muted">
        Hesabınızın e-posta adresini yazın; parola belirleme bağlantısı gönderelim.
      </p>
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <label htmlFor="reset-email" className="text-sm font-medium text-fg">
            E-posta
          </label>
          <input
            id="reset-email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="field"
          />
        </div>
        {error !== null && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <button type="submit" disabled={pending} className="btn-primary w-full">
          {pending ? "Gönderiliyor…" : "Bağlantı gönder"}
        </button>
        <Link href="/login" className="back-link">
          ← Giriş sayfasına dön
        </Link>
      </form>
    </>
  );
}

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (password.length < MIN_LENGTH) {
      setError(`Parola en az ${MIN_LENGTH} karakter olmalı.`);
      return;
    }
    if (password !== repeat) {
      setError("İki parola aynı değil.");
      return;
    }
    setPending(true);
    try {
      const response = await fetch("/api/v1/auth/password-reset/confirm", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      });
      if (response.status === 204) {
        setDone(true);
        return;
      }
      if (response.status === 422 || response.status === 400) {
        throw new Error("Bağlantı geçersiz ya da süresi dolmuş. Yeni bir bağlantı isteyin.");
      }
      throw new Error("Parola kaydedilemedi; lütfen sonra tekrar deneyin.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bilinmeyen hata.");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-8">
          <Wordmark />
        </div>
        <h1 className="page-title mb-1">{token === "" && !done ? "Parolamı unuttum" : "Parola belirle"}</h1>
        {done ? (
          <div className="space-y-4">
            <p role="status" className="text-sm text-fg">
              Parolanız kaydedildi. Artık giriş yapabilirsiniz.
            </p>
            <Link href="/login" className="btn-primary inline-flex w-full justify-center">
              Giriş yap
            </Link>
          </div>
        ) : token === "" ? (
          <RequestLink />
        ) : (
          <>
            <p className="mb-6 text-sm text-muted">
              Hesabınız için yeni bir parola seçin (en az {MIN_LENGTH} karakter).
            </p>
            <form onSubmit={onSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="password" className="text-sm font-medium text-fg">
                  Yeni parola
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={MIN_LENGTH}
                  maxLength={128}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="field"
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="repeat" className="text-sm font-medium text-fg">
                  Yeni parola (tekrar)
                </label>
                <input
                  id="repeat"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={repeat}
                  onChange={(e) => setRepeat(e.target.value)}
                  className="field"
                />
              </div>
              {error !== null && (
                <p role="alert" className="text-sm text-danger">
                  {error}
                </p>
              )}
              <button type="submit" disabled={pending} className="btn-primary w-full">
                {pending ? "Kaydediliyor…" : "Parolayı kaydet"}
              </button>
            </form>
          </>
        )}
      </div>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetForm />
    </Suspense>
  );
}
