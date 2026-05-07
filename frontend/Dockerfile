# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json yarn.lock ./
RUN --mount=type=cache,target=/usr/local/share/.cache/yarn yarn install --frozen-lockfile

FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NODE_ENV=production
RUN yarn build

FROM nginx:1.29-alpine AS runtime

LABEL org.opencontainers.image.title="my-family-tree-frontend" \
      org.opencontainers.image.licenses="MIT"

RUN addgroup -S app && adduser -S app -G app
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
RUN chown -R app:app /usr/share/nginx/html /var/cache/nginx /var/run /var/log/nginx \
 && touch /var/run/nginx.pid && chown app:app /var/run/nginx.pid

USER app

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:8080/ >/dev/null || exit 1
CMD ["nginx", "-g", "daemon off;"]
