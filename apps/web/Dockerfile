FROM node:24-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
COPY apps/web/package.json apps/web/package.json
COPY packages/chat-widget/package.json packages/chat-widget/package.json

RUN npm ci

COPY . .

WORKDIR /app/apps/web

EXPOSE 3000

CMD ["npm", "run", "dev"]
