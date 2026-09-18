# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json tsconfig.json tsconfig.app.json vite.config.ts index.html ./
COPY public ./public
COPY src ./src
RUN npm install --no-audit --no-fund && npm run build

FROM nginx:1.29-alpine
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.d/10-runtime-config.sh /docker-entrypoint.d/10-runtime-config.sh
COPY --from=build /app/dist /usr/share/nginx/html
RUN chmod +x /docker-entrypoint.d/10-runtime-config.sh \
    && sed -i '/^user[[:space:]]/d' /etc/nginx/nginx.conf \
    && if grep -q '^pid[[:space:]]' /etc/nginx/nginx.conf; then \
         sed -i 's#^pid[[:space:]].*#pid /tmp/nginx.pid;#' /etc/nginx/nginx.conf; \
       else \
         sed -i '1i pid /tmp/nginx.pid;' /etc/nginx/nginx.conf; \
       fi \
    && chown -R nginx:nginx /usr/share/nginx/html /etc/nginx/conf.d /var/cache/nginx
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=3s --start-period=10s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
