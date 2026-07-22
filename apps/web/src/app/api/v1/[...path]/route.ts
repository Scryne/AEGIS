// Aynı-origin API proxy'si: /api/v1/* isteklerini backend'e iletir.
//
// Cookie'deki erişim token'ı Authorization'a çevrilir; tarayıcı token'ı hiç görmez.
// Erişim token'ı süresi dolmuşsa (401) ve yenileme cookie'si varsa bir kez /auth/refresh
// ile tazelenir, yeni erişim token'ı cookie'ye yazılır ve istek yeniden denenir.

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import {
  ACCESS_MAX_AGE_SECONDS,
  API_URL,
  REFRESH_COOKIE,
  SESSION_COOKIE,
} from "@/lib/server/backend";

export const dynamic = "force-dynamic";

const FORWARDED_REQUEST_HEADERS = ["content-type", "accept"];
const secure = process.env.NODE_ENV === "production";

function buildHeaders(request: NextRequest, token: string | undefined): Headers {
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor !== null) headers.set("x-forwarded-for", forwardedFor);
  if (token !== undefined) headers.set("authorization", `Bearer ${token}`);
  return headers;
}

async function tryRefresh(refreshToken: string): Promise<string | null> {
  try {
    const res = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    });
    if (!res.ok) return null;
    const body = (await res.json().catch(() => null)) as { access_token?: string } | null;
    return body?.access_token ?? null;
  } catch {
    return null;
  }
}

async function proxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await params;
  const target = new URL(`${API_URL}/api/v1/${path.join("/")}`);
  target.search = request.nextUrl.search;

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const bodyBuffer = hasBody ? await request.arrayBuffer() : undefined;

  const accessToken = request.cookies.get(SESSION_COOKIE)?.value;
  let backendResponse = await fetch(target, {
    method: request.method,
    headers: buildHeaders(request, accessToken),
    body: bodyBuffer,
    cache: "no-store",
  });

  // 401 → erişim token'ı tazelenmeyi dene (yenileme cookie'si varsa), bir kez yeniden dene.
  let refreshedAccess: string | null = null;
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
  if (backendResponse.status === 401 && refreshToken !== undefined) {
    refreshedAccess = await tryRefresh(refreshToken);
    if (refreshedAccess !== null) {
      backendResponse = await fetch(target, {
        method: request.method,
        headers: buildHeaders(request, refreshedAccess),
        body: bodyBuffer,
        cache: "no-store",
      });
    }
  }

  const responseHeaders = new Headers(backendResponse.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");
  responseHeaders.delete("transfer-encoding");

  const out = new NextResponse(backendResponse.body, {
    status: backendResponse.status,
    headers: responseHeaders,
  });

  if (refreshedAccess !== null) {
    // Tazelenen erişim token'ını cookie'ye yaz (yenileme başarılıysa).
    out.cookies.set(SESSION_COOKIE, refreshedAccess, {
      httpOnly: true,
      sameSite: "lax",
      secure,
      path: "/",
      maxAge: ACCESS_MAX_AGE_SECONDS,
    });
  } else if (backendResponse.status === 401) {
    // Tazeleme de başarısız: oturumu temizle (yönlendirme döngüsünü önler).
    out.cookies.delete(SESSION_COOKIE);
    out.cookies.delete(REFRESH_COOKIE);
  }
  return out;
}

export { proxy as DELETE, proxy as GET, proxy as PATCH, proxy as POST, proxy as PUT };
