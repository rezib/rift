#
# Copyright (C) 2014 CEA
#

"""
Contains helper class to work with 'mock' tool, used to build RPMS in a chroot
environment.
"""

import os
import shutil
import glob
import getpass
from subprocess import Popen, PIPE
from jinja2 import Template

from Rift import RiftError
from Rift.TempDir import TempDir
from Rift.RPM import RPM

class Mock(object):
    """
    Interact with 'mock' command, manage its config files and created RPMS.
    """

    MOCK_DIR = '/etc/mock'
    MOCK_TEMPLATE = 'mock.tpl'
    MOCK_DEFAULT = 'default.cfg'
    MOCK_FILES = ['logging.ini', 'site-defaults.cfg']
    MOCK_RESULT = '/var/lib/mock/%s/result'

    def __init__(self):
        self._tmpdir = None
        self._mockname = 'rift-%s' % getpass.getuser()

    def _create_template(self, repolist, dstpath):
        """Create 'default.cfg' config file based on a template."""
        # Read template
        tpl = Template(open(self.MOCK_TEMPLATE).read())
        context = {'name': self._mockname, 'repos': []}

        # Populate with repolist
        for prio, repo in enumerate(reversed(repolist), start=1):
            context['repos'].insert(0, {
                'name': repo.name or 'repo%s' % prio,
                'priority': prio,
                'url': 'file://%s' % os.path.realpath(repo.rpms_dir) })

        # Write file content
        with open(dstpath, 'w') as fmock:
            fmock.write(tpl.render(context))
        # We have to keep template timestamp to avoid being detected as a new
        # one each time.
        shutil.copystat(self.MOCK_TEMPLATE, dstpath)

    def init(self, repolist):
        """
        Create a Mock environment.
        
        This should be cleaned with clean().
        """
        # Initialize the custom config directory
        self._tmpdir = TempDir()
        self._tmpdir.create()
        dstpath = os.path.join(self._tmpdir.path, self.MOCK_DEFAULT)
        self._create_template(repolist, dstpath)
        for filename in self.MOCK_FILES:
            filepath = os.path.join(self.MOCK_DIR, filename)
            shutil.copy2(filepath, self._tmpdir.path)

        # Be sure all repos are initialized
        for repo in repolist:
            repo.create()

    def clean(self):
        """Clean temporary files and RPMS created for this instance."""
        self._tmpdir.delete()
        pattern = os.path.join(self.MOCK_RESULT % self._mockname, '*.rpm')
        for filepath in glob.glob(pattern):
            os.unlink(filepath)

#    def build_srpm(self, specpath, sourcedir):
#        """
#        Build a source RPMS using the provided Source RPM pointed by `srpm'
#        """
#        cmd = ['mock', '--configdir=%s' % self._tmpdir.path ]
#        cmd += ['--buildsrpm', '--spec', specpath, '--source', sourcedir]
#        popen = Popen(cmd, stdout=PIPE) #, stderr=STDOUT)
#        stdout = popen.communicate()[0]
#        if popen.returncode != 0:
#            raise RiftError(stdout)

    def build_rpms(self, srpm):
        """Build binary RPMS using the provided Source RPM pointed by `srpm'"""
        cmd = ['mock', '--configdir=%s' % self._tmpdir.path, srpm.filepath]
        popen = Popen(cmd, stdout=PIPE) #, stderr=STDOUT)
        stdout = popen.communicate()[0]
        if popen.returncode != 0:
            raise RiftError(stdout)
        # It could be nice if we can return the list of built RPMs here.

    def publish(self, repo):
        """
        Copy binary RPMS from Mock result directory into provided repository
        `repo'.
        """
        pattern = os.path.join(self.MOCK_RESULT % self._mockname, '*.rpm')
        for filepath in glob.glob(pattern):
            rpm = RPM(filepath)
            if not rpm.is_source:
                repo.add(rpm)
