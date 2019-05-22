#
# This file is part of FreedomBox.
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""
FreedomBox app to configure MediaWiki.
"""

from django.utils.translation import ugettext_lazy as _

from plinth import action_utils, actions
from plinth import app as app_module
from plinth import frontpage, menu
from plinth import service as service_module
from plinth.modules.apache.components import Webserver
from plinth.modules.firewall.components import Firewall

from .manifest import backup, clients

version = 6

managed_packages = ['mediawiki', 'imagemagick', 'php-sqlite3']

name = _('MediaWiki')

short_description = _('Wiki')

description = [
    _('MediaWiki is the wiki engine that powers Wikipedia and other WikiMedia '
      'projects. A wiki engine is a program for creating a collaboratively '
      'edited website. You can use MediaWiki to host a wiki-like website, '
      'take notes or collaborate with friends on projects.'),
    _('This MediaWiki instance comes with a randomly generated administrator '
      'password. You can set a new password in the "Configuration" section '
      'and log in using the "admin" account. You can then create more user '
      'accounts from MediaWiki itself by going to the <a '
      'href="/mediawiki/index.php/Special:CreateAccount">'
      'Special:CreateAccount</a> page.'),
    _('Anyone with a link to this wiki can read it. Only users that are '
      'logged in can make changes to the content.')
]

service = None

manual_page = 'MediaWiki'

clients = clients

app = None


class MediaWikiApp(app_module.App):
    """FreedomBox app for MediaWiki."""

    def __init__(self):
        """Create components for the app."""
        super().__init__()
        self._private_mode = True

        menu_item = menu.Menu('menu-mediawiki', name, short_description,
                              'mediawiki', 'mediawiki:index',
                              parent_url_name='apps')
        self.add(menu_item)

        shortcut = Shortcut('shortcut-mediawiki', name,
                            short_description=short_description,
                            icon='mediawiki', url='/mediawiki',
                            clients=clients, login_required=True)
        self.add(shortcut)

        firewall = Firewall('firewall-mediawiki', name,
                            ports=['http', 'https'], is_external=True)
        self.add(firewall)

        webserver = Webserver('webserver-mediawiki', 'mediawiki')
        self.add(webserver)

        webserver = Webserver('webserver-mediawiki-freedombox',
                              'mediawiki-freedombox')
        self.add(webserver)


class Shortcut(frontpage.Shortcut):
    """Frontpage shortcut for only logged users when in private mode."""

    def enable(self):
        """When enabled, check if MediaWiki is in private mode."""
        super().enable()
        self.login_required = is_private_mode_enabled()


def init():
    """Intialize the module."""
    global app
    app = MediaWikiApp()

    global service
    setup_helper = globals()['setup_helper']
    if setup_helper.get_state() != 'needs-setup':
        service = service_module.Service('mediawiki', name,
                                         is_enabled=is_enabled, enable=enable,
                                         disable=disable)
        if is_enabled():
            app.set_enabled(True)


def setup(helper, old_version=None):
    """Install and configure the module."""
    helper.install(managed_packages)
    helper.call('setup', actions.superuser_run, 'mediawiki', ['setup'])
    helper.call('update', actions.superuser_run, 'mediawiki', ['update'])
    helper.call('enable', actions.superuser_run, 'mediawiki', ['enable'])
    global service
    if service is None:
        service = service_module.Service('mediawiki', name,
                                         is_enabled=is_enabled, enable=enable,
                                         disable=disable)
    helper.call('post', app.enable)


def is_enabled():
    """Return whether the module is enabled."""
    return app.is_enabled()


def enable():
    """Enable the module."""
    actions.superuser_run('mediawiki', ['enable'])
    app.enable()


def disable():
    """Enable the module."""
    actions.superuser_run('mediawiki', ['disable'])
    app.disable()


def diagnose():
    """Run diagnostics and return the results."""
    results = []

    results.extend(
        action_utils.diagnose_url_on_all('https://{host}/mediawiki',
                                         check_certificate=False))
    return results


def is_public_registration_enabled():
    """Return whether public registration is enabled."""
    output = actions.superuser_run('mediawiki',
                                   ['public-registrations', 'status'])
    return output.strip() == 'enabled'


def is_private_mode_enabled():
    """ Return wheter private mode is enabled or disabled"""
    output = actions.superuser_run('mediawiki', ['private-mode', 'status'])
    return output.strip() == 'enabled'
