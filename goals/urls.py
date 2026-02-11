from django.urls import path
from . import views

app_name = "goals"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("api/goals/add/", views.add_goal, name="add_goal"),
    path("api/goals/<int:goal_id>/toggle/", views.toggle_goal, name="toggle_goal"),
    path("api/goals/<int:goal_id>/delete/", views.delete_goal, name="delete_goal"),
    path("api/goals/<int:goal_id>/fail/", views.mark_failed, name="mark_failed"),
    path("api/goals/<int:goal_id>/evidence/", views.upload_evidence, name="upload_evidence"),
    path("api/planner/generate/", views.generate_plan, name="generate_plan"),
    path("api/report/yearly/", views.yearly_report, name="yearly_report"),
    path("api/goals/<int:goal_id>/reminder/", views.update_reminder, name="update_reminder"),
    path("api/goals/<int:goal_id>/alarm/later/", views.snooze_alarm, name="snooze_alarm"),
    path("api/coach/chat/", views.coach_chat, name="coach_chat"),
    path("api/goals/refine/", views.refine_goal, name="refine_goal"),
    path("api/goals/<int:goal_id>/tips/", views.generate_goal_tips, name="generate_goal_tips"),
]
