# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Forms for backups module.
"""

import logging
import os
import re
import subprocess

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import (FileExtensionValidator,
                                    validate_ipv46_address)
from django.utils.translation import ugettext
from django.utils.translation import ugettext_lazy as _

from plinth.modules.storage import get_mounts
from plinth.utils import format_lazy

from . import api, split_path
from .repository import get_repositories

logger = logging.getLogger(__name__)


def _get_app_choices(apps):
    """Return a list of check box multiple choices from list of apps."""
    choices = []
    for app in apps:
        name = app.app.app.info.name
        if not app.has_data:
            name = ugettext('{app} (No data to backup)').format(
                app=app.app.app.info.name)

        choices.append((app.name, name))

    return choices


def _get_repository_choices():
    """Return the list of available repositories."""
    choices = [(repository.uuid, repository.name)
               for repository in get_repositories() if repository.is_usable()]

    return choices


class CreateArchiveForm(forms.Form):
    repository = forms.ChoiceField()
    name = forms.RegexField(
        label=_('Name'),
        help_text=_('(Optional) Set a name for this backup archive'),
        regex=r'^[^{}/]*$', required=False, strip=True)
    selected_apps = forms.MultipleChoiceField(
        label=_('Included apps'), help_text=_('Apps to include in the backup'),
        widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        """Initialize the form with selectable apps."""
        super().__init__(*args, **kwargs)
        apps = api.get_all_apps_for_backup()
        self.fields['selected_apps'].choices = _get_app_choices(apps)
        self.fields['selected_apps'].initial = [app.name for app in apps]
        self.fields['repository'].choices = _get_repository_choices()


class RestoreForm(forms.Form):
    selected_apps = forms.MultipleChoiceField(
        label=_('Select the apps you want to restore'),
        widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        """Initialize the form with selectable apps."""
        apps = kwargs.pop('apps')
        super().__init__(*args, **kwargs)
        self.fields['selected_apps'].choices = _get_app_choices(apps)
        self.fields['selected_apps'].initial = [app.name for app in apps]


class UploadForm(forms.Form):
    file = forms.FileField(
        label=_('Upload File'), required=True, validators=[
            FileExtensionValidator(
                ['gz'], _('Backup files have to be in .tar.gz format'))
        ], help_text=_('Select the backup file you want to upload'))


def repository_validator(path):
    """Validate an SSH repository path."""
    if not ('@' in path and ':' in path):
        raise ValidationError(_('Repository path format incorrect.'))

    username, hostname, dir_path = split_path(path)
    hostname = hostname.split('%')[0]

    # Validate username using Unix username regex
    if not re.match(r'[a-z0-9_][a-z0-9_-]*$', username):
        raise ValidationError(_(f'Invalid username: {username}'))

    # The hostname should either be a valid IP address or hostname
    # Follows RFC1123 (hostnames can start with digits) instead of RFC952
    hostname_re = (r'^(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*'
                   r'([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$')
    try:
        validate_ipv46_address(hostname)
    except ValidationError:
        if not re.match(hostname_re, hostname):
            raise ValidationError(_(f'Invalid hostname: {hostname}'))

    # Validate directory path
    if not re.match(r'[^\0]*', dir_path):
        raise ValidationError(_(f'Invalid directory path: {dir_path}'))


class EncryptedBackupsMixin(forms.Form):
    """Form to add a new backup repository."""
    encryption = forms.ChoiceField(
        label=_('Encryption'), help_text=format_lazy(
            _('"Key in Repository" means that a '
              'password-protected key is stored with the backup.')),
        choices=[('repokey', 'Key in Repository'), ('none', 'None')])
    encryption_passphrase = forms.CharField(
        label=_('Passphrase'),
        help_text=_('Passphrase; Only needed when using encryption.'),
        widget=forms.PasswordInput(), required=False)
    confirm_encryption_passphrase = forms.CharField(
        label=_('Confirm Passphrase'), help_text=_('Repeat the passphrase.'),
        widget=forms.PasswordInput(), required=False)

    def clean(self):
        super().clean()
        passphrase = self.cleaned_data.get('encryption_passphrase')
        confirm_passphrase = self.cleaned_data.get(
            'confirm_encryption_passphrase')

        if passphrase != confirm_passphrase:
            raise forms.ValidationError(
                _('The entered encryption passphrases do not match'))

        if self.cleaned_data.get('encryption') != 'none' and not passphrase:
            raise forms.ValidationError(
                _('Passphrase is needed for encryption.'))

        return self.cleaned_data


encryption_fields = [
    'encryption', 'encryption_passphrase', 'confirm_encryption_passphrase'
]


def get_disk_choices():
    """Returns a list of all available partitions except the root partition."""
    repositories = get_repositories()
    existing_paths = [
        repository.path for repository in repositories
        if repository.storage_type == 'disk'
    ]
    choices = []
    for device in get_mounts():
        if device['mount_point'] == '/':
            continue

        path = os.path.join(device['mount_point'], 'FreedomBoxBackups')
        if path in existing_paths:
            continue

        name = device['label'] if device['label'] else device['mount_point']
        choices.append((device['mount_point'], name))

    return choices


class AddRepositoryForm(EncryptedBackupsMixin, forms.Form):
    """Form to create a new backups repository on a disk."""
    disk = forms.ChoiceField(
        label=_('Select Disk or Partition'), help_text=format_lazy(
            _('Backups will be stored in the directory FreedomBoxBackups')),
        choices=get_disk_choices)

    field_order = ['disk'] + encryption_fields


class AddRemoteRepositoryForm(EncryptedBackupsMixin, forms.Form):
    """Form to add new SSH remote repository."""
    repository = forms.CharField(
        label=_('SSH Repository Path'), strip=True,
        help_text=_('Path of a new or existing repository. Example: '
                    '<i>user@host:~/path/to/repo/</i>'),
        validators=[repository_validator])
    ssh_password = forms.CharField(
        label=_('SSH server password'), strip=True,
        help_text=_('Password of the SSH Server.<br />'
                    'SSH key-based authentication is not yet possible.'),
        widget=forms.PasswordInput(), required=False)

    field_order = ['repository', 'ssh_password'] + encryption_fields

    def clean_repository(self):
        """Validate repository form field."""
        path = self.cleaned_data.get('repository')
        # Avoid creation of duplicate ssh remotes
        self._check_if_duplicate_remote(path)
        return path

    @staticmethod
    def _check_if_duplicate_remote(path):
        """Raise validation error if given path is a stored remote."""
        for repository in get_repositories():
            if repository.path == path:
                raise forms.ValidationError(
                    _('Remote backup repository already exists.'))


class VerifySshHostkeyForm(forms.Form):
    """Form to verify the SSH public key for a host."""
    ssh_public_key = forms.ChoiceField(
        label=_('Select verified SSH public key'), widget=forms.RadioSelect)

    def __init__(self, *args, **kwargs):
        """Initialize the form with selectable apps."""
        hostname = kwargs.pop('hostname')
        super().__init__(*args, **kwargs)
        (self.fields['ssh_public_key'].choices,
         self.keyscan_error) = self._get_all_public_keys(hostname)

    @staticmethod
    def _get_all_public_keys(hostname):
        """Use ssh-keyscan to get all the SSH public keys of a host."""
        # Fetch public keys of ssh remote
        keyscan = subprocess.run(['ssh-keyscan', hostname],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        keys = keyscan.stdout.decode().splitlines()
        error_message = keyscan.stderr.decode() if keyscan.returncode else None
        # Generate user-friendly fingerprints of public keys
        keygen = subprocess.run(['ssh-keygen', '-l', '-f', '-'],
                                input=keyscan.stdout, stdout=subprocess.PIPE)
        fingerprints = keygen.stdout.decode().splitlines()

        return zip(keys, fingerprints), error_message
