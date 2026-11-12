"""Setup detectors. Each works on numpy arrays and an end index `t`, so the same
code can later be replayed over history for backtesting."""
import numpy as np

import config as C


def _clip01(x):
    return float(max(0.0, min(1.0, x)))


# --------------------------------------------------------------------------- pullback
def pullback_at(a, t):
    """Is there a valid pullback-in-uptrend as of bar t? Returns dict or None."""
    h, l, c, v = a["h"], a["l"], a["c"], a["v"]
    if t < C.PB_HIGH_LOOKBACK + 70:
        return None
    w0 = t - C.PB_MAX_DAYS
    hi_i = w0 + int(np.argmax(h[w0 : t + 1]))
    days = t - hi_i
    if days < C.PB_MIN_DAYS:
        return None
    H = h[hi_i]
    if H < h[hi_i - C.PB_HIGH_LOOKBACK : hi_i].max():
        return None  # swing high was not a fresh 60-bar high
    prior_low = l[hi_i - C.PB_HIGH_LOOKBACK : hi_i].min()
    if H / prior_low - 1 < C.PB_MIN_PRIOR_ADVANCE:
        return None
    lo_i = hi_i + 1 + int(np.argmin(l[hi_i + 1 : t + 1]))
    L = l[lo_i]
    depth = (H - L) / H
    if not (C.PB_MIN_DEPTH <= depth <= C.PB_MAX_DEPTH):
        return None
    e50 = a["ema50"][t]
    if e50 <= a["ema50"][t - 20]:
        return None  # the 50 EMA is not rising
    # Recent closes (the pullback and the bars before it) must hold at or above the 50 EMA;
    # holding the 20 EMA through the pullback is better.
    pb = slice(hi_i + 1, t + 1)
    recent = slice(min(hi_i + 1, t + 1 - C.PB_HOLD_BARS), t + 1)
    if (c[recent] < a["ema50"][recent]).any():
        return None
    if c[pb].min() >= c[hi_i]:
        return None  # no close below the swing-high day's close: price has not actually pulled back
    held = "20 EMA" if (c[pb] >= a["ema20"][pb]).all() else "50 EMA"
    # which moving average did the pullback low reach?
    best = None
    for name, arr in (("10 EMA", a["ema10"]), ("20 EMA", a["ema20"]), ("50 EMA", a["ema50"])):
        ma = arr[lo_i]
        dist = (L - ma) / ma
        if -C.PB_MA_TOLERANCE * 1.5 <= dist <= C.PB_MA_TOLERANCE:
            if best is None or abs(dist) < abs(best[1]):
                best = (name, dist)
    if best is None:
        return None
    pb_vol = v[hi_i + 1 : t + 1].mean()
    vol_ratio = pb_vol / a["vol50"][t] if a["vol50"][t] > 0 else 1.0
    return {"hi_i": hi_i, "lo_i": lo_i, "high": float(H), "low": float(L), "depth": float(depth),
            "days": int(days), "held": held, "ma": best[0], "ma_dist": float(best[1]), "vol_ratio": float(vol_ratio)}


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
    if risk <= 0.005 or risk > 0.12:
        return None
    # Volume is shown in the details but deliberately not scored.
    score = 100 * (0.40 * _clip01(rs / 100)
                   + 0.25 * (1.0 if p["held"] == "20 EMA" else 0.4)      # closes held the 20 EMA / only the 50 EMA
                   + 0.20 * _clip01(1 - abs(p["ma_dist"]) / 0.03)       # clean tag of the MA
                   + 0.15 * _clip01(1 - abs(p["depth"] - 0.07) / 0.08))  # moderate depth
    return {
        "type": "pullback", "status": status, "score": round(score),
        "entry": round(entry, 2), "stop": round(stop, 2),
        "target": round(entry + C.TARGET_R * (entry - stop), 2), "risk": round(risk * 100, 1),
        "ext": round((c[t] / entry - 1) * 100, 1),
        "notes": {"Swing high": round(p["high"], 2), "Pullback low": round(low, 2),
                  "Depth": f"{p['depth'] * 100:.1f}%", "Days from high": p["days"],
                  "Closes held above": p["held"], "Low reached": p["ma"], "Pullback volume": f"{p['vol_ratio']:.2f}x avg"},
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
    """Longest valid flat base ending at bar t. Returns dict or None."""
    h, l, c = a["h"], a["l"], a["c"]
    if t < C.FB_MAX_LEN + C.FB_PRIOR_LOOKBACK + 50:
        return None
    max_depth = min(C.FB_MAX_DEPTH_CAP, max(C.FB_MAX_DEPTH, 4 * a["atr"][t] / c[t]))
    windows = []
    for n in range(C.FB_MIN_LEN, C.FB_MAX_LEN + 1):
        s = t - n + 1
        hi, lo = h[s : t + 1].max(), l[s : t + 1].min()
        if (hi - lo) / hi > max_depth:
            break  # longer windows only get deeper
        windows.append((n, s, hi, lo))
    zone_w = min(C.FB_ZONE_MAX, max(C.FB_ZONE_MIN, C.FB_TOUCH_ATR * a["atr"][t] / c[t]))
    for n, s, hi, lo in reversed(windows):  # longest first
        hi_i = s + int(np.argmax(h[s : t + 1]))
        if hi_i == t:
            return None  # making the high today, no pivot yet
        floor = hi * (1 - zone_w)
        touches = _touches(h, s, t, floor)
        if len(touches) < C.FB_MIN_TOUCHES or touches[-1] - touches[0] < C.FB_MIN_RESISTANCE_BARS:
            continue  # no clear resistance across the top
        # The base starts at the first touch of resistance, so the run-up before it
        # does not count towards the base low, depth or length.
        s = touches[0]
        n = t - s + 1
        if n < C.FB_MIN_LEN:
            continue
        lo = l[s : t + 1].min()
        prior_low = l[s - C.FB_PRIOR_LOOKBACK : s].min()
        if hi / prior_low - 1 < C.FB_MIN_PRIOR_ADVANCE:
            continue
        if (c[s : t + 1] >= a["ema50"][s : t + 1]).mean() < C.FB_MIN_PCT_ABOVE_EMA50:
            continue
        if c[t] < lo + 0.5 * (hi - lo):
            continue  # sitting in the lower half of the base
        third = n // 3
        if abs(c[t - third + 1 : t + 1].mean() / c[s : s + third].mean() - 1) > C.FB_MAX_DRIFT:
            continue  # drifting up or down, not sideways
        dry = a["v"][t - 9 : t + 1].mean() / a["vol50"][t] if a["vol50"][t] > 0 else 1.0
        return {"len": int(n), "start": int(s), "pivot": float(hi), "low": float(lo),
                "depth": float((hi - lo) / hi), "advance": float(hi / prior_low - 1), "dry": float(dry),
                "zone": float(floor), "support": float(lo * (1 + zone_w)), "touches": touches}
    return None


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
    # Volume is shown in the details but deliberately not scored.
    nt = len(b["touches"])
    score = 100 * (0.30 * _clip01(rs / 100)
                   + 0.30 * _clip01((0.16 - b["depth"]) / 0.11)   # tighter is better
                   + 0.20 * _clip01((nt - 1) / 3)                 # 2 touches = 1/3, 4+ = full
                   + 0.10 * _clip01(b["len"] / 45)
                   + 0.10 * _clip01(1 - abs(c[t] / entry - 1) / 0.08))
    notes = {"Pivot (base high)": round(b["pivot"], 2), "Base low": round(b["low"], 2),
             "Resistance touches": nt,
             "Resistance zone": f"{b['zone']:.2f} - {b['pivot']:.2f}",
             "Support zone": f"{b['low']:.2f} - {b['support']:.2f}",
             "Base depth": f"{b['depth'] * 100:.1f}%", "Base length": f"{b['len'] / 5:.0f} weeks",
             "Prior advance": f"{b['advance'] * 100:.0f}%", "Recent volume": f"{b['dry']:.2f}x avg"}
    if bo_vol is not None:
        notes["Breakout volume"] = f"{bo_vol:.1f}x avg"
        notes["Breakout"] = "today" if days_since == 0 else f"{days_since} bars ago"
    return {
        "type": "flatbase", "status": status, "score": round(score),
        "entry": round(entry, 2), "stop": round(stop, 2),
        "target": round(entry + C.TARGET_R * (entry - stop), 2), "risk": round(risk * 100, 1),
        "ext": round((c[t] / entry - 1) * 100, 1),
        "notes": notes,
        "lines": {"low": round(b["low"], 2), "zone": round(b["zone"], 2), "support": round(b["support"], 2),
                  "pivot": round(b["pivot"], 2)},
        "touches": [int(t - i) for i in b["touches"]],
        "span": [int(t - b["start"]), int(t - end)],
    }
