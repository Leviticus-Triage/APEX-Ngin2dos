# nginx-Härtung — mrx3k1.de (HTTP/2 HPACK Bomb)

Zielserver: `69.62.121.168` / `mrx3k1.de` — nginx **1.24.0** (Ubuntu), anfällig.

## Priorität

| Prio | Maßnahme | Wirkung |
|------|----------|---------|
| **1** | Upgrade nginx **≥ 1.29.8** + `http2_max_headers 100` | Fix laut upstream |
| **2** | `limit_conn` + niedrigere `http2_max_concurrent_streams` | Bremst Amplification |
| **3** | `send_timeout 15s` | Window-Stall kürzer |
| **4** | Notfall: HTTP/2 deaktivieren | Vektor weg, h2-Clients betroffen |

## Deployment (Ubuntu, nginx 1.24.0)

```bash
# 1. Config kopieren
sudo cp nginx-http2-bomb-mrx3k1.conf /etc/nginx/conf.d/
sudo cp mrx3k1.de.conf /etc/nginx/snippets/   # oder in bestehende site einfügen

# 2. In /etc/nginx/nginx.conf unter http { }:
#    include /etc/nginx/conf.d/nginx-http2-bomb-mrx3k1.conf;

# 3. In sites-available/mrx3k1.de die limit_conn/limit_req Zeilen aus mrx3k1.de.conf übernehmen

# 4. Test & reload
sudo nginx -t && sudo systemctl reload nginx
```

## Upgrade-Pfad (empfohlen)

```bash
# Ubuntu: nginx.org Mainline oder backports — Ziel >= 1.29.8
nginx -v   # nach Upgrade prüfen

# Dann nginx-1.29.8-post-upgrade.conf anwenden:
#   http2_max_headers 100;
```

## Verifikation nach Härtung

```bash
# Harmlos
curl -sI --http2 https://mrx3k1.de/

# MCP/Plugin (autorisiert)
# probe_http2 → run_http2_bomb_test profile=safe
# Erwartung: früher Abbruch / GOAWAY / weniger parallele Streams
```

## Notfall: HTTP/2 aus

In der site config `http2` von `listen` entfernen → nur TLS + HTTP/1.1.

## Referenz

Benchmark-Ergebnisse: Notion-Seite „HTTP/2 Bomb — MCP Plugin & OOM Benchmark“
