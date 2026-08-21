FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./

RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .

RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /tmp/dist

RUN set -eux; \
  mkdir -p /usr/share/nginx/html; \
  INDEX_PATH="$(find /tmp/dist -name index.html | head -n 1)"; \
  if [ -z "$INDEX_PATH" ]; then echo "index.html introuvable dans dist"; exit 1; fi; \
  APP_DIR="$(dirname "$INDEX_PATH")"; \
  cp -r "$APP_DIR"/* /usr/share/nginx/html/; \
  rm -rf /tmp/dist

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
