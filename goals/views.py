from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Q, Count, Sum
from datetime import datetime, timedelta
import json

from .models import Goal, UserStats


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
    
    # Get goals by timeframe
    goals_by_timeframe = {
        "Daily": goals.filter(timeframe="Daily", status="pending"),
        "Weekly": goals.filter(timeframe="Weekly", status="pending"),
        "Monthly": goals.filter(timeframe="Monthly", status="pending"),
        "Yearly": goals.filter(timeframe="Yearly", status="pending"),
    }
    
    active_tab = request.GET.get("tab", "board")
    
    context = {
        "goals": goals,
        "goals_by_timeframe": goals_by_timeframe,
        "user_stats": user_stats,
        "active_tab": active_tab,
        "completed_goals": completed,
        "failed_goals": failed,
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


@login_required
@require_http_methods(["POST"])
def upload_evidence(request, goal_id):
    """Upload evidence image for a goal."""
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    
    if "evidence" in request.FILES:
        goal.evidence = request.FILES["evidence"]
        goal.status = "completed"
        # TODO: Add AI verification here
        goal.save()
        return JsonResponse({
            "message": "Evidence uploaded",
            "evidence_url": goal.evidence.url if goal.evidence else None,
        })
    
    return JsonResponse({"error": "No file uploaded"}, status=400)
