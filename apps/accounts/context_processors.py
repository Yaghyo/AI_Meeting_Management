from django.contrib.auth import get_user_model
from django.db.models import Count

from apps.projects.models import ProjectGroup
from apps.projects.models import DirectMessage, GroupMessage
from .permissions import is_company_admin


def sidebar_items(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    if is_company_admin(request.user):
        groups = ProjectGroup.objects.select_related('project').order_by('project__name')
    else:
        groups = ProjectGroup.objects.filter(members=request.user).select_related('project').order_by('project__name')
    groups = list(groups)
    group_counts = dict(
        GroupMessage.objects.filter(group_id__in=[group.pk for group in groups])
        .exclude(sender=request.user).exclude(read_by=request.user)
        .values('group_id').annotate(total=Count('pk')).values_list('group_id', 'total')
    )
    for group in groups:
        group.unread_count = group_counts.get(group.pk, 0)

    people = list(get_user_model().objects.filter(is_active=True).exclude(pk=request.user.pk).order_by('username'))
    direct_counts = dict(
        DirectMessage.objects.filter(recipient=request.user, sender_id__in=[person.pk for person in people])
        .exclude(read_by=request.user)
        .values('sender_id').annotate(total=Count('pk')).values_list('sender_id', 'total')
    )
    for person in people:
        person.unread_count = direct_counts.get(person.pk, 0)
    return {'sidebar_groups': groups, 'sidebar_people': people}
