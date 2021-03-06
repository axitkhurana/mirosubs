# Universal Subtitles, universalsubtitles.org
# 
# Copyright (C) 2010 Participatory Culture Foundation
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see 
# http://www.gnu.org/licenses/agpl-3.0.html.

#  Based on: http://www.djangosnippets.org/snippets/73/
#
#  Modified by Sean Reifschneider to be smarter about surrounding page
#  link context.  For usage documentation see:
#
#     http://www.tummy.com/Community/Articles/django-pagination/
from django.contrib import admin
from teams.models import Team, TeamMember, TeamVideo
from videos.models import Video
from django.utils.translation import ugettext_lazy as _

class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'membership_policy', 'video_policy', 'is_visible', 'highlight')
    list_filter = ('highlight',)
    actions = ['highlight', 'unhighlight']
    
    def highlight(self, request, queryset):
        queryset.update(highlight=True)
    highlight.short_description = _('Feature teams')
    
    def unhighlight(self, request, queryset):
        queryset.update(highlight=False)
    unhighlight.short_description = _('Unfeature teams')

class TeamMemberAdmin(admin.ModelAdmin):
    search_fields = ('team__name', 'user__username', 'user__first_name', 'user__last_name')
    list_display = ('team', 'user', 'is_manager')

class TeamVideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'description')

admin.site.register(TeamMember, TeamMemberAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(TeamVideo, TeamVideoAdmin)
