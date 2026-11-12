"""All tunable scan rules live here. Edit and re-run `python scan.py`.

Two kinds of rule, kept strictly apart:

* PATTERN rules say what the setup *is*. Without them there is no swing high,
  no resistance zone, no entry or stop to compute, so a stock that fails one is
  simply not that setup.
* SCORE rules say how *good* the setup is. They only raise or lower the score.
  They never remove a stock; screening out is the job of the dashboard filters
  (dollar volume, price, moving-average rules, minimum score).
"""

# ---- Universe scanned each night (wider than the dashboard defaults, so the
# ---- filters in the dashboard can be loosened without a rescan)
UNIVERSE_MIN_PRICE = 3.0
UNIVERSE_MIN_DOLLAR_VOLUME = 10_000_000  # price x shares, 20-day average
HISTORY_PERIOD = "2y"
MIN_BARS = 250                         # skip recent IPOs

# ---- Values precomputed for the dashboard's adjustable filters
MA_PERIODS = [5, 10, 20, 50, 100, 150, 200]
VOLUME_PERIODS = [5, 10, 20, 50]
RETURN_PERIODS = [20, 60, 90]          # trading days, shown as % change columns

# ---- Pullback: PATTERN rules
PB_MIN_DAYS = 2              # bars since the swing high
PB_MAX_DAYS = 10             # the swing high is the highest high of this many recent bars
PB_MIN_DEPTH = 0.03          # high -> pullback low; less than this is not a pullback
PB_MAX_DEPTH_CAP = 0.25      # more than this is a breakdown, not a pullback

# ---- Pullback: SCORE rules (never screen out)
PB_HIGH_LOOKBACK = 60        # points if the swing high was the highest high of this many bars
PB_MIN_PRIOR_ADVANCE = 0.15  # full points for this rise into the swing high over those bars
PB_HOLD_BARS = 20            # points for closes holding the 50 EMA over this many recent bars
PB_MA_TOLERANCE = 0.02       # points if the pullback low came within 2% of the 10/20/50 EMA
PB_IDEAL_DEPTH = 0.07        # full depth points here, none at PB_DEEP
PB_DEEP = 0.15

# ---- Flat base: PATTERN rules
FB_MIN_LEN = 20              # 4 weeks, measured from the first touch of resistance
FB_MAX_LEN = 65              # 13 weeks
FB_MAX_DEPTH_CAP = 0.25      # deeper than this is not a base
FB_TOUCH_ATR = 0.5           # a touch must peak within this many ATRs of the base high (same level, scaled to volatility)
FB_ZONE_MIN = 0.005          # ...but the zone is never tighter than 0.5%
FB_ZONE_MAX = 0.02           # ...or looser than 2%
FB_MIN_TOUCHES = 2           # separate rallies into the resistance zone
FB_TOUCH_GAP = 4             # bars out of the zone before the next rally counts as a new touch
FB_MIN_RESISTANCE_BARS = 10  # first touch to last touch must span at least this many bars
FB_BUY_RANGE = 0.05          # up to 5% above the pivot counts as "in buy range"
FB_BREAKOUT_LOOKBACK = 10    # keep showing breakouts this many bars back
FB_MAX_STOP = 0.07           # stop no further than 7% below entry

# ---- Flat base: SCORE rules (never screen out)
FB_TIGHT = 0.05              # full tightness points at this depth, none at FB_MAX_DEPTH_CAP
FB_PRIOR_LOOKBACK = 120      # bars before the base used to measure the prior advance
FB_MIN_PRIOR_ADVANCE = 0.20  # full points for this advance into the base
FB_MAX_DRIFT = 0.10          # no sideways points once the last third drifts this far from the first third
FB_PCT_ABOVE_EMA50 = 0.90    # full points when this share of base closes is at or above the 50 EMA

# ---- Trade levels
TARGET_R = 2.0               # target = entry + 2 x risk
CHART_BARS = 320             # bars shipped to the dashboard per candidate
