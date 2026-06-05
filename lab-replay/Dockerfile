# Lab replay: nginx ~1.24.x, single worker, HTTP/2, defaults (blog-like)
FROM nginx:1.24

RUN apt-get update && apt-get install -y openssl procps python3 && \
    rm -rf /var/lib/apt/lists/*

RUN openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
      -keyout /etc/nginx/server.key -out /etc/nginx/server.crt \
      -days 3650 -nodes -subj "/CN=localhost"

RUN echo "ok" > /usr/share/nginx/html/index.html

COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 443/tcp
CMD ["nginx", "-g", "daemon off;"]
