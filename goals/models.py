from django.db import models
from django.conf import settings
from django.utils import timezone


class Goal(models.Model):
    """Goal model for tracking user goals."""
    
    TIMEFRAME_CHOICES = [
        ("Daily", "Daily"),
        ("Weekly", "Weekly"),
        ("Monthly", "Monthly"),
        ("Yearly", "Yearly"),
    ]
    
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="goals",
    )
    text = models.CharField(max_length=500)
    timeframe = models.CharField(max_length=20, choices=TIMEFRAME_CHOICES, default="Daily")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_date = models.DateField(null=True, blank=True)
    reminder_time = models.DateTimeField(null=True, blank=True)
    category = models.CharField(max_length=100, blank=True)
    lesson = models.TextField(blank=True)  # For failed goals
    tips = models.JSONField(default=list, blank=True)  # AI-generated tips
    evidence = models.ImageField(upload_to="goal_evidence/", null=True, blank=True)
    verified = models.BooleanField(null=True, blank=True)  # AI verification status
    ai_feedback = models.TextField(blank=True)  # AI's analysis of evidence
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "timeframe"]),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.text[:50]}"


class UserStats(models.Model):
    """Cached user statistics for performance."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stats",
    )
    points = models.IntegerField(default=0)
    streak = models.IntegerField(default=0)
    total_goals_completed = models.IntegerField(default=0)
    growth_rate = models.IntegerField(default=0)
    discipline_score = models.IntegerField(default=100)
    verified_count = models.IntegerField(default=0)
    last_calculated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.email} - {self.points} points"
