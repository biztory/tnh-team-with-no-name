# imports - Python/general
import re, requests, json
import traceback
import slack_sdk
import urllib.parse
import slack_sdk.errors

# imports - Django
from django.conf import settings
from django.db.models import Q

# imports - Orbit One
# Models
from core.models import SlackCredential, SlackChannelMapping
# Functions
from tableau_next_question.functions import log_and_display_message
import core.functions.helpers_other as helpers_other

# Orbit One to Slack #
# ################## #

# Functions for interacting with Slack


def get_slack_redirect_uri(url_encoded:bool=True) -> str:
    redirect_uri = f"https://{ settings.ORBIT_ONE_APP_DOMAIN }/organization/slack_authorization_response"
    if url_encoded:
        return urllib.parse.quote_plus(redirect_uri)
    else:
        return redirect_uri

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


def determine_channel_type(slack_channel:dict) -> SlackChannelMapping.SlackChannelType:
    """
    Takes a Slack channel object (from the API) and returns the corresponding SlackChannelMapping.SlackChannelType.
    """
    if slack_channel.get("is_private", False):
        return SlackChannelMapping.SlackChannelType.private_channel
    elif slack_channel.get("is_im", False):
        return SlackChannelMapping.SlackChannelType.im
    elif slack_channel.get("is_mpim", False):
        return SlackChannelMapping.SlackChannelType.mpim
    else:
        return SlackChannelMapping.SlackChannelType.public_channel

def update_slack_channel_mappings() -> None:
    """
    Called by a scheduled task, updates the Slack channel mappings for all channels in the organization.
    """
    log_and_display_message("Updating Slack channel mappings for all organizations.")
    slack_credential = SlackCredential.objects.first()
    if slack_credential is None:
        raise Exception("No credentials found for Slack (any app). Has it been installed and configured in Orbit One?")
    
    slack_webclient = slack_sdk.WebClient(token=slack_credential.slack_workspace_bot_user_access_token)
    
    mappings_new = []
    mappings_existing = SlackChannelMapping.objects.filter(slack_workspace_id=slack_credential.slack_workspace_id)
    
    # We will be bulk creating and bulk updating the mappings

    try:
        cursor = None
        
        while True:
            response = slack_webclient.conversations_list(cursor=cursor, exclude_archived=True, limit=1000)

            for channel in response.get("channels", []):

                try:

                    # Get properties
                    slack_channel_id = channel.get("id")
                    slack_channel_name = channel.get("name")
                    slack_channel_type = determine_channel_type(channel)

                    # Update if it exists, or create if it doesn't.
                    if slack_channel_id and slack_channel_name:
                        # Check if the mapping already exists
                        slack_channel_mapping = mappings_existing.filter(slack_channel_name=slack_channel_name).first()
                        if slack_channel_mapping is None:
                            # Create a new mapping
                            slack_channel_mapping = SlackChannelMapping(
                                slack_channel_id=slack_channel_id,
                                slack_workspace_id=slack_credential.slack_workspace_id,
                                slack_channel_name=slack_channel_name,
                                slack_channel_type=slack_channel_type
                            )
                            mappings_new.append(slack_channel_mapping)
                        else:
                            # Update the existing mapping, but only if the ID or type has changed
                            if slack_channel_mapping.slack_channel_id != slack_channel_id or slack_channel_mapping.slack_channel_type != slack_channel_type:
                                slack_channel_mapping.slack_channel_id = slack_channel_id
                                slack_channel_type = slack_channel_mapping.slack_channel_type
                            else:
                                # Drop it so we don't re-update it for nothing
                                mappings_existing = mappings_existing.exclude(id=slack_channel_mapping.id)

                except Exception as e:
                    log_and_display_message(f"There was an error processing the Slack channel { slack_channel_id }.\n\t{e}\n\t{traceback.format_exc()}")

            cursor = response.get("response_metadata", {}).get("next_cursor")
            
            if not cursor:
                break
        
        # Bulk create new mappings
        if mappings_new:
            SlackChannelMapping.objects.bulk_create(mappings_new)
            log_and_display_message(f"Created { len(mappings_new) } new Slack channel mappings.")
        else:
            log_and_display_message("No new Slack channel mappings to create.")
        # Bulk update existing mappings
        if mappings_existing:
            SlackChannelMapping.objects.bulk_update(mappings_existing, ["slack_channel_name"])
            log_and_display_message(f"Updated { len(mappings_existing) } existing Slack channel mappings.")
        else:
            log_and_display_message("No existing Slack channel mappings to update.")
        
        log_and_display_message("Finished updating Slack channel mappings.")
        return None
    
    except slack_sdk.errors.SlackApiError as e:
        log_and_display_message(f"Slack API error: {e}", level="error")
        return None
        

def find_slack_channel_mapping(slack_channel_identifier:str, slack_channel_type:SlackChannelMapping.SlackChannelType=None) -> SlackChannelMapping | None:
    """
    Takes either a Slack channel ID or a Slack channel as the slack_channel_identifier, and returns the corresponding SlackChannelMapping object.

    slack_channel_identifier: The ID of the Slack channel (e.g. "C1234567890" or "U12312312") or the name of the Slack channel (e.g. "general" or "#general"). Also allows for an email address (e.g. "timothy.vermeiren@biztory.be") to be passed in, which will attempt to find the user's DM/ID in the mappings.
     
    If the prefix (#) is provided, it will be used to determine the type of channel.
    
    slack_channel_type: The type of channel (e.g. public_channel, private_channel, im, mpim), if known.

    If the SlackChannelMapping object is not found, we'll use the Slack API to try to resolve the name from the ID, or the ID from the name. This means iterating until we find the mapping, or until we run out of channels to check. If a result is found with the API, it is stored in the database.
    """

    # Determine the type of channel based on the name or ID, if we can
    if slack_channel_type is None:
        if slack_channel_identifier.startswith("#") or slack_channel_identifier.startswith("C") or slack_channel_identifier.startswith("Z"):
            # Not 1000% correct, # could be a private channel, but we don't fully support that yet. Z is Slack Connect.
            slack_channel_type = SlackChannelMapping.SlackChannelType.public_channel
        elif "@" in slack_channel_identifier or slack_channel_identifier.startswith("D") or slack_channel_identifier.startswith("U"):
            # "@" in the identifier means it's an email address, and thus a user and thus an IM/DM.
            slack_channel_type = SlackChannelMapping.SlackChannelType.im
        elif slack_channel_identifier.startswith("G"):
            slack_channel_type = SlackChannelMapping.SlackChannelType.private_channel
        # There is no else; the type will remain None or whatever it was set to.

    # Remove the name prefixes from the identifier if it exists; we don't store it or use it in lookups.
    if slack_channel_identifier.startswith("#"):
        slack_channel_identifier = slack_channel_identifier[1:]

    # Try known mappings by name first.
    if slack_channel_type:
        slack_channel_mapping = SlackChannelMapping.objects.filter(slack_channel_name=slack_channel_identifier, slack_channel_type=slack_channel_type).first()
    else:
        slack_channel_mapping = SlackChannelMapping.objects.filter(slack_channel_name=slack_channel_identifier).first()

    if slack_channel_mapping is not None:
        return slack_channel_mapping
    
    # Try known mappings by ID second.
    if slack_channel_type:
        slack_channel_mapping = SlackChannelMapping.objects.filter(slack_channel_id=slack_channel_identifier, slack_channel_type=slack_channel_type).first()
    else:
        slack_channel_mapping = SlackChannelMapping.objects.filter(slack_channel_id=slack_channel_identifier).first()
    if slack_channel_mapping is not None:
        return slack_channel_mapping
    
    # Or try by email third, if the identifier is an email address.
    if "@" in slack_channel_identifier:
        if slack_channel_type:
            slack_channel_mapping = SlackChannelMapping.objects.filter(slack_channel_email=slack_channel_identifier, slack_channel_type=slack_channel_type).first()
        else:
            slack_channel_mapping = SlackChannelMapping.objects.filter(slack_channel_email=slack_channel_identifier).first()
        if slack_channel_mapping is not None:
            return slack_channel_mapping
    
    
    # If we didn't have the mapping already, let's use the Slack API to try and find it.
    slack_credential = SlackCredential.objects.first()
    if slack_credential is None:
        raise Exception("No credentials found for Slack (any app). Has it been installed and configured in Orbit One?")
    slack_webclient = slack_sdk.WebClient(token=slack_credential.slack_workspace_bot_user_access_token)

    found_slack_channel = None

    # If we know the type, we can use it to filter the channels we'll be requesting from the Slack API. The SlackChannelType should coincide with the value(s) the API is expecting.
    slack_channel_type_for_api = None
    if slack_channel_type:
        slack_channel_type_for_api = [slack_channel_type.value]

    # Different approach for channels, as for DMs. DMs, we can just initiate through the user ID and get a conversation ID. Channels, we look up.
    try:

        if slack_channel_type in [SlackChannelMapping.SlackChannelType.public_channel, SlackChannelMapping.SlackChannelType.private_channel]:

            cursor = None
            
            while not found_slack_channel:
                if slack_channel_type_for_api:
                    response = slack_webclient.conversations_list(cursor=cursor, exclude_archived=True, limit=1000, types=slack_channel_type_for_api)
                else:
                    response = slack_webclient.conversations_list(cursor=cursor, exclude_archived=True, limit=1000)

                found_slack_channel = next((channel for channel in response.get("channels", []) if channel.get("id") == slack_channel_identifier or channel.get("name") == slack_channel_identifier), None)

                if found_slack_channel is not None:
                    # We found the name, let's create a new mapping
                    slack_channel_mapping = SlackChannelMapping.objects.create(
                        slack_channel_id=found_slack_channel.get("id"),
                        slack_workspace_id=slack_credential.slack_workspace_id,
                        slack_channel_name=found_slack_channel.get("name"),
                        slack_channel_type=determine_channel_type(found_slack_channel)
                    )
                    return slack_channel_mapping
                
                else:
                    cursor = response.get("response_metadata", {}).get("next_cursor")
                
                if not cursor:
                    break

            # If we get here, we didn't find the channel name
            log_and_display_message(f"Slack channel identifier \"{ slack_channel_identifier }\" could not be resolved to a name or ID.")
            return None
    
        else:
            # DMs, either by:
            # - email, which we need to look up and store
            # - or ID, where we can just initiate the conversation with the user ID and get a conversation ID.
            if "@" in slack_channel_identifier:
                # We have an email address, so we need to look it up first.
                user = slack_webclient.users_lookupByEmail(email=slack_channel_identifier)
                if user is not None:
                    # We will also initiate a conversation with the user, so we can get the ID for the DM (and not just the user).
                    conversation = slack_webclient.conversations_open(users=user.get("user", {}).get("id"))
                    if conversation is not None:
                        slack_dm_channel_id = conversation.get("channel", {}).get("id")
                    else:
                        slack_dm_channel_id = None
                    slack_channel_mapping = SlackChannelMapping.objects.create(
                        slack_workspace_id=slack_credential.slack_workspace_id,
                        slack_channel_id=slack_dm_channel_id,
                        slack_channel_name=user.get("user", {}).get("id"),
                        slack_channel_email=slack_channel_identifier,
                        slack_channel_type=SlackChannelMapping.SlackChannelType.im
                    )
                    return slack_channel_mapping
                else:
                    log_and_display_message(f"Slack channel identifier \"{ slack_channel_identifier }\" could not be resolved to a name or ID.")
                    return None
            else:
                log_and_display_message(f"Opening Bot DM with { slack_channel_identifier }")
                conversation = slack_webclient.conversations_open(users=slack_channel_identifier)
                if conversation is not None:
                    # We found the name, let's create a new mapping
                    slack_channel_mapping = SlackChannelMapping.objects.create(
                        slack_channel_id=conversation.get("channel", {}).get("id"),
                        slack_workspace_id=slack_credential.slack_workspace_id,
                        slack_channel_name=slack_channel_identifier,
                        slack_channel_type=SlackChannelMapping.SlackChannelType.im
                    )
                    return slack_channel_mapping
                else:
                    log_and_display_message(f"Slack channel identifier \"{ slack_channel_identifier }\" could not be resolved to a name or ID.")
                    return None

    except Exception as e:
        log_and_display_message(f"There was an error processing the Slack channel { slack_channel_identifier }.\n\t{e}\n\t{traceback.format_exc()}")
        return None
