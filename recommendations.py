"""Rule-based study recommendations. Works fully offline, with no AI API.

An optional wording polish via an LLM exists but runs ONLY when explicitly
enabled with environment variables (see .env.example). It sends only the generic
suggestion text - never student names, IDs or marks - and silently falls back to
the original rule-based wording on any problem.
"""
import json
import os

import risk_engine as risk

REC_STATUSES = ["Suggested", "In progress", "Completed", "Dismissed"]


def _rec(key, action, reason, timeframe, goal):
    return {"key": key, "action": action, "reason": reason, "timeframe": timeframe,
            "goal": goal, "status": "Suggested"}


def generate_recommendations(student, screening, config=None):
    """Return a list of recommendation dicts for one student."""
    cfg = risk.merge_config(config)
    by_key = {i["key"]: i for i in screening["indicators"]}
    recs = []
    triggered = screening["triggered_keys"]

    if screening["category"] == risk.INSUFFICIENT:
        return [_rec("missing_data",
                     "Complete the missing academic records so support can be planned accurately.",
                     "Attendance, marks and assignment data are all unavailable.",
                     "1 week", "All three core metrics are recorded.")]

    if len(triggered) >= 2:
        recs.append(_rec(
            "check_in", "Arrange a faculty check-in and build an individualized support plan.",
            f"{len(triggered)} indicators are below guideline at the same time.",
            "This week", "Hold the check-in within 7 days and agree on 2-3 measurable targets."))

    if "score" in triggered:
        ind = by_key["score"]
        gap = ind["threshold"] - ind["value"]
        recs.append(_rec(
            "low_score",
            "Review the weakest topics, practise past questions, and ask faculty for help on difficult units.",
            ind["message"], "4 weeks",
            f"Reach at least {ind['threshold']:.0f}% in the next assessment (about +{gap:.1f} points)."))
    if "attendance" in triggered:
        ind = by_key["attendance"]
        recs.append(_rec(
            "low_attendance",
            "Talk through anything making it hard to attend and agree on a realistic weekly attendance plan.",
            ind["message"], "4 weeks",
            f"Attend at least {ind['threshold']:.0f}% of classes over the next 4 weeks."))
    if "assignment" in triggered:
        ind = by_key["assignment"]
        recs.append(_rec(
            "low_assignment",
            "Split pending assignments into smaller tasks with weekly milestones.",
            ind["message"], "3 weeks",
            f"Submit at least {ind['threshold']:.0f}% of assignments by their due dates."))
    if "decline" in triggered:
        ind = by_key["decline"]
        recs.append(_rec(
            "declining_trend",
            "Review recent topics and study habits with a mentor to find out what changed.",
            ind["message"], "3 weeks",
            "The next recorded score is at least equal to the most recent one."))

    # Only missing CORE metrics matter here; having no history is normal and not a data gap.
    missing_core = [i["label"] for i in screening["indicators"]
                    if i["key"] != "decline" and i["status"] == "Unavailable"]
    if missing_core:
        missing = ", ".join(missing_core)
        recs.append(_rec(
            "missing_data", "Fill in missing records so the picture is complete.",
            f"Not recorded: {missing}.", "2 weeks", "Missing metrics are recorded."))

    if not triggered:
        recs.append(_rec(
            "maintain", "Keep the current routine going and consider peer-mentoring or stretch goals.",
            "All available metrics are within guidelines.", "Ongoing",
            "Keep every metric at or above its guideline."))
    return recs


def llm_enabled():
    return os.environ.get("EDUPULSE_USE_LLM", "0") == "1" and bool(os.environ.get("ANTHROPIC_API_KEY"))


def enhance_wording(recs):
    """Optionally rewrite the action text in a warmer tone. Always safe to call."""
    if not recs or not llm_enabled():
        return recs
    try:
        import anthropic  # optional dependency

        client = anthropic.Anthropic()
        texts = [r["action"] for r in recs]
        prompt = (
            "Rewrite each study-support suggestion below in a warm, encouraging, non-punitive tone. "
            "Keep the meaning identical and keep each under 30 words. "
            "Return only a JSON list of strings in the same order.\n" + json.dumps(texts)
        )
        msg = client.messages.create(
            model=os.environ.get("EDUPULSE_LLM_MODEL", "claude-sonnet-5-5"),
            max_tokens=800, messages=[{"role": "user", "content": prompt}])
        out = json.loads(msg.content[0].text)
        if isinstance(out, list) and len(out) == len(recs) and all(isinstance(x, str) for x in out):
            return [{**r, "action": text} for r, text in zip(recs, out)]
    except Exception:  # noqa: BLE001 - any failure falls back to the rule-based text
        pass
    return recs
