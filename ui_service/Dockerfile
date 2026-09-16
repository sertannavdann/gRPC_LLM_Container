# Multi-stage build for Next.js UI service with BuildKit caching
FROM node:20-alpine AS base

# Install dependencies only when needed
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Copy package files
COPY ui_service/package.json ./
# Use BuildKit cache mount for faster npm installs
RUN --mount=type=cache,target=/root/.npm \
    npm install

# Rebuild the source code only when needed
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY ui_service/ .

# Copy shared proto to ensure single source of truth
RUN mkdir -p proto
COPY shared/proto/agent.proto ./proto/agent.proto

# Dev seam for LLM-authored canvas ops (Phase 9 plan 09, ecs/ingress.ts).
# NEXT_PUBLIC_* vars are inlined by Next.js at BUILD time, so this must be
# set here, immediately before `npm run build`, not just at runtime. Defaults
# to EMPTY (off) so a hardened/production image ships without the
# window.__nexusCanvas handle; only docker-compose.yaml's local stack opts in
# via its build.args. Setting this to anything other than "1" removes the
# handle entirely — see ecs/ingress.ts's guard.
ARG NEXT_PUBLIC_CANVAS_DEV_SEAM=""
ENV NEXT_PUBLIC_CANVAS_DEV_SEAM=${NEXT_PUBLIC_CANVAS_DEV_SEAM}

# Build Next.js
RUN npm run build

# Production image, copy all the files and run next
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Install docker-cli for orchestrator restart capability
RUN apk add --no-cache docker-cli

# Security Note: Running as root to access Docker socket
# This is acceptable for development but poses security risks in production.
# Production recommendations:
# 1. Use a dedicated Docker socket proxy (e.g., tecnativa/docker-socket-proxy)
# 2. Implement proper socket permission restrictions with user namespaces
# 3. Consider using Docker API with proper authentication instead of socket mounting
# 4. Use least-privilege principles with specific socket access controls

# Copy necessary files
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# Copy proto files for runtime gRPC
COPY --from=builder /app/proto ./proto
# Copy startup script
COPY ui_service/start.sh ./start.sh
RUN chmod +x ./start.sh

EXPOSE 5000

ENV PORT=5000
ENV HOSTNAME="0.0.0.0"

CMD ["./start.sh"]
