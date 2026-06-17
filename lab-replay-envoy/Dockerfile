FROM envoyproxy/envoy:v1.37-latest

USER root
RUN apt-get update && apt-get install -y openssl curl procps && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /etc/envoy/certs && \
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
      -keyout /etc/envoy/certs/server.key -out /etc/envoy/certs/server.crt \
      -days 3650 -nodes -subj "/CN=localhost" && \
    chmod 644 /etc/envoy/certs/server.crt && \
    chmod 644 /etc/envoy/certs/server.key

COPY envoy.yaml /etc/envoy/envoy.yaml
EXPOSE 10000 9901
CMD ["/usr/local/bin/envoy", "-c", "/etc/envoy/envoy.yaml", "--log-level", "info"]
