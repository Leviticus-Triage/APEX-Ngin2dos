# Apache httpd mod_http2 lab — port 10080 (TLS + h2)
FROM httpd:2.4

RUN apt-get update && apt-get install -y openssl procps curl && \
    rm -rf /var/lib/apt/lists/* && \
    openssl req -x509 -newkey rsa:2048 -keyout /usr/local/apache2/conf/server.key \
      -out /usr/local/apache2/conf/server.crt -days 3650 -nodes -subj "/CN=localhost" && \
    echo "ok" > /usr/local/apache2/htdocs/index.html

COPY httpd.conf /usr/local/apache2/conf/httpd.conf

EXPOSE 10080
