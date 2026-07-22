// Next.js 16: `middleware.ts` → `proxy.ts` olarak yeniden adlandırıldı (Node runtime;
// yalnız rewrite/redirect/başlık düzenler). Bu dosya SADECE UX yönlendirmesi yapar:
// oturum cookie'si yoksa korumalı sayfayı /login'e gönderir. GERÇEK yetkilendirme her
// API çağrısında backend JWT doğrulamasıyla yapılır (bkz. CLAUDE.md).

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { SESSION_COOKIE } from "@/lib/server/backend";

export function proxy(request: NextRequest): NextResponse {
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const { pathname } = request.nextUrl;

  const isProtected = pathname.startsWith("/dashboard");
  if (isProtected && !hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  if (pathname === "/login" && hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/login"],
};
