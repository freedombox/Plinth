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
Utilities for managing WireGuard.
"""

import datetime
import json
import subprocess
import time

from plinth import actions, network
from plinth.utils import import_from_gi

nm = import_from_gi('NM', '1.0')

IP_TEMPLATE = '10.84.0.{}'
WIREGUARD_SETTING = nm.SETTING_WIREGUARD_SETTING_NAME


def get_nm_info():
    """Get information from network manager."""
    client = network.get_nm_client()

    connections = {}
    for connection in client.get_connections():
        if connection.get_connection_type() != WIREGUARD_SETTING:
            continue

        settings = connection.get_setting_by_name(WIREGUARD_SETTING)
        secrets = connection.get_secrets(WIREGUARD_SETTING)
        connection.update_secrets(WIREGUARD_SETTING, secrets)

        info = {}
        info['interface'] = connection.get_interface_name()
        info['private_key'] = settings.get_private_key()
        info['public_key'] = None
        info['listen_port'] = settings.get_listen_port()
        info['fwmark'] = settings.get_fwmark()
        info['mtu'] = settings.get_mtu()
        info['default_route'] = settings.get_ip4_auto_default_route()
        info['peers'] = {}
        for peer_index in range(settings.get_peers_len()):
            peer = settings.get_peer(peer_index)
            peer_info = {
                'endpoint': peer.get_endpoint(),
                'public_key': peer.get_public_key(),
                'preshared_key': peer.get_preshared_key(),
                'persistent_keepalive': peer.get_persistent_keepalive(),
                'allowed_ips': []
            }
            for index in range(peer.get_allowed_ips_len()):
                allowed_ip = peer.get_allowed_ip(index, None)
                peer_info['allowed_ips'].append(allowed_ip)

            info['peers'][peer_info['public_key']] = peer_info

        settings_ipv4 = connection.get_setting_ip4_config()
        if settings_ipv4 and settings_ipv4.get_num_addresses():
            info['ip_address'] = settings_ipv4.get_address(0).get_address()

        connections[info['interface']] = info

    return connections


def get_info():
    """Return server and clients info."""
    output = actions.superuser_run('wireguard', ['get-info'])
    status = json.loads(output)

    nm_info = get_nm_info()

    my_server_info = None
    my_client_servers = {}
    for interface, info in nm_info.items():
        if interface == 'wg0':
            my_server_info = info
        else:
            my_client_servers[interface] = info

        if interface not in status:
            continue

        info['public_key'] = status[interface]['public_key']
        for status_peer in status[interface]['peers']:
            if status_peer['latest_handshake']:
                status_peer['latest_handshake'] = \
                    datetime.datetime.fromtimestamp(
                        status_peer['latest_handshake'])
            public_key = status_peer['public_key']
            info_peer = info['peers'].setdefault(public_key, {})
            info_peer['status'] = status_peer

    return {
        'my_server': my_server_info,
        'my_client': {
            'servers': my_client_servers,
        },
    }


def find_next_interface():
    """Find next unused wireguard interface name."""
    output = subprocess.check_output(['wg', 'show',
                                      'interfaces']).decode().strip()
    interfaces = output.split()
    interface_num = 1
    new_interface_name = 'wg1'
    while new_interface_name in interfaces:
        interface_num += 1
        new_interface_name = 'wg' + str(interface_num)

    return new_interface_name


def add_server(settings):
    """Add information for connecting to a server."""
    interface_name = find_next_interface()
    settings['common']['name'] = 'WireGuard-Client-' + interface_name
    settings['common']['interface'] = interface_name
    network.add_connection(settings)


def setup_server():
    """Setup a server connection that clients can connect to."""
    process = subprocess.run(['wg', 'genkey'], check=True, capture_output=True)
    private_key = process.stdout.decode().strip()
    settings = {
        'common': {
            'name': 'WireGuard-Server-wg0',
            'type': WIREGUARD_SETTING,
            'zone': 'internal',
            'interface': 'wg0'
        },
        'ipv4': {
            'method': 'manual',
            'address': IP_TEMPLATE.format(1),
            'netmask': '255.255.255.0',
            'gateway': '',
            'dns': '',
            'second_dns': '',
        },
        'wireguard': {
            'private_key': private_key,
            'listen_port': 51820,
        }
    }
    network.add_connection(settings)


def _get_next_available_ip_address(settings):
    """Get the next available IP address to allocate to a client."""
    allocated_ips = set()
    for peer_index in range(settings.get_peers_len()):
        peer = settings.get_peer(peer_index)
        for ip_index in range(peer.get_allowed_ips_len()):
            allowed_ip = peer.get_allowed_ip(ip_index)
            # We assume these are simple IP addresses but they can be subnets.
            allocated_ips.add(allowed_ip)

    for index in range(2, 254):
        ip_address = IP_TEMPLATE.format(index)
        if ip_address not in allocated_ips:
            return ip_address

    raise IndexError('Reached client limit')


def _server_connection():
    """Return a server connection. Create one if necessary."""
    connection = network.get_connection_by_interface_name('wg0')
    if not connection:
        setup_server()

    for _ in range(10):
        # XXX: Improve this waiting by doing a synchronous D-Bus operation to
        # add network manager connection instead.
        time.sleep(1)
        connection = network.get_connection_by_interface_name('wg0')
        if connection:
            break

    if not connection:
        raise RuntimeError('Unable to create a server connection.')

    # Retrieve secrets so that when the connection is changed, secrets are
    # preserved properly.
    secrets = connection.get_secrets(WIREGUARD_SETTING)
    connection.update_secrets(WIREGUARD_SETTING, secrets)

    return connection


def add_client(public_key):
    """Add a permission for a client to connect our server."""
    connection = _server_connection()
    settings = connection.get_setting_by_name(WIREGUARD_SETTING)
    peer, _ = settings.get_peer_by_public_key(public_key)
    if peer:
        raise ValueError('Peer with public key already exists')

    peer = nm.WireGuardPeer.new()
    peer.set_public_key(public_key, False)
    peer.set_persistent_keepalive(25)  # To keep NAT 'connections' alive
    peer.append_allowed_ip(_get_next_available_ip_address(settings), False)
    settings.append_peer(peer)
    connection.commit_changes(True)


def remove_client(public_key):
    """Remove permission for a client to connect our server."""
    connection = _server_connection()
    settings = connection.get_setting_by_name(WIREGUARD_SETTING)
    peer, peer_index = settings.get_peer_by_public_key(public_key)
    if not peer:
        raise KeyError('Client not found')

    settings.remove_peer(peer_index)
    connection.commit_changes(True)
