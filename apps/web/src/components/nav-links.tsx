"use client";

// Kabuk gezinmesi. Genişte sabit mürekkep sütunu, dar ekranda açılır çekmece: 11 maddelik yatay
// şerit telefonda ekranın dışına taşıyordu. Aktif sayfa `aria-current` ve pirinç çizgiyle işaretlenir.

import {
  Activity,
  BadgeCheck,
  Building2,
  CreditCard,
  FileWarning,
  Gauge,
  Layers,
  LayoutDashboard,
  Menu,
  Plug,
  ScanSearch,
  ScrollText,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

export interface NavItem {
  label: string;
  href: string;
  group: string;
}

const ICONS: Record<string, LucideIcon> = {
  "/dashboard": LayoutDashboard,
  "/screenings": ScanSearch,
  "/batches": Layers,
  "/entities": Building2,
  "/monitoring": Activity,
  "/cases": BadgeCheck,
  "/sib": FileWarning,
  "/audit": ScrollText,
  "/quality": Gauge,
  "/integrations": Plug,
  "/plan": CreditCard,
};

export function Wordmark({ inverse = false }: { inverse?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" aria-hidden="true" className="size-6 shrink-0">
        <path
          d="M16 2.5 4.5 7v8.2c0 7.1 4.9 12.4 11.5 14.3 6.6-1.9 11.5-7.2 11.5-14.3V7z"
          fill="var(--color-seal)"
        />
        <path
          d="m11.2 16.4 3.4 3.4 6.4-7"
          fill="none"
          stroke="var(--color-ink)"
          strokeWidth="2.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span
        className={`font-mono text-sm font-semibold tracking-[0.2em] ${inverse ? "text-ink-fg" : "text-fg"}`}
      >
        AEGIS
      </span>
    </span>
  );
}

function Links({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  const pathname = usePathname();
  const groups = [...new Set(items.map((item) => item.group))];
  return (
    <nav aria-label="Ana gezinme" className="space-y-5">
      {groups.map((group) => (
        <div key={group}>
          <div className="mb-1.5 px-3 text-[11px] font-semibold tracking-[0.08em] text-ink-muted uppercase">
            {group}
          </div>
          <ul className="space-y-0.5">
            {items
              .filter((item) => item.group === group)
              .map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                const Icon = ICONS[item.href];
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={`flex min-h-10 items-center gap-2.5 rounded-md border-l-2 px-2.5 text-sm transition-colors ${
                        active
                          ? "border-seal bg-ink-raised font-medium text-ink-fg"
                          : "border-transparent text-ink-muted hover:bg-ink-raised/60 hover:text-ink-fg"
                      }`}
                    >
                      {Icon && <Icon aria-hidden="true" className="size-4 shrink-0" strokeWidth={1.75} />}
                      {item.label}
                    </Link>
                  </li>
                );
              })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function AppShell({
  items,
  account,
  children,
}: {
  items: NavItem[];
  account: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const openRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const trigger = openRef.current;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      trigger?.focus();
    };
  }, [open]);

  return (
    <div className="min-h-dvh md:pl-60">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col bg-ink md:flex">
        <div className="flex h-14 items-center border-b border-ink-line px-5">
          <Link href="/dashboard" aria-label="AEGIS panel">
            <Wordmark inverse />
          </Link>
        </div>
        <div className="flex-1 overflow-y-auto px-2.5 py-5">
          <Links items={items} />
        </div>
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Gezinme">
          <button
            type="button"
            aria-label="Gezinmeyi kapat"
            tabIndex={-1}
            className="absolute inset-0 bg-ink/60"
            onClick={() => setOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-ink">
            <div className="flex h-14 items-center justify-between border-b border-ink-line px-4">
              <Wordmark inverse />
              <button
                ref={closeRef}
                type="button"
                aria-label="Gezinmeyi kapat"
                onClick={() => setOpen(false)}
                className="grid size-10 place-items-center rounded-md text-ink-fg hover:bg-ink-raised"
              >
                <X aria-hidden="true" className="size-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-2.5 py-5">
              <Links items={items} onNavigate={() => setOpen(false)} />
            </div>
          </div>
        </div>
      )}

      <header className="sticky top-0 z-10 flex h-14 items-center justify-between gap-3 border-b border-border bg-surface/95 px-4 backdrop-blur md:px-8">
        <div className="flex min-w-0 items-center gap-2">
          <button
            ref={openRef}
            type="button"
            aria-label="Gezinmeyi aç"
            aria-expanded={open}
            onClick={() => setOpen(true)}
            className="grid size-10 place-items-center rounded-md text-fg hover:bg-subtle md:hidden"
          >
            <Menu aria-hidden="true" className="size-5" />
          </button>
          <span className="md:hidden">
            <Wordmark />
          </span>
        </div>
        {account}
      </header>

      <main className="min-w-0 px-4 py-6 md:px-8 md:py-8">{children}</main>
    </div>
  );
}
