// Sunucu tarafı (route handler / server component) yardımcıları — tarayıcıya sızmaz.

import { cookies } from "next/headers";

/** Backend API taban URL'i (yalnızca sunucuda okunur). */
export const API_URL =
  process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Oturum (erişim) token'ının saklandığı httpOnly cookie adı. */
export const SESSION_COOKIE = "aegis_token";

/** Yenileme token'ının saklandığı httpOnly cookie adı. */
export const REFRESH_COOKIE = "aegis_refresh";

/** Erişim cookie ömrü — backend erişim token'ı ömrüyle hizalı (60 dk). */
export const ACCESS_MAX_AGE_SECONDS = 60 * 60;

/** Yenileme cookie ömrü — backend yenileme token'ı ömrüyle hizalı (30 gün). */
export const REFRESH_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;

/**
 * Sunucu bileşeninden backend'e kimlikli istek (cookie'deki erişim token'ı ile).
 * Token tarayıcıya hiç açılmaz. 401 durumunda çağıran /login'e yönlendirir.
 */
export async function serverFetch(path: string): Promise<Response> {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  return fetch(`${API_URL}/api/v1${path}`, {
    headers: token ? { authorization: `Bearer ${token}` } : {},
    cache: "no-store",
  });
}
