"""All tunable scan rules live here. Edit and re-run `python scan.py`.

Every stock in the scan universe is listed. The base rules below only measure
and score; they never remove a stock. Screening out is done only by the
dashboard filters (dollar and share volume, price, moving-average rules,
RS Rating, minimum score, earnings).
"""

# ---- Universe scanned each night (wider than the dashboard defaults, so the
# ---- filters in the dashboard can be loosened without a rescan)
UNIVERSE_MIN_PRICE = 3.0
UNIVERSE_MIN_DOLLAR_VOLUME = 10_000_000  # price x shares, 20-day average
HISTORY_PERIOD = "2y"
MIN_BARS = 253                         # a full year plus one bar, needed for the RS Rating

# ---- Values precomputed for the dashboard's adjustable filters
MA_PERIODS = [5, 10, 20, 50, 100, 150, 200]
VOLUME_PERIODS = [5, 10, 20, 50]
RETURN_PERIODS = [20, 60, 90]          # trading days, shown as % change columns

# ---- RS Rating (1-99): weighted 12-month performance ranked against the whole scan.
# Each quarter is 63 trading days; the most recent quarter counts double.
RS_QUARTER = 63
RS_WEIGHTS = [0.4, 0.2, 0.2, 0.2]      # last 3 months, 3-6, 6-9, 9-12 months ago

# ---- Flat base: how the base is measured
FB_MIN_LEN = 20              # 4 weeks, measured from the first touch of resistance
FB_MAX_LEN = 65              # 13 weeks
FB_MAX_DEPTH_CAP = 0.25      # no tightness points at this depth or deeper
FB_TOUCH_ATR = 0.5           # a touch must peak within this many ATRs of the base high (same level, scaled to volatility)
FB_ZONE_MIN = 0.005          # ...but the zone is never tighter than 0.5%
FB_ZONE_MAX = 0.02           # ...or looser than 2%
FB_MIN_TOUCHES = 2           # touches needed before a move above the base high counts as a breakout
FB_TOUCH_GAP = 4             # bars out of the zone before the next rally counts as a new touch
FB_MIN_RESISTANCE_BARS = 10  # touches closer together than this count as one
FB_BUY_RANGE = 0.05          # up to 5% above the pivot counts as "in buy range"
FB_BREAKOUT_LOOKBACK = 10    # keep showing breakouts this many bars back
FB_MAX_STOP = 0.07           # stop no further than 7% below entry

# ---- Flat base: score settings
FB_TIGHT = 0.05              # full tightness points at this depth, none at FB_MAX_DEPTH_CAP
FB_PRIOR_LOOKBACK = 120      # bars before the base used to measure the prior advance
FB_MIN_PRIOR_ADVANCE = 0.20  # full points for this advance into the base
FB_MAX_DRIFT = 0.10          # no sideways points once the last third drifts this far from the first third
FB_PCT_ABOVE_EMA50 = 0.90    # full points when this share of base closes is at or above the 50 EMA

# ---- Trade levels
TARGET_R = 2.0               # target = entry + 2 x risk
CHART_BARS = 320             # bars shipped to the dashboard per candidate
