# AIFA · Osservatorio Spesa Farmaceutica

Dashboard interattiva sulla spesa farmaceutica pubblica italiana 2020–2024.

**→ [Apri la dashboard](https://TUOUSERNAME.github.io/aifa-dashboard)**

## Dati

Fonte: [AIFA Open Data](https://www.aifa.gov.it/spesa-farmaceutica)  
Aggiornamento: automatico ogni lunedì

## Come funziona

Lo script `build_dashboard.py` scarica i CSV AIFA, li aggrega e genera
`docs/index.html` — un file HTML standalone con tutti i dati incorporati.

GitHub Actions esegue lo script ogni settimana e pubblica l'HTML su GitHub Pages.

## Esecuzione locale

```bash
python build_dashboard.py
# genera docs/index.html — aprilo nel browser
```

Nessuna dipendenza esterna necessaria (solo Python 3 standard).
