FROM node:18-alpine AS build-step
WORKDIR /app
ENV PATH /app/node_modules/.bin:$PATH

COPY package.json package-lock.json vite.config.js index.html ./
COPY ./src ./src
COPY ./public ./public

RUN npm ci
RUN npm run build

# Build step #2: build an nginx container
FROM nginx:stable-alpine
COPY --from=build-step /app/dist /usr/share/nginx/html
#COPY ./nginx.conf /etc/nginx/conf.d/default.conf

##EXPOSE 8080
##CMD ["nginx", "-g", "daemon off;"]

