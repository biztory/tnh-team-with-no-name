from django.contrib import admin

# Register your models here.

from core.models import SlackCredential, SlackChannelMapping, OpenAISettings
admin.site.register(SlackCredential)
admin.site.register(SlackChannelMapping)
admin.site.register(OpenAISettings)