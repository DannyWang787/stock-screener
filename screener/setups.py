"""Setup detectors. Each works on numpy arrays and an end index `t`, so the same
code can later be replayed over history for backtesting.

PATTERN rules decide whether the setup exists at all. Everything else is a SCORE
rule: it moves the score and is listed in the score breakdown, but never removes
a stock. See config.py.
"""
import numpy as np

import config as C


def _clip01(x):
    return float(max(0.0, min(1.0, x)))


def _score(parts):
    """parts: [(label, fraction 0..1, max points)] -> (total, breakdown for the dashboard)."""
    rows = [[label, round(frac * pts), pts] for label, frac, pts in parts]
    return sum(r[1] for r in rows), rows


# --------------------------------------------------------------------------- pullback
def pullback_at(a, t):
    """Is there a pullback as of bar t? Returns measurements or None."""
    h, l, c, v = a["h"], a["l"], a["c"], a["v"]
    if t < C.PB_HIGH_LOOKBACK + 70:
        return None
    # ---- pattern: a swing high in the last few bars, then a real dip from it
    w0 = t - C.PB_MAX_DAYS
    hi_i = w0 + int(np.argmax(h[w0 : t + 1]))
    days = t - hi_i
    if days < C.PB_MIN_DAYS:
        return None
    H = h[hi_i]
    lo_i = hi_i + 1 + int(np.argmin(l[hi_i + 1 : t + 1]))
    L = l[lo_i]
    depth = (H - L) / H
    if not (C.PB_MIN_DEPTH <= depth <= C.PB_MAX_DEPTH_CAP):
        return None
    pb = slice(hi_i + 1, t + 1)
    if c[pb].min() >= c[hi_i]:
        return None  # no close below the swing-high day's close: price has not actually pulled back

    # ---- score inputs only from here on
    fresh_high = bool(H >= h[hi_i - C.PB_HIGH_LOOKBACK : hi_i].max())
    advance = float(H / l[hi_i - C.PB_HIGH_LOOKBACK : hi_i].min() - 1)
    ema50_rising = bool(a["ema50"][t] > a["ema50"][t - 20])
    recent = slice(min(hi_i + 1, t + 1 - C.PB_HOLD_BARS), t + 1)
    below50 = int((c[recent] < a["ema50"][recent]).sum())
    if below50 == 0 and (c[pb] >= a["ema20"][pb]).all():
        held, hold = "20 EMA", 1.0
    elif below50 == 0:
        held, hold = "50 EMA", 0.6
    elif c[t] >= a["ema50"][t]:
        held, hold = f"No: {below50} closes below 50 EMA, back above now", 0.25
    else:
        held, hold = f"No: {below50} closes below 50 EMA, still below", 0.0
    best = None  # which moving average did the pullback low reach?
    for name, arr in (("10 EMA", a["ema10"]), ("20 EMA", a["ema20"]), ("50 EMA", a["ema50"])):
        dist = (L - arr[lo_i]) / arr[lo_i]
        if -C.PB_MA_TOLERANCE * 1.5 <= dist <= C.PB_MA_TOLERANCE:
            if best is None or abs(dist) < abs(best[1]):
                best = (name, dist)
    pb_vol = v[pb].mean()
    return {"hi_i": hi_i, "lo_i": lo_i, "high": float(H), "low": float(L), "depth": float(depth),
            "days": int(days), "held": held, "hold": hold, "fresh_high": fresh_high, "advance": advance,
            "ema50_rising": ema50_rising, "ma": best[0] if best else "None within 2%",
            "ma_dist": float(best[1]) if best else None,
            "vol_ratio": float(pb_vol / a["vol50"][t]) if a["vol50"][t] > 0 else 1.0}


def detect_pullback(a, rs):
    t = len(a["c"]) - 1
    c, h = a["c"], a["h"]
    atr = a["atr"][t]
    prev = pullback_at(a, t - 1)
    if prev and c[t] > h[t - 1]:
        status, p = "triggered", prev
        entry = float(h[t - 1]) + 0.01
        low = min(p["low"], float(a["l"][t]))
    else:
        p = pullback_at(a, t)
        if not p:
            return None
        status = "setup"
        entry = float(h[t]) + 0.01
        low = p["low"]
    stop = low - 0.1 * atr
    risk = (entry - stop) / entry
    if risk <= 0.005:
        return None  # no room between entry and stop: levels are not usable
    trend = (0.4 * p["ema50_rising"] + 0.3 * p["fresh_high"]
             + 0.3 * _clip01(p["advance"] / C.PB_MIN_PRIOR_ADVANCE))
    span = C.PB_DEEP - C.PB_IDEAL_DEPTH
    # Volume is shown in the details but deliberately not scored.
    score, parts = _score([
        ("Relative strength", _clip01(rs / 100), 30),
        ("Closes held the 20 / 50 EMA", p["hold"], 25),
        ("Uptrend into the high", trend, 15),
        ("Low tagged an EMA", 0.0 if p["ma_dist"] is None else _clip01(1 - abs(p["ma_dist"]) / 0.03), 15),
        ("Depth near 7%", _clip01(1 - abs(p["depth"] - C.PB_IDEAL_DEPTH) / span), 15),
    ])
    return {
        "type": "pullback", "status": status, "score": score, "parts": parts,
        "entry": round(entry, 2), "stop": round(stop, 2),
        "target": round(entry + C.TARGET_R * (entry - stop), 2), "risk": round(risk * 100, 1),
        "ext": round((c[t] / entry - 1) * 100, 1),
        "notes": {"Swing high": round(p["high"], 2), "Pullback low": round(low, 2),
                  "Depth": f"{p['depth'] * 100:.1f}%", "Days from high": p["days"],
                  "Closes held above": p["held"], "Low reached": p["ma"],
                  "Swing high is a 60-day high": "Yes" if p["fresh_high"] else "No",
                  "50 EMA rising": "Yes" if p["ema50_rising"] else "No",
                  "Advance into the high": f"{p['advance'] * 100:.0f}%",
                  "Pullback volume": f"{p['vol_ratio']:.2f}x avg"},
        "lines": {"high": round(p["high"], 2)},
        "span": [int(len(c) - 1 - p["hi_i"]), 0],
    }


# --------------------------------------------------------------------------- flat base
def _touches(h, s, t, floor):
    """Separate rallies into the resistance zone. Consecutive bars in the zone are one
    touch; a new touch needs FB_TOUCH_GAP bars back below the zone first.
    Returns the bar index of the highest high of each touch."""
    idx = s + np.nonzero(h[s : t + 1] >= floor)[0]
    out, group = [], []
    for i in idx:
        if group and i - group[-1] > C.FB_TOUCH_GAP:
            out.append(max(group, key=lambda j: h[j]))
            group = []
        group.append(int(i))
    if group:
        out.append(max(group, key=lambda j: h[j]))
    return out


def flat_base_at(a, t):
    """Best flat base ending at bar t. Returns measurements or None.

    Pattern: a resistance zone under the base high that price rallied into at least
    FB_MIN_TOUCHES separate times, at the same level, over FB_MIN_RESISTANCE_BARS or more.
    Several windows can qualify; the one with the best quality wins."""
    h, l, c = a["h"], a["l"], a["c"]
    if t < C.FB_MAX_LEN + C.FB_PRIOR_LOOKBACK + 50:
        return None
    windows = []
    for n in range(C.FB_MIN_LEN, C.FB_MAX_LEN + 1):
        s = t - n + 1
        hi, lo = h[s : t + 1].max(), l[s : t + 1].min()
        if (hi - lo) / hi > C.FB_MAX_DEPTH_CAP:
            break  # longer windows only get deeper
        windows.append((s, hi))
    zone_w = min(C.FB_ZONE_MAX, max(C.FB_ZONE_MIN, C.FB_TOUCH_ATR * a["atr"][t] / c[t]))
    best, seen = None, set()
    for s, hi in reversed(windows):  # longest first
        if h[t] >= hi:
            return None  # making the high today, no pivot yet
        floor = hi * (1 - zone_w)
        touches = _touches(h, s, t, floor)
        if len(touches) < C.FB_MIN_TOUCHES or touches[-1] - touches[0] < C.FB_MIN_RESISTANCE_BARS:
            continue  # no clear resistance across the top
        # The base starts at the first touch of resistance, so the run-up before it
        # does not count towards the base low, depth or length.
        s = touches[0]
        if (s, hi) in seen:
            continue
        seen.add((s, hi))
        n = t - s + 1
        if n < C.FB_MIN_LEN:
            continue
        lo = l[s : t + 1].min()
        depth = (hi - lo) / hi

        # ---- score inputs only from here on
        advance = float(hi / l[s - C.FB_PRIOR_LOOKBACK : s].min() - 1)
        above50 = float((c[s : t + 1] >= a["ema50"][s : t + 1]).mean())
        third = n // 3
        drift = float(c[t - third + 1 : t + 1].mean() / c[s : s + third].mean() - 1)
        q = {"tight": _clip01((C.FB_MAX_DEPTH_CAP - depth) / (C.FB_MAX_DEPTH_CAP - C.FB_TIGHT)),
             "touch": _clip01((len(touches) - 1) / 3),            # 2 touches = 1/3, 4+ = full
             "above": _clip01((above50 - 0.4) / (C.FB_PCT_ABOVE_EMA50 - 0.4)),
             "side": _clip01(1 - abs(drift) / C.FB_MAX_DRIFT),
             "adv": _clip01(advance / C.FB_MIN_PRIOR_ADVANCE)}
        quality = 25 * q["tight"] + 20 * q["touch"] + 10 * q["above"] + 10 * q["side"] + 5 * q["adv"]
        if best is None or quality > best["quality"]:
            dry = a["v"][t - 9 : t + 1].mean() / a["vol50"][t] if a["vol50"][t] > 0 else 1.0
            best = {"len": int(n), "start": int(s), "pivot": float(hi), "low": float(lo), "depth": float(depth),
                    "advance": advance, "above50": above50, "drift": drift, "dry": float(dry),
                    "zone": float(floor), "support": float(lo * (1 + zone_w)), "touches": touches,
                    "q": q, "quality": quality}
    return best


def detect_flat_base(a, rs):
    t = len(a["c"]) - 1
    c, v = a["c"], a["v"]
    found = None
    for k in range(1, C.FB_BREAKOUT_LOOKBACK + 1):  # did it break out in the last k bars?
        b = flat_base_at(a, t - k)
        if not b or c[t - k] > b["pivot"]:
            continue
        after = np.nonzero(c[t - k + 1 : t + 1] > b["pivot"])[0]
        if not len(after):
            continue
        bo = t - k + 1 + int(after[0])
        if c[t] < b["pivot"]:
            return None  # broke out and failed
        bo_vol = v[bo] / a["vol50"][bo - 1] if a["vol50"][bo - 1] > 0 else 0
        if c[t] > b["pivot"] * (1 + C.FB_BUY_RANGE):
            status = "extended"
        elif bo == t:
            status = "breakout"
        else:
            status = "buyrange"
        found = (b, status, t - bo, float(bo_vol), t - k)
        break
    if not found:
        b = flat_base_at(a, t)
        if not b or c[t] > b["pivot"]:
            return None
        found = (b, "setup", None, None, t)
    b, status, days_since, bo_vol, end = found
    entry = b["pivot"] * 1.001
    stop = max(b["low"] * 0.995, entry * (1 - C.FB_MAX_STOP))
    risk = (entry - stop) / entry
    nt, q = len(b["touches"]), b["q"]
    # Volume is shown in the details but deliberately not scored.
    score, parts = _score([
        ("Tight base", q["tight"], 25),
        ("Relative strength", _clip01(rs / 100), 20),
        ("Touches of resistance", q["touch"], 20),
        ("Closes above the 50 EMA", q["above"], 10),
        ("Sideways, not drifting", q["side"], 10),
        ("Price near the base high", _clip01(1 - abs(c[t] / entry - 1) / 0.08), 10),
        ("Advance before the base", q["adv"], 5),
    ])
    notes = {"Pivot (base high)": round(b["pivot"], 2), "Base low": round(b["low"], 2),
             "Resistance touches": nt,
             "Resistance zone": f"{b['zone']:.2f} - {b['pivot']:.2f}",
             "Support zone": f"{b['low']:.2f} - {b['support']:.2f}",
             "Base depth": f"{b['depth'] * 100:.1f}%", "Base length": f"{b['len'] / 5:.0f} weeks",
             "Closes above 50 EMA": f"{b['above50'] * 100:.0f}%",
             "Drift across the base": f"{b['drift'] * 100:+.1f}%",
             "Prior advance": f"{b['advance'] * 100:.0f}%", "Recent volume": f"{b['dry']:.2f}x avg"}
    if bo_vol is not None:
        notes["Breakout volume"] = f"{bo_vol:.1f}x avg"
        notes["Breakout"] = "today" if days_since == 0 else f"{days_since} bars ago"
    return {
        "type": "flatbase", "status": status, "score": score, "parts": parts,
        "entry": round(entry, 2), "stop": round(stop, 2),
        "target": round(entry + C.TARGET_R * (entry - stop), 2), "risk": round(risk * 100, 1),
        "ext": round((c[t] / entry - 1) * 100, 1),
        "notes": notes,
        "lines": {"low": round(b["low"], 2), "zone": round(b["zone"], 2), "support": round(b["support"], 2),
                  "pivot": round(b["pivot"], 2)},
        "touches": [int(t - i) for i in b["touches"]],
        "span": [int(t - b["start"]), int(t - end)],
    }
