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
URLs for the samba module.
"""

from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^apps/samba/$', views.SambaAppView.as_view(), name='index'),
    url(r'^apps/samba/share/(?P<mount_point>[A-Za-z0-9%_.\-~]+)/$',
        views.share, name='share'),
    url(r'^apps/samba/unshare/(?P<mount_point>[A-Za-z0-9%_.\-~]+)/$',
        views.unshare, name='unshare'),
]
