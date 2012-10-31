# -*- coding: utf-8 -*-

from __future__ import absolute_import

import mock

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

from sentry.constants import MEMBER_OWNER, MEMBER_USER
from sentry.models import Team
from sentry.testutils import fixture
from tests.base import TestCase


class BaseTeamTest(TestCase):
    fixtures = ['tests/fixtures/views.json']

    @fixture
    def user(self):
        user = User(username="user", email="admin@localhost", is_staff=False, is_superuser=False)
        user.set_password('password')
        user.save()
        return user

    @fixture
    def user2(self):
        user = User.objects.create(username="other", email="other@localhost")
        self.team.member_set.create(user=user, type=MEMBER_USER)
        return user

    @fixture
    def tm(self):
        return self.team.member_set.get(user=self.user, type=MEMBER_OWNER)

    @fixture
    def tm2(self):
        return self.team.member_set.get(user=self.user2)

    def setUp(self):
        self.team = Team.objects.create(name='foo', slug='foo', owner=self.user)
        assert self.client.login(username=self.user.username, password='password')


class TeamListTest(BaseTeamTest):
    def test_loads(self):
        resp = self.client.post(reverse('sentry-team-list'))
        self.assertEquals(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'sentry/teams/list.html')


class NewTeamTest(BaseTeamTest):
    @fixture
    def path(self):
        return reverse('sentry-new-team')

    @mock.patch('sentry.web.frontend.teams.can_create_teams', mock.Mock(return_value=False))
    def test_missing_permission(self):
        resp = self.client.post(self.path)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp['Location'], 'http://testserver' + reverse('sentry'))

    @mock.patch('sentry.web.frontend.teams.can_create_teams', mock.Mock(return_value=True))
    def test_missing_params(self):
        resp = self.client.post(self.path)
        self.assertEquals(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'sentry/teams/new.html')

    @mock.patch('sentry.web.frontend.teams.can_create_teams', mock.Mock(return_value=True))
    def test_valid_params(self):
        resp = self.client.post(self.path, {
            'name': 'Test Team',
            'slug': 'test',
        })
        self.assertNotEquals(resp.status_code, 200)

        team = Team.objects.filter(name='Test Team')
        self.assertTrue(team.exists())
        team = team.get()

        self.assertEquals(team.owner, self.user)

        member_set = list(team.member_set.all())

        self.assertEquals(len(member_set), 1)
        member = member_set[0]
        self.assertEquals(member.user, self.user)
        self.assertEquals(member.type, MEMBER_OWNER)

    @mock.patch('sentry.web.frontend.teams.can_create_teams', mock.Mock(return_value=True))
    @mock.patch('django.contrib.auth.models.User.has_perm', mock.Mock(return_value=True))
    def test_superuser_can_set_owner(self):
        resp = self.client.post(self.path, {
            'name': 'Test Team',
            'slug': 'test',
            'owner': self.user2.username,
        })
        self.assertNotEquals(resp.status_code, 200)

        team = Team.objects.get(name='Test Team')
        self.assertEquals(team.owner, self.user2)

        member_set = list(team.member_set.all())

        self.assertEquals(len(member_set), 1)
        member = member_set[0]
        self.assertEquals(member.user, self.user2)
        self.assertEquals(member.type, MEMBER_OWNER)


class ManageTeamTest(BaseTeamTest):
    def test_loads(self):
        resp = self.client.get(reverse('sentry-manage-team', args=[self.team.slug]))
        self.assertEquals(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'sentry/teams/manage.html')

    def test_valid_params(self):
        path = reverse('sentry-manage-team', args=[self.team.slug])
        resp = self.client.post(path, {
            'name': 'bar',
        })
        self.assertNotEquals(resp.status_code, 200)
        self.assertEquals(resp['Location'], 'http://testserver' + path + '?success=1')
        team = Team.objects.get(pk=self.team.pk)
        self.assertEquals(team.name, 'bar')


class RemoveTeamTest(BaseTeamTest):
    @mock.patch('sentry.web.frontend.teams.can_remove_team', mock.Mock(return_value=False))
    def test_missing_permission(self):
        resp = self.client.post(reverse('sentry-remove-team', args=[self.team.slug]))
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp['Location'], 'http://testserver' + reverse('sentry'))

    @mock.patch('sentry.web.frontend.teams.can_remove_team', mock.Mock(return_value=True))
    def test_loads(self):
        resp = self.client.get(reverse('sentry-remove-team', args=[self.team.slug]))
        self.assertEquals(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'sentry/teams/remove.html')

    @mock.patch('sentry.web.frontend.teams.can_remove_team', mock.Mock(return_value=True))
    def test_valid_params(self):
        path = reverse('sentry-remove-team', args=[self.team.slug])
        resp = self.client.post(path, {'a': 'b'})  # HACK: pass a param since we're faking CSRF to get the form to load
        self.assertNotEquals(resp.status_code, 200)
        self.assertEquals(resp['Location'], 'http://testserver' + reverse('sentry-team-list'))
        self.assertFalse(Team.objects.filter(pk=self.team.pk).exists())


class SuspendTeamMemberTest(BaseTeamTest):
    def test_cannot_suspend_owner(self):
        resp = self.client.post(reverse('sentry-suspend-team-member', args=[self.team.slug, self.tm.id]))
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp['Location'], 'http://testserver' + reverse('sentry-manage-team', args=[self.team.slug]))
        tm = self.team.member_set.get(pk=self.tm2.id)
        self.assertTrue(tm.is_active)

    def test_does_suspend(self):
        resp = self.client.get(reverse('sentry-suspend-team-member', args=[self.team.slug, self.tm2.id]))
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp['Location'], 'http://testserver' + reverse('sentry-manage-team', args=[self.team.slug]) + '?success=1')
        tm = self.team.member_set.get(pk=self.tm2.id)
        self.assertFalse(tm.is_active)


class RestoreTeamMemberTest(BaseTeamTest):
    def test_cannot_restore_owner(self):
        resp = self.client.post(reverse('sentry-restore-team-member', args=[self.team.slug, self.tm.id]))
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp['Location'], 'http://testserver' + reverse('sentry-manage-team', args=[self.team.slug]))
        tm = self.team.member_set.get(pk=self.tm2.id)
        self.assertTrue(tm.is_active)

    def test_does_restore(self):
        self.tm2.update(is_active=False)
        resp = self.client.get(reverse('sentry-restore-team-member', args=[self.team.slug, self.tm2.id]))
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp['Location'], 'http://testserver' + reverse('sentry-manage-team', args=[self.team.slug]) + '?success=1')
        tm = self.team.member_set.get(pk=self.tm2.id)
        self.assertTrue(tm.is_active)
