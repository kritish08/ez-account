# ============================================================
# EZ Account — Frontend Dockerfile
# React (CRACO) build → Nginx production serve
# ============================================================

# --- Stage 1: Build ---
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (layer-cached)
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

# Copy source (frontend .env is baked in at build time)
COPY . .

# REACT_APP_BACKEND_URL must be passed as a build ARG so the JS bundle
# knows the production API URL at compile time.
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

# Source maps were being emitted and then served by nginx, publishing the
# full application source. They also account for a large share of build time.
ENV GENERATE_SOURCEMAP=false

RUN npm run build

# Pre-compress everything nginx will serve, so `gzip_static` can hand over a
# maximally-compressed file instead of nginx re-compressing each asset at a
# weak level on every request.
RUN find /app/build -type f \
        \( -name '*.js' -o -name '*.css' -o -name '*.html' -o -name '*.svg' \
           -o -name '*.json' -o -name '*.txt' \) \
        -exec gzip -9 -k {} \;

# --- Stage 2: Serve with Nginx ---
FROM nginx:alpine

# Remove default nginx page
RUN rm -rf /usr/share/nginx/html/*

# Copy production build
COPY --from=builder /app/build /usr/share/nginx/html

# Nginx config for React Router (client-side routing)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
