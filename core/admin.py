from django.contrib import admin

# Register your models here.

from core.models import SlackCredential, OpenAISettings
admin.site.register(SlackCredential)
admin.site.register(OpenAISettings)