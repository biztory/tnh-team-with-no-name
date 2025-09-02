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
    
# OpenAI-related settings
class OpenAISettings(models.Model):
    api_key = EncryptedCharField(null=True, blank=True)
    preferred_model = models.TextField(default="gpt-4o-mini", null=False, blank=False)
    max_completion_tokens = models.IntegerField(default=500, null=False, blank=False)

    def __repr__(self):
        return f"<OpenAISettings { self.id }>"
