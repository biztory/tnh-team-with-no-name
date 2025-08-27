from django.urls import path
from core import views_slack

from . import views

urlpatterns = [
    path("", views.index, name="index"),

    # Slack views
    path("slack/event", views_slack.event, name="slack_event"),
    path("slack/interaction", views_slack.interaction, name="slack_interaction"),
]