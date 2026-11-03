import { Wordmark } from "@/components/nav-links";
import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 p-6 text-center">
      <Wordmark />
      <div className="max-w-md">
        <h1 className="page-title mb-2">Sayfa bulunamadı</h1>
        <p className="text-sm text-muted-foreground">
          Bağlantı eskimiş ya da kayıt kaldırılmış olabilir. Panelden devam edebilirsiniz.
        </p>
      </div>
      <Link href="/dashboard" className="btn-primary">
        Panele dön
      </Link>
    </main>
  );
}
