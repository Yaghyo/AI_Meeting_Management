from django.contrib import admin
from .models import Project, ProjectGroup

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    search_fields = ('name',)


@admin.register(ProjectGroup)
class ProjectGroupAdmin(admin.ModelAdmin):
    filter_horizontal = ('members',)
