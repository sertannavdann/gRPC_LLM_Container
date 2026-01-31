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

# Build Next.js
RUN npm run build

# Production image, copy all the files and run next
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Install docker-cli for orchestrator restart capability
RUN apk add --no-cache docker-cli

# Note: We run as root to access docker socket
# In production, consider using a dedicated socket proxy service

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
