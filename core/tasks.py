# General imports
import sys, datetime, logging
from django_q.tasks import schedule, Schedule, async_task, AsyncTask

# App imports
# Models
from core.models import SlackCredential
# Functions
import core.functions.slack as slack

# Django-Q2: To effectively schedule a task, what we need to do is add it through the Django admin interface, as a scheduled task. It can be done through code as well, but hey.
# Moreover, for tasks to effectively be processed, "python manage.py qcluster" must be running. In development, that is to be done interactively. On Digital Ocean, it is done through a worker with that run command.

def respond_to_data_question_task(source:str, question:str, kwargs:dict) -> AsyncTask:
    """
    Respond to a data question from a user in "Slack", "Teams", or "Google Chat" (those are also the respective values allowed for source). 

    Question is to contain the question written by the user, which can be further narrowed down by our function here.

    Kwargs is a dictionary containing additional information that may vary depending on the source. For example, in Slack, it may contain the user ID.
    """
    return async_task("core.functions.ask_your_data.respond_to_data_question", source=source, question=question, kwargs=kwargs)

def respond_to_data_question_part_deux_task(data_question_id:int, entity_id:int, kwargs:dict) -> AsyncTask:
    """
    Part two of responding to a data question from a user in "Slack", "Teams", or "Google Chat". This means that in the first part, the user has been presented with a list of data sets to answer the question with, and now they have chosen one. This was stored as a DataQuestion object in the database, and now we need to process it.

    As a next step, we're going to pick up the DataQuestion, and use the information in it as well as the data set to answer the question.

    Kwargs is a dictionary containing additional information that may vary depending on the source. For example, in Slack, it may contain the Channel ID and thread we'll use to respond.
    """
    return async_task("ask_your_data.functions.respond_to_data_question_part_deux", data_question_id=data_question_id, entity_id=entity_id, kwargs=kwargs)

def test_task():
    with open("test_task.txt", "a") as f:
        f.write(f"Here we are at { datetime.datetime.now(datetime.timezone.utc) }\n")


# "Meta" functions used to manage the scheduled tasks.

def print_task_result(task):
    print(f"Task \"{ task }\" completed.")
