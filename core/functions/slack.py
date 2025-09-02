# imports - Python/general
import re, requests, json
import traceback
import slack_sdk
import urllib.parse
import slack_sdk.errors

# imports - Django
from django.conf import settings
from django.db.models import Q

# imports - our app
# Models
from core.models import SlackCredential
# Functions
from tableau_next_question.functions import log_and_display_message
import core.functions.helpers_other as helpers_other

# Our app to Slack #
# ################## #

# Functions for interacting with Slack

def check_slack_credentials(slack_credentials:SlackCredential) -> SlackCredential | str | None:
    """
    Connects to Slack to verify the validity of stored Slack Credentials. Returns the same SlackCredential object if successful. If no credentials exist, it returns None. But if credentials exist and they yield an error message, that error is returned.
    """
    log_and_display_message(f"Checking Slack App credentials validity for { slack_credentials.slack_app }.")

    try:
        slack_webclient = slack_sdk.WebClient(token=slack_credentials.slack_workspace_bot_user_access_token)
        test_result = slack_webclient.auth_test()
        if test_result.get("ok", False):
            return slack_credentials
        else:
            slack_error_message = test_result.get("error", "Unknown error")
            raise Exception(f"Slack API returned an error: { test_result }")
    except Exception as e:
        log_and_display_message(f"There was an error connecting to Slack.\n\t{e}\n\t{traceback.format_exc()}")
        return str(e)

def check_and_join_channel(slack_channel:str, slack_webclient:slack_sdk.WebClient) -> bool:
    """
    If we are posting to a channel, we need to join that channel. Unless we are posting a DM, in which case we need to initiate the conversation with the user if that wasn't done already.
    """

    if not slack_channel.startswith("D") and not slack_channel.startswith("U"):
        if not slack_webclient.conversations_info(channel=slack_channel).get("channel", {}).get("is_member", False):
            log_and_display_message(f"Bot is not a member of channel { slack_channel } yet; joining it first.")
            return slack_webclient.conversations_join(channel=slack_channel)

def get_user_info(slack_user_id:str, slack_credential:SlackCredential) -> dict:
    """
    Get the user info and profile for a Slack user ID. This is used to get the user's name and email address, for example.
    """

    log_and_display_message(f"Getting user and their profile for Slack user ID { slack_user_id }.")
    slack_webclient = slack_sdk.WebClient(token=slack_credential.slack_workspace_bot_user_access_token)

    try:
        response = slack_webclient.users_info(user=slack_user_id)
        if response.get("ok", False):
            return response.get("user", {})
        else:
            raise Exception(f"Slack API returned an error: { response }")
    except Exception as e:
        log_and_display_message(f"There was an error getting the user info and profile for Slack user ID { slack_user_id }.\n\t{e}\n\t{traceback.format_exc()}")
        return None

def upload_file(slack_channel:str, slack_credential:SlackCredential, file:bytes, file_format:str, file_title:str, initial_comment:str=None, thread_ts:str=None) -> dict:
    """
    Upload a file to a Slack channel, and return the JSON/dict response from the Slack API.
    """

    log_and_display_message(f"Connecting to Slack workspace and uploading file to channel: { slack_channel }.")
    slack_webclient = slack_sdk.WebClient(token=slack_credential.slack_workspace_bot_user_access_token)

    check_and_join_channel(slack_channel, slack_webclient)

    file_title_for_upload = helpers_other.slugify(file_title) if file_title else "uploaded_file"
    file_name_for_upload = f"{ file_title_for_upload }.{ file_format }" if file_format else f"{ file_title_for_upload }.png"
    
    return slack_webclient.files_upload_v2(file=file, filename=file_name_for_upload, channel=slack_channel, initial_comment=initial_comment, title=file_title, thread_ts=thread_ts)

def post_message(slack_channel:str, slack_credential:SlackCredential, text:str=None, blocks:list=[], icon_emoji:str=None, thread_ts:str=None) -> dict:
    """
    Post a message to a Slack channel, and return the JSON/dict response from the Slack API.
    """

    if text is None and len(blocks) == 0:
        raise Exception("No text or blocks provided to post_message.")

    log_and_display_message(f"Connecting to Slack workspace and posting to channel: { slack_channel }.")
    slack_webclient = slack_sdk.WebClient(token=slack_credential.slack_workspace_bot_user_access_token)

    check_and_join_channel(slack_channel, slack_webclient)

    if blocks and len(blocks) > 0:
        if icon_emoji is not None:
            return slack_webclient.chat_postMessage(channel=slack_channel, text=text, blocks=blocks, icon_emoji=icon_emoji, thread_ts=thread_ts)
        else:
            return slack_webclient.chat_postMessage(channel=slack_channel, text=text, blocks=blocks, thread_ts=thread_ts)
    else: # Then it has to be text
        if icon_emoji is not None:
            return slack_webclient.chat_postMessage(channel=slack_channel, markdown_text=text, icon_emoji=icon_emoji, thread_ts=thread_ts)
        else:
            return slack_webclient.chat_postMessage(channel=slack_channel, markdown_text=text, thread_ts=thread_ts)
    

def update_message(slack_channel:str, slack_credential:SlackCredential, text:str=None, blocks:list=[], thread_ts:str=None) -> dict:
    """
    Update a message on Slack, and return the JSON/dict response from the Slack API.
    """

    if text is None and len(blocks) == 0:
        raise Exception("No text or blocks provided to update_message.")

    log_and_display_message(f"Connecting to Slack workspace and updating message with ts { thread_ts } in channel: { slack_channel }.")
    slack_webclient = slack_sdk.WebClient(token=slack_credential.slack_workspace_bot_user_access_token)

    if blocks and len(blocks) > 0:
        return slack_webclient.chat_update(channel=slack_channel, text=text, blocks=blocks, ts=thread_ts)
    else: # Then it has to be text
        return slack_webclient.chat_update(channel=slack_channel, text=text, ts=thread_ts)
    


def post_status_message(slack_channel:str, slack_credential:SlackCredential, previous_status_message_ts:str=None, thread_ts:str=None, text:str=None, icon_emoji:str=":thinkspin:") -> dict:
    """
    Post a "status message" to a Slack channel. The intended use is the have a message that is updated with the current status of a task, such as "thinking", "processing", etc. When the status is updated by calling the function again, the previous message is deleted and replaced with the new one, seemingly in-place.

    Requires the `previous_status_message` to be a dict containing the response from the Slack API when the message was posted. This is used to delete the previous message before posting the new one.

    Deleting the message can be done by passing no text argument, or None.

    Arguments:
    - `slack_channel`: The Slack channel to post the status message to.
    - `slack_credential`: The Slack credentials to use for posting the message.
    - `previous_status_message_ts`: The timestamp of the previous status message to delete. If None, starts a new status message.
    - `text`: The text of the status message to post. If None, the status message will be removed.
    - `icon_emoji`: The emoji to use as the icon for the status message. Defaults to ":thinkspin:".
    """

    log_and_display_message(f"Connecting to Slack workspace and posting status message to channel: { slack_channel }.")
    slack_webclient = slack_sdk.WebClient(token=slack_credential.slack_workspace_bot_user_access_token)

    check_and_join_channel(slack_channel, slack_webclient)

    if text is not None:
        text = f"{ icon_emoji } { text }"

    # New message, or update existing one?
    if previous_status_message_ts and text is not None:
        # Update this message
        log_and_display_message(f"Updating previous status message in channel { slack_channel } with text: { text }.", level="debug")
        try:
            response = slack_webclient.chat_update(channel=slack_channel, ts=previous_status_message_ts, text=text)
            return response
        except slack_sdk.errors.SlackApiError as e:
            log_and_display_message(f"There was an error updating the status message in Slack: { e.response['error'] }", level="error")
            return None
    elif text is not None:
        log_and_display_message(f"Posting new status message in channel { slack_channel } with text: { text }.", level="debug")
        try:
            response = slack_webclient.chat_postMessage(channel=slack_channel, text=text, thread_ts=thread_ts)
            return response
        except slack_sdk.errors.SlackApiError as e:
            log_and_display_message(f"There was an error posting the status message in Slack: { e.response['error'] }", level="error")
            return None
    else:
        # Delete the previous message
        log_and_display_message(f"Deleting previous status message in channel { slack_channel } with timestamp: { previous_status_message_ts }.", level="debug")
        try:
            response = slack_webclient.chat_delete(channel=slack_channel, ts=previous_status_message_ts)
            return response
        except slack_sdk.errors.SlackApiError as e:
            log_and_display_message(f"There was an error deleting the status message in Slack: { e.response['error'] }", level="error")
            return None


def respond_to_response_url(response_url:str, text:str) -> dict:
    """
    Respond to a Slack response URL with a message. This is used for interactive messages and modals; probably not interesting in other cases.
    """

    log_and_display_message(f"Posting a direct text response to a Slack response URL: { response_url }.")

    try:
        response = requests.post(response_url, json={"text": text})
        if response.status_code != 200:
            raise Exception(f"Failed to post message to Slack response URL: { response.text }")
        return response.json()
    except Exception as e:
        log_and_display_message(f"There was an error posting a message to the Slack response URL: { e }")
        return None
    
# Functions related to Slack channel mappings


def determine_channel_type(slack_channel:dict) -> str:
    """
    Takes a Slack channel object (from the API) and returns the corresponding channel type. (The intention was to extend this to a full mapping, but this may be applicable later only.)
    """
    if slack_channel.get("is_private", False):
        return "private_channel"
    elif slack_channel.get("is_im", False):
        return "im"
    elif slack_channel.get("is_mpim", False):
        return "mpim"
    else:
        return "public_channel"
