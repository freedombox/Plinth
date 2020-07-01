# SPDX-License-Identifier: AGPL-3.0-or-later
"""
FreedomBox app for upgrades.
"""

import subprocess

from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ugettext_noop

import plinth
from plinth import actions
from plinth import app as app_module
from plinth import cfg, glib, menu

from .manifest import backup  # noqa, pylint: disable=unused-import

version = 3

is_essential = True

managed_packages = ['unattended-upgrades', 'needrestart']

_description = [
    _('Check for and apply the latest software and security updates.'),
    _('Updates are run at 06:00 everyday according to local time zone. Set '
      'your time zone in Date & Time app. Apps are restarted after update '
      'causing them to be unavailable briefly. If system reboot is deemed '
      'necessary, it is done automatically at 02:00 causing all apps to be '
      'unavailable briefly.')
]

app = None


class UpgradesApp(app_module.App):
    """FreedomBox app for software upgrades."""

    app_id = 'upgrades'

    can_be_disabled = False

    def __init__(self):
        """Create components for the app."""
        super().__init__()
        info = app_module.Info(app_id=self.app_id, version=version,
                               is_essential=is_essential, name=_('Update'),
                               icon='fa-refresh', description=_description,
                               manual_page='Upgrades')
        self.add(info)

        menu_item = menu.Menu('menu-upgrades', info.name, None, info.icon,
                              'upgrades:index', parent_url_name='system')
        self.add(menu_item)

        self._show_new_release_notification()

        # Check every day for setting up apt backport sources, every 3 minutes
        # in debug mode.
        interval = 180 if cfg.develop else 24 * 3600
        glib.schedule(interval, setup_repositories)

    def _show_new_release_notification(self):
        """When upgraded to new release, show a notification."""
        from plinth.notification import Notification
        try:
            note = Notification.get('upgrades-new-release')
            if note.data['version'] == plinth.__version__:
                # User already has notification for update to this version. It
                # may be dismissed or not yet dismissed
                return

            # User currently has a notification for an older version, update.
            dismiss = False
        except KeyError:
            # Don't show notification for the first version user runs, create
            # but don't show it.
            dismiss = True

        data = {
            'version': plinth.__version__,
            'app_name': 'Update',
            'app_icon': 'fa-refresh'
        }
        title = ugettext_noop('FreedomBox Updated')
        note = Notification.update_or_create(
            id='upgrades-new-release', app_id='upgrades', severity='info',
            title=title, body_template='upgrades-new-release.html', data=data,
            group='admin')
        note.dismiss(should_dismiss=dismiss)


def init():
    """Initialize the module."""
    global app
    app = UpgradesApp()
    app.set_enabled(True)


def setup(helper, old_version=None):
    """Install and configure the module."""
    helper.install(managed_packages)

    # Enable automatic upgrades but only on first install
    if not old_version and not cfg.develop:
        helper.call('post', actions.superuser_run, 'upgrades', ['enable-auto'])

    # Update apt preferences whenever on first install and on version
    # increment.
    helper.call('post', actions.superuser_run, 'upgrades', ['setup'])

    # Try to setup apt repositories, if needed, if possible, on first install
    # and on version increment.
    helper.call('post', setup_repositories, None)


def is_enabled():
    """Return whether the module is enabled."""
    output = actions.run('upgrades', ['check-auto'])
    return 'True' in output.split()


def enable():
    """Enable the module."""
    actions.superuser_run('upgrades', ['enable-auto'])


def disable():
    """Disable the module."""
    actions.superuser_run('upgrades', ['disable-auto'])


def setup_repositories(data):
    """Setup apt backport repositories."""
    actions.superuser_run('upgrades', ['setup-repositories'])


def get_backports_in_use():
    """Return whether backports packages are installed."""
    # Only freedombox package is set to be installed from backports currently.
    output = subprocess.check_output(['apt-cache', 'policy', 'freedombox'])
    for line in output.decode().split('\n'):
        if 'Installed:' in line:
            version = line.strip().split(': ')[1]
            if 'bpo' in version:
                return True

    return False


def can_activate_backports():
    """Return whether backports can be activated."""
    if get_backports_in_use():
        return False

    release = subprocess.check_output(['lsb_release', '--release',
                                       '--short']).decode().strip()
    if release in ['testing', 'unstable']:
        return False

    return True
