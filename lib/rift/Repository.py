#
# Copyright (C) 2014-2016 CEA
#
# This file is part of Rift project.
#
# This software is governed by the CeCILL license under French law and
# abiding by the rules of distribution of free software.  You can  use,
# modify and/ or redistribute the software under the terms of the CeCILL
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or
# data to be ensured and,  more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.
#

"""
Helper class for YUM repository structure management.
"""

import os
import logging
import shutil
from subprocess import Popen, PIPE, STDOUT

from rift import RiftError
from rift.Config import _DEFAULT_REPO_CMD

class RemoteRepository():
    """
    Simple container for dealing with read-only remote repository using http or
    ftp.
    """
    def __init__(self, url, name=None, priority=None, options=None, config=None):
        self.url = url
        self.name = name
        self.priority = priority
        if config is None:
            config = {}
        if options is None:
            options = {}
        self.module_hotfixes = options.get('module_hotfixes')
        self.excludepkgs = options.get('excludepkgs')
        self.proxy = options.get('proxy', config.get('proxy'))
        self.createrepo = config.get('createrepo', _DEFAULT_REPO_CMD)

    def is_file(self):
        """True if repository URL looks like a file URI."""
        return self.url.startswith('file://') or self.url.startswith('/')

    @property
    def rpms_dir(self):
        """
        Path to RPMS directory if this is a local file repo. None otherwise.
        """
        if self.url.startswith('/'):
            return self.url
        if self.url.startswith('file://'):
            return self.url[len('file://'):]
        return None

    def create(self):
        """
        Read-only repository, create() is a no-op, considering it is always
        created and usable.
        """


class Repository(RemoteRepository):
    """
    Manipulate a RPMS repository structures: RPMs, directories and metadata.

    Metadata are created using 'createrepo' tool.
    """

    def __init__(self, path, arch, name=None, options=None, config=None):
        self.path = os.path.realpath(path)
        self.srpms_dir = os.path.join(self.path, 'SRPMS')
        rpms_dir = os.path.join(self.path, arch)

        name = name or os.path.basename(self.path)
        url = 'file://%s' % os.path.realpath(rpms_dir)
        RemoteRepository.__init__(self,
                                  url,
                                  name=name,
                                  options=options,
                                  config=config)

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
        cmd = [self.createrepo, '-q', '--update', self.rpms_dir]
        popen = Popen(cmd, stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        stdout = popen.communicate()[0]
        if popen.returncode != 0:
            raise RiftError(stdout)

        cmd = [self.createrepo, '-q', '--update', self.srpms_dir]
        popen = Popen(cmd, stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        stdout = popen.communicate()[0]
        if popen.returncode != 0:
            raise RiftError(stdout)

    def add(self, rpm):
        """
        Copy RPM file pointed `rpm' into the repository, in the correct
        subdirectory based on RPM type and architecture.
        """
        if rpm.is_source:
            logging.debug("Adding %s to repo %s", rpm.filepath, self.srpms_dir)
            shutil.copy(rpm.filepath, self.srpms_dir)
        else:
            logging.debug("Adding %s to repo %s", rpm.filepath, self.rpms_dir)
            # rpms_dir already points to architecture directory
            shutil.copy(rpm.filepath, self.rpms_dir)
