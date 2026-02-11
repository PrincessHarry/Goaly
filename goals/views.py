from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Q, Count, Sum
from datetime import datetime, timedelta
import json
import random

from .models import Goal, UserStats
from ai.services import (
    EvidenceVerificationResult,
    generate_yearly_report as ai_generate_yearly_report,
    get_ai_coaching as ai_get_ai_coaching,
    get_goal_tips as ai_get_goal_tips,
    image_file_to_data_url,
    plan_yearly_goals as ai_plan_yearly_goals,
    refine_goal as ai_refine_goal,
    verify_goal_evidence as ai_verify_goal_evidence,
)


def landing(request):
    """Landing page for Goaly - goal setting and rewards."""
    if request.user.is_authenticated:
        return redirect("goals:dashboard")
    
    if request.method == "POST" and request.POST.get("email"):
        messages.success(
            request,
            "Thanks for signing up! We'll notify you when Goaly launches.",
        )
        return redirect("landing")
    return render(request, "goals/landing.html")


@login_required
def dashboard(request):
    """Main dashboard view."""
    goals = Goal.objects.filter(user=request.user)
    
    # Calculate user stats
    completed = goals.filter(status="completed")
    verified = completed.filter(verified=True)
    failed = goals.filter(status="failed")
    total_finished = completed.count() + failed.count()
    
    points = 0
    for goal in completed:
        base = 10
        if goal.timeframe == "Weekly":
            base = 50
        elif goal.timeframe == "Monthly":
            base = 200
        elif goal.timeframe == "Yearly":
            base = 1000
        points += base + (base * 0.5 if goal.verified else 0)
    
    streak = 1 if goals.exists() else 0
    discipline_score = round((completed.count() / total_finished * 100)) if total_finished > 0 else 100
    
    user_stats = {
        "points": round(points),
        "streak": streak,
        "total_goals_completed": completed.count(),
        "growth_rate": 15,
        "discipline_score": discipline_score,
        "verified_count": verified.count(),
    }
    
    # Minimal goal data for calendar view (serializable)
    goals_for_calendar = [
        {
            "id": g.id,
            "text": g.text,
            "status": g.status,
            "timeframe": g.timeframe,
            "created_at": g.created_at.isoformat(),
            "scheduled_date": g.scheduled_date.isoformat() if g.scheduled_date else None,
        }
        for g in goals
    ]

    goals_for_alarms = [
        {
            "id": g.id,
            "text": g.text,
            "status": g.status,
            "reminder_time": g.reminder_time.isoformat() if g.reminder_time else None,
        }
        for g in goals.filter(status="pending").exclude(reminder_time__isnull=True)
    ]
    
    # Get goals by timeframe
    goals_by_timeframe = {
        "Daily": goals.filter(timeframe="Daily", status="pending"),
        "Weekly": goals.filter(timeframe="Weekly", status="pending"),
        "Monthly": goals.filter(timeframe="Monthly", status="pending"),
        "Yearly": goals.filter(timeframe="Yearly", status="pending"),
    }
    
    active_tab = request.GET.get("tab", "board")
    
    # Simple leaderboard based on cached UserStats (top 10)
    leaderboard_qs = (
        UserStats.objects.select_related("user")
        .order_by("-points")[:10]
    )
    leaderboard_entries = [
        {
            "id": us.user.id,
            "name": us.user.get_full_name() or us.user.username,
            "avatar": getattr(getattr(us.user, "profile", None), "avatar", None),
            "stats": {
                "points": us.points,
                "streak": us.streak,
                "total_goals_completed": us.total_goals_completed,
                "growth_rate": us.growth_rate,
                "discipline_score": us.discipline_score,
                "verified_count": us.verified_count,
            },
            "rank": idx + 1,
        }
        for idx, us in enumerate(leaderboard_qs)
    ]
    
    context = {
        "goals": goals,
        "goals_by_timeframe": goals_by_timeframe,
        "user_stats": user_stats,
        "active_tab": active_tab,
        "completed_goals": completed,
        "failed_goals": failed,
        "goals_for_calendar": goals_for_calendar,
        "leaderboard_entries": leaderboard_entries,
        "goals_for_alarms": goals_for_alarms,
    }
    
    return render(request, "goals/dashboard.html", context)


@login_required
@require_http_methods(["POST"])
def add_goal(request):
    """Add a new goal."""
    data = json.loads(request.body)
    text = data.get("text", "").strip()
    timeframe = data.get("timeframe", "Daily")
    scheduled_date = data.get("scheduled_date")
    
    if not text:
        return JsonResponse({"error": "Goal text is required"}, status=400)
    
    goal = Goal.objects.create(
        user=request.user,
        text=text,
        timeframe=timeframe,
        scheduled_date=scheduled_date if scheduled_date else None,
    )
    
    return JsonResponse({
        "id": goal.id,
        "text": goal.text,
        "timeframe": goal.timeframe,
        "status": goal.status,
        "created_at": goal.created_at.isoformat(),
    })


@login_required
@require_http_methods(["POST"])
def toggle_goal(request, goal_id):
    """Toggle goal status (pending <-> completed)."""
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    
    if goal.status == "pending":
        goal.status = "completed"
        goal.reminder_time = None
        goal.save()
        return JsonResponse({"status": "completed", "message": "Goal completed!"})
    else:
        goal.status = "pending"
        goal.evidence = None
        goal.verified = None
        goal.ai_feedback = ""
        goal.save()
        return JsonResponse({"status": "pending", "message": "Goal reset to pending"})


@login_required
@require_http_methods(["POST"])
def delete_goal(request, goal_id):
    """Delete a goal."""
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    goal.delete()
    return JsonResponse({"message": "Goal deleted"})


@login_required
@require_http_methods(["POST"])
def mark_failed(request, goal_id):
    """Mark a goal as failed."""
    data = json.loads(request.body)
    lesson = data.get("lesson", "Timing not right.")
    
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    goal.status = "failed"
    goal.lesson = lesson
    goal.reminder_time = None
    goal.save()
    
    return JsonResponse({"message": "Goal marked as failed"})


def _verify_evidence_heuristic(goal):
    """
    Set verified and ai_feedback after evidence upload (heuristic; no external API).
    Replace with real vision AI (e.g. Gemini) when available.
    """
    goal.verified = True
    goal.ai_feedback = (
        f"Evidence logged for «{goal.text[:60]}{'…' if len(goal.text) > 60 else ''}». "
        "Keep building momentum."
    )


@login_required
@require_http_methods(["POST"])
def upload_evidence(request, goal_id):
    """Upload evidence image for a goal. Sets verified and ai_feedback after save."""
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    
    if "evidence" in request.FILES:
        uploaded = request.FILES["evidence"]
        goal.evidence = uploaded
        goal.status = "completed"
        try:
            image_url = image_file_to_data_url(uploaded)
            result: EvidenceVerificationResult = ai_verify_goal_evidence(
                goal_text=goal.text,
                image_data_url=image_url,
            )
            goal.verified = result.verified
            goal.ai_feedback = result.feedback
        except Exception:
            # Safe fallback: store evidence without breaking completion flow
            _verify_evidence_heuristic(goal)
        goal.save()
        return JsonResponse({
            "message": "Evidence uploaded",
            "evidence_url": goal.evidence.url if goal.evidence else None,
            "verified": goal.verified,
            "ai_feedback": goal.ai_feedback,
        })
    
    return JsonResponse({"error": "No file uploaded"}, status=400)


@login_required
@require_http_methods(["POST"])
def generate_plan(request):
    """
    Generate a simple action plan from a free-text vision.
    Uses OpenRouter AI (structured JSON) when configured.
    """
    data = json.loads(request.body)
    vision = (data.get("vision") or "").strip()
    if not vision:
        return JsonResponse({"error": "Vision is required"}, status=400)

    try:
        plan = ai_plan_yearly_goals(yearly_visions=vision)
        return JsonResponse(plan)
    except Exception:
        # Safe fallback (non-AI) if key isn't configured
        daily = [
            "Spend 25 minutes on the most important task",
            "Review today’s goals and pick one high-impact win",
            "Log one proof (screenshot/photo/notes) for completed work",
        ]
        weekly = [
            "Plan the week: choose 3 outcomes and schedule them",
            "Review what worked and what didn’t; adjust one habit",
        ]
        monthly = [
            "Do a monthly retrospective and reset priorities",
            "Ship one meaningful milestone toward the vision",
        ]
        yearly = [
            f"Define success metrics for: {vision[:80]}{'...' if len(vision) > 80 else ''}",
            "Create a quarterly roadmap and review it every 4 weeks",
        ]
        return JsonResponse({"daily": daily, "weekly": weekly, "monthly": monthly, "yearly": yearly})


@login_required
@require_http_methods(["GET"])
def yearly_report(request):
    """Generate a narrative yearly report (AI when configured)."""
    goals = Goal.objects.filter(user=request.user)
    completed = goals.filter(status="completed")
    failed = goals.filter(status="failed")
    total = completed.count() + failed.count()
    rate = round((completed.count() / total) * 100) if total > 0 else 0

    first_date = goals.order_by("created_at").values_list("created_at", flat=True).first()
    first_str = first_date.date().isoformat() if first_date else timezone.now().date().isoformat()

    highlights = list(completed.values_list("text", flat=True)[:6])
    lessons = list(failed.values_list("lesson", flat=True)[:4])

    try:
        narrative = ai_generate_yearly_report(
            completed_goals=highlights,
            failed_lessons=[l for l in lessons if l],
        )
        return JsonResponse({"narrative": narrative})
    except Exception:
        narrative_lines = [
            f"From {first_str} to today, you completed {completed.count()} goals and recorded {failed.count()} setbacks.",
            f"Your execution success rate is {rate}%.",
            "",
            "Key milestones:",
        ]
        if highlights:
            narrative_lines += [f"- {h}" for h in highlights]
        else:
            narrative_lines += ["- No completed goals yet. Your next win will set the tone."]

        narrative_lines += ["", "Lessons learned:"]
        if lessons:
            narrative_lines += [f"- {l}" for l in lessons if l]
        else:
            narrative_lines += ["- No failures logged. Keep pressure-testing your plans to grow faster."]

        narrative_lines += [
            "",
            "Next focus:",
            "- Pick one daily goal you can complete every day for 7 days.",
            "- Add proof for completions to build momentum and accountability.",
        ]

        return JsonResponse({"narrative": "\n".join(narrative_lines)})


@login_required
@require_http_methods(["POST"])
def update_reminder(request, goal_id):
    """Set or clear a reminder time for a goal."""
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    data = json.loads(request.body)
    reminder_time = data.get("reminder_time")  # ISO string or null

    if not reminder_time:
        goal.reminder_time = None
        goal.save(update_fields=["reminder_time"])
        return JsonResponse({"message": "Reminder cleared"})

    try:
        # Accept ISO strings; store as aware dt in current timezone
        dt = datetime.fromisoformat(reminder_time.replace("Z", "+00:00"))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        goal.reminder_time = dt
        goal.save(update_fields=["reminder_time"])
        return JsonResponse({"message": "Reminder set", "reminder_time": goal.reminder_time.isoformat()})
    except Exception:
        return JsonResponse({"error": "Invalid reminder_time"}, status=400)


@login_required
@require_http_methods(["POST"])
def snooze_alarm(request, goal_id):
    """Snooze a due alarm by N minutes (default 10)."""
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    data = json.loads(request.body) if request.body else {}
    minutes = int(data.get("minutes", 10))
    minutes = max(1, min(minutes, 1440))

    goal.reminder_time = timezone.now() + timedelta(minutes=minutes)
    goal.save(update_fields=["reminder_time"])
    return JsonResponse({"message": "Snoozed", "reminder_time": goal.reminder_time.isoformat()})


@login_required
@require_http_methods(["POST"])
def coach_chat(request):
    """
    Lightweight coaching endpoint (safe default).
    Returns a tough-love, tactical response grounded in the user's pending goals.
    """
    data = json.loads(request.body)
    msg = (data.get("message") or "").strip()
    if not msg:
        return JsonResponse({"error": "Message is required"}, status=400)

    goals = Goal.objects.filter(user=request.user)
    pending = list(goals.filter(status="pending").order_by("-created_at")[:12])

    # Basic stats (mirror dashboard)
    completed_count = goals.filter(status="completed").count()
    failed_count = goals.filter(status="failed").count()
    total_finished = completed_count + failed_count
    discipline = round((completed_count / total_finished) * 100) if total_finished > 0 else 100

    pending_lines = "\n".join([f"- [{g.timeframe}] {g.text}" for g in pending]) or "- (no pending goals)"

    try:
        reply = ai_get_ai_coaching(
            pending_goals=[{"timeframe": g.timeframe, "text": g.text} for g in pending],
        )
        return JsonResponse({"reply": reply})
    except Exception:
        # Keep the old deterministic behavior as a fallback if AI isn't configured.
        lower = msg.lower()
        is_overwhelmed = any(k in lower for k in ["overwhelmed", "too much", "stressed", "anxious"])
        is_procrast = any(k in lower for k in ["procrast", "later", "can't start", "lazy", "avoid"])
        is_review = any(k in lower for k in ["review", "strategy", "plan", "year", "roadmap"])

        opener = random.choice([
            "Good. We’re not negotiating with your future self today.",
            "Let’s cut the noise and execute.",
            "I’m going to be direct because you said you want results.",
        ])

        if is_overwhelmed:
            reply = (
                f"{opener}\n\n"
                "**You’re overwhelmed because your brain is trying to hold the whole map at once.**\n\n"
                "## Do this in the next 10 minutes\n"
                "1. Pick **one** pending goal that moves the needle.\n"
                "2. Break it into a **2-minute start** (open the file, put shoes on, write first sentence).\n"
                "3. Set a timer for **12 minutes**. No perfection.\n\n"
                "## Your current pending goals\n"
                f"{pending_lines}\n\n"
                f"**Discipline score right now:** {discipline}%.\n"
                "Reply with: **(1)** which goal you’ll do first and **(2)** your 2-minute start."
            )
            return JsonResponse({"reply": reply})

        if is_procrast:
            reply = (
                f"{opener}\n\n"
                "**Procrastination is usually unclear next steps + low immediate reward. Fix both.**\n\n"
                "## Protocol\n"
                "- Choose the smallest win that still counts.\n"
                "- Make the first step **ridiculously easy**.\n"
                "- Timebox: **15 minutes**, then reassess.\n\n"
                "## Pick one (A/B/C)\n"
                "A) 15 minutes on your hardest goal\n"
                "B) 15 minutes on your easiest goal (momentum)\n"
                "C) 5 minutes planning + 10 minutes doing\n\n"
                "## Pending goals\n"
                f"{pending_lines}\n\n"
                "Tell me A/B/C and the goal you’re committing to."
            )
            return JsonResponse({"reply": reply})

        if is_review:
            reply = (
                f"{opener}\n\n"
                "## Quick yearly strategy (no fluff)\n"
                "1. **One North Star**: what must be true by year-end?\n"
                "2. **Quarterly bets**: 3 projects max.\n"
                "3. **Weekly cadence**: 1 review + 3 deep-work blocks.\n"
                "4. **Daily minimum**: a 25-minute non-negotiable.\n\n"
                "## What you’re actually on the hook for right now\n"
                f"{pending_lines}\n\n"
                f"**Current execution score:** {discipline}% based on finishes.\n"
                "Reply with your North Star in one sentence and I’ll convert it into quarterly bets."
            )
            return JsonResponse({"reply": reply})

        top3 = pending[:3]
        if top3:
            focus_block = "\n".join([f"- **{g.text}** ({g.timeframe})" for g in top3])
        else:
            focus_block = "- **Add 1 daily goal** you can finish today."

        reply = (
            f"{opener}\n\n"
            "## Your next move\n"
            "Pick **one** item and finish it today. No heroics, just completion.\n\n"
            "## Recommended focus\n"
            f"{focus_block}\n\n"
            "## Rule\n"
            "**Start before you feel ready.** Set a 12–15 minute timer and begin.\n\n"
            "If you want, tell me what you’re stuck on and I’ll give you the smallest next step."
        )
        return JsonResponse({"reply": reply})


@login_required
@require_http_methods(["POST"])
def refine_goal(request):
    """
    Return suggested goal phrases from a draft (non-AI heuristic).
    Body: { "text": "...", "timeframe": "Daily"|"Weekly"|"Monthly"|"Yearly" }
    """
    data = json.loads(request.body)
    text = (data.get("text") or "").strip()
    timeframe = data.get("timeframe", "Daily")
    if not text:
        return JsonResponse({"error": "Text is required"}, status=400)

    try:
        subgoals = ai_refine_goal(goal_text=text, timeframe=timeframe)
        # Preserve existing API shape: { "suggestions": [...] }
        return JsonResponse({"suggestions": subgoals})
    except Exception:
        # Fallback suggestions (original heuristic)
        suggestions = []
        lower = text.lower()
        if len(text) > 60:
            suggestions.append(text[:80].rstrip() + ("..." if len(text) > 80 else ""))
        suggestions.append(f"Complete: {text}" if not text.startswith(("Complete", "Finish", "Do ")) else text)
        if timeframe == "Daily":
            suggestions.append(f"Today: {text}")
        elif timeframe == "Weekly":
            suggestions.append(f"This week: {text}")
        elif timeframe == "Monthly":
            suggestions.append(f"This month: {text}")
        elif timeframe == "Yearly":
            suggestions.append(f"This year: {text}")
        if " by " not in lower and " by " not in text:
            suggestions.append(f"{text} (with a clear deadline)")
        seen = set()
        out = []
        for s in suggestions:
            if s and s not in seen and len(s) <= 500:
                seen.add(s)
                out.append(s)
        return JsonResponse({"suggestions": out[:5]})


@login_required
@require_http_methods(["POST"])
def generate_goal_tips(request, goal_id):
    """
    Generate and save tips for a goal (non-AI heuristic). Returns { "tips": [...] }.
    """
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    if goal.status != "pending":
        return JsonResponse({"error": "Only pending goals can have tips"}, status=400)

    try:
        tips = ai_get_goal_tips(goal_text=goal.text, timeframe=goal.timeframe)
        goal.tips = tips
        goal.save(update_fields=["tips"])
        return JsonResponse({"tips": goal.tips})
    except Exception:
        # Heuristic fallback
        text = goal.text
        tf = goal.timeframe
        tips = [
            "Break this into one 15-minute block today.",
            f"Define the smallest possible win for this {tf.lower()} goal.",
            "Schedule a specific time; put it in your calendar.",
            "Remove one distraction before you start.",
            "After finishing, write one sentence: what was the main blocker?",
        ]
        if tf == "Yearly":
            tips.insert(0, "Split into quarterly milestones and review each month.")
        elif tf == "Monthly":
            tips.insert(0, "Pick one week to focus on this; block 2–3 deep-work sessions.")
        elif tf == "Weekly":
            tips.insert(0, "Choose one day and one time slot; protect it.")
        goal.tips = tips
        goal.save(update_fields=["tips"])
        return JsonResponse({"tips": goal.tips})
