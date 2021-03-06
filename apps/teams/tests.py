# -*- coding: utf-8 -*-
from django.test import TestCase
from django.core.urlresolvers import reverse
from os import path
from django.conf import settings
from teams.models import Team, Invite, TeamVideo, Application, TeamMember, TeamVideoLanguage
from messages.models import Message
from videos.models import Video, VIDEO_TYPE_YOUTUBE, SubtitleLanguage
from django.db.models import ObjectDoesNotExist
from auth.models import CustomUser as User
from django.contrib.contenttypes.models import ContentType
from teams import tasks
from django.core import mail
from datetime import datetime, timedelta
from django.core.management import call_command
from django.core import mail

class TestCommands(TestCase):
    
    fixtures = ["test.json"]
    
    def setUp(self):
        self.team = Team(name='test', slug='test')
        self.team.save()
        
        self.user = User.objects.all()[:1].get()
        self.user.is_active = True
        self.user.changes_notification = True
        self.user.email = 'test@test.com'
        self.user.save()
        
        self.tm = TeamMember(team=self.team, user=self.user)
        self.tm.save()

        v1 = Video.objects.all()[:1].get()
        self.tv1 = TeamVideo(team=self.team, video=v1, added_by=self.user)
        self.tv1.save()
        
        v2 = Video.objects.exclude(pk=v1.pk)[:1].get()
        self.tv2 = TeamVideo(team=self.team, video=v2, added_by=self.user)
        self.tv2.save()
        
    def test_new_team_video_notification(self):
        #mockup for send_templated_email to test context of email
        import utils
        
        send_templated_email = utils.send_templated_email
        
        def send_templated_email_mockup(to, subject, body_template, body_dict, *args, **kwargs):
            send_templated_email_mockup.context = body_dict
            send_templated_email(to, subject, body_template, body_dict, *args, **kwargs)
        
        utils.send_templated_email = send_templated_email_mockup
        
        #check initial data
        self.assertEqual(self.team.teamvideo_set.count(), 2)
        self.assertEqual(self.team.users.count(), 1)
        
        today = datetime.today()
        date = today - timedelta(hours=24)
        
        #test notification about two new videos
        TeamVideo.objects.filter(pk__in=[self.tv1.pk, self.tv2.pk]).update(created=datetime.today())
        self.assertEqual(TeamVideo.objects.filter(created__gte=date).count(), 2)
        mail.outbox = []
        call_command('new_team_video_notification')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertEqual(len(send_templated_email_mockup.context['team_videos']), 2)
        
        #test if user turn off notification
        self.user.is_active = False
        self.user.save()
        mail.outbox = []
        call_command('new_team_video_notification')
        self.assertEqual(len(mail.outbox), 0)
        
        self.user.is_active = True
        self.user.changes_notification = False
        self.user.save()
        mail.outbox = []
        call_command('new_team_video_notification')
        self.assertEqual(len(mail.outbox), 0)        

        self.user.changes_notification = True
        self.user.save()
        self.tm.changes_notification = False
        self.tm.save()
        mail.outbox = []
        call_command('new_team_video_notification')
        self.assertEqual(len(mail.outbox), 0)    

        self.tm.changes_notification = True
        self.tm.save()
        
        #test notification if one video is new
        past_date = today - timedelta(days=2)
        TeamVideo.objects.filter(pk=self.tv1.pk).update(created=past_date)
        self.assertEqual(TeamVideo.objects.filter(created__gte=date).count(), 1)
        mail.outbox = []
        call_command('new_team_video_notification')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(send_templated_email_mockup.context['team_videos']), 1)
        self.assertEqual(send_templated_email_mockup.context['team_videos'][0], self.tv2)
        
        #test notification if all videos are old
        TeamVideo.objects.filter(pk__in=[self.tv1.pk, self.tv2.pk]).update(created=past_date)
        self.assertEqual(TeamVideo.objects.filter(created__gte=date).count(), 0)
        mail.outbox = []
        call_command('new_team_video_notification')
        self.assertEqual(len(mail.outbox), 0)
        
class TestTasks(TestCase):
    
    fixtures = ["staging_users.json", "staging_videos.json", "staging_teams.json"]
    
    def setUp(self):
        self.tv = TeamVideo.objects.all()[0]
        self.sl = SubtitleLanguage.objects.exclude(language='')[0]
        self.team = Team.objects.all()[0]
        tv = TeamVideo(team=self.team, video=self.sl.video, added_by=self.team.users.all()[:1].get())
        tv.save()
        
    def test_tasks(self):
        #TODO: improve this
        result = tasks.update_team_video.delay(self.tv.video_id)
        if result.failed():
            self.fail(result.traceback)
        
        result = tasks.update_one_team_video.delay(self.team.id)
        if result.failed():
            self.fail(result.traceback)
    
    def test_update_team_video_for_sl(self):
        result = tasks.update_team_video_for_sl.delay(self.sl.id)
        if result.failed():
            self.fail(result.traceback)        
    
    def test_add_video_notification(self):
        team = self.tv.team
        
        #at list one user should receive email
        self.assertTrue(team.users.count() > 1)
        mail.outbox = []
        
        result = tasks.add_video_notification.delay(self.tv.id)
        if result.failed():
            self.fail(result.traceback)        

        self.assertEqual(len(mail.outbox), 2)
        
        for email in mail.outbox:
            u = team.users.get(email=email.to[0])
            self.assertTrue(u != self.tv.added_by and u.is_active and u.changes_notification)
        
        #test changes_notification and is_active
        mail.outbox = []
        some_member = team.users.exclude(pk=self.tv.added_by_id)[:1].get()
        some_member.changes_notification = False
        some_member.save()

        result = tasks.add_video_notification.delay(self.tv.id)
        if result.failed():
            self.fail(result.traceback)        
        
        self.assertEqual(len(mail.outbox), 1)
        
        mail.outbox = []
        some_member.changes_notification = True
        some_member.is_active = False
        some_member.save()        

        result = tasks.add_video_notification.delay(self.tv.id)
        if result.failed():
            self.fail(result.traceback)        
        
        self.assertEqual(len(mail.outbox), 1)

        mail.outbox = []
        some_member.is_active = True
        some_member.save()    
        
        tm = TeamMember.objects.get(team=team, user=some_member)
        tm.changes_notification = False
        tm.save()

        result = tasks.add_video_notification.delay(self.tv.id)
        if result.failed():
            self.fail(result.traceback)        
        
        self.assertEqual(len(mail.outbox), 1)
                
class TeamsTest(TestCase):
    
    fixtures = ["staging_users.json", "staging_videos.json", "staging_teams.json"]
    
    def setUp(self):
        self.auth = {
            "username": u"admin",
            "password": u"admin"
        }
        self.user = User.objects.get(username=self.auth["username"])

    def _add_team_video(self, team, language, video_url):
        mail.outbox = []
        data = {
            "description": u"",
            "language": language,
            "title": u"",
            "video_url": video_url,
            "thumbnail": u"",
        }
        url = reverse("teams:add_video", kwargs={"slug": team.slug})
        self.client.post(url, data)
        
    def _set_my_languages(self, *args):
        from auth.models import UserLanguage
        for ul in self.user.userlanguage_set.all():
            ul.delete()
        for lang in args:
            ul = UserLanguage(
                user=self.user,
                language=lang)
            ul.save()
        self.user = User.objects.get(id=self.user.id)

    def _create_new_team_video(self):
        self.client.login(**self.auth)
        
        response = self.client.get(reverse("teams:create"))
        
        data = {
            "description": u"",
            "video_url": u"",
            "membership_policy": u"4",
            "video_policy": u"1",
            "logo": u"",
            "slug": u"new-team",
            "name": u"New team"
        }

        response = self.client.post(reverse("teams:create"), data)
        self.assertEqual(response.status_code, 302)

        team = Team.objects.get(slug=data['slug'])

        self._add_team_video(team, u'en', u"http://videos.mozilla.org/firefox/3.5/switch/switch.ogv")
        
        tv = TeamVideo.objects.order_by('-id')[0]
        
        result = tasks.update_one_team_video.delay(tv.id)
        
        if result.failed():
            self.fail(result.traceback)

        return team, tv

    def _make_data(self, video_id, lang):
        import os
        return {
            'language': lang,
            'video': video_id,
            'subtitles': open(os.path.join(os.path.dirname(__file__), '../videos/fixtures/test.srt'))
            }

    def _video_lang_list(self, team):
        url = reverse("teams:detail", kwargs={"slug": team.slug})
        response = self.client.get(url)
        return response.context['team_video_md_list']
    
    def test_add_video(self):
        self.client.login(**self.auth)
        
        team = Team.objects.get(pk=1)
        TeamMember.objects.get_or_create(user=self.user, team=team)
        
        self.assertTrue(team.users.count() > 1)
        
        for tm in team.members.all():
            tm.changes_notification = True
            tm.save()
            tm.user.is_active = True
            tm.user.changes_notification = True
            tm.user.save()
        
        self._add_team_video(team, u'en', u"http://videos.mozilla.org/firefox/3.5/switch/switch.ogv")
        
    def test_detail_contents(self):
        team, new_team_video = self._create_new_team_video()
        self.assertEqual(1, new_team_video.video.subtitlelanguage_set.count())

        # The video should be in the list. 
        self.assertEqual(1, len(self._video_lang_list(team)))

    def test_detail_contents_original_subs(self):
        team, new_team_video = self._create_new_team_video()

        # upload some subs to the new video. make sure it still appears.
        data = self._make_data(new_team_video.video.id, 'en')
        response = self.client.post(reverse('videos:upload_subtitles'), data)

        url = reverse("teams:detail", kwargs={"slug": team.slug})
        response = self.client.get(url)

        # The video should be in the list.
        self.assertEqual(1, len(response.context['team_video_md_list']))

        # but we should see no "no work" message
        self.assertTrue('allow_noone_language' not in response.context or \
                            not response.context['allow_noone_language'])

    def test_detail_contents_unrelated_video(self):
        team, new_team_video = self._create_new_team_video()
        self._set_my_languages('en', 'ru')
        # now add a Russian video with no subtitles.
        self._add_team_video(
            team, u'ru',
            u'http://upload.wikimedia.org/wikipedia/commons/6/61/CollateralMurder.ogv')

        team = Team.objects.get(id=team.id)

        self.assertEqual(2, team.teamvideo_set.count())

        # both videos should be in the list
        self.assertEqual(2, len(self._video_lang_list(team)))

        # but the one with russian subs should be second.
        video_langs = self._video_lang_list(team)
        self.assertEqual('ru', video_langs[1].video.subtitle_language().language)

    def test_one_tvl(self):
        team, new_team_video = self._create_new_team_video()
        self._set_my_languages('ko')
        url = reverse("teams:detail", kwargs={"slug": team.slug})
        response = self.client.get(url)
        self.assertEqual(1, len(response.context['team_video_md_list']))

    def test_no_dupes_without_buttons(self):
        team, new_team_video = self._create_new_team_video()
        self._set_my_languages('ko', 'en')

        self.client.post(
            reverse('videos:upload_subtitles'), 
            self._make_data(new_team_video.video.id, 'en'))

        self.client.post(
            reverse('videos:upload_subtitles'), 
            self._make_data(new_team_video.video.id, 'es'))

        url = reverse("teams:detail", kwargs={"slug": team.slug})
        response = self.client.get(url)
        self.assertEqual(1, len(response.context['team_video_md_list']))

    def test_views(self):
        self.client.login(**self.auth)
        
        #------- create ----------
        response = self.client.get(reverse("teams:create"))
        self.failUnlessEqual(response.status_code, 200)
        
        data = {
            "description": u"",
            "video_url": u"",
            "membership_policy": u"4",
            "video_policy": u"1",
            "logo": u"",
            "slug": u"new-team",
            "name": u"New team"
        }
        response = self.client.post(reverse("teams:create"), data)
        self.failUnlessEqual(response.status_code, 302)
        team = Team.objects.get(slug=data['slug'])

        #---------- index -------------
        response = self.client.get(reverse("teams:index"))
        self.failUnlessEqual(response.status_code, 200) 
               
        response = self.client.get(reverse("teams:index"), {'q': 'vol'})
        self.failUnlessEqual(response.status_code, 200)
        
        data = {
            "q": u"vol",
            "o": u"date"
        }
        response = self.client.get(reverse("teams:index"), data)
        self.failUnlessEqual(response.status_code, 200)

        response = self.client.get(reverse("teams:index"), {'o': 'my'})
        self.failUnlessEqual(response.status_code, 200)
                
        #---------- edit ------------
        url = reverse("teams:edit", kwargs={"slug": team.slug})
        response = self.client.get(url)

        self.failUnlessEqual(response.status_code, 200)
        
        data = {
            "logo": open(path.join(settings.MEDIA_ROOT, "test/71600102.jpg"), "rb")
        }
        url = reverse("teams:edit_logo", kwargs={"slug": team.slug})
        response = self.client.post(url, data)
        self.failUnlessEqual(response.status_code, 200)
        team = Team.objects.get(pk=team.pk)
        self.assertTrue(team.logo)
        
        data = {
            "name": u"New team",
            "video_url": u"http://www.youtube.com/watch?v=tGsHDUdw8As",
            "membership_policy": u"4",
            "video_policy": u"1",
            "description": u"",
            "logo": open(path.join(settings.MEDIA_ROOT, "test/71600102.jpg"), "rb")
        }
        url = reverse("teams:edit", kwargs={"slug": team.slug})
        response = self.client.post(url, data)
        self.failUnlessEqual(response.status_code, 302)
        video = Video.objects.get(videourl__type=VIDEO_TYPE_YOUTUBE, videourl__videoid='tGsHDUdw8As')
        team = Team.objects.get(pk=team.pk)
        self.assertEqual(team.video, video)
        
        #-------------- edit members ---------------
        url = reverse("teams:edit_members", kwargs={"slug": team.slug})
        response = self.client.get(url)
        self.failUnlessEqual(response.status_code, 200)
        
        #-------------- edit videos -----------------
        url = reverse("teams:edit_videos", kwargs={"slug": team.slug})
        response = self.client.get(url)
        self.failUnlessEqual(response.status_code, 200)

        url = reverse("teams:edit", kwargs={"slug": "volunteer1"})
        response = self.client.get(url)
        self.failUnlessEqual(response.status_code, 404)

        self.client.logout()
        
        url = reverse("teams:edit", kwargs={"slug": "volunteer"})
        response = self.client.get(url)
        self.failUnlessEqual(response.status_code, 302)
        
        self.client.login(**self.auth)
        #-------------- applications ----------------
        url = reverse("teams:applications", kwargs={"slug": team.slug})
        response = self.client.get(url)
        self.failUnlessEqual(response.status_code, 200)
        
        #------------ detail ---------------------
        url = reverse("teams:detail", kwargs={"slug": team.slug})
        response = self.client.get(url)
        self.failUnlessEqual(response.status_code, 200)
        
        url = reverse("teams:detail", kwargs={"slug": team.pk})
        response = self.client.get(url)
        self.failUnlessEqual(response.status_code, 200)
        
        url = reverse("teams:detail", kwargs={"slug": team.slug})
        response = self.client.get(url)
        self.failUnlessEqual(response.status_code, 200)
        
        url = reverse("teams:detail", kwargs={"slug": team.slug})
        response = self.client.get(url, {'q': 'Lions'})
        self.failUnlessEqual(response.status_code, 200)
        
        url = reverse("teams:detail", kwargs={"slug": team.slug})
        response = self.client.get(url, {'q': 'empty result'})
        self.failUnlessEqual(response.status_code, 200)        
        
        #------------ detail members -------------
        
        url = reverse("teams:detail_members", kwargs={"slug": team.slug})
        response = self.client.get(url)
        self.failUnlessEqual(response.status_code, 200)
        
        url = reverse("teams:detail_members", kwargs={"slug": team.slug})
        response = self.client.get(url, {'q': 'test'})
        self.failUnlessEqual(response.status_code, 200)

        #-------------members activity ---------------
        #Deprecated
        #url = reverse("teams:members_actions", kwargs={"slug": team.slug})
        #response = self.client.get(url)
        #self.failUnlessEqual(response.status_code, 200)        
        
        #------------- add video ----------------------
        self.client.login(**self.auth)
        
        data = {
            "languages-MAX_NUM_FORMS": u"",
            "description": u"",
            "language": u"en",
            "title": u"",
            "languages-0-language": u"be",
            "languages-0-id": u"",
            "languages-TOTAL_FORMS": u"1",
            "video_url": u"http://www.youtube.com/watch?v=Hhgfz0zPmH4&feature=grec_index",
            "thumbnail": u"",
            "languages-INITIAL_FORMS": u"0"
        }
        tv_len = team.teamvideo_set.count()
        url = reverse("teams:add_video", kwargs={"slug": team.slug})
        response = self.client.post(url, data)
        self.assertEqual(tv_len+1, team.teamvideo_set.count())
        self.assertRedirects(response, reverse("teams:team_video", kwargs={"team_video_pk": 3}))

        #-------edit team video -----------------
        team = Team.objects.get(pk=1)
        tv = team.teamvideo_set.get(pk=1)
        tv.title = ''
        tv.description = ''
        tv.save()
        data = {
            "languages-MAX_NUM_FORMS": u"",
            "languages-INITIAL_FORMS": u"0",
            "title": u"change title",
            "languages-0-language": u"el",
            "languages-0-id": u"",
            "languages-TOTAL_FORMS": u"1",
            "languages-0-completed": u"on",
            "thumbnail": u"",
            "description": u"and description"
        }
        url = reverse("teams:team_video", kwargs={"team_video_pk": tv.pk})
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("teams:team_video", kwargs={"team_video_pk": tv.pk}))        
        tv = team.teamvideo_set.get(pk=1)
        self.assertEqual(tv.title, u"change title")
        self.assertEqual(tv.description, u"and description")
        
        #-----------delete video -------------
        url = reverse("teams:remove_video", kwargs={"team_video_pk": tv.pk})
        response = self.client.post(url)
        self.failUnlessEqual(response.status_code, 200)
        try:
            team.teamvideo_set.get(pk=1)
            self.fail()
        except ObjectDoesNotExist:
            pass
        
        #----------inviting to team-----------
        user2 = User.objects.get(username="alerion")
        TeamMember.objects.filter(user=user2, team=team).delete()
        
        data = {
            "username": user2.username,
            "note": u"asd",
            "team_id": team.pk
        }
        response = self.client.post(reverse("teams:invite"), data)
        self.failUnlessEqual(response.status_code, 200)

        invite = Invite.objects.get(user__username=user2.username, team=team)
        ct = ContentType.objects.get_for_model(Invite)
        message = Message.objects.get(object_pk=invite.pk, content_type=ct, user=user2)
        
        members_count = team.members.count()
        
        self.client.login(username = user2.username, password ='alerion')
        url = reverse("teams:accept_invite", kwargs={"invite_pk": invite.pk})
        response = self.client.get(url)
        
        self.assertEqual(members_count+1, team.members.count())
        
        self.client.login(**self.auth)

        url = reverse("teams:edit_members", kwargs={"slug": team.slug})
        response = self.client.get(url)
        self.failUnlessEqual(response.status_code, 200)
 
        data = {
            "ot": u"desc",
            "page": u"1",
            "o": u"username"
        }
        url = reverse("teams:edit_members", kwargs={"slug": team.slug})
        response = self.client.get(url, data)
        self.failUnlessEqual(response.status_code, 200) 
        
        self.assertFalse(team.is_manager(user2))
        
        url = reverse("teams:promote_member", kwargs={"user_pk": user2.pk, "slug": team.slug})
        response = self.client.get(url)
        self.assertRedirects(response, reverse("teams:edit_members", kwargs={"slug": team.slug}))
        
        self.assertTrue(team.is_manager(user2))
        
        url = reverse("teams:demote_member", kwargs={"user_pk": user2.pk, "slug": team.slug})
        response = self.client.get(url)
        self.assertRedirects(response, reverse("teams:edit_members", kwargs={"slug": team.slug}))
        
        self.assertFalse(team.is_manager(user2))
        
        url = reverse("teams:remove_member", kwargs={"user_pk": user2.pk, "slug": team.slug})
        response = self.client.post(url)
        self.failUnlessEqual(response.status_code, 200)
        
        self.assertFalse(team.is_member(user2))
        
        url = reverse("teams:completed_videos", kwargs={"slug": team.slug})
        response = self.client.post(url)
        self.failUnlessEqual(response.status_code, 200)

        url = reverse("teams:videos_actions", kwargs={"slug": team.slug})
        response = self.client.post(url)
        self.failUnlessEqual(response.status_code, 200)
        
        self.client.login()
        TeamMember.objects.filter(user=self.user, team=team).delete()
        self.assertFalse(team.is_member(self.user))
        url = reverse("teams:join_team", kwargs={"slug": team.slug})
        response = self.client.post(url)
        self.failUnlessEqual(response.status_code, 302)
        self.assertTrue(team.is_member(self.user))

    def test_tvl_language_syncs(self):
        team, new_team_video = self._create_new_team_video()
        self._set_my_languages('en', 'ru')
        # now add a Russian video with no subtitles.
        self._add_team_video(
            team, u'ru',
            u'http://upload.wikimedia.org/wikipedia/commons/6/61/CollateralMurder.ogv')
        tvl = TeamVideoLanguage.objects.get(team_video=new_team_video, language='ru')
        self.assertEqual(tvl.language, 'ru')
        
    def test_fixes(self):
        url = reverse("teams:detail", kwargs={"slug": 'slug-does-not-exist'})
        response = self.client.get(url)
        self.failUnlessEqual(response.status_code, 404)

from teams.rpc import TeamsApiClass
from utils.rpc import Error, Msg
from django.contrib.auth.models import AnonymousUser

class TestJqueryRpc(TestCase):
    
    def setUp(self):
        self.team = Team(name='Test', slug='test')
        self.team.save()
        self.user = User.objects.all()[:1].get()
        self.rpc = TeamsApiClass()
        
    def test_create_application(self):
        response = self.rpc.create_application(self.team.pk, '', AnonymousUser())
        if not isinstance(response, Error):
            self.fail('User should be authenticated')
        #---------------------------------------

        response = self.rpc.create_application(None, '', self.user)
        if not isinstance(response, Error):
            self.fail('Undefined team')
        #---------------------------------------    
        self.team.membership_policy = Team.INVITATION_BY_MANAGER
        self.team.save()
        
        response = self.rpc.create_application(self.team.pk, '', self.user)
        if not isinstance(response, Error):
            self.fail('Team is not opened')
        #---------------------------------------
        self.team.membership_policy = Team.OPEN
        self.team.save()
        
        self.assertFalse(self.team.is_member(self.user))
        
        response = self.rpc.create_application(self.team.pk, '', self.user)
        
        if isinstance(response, Error):
            self.fail(response)
        
        self.assertTrue(self.team.is_member(self.user))
        #---------------------------------------
        response = self.rpc.leave(self.team.pk, self.user)
        
        if not isinstance(response, Error):
            self.fail('You are the only member of team')
        
        other_user = User.objects.exclude(pk=self.user)[:1].get()
        self.rpc.join(self.team.pk, other_user)    
        
        response = self.rpc.leave(self.team.pk, self.user)
        if isinstance(response, Error):
            self.fail(response)
                    
        self.assertFalse(self.team.is_member(self.user))           
        #---------------------------------------
        self.team.membership_policy = Team.APPLICATION
        self.team.save()
        
        self.assertFalse(Application.objects.filter(user=self.user, team=self.team).exists())  
        response = self.rpc.create_application(self.team.pk, '', self.user)

        if isinstance(response, Error):
            self.fail(response)
        
        self.assertFalse(self.team.is_member(self.user))
        self.assertTrue(Application.objects.filter(user=self.user, team=self.team).exists())
        #---------------------------------------
        
    def test_join(self):
        self.team.membership_policy = Team.OPEN
        self.team.save()
        
        self.assertFalse(self.team.is_member(self.user))
        
        response = self.rpc.join(self.team.pk, self.user)
        
        if isinstance(response, Error):
            self.fail(response)
        
        self.assertTrue(self.team.is_member(self.user))            
