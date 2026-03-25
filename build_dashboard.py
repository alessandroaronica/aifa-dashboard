#!/usr/bin/env python3
"""
AIFA Dashboard Builder
Scarica i CSV AIFA, li processa e genera una dashboard HTML standalone.
Eseguire con: python3 build_dashboard.py
"""

import urllib.request
import csv
import json
import io
import sys
import os
from collections import defaultdict

URLS = {
    2024: "https://www.aifa.gov.it/documents/20142/847578/dati2024_04.12.2025.csv",
    2023: "https://www.aifa.gov.it/documents/20142/847578/dati2023_15.01.2025.csv",
    2022: "https://www.aifa.gov.it/documents/20142/847578/dati2022_07.02.2024.csv",
    2021: "https://www.aifa.gov.it/documents/20142/847578/dati2021_24.10.2022.csv",
    2020: "https://www.aifa.gov.it/documents/20142/847578/dati2020_22.10.2021.csv",
}

def download(year, url):
    print(f"  [{year}] Scaricamento...", end=" ", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", errors="replace")
        print(f"OK ({len(raw)//1024} KB)")
        return raw
    except Exception as e:
        print(f"ERRORE: {e}")
        return None

def parse(raw):
    reader = csv.DictReader(io.StringIO(raw), delimiter="|")
    rows = []
    for row in reader:
        rows.append({
            "anno": row.get("anno",""),
            "mese": row.get("mese",""),
            "regione": row.get("regione","").strip(),
            "classe": row.get("classe","").strip(),
            "atc1": row.get("atc1","").strip(),
            "desc_atc1": row.get("descrizione_atc1","").strip(),
            "atc2": row.get("atc2","").strip(),
            "desc_atc2": row.get("descrizione_atc2","").strip(),
            "atc3": row.get("atc3","").strip(),
            "desc_atc3": row.get("descrizione_atc3","").strip(),
            "atc4": row.get("atc4","").strip(),
            "desc_atc4": row.get("descrizione_atc4","").strip(),
            "n_traccia": int(float(row.get("numero_confezioni_traccia","0") or 0)),
            "spesa_traccia": float(row.get("spesa_flusso_tracciabilita","0") or 0),
            "n_conv": int(float(row.get("numero_confezioni_convenzionata","0") or 0)),
            "spesa_conv": float(row.get("spesa_convenzionata","0") or 0),
        })
    return rows

def aggregate(rows):
    """Aggrega i dati per le varie dimensioni necessarie alla dashboard."""

    def total(rs):
        return sum(r["spesa_traccia"] + r["spesa_conv"] for r in rs)
    def conv(rs):
        return sum(r["spesa_conv"] for r in rs)
    def traccia(rs):
        return sum(r["spesa_traccia"] for r in rs)
    def confezioni(rs):
        return sum(r["n_traccia"] + r["n_conv"] for r in rs)

    # KPI
    tot = total(rows)
    kpi = {
        "totale": tot,
        "convenzionata": conv(rows),
        "tracciabilita": traccia(rows),
        "confezioni": confezioni(rows),
    }

    # Per ATC1
    by_atc1 = defaultdict(list)
    for r in rows:
        by_atc1[r["desc_atc1"]].append(r)
    atc1 = sorted(
        [{"label": k, "totale": total(v), "conv": conv(v), "traccia": traccia(v)}
         for k, v in by_atc1.items() if k],
        key=lambda x: -x["totale"]
    )

    # Per ATC2 - manteniamo TUTTO per i movers, slice solo per display
    by_atc2 = defaultdict(list)
    for r in rows:
        # usiamo codice ATC2 come chiave stabile + descrizione per label
        key = r["atc2"] if r["atc2"] else r["desc_atc2"]
        by_atc2[key].append(r)
    atc2_all = sorted(
        [{"code": k, "label": v[0]["desc_atc2"] or k, "totale": total(v), "conv": conv(v), "traccia": traccia(v)}
         for k, v in by_atc2.items() if k],
        key=lambda x: -x["totale"]
    )
    atc2 = atc2_all[:20]  # solo top 20 per display

    # Per ATC3
    by_atc3 = defaultdict(list)
    for r in rows:
        by_atc3[r["desc_atc3"]].append(r)
    atc3 = sorted(
        [{"label": k, "totale": total(v), "conv": conv(v), "traccia": traccia(v)}
         for k, v in by_atc3.items() if k],
        key=lambda x: -x["totale"]
    )[:30]

    # Per ATC4 — completo per movers/trend, top50 per display
    by_atc4 = defaultdict(list)
    for r in rows:
        key = r["atc4"] if r["atc4"] else r["desc_atc4"]
        by_atc4[key].append(r)
    atc4_all = sorted(
        [{"code": k, "label": v[0]["desc_atc4"] or k,
          "atc1": v[0]["desc_atc1"], "atc2": v[0]["desc_atc2"],
          "classe": v[0]["classe"],
          "totale": total(v), "conv": conv(v), "traccia": traccia(v)}
         for k, v in by_atc4.items() if k],
        key=lambda x: -x["totale"]
    )
    atc4 = atc4_all[:50]

    # Per ATC4 per regione (top1 per regione)
    by_reg_atc4 = defaultdict(lambda: defaultdict(list))
    for r in rows:
        key4 = r["atc4"] if r["atc4"] else r["desc_atc4"]
        if r["regione"] and key4:
            by_reg_atc4[r["regione"]][key4].append(r)
    top_atc4_per_reg = {}
    for reg, by4 in by_reg_atc4.items():
        ranked = sorted(
            [{"code": k, "label": v[0]["desc_atc4"] or k, "totale": total(v)}
             for k, v in by4.items()],
            key=lambda x: -x["totale"]
        )
        if ranked:
            top_atc4_per_reg[reg] = ranked[0]

    # Per ATC4 per classe (top2 per classe)
    by_classe_atc4 = defaultdict(lambda: defaultdict(list))
    for r in rows:
        key4 = r["atc4"] if r["atc4"] else r["desc_atc4"]
        if r["classe"] and key4:
            by_classe_atc4[r["classe"]][key4].append(r)
    top_atc4_per_classe = {}
    for cl, by4 in by_classe_atc4.items():
        ranked = sorted(
            [{"code": k, "label": v[0]["desc_atc4"] or k, "totale": total(v)}
             for k, v in by4.items()],
            key=lambda x: -x["totale"]
        )
        top_atc4_per_classe[cl] = ranked[:2]

    # Per classe
    by_classe = defaultdict(list)
    for r in rows:
        by_classe[r["classe"]].append(r)
    classi = sorted(
        [{"label": k, "totale": total(v), "conv": conv(v), "traccia": traccia(v)}
         for k, v in by_classe.items() if k],
        key=lambda x: -x["totale"]
    )

    # Per regione
    by_reg = defaultdict(list)
    for r in rows:
        by_reg[r["regione"]].append(r)
    regioni = sorted(
        [{"label": k, "totale": total(v), "conv": conv(v), "traccia": traccia(v)}
         for k, v in by_reg.items() if k],
        key=lambda x: -x["totale"]
    )

    # Per mese
    by_mese = defaultdict(list)
    for r in rows:
        by_mese[r["mese"]].append(r)
    mesi = [{"mese": k, "totale": total(v)} for k, v in sorted(by_mese.items())]

    return {
        "kpi": kpi,
        "atc1": atc1,
        "atc2": atc2,
        "atc2_all": atc2_all,
        "atc3": atc3,
        "atc4": atc4,
        "atc4_all": atc4_all,
        "top_atc4_per_reg": top_atc4_per_reg,
        "top_atc4_per_classe": top_atc4_per_classe,
        "classi": classi,
        "regioni": regioni,
        "mesi": mesi,
    }

def compute_movers(all_agg):
    """Calcola top/bottom movers ATC2 e regioni tra primo e ultimo anno."""
    years = sorted(all_agg.keys())
    if len(years) < 2:
        return [], []
    yr1, yr2 = years[0], years[-1]

    # Usa codice ATC2 come chiave stabile (non la descrizione che può variare)
    def idx_by_code(items):
        return {x["code"]: x for x in items}

    a2_1 = idx_by_code(all_agg[yr1]["atc2_all"])
    a2_2 = idx_by_code(all_agg[yr2]["atc2_all"])
    keys = set(a2_1) & set(a2_2)
    atc2_changes = []
    for k in keys:
        v1 = a2_1[k]["totale"]
        v2 = a2_2[k]["totale"]
        label = a2_2[k]["label"] or a2_1[k]["label"] or k
        # soglia minima: almeno €500k nel 2020 per evitare rumori
        if v1 > 500000:
            pct = (v2 - v1) / v1 * 100
            atc2_changes.append({
                "label": label,
                "code": k,
                "v2020": round(v1, 0),
                "v2024": round(v2, 0),
                "delta_pct": round(pct, 2),
                "delta_abs": round(v2 - v1, 0)
            })
    atc2_changes.sort(key=lambda x: -x["delta_pct"])

    r1 = {x["label"]: x["totale"] for x in all_agg[yr1]["regioni"]}
    r2 = {x["label"]: x["totale"] for x in all_agg[yr2]["regioni"]}
    rkeys = set(r1) & set(r2)
    reg_changes = []
    for k in rkeys:
        v1, v2 = r1[k], r2[k]
        if v1 > 0:
            pct = (v2 - v1) / v1 * 100
            reg_changes.append({"label": k, "v2020": v1, "v2024": v2, "delta_pct": round(pct, 2), "delta_abs": round(v2 - v1, 0)})
    reg_changes.sort(key=lambda x: -x["delta_pct"])

    print(f"  ATC-2 con match: {len(keys)} | con soglia 500k: {len(atc2_changes)}")
    for x in atc2_changes[:5]:
        print(f"  TOP: {x['label'][:40]} {x['delta_pct']:+.0f}%")

    return atc2_changes, reg_changes

def compute_yoy(all_agg):
    """Variazione YoY per regione e ATC1."""
    years = sorted(all_agg.keys())
    result = {}
    for i in range(1, len(years)):
        y0, y1 = years[i-1], years[i]
        reg0 = {x["label"]: x["totale"] for x in all_agg[y0]["regioni"]}
        reg1 = {x["label"]: x["totale"] for x in all_agg[y1]["regioni"]}
        yoy = {}
        for k in set(reg0) & set(reg1):
            if reg0[k] > 0:
                yoy[k] = round((reg1[k] - reg0[k]) / reg0[k] * 100, 2)
        result[y1] = yoy
    return result

def compute_atc4_movers(all_agg):
    """
    Calcola per ATC4:
    - top5 crescita % 2020->2024 (tutti)
    - top5 crescita % 2020->2024 solo se spesa 2024 nel top quartile (Q4)
    - top5 decrescita in valore assoluto con trend annuo
    """
    years = sorted(all_agg.keys())
    if len(years) < 2:
        return [], [], []
    yr1, yr2 = years[0], years[-1]

    def idx(items):
        return {x["code"]: x for x in items}

    a4_1 = idx(all_agg[yr1]["atc4_all"])
    a4_2 = idx(all_agg[yr2]["atc4_all"])
    keys = set(a4_1) & set(a4_2)

    # Pre-calcola indice per tutti gli anni
    atc4_by_year = {}
    for y in years:
        atc4_by_year[y] = idx(all_agg[y]["atc4_all"])

    changes = []
    for k in keys:
        v1 = a4_1[k]["totale"]
        v2 = a4_2[k]["totale"]
        if v1 > 200000:
            pct_change = (v2 - v1) / v1 * 100
            label = a4_2[k]["label"] or a4_1[k]["label"] or k
            trend = [{"year": y, "v": round(atc4_by_year[y].get(k, {}).get("totale", 0), 0)} for y in years]
            changes.append({
                "code": k,
                "label": label,
                "v2020": round(v1, 0),
                "v2024": round(v2, 0),
                "delta_pct": round(pct_change, 2),
                "delta_abs": round(v2 - v1, 0),
                "trend": trend,
            })

    # Soglia Q4: 75° percentile della spesa 2024
    all_v2024 = sorted([x["totale"] for x in all_agg[yr2]["atc4_all"]])
    q3_threshold = all_v2024[int(len(all_v2024) * 0.75)] if all_v2024 else 0

    top_pct_all = sorted(changes, key=lambda x: -x["delta_pct"])[:5]
    top_pct_q4 = sorted(
        [c for c in changes if c["v2024"] >= q3_threshold],
        key=lambda x: -x["delta_pct"]
    )[:5]
    top_abs_decline = sorted(
        [c for c in changes if c["delta_abs"] < 0],
        key=lambda x: x["delta_abs"]
    )[:5]

    print(f"  ATC-4 analizzate: {len(changes)} | Q4 soglia: >{q3_threshold/1e6:.1f}M")
    for x in top_pct_all[:3]:
        print(f"  CRESCITA: {x['label'][:45]} {x['delta_pct']:+.0f}%")
    for x in top_abs_decline[:3]:
        print(f"  CALO ABS: {x['label'][:40]} {x['delta_abs']/1e6:.0f}M")

    return top_pct_all, top_pct_q4, top_abs_decline

print("\n╔══════════════════════════════════════╗")
print("║   AIFA Dashboard Builder v1.0        ║")
print("╚══════════════════════════════════════╝\n")
print("► Scaricamento dati AIFA...\n")

all_raw = {}
for year, url in sorted(URLS.items()):
    raw = download(year, url)
    if raw:
        all_raw[year] = raw

if not all_raw:
    print("\n✗ Nessun file scaricato. Controlla la connessione internet.")
    sys.exit(1)

print(f"\n► Parsing e aggregazione ({len(all_raw)} anni)...\n")
all_agg = {}
for year, raw in sorted(all_raw.items()):
    print(f"  [{year}] elaborazione...", end=" ", flush=True)
    rows = parse(raw)
    all_agg[year] = aggregate(rows)
    t = all_agg[year]["kpi"]["totale"]
    print(f"OK — {len(rows):,} righe — totale €{t/1e9:.2f}mld")

print("\n► Calcolo variazioni e movers...")
atc2_changes, reg_changes = compute_movers(all_agg)
yoy = compute_yoy(all_agg)

print("\n► Calcolo movers ATC-4...")
atc4_top_pct, atc4_top_pct_q4, atc4_top_decline = compute_atc4_movers(all_agg)

# Rimuovi atc2_all e atc4_all dal payload finale (servono solo per i calcoli)
all_agg_clean = {}
for y, d in all_agg.items():
    all_agg_clean[y] = {k: v for k, v in d.items() if k not in ("atc2_all", "atc4_all")}

# Build JS payload
payload = {
    "years": sorted(all_agg.keys()),
    "data": {str(y): v for y, v in all_agg_clean.items()},
    "atc2_changes": atc2_changes,
    "reg_changes": reg_changes,
    "yoy": {str(k): v for k, v in yoy.items()},
    "atc4_top_pct": atc4_top_pct,
    "atc4_top_pct_q4": atc4_top_pct_q4,
    "atc4_top_decline": atc4_top_decline,
    "build_date": build_date,
}

print("► Generazione HTML dashboard...\n")

HTML = r"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIFA · Osservatorio Spesa Farmaceutica 2020–2024</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;1,9..144,300&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root {
  --bg:#0a0d14; --surface:#111520; --surface2:#171d2e;
  --border:#1e2540; --accent:#00d4ff; --accent2:#ff6b35;
  --accent3:#7fff6b; --accent4:#c084fc;
  --text:#e8ecf5; --text-dim:#6b7a99; --text-muted:#3a4560;
  --red:#ff4d6d; --green:#00e5a0; --yellow:#ffd166;
  --serif:'Fraunces',serif; --sans:'Syne',sans-serif; --mono:'DM Mono',monospace;
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:var(--sans);min-height:100vh;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(var(--border) 1px,transparent 1px),linear-gradient(90deg,var(--border) 1px,transparent 1px);background-size:60px 60px;opacity:.2;pointer-events:none;z-index:0}

header{position:relative;z-index:10;padding:1.5rem 3rem;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;backdrop-filter:blur(20px);background:rgba(10,13,20,.9)}
.logo h1{font-family:var(--serif);font-size:1.7rem;font-weight:300;font-style:italic;letter-spacing:-.02em}
.logo h1 span{color:var(--accent);font-style:normal;font-weight:700}
.logo .sub{font-family:var(--mono);font-size:.6rem;color:var(--text-dim);letter-spacing:.15em;text-transform:uppercase;margin-top:2px}
.hright{display:flex;align-items:center;gap:1rem}
.badge{font-family:var(--mono);font-size:.6rem;letter-spacing:.1em;text-transform:uppercase;padding:4px 10px;border:1px solid var(--accent);color:var(--accent);border-radius:20px}

.year-tabs{display:flex;gap:4px;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:4px}
.yt{font-family:var(--mono);font-size:.7rem;padding:5px 12px;border-radius:5px;cursor:pointer;color:var(--text-dim);border:none;background:transparent;transition:all .2s}
.yt.active{background:var(--accent);color:var(--bg);font-weight:500}
.yt:hover:not(.active){color:var(--text);background:var(--surface2)}

main{position:relative;z-index:5;padding:2rem 3rem;max-width:1600px;margin:0 auto}

/* KPI */
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:2rem}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.5rem;position:relative;overflow:hidden;transition:border-color .2s}
.kpi:hover{border-color:var(--accent)}
.kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.kpi.blue::before{background:var(--accent)}.kpi.orange::before{background:var(--accent2)}.kpi.green::before{background:var(--green)}.kpi.purple::before{background:var(--accent4)}
.kpi-lbl{font-family:var(--mono);font-size:.6rem;letter-spacing:.15em;text-transform:uppercase;color:var(--text-dim);margin-bottom:.75rem}
.kpi-val{font-family:var(--serif);font-size:2.2rem;font-weight:400;line-height:1;margin-bottom:.4rem}
.kpi-sub{font-family:var(--mono);font-size:.62rem;color:var(--text-dim)}
.kpi-delta{position:absolute;top:1.5rem;right:1.5rem;font-family:var(--mono);font-size:.7rem;font-weight:500}
.up{color:var(--green)}.down{color:var(--red)}

/* PANELS */
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-bottom:2rem}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1.5rem;margin-bottom:2rem}
.grid12{display:grid;grid-template-columns:1fr 2fr;gap:1.5rem;margin-bottom:2rem}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.5rem}
.panel-full{margin-bottom:2rem}
.ptitle{font-family:var(--mono);font-size:.6rem;letter-spacing:.15em;text-transform:uppercase;color:var(--text-dim);margin-bottom:1.25rem;padding-bottom:.75rem;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px}
.dot{width:6px;height:6px;border-radius:50%;background:var(--accent);flex-shrink:0}
.ch{position:relative}

/* SECTION HEADER */
.sh{display:flex;align-items:baseline;gap:1rem;margin-bottom:1.5rem;margin-top:.5rem}
.sh h2{font-family:var(--serif);font-size:1.5rem;font-weight:300;font-style:italic}
.sh .sl{font-family:var(--mono);font-size:.6rem;letter-spacing:.15em;text-transform:uppercase;color:var(--text-dim)}

/* RANK LIST */
.rl{display:flex;flex-direction:column;gap:.45rem}
.ri{display:flex;align-items:center;gap:.75rem;padding:.6rem .75rem;border-radius:8px;background:var(--surface2);border:1px solid var(--border);transition:border-color .15s}
.ri:hover{border-color:var(--accent)}
.rn{font-family:var(--mono);font-size:.62rem;color:var(--text-muted);width:20px;flex-shrink:0}
.rbw{flex:1;min-width:0}
.rlbl{font-size:.7rem;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:3px}
.rbb{height:3px;background:var(--border);border-radius:2px;overflow:hidden}
.rbf{height:100%;border-radius:2px;transition:width .8s cubic-bezier(.4,0,.2,1)}
.rv{font-family:var(--mono);font-size:.62rem;color:var(--text-dim);text-align:right;flex-shrink:0;min-width:90px}

/* REGION CARDS */
.rgrid{display:grid;grid-template-columns:repeat(5,1fr);gap:.5rem}
.rc{padding:.75rem;background:var(--surface2);border:1px solid var(--border);border-radius:8px;cursor:default;transition:all .15s}
.rc:hover{border-color:var(--accent);transform:translateY(-1px)}
.rcn{font-size:.68rem;font-weight:600;margin-bottom:3px}
.rcs{font-family:var(--mono);font-size:.6rem;color:var(--text-dim)}
.rcd{font-family:var(--mono);font-size:.6rem;font-weight:500;margin-top:3px}
.rch{height:3px;border-radius:2px;margin-top:5px}

/* MOVER CARDS */
.mover-section{display:grid;grid-template-columns:1fr 1fr;gap:.5rem;margin-top:.5rem}
.mc{padding:.65rem 1rem;border-radius:8px;display:flex;align-items:center;justify-content:space-between;border:1px solid var(--border);gap:.5rem}
.mc.up{background:rgba(0,229,160,.06);border-color:rgba(0,229,160,.2)}
.mc.down{background:rgba(255,77,109,.06);border-color:rgba(255,77,109,.2)}
.mn{font-size:.7rem;font-weight:500;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.msub{font-family:var(--mono);font-size:.58rem;color:var(--text-dim);margin-top:2px}
.md{font-family:var(--mono);font-size:.95rem;font-weight:600;flex-shrink:0}
.mc.up .md{color:var(--green)}.mc.down .md{color:var(--red)}

/* AI */
.ai-panel{background:linear-gradient(135deg,rgba(0,212,255,.04),rgba(192,132,252,.04));border:1px solid rgba(0,212,255,.2);border-radius:12px;padding:1.5rem;margin-bottom:2rem}
.ai-hdr{display:flex;align-items:center;gap:10px;margin-bottom:1rem}
.ai-badge{font-family:var(--mono);font-size:.55rem;letter-spacing:.15em;text-transform:uppercase;padding:3px 8px;background:rgba(0,212,255,.12);color:var(--accent);border-radius:20px;border:1px solid rgba(0,212,255,.25)}
.ai-title{font-family:var(--serif);font-size:1rem;font-style:italic;color:var(--text-dim)}
#ai-out{font-size:.82rem;line-height:1.75;color:var(--text)}
#ai-out p{margin-bottom:.5rem}
#ai-btn{font-family:var(--mono);font-size:.65rem;letter-spacing:.1em;text-transform:uppercase;padding:7px 14px;background:rgba(0,212,255,.1);border:1px solid rgba(0,212,255,.3);color:var(--accent);border-radius:6px;cursor:pointer;transition:all .2s;margin-left:auto}
#ai-btn:hover{background:rgba(0,212,255,.2)}
#ai-btn:disabled{opacity:.5;cursor:default}

/* MONTHLY */
.monthly-info{font-family:var(--mono);font-size:.65rem;color:var(--text-dim);text-align:center;margin-top:.5rem}

footer{text-align:center;padding:2rem 0;font-family:var(--mono);font-size:.58rem;color:var(--text-muted);border-top:1px solid var(--border);margin-top:1rem}

@media(max-width:1100px){
  .kpi-grid{grid-template-columns:repeat(2,1fr)}
  .grid2,.grid3,.grid12{grid-template-columns:1fr}
  .rgrid{grid-template-columns:repeat(3,1fr)}
  header,main{padding:1.25rem 1.5rem}
}
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:var(--surface)}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
.fade{animation:fi .4s ease forwards;opacity:0}
@keyframes fi{to{opacity:1}}
</style>
</head>
<body>

<header>
  <div class="logo">
    <h1><span>AIFA</span> · Osservatorio Farmaceutico</h1>
    <div class="sub">Spesa farmaceutica nazionale SSN · 2020–2024 · Open Data AIFA</div>
  </div>
  <div class="hright">
    <span class="badge">Dati Embedded</span>
    <div class="year-tabs" id="ytabs">
      <button class="yt" data-y="2020">2020</button>
      <button class="yt" data-y="2021">2021</button>
      <button class="yt" data-y="2022">2022</button>
      <button class="yt" data-y="2023">2023</button>
      <button class="yt active" data-y="2024">2024</button>
    </div>
  </div>
</header>

<main>

<!-- AI -->
<div class="ai-panel">
  <div class="ai-hdr">
    <span class="ai-badge">AI · Claude</span>
    <span class="ai-title">Analisi intelligente della spesa farmaceutica</span>
    <button id="ai-btn">Genera analisi →</button>
  </div>
  <div id="ai-out" style="color:var(--text-dim);font-family:var(--mono);font-size:.68rem">
    Clicca "Genera analisi" per ricevere un'interpretazione automatica dei trend più rilevanti (richiede connessione internet).
  </div>
</div>

<!-- KPI -->
<div class="kpi-grid">
  <div class="kpi blue fade"><div class="kpi-lbl">Spesa totale SSN</div><div class="kpi-val" id="k-tot">—</div><div class="kpi-sub" id="k-tot-s"></div><div class="kpi-delta" id="k-tot-d"></div></div>
  <div class="kpi orange fade" style="animation-delay:.1s"><div class="kpi-lbl">Farmaceutica Convenzionata</div><div class="kpi-val" id="k-conv">—</div><div class="kpi-sub" id="k-conv-s"></div><div class="kpi-delta" id="k-conv-d"></div></div>
  <div class="kpi green fade" style="animation-delay:.2s"><div class="kpi-lbl">Flusso Tracciabilità</div><div class="kpi-val" id="k-trac">—</div><div class="kpi-sub" id="k-trac-s"></div><div class="kpi-delta" id="k-trac-d"></div></div>
  <div class="kpi purple fade" style="animation-delay:.3s"><div class="kpi-lbl">Confezioni dispensate</div><div class="kpi-val" id="k-conf">—</div><div class="kpi-sub" id="k-conf-s"></div></div>
</div>

<!-- ATC + CLASSI -->
<div class="sh"><h2>Ripartizione della Spesa</h2><span class="sl">Classificazione ATC · classi di rimborso</span></div>
<div class="grid2">
  <div class="panel"><div class="ptitle"><div class="dot"></div>Top categorie terapeutiche ATC-1</div><div class="ch" style="height:280px"><canvas id="c-atc1"></canvas></div></div>
  <div class="panel"><div class="ptitle"><div class="dot"></div>Distribuzione per classe di rimborso</div><div class="ch" style="height:280px"><canvas id="c-classi"></canvas></div></div>
</div>

<div class="grid2">
  <div class="panel"><div class="ptitle"><div class="dot"></div>Top 15 sottogruppi ATC-2 per spesa</div><div id="r-atc2" class="rl"></div></div>
  <div class="panel"><div class="ptitle"><div class="dot"></div>Convenzionata vs Tracciabilità per ATC-1</div><div class="ch" style="height:340px"><canvas id="c-flussi"></canvas></div></div>
</div>

<!-- DETAIL CLASSI -->
<div class="panel panel-full">
  <div class="ptitle"><div class="dot"></div>Dettaglio classi di rimborso · spesa e canale di erogazione</div>
  <div id="r-classi" class="rl"></div>
</div>

<!-- TREND -->
<div class="sh"><h2>Evoluzione Temporale</h2><span class="sl">Confronto 2020–2024</span></div>
<div class="panel panel-full"><div class="ptitle"><div class="dot"></div>Spesa totale SSN per anno</div><div class="ch" style="height:200px"><canvas id="c-trend"></canvas></div></div>

<div class="grid2">
  <div class="panel"><div class="ptitle"><div class="dot"></div>Evoluzione per categoria ATC-1</div><div class="ch" style="height:280px"><canvas id="c-atc1-trend"></canvas></div></div>
  <div class="panel"><div class="ptitle"><div class="dot"></div>Evoluzione classi di rimborso</div><div class="ch" style="height:280px"><canvas id="c-classi-trend"></canvas></div></div>
</div>

<!-- MOVERS ATC2 -->
<div class="sh"><h2>Categorie in Movimento</h2><span class="sl">Variazione % 2020→2024 · ATC-2</span></div>
<div class="grid2">
  <div class="panel"><div class="ptitle"><div class="dot"></div>🚀 Top 5 categorie con maggiore crescita</div><div class="mover-section" id="m-up"></div></div>
  <div class="panel"><div class="ptitle"><div class="dot"></div>📉 Top 5 categorie con maggiore riduzione</div><div class="mover-section" id="m-down"></div></div>
</div>

<!-- ATC4 NAZIONALE -->
<div class="sh"><h2>Focus ATC-4</h2><span class="sl">Principi attivi · ultimo anno disponibile</span></div>
<div class="grid2">
  <div class="panel"><div class="ptitle"><div class="dot"></div>🏆 Top 5 ATC-4 per spesa nazionale 2024</div><div id="r-atc4-top" class="rl"></div></div>
  <div class="panel"><div class="ptitle"><div class="dot"></div>📋 Top 2 ATC-4 per ogni classe di rimborso</div><div id="r-atc4-classe" style="display:flex;flex-direction:column;gap:.75rem"></div></div>
</div>

<!-- ATC4 TREND CRESCITA -->
<div class="grid2">
  <div class="panel">
    <div class="ptitle"><div class="dot"></div>📈 Top 5 ATC-4 per crescita % 2020→2024 (tutti)</div>
    <div class="ch" style="height:260px"><canvas id="c-atc4-pct"></canvas></div>
  </div>
  <div class="panel">
    <div class="ptitle"><div class="dot"></div>💊 Top 5 ATC-4 per crescita % · solo farmaci ad alto volume (Q4 2024)</div>
    <div class="ch" style="height:260px"><canvas id="c-atc4-pct-q4"></canvas></div>
  </div>
</div>

<!-- ATC4 DECRESCITE -->
<div class="panel panel-full">
  <div class="ptitle"><div class="dot"></div>📉 Top 5 ATC-4 per maggiore calo in valore assoluto 2020→2024</div>
  <div class="ch" style="height:260px"><canvas id="c-atc4-decline"></canvas></div>
</div>

<!-- REGIONI -->
<div class="sh"><h2>Analisi Regionale</h2><span class="sl">Tutte le regioni italiane · anno selezionato</span></div>

<!-- TOP ATC4 PER REGIONE -->
<div class="panel panel-full">
  <div class="ptitle"><div class="dot"></div>🗺️ ATC-4 più prescritta per regione · 2024</div>
  <div class="rgrid" id="reg-atc4-cards"></div>
</div>

<div class="grid2">
  <div class="panel"><div class="ptitle"><div class="dot"></div>Spesa per regione</div><div class="ch" style="height:380px"><canvas id="c-reg"></canvas></div></div>
  <div class="panel"><div class="ptitle"><div class="dot"></div>Variazione % vs anno precedente</div><div class="ch" style="height:380px"><canvas id="c-reg-yoy"></canvas></div></div>
</div>

<div class="panel panel-full">
  <div class="ptitle"><div class="dot"></div>Mappa regionale · spesa e variazione vs media nazionale</div>
  <div class="rgrid" id="reg-cards"></div>
</div>

<div class="grid2">
  <div class="panel"><div class="ptitle"><div class="dot"></div>Regioni con maggiore crescita 2020→2024</div><div id="r-reg-up" class="rl"></div></div>
  <div class="panel"><div class="ptitle"><div class="dot"></div>Regioni con maggiore riduzione 2020→2024</div><div id="r-reg-down" class="rl"></div></div>
</div>

<!-- MENSILE -->
<div class="sh"><h2>Andamento Mensile</h2><span class="sl">Spesa per mese · anno selezionato</span></div>
<div class="panel panel-full"><div class="ptitle"><div class="dot"></div>Spesa mensile SSN</div><div class="ch" style="height:200px"><canvas id="c-mesi"></canvas></div><div class="monthly-info" id="monthly-note"></div></div>

<footer>Fonte: AIFA Open Data · Aggiornato: ' + (D.build_date||'—') + ' · Dati elaborati e incorporati in locale · Nessuna connessione necessaria per visualizzare</footer>
</main>

<script>
// ── DATA ──
const D = __DATA__;

const COLORS = ['#00d4ff','#ff6b35','#7fff6b','#c084fc','#ffd166','#ff4d6d','#00e5a0','#f472b6','#38bdf8','#a3e635','#fb923c','#818cf8','#34d399','#f87171','#fbbf24'];
const MESI_LABEL = ['','Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'];

let AY = 2024;
let charts = {};

const fmt = v => {
  if(v>=1e9) return `€${(v/1e9).toFixed(2)}mld`;
  if(v>=1e6) return `€${(v/1e6).toFixed(0)}M`;
  if(v>=1e3) return `€${(v/1e3).toFixed(0)}K`;
  return `€${v.toFixed(0)}`;
};
const fmtM = v => `€${(v/1e6).toFixed(1)}M`;
const fmtN = v => v>=1e6 ? `${(v/1e6).toFixed(1)}M` : v>=1e3 ? `${(v/1e3).toFixed(0)}K` : v;
const pct = (a,b) => b ? ((a-b)/b*100) : 0;
const sign = v => (v>=0?'+':'')+v.toFixed(1)+'%';

function dc(id){if(charts[id]){charts[id].destroy();delete charts[id];}}

const CO = {
  responsive:true, maintainAspectRatio:false,
  plugins:{legend:{display:false}, tooltip:{backgroundColor:'#111520',borderColor:'#1e2540',borderWidth:1,titleColor:'#6b7a99',bodyColor:'#e8ecf5'}},
  scales:{x:{grid:{color:'#1e2540'},ticks:{color:'#6b7a99',font:{family:'DM Mono',size:9}}},
          y:{grid:{color:'#1e2540'},ticks:{color:'#6b7a99',font:{family:'DM Mono',size:9}}}}
};

function barH(id, labels, data, colors, callbackFn){
  dc(id);
  const ctx = document.getElementById(id); if(!ctx) return;
  charts[id] = new Chart(ctx, {
    type:'bar',
    data:{labels, datasets:[{data, backgroundColor:colors||COLORS[0], borderRadius:4}]},
    options:{...CO, indexAxis:'y',
      plugins:{...CO.plugins, tooltip:{...CO.plugins.tooltip, callbacks:{label: callbackFn || (c=>`  ${fmtM(c.raw)}`)} }},
      scales:{x:{...CO.scales.x, ticks:{...CO.scales.x.ticks,callback:v=>`€${(v/1e6).toFixed(0)}M`}}, y:{...CO.scales.y}}}
  });
}

function barV(id, labels, data, colors){
  dc(id);
  const ctx = document.getElementById(id); if(!ctx) return;
  charts[id] = new Chart(ctx, {
    type:'bar',
    data:{labels, datasets:[{data, backgroundColor:colors||COLORS[0], borderRadius:5, borderSkipped:false}]},
    options:{...CO,
      plugins:{...CO.plugins, tooltip:{...CO.plugins.tooltip, callbacks:{label:c=>`  €${(c.raw/1e9).toFixed(3)}mld`}}},
      scales:{x:{...CO.scales.x}, y:{...CO.scales.y, ticks:{...CO.scales.y.ticks,callback:v=>`€${(v/1e9).toFixed(1)}mld`}}}
    }
  });
}

function doughnut(id, labels, data){
  dc(id);
  const ctx = document.getElementById(id); if(!ctx) return;
  charts[id] = new Chart(ctx, {
    type:'doughnut',
    data:{labels, datasets:[{data, backgroundColor:COLORS.slice(0,labels.length), borderWidth:2, borderColor:'#0a0d14'}]},
    options:{responsive:true, maintainAspectRatio:false, cutout:'58%',
      plugins:{legend:{position:'right',labels:{color:'#6b7a99',font:{family:'DM Mono',size:9},boxWidth:10,padding:10}},
        tooltip:{backgroundColor:'#111520',borderColor:'#1e2540',borderWidth:1,titleColor:'#6b7a99',bodyColor:'#e8ecf5',
          callbacks:{label:c=>`  €${(c.raw/1e6).toFixed(0)}M (${(c.raw/c.dataset.data.reduce((a,b)=>a+b)*100).toFixed(1)}%)`}}}}
  });
}

function line(id, labels, datasets){
  dc(id);
  const ctx = document.getElementById(id); if(!ctx) return;
  charts[id] = new Chart(ctx, {
    type:'line',
    data:{labels, datasets: datasets.map((d,i)=>({
      label:d.label, data:d.data,
      borderColor:COLORS[i%COLORS.length], backgroundColor:COLORS[i%COLORS.length]+'18',
      borderWidth:2, pointRadius:4, pointHoverRadius:6, fill:false, tension:.3
    }))},
    options:{...CO,
      plugins:{...CO.plugins,
        legend:{display:true, position:'bottom', labels:{color:'#6b7a99',font:{family:'DM Mono',size:9},boxWidth:10,padding:10}},
        tooltip:{...CO.plugins.tooltip, callbacks:{label:c=>`  ${c.dataset.label}: €${(c.raw/1e6).toFixed(0)}M`}}},
      scales:{x:{...CO.scales.x}, y:{...CO.scales.y, ticks:{...CO.scales.y.ticks, callback:v=>`€${(v/1e6).toFixed(0)}M`}}}
    }
  });
}

function stacked(id, labels, datasets){
  dc(id);
  const ctx = document.getElementById(id); if(!ctx) return;
  charts[id] = new Chart(ctx, {
    type:'bar',
    data:{labels, datasets: datasets.map((d,i)=>({label:d.label, data:d.data, backgroundColor:COLORS[i%COLORS.length], borderRadius:3}))},
    options:{...CO, indexAxis:'y',
      plugins:{...CO.plugins,
        legend:{display:true, position:'bottom', labels:{color:'#6b7a99',font:{family:'DM Mono',size:9},boxWidth:10}},
        tooltip:{...CO.plugins.tooltip, callbacks:{label:c=>`  ${c.dataset.label}: €${(c.raw/1e6).toFixed(0)}M`}}},
      scales:{x:{stacked:true, ...CO.scales.x, ticks:{...CO.scales.x.ticks,callback:v=>`€${(v/1e6).toFixed(0)}M`}},
              y:{stacked:true, ...CO.scales.y}}}
  });
}

function rankList(id, items, max, colorFn, valFn){
  const el = document.getElementById(id); if(!el) return;
  el.innerHTML = items.map((d,i)=>`
    <div class="ri">
      <div class="rn">${String(i+1).padStart(2,'0')}</div>
      <div class="rbw">
        <div class="rlbl">${d.label}</div>
        <div class="rbb"><div class="rbf" style="width:${(d.v/max*100).toFixed(1)}%;background:${colorFn?colorFn(d,i):COLORS[i%COLORS.length]}"></div></div>
      </div>
      <div class="rv">${valFn?valFn(d):fmtM(d.v)}</div>
    </div>`).join('');
}

// ── RENDER ──
function render(){
  const yd = D.data[AY];
  const ypd = D.data[AY-1];
  if(!yd) return;

  // KPI
  const tot = yd.kpi.totale, conv = yd.kpi.convenzionata, trac = yd.kpi.tracciabilita, conf = yd.kpi.confezioni;
  document.getElementById('k-tot').textContent = fmt(tot);
  document.getElementById('k-tot-s').textContent = `Anno ${AY}`;
  document.getElementById('k-conv').textContent = fmt(conv);
  document.getElementById('k-conv-s').textContent = `${(conv/tot*100).toFixed(1)}% della spesa SSN`;
  document.getElementById('k-trac').textContent = fmt(trac);
  document.getElementById('k-trac-s').textContent = `${(trac/tot*100).toFixed(1)}% della spesa SSN`;
  document.getElementById('k-conf').textContent = fmtN(conf);
  document.getElementById('k-conf-s').textContent = `confezioni dispensate`;

  function setDelta(id, cur, prev){
    if(!prev || !prev.kpi) return;
    const d = pct(cur, prev.kpi[id.includes('tot')?'totale':id.includes('conv')?'convenzionata':'tracciabilita']);
    const el = document.getElementById(id);
    el.textContent = sign(d);
    el.className = 'kpi-delta ' + (d>=0?'up':'down');
  }
  if(ypd){
    setDelta('k-tot-d', tot, ypd);
    setDelta('k-conv-d', conv, ypd);
    setDelta('k-trac-d', trac, ypd);
  }

  // ATC1 bar
  const atc1 = yd.atc1.slice(0,8);
  barH('c-atc1', atc1.map(d=>d.label.split(' ').slice(0,3).join(' ')), atc1.map(d=>d.totale), atc1.map((_,i)=>COLORS[i%COLORS.length]));

  // Classi doughnut
  doughnut('c-classi', yd.classi.map(d=>`Classe ${d.label}`), yd.classi.map(d=>d.totale));

  // Flussi stacked
  const atc1s = yd.atc1.slice(0,10);
  stacked('c-flussi', atc1s.map(d=>d.label.split(' ').slice(0,3).join(' ')),
    [{label:'Convenzionata', data:atc1s.map(d=>d.conv)},
     {label:'Tracciabilità', data:atc1s.map(d=>d.traccia)}]);

  // ATC2 rank
  const atc2 = yd.atc2.slice(0,15).map(d=>({...d, v:d.totale}));
  rankList('r-atc2', atc2, atc2[0]?.v||1, (_,i)=>COLORS[i%COLORS.length]);

  // Classi detail
  const classiD = yd.classi.map(d=>({...d, v:d.totale}));
  const classiMax = classiD[0]?.v||1;
  const clColors = {'A':'#00d4ff','H':'#c084fc','C':'#ff6b35','C-bis':'#ffd166','PHT':'#7fff6b','RRL':'#ff4d6d'};
  document.getElementById('r-classi').innerHTML = classiD.map(d=>`
    <div class="ri">
      <div style="font-family:var(--mono);font-size:.65rem;font-weight:700;color:${clColors[d.label]||'#6b7a99'};width:45px;flex-shrink:0">${d.label}</div>
      <div class="rbw">
        <div class="rbb"><div class="rbf" style="width:${(d.v/classiMax*100).toFixed(1)}%;background:${clColors[d.label]||'#6b7a99'}"></div></div>
        <div style="font-family:var(--mono);font-size:.58rem;color:var(--text-muted);margin-top:3px">Conv: ${fmtM(d.conv)} · Traccia: ${fmtM(d.traccia)}</div>
      </div>
      <div class="rv"><div>${fmtM(d.v)}</div><div style="color:var(--text-muted)">${(d.v/tot*100).toFixed(1)}%</div></div>
    </div>`).join('');

  // TREND bar
  const yrs = D.years;
  barV('c-trend', yrs, yrs.map(y=>D.data[y]?.kpi.totale||0),
    yrs.map(y=>y==AY?'#00d4ff':'#1e2540'));

  // ATC1 line trend
  const top6 = (D.data[Math.max(...yrs)]?.atc1||[]).slice(0,6).map(d=>d.label);
  line('c-atc1-trend', yrs, top6.map(atc=>({
    label: atc.split(' ').slice(0,3).join(' '),
    data: yrs.map(y=>(D.data[y]?.atc1||[]).find(d=>d.label===atc)?.totale||0)
  })));

  // Classi line trend
  const clabels = [...new Set(yrs.flatMap(y=>(D.data[y]?.classi||[]).map(d=>d.label)))].filter(Boolean);
  line('c-classi-trend', yrs, clabels.map(cl=>({
    label: `Classe ${cl}`,
    data: yrs.map(y=>(D.data[y]?.classi||[]).find(d=>d.label===cl)?.totale||0)
  })));

  // MOVERS
  const up5 = D.atc2_changes.slice(0,5);
  const dn5 = [...D.atc2_changes].reverse().slice(0,5);
  const fmt2 = v => v>=1e9?`€${(v/1e9).toFixed(2)}mld`:v>=1e6?`€${(v/1e6).toFixed(0)}M`:`€${(v/1e3).toFixed(0)}K`;
  document.getElementById('m-up').innerHTML = up5.length ? up5.map(d=>`
    <div class="mc up">
      <div style="flex:1;min-width:0">
        <div class="mn">${d.label}</div>
        <div class="msub">${fmt2(d.v2020)} → ${fmt2(d.v2024)}</div>
      </div>
      <div class="md">+${d.delta_pct.toFixed(0)}%</div>
    </div>`).join('') : '<div style="color:var(--text-muted);font-family:var(--mono);font-size:.65rem;padding:1rem">Nessun dato disponibile</div>';
  document.getElementById('m-down').innerHTML = dn5.length ? dn5.map(d=>`
    <div class="mc down">
      <div style="flex:1;min-width:0">
        <div class="mn">${d.label}</div>
        <div class="msub">${fmt2(d.v2020)} → ${fmt2(d.v2024)}</div>
      </div>
      <div class="md">${d.delta_pct.toFixed(0)}%</div>
    </div>`).join('') : '<div style="color:var(--text-muted);font-family:var(--mono);font-size:.65rem;padding:1rem">Nessun dato disponibile</div>';

  // ── ATC4 NAZIONALE TOP 5 ──
  const atc4top = (yd.atc4||[]).slice(0,5).map(d=>({...d,v:d.totale}));
  rankList('r-atc4-top', atc4top, atc4top[0]?.v||1, (_,i)=>COLORS[i%COLORS.length]);

  // ── ATC4 PER CLASSE (top2 per classe) ──
  const atc4Classe = yd.top_atc4_per_classe || {};
  const clOrder = Object.keys(atc4Classe).sort();
  document.getElementById('r-atc4-classe').innerHTML = clOrder.map(cl => {
    const items = atc4Classe[cl] || [];
    return `<div>
      <div style="font-family:var(--mono);font-size:.58rem;letter-spacing:.12em;text-transform:uppercase;color:${clColors[cl]||'#6b7a99'};margin-bottom:.4rem">Classe ${cl}</div>
      ${items.map((it,i) => `
        <div class="ri" style="margin-bottom:.3rem">
          <div class="rn">${i+1}</div>
          <div class="rbw">
            <div class="rlbl">${it.label}</div>
            <div class="rbb"><div class="rbf" style="width:${i===0?'100':(it.totale/(items[0]?.totale||1)*100).toFixed(0)}%;background:${clColors[cl]||COLORS[i]}"></div></div>
          </div>
          <div class="rv">${fmtM(it.totale)}</div>
        </div>`).join('')}
    </div>`;
  }).join('');

  // ── ATC4 TREND CRESCITA % ──
  function trendLine(id, items, note) {
    if(!items || !items.length){ dc(id); return; }
    line(id, yrs, items.map(d=>({
      label: d.label.length>35 ? d.label.slice(0,33)+'…' : d.label,
      data: d.trend.map(t=>t.v)
    })));
    // aggiungi nota sotto
    const wrap = document.getElementById(id)?.closest('.ch');
    if(wrap && note){
      let n = wrap.querySelector('.trend-note');
      if(!n){ n = document.createElement('div'); n.className='trend-note'; n.style.cssText='font-family:var(--mono);font-size:.58rem;color:var(--text-muted);text-align:center;margin-top:.4rem'; wrap.appendChild(n); }
      n.textContent = note;
    }
  }
  trendLine('c-atc4-pct', D.atc4_top_pct, 'Crescita % 2020→2024 — tutti i principi attivi con spesa >€200k');
  trendLine('c-atc4-pct-q4', D.atc4_top_pct_q4, 'Crescita % 2020→2024 — solo farmaci nel top quartile per volume 2024');

  // ── ATC4 DECRESCITE ASSOLUTE ──
  if(D.atc4_top_decline && D.atc4_top_decline.length){
    dc('c-atc4-decline');
    const ctx4 = document.getElementById('c-atc4-decline');
    if(ctx4){
      charts['c-atc4-decline'] = new Chart(ctx4, {
        type:'line',
        data:{
          labels: yrs,
          datasets: D.atc4_top_decline.map((d,i)=>({
            label: d.label.length>40 ? d.label.slice(0,38)+'…' : d.label,
            data: d.trend.map(t=>t.v),
            borderColor: COLORS[i%COLORS.length],
            backgroundColor: COLORS[i%COLORS.length]+'18',
            borderWidth:2, pointRadius:4, fill:false, tension:.3,
            borderDash: [5,3],
          }))
        },
        options:{...CO,
          plugins:{...CO.plugins,
            legend:{display:true,position:'bottom',labels:{color:'#6b7a99',font:{family:'DM Mono',size:9},boxWidth:10,padding:8}},
            tooltip:{...CO.plugins.tooltip,callbacks:{label:c=>`  ${c.dataset.label}: €${(c.raw/1e6).toFixed(0)}M`}}},
          scales:{x:{...CO.scales.x},y:{...CO.scales.y,ticks:{...CO.scales.y.ticks,callback:v=>`€${(v/1e6).toFixed(0)}M`}}}
        }
      });
    }
  }

  // ── TOP ATC4 PER REGIONE ──
  const topA4reg = yd.top_atc4_per_reg || {};
  const regKeys = Object.keys(topA4reg).sort();
  document.getElementById('reg-atc4-cards').innerHTML = regKeys.map((reg,i) => {
    const it = topA4reg[reg];
    const col = COLORS[i % COLORS.length];
    return `<div class="rc" style="border-top:2px solid ${col}20;border-color:${col}30">
      <div class="rcn" style="color:${col}">${reg}</div>
      <div style="font-size:.68rem;font-weight:500;margin:.3rem 0;line-height:1.3">${it.label}</div>
      <div class="rcs">${fmtM(it.totale)}</div>
      <div style="font-family:var(--mono);font-size:.55rem;color:var(--text-muted);margin-top:2px">${it.code}</div>
    </div>`;
  }).join('');

  // REGIONI
  const regs = yd.regioni;
  const yoy = D.yoy[AY] || {};
  const regMax = regs[0]?.totale||1;
  const regAvg = regs.reduce((s,r)=>s+r.totale,0) / (regs.length||1);

  barH('c-reg', regs.map(d=>d.label), regs.map(d=>d.totale),
    regs.map((_,i)=>COLORS[i%COLORS.length]));

  // YoY bar (green/red)
  const regsWithYoy = regs.filter(r=>yoy[r.label]!==undefined);
  if(regsWithYoy.length){
    dc('c-reg-yoy');
    const ctx = document.getElementById('c-reg-yoy');
    charts['c-reg-yoy'] = new Chart(ctx, {
      type:'bar',
      data:{labels:regsWithYoy.map(r=>r.label),
        datasets:[{data:regsWithYoy.map(r=>yoy[r.label]),
          backgroundColor:regsWithYoy.map(r=>yoy[r.label]>=0?'#00e5a040':'#ff4d6d40'),
          borderColor:regsWithYoy.map(r=>yoy[r.label]>=0?'#00e5a0':'#ff4d6d'),
          borderWidth:1, borderRadius:4}]},
      options:{...CO, indexAxis:'y',
        plugins:{...CO.plugins,tooltip:{...CO.plugins.tooltip,callbacks:{label:c=>`  ${c.raw>=0?'+':''}${c.raw.toFixed(1)}%`}}},
        scales:{x:{...CO.scales.x,ticks:{...CO.scales.x.ticks,callback:v=>v.toFixed(0)+'%'}}, y:{...CO.scales.y}}}
    });
  }

  // Region cards
  document.getElementById('reg-cards').innerHTML = regs.map(r=>{
    const dy = yoy[r.label];
    const vsAvg = (r.totale - regAvg) / regAvg * 100;
    const heat = Math.min(r.totale / regMax, 1);
    const col = heat > .7 ? '#ff6b35' : heat > .4 ? '#00d4ff' : '#3a4560';
    return `<div class="rc">
      <div class="rcn">${r.label}</div>
      <div class="rcs">${fmt(r.totale)}</div>
      <div class="rcd" style="color:${dy===undefined?'var(--text-muted)':dy>=0?'var(--green)':'var(--red)'}">${dy!==undefined?sign(dy):'—'} vs ${AY-1}</div>
      <div style="font-family:var(--mono);font-size:.55rem;color:var(--text-muted);margin-top:2px">${sign(vsAvg)} vs media</div>
      <div class="rch" style="background:${col};width:${(heat*100).toFixed(0)}%"></div>
    </div>`;
  }).join('');

  // Reg movers 2020→2024
  const ru5 = D.reg_changes.slice(0,5).map(d=>({...d,v:d.delta_pct}));
  const rd5 = [...D.reg_changes].reverse().slice(0,5).map(d=>({...d,v:Math.abs(d.delta_pct)}));
  rankList('r-reg-up', ru5, Math.max(...ru5.map(d=>d.v)), ()=>'var(--green)', d=>sign(d.v));
  rankList('r-reg-down', rd5, Math.max(...rd5.map(d=>d.v)), ()=>'var(--red)', d=>'-'+d.v.toFixed(1)+'%');

  // Mensile
  const mesi = yd.mesi;
  dc('c-mesi');
  const ctx = document.getElementById('c-mesi');
  if(ctx && mesi.length){
    charts['c-mesi'] = new Chart(ctx, {
      type:'line',
      data:{
        labels: mesi.map(m=>MESI_LABEL[parseInt(m.mese)]||m.mese),
        datasets:[{
          data: mesi.map(m=>m.totale),
          borderColor:'#00d4ff', backgroundColor:'#00d4ff15',
          borderWidth:2, pointRadius:4, pointHoverRadius:6, fill:true, tension:.3
        }]
      },
      options:{...CO,
        plugins:{...CO.plugins,tooltip:{...CO.plugins.tooltip,callbacks:{label:c=>`  €${(c.raw/1e6).toFixed(0)}M`}}},
        scales:{x:{...CO.scales.x},y:{...CO.scales.y,ticks:{...CO.scales.y.ticks,callback:v=>`€${(v/1e6).toFixed(0)}M`}}}
      }
    });
    const avg = mesi.reduce((s,m)=>s+m.totale,0)/mesi.length;
    document.getElementById('monthly-note').textContent = `Media mensile: ${fmtM(avg)} · ${mesi.length} mesi nel dataset`;
  }
}

// YEAR TABS
document.querySelectorAll('.yt').forEach(t=>{
  t.addEventListener('click',()=>{
    document.querySelectorAll('.yt').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    AY = parseInt(t.dataset.y);
    render();
  });
});

// AI
document.getElementById('ai-btn').addEventListener('click', async ()=>{
  const btn = document.getElementById('ai-btn');
  const out = document.getElementById('ai-out');
  btn.disabled = true; btn.textContent = 'Analisi in corso...';
  out.innerHTML = '<span style="color:var(--text-dim)">Claude sta elaborando i dati...</span>';

  const summary = D.years.map(y=>{
    const d = D.data[y];
    const top3atc = d.atc1.slice(0,3).map(a=>`${a.label.split(' ').slice(0,3).join(' ')}: €${(a.totale/1e9).toFixed(2)}mld`).join(', ');
    const top3reg = d.regioni.slice(0,3).map(r=>`${r.label}: €${(r.totale/1e6).toFixed(0)}M`).join(', ');
    return `Anno ${y}: totale €${(d.kpi.totale/1e9).toFixed(2)}mld | convenzionata €${(d.kpi.convenzionata/1e9).toFixed(2)}mld (${(d.kpi.convenzionata/d.kpi.totale*100).toFixed(0)}%) | tracciabilità €${(d.kpi.tracciabilita/1e9).toFixed(2)}mld (${(d.kpi.tracciabilita/d.kpi.totale*100).toFixed(0)}%) | Top ATC: ${top3atc} | Top regioni: ${top3reg}`;
  }).join('\n');

  const top5up = D.atc2_changes.slice(0,5).map(d=>`${d.label} +${d.delta_pct.toFixed(0)}%`).join(', ');
  const top5dn = [...D.atc2_changes].reverse().slice(0,5).map(d=>`${d.label} ${d.delta_pct.toFixed(0)}%`).join(', ');
  const topRegUp = D.reg_changes.slice(0,3).map(d=>`${d.label} +${d.delta_pct.toFixed(0)}%`).join(', ');

  const prompt = `Sei un esperto di sanità pubblica e spesa farmaceutica italiana. Analizza questi dati AIFA e scrivi un'analisi professionale di circa 300 parole.

DATI PER ANNO:
${summary}

TOP 5 CRESCITA ATC-2 (2020→2024): ${top5up}
TOP 5 CALO ATC-2 (2020→2024): ${top5dn}
REGIONI CON MAGGIORE CRESCITA: ${topRegUp}

Scrivi in italiano, in modo chiaro e professionale. Struttura la risposta con:
1. Un paragrafo sul trend generale della spesa 2020-2024
2. Un paragrafo sulle categorie terapeutiche più dinamiche (crescite e cali)
3. Un paragrafo sulle differenze regionali
4. Una conclusione con 1-2 implicazioni per le politiche sanitarie

Usa dati concreti. Sii diretto. Massimo 320 parole.`;

  try {
    const r = await fetch('https://api.anthropic.com/v1/messages',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({model:'claude-sonnet-4-20250514',max_tokens:1000,messages:[{role:'user',content:prompt}]})
    });
    const data = await r.json();
    const text = data.content?.map(c=>c.text||'').join('')||'Analisi non disponibile.';
    out.innerHTML = text.split('\n').filter(Boolean).map(l=>`<p>${l}</p>`).join('');
  } catch(e) {
    out.innerHTML = `<span style="color:var(--text-dim)">Analisi AI non disponibile offline. Apri la dashboard con connessione internet attiva per abilitarla.</span>`;
  }
  btn.disabled = false; btn.textContent = 'Rigenera →';
});

// INIT
render();
</script>
</body>
</html>""".replace('__DATA__', json.dumps(payload, ensure_ascii=False, separators=(',', ':')))

import datetime
os.makedirs("docs", exist_ok=True)
out_path = "docs/index.html"
build_date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(HTML)

size_kb = os.path.getsize(out_path) // 1024
print(f"\n✓ Dashboard generata: {out_path} ({size_kb} KB)")
print(f"\n  Anni inclusi: {sorted(payload['years'])}")
for y in sorted(all_agg.keys()):
    t = all_agg[y]['kpi']['totale']
    n4 = len(all_agg[y]['atc4_all'])
    print(f"  {y}: €{t/1e9:.2f}mld | {len(all_agg[y]['atc1'])} ATC-1 | {n4} ATC-4 | {len(all_agg[y]['regioni'])} regioni")
print(f"\n  ATC-4 top crescita %: {[x['label'][:30] for x in atc4_top_pct]}")
print(f"  ATC-4 top crescita Q4: {[x['label'][:30] for x in atc4_top_pct_q4]}")
print(f"  ATC-4 top calo assoluto: {[x['label'][:30] for x in atc4_top_decline]}")
print(f"\n► Apri {out_path} nel browser — funziona completamente offline!")
print("  (L'analisi AI richiede connessione internet)\n")
