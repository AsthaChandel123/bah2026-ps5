# Bharat Climate Twin — Next.js dashboard (multi-stage production image).
#
# Build (from the repo root or this dir):
#   docker build -t bct-frontend ./frontend
# Run:
#   docker run --rm -p 3000:3000 bct-frontend
#   # → http://localhost:3000  (reads bundled /data/*.json by default)
#
# To point the dashboard at the FastAPI backend instead of the bundled static
# data, set NEXT_PUBLIC_API_BASE *at build time* (it is inlined into the client
# bundle by Next.js):
#   docker build --build-arg NEXT_PUBLIC_API_BASE=http://localhost:8000/api \
#       -t bct-frontend ./frontend
# (docker-compose.yml does exactly this.)
#
# Uses Next.js `output: "standalone"` (see next.config.mjs) so the runtime image
# ships only the traced server + its minimal node_modules.

# ── 1) deps: install node_modules with good layer caching ──────────────────
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# ── 2) builder: compile the production build ───────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* must be present at build time to be inlined into the client.
ARG NEXT_PUBLIC_API_BASE=""
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── 3) runner: minimal runtime image ───────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Run as an unprivileged user.
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# `output: standalone` traces a self-contained server bundle. `public/` and
# `.next/static` are NOT included automatically — copy them in explicitly.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

# The standalone bundle emits server.js at the app root.
CMD ["node", "server.js"]
