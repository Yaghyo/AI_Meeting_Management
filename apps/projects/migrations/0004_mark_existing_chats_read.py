from django.conf import settings
from django.db import migrations


def mark_existing_chats_read(apps, schema_editor):
    DirectMessage = apps.get_model('projects', 'DirectMessage')
    GroupMessage = apps.get_model('projects', 'GroupMessage')
    for message in DirectMessage.objects.all().iterator():
        message.read_by.add(message.sender_id, message.recipient_id)
    for message in GroupMessage.objects.select_related('group').iterator():
        member_ids = list(message.group.members.values_list('id', flat=True))
        message.read_by.add(message.sender_id, *member_ids)


class Migration(migrations.Migration):
    dependencies = [
        ('projects', '0003_directmessage_read_by_groupmessage_read_by'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [migrations.RunPython(mark_existing_chats_read, migrations.RunPython.noop)]
