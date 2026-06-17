# CVE Maximization Plan — Daniel F. Hensen

**Ziel:** Chancen maximieren, dass eine **neue CVE** (nicht nur Advisory / Config-Hinweis) auf deinen Namen vergeben wird.  
**Stand:** 2026-06-17  
**Ausgangslage:** Fat-Cookie auf Apache 2.0.41 reproduziert — reicht allein **nicht** für „100 % CVE“. Vendor kann „same class / config“ sagen.

---

## Warum der aktuelle Stand abgeschmettert werden kann

| Einwand des Vendors | Unser aktuelles Finding |
|---------------------|-------------------------|
| „Gleiche Klasse wie CVE-2026-49975“ | Fat-Cookie ist Variante, kein neuer Bug-Typ |
| „Kein Bypass der Fix-Logik“ | Wir bleiben unter `LimitRequestFields` — kein Zähler-Bypass |
| „Default-Limits sind Admin-Sache“ | `H2MaxSessionStreams`, `LimitRequestFieldSize` bekannt |
| „califio hat das schon gemeldet“ | Fat-Cookie-Pfad evtl. in Disclosure-Pipeline |
| „Nur Volumen unter dem Limit“ | nginx 999 hdr — gleiches Problem |

**Fazit:** Wir brauchen mindestens **einen** Finding-Typ, der **die Patch-Logik selbst** umgeht oder **gepatchte Software** nochmal trifft.

---

## Was MITRE/Vendors als „neue CVE“ eher akzeptieren

1. **Echter Fix-Bypass** — Limit/Counter wird umgangen (nicht nur „unter Limit skalieren“).
2. **Patch unvollständig** — Fix adressiert Vektor A, Vektor B nutzt **denselben Codepfad** falsch.
3. **Regression** — Fix in Version X, Bypass in Version X+Y.
4. **Anderes Produkt, noch kein CVE** — z.B. Pingora **≥0.8.1** hardened bypass, IIS, Envoy **≥1.37.3**.
5. **Neuer CWE-Mechanismus** — z.B. Trailer nicht gezählt, CONTINUATION erst am END_HEADERS, encoded-vs-decoded ratio.

---

## Strategie in 5 Phasen (Priorität)

```
Phase 1 ──► Fix-Logik analysieren (Code, nicht nur PoC)
Phase 2 ──► Echter Bypass-Hunt (CONTINUATION, Trailer, Ratio, Table-Size)
Phase 3 ──► Post-Patch Targets (Pingora 0.8.1+, Envoy 1.37.3+, IIS)
Phase 4 ──► Evidence + Submission Package (vendor-proof)
Phase 5 ──► Multi-Vendor + CNA Fallback
```

---

## Phase 1: Fix-Logik verstehen (2–3 Tage)

**Ziel:** In Vendor-Reports **exakte Code-Zeile** nennen, die fehlt/falsch ist — nicht nur „OOM bei vielen Conn“.

### Apache mod_http2 (Commit `47d3100b25`)

| Task | Erwarteter CVE-Hebel |
|------|----------------------|
| `mod_http2` Source lesen: Cookie-Merge, `*pwas_added`, `LimitRequestFields` | Zeigen: Fix zählt Crumbs, aber **nicht decoded-bytes / merge-allocation** |
| Grep: `LimitRequestFieldSize`, pool alloc bei merge | Beweis: **Field-Count ok, Memory unbounded** = incomplete fix |
| Edge cases: halb-leere Crumbs, `;` ohne Wert, duplicate `Cookie` headers | Echter Zähler-Bypass? |
| Trailer `Cookie` nach DATA auf gleichem Stream | Werden Trailer gegen Limit gezählt? |

**Deliverable:** `docs/disclosure/APACHE_ROOT_CAUSE_ANALYSIS.md` mit Code-Zitaten + Diff zum Fix.

### nginx (`max_headers` in 1.29.8+)

| Task | Erwarteter CVE-Hebel |
|------|----------------------|
| Prüfen: Zählt `max_headers` bei **CONTINUATION** inkrementell oder nur am END_HEADERS? | Bypass = >1000 Felder in einem Block |
| Prüfen: Zählen **Trailer-Header** gegen `max_headers`? | Klassischer Bypass-Pfad |
| Prüfen: Pseudo-Headers `:method` etc. — laut PR nicht gezählt; normale Header danach | Kombi-Exploit |
| califio Fix #2: **wire/decoded ratio** — ist das in nginx implementiert? | Wenn nein: „recommended fix not implemented“ |

**Deliverable:** `docs/disclosure/NGINX_LIMIT_ENFORCEMENT_AUDIT.md`

---

## Phase 2: Echter Bypass-Hunt (1–2 Wochen, parallel)

Jeder Vektor braucht **Success-Kriterium:** Limit wird überschritten ODER Patch-Version OOM mit **weniger** Ressourcen als Pre-Patch.

### Vektor 2A — CONTINUATION / Trailer Evasion (nginx + httpd)

| Test | Methode | CVE wenn… |
|------|---------|-----------|
| CONTINUATION split | HPACK-Bomb über 50+ Frames, END_HEADERS nur am Ende | Server alloziert **>max_headers** bevor Abbruch |
| Trailer bomb | HEADERS (klein) + DATA + TRAILER mit 2000 indexed refs | Trailer nicht in `max_headers` / `LimitRequestFields` |
| Mid-stream Cookie | Cookie nur in CONTINUATION Frame 2+ | Zähler umgangen |

**Implementierung:** `benchmark/evasion_hpack.py` — echte califio HPACK-Blocks, nicht nur Literal-`0x40`-Bytes.

### Vektor 2B — Encoded vs. Decoded Ratio (califio Fix #2)

califio empfiehlt: `if (wire_bytes * 10 < decoded_bytes) reject`.

| Test | CVE wenn… |
|------|-----------|
| Messung wire/decoded pro Request auf patched nginx/httpd | Ratio >100:1 **und** Request akzeptiert |
| APEX liefert Ratio-Metrik im Harness | Vendor kann Fix #2 nicht als „done“ behaupten |

**Implementierung:** `benchmark/ratio_probe.py` + Log in jedem Run.

### Vektor 2C — SETTINGS_HEADER_TABLE_SIZE + Bomb

| Test | CVE wenn… |
|------|-----------|
| Große Table Size vor Bomb | Zusätzliche Allocation **über** Header-Count-Limit hinaus |
| Kombination mit Window-Stall | Messbar höherer RSS als ohne SETTINGS |

### Vektor 2D — Apache-spezifisch: „Crumb-Grenze“-Bypass

| Variante | Hypothese |
|----------|-----------|
| `cookie: a=1; b=2; …` mit **je 1 Byte** Wert, 95 Crumbs | Unter Limit, aber hohe Merge-Kosten? |
| **Zwei** Cookie-Header-Zeilen pro Stream | Zählt mod_http2 beide? |
| Cookie in **response** path (falls proxy) | Anderer Codepfad |

### Vektor 2E — Kombinationsketten (Exploit Chain)

```
SETTINGS large table
  → CONTINUATION-split header block (evade early count)
  → fat cookie indexed refs
  → INITIAL_WINDOW_SIZE=0 + hard_hold
```

**CVE-Narrativ:** „Chain bypasses per-request limits that vendors assumed sufficient.“

---

## Phase 3: Post-Patch / No-CVE-yet Targets

| Target | Version | Warum höhere CVE-Chance |
|--------|---------|-------------------------|
| **Pingora** | **0.8.1+** (nicht 0.8.0 Lab!) | Fix shipped Jun 2026 — wenn hardened defaults **bypassbar** = klare neue CVE |
| **Envoy** | **1.37.3 / 1.37.4** (gepatcht) | CVE-2026-47774 fixed — **Bypass auf gepatchter** Version = neue CVE |
| **Envoy** | **1.37.2** (vuln) | Repro + **dein** Reporter-Credit wenn noch nicht öffentlich mit deinem Namen |
| **IIS** | Windows Server 2025 | califio: **kein CVE**, kein Fix — höchste „neue CVE“-Chance wenn Lab möglich |
| **httpd** | 2.0.42+ (falls released) | Regression-Test |

### Pingora 0.8.1 Plan

1. Lab auf `pingora = "0.8.1"` in `Cargo.toml` pinnen, rebuild.
2. Default **und** hardened (`PINGORA_H2_MAX_HEADER_LIST_SIZE=65536`) testen.
3. Wenn OOM auf **0.8.1 hardened** → starke CVE gegen Cloudflare.
4. Vendor: security@cloudflare.com

### Envoy gepatcht-Bypass Plan

1. Lab: `envoyproxy/envoy:v1.37.3` vs `v1.37.4` A/B.
2. Vektoren: cookie size accounting edge, **decoded** limit, neue frame shapes.
3. Wenn nur Volumen unter `max_headers_count=1000` (post-fix default) → schwach.
4. Wenn **accounting bug** auf 1.37.4 → CVE.

### IIS Plan (falls Windows VM verfügbar)

- califio PoC: `iis_hpack_dos.py` — **kein Vendor-Fix** per CSA Research Note.
- **Höchste Wahrscheinlichkeit für neue CVE**, wenn reproduzierbar.
- Microsoft MSRC: https://msrc.microsoft.com/report

---

## Phase 4: Submission Package (CVE-Quote erhöhen)

Vendor lehnen ab, wenn Report wie „Blog + Zahlen“ aussieht. Paket muss wie **Professional Advisory** wirken.

### Pflicht-Checkliste pro Finding

- [ ] `httpd -v`, `nginx -v`, `envoy --version`, `mod_http2` Version Screenshot
- [ ] **A/B:** vuln vs patched vs hardened — gleiche Harness-Kommandos
- [ ] **Root cause:** 1–2 Code-Stellen (Datei:Zeile) oder klarer Protocol-Gap
- [ ] **Minimal PoC:** <20 Zeilen oder 1 Harness-Befehl
- [ ] **Impact:** RSS, OOM-Kill, `server_down`, CVSS-Vorschlag
- [ ] **Fix-Vorschlag:** konkret (nicht nur „senkt Limits“)
- [ ] **Timeline:** private report date, embargo 90d
- [ ] **Reporter:** Daniel F. Hensen, eindeutige Discovery-Claim (was **du** gefunden hast vs califio)

### Narrativ-Upgrade (Apache)

**Schwach:** „Fat cookie causes OOM at 800 conn.“  
**Stark:** „Commit 47d3100b25 adds field counting for empty crumbs but does not bound **per-stream decoded cookie bytes** or **wire/decoded ratio**; fat indexed refs remain exploitable on 2.0.41 default config — incomplete remediation of CVE-2026-49975.“

### Zwei CVE-Stories parallel einreichen

| # | Story | Wann einreichen |
|---|-------|-----------------|
| A | Apache incomplete fix + **root cause** | Sobald Phase 1 Apache fertig |
| B | Pingora 0.8.1 hardened bypass **oder** IIS | Sobald Phase 3 reproduziert |
| C | nginx trailer/CONTINUATION bypass | Nur wenn Phase 2 positiv |

**Nicht** alles in eine Mail — **getrennte** Reports = getrennte CVE-Chancen.

---

## Phase 5: Wenn Vendor ablehnt — CNA Fallback

| Schritt | Aktion |
|---------|--------|
| 1 | Vendor-Antwort dokumentieren (ablehnung + Begründung) |
| 2 | **MITRE CVE Request:** https://cveform.mitre.org/ — als Reporter mit Evidence |
| 3 | **GitHub Security Advisory** (für Pingora/Envoy Open Source) |
| 4 | **CNA über CERT** (z.B. BSI, falls DE) — bei Ablehnung durch Vendor |
| 5 | Öffentlicher Blog **nach** Embargo — erhöht Druck für CVE-Zuweisung |

**Wichtig:** MITRE vergibt CVE auch bei Vendor-Dissens, wenn Impact + Distinctness nachweisbar.

---

## Erfolgs-Kriterien (wann wir „CVE-ready“ sagen)

| Stufe | Kriterium | Geschätzte CVE-Chance |
|-------|-----------|------------------------|
| **Bronze** | OOM auf patched, unter Limits, nur Volume | 15–25 % |
| **Silber** | Incomplete fix + Root-Cause-Code + A/B + Default-Config | 40–55 % |
| **Gold** | Echter Limit-Bypass (Trailer/CONTINUATION/Ratio) auf patched | 65–80 % |
| **Platin** | Post-patch bypass (Pingora 0.8.1+ / Envoy 1.37.4+ / IIS) | 70–85 % |

**Aktueller Stand: Bronze–Silber** (Apache Fat-Cookie). **Ziel: Gold oder Platin.**

---

## Konkrete nächste 7 Tage (Execution Order)

| Tag | Fokus | Output |
|-----|-------|--------|
| 1 | Apache `mod_http2` Source-Audit + Root-Cause-Doc | `APACHE_ROOT_CAUSE_ANALYSIS.md` |
| 2 | `evasion_hpack.py` — echte HPACK CONTINUATION + Trailer Tests nginx/httpd | `evasion_results.json` |
| 3 | Pingora 0.8.1 Lab rebuild + hardened bypass campaign | Pingora CVE candidate ja/nein |
| 4 | Envoy 1.37.2 (vuln) vs 1.37.4 (patched) A/B cookie bomb | Envoy bypass ja/nein |
| 5 | Ratio-Probe in Harness + nginx `max_headers` Trailer-Test | Ratio evidence |
| 6 | Submission Package Apache (upgraded narrative) | Mail draft EN |
| 7 | IIS VM eval **oder** zweiter Vendor-Report (Pingora/Envoy) | Second CVE path |

---

## Was wir **nicht** tun (verschwendet CVE-Chance)

- Noch mehr „999 headers + 500 conn“ ohne neuen Mechanismus
- Öffentlicher LinkedIn-Post vor Vendor-Mail
- CVE-Nummer in Repo behaupten bevor zugewiesen
- Fat-Cookie als „brand new 0-day class“ verkaufen
- Pingora 0.8.0 als Discovery claimen (bekannt, fixed 0.8.1)

---

## Karriere-Narrativ (realistisch, auch bei „nur“ Advisory)

> *Discovered post-patch HTTP/2 HPACK remediation gaps across Apache/nginx; developed ratio/continuation audit methodology; coordinated multi-vendor disclosure; CVE-2026-XXXX assigned for [specific bypass].*

---

## Entscheidungspunkt für dich

**Option A — Schnell (1 Woche):** Apache-Report mit Root-Cause upgraden + einreichen → ~40 % CVE-Chance  
**Option B — Aggressiv (2–3 Wochen):** Phase 1–3 voll → Gold/Platin Finding → ~70 %+ CVE-Chance  
**Option C — IIS/Windows:** Höchste „neue CVE“-Wahrscheinlichkeit, braucht VM

**Empfehlung: Option B** — zuerst Phase 2A (Trailer/CONTINUATION mit echtem HPACK) + Phase 3 Pingora 0.8.1, **dann** Apache-Mail mit stärkerem Paket.

---

*Plan-Autor: APEX CVE Hunt Session — authorized lab research only.*
