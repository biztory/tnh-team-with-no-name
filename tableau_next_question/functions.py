# App-wide helper functions

# imports - Python/general
import logging, inspect, os

# imports - Django
from django.contrib import messages

# imports - our app
# N/A

# For reporting messages, and errors.
logger = logging.getLogger(__name__)

# General functions

def log_and_display_message(message:str, level:str="info", context:dict=None, no_message:bool=False):
    '''
    Function that combines log (backend) and message (frontend) handling. In other words, a shortcut to both log and display messages. Mostly designed to prevent us having to repeat too much code when we want to do this.
    '''
    # Determine where the call to this function took place
    logging_prefix = ""
    try:
        stack_this_function = next((i for i, f in enumerate(inspect.stack()) if f.function == "log_and_display_message"))
        if stack_this_function is not None:
            # The next frame in the stack should be the one we called log_and_display_message from
            stack_calling_function = inspect.stack()[stack_this_function + 1]
            # The app name should be part of [1] which s the file path.
            called_from_app = stack_calling_function[1].split(os.sep)[-2]
            logging_prefix = f"[{ called_from_app }] "
            # Specify if it's not "just" views.py
            called_from_app_module = stack_calling_function[1].split(os.sep)[-1].replace(".py", "")
            if called_from_app_module != "views":
                logging_prefix = f"[{ called_from_app } { called_from_app_module }] "
    except Exception as e:
        pass # Don't really need to "complain" here

    level_mapping = {
        "debug": {
            "logger": logger.debug,
            "messages": messages.info,
        },
        "success": {
            "logger": logger.info,
            "messages": messages.success,
        },
        "info": {
            "logger": logger.info,
            "messages": messages.info,
        },
        "warning": {
            "logger": logger.warning,
            "messages": messages.warning,
        },
        "warn": {
            "logger": logger.warn,
            "messages": messages.warning,
        },
        "error": {
            "logger": logger.error,
            "messages": messages.error,
        },
    }
    try:
        level_mapping[level]["logger"](f"{ logging_prefix }{ message }")
        if context is not None and not no_message:
            if "messages" not in context:
                context["messages"] = []
            context["messages"].append({ "severity": level, "message": message})
    except Exception as e:
        logger.error(f"There was an error logging the error message we want to log...\n\tCause:\n\t\t{ e }\n\tOriginal message:\n\t\t{ message }")
