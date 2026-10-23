FROM node:22-alpine AS web
WORKDIR /src
RUN corepack enable
COPY apps/web/package.json apps/web/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile --dangerously-allow-all-builds || pnpm install --dangerously-allow-all-builds
COPY apps/web ./
RUN pnpm build

FROM nginx:1.27-alpine
RUN apk add --no-cache openssl
COPY deploy/prod/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY deploy/prod/nginx/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
COPY --from=web /src/dist /usr/share/nginx/html
EXPOSE 80
ENTRYPOINT ["/entrypoint.sh"]
