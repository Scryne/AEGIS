"use client";

// Entegrasyonlar (E3.4): API anahtarı açma/iptal ve webhook yönetimi. Tam anahtar ve imza sırrı
// yalnız oluşturulduğu an gösterilir; sayfa yenilenince bir daha görünmez (backend saklamaz).

import { useRouter } from "next/navigation";
import { useId, useState } from "react";

async function call(url: string, method: string, body?: unknown) {
  try {
    const res = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = (await res.json().catch(() => null)) as Record<string, unknown> | null;
    const message = (data as { error?: { message?: string } } | null)?.error?.message;
    return { ok: res.ok, data, message: message ?? (res.ok ? null : "İşlem yapılamadı.") };
  } catch {
    return { ok: false, data: null, message: "Sunucuya ulaşılamadı." };
  }
}

function SecretOnce({ label, value, onDone }: { label: string; value: string; onDone: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div role="status" className="space-y-2 rounded-md border border-warning bg-warning/10 p-3">
      <p className="text-sm font-medium text-fg">{label} — yalnız şimdi gösteriliyor</p>
      <code className="block font-mono text-xs break-all text-fg">{value}</code>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value);
              setCopied(true);
            } catch {
              setCopied(false);
            }
          }}
          className="rounded-md border border-border bg-surface px-3 py-1 text-xs font-medium text-fg"
        >
          {copied ? "Kopyalandı" : "Kopyala"}
        </button>
        <button type="button" onClick={onDone} className="px-3 py-1 text-xs text-muted hover:text-fg">
          Kaydettim, kapat
        </button>
      </div>
    </div>
  );
}

export function ApiKeyCreate() {
  const router = useRouter();
  const nameId = useId();
  const roleId = useId();
  const daysId = useId();
  const [name, setName] = useState("");
  const [role, setRole] = useState("analyst");
  const [days, setDays] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);

  if (created) {
    return (
      <SecretOnce
        label="API anahtarı"
        value={created}
        onDone={() => {
          setCreated(null);
          router.refresh();
        }}
      />
    );
  }

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        const r = await call("/api/v1/api-keys", "POST", {
          name: name.trim(),
          role,
          expires_in_days: days ? Number(days) : null,
        });
        setBusy(false);
        if (!r.ok) {
          setError(r.message);
          return;
        }
        setName("");
        setCreated(String((r.data as { key: string }).key));
      }}
      className="grid gap-2 sm:grid-cols-[1fr_13rem_8rem_auto] sm:items-end"
    >
      <label htmlFor={nameId} className="space-y-1 text-xs text-muted">
        <span className="block">Ad (nerede kullanılacak)</span>
        <input
          id={nameId}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          minLength={2}
          placeholder="ör. ERP müşteri kabul"
          className="field"
        />
      </label>
      <label htmlFor={roleId} className="space-y-1 text-xs text-muted">
        <span className="block">Yetki</span>
        <select
          id={roleId}
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="field"
        >
          <option value="analyst">Analist (tarar, okur)</option>
          <option value="auditor">Denetçi (yalnız okur)</option>
        </select>
      </label>
      <label htmlFor={daysId} className="space-y-1 text-xs text-muted">
        <span className="block">Süre (gün)</span>
        <input
          id={daysId}
          type="number"
          min={1}
          max={730}
          value={days}
          onChange={(e) => setDays(e.target.value)}
          placeholder="süresiz"
          className="field"
        />
      </label>
      <button
        type="submit"
        disabled={busy}
        className="btn-primary"
      >
        {busy ? "Açılıyor…" : "Anahtar aç"}
      </button>
      {error && (
        <p role="alert" className="text-sm text-danger sm:col-span-4">
          {error}
        </p>
      )}
    </form>
  );
}

export function ApiKeyRevoke({ keyId, name }: { keyId: string; name: string }) {
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!confirm) {
    return (
      <button type="button" onClick={() => setConfirm(true)} className="text-xs text-danger underline">
        İptal et
      </button>
    );
  }
  return (
    <span className="flex flex-wrap items-center gap-2 text-xs">
      <span className="text-fg">&quot;{name}&quot; anahtarı hemen çalışmaz olacak.</span>
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          await call(`/api/v1/api-keys/${keyId}`, "DELETE");
          setBusy(false);
          router.refresh();
        }}
        className="rounded border border-danger px-2 py-0.5 font-medium text-danger"
      >
        Anahtarı iptal et
      </button>
      <button type="button" onClick={() => setConfirm(false)} className="text-muted">
        Vazgeç
      </button>
    </span>
  );
}

export function WebhookCreate({ events }: { events: string[] }) {
  const router = useRouter();
  const urlId = useId();
  const [url, setUrl] = useState("");
  const [picked, setPicked] = useState<string[]>(["alert.raised", "case.updated"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);

  if (secret) {
    return (
      <SecretOnce
        label="İmza sırrı"
        value={secret}
        onDone={() => {
          setSecret(null);
          router.refresh();
        }}
      />
    );
  }

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        const r = await call("/api/v1/webhooks", "POST", { url: url.trim(), events: picked });
        setBusy(false);
        if (!r.ok) {
          setError(r.message);
          return;
        }
        setUrl("");
        setSecret(String((r.data as { secret: string }).secret));
      }}
      className="space-y-3"
    >
      <label htmlFor={urlId} className="block space-y-1 text-xs text-muted">
        <span className="block">Alıcı adres (https)</span>
        <input
          id={urlId}
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          placeholder="https://erp.kurumunuz.com.tr/aegis/webhook"
          className="field font-mono"
        />
      </label>
      <fieldset className="flex flex-wrap gap-x-4 gap-y-2">
        <legend className="mb-1 text-xs text-muted">Olaylar</legend>
        {events.map((ev) => (
          <label key={ev} className="flex items-center gap-1.5 text-sm text-fg">
            <input
              type="checkbox"
              className="size-4"
              checked={picked.includes(ev)}
              onChange={() =>
                setPicked(picked.includes(ev) ? picked.filter((x) => x !== ev) : [...picked, ev])
              }
            />
            <span className="font-mono text-xs">{ev}</span>
          </label>
        ))}
      </fieldset>
      <button
        type="submit"
        disabled={busy || picked.length === 0}
        className="btn-primary"
      >
        {busy ? "Ekleniyor…" : "Webhook ekle"}
      </button>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </form>
  );
}

export function WebhookActions({ id, active }: { id: string; active: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);

  async function run(path: string, method: string, body?: unknown, done?: (d: unknown) => void) {
    setBusy(true);
    setNote(null);
    const r = await call(`/api/v1/webhooks/${id}${path}`, method, body);
    setBusy(false);
    if (!r.ok) {
      setNote(r.message);
      return;
    }
    done?.(r.data);
    router.refresh();
  }

  if (secret) return <SecretOnce label="Yeni imza sırrı" value={secret} onDone={() => setSecret(null)} />;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <button
        type="button"
        disabled={busy || !active}
        onClick={() => run("/test", "POST", undefined, () => setNote("Test olayı sıraya alındı; birkaç saniye içinde gönderilir."))}
        className="rounded border border-border px-2 py-1 font-medium text-fg disabled:opacity-50"
      >
        Test gönder
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => run("", "PATCH", { active: !active })}
        className="rounded border border-border px-2 py-1 font-medium text-fg disabled:opacity-50"
      >
        {active ? "Durdur" : "Etkinleştir"}
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => run("/rotate-secret", "POST", undefined, (d) => setSecret(String((d as { secret: string }).secret)))}
        className="rounded border border-border px-2 py-1 font-medium text-fg disabled:opacity-50"
      >
        Sırrı yenile
      </button>
      {note && (
        <span role="status" className="text-muted">
          {note}
        </span>
      )}
    </div>
  );
}

export function Redeliver({ deliveryId }: { deliveryId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <button
      type="button"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        await call(`/api/v1/webhooks/deliveries/${deliveryId}/redeliver`, "POST");
        setBusy(false);
        router.refresh();
      }}
      className="text-xs text-primary underline disabled:opacity-50"
    >
      Yeniden gönder
    </button>
  );
}
