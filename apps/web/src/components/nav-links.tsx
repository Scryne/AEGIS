"use client";

// Kabuk gezinmesi — aktif sayfa görsel olarak ve `aria-current` ile işaretlenir.
// Dar ekranda yatay (kaydırılabilir) şerit, genişte dikey liste.

import Link from "next/link";
import { usePathname } from "next/navigation";

export interface NavItem {
  label: string;
  href: string;
}

export function NavLinks({ items }: { items: NavItem[] }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Ana gezinme" className="flex gap-1 overflow-x-auto md:flex-col">
      {items.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`shrink-0 rounded-md px-3 py-2 text-sm font-medium whitespace-nowrap ${
              active ? "bg-bg text-primary" : "text-fg hover:bg-bg"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
