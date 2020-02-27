# SPDX-License-Identifier: AGPL-3.0-or-later
"""
FreedomBox app to configure Privoxy.
"""

from django.urls import reverse_lazy
from django.utils.translation import ugettext_lazy as _

from plinth import action_utils, actions
from plinth import app as app_module
from plinth import cfg, frontpage, menu
from plinth.daemon import Daemon
from plinth.modules.apache.components import diagnose_url
from plinth.modules.firewall.components import Firewall
from plinth.utils import format_lazy
from plinth.views import AppView

from .manifest import backup  # noqa, pylint: disable=unused-import

version = 1

is_essential = False

managed_services = ['privoxy']

managed_packages = ['privoxy']

_description = [
    _('Privoxy is a non-caching web proxy with advanced filtering '
      'capabilities for enhancing privacy, modifying web page data and '
      'HTTP headers, controlling access, and removing ads and other '
      'obnoxious Internet junk. '),
    format_lazy(
        _('You can use Privoxy by modifying your browser proxy settings to '
          'your {box_name} hostname (or IP address) with port 8118. '
          'While using Privoxy, you can see its configuration details and '
          'documentation at '
          '<a href="http://config.privoxy.org">http://config.privoxy.org/</a> '
          'or <a href="http://p.p">http://p.p</a>.'),
        box_name=_(cfg.box_name)),
]

reserved_usernames = ['privoxy']

app = None


class PrivoxyApp(app_module.App):
    """FreedomBox app for Privoxy."""

    app_id = 'privoxy'

    def __init__(self):
        """Create components for the app."""
        super().__init__()
        info = app_module.Info(app_id=self.app_id, version=version,
                               name=_('Privoxy'), icon_filename='privoxy',
                               short_description=_('Web Proxy'),
                               description=_description, manual_page='Privoxy')
        self.add(info)

        menu_item = menu.Menu('menu-privoxy', info.name,
                              info.short_description, info.icon_filename,
                              'privoxy:index', parent_url_name='apps')
        self.add(menu_item)

        shortcut = frontpage.Shortcut(
            'shortcut-privoxy', info.name,
            short_description=info.short_description, icon=info.icon_filename,
            description=info.description,
            configure_url=reverse_lazy('privoxy:index'), login_required=True)
        self.add(shortcut)

        firewall = Firewall('firewall-privoxy', info.name, ports=['privoxy'],
                            is_external=False)
        self.add(firewall)

        daemon = Daemon('daemon-privoxy', managed_services[0],
                        listen_ports=[(8118, 'tcp4'), (8118, 'tcp6')])
        self.add(daemon)

    def diagnose(self):
        """Run diagnostics and return the results."""
        results = super().diagnose()
        results.append(diagnose_url('https://www.debian.org'))
        results.extend(diagnose_url_with_proxy())
        return results


def init():
    """Initialize the module."""
    global app
    app = PrivoxyApp()

    setup_helper = globals()['setup_helper']
    if setup_helper.get_state() != 'needs-setup' and app.is_enabled():
        app.set_enabled(True)


def setup(helper, old_version=None):
    """Install and configure the module."""
    helper.call('pre', actions.superuser_run, 'privoxy', ['pre-install'])
    helper.install(managed_packages)
    helper.call('post', app.enable)


class PrivoxyAppView(AppView):
    app_id = 'privoxy'


def diagnose_url_with_proxy():
    """Run a diagnostic on a URL with a proxy."""
    url = 'https://debian.org/'  # Gives a simple redirect to www.

    results = []
    for address in action_utils.get_addresses():
        proxy = 'http://{host}:8118/'.format(host=address['url_address'])
        env = {'https_proxy': proxy}

        result = diagnose_url(url, kind=address['kind'], env=env)
        result[0] = _('Access {url} with proxy {proxy} on tcp{kind}') \
            .format(url=url, proxy=proxy, kind=address['kind'])
        results.append(result)

    return results
