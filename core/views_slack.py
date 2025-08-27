# imports - Python/general
import os, json
import traceback

# imports - Django
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

# imports - Orbit One
# Models
from core.models import SlackCredential
# Functions
from tableau_next_question.functions import log_and_display_message
from django.conf import settings
import core.functions.slack as slack
import core.tasks as tasks


# Slack to Orbit One #
# ################## #

# Endpoints Slack (users) can post to to interact with Orbit One.

# Event subscriptions: https://api.slack.com/events-api#event_subscriptions
# Interactive components: https://api.slack.com/interactivity

@csrf_exempt
@require_http_methods(["POST"])
def event(request:HttpRequest):
    """
    Handle any even we receive from Slack. Usually, a message from a user.
    
    Or initially: respond positively to the challenge Slack sends us when we subscribe to events. See: https://api.slack.com/events/url_verification
    """

    # Process the request body
    try:
        request_body = request.body.decode("utf-8")
        request_json = json.loads(request_body)
    except json.JSONDecodeError:
        log_and_display_message("Failed to decode JSON from request body: " + request_body)
        return JsonResponse({ "error": "Invalid JSON" }, status=400)
    
    if "challenge" in request_json:
        # Respond with the challenge
        log_and_display_message("Slack challenge received: " + request_json["challenge"])
        response = JsonResponse({ "challenge": request_json["challenge"] })
        response.status_code = 200
        return response
    else:
        # If not a challenge, process it as a normal event
        # log_and_display_message("Slack event received: " + json.dumps(request_json)) # Uncomment this line to log the event and view its payload.

        if "token" not in request_json or request_json["token"] != settings.SLACK_EVENTS_API_VERIFICATION_TOKEN:
            log_and_display_message(f"Invalid token in request: { request_json.get('token', 'no token at all!') }.")
            return JsonResponse({ "error": "Invalid token" }, status=403)

        # Start task and respond to the user if it's a direct message, not sent by a bot/Orbit One itself.
        if request_json["event"].get("type") == "message" and request_json["event"].get("subtype") not in ["message_changed", "message_deleted"] and request_json["event"].get("channel_type") == "im" and "bot_id" not in request_json["event"]:

            slack_credential, slack_credential_created = SlackCredential.objects.get_or_create()

            thread_ts = request_json["event"].get("thread_ts", request_json["event"].get("message", {}).get("ts"))
            first_name = request_json["event"].get("user_profile", {}).get("first_name")

            # Start an async task to respond to the user with the actual answer.
            try:
                kwargs_for_task = {
                    "slack_channel": request_json["event"]["channel"],
                    "thread_ts": thread_ts,
                    "slack_user_id": request_json["event"]["user"],
                    "first_name": first_name,
                }
                task_result = tasks.respond_to_data_question_task(source="slack", question=request_json["event"]["text"], kwargs=kwargs_for_task)
            except Exception as e:
                error_message = f"Failed to start async task:\n\t{e}\n\t{traceback.format_exc}"
                log_and_display_message(error_message, level="error")
                return JsonResponse({ "error": error_message }, status=500)
            else:
                log_and_display_message(f"Started async task { task_result } to respond to user.")
                # Respond with a preliminary message
                if first_name is not None:
                    message = f"Thanks, got your question, { first_name }! I'll start thinking about it and get back to you in a moment."
                else:
                    message = f"Thanks, got your question! I'll start thinking about it and get back to you in a moment."
                slack.post_message(slack_channel=request_json["event"]["channel"], slack_credential=slack_credential, text=message, thread_ts=thread_ts)

        response = JsonResponse({ "message": "Event received" })
        return response


@csrf_exempt
@require_http_methods(["POST"])
def interaction(request:HttpRequest):
    """
    Handle any interaction we receive from Slack. Usually, a user pressing a button or something along those lines.
    """

    # Process the request body
    try:
        request_body = request.POST.get("payload", "{}")
        request_json = json.loads(request_body)
    except json.JSONDecodeError:
        log_and_display_message("Failed to decode JSON from request body: " + request_body)
        return JsonResponse({ "error": "Invalid JSON" }, status=400)
    
    # log_and_display_message("Slack interaction received: " + json.dumps(request_json)) # Uncomment this line to log the event and view its payload.

    if "token" not in request_json or request_json["token"] != settings.SLACK_EVENTS_API_VERIFICATION_TOKEN:
        log_and_display_message(f"Invalid token in request: { request_json.get('token', 'no token at all!') }.")
        return JsonResponse({ "error": "Invalid token" }, status=403)

    # INTERACTION ROUTING #
    # ------------------- #

    # This is the part where, depending on the type of interaction, we start the appropriate workflow.
    if "actions" in request_json:
        # This is a button click or something similar.
        action = request_json["actions"][0]
        action_id = action.get("action_id")
        action_value = action.get("value")
        slack_channel = request_json.get("container", {}).get("channel_id")
        thread_ts = request_json.get("container", {}).get("thread_ts")
        slack_user_id = request_json.get("user", {}).get("id")

        log_and_display_message(f"Action: { action_id } in channel { slack_channel } with thread_ts { thread_ts }")

        # Routing based on action_id
        if action_id == "answer_im_data_question":
            log_and_display_message(f"{ action_id }: { action_value }")
            # Action value naming convention: "data_question_id:entity_id"
            data_question_id, entity_id = action_value.split(":")
            try:
                kwargs_for_task = {
                    "slack_channel": slack_channel,
                    "thread_ts": thread_ts,
                    "slack_user_id": slack_user_id
                }
                # task_result = tasks.respond_to_data_question_part_deux_task(data_question_id=int(data_question_id), entity_id=int(entity_id), kwargs=kwargs_for_task)
            except Exception as e:
                error_message = f"Failed to start async task:\n\t{e}\n\t{traceback.format_exc}"
                log_and_display_message(error_message, level="error")
            else:
                # log_and_display_message(f"Started async task { task_result } to respond to data question.")
                log_and_display_message(f"Started async task <TO DO> to respond to data question.")

    response = JsonResponse({ "message": "Interaction received" })
    return response
