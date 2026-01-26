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
]
