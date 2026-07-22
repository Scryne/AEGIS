// Oturum uçları: backend'e giriş yapar, JWT'leri httpOnly cookie'lere yazar.
//
// Token'lar tarayıcı JS'ine hiç verilmez (XSS'e karşı); API çağrıları aynı-origin
// /api/v1 proxy'si üzerinden, cookie'deki erişim token'ı Authorization'a çevrilerek gider.

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import {
  ACCESS_MAX_AGE_SECONDS,
  API_URL,
  REFRESH_COOKIE,
  REFRESH_MAX_AGE_SECONDS,
  SESSION_COOKIE,
} from "@/lib/server/backend";

const secure = process.env.NODE_ENV === "production";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credentials: unknown = await request.json().catch(() => null);
  if (credentials === null || typeof credentials !== "object") {
    return NextResponse.json(
      { error: { code: "validation_error", message: "Geçersiz istek gövdesi." } },
      { status: 422 },
    );
  }

  const headers = new Headers({ "content-type": "application/json" });
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor !== null) headers.set("x-forwarded-for", forwardedFor);

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST",
      headers,
      body: JSON.stringify(credentials),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { error: { code: "internal_error", message: "Kimlik servisine ulaşılamadı." } },
      { status: 502 },
    );
  }
  const payload: unknown = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok) {
    return NextResponse.json(
      payload ?? { error: { code: "internal_error", message: "Giriş başarısız." } },
      { status: backendResponse.status },
    );
  }

  const tokens = payload as { access_token?: string; refresh_token?: string };
  if (tokens.access_token === undefined || tokens.refresh_token === undefined) {
    return NextResponse.json(
      { error: { code: "internal_error", message: "Beklenmeyen giriş yanıtı." } },
      { status: 502 },
    );
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, tokens.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: ACCESS_MAX_AGE_SECONDS,
  });
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: REFRESH_MAX_AGE_SECONDS,
  });
  return response;
}

export async function DELETE(): Promise<NextResponse> {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete(SESSION_COOKIE);
  response.cookies.delete(REFRESH_COOKIE);
  return response;
}
