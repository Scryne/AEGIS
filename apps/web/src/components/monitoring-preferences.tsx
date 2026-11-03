"use client";

// İzleme bildirimi tercihi: derece başına hemen / günlük özet, alıcı roller.
// Alarm her durumda bu ekranda görünür; tercih yalnız e-postayı yönetir.

import { useRouter } from "next/navigation";
import { useState } from "react";

type Mode = "immediate" | "digest";
type RoleKey = "owner" | "compliance_officer" | "analyst" | "auditor";

export interface NotificationPrefs {
  critical: Mode;
  high: Mode;
  info: Mode;
  roles: RoleKey[];
  email_configured: boolean;
}

const LEVELS: { key: "critical" | "high" | "info"; label: string }[] = [
  { key: "critical", label: "Kritik" },
  { key: "high", label: "Yüksek" },
  { key: "info", label: "Bilgi" },
];

const ROLES: { key: RoleKey; label: string }[] = [
  { key: "owner", label: "Sahip" },
  { key: "compliance_officer", label: "Uyum görevlisi" },
  { key: "analyst", label: "Analist" },
  { key: "auditor", label: "Denetçi" },
];

export function MonitoringPreferences({
  initial,
  canEdit,
}: {
  initial: NotificationPrefs;
  canEdit: boolean;
}) {
  const router = useRouter();
  const [prefs, setPrefs] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (prefs.roles.length === 0) {
      setMessage({ tone: "error", text: "En az bir alıcı rol seçin." });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/api/v1/monitoring/notifications", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          critical: prefs.critical,
          high: prefs.high,
          info: prefs.info,
          roles: prefs.roles,
        }),
      });
      if (!res.ok) {
        setMessage({ tone: "error", text: "Tercih kaydedilemedi. Yetkinizi denetleyip yeniden deneyin." });
        return;
      }
      setMessage({ tone: "ok", text: "Tercih kaydedildi ve denetim izine yazıldı." });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="panel space-y-4 p-5">
      <div>
        <h2 className="eyebrow">E-posta bildirimi</h2>
        <p className="mt-1 text-xs text-muted">
          E-postada kişisel veri bulunmaz: yalnız sayı, derece ve panele bağlantı.
        </p>
      </div>

      {!prefs.email_configured && (
        <p role="status" className="rounded-md border border-warning/40 bg-warning-soft p-3 text-xs text-warning">
          E-posta sunucusu tanımlı değil, bu yüzden şu an e-posta gitmiyor. Alarmlar bu ekranda
          görünmeye devam eder. Açmak için sunucuda SMTP ayarlarını girin.
        </p>
      )}

      <fieldset disabled={!canEdit} className="space-y-4">
        <div className="space-y-2">
          {LEVELS.map((level) => (
            <label key={level.key} className="flex items-center justify-between gap-3 text-sm text-fg">
              {level.label}
              <select
                value={prefs[level.key]}
                onChange={(e) => setPrefs({ ...prefs, [level.key]: e.target.value as Mode })}
                className="field w-auto"
              >
                <option value="immediate">Hemen</option>
                <option value="digest">Günlük özet</option>
              </select>
            </label>
          ))}
        </div>

        <fieldset>
          <legend className="mb-1.5 text-xs font-medium text-muted">Alıcı roller</legend>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
            {ROLES.map((role) => (
              <label key={role.key} className="flex min-h-8 items-center gap-2 text-sm text-fg">
                <input
                  type="checkbox"
                  checked={prefs.roles.includes(role.key)}
                  onChange={(e) =>
                    setPrefs({
                      ...prefs,
                      roles: e.target.checked
                        ? [...prefs.roles, role.key]
                        : prefs.roles.filter((r) => r !== role.key),
                    })
                  }
                />
                {role.label}
              </label>
            ))}
          </div>
        </fieldset>

        {canEdit && (
          <button type="submit" disabled={busy} className="btn-primary">
            {busy ? "Kaydediliyor…" : "Tercihi kaydet"}
          </button>
        )}
      </fieldset>

      {message && (
        <p
          role={message.tone === "error" ? "alert" : "status"}
          className={`text-sm ${message.tone === "error" ? "text-danger" : "text-success"}`}
        >
          {message.text}
        </p>
      )}
    </form>
  );
}
