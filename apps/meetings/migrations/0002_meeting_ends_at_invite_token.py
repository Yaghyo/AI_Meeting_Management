import uuid

from django.db import migrations, models


def assign_invite_tokens(apps, schema_editor):
    Meeting = apps.get_model('meetings', 'Meeting')
    for meeting in Meeting.objects.filter(invite_token__isnull=True).iterator():
        meeting.invite_token = uuid.uuid4()
        meeting.save(update_fields=['invite_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('meetings', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='meeting',
            name='ends_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='meeting',
            name='invite_token',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.RunPython(assign_invite_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='meeting',
            name='invite_token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
