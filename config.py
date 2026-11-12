"""All tunable scan rules live here. Edit and re-run `python scan.py`."""

# ---- Universe scanned each night (wider than the dashboard defaults, so the
# ---- filters in the dashboard can be loosened without a rescan)
UNIVERSE_MIN_PRICE = 3.0
UNIVERSE_MIN_AVG_VOLUME = 500_000      # shares, 10-day average
HISTORY_PERIOD = "2y"
MIN_BARS = 250                         # skip recent IPOs

# ---- Values precomputed for the dashboard's adjustable filters
MA_PERIODS = [5, 10, 20, 50, 100, 150, 200]
VOLUME_PERIODS = [5, 10, 20, 50]

# ---- Pullback in uptrend
PB_HIGH_LOOKBACK = 60        # the swing high must be the highest high of this many bars
PB_MIN_DAYS = 2              # bars since the swing high
PB_MAX_DAYS = 10
PB_MIN_DEPTH = 0.03          # high -> pullback low
PB_MAX_DEPTH = 0.15
PB_MA_TOLERANCE = 0.02       # pullback low must come within 2% of the 10/20/50 EMA
PB_HOLD_BARS = 20            # every close in this many recent bars must be at or above the 50 EMA
PB_MIN_PRIOR_ADVANCE = 0.15  # rise into the swing high over the 60 bars before it

# ---- Flat base
FB_MIN_LEN = 20              # 4 weeks
FB_MAX_LEN = 65              # 13 weeks
FB_MAX_DEPTH = 0.15          # for quiet stocks; volatile stocks get up to 4 x ATR...
FB_MAX_DEPTH_CAP = 0.25      # ...but never deeper than this
FB_PRIOR_LOOKBACK = 120      # bars before the base used to measure the prior advance
FB_MIN_PRIOR_ADVANCE = 0.10
FB_TOUCH_ATR = 0.5           # a touch must peak within this many ATRs of the base high (same level, scaled to the stock's volatility)
FB_ZONE_MIN = 0.005          # ...but never tighter than 0.5%
FB_ZONE_MAX = 0.02           # ...or looser than 2%
FB_MIN_TOUCHES = 2           # separate rallies into the resistance zone
FB_TOUCH_GAP = 4             # bars out of the zone before the next rally counts as a new touch
FB_MIN_RESISTANCE_BARS = 10  # first touch to last touch must span at least this many bars
FB_MAX_DRIFT = 0.05          # average close of the last third vs the first third: the base must be sideways
FB_MIN_PCT_ABOVE_EMA50 = 0.70  # share of base closes at or above the 50 EMA
FB_BUY_RANGE = 0.05          # up to 5% above the pivot
FB_BREAKOUT_LOOKBACK = 10    # keep showing breakouts this many bars back
FB_MAX_STOP = 0.07           # stop no further than 7% below entry

# ---- Trade levels
TARGET_R = 2.0               # target = entry + 2 x risk
CHART_BARS = 320             # bars shipped to the dashboard per candidate
