# ── Stage 1: build the React/Vite frontend ─────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

# Install deps first for better layer caching
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline

# Copy source and build
COPY frontend/ .
RUN npm run build

# ── Stage 2: nginx image with embedded config + static assets ───────────────
FROM nginx:1.27-alpine

# Copy the compiled SPA
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration (baked in — no bind-mount needed in production)
COPY nginx/nginx.conf /etc/nginx/nginx.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
