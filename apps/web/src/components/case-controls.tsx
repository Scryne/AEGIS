"use client";

// Vaka ayrıntısının etkileşimli parçaları (E3.2): durum geçişi, atama, son tarih, EDD maddesi,
// yorum. Kurallar backend'dedir (lifecycle); burada yalnız izin verilen eylemler gösterilir ve
// sunucunun hata mesajı olduğu gibi aktarılır.

import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import {
  ACTION_LABELS,
  REASON_ACTIONS,
  type CaseAction,
  type ChecklistItem,
  type Member,
} from "@/lib/cases";

async function send(url: string, method: string, body: unknown): Promise<string | null> {
  try {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) return null;
    const data = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
    return data?.error?.message ?? "İşlem kaydedilemedi.";
  } catch {
    return "Sunucuya ulaşılamadı.";
  }
}

function useSubmit() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(url: string, method: string, body: unknown): Promise<boolean> {
    setBusy(true);
    setError(null);
    const err = await send(url, method, body);
    setBusy(false);
    if (err) {
      setError(err);
      return false;
    }
    router.refresh();
    return true;
  }
  return { busy, error, run };
}

const ACTION_STYLE: Record<CaseAction, string> = {
  start_review: "bg-primary text-primary-fg",
  escalate: "border border-danger text-danger",
  approve: "bg-primary text-primary-fg",
  close: "border border-border text-fg",
  reopen: "border border-border text-fg",
};

export function CaseActions({
  caseId,
  actions,
  eddOpen,
}: {
  caseId: string;
  actions: CaseAction[];
  eddOpen: boolean;
}) {
  const { busy, error, run } = useSubmit();
  const [pending, setPending] = useState<CaseAction | null>(null);
  const [reason, setReason] = useState("");
  const reasonId = useId();

  if (actions.length === 0) {
    return <p className="text-sm text-muted">Bu vakada sizin için bekleyen bir eylem yok.</p>;
  }

  async function submit(action: CaseAction) {
    const ok = await run(`/api/v1/cases/${caseId}/actions`, "POST", {
      action,
      reason: reason.trim() || null,
    });
    if (ok) {
      setPending(null);
      setReason("");
    }
  }

  function choose(action: CaseAction) {
    if (REASON_ACTIONS.includes(action)) {
      setPending(action);
      return;
    }
    void submit(action);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {actions.map((a) => (
          <button
            key={a}
            type="button"
            disabled={busy}
            onClick={() => choose(a)}
            aria-pressed={pending === a}
            className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${ACTION_STYLE[a]}`}
          >
            {ACTION_LABELS[a]}
          </button>
        ))}
      </div>
      {pending && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit(pending);
          }}
          className="space-y-2 rounded-md border border-border bg-bg p-3"
        >
          <label htmlFor={reasonId} className="block text-sm font-medium text-fg">
            {ACTION_LABELS[pending]}: gerekçe
          </label>
          <textarea
            id={reasonId}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            required
            minLength={10}
            placeholder="Ne incelendi, hangi kanıta dayanıyor? (en az 10 karakter)"
            className="field"
          />
          {(pending === "approve" || pending === "close") && eddOpen && (
            <p className="text-xs text-warning">
              EDD kontrol listesi tamamlanmadan bu karar kaydedilmez.
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={busy}
              className="btn-primary"
            >
              {busy ? "Kaydediliyor…" : "Kaydet"}
            </button>
            <button
              type="button"
              onClick={() => setPending(null)}
              className="rounded-md px-3 py-1.5 text-sm text-muted hover:text-fg"
            >
              Vazgeç
            </button>
          </div>
        </form>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

export function CaseAssign({
  caseId,
  assignee,
  members,
  canDue,
  dueAt,
}: {
  caseId: string;
  assignee: string | null;
  members: Member[];
  canDue: boolean;
  dueAt: string | null;
}) {
  const { busy, error, run } = useSubmit();
  const assignId = useId();
  const dueId = useId();
  const [due, setDue] = useState(dueAt ? dueAt.slice(0, 10) : "");

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="space-y-1">
        <label htmlFor={assignId} className="block text-xs text-muted">
          Atanan
        </label>
        <select
          id={assignId}
          defaultValue={assignee ?? ""}
          disabled={busy}
          onChange={(e) =>
            void run(`/api/v1/cases/${caseId}/assignee`, "PUT", { user_id: e.target.value || null })
          }
          className="field"
        >
          <option value="">Atanmadı</option>
          {members.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {m.full_name ?? m.email}
            </option>
          ))}
        </select>
      </div>
      {canDue && (
        <form
          className="space-y-1"
          onSubmit={(e) => {
            e.preventDefault();
            if (due) void run(`/api/v1/cases/${caseId}/due`, "PUT", { due_at: `${due}T17:00:00+03:00` });
          }}
        >
          <label htmlFor={dueId} className="block text-xs text-muted">
            Son tarih
          </label>
          <div className="flex gap-2">
            <input
              id={dueId}
              type="date"
              value={due}
              onChange={(e) => setDue(e.target.value)}
              className="field min-w-0 flex-1"
            />
            <button
              type="submit"
              disabled={busy || !due}
              className="btn-quiet"
            >
              Değiştir
            </button>
          </div>
        </form>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger sm:col-span-2">
          {error}
        </p>
      )}
    </div>
  );
}

function EddRow({ caseId, item, editable }: { caseId: string; item: ChecklistItem; editable: boolean }) {
  const { busy, error, run } = useSubmit();
  const [note, setNote] = useState(item.note ?? "");
  const [editing, setEditing] = useState(false);
  const noteId = useId();

  return (
    <li className="space-y-2 py-3">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={`mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border text-xs ${
            item.done ? "border-success bg-success text-primary-fg" : "border-border text-transparent"
          }`}
        >
          ✓
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm text-fg">
            <span className="sr-only">{item.done ? "Tamamlandı: " : "Bekliyor: "}</span>
            {item.label}
          </p>
          {item.done && item.note && <p className="mt-0.5 text-xs text-muted">{item.note}</p>}
        </div>
        {editable && !editing && (
          <button
            type="button"
            onClick={() => (item.done ? void run(`/api/v1/cases/${caseId}/edd/${item.key}`, "PUT", { done: false }) : setEditing(true))}
            disabled={busy}
            className="shrink-0 text-xs text-primary underline disabled:opacity-50"
          >
            {item.done ? "Geri al" : "Tamamla"}
          </button>
        )}
      </div>
      {editing && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (await run(`/api/v1/cases/${caseId}/edd/${item.key}`, "PUT", { done: true, note: note.trim() })) {
              setEditing(false);
            }
          }}
          className="ml-8 flex flex-col gap-2 sm:flex-row"
        >
          <label htmlFor={noteId} className="sr-only">
            Ne yapıldı
          </label>
          <input
            id={noteId}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            required
            placeholder="Ne yapıldı, kanıt nerede?"
            className="field min-w-0 flex-1"
          />
          <button
            type="submit"
            disabled={busy}
            className="btn-primary"
          >
            Kaydet
          </button>
        </form>
      )}
      {error && (
        <p role="alert" className="ml-8 text-xs text-danger">
          {error}
        </p>
      )}
    </li>
  );
}

export function EddChecklist({
  caseId,
  items,
  editable,
}: {
  caseId: string;
  items: ChecklistItem[];
  editable: boolean;
}) {
  return (
    <ul className="divide-y divide-border">
      {items.map((item) => (
        <EddRow key={item.key} caseId={caseId} item={item} editable={editable} />
      ))}
    </ul>
  );
}

export function CaseCommentForm({ caseId }: { caseId: string }) {
  const { busy, error, run } = useSubmit();
  const [body, setBody] = useState("");
  const id = useId();
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        if (await run(`/api/v1/cases/${caseId}/comments`, "POST", { body: body.trim() })) setBody("");
      }}
      className="space-y-2"
    >
      <label htmlFor={id} className="sr-only">
        Yorum
      </label>
      <textarea
        id={id}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={2}
        required
        minLength={2}
        placeholder="Not ekleyin (silinmez, düzenlenmez)"
        className="field"
      />
      <button
        type="submit"
        disabled={busy || body.trim().length < 2}
        className="btn-quiet"
      >
        {busy ? "Ekleniyor…" : "Yorum ekle"}
      </button>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </form>
  );
}

export function CaseCreate({ entityId }: { entityId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [severity, setSeverity] = useState("info");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();
  const sevId = useId();
  const noteId = useId();

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="btn-quiet"
      >
        Vaka aç
      </button>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity_id: entityId, title: title.trim(), severity, note: note.trim() || null }),
      });
      const body = (await res.json().catch(() => null)) as { id?: string; error?: { message?: string } } | null;
      if (!res.ok || !body?.id) {
        setError(body?.error?.message ?? "Vaka açılamadı.");
        return;
      }
      router.push(`/cases/${body.id}`);
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <div className="grid gap-2 sm:grid-cols-[1fr_10rem]">
        <div className="space-y-1">
          <label htmlFor={titleId} className="block text-xs text-muted">
            Konu
          </label>
          <input
            id={titleId}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            minLength={3}
            maxLength={200}
            placeholder="ör. Ortaklık yapısı değişti"
            className="field"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor={sevId} className="block text-xs text-muted">
            Derece
          </label>
          <select
            id={sevId}
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className="field"
          >
            <option value="info">Bilgi</option>
            <option value="high">Yüksek</option>
            <option value="critical">Kritik</option>
          </select>
        </div>
      </div>
      <div className="space-y-1">
        <label htmlFor={noteId} className="block text-xs text-muted">
          İlk not (isteğe bağlı)
        </label>
        <textarea
          id={noteId}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          className="field"
        />
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="btn-primary"
        >
          {busy ? "Açılıyor…" : "Vakayı aç"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="px-3 py-1.5 text-sm text-muted hover:text-fg">
          Vazgeç
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </form>
  );
}
