FROM envoyproxy/envoy:v1.37-latest

USER root
RUN apt-get update && apt-get install -y openssl curl procps && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /etc/envoy/certs && \
    openssl req -x509 -newkey rsa:2048 -keyout /etc/envoy/certs/server.key \
      -out /etc/envoy/certs/server.crt -days 3650 -nodes -subj "/CN=localhost"

COPY envoy.yaml /etc/envoy/envoy.yaml
EXPOSE 10000 9901
CMD ["/usr/local/bin/envoy", "-c", "/etc/envoy/envoy.yaml", "--log-level", "info"]
