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
Views for samba module.
"""

import logging
import urllib.parse

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import ugettext as _
from django.views.decorators.http import require_POST
from plinth import views
from plinth.modules import samba, storage

logger = logging.getLogger(__name__)


class SambaAppView(views.AppView):
    """Samba sharing basic configuration."""
    name = samba.name
    description = samba.description
    diagnostics_module_name = 'samba'
    app_id = 'samba'
    template_name = 'samba.html'

    def get_context_data(self, *args, **kwargs):
        """Return template context data."""
        context = super().get_context_data(*args, **kwargs)
        disks = storage.get_disks()
        context['disks'] = disks
        shares = samba.get_shares()
        context['shared_mounts'] = [share['mount_point'] for share in shares]

        unavailable_shares = []
        for share in shares:
            for disk in disks:
                if share['mount_point'] == disk['mount_point']:
                    break
            else:
                unavailable_shares.append(share)
        context['unavailable_shares'] = unavailable_shares

        return context


@require_POST
def share(request, mount_point):
    """Enable sharing, given its root path.

    mount_point is urlquoted.

    """
    mount_point = urllib.parse.unquote(mount_point)
    filesystem = request.POST.get('filesystem_type', '')
    try:
        samba.add_share(mount_point, filesystem)
        messages.success(request, _('Share enabled.'))
    except Exception as exception:
        logger.exception('Error enabling share')
        messages.error(
            request,
            _('Error enabling share: {error_message}').format(
                error_message=exception))

    return redirect(reverse('samba:index'))


@require_POST
def unshare(request, mount_point):
    """Disable sharing, given its name.

    mount_point is urlquoted.

    """
    mount_point = urllib.parse.unquote(mount_point)
    try:
        samba.delete_share(mount_point)
        messages.success(request, _('Share disabled.'))
    except Exception as exception:
        logger.exception('Error disabling share')
        messages.error(
            request,
            _('Error disabling share: {error_message}').format(
                error_message=exception))

    return redirect(reverse('samba:index'))