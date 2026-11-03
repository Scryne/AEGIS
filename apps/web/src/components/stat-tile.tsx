import Link from "next/link";

// Sayaç: etiket + değer + bağlam. Ton yalnız değer karar gerektirdiğinde verilir; kuyruk boşken
// sayfa sakin kalır. Bağlantılı sürüm ilgili kuyruğa götürür.

export type StatTone = "danger" | "warning" | "success" | "neutral";

const VALUE_TONE: Record<StatTone, string> = {
  danger: "text-danger",
  warning: "text-warning",
  success: "text-success",
  neutral: "text-fg",
};

export function StatTile({
  label,
  value,
  hint,
  tone = "neutral",
  href,
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: StatTone;
  href?: string;
}) {
  const body = (
    <div className={`rail rail-${tone} h-full`}>
      <div className="text-xs font-medium text-muted">{label}</div>
      <div className={`mt-1 font-mono text-[1.75rem] leading-none font-medium tabular-nums ${VALUE_TONE[tone]}`}>
        {value}
      </div>
      {hint && <div className="mt-1.5 text-xs text-muted">{hint}</div>}
    </div>
  );
  if (href) {
    return (
      <Link href={href} className="panel block p-4 transition-colors hover:border-border-strong">
        {body}
      </Link>
    );
  }
  return <div className="panel p-4">{body}</div>;
}
