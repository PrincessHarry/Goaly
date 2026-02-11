from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .observability import opik_span, opik_trace
from .openrouter import OpenRouterConfig, chat_completion, require_openrouter_api_key


# -----------------------------
# Utilities
# -----------------------------


_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _best_effort_json_loads(text: str) -> dict:
    """
    OpenRouter models are usually well-behaved but can still wrap JSON in prose.
    This function tries to recover the first JSON object found.
    """
    text = (text or "").strip()
    if not text:
        return {}
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _require_keys(obj: dict, keys: Iterable[str]) -> bool:
    return all(k in obj for k in keys)


def image_file_to_data_url(image_file) -> str:
    """
    Takes a Django UploadedFile and returns a data URL usable by OpenAI-compatible vision.
    """
    raw = image_file.read()
    mime = getattr(image_file, "content_type", None) or "image/jpeg"
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


# -----------------------------
# Public service APIs
# -----------------------------


@dataclass(frozen=True)
class EvidenceVerificationResult:
    verified: bool
    feedback: str


def verify_goal_evidence(
    *,
    goal_text: str,
    image_data_url: str,
) -> EvidenceVerificationResult:
    """
    Multimodal evidence verification using OpenRouter.
    Returns a strict, structured result.
    """
    require_openrouter_api_key()
    cfg = OpenRouterConfig()

    with opik_trace(
        "verify_goal_evidence",
        metadata={"model": cfg.model_vision},
    ):
        with opik_span("prompt_and_call"):
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an achievement verification agent for a goal-tracking app.\n"
                        "Be reasonably strict but encouraging.\n"
                        "Return ONLY valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f'The user claims they completed the goal: "{goal_text}".\n'
                                "Analyze the provided image. Does it plausibly show evidence?\n\n"
                                "Respond in JSON with:\n"
                                '  - "verified": boolean\n'
                                '  - "feedback": short 10-15 word explanation\n'
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                },
            ]

            text = chat_completion(
                model=cfg.model_vision,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=250,
            )

        with opik_span("parse_and_validate"):
            obj = _best_effort_json_loads(text)
            if not _require_keys(obj, ["verified", "feedback"]):
                return EvidenceVerificationResult(
                    verified=False,
                    feedback="Could not confidently verify evidence from the provided image.",
                )
            verified = bool(obj.get("verified"))
            feedback = str(obj.get("feedback") or "").strip()[:300]
            if not feedback:
                feedback = "Could not determine clear evidence; try a clearer photo."
            return EvidenceVerificationResult(verified=verified, feedback=feedback)


def get_ai_coaching(
    *,
    pending_goals: List[Dict[str, str]],
) -> str:
    """
    Returns a short coaching message (2 high-impact tips).
    """
    require_openrouter_api_key()
    cfg = OpenRouterConfig()

    goals_block = "\n".join([f'- [{g.get("timeframe")}] {g.get("text")}' for g in pending_goals]) or "Clear board."

    with opik_trace("get_ai_coaching", metadata={"model": cfg.model_text}):
        prompt = (
            "You are Goaly AI coach.\n"
            "Given the user's pending goals, provide 2 specific high-impact tips.\n"
            "Keep it concise, actionable, and not generic.\n\n"
            f"Pending goals:\n{goals_block}"
        )
        with opik_span("call"):
            return chat_completion(
                model=cfg.model_text,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=250,
            ) or "Pick one goal and do a 12-minute start right now."


def decompose_yearly_goal(
    *,
    yearly_goal_text: str,
) -> Dict[str, List[str]]:
    require_openrouter_api_key()
    cfg = OpenRouterConfig()

    with opik_trace("decompose_yearly_goal", metadata={"model": cfg.model_text}):
        messages = [
            {
                "role": "system",
                "content": "Return ONLY valid JSON. Be concrete and measurable where possible.",
            },
            {
                "role": "user",
                "content": (
                    f'Decompose this yearly goal: "{yearly_goal_text}"\n'
                    "into exactly:\n"
                    "- 3 daily sub-goals\n"
                    "- 2 weekly sub-goals\n"
                    "- 1 monthly sub-goal\n\n"
                    'Return JSON: {"daily":[...], "weekly":[...], "monthly":[...]}'
                ),
            },
        ]

        with opik_span("call"):
            text = chat_completion(
                model=cfg.model_text,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.5,
                max_tokens=400,
            )

        obj = _best_effort_json_loads(text)
        out = {
            "daily": list(map(str, obj.get("daily", []) or []))[:3],
            "weekly": list(map(str, obj.get("weekly", []) or []))[:2],
            "monthly": list(map(str, obj.get("monthly", []) or []))[:1],
        }
        # Ensure list types even if model misbehaves.
        for k in ["daily", "weekly", "monthly"]:
            out[k] = [s.strip() for s in out[k] if isinstance(s, str) and s.strip()]
        return out


def refine_goal(
    *,
    goal_text: str,
    timeframe: str,
) -> List[str]:
    """
    Refines a goal into 3 sub-goals (structured).
    """
    require_openrouter_api_key()
    cfg = OpenRouterConfig()

    with opik_trace("refine_goal", metadata={"model": cfg.model_text, "timeframe": timeframe}):
        messages = [
            {
                "role": "system",
                "content": "Return ONLY valid JSON. Make sub-goals specific and actionable.",
            },
            {
                "role": "user",
                "content": (
                    f'Refine this {timeframe} goal: "{goal_text}"\n'
                    "into exactly 3 sub-goals.\n"
                    'Return JSON: {"subgoals":[...]}'
                ),
            },
        ]

        with opik_span("call"):
            text = chat_completion(
                model=cfg.model_text,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.5,
                max_tokens=300,
            )

        obj = _best_effort_json_loads(text)
        subgoals = obj.get("subgoals", []) or []
        if not isinstance(subgoals, list):
            subgoals = []
        out = [str(s).strip() for s in subgoals if str(s).strip()]
        return out[:3]


def get_goal_tips(
    *,
    goal_text: str,
    timeframe: str,
) -> List[str]:
    """
    Returns 3 specific tips, max ~15 words each (structured).
    """
    require_openrouter_api_key()
    cfg = OpenRouterConfig()

    with opik_trace("get_goal_tips", metadata={"model": cfg.model_text, "timeframe": timeframe}):
        messages = [
            {
                "role": "system",
                "content": "Return ONLY valid JSON. Tips must be specific, not generic.",
            },
            {
                "role": "user",
                "content": (
                    f'Give 3 specific tips for this {timeframe} goal: "{goal_text}".\n'
                    "Each tip: max 15 words.\n"
                    'Return JSON: {"tips":[...]}'
                ),
            },
        ]

        with opik_span("call"):
            text = chat_completion(
                model=cfg.model_text,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.6,
                max_tokens=250,
            )

        obj = _best_effort_json_loads(text)
        tips = obj.get("tips", []) or []
        if not isinstance(tips, list):
            tips = []
        out = [str(t).strip() for t in tips if str(t).strip()]
        return out[:3] or ["Break it down", "Schedule time", "Track progress"]


def plan_yearly_goals(
    *,
    yearly_visions: str,
) -> Dict[str, List[str]]:
    """
    Plans goals for visions: 3 per timeframe (daily/weekly/monthly/yearly).
    Structured JSON output.
    """
    require_openrouter_api_key()
    cfg = OpenRouterConfig()

    with opik_trace("plan_yearly_goals", metadata={"model": cfg.model_text}):
        messages = [
            {
                "role": "system",
                "content": (
                    "Return ONLY valid JSON.\n"
                    "Goals must be concrete, non-overlapping, and aligned to the vision.\n"
                    "Prefer outcomes + habits."
                ),
            },
            {
                "role": "user",
                "content": (
                    f'Plan goals for these visions: "{yearly_visions}"\n'
                    "Return exactly 3 per timeframe.\n"
                    'Return JSON: {"daily":[...],"weekly":[...],"monthly":[...],"yearly":[...]}'
                ),
            },
        ]

        with opik_span("call"):
            text = chat_completion(
                model=cfg.model_text,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.6,
                max_tokens=650,
            )

        obj = _best_effort_json_loads(text)
        out = {
            "daily": obj.get("daily", []) or [],
            "weekly": obj.get("weekly", []) or [],
            "monthly": obj.get("monthly", []) or [],
            "yearly": obj.get("yearly", []) or [],
        }
        for k in out:
            if not isinstance(out[k], list):
                out[k] = []
            out[k] = [str(s).strip() for s in out[k] if str(s).strip()][:3]
        return out


def generate_yearly_report(
    *,
    completed_goals: List[str],
    failed_lessons: List[str],
) -> str:
    """
    Generates a narrative yearly summary (free text).
    """
    require_openrouter_api_key()
    cfg = OpenRouterConfig()

    wins = ", ".join([w for w in completed_goals if w]) or "(none)"
    lessons = ", ".join([l for l in failed_lessons if l]) or "(none)"

    with opik_trace("generate_yearly_report", metadata={"model": cfg.model_text}):
        prompt = (
            "Write a warm but direct yearly progress summary.\n"
            "Include: 3 highlights, 3 lessons, and 3 next-year focus points.\n"
            "Keep it under 250 words.\n\n"
            f"Wins: {wins}\n"
            f"Lessons from failures: {lessons}\n"
        )
        with opik_span("call"):
            return chat_completion(
                model=cfg.model_text,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500,
            ) or "Your year is still being written. Keep showing up."

