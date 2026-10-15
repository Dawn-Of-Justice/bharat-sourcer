FROM node:25-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM node:25-alpine
ENV NODE_ENV=production PORT=8080
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY server.mjs ./server.mjs
USER node
CMD ["node", "server.mjs"]
