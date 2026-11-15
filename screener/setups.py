"""Flat base detector. It works on numpy arrays and an end index `t`, so the same
code can later be replayed over history for backtesting.

Every stock in the scan is measured and scored. Nothing here removes a stock;
only the dashboard filters do. See config.py.
"""
import numpy as np

import config as C


def _clip01(x):
    return float(max(0.0, min(1.0, x)))


def _score(parts):
    """parts: [(label, fraction 0..1, max points)] -> (total, breakdown for the dashboard)."""
    rows = [[label, round(frac * pts), pts] for label, frac, pts in parts]
    return sum(r[1] for r in rows), rows


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


def _effective_touches(touches):
    """Touches only count as separate if they are spread out; bunched together they are one."""
    if len(touches) >= 2 and touches[-1] - touches[0] >= C.FB_MIN_RESISTANCE_BARS:
        return len(touches)
    return min(len(touches), 1)


def flat_base_at(a, t):
    """Measure the best base-like window ending at bar t. Always returns a measurement.

    Nothing here screens a stock out: a stock with no real base still gets its best
    window measured, and simply scores low. Windows of FB_MIN_LEN to FB_MAX_LEN bars are
    tried and the one with the highest base quality is kept."""
    h, l, c = a["h"], a["l"], a["c"]
    zone_w = min(C.FB_ZONE_MAX, max(C.FB_ZONE_MIN, C.FB_TOUCH_ATR * a["atr"][t] / c[t]))
    best, seen = None, set()
    for n in range(C.FB_MAX_LEN, C.FB_MIN_LEN - 1, -1):  # longest first
        s = t - n + 1
        hi = h[s : t + 1].max()
        floor = hi * (1 - zone_w)
        touches = _touches(h, s, t, floor)
        nt = _effective_touches(touches)
        # With real resistance the base starts at the first touch, so the run-up
        # before it does not count towards the base low, depth or length.
        if nt >= 2 and t - touches[0] + 1 >= C.FB_MIN_LEN:
            s = touches[0]
        if (s, hi) in seen:
            continue
        seen.add((s, hi))
        n = t - s + 1
        lo = l[s : t + 1].min()
        depth = (hi - lo) / hi
        advance = float(hi / l[max(0, s - C.FB_PRIOR_LOOKBACK) : s].min() - 1)
        above50 = float((c[s : t + 1] >= a["ema50"][s : t + 1]).mean())
        third = n // 3
        drift = float(c[t - third + 1 : t + 1].mean() / c[s : s + third].mean() - 1)
        q = {"tight": _clip01((C.FB_MAX_DEPTH_CAP - depth) / (C.FB_MAX_DEPTH_CAP - C.FB_TIGHT)),
             "touch": _clip01((nt - 1) / 3),                      # 1 touch = 0, 2 = 1/3, 4+ = full
             "above": _clip01((above50 - 0.4) / (C.FB_PCT_ABOVE_EMA50 - 0.4)),
             "side": _clip01(1 - abs(drift) / C.FB_MAX_DRIFT),
             "adv": _clip01(advance / C.FB_MIN_PRIOR_ADVANCE),
             "near": _clip01(1 - abs(c[t] / hi - 1) / 0.08)}
        quality = (25 * q["tight"] + 20 * q["touch"] + 10 * q["above"] + 10 * q["side"]
                   + 10 * q["near"] + 5 * q["adv"])
        if best is None or quality > best["quality"]:
            dry = a["v"][t - 9 : t + 1].mean() / a["vol50"][t] if a["vol50"][t] > 0 else 1.0
            best = {"len": int(n), "start": int(s), "pivot": float(hi), "low": float(lo), "depth": float(depth),
                    "advance": advance, "above50": above50, "drift": drift, "dry": float(dry),
                    "zone": float(floor), "support": float(lo * (1 + zone_w)), "touches": touches,
                    "nt": nt, "q": q, "quality": quality}
    return best


def detect_flat_base(a, rs):
    t = len(a["c"]) - 1
    c, v = a["c"], a["v"]
    found = None
    for k in range(1, C.FB_BREAKOUT_LOOKBACK + 1):  # did it break out in the last k bars?
        b = flat_base_at(a, t - k)
        if b["nt"] < C.FB_MIN_TOUCHES or c[t - k] > b["pivot"]:
            continue  # a breakout needs resistance to break through
        after = np.nonzero(c[t - k + 1 : t + 1] > b["pivot"])[0]
        if not len(after):
            continue
        bo = t - k + 1 + int(after[0])
        if c[t] < b["pivot"]:
            continue  # broke out and fell back: measure the base as it stands today instead
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
        found = (flat_base_at(a, t), "setup", None, None, t)
    b, status, days_since, bo_vol, end = found
    entry = b["pivot"] * 1.001
    stop = max(b["low"] * 0.995, entry * (1 - C.FB_MAX_STOP))
    risk = (entry - stop) / entry
    nt, q = b["nt"], b["q"]
    # Volume is shown in the details but deliberately not scored.
    score, parts = _score([
        ("Tight base", q["tight"], 25),
        ("Relative strength", _clip01(rs / 100), 20),
        ("Touches of resistance", q["touch"], 20),
        ("Closes above the 50 EMA", q["above"], 10),
        ("Sideways, not drifting", q["side"], 10),
        ("Price near the base high", q["near"], 10),
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
