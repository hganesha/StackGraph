FROM node:22-alpine AS dependencies

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH

RUN corepack enable

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/design-system/package.json packages/design-system/package.json
COPY packages/graph-ui/package.json packages/graph-ui/package.json
COPY packages/shared/package.json packages/shared/package.json

RUN pnpm install --frozen-lockfile

FROM dependencies AS builder

ARG NEXT_PUBLIC_DATA_SOURCE=live
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
ARG NEXT_PUBLIC_AUTH_REQUIRED=false

ENV NEXT_PUBLIC_DATA_SOURCE=$NEXT_PUBLIC_DATA_SOURCE \
    NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_AUTH_REQUIRED=$NEXT_PUBLIC_AUTH_REQUIRED \
    NEXT_TELEMETRY_DISABLED=1

COPY . .

RUN pnpm --filter @stackgraph/web build

FROM node:22-alpine AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN addgroup --system --gid 1001 stackgraph \
    && adduser --system --uid 1001 --ingroup stackgraph stackgraph

WORKDIR /app

COPY --from=builder --chown=stackgraph:stackgraph /app/apps/web/.next/standalone ./
COPY --from=builder --chown=stackgraph:stackgraph /app/apps/web/.next/static ./apps/web/.next/static
# Next's standalone output does not include public/, so copy it explicitly.
COPY --from=builder --chown=stackgraph:stackgraph /app/apps/web/public ./apps/web/public

USER stackgraph

EXPOSE 3000

CMD ["node", "apps/web/server.js"]
