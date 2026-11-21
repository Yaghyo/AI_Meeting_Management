from django.contrib import admin
from .models import Meeting, MeetingParticipant, TranscriptLine

admin.site.register(Meeting)
admin.site.register(MeetingParticipant)
admin.site.register(TranscriptLine)
