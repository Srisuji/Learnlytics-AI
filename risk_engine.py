"""Transparent, configurable rule-based support screening.

HOW THE SCREENING SCORE WORKS (defaults - all configurable in Settings):
  Each indicator that is triggered adds its weight to the score (max 100):
      Attendance below 75%                     +30
      Academic score below 50%                 +35
      Assignment completion below 60%          +20
      Score dropped by 10+ points over history +15   (needs 3+ history records)
  Categories:   0-24 Low | 25-49 Medium | 50-74 High | 75-100 Critical
  Rules of fairness:
      * A missing value is "Unavailable" - it is NEVER counted as a failure.
      * Trend indicators are skipped when there is not enough real history.
      * If all three core metrics are missing the result is "Insufficient data".
      * No sensitive attributes (gender, religion, caste, etc.) are used.
  The result is a support-screening aid for human review, NOT a prediction.
"""
import math

DEFAULT_CONFIG = {
    "attendance_threshold": 75.0,
    "score_threshold": 50.0,
    "assignment_threshold": 60.0,
    "attendance_weight": 30,
    "score_weight": 35,
    "assignment_weight": 20,
    "decline_weight": 15,
    "decline_points": 10.0,
    "min_history": 3,
    "medium_min": 25,
    "high_min": 50,
    "critical_min": 75,
}

CATEGORIES = ["Low", "Medium", "High", "Critical"]
INSUFFICIENT = "Insufficient data"
ALL_CATEGORIES = CATEGORIES + [INSUFFICIENT]

DISCLAIMER = (
    "This is a support-screening indicator based on simple, documented rules. It is not a prediction "
    "of outcomes. Faculty should review each flag and use professional judgment."
)

FACULTY_ACTIONS = {
    "attendance": "Have a supportive conversation about any barriers to attending and agree on a realistic attendance plan.",
    "score": "Identify which topics are difficult and arrange extra practice, tutoring, or a doubt-clearing session.",
    "assignment": "Break upcoming work into smaller milestones and check in on progress each week.",
    "decline": "Explore what changed recently (workload, understanding, circumstances) and discuss it with the student.",
}
MULTI_ACTION = "Schedule a faculty check-in to build an individual support plan with 2-3 measurable targets."

_CORE = [
    ("attendance", "Attendance", "attendance_rate", "attendance_threshold", "attendance_weight"),
    ("score", "Academic score", "academic_score", "score_threshold", "score_weight"),
    ("assignment", "Assignment completion", "assignment_rate", "assignment_threshold", "assignment_weight"),
]


def is_missing(value):
    """True for None, NaN and pandas NA."""
    if value is None:
        return True
    try:
        return bool(value != value)
    except TypeError:
        return True


def merge_config(config=None):
    """Defaults overridden by any valid values in `config`."""
    cfg = dict(DEFAULT_CONFIG)
    for key, default in DEFAULT_CONFIG.items():
        if config and config.get(key) is not None:
            try:
                number = float(config[key])
                cfg[key] = int(number) if isinstance(default, int) else number
            except (TypeError, ValueError):
                pass
    return cfg


def validate_config(config):
    """Return a list of human-readable problems (empty list = valid)."""
    cfg = merge_config(config)
    errors = []
    for key in ("attendance_threshold", "score_threshold", "assignment_threshold"):
        if not 0 <= cfg[key] <= 100:
            errors.append(f"{key.replace('_', ' ')} must be between 0 and 100.")
    for key in ("attendance_weight", "score_weight", "assignment_weight", "decline_weight"):
        if not 0 <= cfg[key] <= 100:
            errors.append(f"{key.replace('_', ' ')} must be between 0 and 100.")
    if cfg["decline_points"] <= 0:
        errors.append("decline points must be greater than 0.")
    if cfg["min_history"] < 2:
        errors.append("minimum history records must be at least 2.")
    if not 0 < cfg["medium_min"] < cfg["high_min"] < cfg["critical_min"] <= 100:
        errors.append("category boundaries must satisfy 0 < medium < high < critical <= 100.")
    return errors


def category_for_score(score, config=None):
    cfg = merge_config(config)
    if score >= cfg["critical_min"]:
        return "Critical"
    if score >= cfg["high_min"]:
        return "High"
    if score >= cfg["medium_min"]:
        return "Medium"
    return "Low"


def _history_decline(history, cfg):
    """Return (drop in score from first to last record, or None if not enough history)."""
    points = []
    for rec in history or []:
        score = rec.get("academic_score")
        if not is_missing(score):
            points.append((str(rec.get("week_date", "")), float(score)))
    if len(points) < cfg["min_history"]:
        return None
    points.sort(key=lambda p: p[0])
    return points[0][1] - points[-1][1]


def screen_student(student, history=None, config=None):
    """Screen one student. `student` is a dict; `history` a list of dicts (optional).

    Returns a dict with: score, category, indicators, reasons, unavailable,
    faculty_actions, disclaimer.
    """
    cfg = merge_config(config)
    indicators = []
    available_core = 0

    for key, label, field, thr_key, w_key in _CORE:
        value = student.get(field)
        thr, weight = cfg[thr_key], cfg[w_key]
        if is_missing(value):
            indicators.append({
                "key": key, "label": label, "value": None, "threshold": thr, "weight": weight,
                "status": "Unavailable", "triggered": False,
                "message": f"{label} is not recorded, so it was not counted.",
            })
            continue
        available_core += 1
        value = float(value)
        triggered = value < thr
        indicators.append({
            "key": key, "label": label, "value": value, "threshold": thr, "weight": weight,
            "status": "Below guideline" if triggered else "Within guideline", "triggered": triggered,
            "message": (f"{label} is {value:.1f}%, below the {thr:.0f}% guideline." if triggered
                        else f"{label} is {value:.1f}%, within the {thr:.0f}% guideline."),
        })

    drop = _history_decline(history, cfg)
    if drop is None:
        indicators.append({
            "key": "decline", "label": "Score trend", "value": None, "threshold": cfg["decline_points"],
            "weight": cfg["decline_weight"], "status": "Unavailable", "triggered": False,
            "message": f"Fewer than {cfg['min_history']} history records, so no trend was assessed.",
        })
    else:
        triggered = drop >= cfg["decline_points"]
        indicators.append({
            "key": "decline", "label": "Score trend", "value": drop, "threshold": cfg["decline_points"],
            "weight": cfg["decline_weight"], "status": "Declining" if triggered else "Stable or improving",
            "triggered": triggered,
            "message": (f"Academic score fell by {drop:.1f} points across the recorded history."
                        if triggered else "No meaningful decline in the recorded history."),
        })

    triggered_inds = [i for i in indicators if i["triggered"]]
    score = min(100, sum(i["weight"] for i in triggered_inds))
    category = INSUFFICIENT if available_core == 0 else category_for_score(score, cfg)

    actions = [FACULTY_ACTIONS[i["key"]] for i in triggered_inds]
    if len(triggered_inds) >= 2:
        actions.append(MULTI_ACTION)
    if not actions and category == "Low":
        actions.append("No extra action needed; continue routine encouragement.")
    if category == INSUFFICIENT:
        actions = ["Complete the missing records so support can be planned accurately."]

    return {
        "score": int(score) if category != INSUFFICIENT else 0,
        "category": category,
        "indicators": indicators,
        "triggered_keys": [i["key"] for i in triggered_inds],
        "reasons": [i["message"] for i in triggered_inds],
        "unavailable": [i["label"] for i in indicators if i["status"] == "Unavailable"],
        "faculty_actions": actions,
        "disclaimer": DISCLAIMER,
    }


def describe_scoring(config=None):
    """Plain-language description of the current formula (shown in Settings and README)."""
    c = merge_config(config)
    return [
        f"Attendance below {c['attendance_threshold']:.0f}%  ->  +{c['attendance_weight']} points",
        f"Academic score below {c['score_threshold']:.0f}%  ->  +{c['score_weight']} points",
        f"Assignment completion below {c['assignment_threshold']:.0f}%  ->  +{c['assignment_weight']} points",
        (f"Score drop of {c['decline_points']:.0f}+ points over at least {c['min_history']} history records"
         f"  ->  +{c['decline_weight']} points"),
        (f"Categories: Low 0-{c['medium_min'] - 1}, Medium {c['medium_min']}-{c['high_min'] - 1}, "
         f"High {c['high_min']}-{c['critical_min'] - 1}, Critical {c['critical_min']}-100"),
        "Missing values are never counted as failures; they are shown as 'Unavailable'.",
    ]
