FROM node:24-alpine AS web-build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24-alpine AS web
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=web-build --chown=node:node /app/web/.next/standalone ./
COPY --from=web-build --chown=node:node /app/web/.next/static ./.next/static
USER node
CMD ["node", "server.js"]

FROM python:3.12-slim AS api
WORKDIR /app
COPY pyproject.toml ./
COPY backend/ ./backend/
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 researcher
USER researcher
ENV PYTHONPATH=/app/backend VERIWEB_API_HOST=0.0.0.0
CMD ["python", "-m", "veriweb"]
