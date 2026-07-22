# AEGIS web imajı — Next.js 16 standalone çıktısı, pnpm monorepo, çok aşamalı.
# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS base
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable

# ── Build aşaması ────────────────────────────────────────────────────────────
FROM base AS build
WORKDIR /app

# 1) Yalnızca manifestler + kilit — bağımlılık katmanını önbelleğe al.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

# 2) Kaynak + build. NEXT_PUBLIC_* build anında gömülür; tarayıcı host'ta
# çalıştığından API'nin host adresi (localhost:8000) varsayılandır.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_OUTPUT=standalone
COPY apps/web apps/web
RUN pnpm --filter @aegis/web build

# ── Çalıştırma aşaması ───────────────────────────────────────────────────────
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN groupadd --system --gid 1001 nodejs \
    && useradd --system --uid 1001 --gid nodejs nextjs

# Standalone çıktı, izleme köküne göre monorepo yapısını korur.
COPY --from=build --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/apps/web/.next/static ./apps/web/.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
