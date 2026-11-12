"""Nightly scan: download bars, compute indicators, detect setups, write site/data."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import config as C
from screener import data, setups

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "site" / "data"


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def sma(x, n):
    return pd.Series(x).rolling(n).mean().to_numpy()


def arrays(df):
    o, h, l, c, v = (df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close", "Volume"))
    a = {"o": o, "h": h, "l": l, "c": c, "v": v}
    for n in C.MA_PERIODS:
        a[f"ema{n}"] = ema(c, n)
        a[f"sma{n}"] = sma(c, n)
    for n in C.VOLUME_PERIODS:
        a[f"vol{n}"] = sma(v, n)
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    a["atr"] = sma(tr, 14)
    return a


def rs_raw(c):
    """Weighted 3/6/12-month return (recent quarter counts double)."""
    def r(n):
        return c[-1] / c[-1 - n] - 1 if len(c) > n else np.nan
    parts = [r(63), r(63), r(126), r(189), r(252)]
    parts = [p for p in parts if not np.isnan(p)]
    return float(np.mean(parts)) if parts else np.nan


def regime(bars_idx, breadth):
    out = {"breadth50": round(breadth * 100), "indexes": []}
    for t, label in (("SPY", "S&P 500"), ("QQQ", "Nasdaq 100")):
        d = bars_idx.get(t)
        if d is None:
            continue
        c = d["Close"].to_numpy(dtype=float)
        s50, s200 = c[-50:].mean(), c[-200:].mean()
        out["indexes"].append({"ticker": t, "label": label, "close": round(c[-1], 2),
                               "chg": round((c[-1] / c[-2] - 1) * 100, 2),
                               "above50": bool(c[-1] > s50), "above200": bool(c[-1] > s200),
                               "vs50": round((c[-1] / s50 - 1) * 100, 1)})
    ups = sum(i["above50"] + i["above200"] for i in out["indexes"])
    full = 2 * len(out["indexes"])
    if ups == full and breadth >= 0.5:
        out["state"], out["text"] = "up", "Uptrend: indexes above their 50- and 200-day averages"
    elif ups >= full / 2:
        out["state"], out["text"] = "mixed", "Mixed: trade smaller, be picky"
    else:
        out["state"], out["text"] = "down", "Downtrend: long setups fail more often"
    return out


def main(limit=None):
    t0 = time.time()
    print("Loading universe...")
    uni = data.load_universe()
    tickers = sorted(uni)[:limit] if limit else sorted(uni)
    print(f"  {len(tickers)} tickers after pre-filter")
    # Reuse today's download when re-running after a rule change (cache/ is not committed).
    import pickle
    cache = ROOT / "cache" / f"bars-{datetime.now(timezone.utc):%Y%m%d}-{len(tickers)}.pkl"
    if cache.exists():
        bars = pickle.loads(cache.read_bytes())
        print("  using cached bars")
    else:
        bars = data.download_bars(tickers + ["SPY", "QQQ"], period=C.HISTORY_PERIOD)
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(pickle.dumps(bars))
    idx = {k: bars.pop(k) for k in ("SPY", "QQQ") if k in bars}
    last_day = max(d.index[-1] for d in idx.values()) if idx else max(d.index[-1] for d in bars.values())

    work, raw = {}, {}
    for t, df in bars.items():
        if len(df) < C.MIN_BARS or df.index[-1] != last_day:
            continue
        c = df["Close"].to_numpy(dtype=float)
        if c[-1] < C.UNIVERSE_MIN_PRICE or (df["Close"] * df["Volume"]).tail(20).mean() < C.UNIVERSE_MIN_DOLLAR_VOLUME:
            continue
        work[t] = df
        raw[t] = rs_raw(c)
    rs = (pd.Series(raw).rank(pct=True) * 99).round().fillna(0).astype(int).to_dict()
    print(f"  {len(work)} stocks in scan universe")

    rows, chart, above50 = [], {}, 0
    for t, df in work.items():
        a = arrays(df)
        c = a["c"]
        above50 += c[-1] > a["sma50"][-1]
        found = [s for s in (setups.detect_pullback(a, rs[t]), setups.detect_flat_base(a, rs[t])) if s]
        if not found:
            continue
        hi52, lo52 = a["h"][-252:].max(), a["l"][-252:].min()
        row = {
            "t": t, **uni[t], "close": round(c[-1], 2), "chg": round((c[-1] / c[-2] - 1) * 100, 2),
            # price change over the last 20 / 60 / 90 trading days
            "ret": {str(n): round((c[-1] / c[-1 - n] - 1) * 100, 1) for n in C.RETURN_PERIODS},
            "rs": rs[t], "atr": round(a["atr"][-1] / c[-1] * 100, 1),
            "fromHigh": round((c[-1] / hi52 - 1) * 100, 1), "fromLow": round((c[-1] / lo52 - 1) * 100, 1),
            "vol": {str(n): int(a[f"vol{n}"][-1]) for n in C.VOLUME_PERIODS},
            "dvol": {str(n): int((c[-n:] * a["v"][-n:]).mean()) for n in C.VOLUME_PERIODS},
            "volToday": round(a["v"][-1] / a["vol50"][-1], 2) if a["vol50"][-1] else 0,
            "ema": {str(n): round(a[f"ema{n}"][-1], 3) for n in C.MA_PERIODS},
            "sma": {str(n): round(float(np.nan_to_num(a[f"sma{n}"][-1])), 3) for n in C.MA_PERIODS},
            "setups": found,
        }
        rows.append(row)
        n = C.CHART_BARS
        chart[t] = {"n": int(min(n, len(c))),
                    "o": np.round(a["o"][-n:], 2).tolist(), "h": np.round(a["h"][-n:], 2).tolist(),
                    "l": np.round(a["l"][-n:], 2).tolist(), "c": np.round(c[-n:], 2).tolist(),
                    "v": a["v"][-n:].astype(int).tolist(),
                    "e200": round(float(a["ema200"][-min(n, len(c))]), 2)}

    print(f"  {len(rows)} candidates; fetching earnings dates...")
    earn = data.earnings_dates([r["t"] for r in rows])
    for r in rows:
        r["earn"] = earn.get(r["t"])

    ref = next(iter(idx.values())) if idx else next(iter(work.values()))
    dates = [d.strftime("%Y-%m-%d") for d in ref.index[-C.CHART_BARS:]]
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"asOf": last_day.strftime("%Y-%m-%d"), "dates": dates,
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "universe": len(work), "maPeriods": C.MA_PERIODS, "volPeriods": C.VOLUME_PERIODS,
            "floor": {"price": C.UNIVERSE_MIN_PRICE, "dollarVolume": C.UNIVERSE_MIN_DOLLAR_VOLUME},
            "regime": regime(idx, above50 / max(1, len(work)))}
    (OUT / "scan.json").write_text(json.dumps({"meta": meta, "rows": rows}, separators=(",", ":")))
    # One small file per candidate, so the dashboard only downloads the chart being viewed.
    bars_dir = OUT / "bars"
    bars_dir.mkdir(exist_ok=True)
    for old in bars_dir.glob("*.json"):
        old.unlink()
    for t, b in chart.items():
        (bars_dir / f"{t}.json").write_text(json.dumps(b, separators=(",", ":")))
    stale = OUT / "bars.json"
    if stale.exists():
        stale.unlink()
    print(f"Done in {time.time() - t0:.0f}s -> {OUT}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
