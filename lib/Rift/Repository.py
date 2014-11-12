#
# Copyright (C) 2014 CEA
#

"""
Helper class for YUM repository structure management.
"""

import os
import shutil
from subprocess import Popen, PIPE, STDOUT

from Rift import RiftError

class Repository(object):
    """
    Manipulate a RPMS repository structures: RPMs, directories and metadata.

    Metadata are created using 'createrepo' tool.
    """

    def __init__(self, path, name=None):
        self.path = path
        self.name = name or os.path.basename(self.path)
        self.srpms_dir = os.path.join(self.path, 'SRPMS')
        self.rpms_dir = os.path.join(self.path, 'RPMS')

    def create(self):
        """Create repository directory structure and metadata."""
        for path in (self.path, self.rpms_dir, self.srpms_dir):
            if not os.path.exists(path):
                os.mkdir(path)

        repodata = os.path.join(self.rpms_dir, 'repodata')
        if not os.path.exists(repodata):
            self.update()

    def update(self):
        """Update the repository metadata."""
        cmd = ['createrepo', '-q', '--update', self.rpms_dir]
        popen = Popen(cmd, stdout=PIPE, stderr=STDOUT)
        stdout = popen.communicate()[0]
        if popen.returncode != 0:
            raise RiftError(stdout)

    def add(self, rpm):
        """
        Copy RPM file pointed `rpm' into the repository, in the correct
        subdirectory based on RPM type and architecture.
        """
        if rpm.is_source:
            shutil.copy(rpm.filepath, self.srpms_dir)
        else:
            archdir = os.path.join(self.rpms_dir, rpm.arch)
            if not os.path.exists(archdir):
                os.mkdir(archdir)
            shutil.copy(rpm.filepath, archdir)
