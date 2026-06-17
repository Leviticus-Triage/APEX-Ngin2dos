# Patched nginx lab — latest (>= 1.29.8, http2_max_headers default 1000)
FROM nginx:latest

RUN apt-get update && apt-get install -y openssl procps curl && \
    rm -rf /var/lib/apt/lists/*

RUN openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
      -keyout /etc/nginx/server.key -out /etc/nginx/server.crt \
      -days 3650 -nodes -subj "/CN=localhost"

RUN echo "ok" > /usr/share/nginx/html/index.html

COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 443/tcp
CMD ["nginx", "-g", "daemon off;"]
