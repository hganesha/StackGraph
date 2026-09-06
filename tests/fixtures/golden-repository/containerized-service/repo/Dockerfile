FROM node:20.11-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm ci --omit=dev
COPY src ./src

FROM node:20.11-alpine
WORKDIR /app
COPY --from=build /app /app
USER node
EXPOSE 8080
CMD ["node", "src/server.js"]
