from django.db import models
from encrypted_model_fields.fields import EncryptedCharField
from django.contrib.auth import get_user_model

# Core Models
User = get_user_model()

# Slack-related settings

class SlackCredential(models.Model):
    slack_app = models.TextField()
    slack_workspace_id = models.TextField(null=True, blank=True)
    slack_workspace_bot_user_id = models.TextField(null=True, blank=True)
    slack_workspace_bot_user_access_token = EncryptedCharField(null=True, blank=True)

    def __repr__(self):
        return f"<SlackCredential { self.id }>"
    
class SlackChannelMapping(models.Model):
    # Not using foreign keys, as we might not want to tie this down to one location where either of these is specified.

    class SlackChannelType(models.TextChoices):
        public_channel = "public_channel", "Public Channel"
        private_channel = "private_channel"
        im = "im", "Direct Message"
        mpim = "mpim", "Group DM"

    slack_workspace_id = models.TextField(null=False, blank=False)
    slack_channel_id = models.TextField(max_length=64, null=False, blank=False)
    slack_channel_name = models.TextField(null=False, blank=False)
    slack_channel_email = models.TextField(null=True, blank=True) # Applies to users; we don't store email addresses for channels.
    slack_channel_type = models.TextField(max_length=128, choices=SlackChannelType.choices, null=False, blank=False, default=SlackChannelType.public_channel)

    def __repr__(self):
        return f"<SlackChannelMapping { self.slack_channel_name }>"

# OpenAI-related settings
class OpenAISettings(models.Model):
    api_key = EncryptedCharField(null=True, blank=True)
    preferred_model = models.TextField(default="gpt-4o-mini", null=False, blank=False)
    max_completion_tokens = models.IntegerField(default=500, null=False, blank=False)

    def __repr__(self):
        return f"<OpenAISettings { self.id }>"
    
# "Internal" models
class DataQuestion(models.Model):
    """
    A data question can be captured from any source, could be IM or could be an Orbit One module. This saves the question and its status.
    """

    class Source(models.TextChoices):
        SLACK = "SLACK", "Slack"
        TEAMS = "TEAMS", "Teams"
        GOOGLE_CHAT = "GOOGLE_CHAT", "Google Chat"
        ORBIT_ONE = "ORBIT_ONE", "Orbit One"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        PENDING = "PENDING", "Pending"
        ANSWERED = "ANSWERED", "Answered"

    source = models.TextField(choices=Source.choices, default=Source.SLACK)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    question = models.TextField()
    status = models.TextField(choices=Status.choices, default=Status.OPEN)
    top_data_sets = models.JSONField(null=True, blank=True) # List of data sets that were presented to the user in the first step of the question. This is a list of Entities with their IDs, relevant fields, other information complemented by OpenAI.

class DataQuestionAnswer(models.Model):
    """
    A data question answer is the answer to a data question. One question can have multiple answers.
    """

    data_question = models.ForeignKey(DataQuestion, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    with_data_set = models.JSONField(null=True, blank=True) # Will contain one of the data sets that were presented to the user in the first step of the question. In other words, _one_ of the top_data_sets from the question.
    answer_text = models.TextField(null=True, blank=True)
    # The answer may have an image with e.g. a chart, which can be stored in Cloud Storage, referred to via answer_image_storage_file_path.
    answer_image_storage_file_path = models.TextField(null=True, blank=True)
    errors = models.TextField(null=True, blank=True) # Errors that occurred while generating the answer. Plain text for now.