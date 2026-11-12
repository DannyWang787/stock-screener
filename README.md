# Swing Setup Screener

End-of-day US stock screener for two swing setups: **pullback in uptrend** and **flat base**.

## Run it

```bash
pip install -r requirements.txt
```

```bash
python scan.py
```

```bash
python build_site.py
```

```bash
python -m http.server 8000 --directory site
```

Then open http://localhost:8000. A full scan downloads about 5,000 tickers and takes roughly 10 minutes.
`python scan.py 400` scans only the first 400 tickers for a quick test.

## Layout

| Path | What it does |
|---|---|
| `config.py` | Every scan rule and threshold |
| `screener/data.py` | Ticker list (exchange symbol directory) and daily bars (yfinance) |
| `screener/setups.py` | Pullback and flat base detectors, scores, entry/stop/target |
| `scan.py` | Runs the scan, writes `site/data/scan.json` and `site/data/bars.json` |
| `web/dashboard.html` | The dashboard; filters run in the browser |
| `.github/workflows/scan.yml` | Nightly scan and GitHub Pages deploy |

## Notes

- Dashboard filters (volume, price, moving-average rules) apply instantly. Pattern rules in `config.py` apply from the next scan.
- The setup rules are not backtested. Earnings dates from Yahoo can be wrong.
