# MyAgent 前端 — Vite 构建 + Nginx 托管
#
# 构建上下文是 frontend/ 目录：
#   docker build -t myagent-frontend ./frontend

# ---------- 构建阶段 ----------
FROM node:20-alpine AS builder

WORKDIR /build

# 依赖层单独缓存（有 lock 文件用 npm ci，没有则退回 npm install）
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .
RUN npm run build

# ---------- 运行阶段 ----------
FROM nginx:alpine

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
