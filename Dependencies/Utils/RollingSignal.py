from collections import defaultdict

# =========================================================
# ROLLING SIGNAL TRACKER
# Per-key history of the last N values with momentum analysis
# =========================================================

h = defaultdict(list)


def add_value(key, value):
    """
    Appends `value` to the rolling history for `key` and evaluates momentum.

    Returns
    -------
    signal   : bool   – True  if mean_diff >= 0.11 AND latest >= 0.70
    near     : bool   – True  if values are monotonically rising AND latest >= 0.65
    mean_diff: float  – average step-change over last 3 readings
    latest   : float  – most recent value
    history  : list   – full history snapshot for this key
    """
    h[key].append(value)
    history = h[key].copy()

    if len(h[key]) < 3:
        return False, False, 0.0, value, history

    last3 = h[key][-3:]
    diffs = [last3[1] - last3[0], last3[2] - last3[1]]
    mean_diff = round(sum(diffs) / len(diffs), 2)
    latest = last3[-1]

    # Trend checks
    n1   = last3[1] >= last3[0] and last3[2] >= last3[1]   # non-decreasing sequence
    n2   = last3[2] >= 0.65                                  # latest near threshold
    near = n1 and n2

    if latest >= 0.70:
        return True, near, mean_diff, latest, history
    else:
        return False, near, mean_diff, latest, history


def reset_history(key=None):
    """Clear history for a specific key, or all keys if None."""
    if key:
        h.pop(key, None)
    else:
        h.clear()
