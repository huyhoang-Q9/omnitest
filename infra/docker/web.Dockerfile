# Image cho frontend: build tĩnh bằng Vite, phục vụ bằng nginx và proxy /api sang API.
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /app
COPY pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile --filter @omnitest/web
COPY apps/web apps/web
RUN pnpm --filter @omnitest/web exec vite build

FROM nginx:1.27-alpine
COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
EXPOSE 8080
