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
from django import template
from teams.models import Team, Invite
from videos.models import Action
from apps.widget import video_cache
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from widget.views import base_widget_params
from django.utils import simplejson as json

DEV_OR_STAGING = getattr(settings, 'DEV', False) or getattr(settings, 'STAGING', False)
ACTIONS_ON_PAGE = getattr(settings, 'ACTIONS_ON_PAGE', 10)

ALL_LANGUAGES_DICT = dict([(val, _(name)) for val, name in settings.ALL_LANGUAGES])

register = template.Library()

@register.filter
def can_approve_application(team, user):
    if not user.is_authenticated():
        return False
    return team.can_approve_application(user)

@register.filter
def can_invite_to_team(team, user):
    if not user.is_authenticated():
        return False
    return team.can_invite(user)

@register.filter
def can_add_video_to_team(team, user):
    return team.can_add_video(user)    

@register.filter
def can_edit_video(tv, user):
    return tv.can_edit(user) 

@register.filter
def can_remove_video(tv, user):
    return tv.can_remove(user) 

@register.filter
def is_team_manager(team, user):
    if not user.is_authenticated():
        return False
    return team.is_manager(user)

@register.filter
def is_team_member(team, user):
    if not user.is_authenticated():
        return False
    return team.is_member(user)

@register.inclusion_tag('teams/_team_select.html', takes_context=True)
def team_select(context, team):
    user = context['user']
    qs = Team.objects.exclude(pk=team.pk).filter(users=user)
    return {
        'team': team,
        'objects': qs,
        'can_create_team': DEV_OR_STAGING or (user.is_superuser and user.is_active)
    }

@register.inclusion_tag('teams/_team_activity.html', takes_context=True)    
def team_activity(context, team):
    from utils.orm import load_related_fk
    
    videos_ids = team.teamvideo_set.values_list('video_id', flat=True)
    action_qs = Action.objects.select_related('video', 'user', 'language', 'language__video').filter(video__pk__in=videos_ids)[:ACTIONS_ON_PAGE]

    context['videos_actions'] = action_qs
    
    return context

@register.inclusion_tag('teams/_team_add_video_select.html', takes_context=True)    
def team_add_video_select(context):
    user = context['user']
    if user.is_authenticated():
        qs = Team.objects.filter(users=user)
        context['teams'] = [item for item in qs if item.can_add_video(user)]
    return context 

@register.inclusion_tag('teams/_team_video_detail.html', takes_context=True)  
def team_video_detail(context, team_video):
    context['team_video'] = team_video
    video_url = team_video.video.get_video_url()
    context['team_video_widget_params'] = base_widget_params(context['request'], {
        'video_url': video_url, 
        'base_state': {},
        'effectiveVideoURL': video_url
    })
    return context

@register.inclusion_tag('teams/_complete_team_video_detail.html', takes_context=True)  
def complete_team_video_detail(context, team_video):
    context['team_video'] = team_video
    return context

@register.inclusion_tag('teams/_team_video_lang_detail.html', takes_context=True)  
def team_video_lang_detail(context, lang, team):
    #from utils.orm import load_related_fk
    
    context['team_video'] = team.teamvideo_set.select_related('video').get(video__id=lang.video_id)
    context['lang'] = lang
    return context

@register.inclusion_tag('teams/_invite_friends_to_team.html', takes_context=True)  
def invite_friends_to_team(context, team):
    context['invite_message'] = _(u'Can somebody help me subtitle these videos? %(url)s') % {
            'url': team.get_site_url()
        }
    return context

@register.inclusion_tag('teams/_team_video_lang_list.html', takes_context=True)  
def team_video_lang_list(context, video, max_items=6):
    """
    max_items: if there are more items than max_items, they will be truncated to X more.
    """
    return  {
        'sub_statuses': video_cache.get_video_languages_verbose(video.video_id, max_items),
        'video': video
        }

