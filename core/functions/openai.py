# imports - Python/general
import json, markdown, base64, typing
import traceback
import openai as openai_client
import pandas as pd
# For typing:
from openai.types.beta.assistant import Assistant

# imports - Django
from django.contrib.auth.base_user import AbstractBaseUser

# imports - our app
# Models
from core.models import OpenAISettings
# Functions
from tableau_next_question.functions import log_and_display_message
import core.functions.helpers_other as helpers_other

# Module containing functions for interacting with OpenAI. Mostly related to the Portal, and how _it_ interacts with the VizQL Data Service, for now.

def generate_vizql_ds_query(question:str, data_model:list, user:AbstractBaseUser) -> dict:
    # Maybe later.
    return {}

def get_openai_api_settings() -> OpenAISettings:
    """
    Get the OpenAI API settings for the organization of the user, or the first organization if no user is provided.
    """
    return OpenAISettings.objects.first()

def assistant_has_tool(assistant:Assistant, tool_type:str) -> bool:
    """
    Check if the assistant has a tool of the specified type.
    
    tool_type: The type of tool to check for. Can be "code_interpreter", "file_search", etc.
    """
    if assistant is None or not hasattr(assistant, 'tools'):
        return False
    
    for tool in assistant.tools:
        if tool.type == tool_type:
            return True
    return False

def find_openai_assistant(assistant_name:str, assistant_tool_types:list=[], assistant_model:str=None, user:AbstractBaseUser=None) -> Assistant:
    """
    Find an OpenAI Assistant by name, tools, and model. Will paginate through the API to find the assistant with the properties, and return as soon as one matches (rather than paginating through all assistants).

    Name is required, tools and model are optional. assistant_tool_types is a list of tool types to check for, e.g. ["code_interpreter", "file_search"]. If no tools are provided, it will match any assistant with the specified name and model.
    
    If the user is provided, it will use the user's organization settings to find the assistant.
    If no user is provided, it will use the first organization's settings.
    Returns None if no assistant is found.
    """

    openai_settings = get_openai_api_settings()
    openai_client.api_key = openai_settings.api_key

    cursor = None
    while True:

        try:
            assistants = openai_client.beta.assistants.list(after=cursor)
            for assistant in assistants.data:
                # Check if the assistant matches the name, tools, and model
                if assistant.name == assistant_name:
                    if (len(assistant_tool_types) == 0 or all(assistant_has_tool(assistant, tool) for tool in assistant_tool_types)) and \
                    (assistant_model is None or assistant.model == assistant_model):
                        log_and_display_message(f"Found OpenAI Assistant: {assistant.name} with tools: {assistant.tools} and model: {assistant.model}", level="info")
                        return assistant
            
            # If we reach here, we did not find the assistant, so we need to paginate
            if assistants.has_more:
                cursor = assistants.last_id
            else:
                break

        except Exception as e:
            message = f"Something went wrong handling this request to the OpenAI API:\n\t{e}\n\t{traceback.format_exc()}"
            log_and_display_message(message=message, level="error")
            raise Exception(message)

    return None

def openai_api_chat_completion(user_prompt:str, system_prompt:str, user:AbstractBaseUser=None, response_format:typing.Any="text", max_tokens:int=0) -> str:
    """
    Send a prompt to the OpenAI API and return the response.

    system_prompt: The system prompt to use for the OpenAI API.
    user_prompt: The user prompt to use for the OpenAI API.
    
    These two are passed to the OpenAI API as a chat completion request.

    user: The user to use for the OpenAI API. If not provided, the first organization will be used.

    response_format: The format of the response. Can be "text" or a pydantic BaseModel. See: https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat&lang=python

    max_tokens: The maximum number of tokens to generate in the response. Defaults to the organization's setting, but can be overridden by passing a value here.
    """

    try:

        openai_settings = get_openai_api_settings()

        # Check if max_tokens is set, if not, use the organization's setting
        if max_tokens <= 0:
            max_tokens = openai_settings.max_completion_tokens

        openai_client.api_key = openai_settings.api_key

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        if response_format == "text":
            response = openai_client.chat.completions.create(
                model=openai_settings.preferred_model,
                messages=messages,
                max_completion_tokens=max_tokens,
            )
            response_content = response.choices[0].message.content
        else:
            # Leaving out max_tokens as structured output may be significantly larger than the max_tokens setting.
            response = openai_client.beta.chat.completions.parse(
                model=openai_settings.preferred_model,
                messages=messages,
                response_format=response_format,
            )
            response_content = response.choices[0].message.parsed

        log_and_display_message(f"[openai_api_chat_completion] Tokens used with model { openai_settings.preferred_model }: { response.usage.prompt_tokens } for prompt, { response.usage.completion_tokens } for completion; { response.usage.total_tokens } total", level="info")

        return response_content

    except Exception as e:
        # Raise through to views.py
        message = f"Something went wrong handling this request to the OpenAI API:\n\t{e}\n\t{traceback.format_exc()}"
        log_and_display_message(message=message, level="error")
        raise Exception(message)

def analyze_dataset(data:dict, question:str, user:AbstractBaseUser, output_format:str="") -> str:
    """
    Pass a dict/JSON data set to the OpenAI API, using chatcompletion to comment on a data set.
    """

    try:

        data_json = data
        if type(data) not in [dict, list]:
            try:
                data_json = json.loads(data)
            except Exception as e:
                message = f"Something went wrong handling this request to the OpenAI API:\n\t{e}\n\t{traceback.format_exc()}"
                log_and_display_message(message=message, level="error")
        data_as_df = pd.DataFrame.from_dict(data_json)

        # Convert the data into a summary format to send as context
        data_summary = data_as_df.to_string(index=False)

        # Define a prompts for data analysis
        system_prompt = f"You are a data analyst. Your job is to analyze the data provided and provide insights, trends, and suggestions for improvement."
        user_prompt = f"""
        Analyze the following dataset, based on the following original question: { question }

        Identify any notable trends, outliers, and potential areas for improvement.

        Data:
        {data_summary}
        """

        response_content = openai_api_chat_completion(user_prompt=user_prompt, system_prompt=system_prompt, user=user)

        if output_format in ["html", "xhtml"]:
            try:
                response_content_formated = markdown.markdown(text=response_content, output_format=output_format)
            except Exception as e:
                response_content_formated = response_content
        else:
            response_content_formated = response_content
        
        return response_content_formated

    except Exception as e:
        # Raise through to views.py
        message = f"Something went wrong analyzing this data set with the OpenAI API:\n\t{e}\n\t{traceback.format_exc()}"
        log_and_display_message(message=message, level="error")
        raise Exception(message)

def comment_on_dashboard_file(file_bytes:bytes, file_format:str, custom_prompt:str="", max_response_words:int=None, convert_to_html:bool=False, convert_to_slack_markdown:bool=True) -> str:
    """
    Upload a dashboard image or PDF to OpenAI and ask for comments. file_format can be "png", "jpg", or "pdf".
    
    A custom prompt can be provided, if not the following default will be used:

    "Can you comment on the data in this dashboard? No need for a general description of the dashboard, but focus on the insights, commentary, and suggestions related to the data."

    The max response length can also be set, but defaults to the organization's setting if not provided.
    """

    openai_settings = get_openai_api_settings()

    if max_response_words is None:
        max_response_words = openai_settings.max_completion_tokens

    try:

        openai_client.api_key = openai_settings.api_key

        file_image_formats = ["png", "jpg", "jpeg"]
        file_base64 = base64.b64encode(file_bytes).decode("utf-8")
        file_content_type = f"image/{file_format}" if file_format in file_image_formats else f"application/{file_format}"
        file_reference = f"dashboard.{file_format}"

        if len(custom_prompt) == 0:
            custom_prompt = f"Can you comment on the data in the attached dashboard file? No need for a general description of the dashboard, but focus on the insights, commentary, and suggestions related to the data. Please keep the response under { max_response_words } words."

        custom_prompt += f"\n\nThe file is in { file_format } format, the file name is { file_reference }."

        content_message_file = {}
        if file_format in file_image_formats:
            content_message_file = { 
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64, { file_base64 }",
                    "detail": "high"
                }
            }
        else:
            content_message_file = { 
                "type": "file",
                "file": {
                    "filename": file_reference,
                    "file_data": f"data:{ file_content_type };base64, { file_base64 }"
                }
            }
        
        # Call the OpenAI API to analyze the dataset
        response = openai_client.chat.completions.create(
            model=openai_settings.preferred_model,
            messages=[
                { 
                    "role": "user",
                    "content": [
                        content_message_file,
                        { "type": "text", "text": custom_prompt }
                    ]
                }
            ],
            max_tokens=max_response_words,
            temperature=0.5
        )

        response_content = response.choices[0].message.content
        if convert_to_html:
            try:
                response_content_formated = markdown.markdown(text=response_content, output_format="html")
            except Exception as e:
                response_content_formated = response_content
        elif convert_to_slack_markdown:
            response_content_formated = helpers_other.convert_to_slack_markdown(response_content)
        else:
            response_content_formated = response_content

        log_and_display_message(f"[comment_on_dashboard_file] Tokens used with model { openai_settings.preferred_model }: { response.usage.prompt_tokens } for prompt, { response.usage.completion_tokens } for completion; { response.usage.total_tokens } total", level="info")
        
        return response_content_formated

    except Exception as e:
        # Raise through to views.py
        message = f"Something went wrong handling this request to the OpenAI API:\n\t{e}\n\t{traceback.format_exc()}"
        log_and_display_message(message=message, level="error")
        raise Exception(message)
