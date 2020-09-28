# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Application manifest for shadowsocks.
"""

backup = {
    'secrets': {
        'files': [
            '/var/lib/private/shadowsocks-libev/freedombox/freedombox.json'
        ]
    },
    'services': ['shadowsocks-libev-local@freedombox']
}
