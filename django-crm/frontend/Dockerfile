# Dos destinos en un mismo archivo: 'dev' levanta el servidor de Vite con
# recarga en caliente, 'prod' sirve el build compilado con adapter-node.
# Cada compose elige el suyo con 'target:'. Sin target se construye el ultimo,
# que es prod a proposito: el descuido debe caer del lado seguro.

FROM node:24-slim AS base

# Enable pnpm via corepack. Pin the version so image builds are reproducible.
RUN corepack enable && corepack prepare pnpm@11.17.0 --activate

WORKDIR /app

# Install dependencies (layer cached).
# pnpm-workspace.yaml carries the install settings (onlyBuiltDependencies,
# allowBuilds) that pnpm 10+ no longer reads from package.json. Without it
# @sentry/cli's postinstall is silently skipped and its binary never lands.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
RUN pnpm install --frozen-lockfile


# --- desarrollo -------------------------------------------------------------
# El codigo entra por bind mount desde el compose, no se copia: la recarga en
# caliente necesita ver los archivos del disco.
FROM base AS dev

EXPOSE 5173

CMD ["pnpm", "dev", "--host", "0.0.0.0"]


# --- compilacion ------------------------------------------------------------
FROM base AS build

COPY . .
RUN pnpm build


# --- produccion -------------------------------------------------------------
# svelte.config.js usa @sveltejs/adapter-node, que deja en build/ un servidor
# de Node autonomo. Escucha en PORT (3000 por defecto); Dokploy enruta su
# dominio a ese puerto por la red interna, sin publicarlo al host.
FROM node:24-slim AS prod

WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000

COPY --from=build /app/build ./build
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./

EXPOSE 3000

CMD ["node", "build"]
