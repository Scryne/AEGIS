"use client";

// Ekip: üyeler ve rolleri. Sahip yeni üye davet eder, rol değiştirir, etkinleşmemiş üyenin
// davetini yeniler; diğer roller listeyi yalnız görür. Yetki API'de (RequireOwner) ayrıca
// kapılıdır. SMTP yoksa davet bağlantısı ekranda bir kez gösterilir; sahip kendisi iletir.

import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";

export type TeamRole = "owner" | "compliance_officer" | "analyst" | "auditor";

export interface TeamMember {
  user_id: string;
  email: string;
  full_name: string | null;
  role: TeamRole;
  pending?: boolean;
}

interface InviteResult {
  member: TeamMember;
  channel: "smtp" | "manual";
  delivered: boolean;
  valid_hours: number;
  invite_link: string | null;
}

const ROLES: { value: TeamRole; label: string; hint: string }[] = [
  { value: "owner", label: "Sahip", hint: "Tam yetki; ekibi ve planı yönetir." },
  { value: "compliance_officer", label: "Uyum Uzmanı", hint: "Tarar, eşleşmeye karar verir, rapor ve ŞİB hazırlar." },
  { value: "analyst", label: "Analist", hint: "Dosya hazırlar ve tarar; karar veremez." },
  { value: "auditor", label: "Denetçi", hint: "Her şeyi okur, hiçbir şeyi değiştiremez." },
];
const LABEL: Record<TeamRole, string> = Object.fromEntries(ROLES.map((r) => [r.value, r.label])) as Record<
  TeamRole,
  string
>;

async function errorMessage(res: Response, fallback: string): Promise<string> {
  const body = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
  return body?.error?.message ?? fallback;
}

function InviteNotice({ result, onClose }: { result: InviteResult; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const who = result.member.full_name ?? result.member.email;
  return (
    <div role="status" className="space-y-2 rounded-md border border-border bg-subtle p-3 text-sm">
      {result.delivered ? (
        <p className="text-fg">
          Davet {result.member.email} adresine gönderildi. Bağlantı {result.valid_hours} saat geçerli.
        </p>
      ) : (
        <>
          <p className="text-fg">
            {result.channel === "smtp"
              ? "E-posta gönderilemedi. "
              : "Bu kurulumda e-posta gönderimi yapılandırılmamış. "}
            Bağlantıyı {who} ile güvenli bir kanaldan paylaşın; {result.valid_hours} saat geçerli ve bu ekranı
            kapatınca yeniden gösterilmez.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <input
              readOnly
              value={result.invite_link ?? ""}
              aria-label="Davet bağlantısı"
              onFocus={(e) => e.currentTarget.select()}
              className="field min-w-0 flex-1 font-mono text-xs"
            />
            <button
              type="button"
              className="btn-quiet"
              onClick={() => {
                void navigator.clipboard?.writeText(result.invite_link ?? "").then(() => setCopied(true));
              }}
            >
              {copied ? "Kopyalandı" : "Kopyala"}
            </button>
          </div>
        </>
      )}
      <button type="button" onClick={onClose} className="inline-flex min-h-6 items-center text-xs text-muted underline">
        Kapat
      </button>
    </div>
  );
}

function InviteForm({ onDone }: { onDone: (r: InviteResult) => void }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<TeamRole>("analyst");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const emailId = useId();
  const nameId = useId();
  const roleId = useId();

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="btn-quiet">
        Üye davet et
      </button>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/members", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), full_name: name.trim() || null, role }),
      });
      if (!res.ok) {
        setError(
          res.status === 422
            ? "E-posta adresi geçerli değil."
            : await errorMessage(res, "Davet oluşturulamadı. Yeniden deneyin."),
        );
        return;
      }
      onDone((await res.json()) as InviteResult);
      setOpen(false);
      setEmail("");
      setName("");
      setRole("analyst");
      router.refresh();
    } catch {
      setError("Sunucuya ulaşılamadı; bağlantınızı denetleyip yeniden deneyin.");
    } finally {
      setBusy(false);
    }
  }

  const hint = ROLES.find((r) => r.value === role)?.hint;
  return (
    <form onSubmit={submit} className="space-y-3 rounded-md border border-border p-3" aria-label="Üye davet et">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor={emailId} className="block text-xs font-medium text-fg">
            E-posta
          </label>
          <input
            id={emailId}
            type="email"
            required
            autoComplete="off"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="field"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor={nameId} className="block text-xs font-medium text-fg">
            Ad soyad <span className="font-normal text-muted">(isteğe bağlı)</span>
          </label>
          <input
            id={nameId}
            maxLength={255}
            autoComplete="off"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="field"
          />
        </div>
      </div>
      <div className="space-y-1">
        <label htmlFor={roleId} className="block text-xs font-medium text-fg">
          Rol
        </label>
        <select id={roleId} value={role} onChange={(e) => setRole(e.target.value as TeamRole)} className="field">
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
        {hint && <p className="text-xs text-muted">{hint}</p>}
      </div>
      {error !== null && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy} className="btn-primary">
          {busy ? "Davet ediliyor…" : "Davet et"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="btn-quiet">
          Vazgeç
        </button>
      </div>
    </form>
  );
}

/** Çıkarma onayı: yerel <dialog> (odak tuzağı, Esc ve arka planın etkisizleşmesi tarayıcıdan). */
function RemoveMember({ member, onRemoved }: { member: TeamMember; onRemoved: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();
  const who = member.full_name ?? member.email;

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/members/${member.user_id}`, { method: "DELETE" });
      if (!res.ok) {
        setError(await errorMessage(res, "Üye çıkarılamadı."));
        return;
      }
      ref.current?.close();
      onRemoved();
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setError(null);
          ref.current?.showModal();
        }}
        className="inline-flex min-h-6 items-center text-xs text-danger underline"
      >
        Çıkar
      </button>
      <dialog
        ref={ref}
        aria-labelledby={titleId}
        className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-card border border-border bg-surface p-5 text-fg shadow-lg backdrop:bg-fg/40"
      >
        <h2 id={titleId} className="text-base font-semibold text-fg">
          {who} kurumdan çıkarılsın mı?
        </h2>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
          <li>Açık oturumları hemen kapanır; yeniden giriş yapamaz.</li>
          <li>Hesabı silinmez: verdiği kararlar ve denetim izi kayıtları adıyla kalır.</li>
          <li>Gerekirse aynı adresle yeniden davet edebilirsiniz.</li>
        </ul>
        {error !== null && (
          <p role="alert" className="mt-3 text-sm text-danger">
            {error}
          </p>
        )}
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <button type="button" onClick={() => ref.current?.close()} className="btn-quiet" disabled={busy}>
            Vazgeç
          </button>
          <button
            type="button"
            onClick={() => void remove()}
            disabled={busy}
            className="btn-primary bg-danger text-primary-fg hover:bg-danger disabled:opacity-60"
          >
            {busy ? "Çıkarılıyor…" : "Üyeyi çıkar"}
          </button>
        </div>
      </dialog>
    </>
  );
}

function MemberRow({
  member,
  isSelf,
  canManage,
  onInvite,
}: {
  member: TeamMember;
  isSelf: boolean;
  canManage: boolean;
  onInvite: (r: InviteResult) => void;
}) {
  const router = useRouter();
  const [role, setRole] = useState<TeamRole>(member.role);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectId = useId();

  async function call(url: string, init: RequestInit, fallback: string): Promise<Response | null> {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(url, init);
      if (!res.ok) {
        setError(await errorMessage(res, fallback));
        return null;
      }
      return res;
    } catch {
      setError("Sunucuya ulaşılamadı.");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function saveRole() {
    const res = await call(
      `/api/v1/members/${member.user_id}`,
      { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role }) },
      "Rol değiştirilemedi.",
    );
    if (res) router.refresh();
    else setRole(member.role);
  }

  async function reinvite() {
    const res = await call(`/api/v1/members/${member.user_id}/invite`, { method: "POST" }, "Davet yenilenemedi.");
    if (res) onInvite((await res.json()) as InviteResult);
  }

  return (
    <li className="space-y-1.5 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <div className="truncate text-sm text-fg">
            {member.full_name ?? member.email}
            {isSelf && <span className="ml-2 text-xs text-muted">(siz)</span>}
          </div>
          {member.full_name && <div className="truncate font-mono text-xs text-muted">{member.email}</div>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {member.pending && (
            <span className="rounded-full border border-warning/40 bg-warning-soft px-2.5 py-0.5 text-xs text-warning">
              Davet bekliyor
            </span>
          )}
          {canManage ? (
            <>
              <label htmlFor={selectId} className="sr-only">
                {member.full_name ?? member.email} rolü
              </label>
              <select
                id={selectId}
                value={role}
                disabled={busy}
                onChange={(e) => setRole(e.target.value as TeamRole)}
                className="field w-auto py-1 text-xs"
              >
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
              {role !== member.role && (
                <button type="button" onClick={() => void saveRole()} disabled={busy} className="btn-primary py-1 text-xs">
                  {busy ? "Kaydediliyor…" : "Rolü kaydet"}
                </button>
              )}
              {member.pending && role === member.role && (
                <button
                  type="button"
                  onClick={() => void reinvite()}
                  disabled={busy}
                  className="inline-flex min-h-6 items-center text-xs text-primary underline disabled:opacity-50"
                >
                  Daveti yenile
                </button>
              )}
              {!isSelf && role === member.role && (
                <RemoveMember member={member} onRemoved={() => router.refresh()} />
              )}
            </>
          ) : (
            <span className="rounded-full border border-border bg-subtle px-2.5 py-0.5 text-xs text-fg">
              {LABEL[member.role]}
            </span>
          )}
        </div>
      </div>
      {error !== null && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </li>
  );
}

export function TeamManager({
  members,
  currentUserId,
  canManage,
}: {
  members: TeamMember[];
  currentUserId: string;
  canManage: boolean;
}) {
  const [notice, setNotice] = useState<InviteResult | null>(null);
  return (
    <div className="mt-3 space-y-3">
      <ul className="divide-y divide-border">
        {members.map((m) => (
          <MemberRow
            key={`${m.user_id}:${m.role}`}
            member={m}
            isSelf={m.user_id === currentUserId}
            canManage={canManage}
            onInvite={setNotice}
          />
        ))}
      </ul>
      {notice !== null && <InviteNotice result={notice} onClose={() => setNotice(null)} />}
      {canManage ? (
        <>
          <InviteForm onDone={setNotice} />
          <p className="text-xs text-muted">
            Davet edilen kişi bağlantıyla parolasını belirler. Rol değişikliği üyenin bir sonraki oturum yenilemesinde
            geçerli olur; çıkarılan üyenin oturumları hemen kapanır. Her davet, rol değişikliği ve çıkarma denetim
            izine girer.
          </p>
        </>
      ) : (
        <p className="text-xs text-muted">Üye ekleme ve rol değişikliğini kurumunuzun sahibi yapar.</p>
      )}
    </div>
  );
}
