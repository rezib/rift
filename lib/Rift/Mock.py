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
import logging
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
            assert repo.url is not None
            context['repos'].insert(0, {
                'name': repo.name or 'repo%s' % prio,
                'priority': prio,
                'url': repo.url })

        # Write file content
        with open(dstpath, 'w') as fmock:
            fmock.write(tpl.render(context))
        # We have to keep template timestamp to avoid being detected as a new
        # one each time.
        shutil.copystat(self.MOCK_TEMPLATE, dstpath)

    def _mock_base(self):
        """Return base argument to launch mock"""
        if logging.getLogger().isEnabledFor(logging.INFO):
            return ['mock', '--configdir=%s' % self._tmpdir.path]
        else:
            return ['mock', '-q', '--configdir=%s' % self._tmpdir.path]

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

        cmd = self._mock_base() + ['--init']
        popen = Popen(cmd, stdout=PIPE) #, stderr=STDOUT)
        stdout = popen.communicate()[0]
        if popen.returncode != 0:
            raise RiftError(stdout)

    def resultrpms(self, pattern='*.rpm', sources=True):
        """
        Iterate over built RPMS matching `pattern' in mock result directory.
        """
        pathname = os.path.join(self.MOCK_RESULT % self._mockname, pattern)
        for filepath in glob.glob(pathname):
            rpm = RPM(filepath)
            if sources or not rpm.is_source:
                yield rpm

    def clean(self):
        """Clean temporary files and RPMS created for this instance."""
        self._tmpdir.delete()
        for rpm in self.resultrpms():
            os.unlink(rpm.filepath)

    def build_srpm(self, specpath, sourcedir):
        """
        Build a source RPM using the provided spec file and source directory.
        """
        specpath = os.path.realpath(specpath)
        sourcedir = os.path.realpath(sourcedir)
        cmd = self._mock_base() + ['--buildsrpm']
        cmd += ['--spec', specpath, '--source', sourcedir]
        popen = Popen(cmd, stdout=PIPE) #, stderr=STDOUT)
        stdout = popen.communicate()[0]
        if popen.returncode != 0:
            raise RiftError(stdout)

        # XXX: Could be better if we do not use glob() here
        return list(self.resultrpms('*.src.rpm'))[0]

    def build_rpms(self, srpm):
        """Build binary RPMS using the provided Source RPM pointed by `srpm'"""
        cmd = self._mock_base() + ['--no-clean', '--no-cleanup-after']
        cmd += ['--configdir=%s' % self._tmpdir.path, srpm.filepath]
        popen = Popen(cmd, stdout=PIPE) #, stderr=STDOUT)
        stdout = popen.communicate()[0]
        if popen.returncode != 0:
            raise RiftError(stdout)

        # Return the list of built RPMs here.
        return self.resultrpms('*.rpm', sources=False)

    def publish(self, repo):
        """
        Copy binary RPMS from Mock result directory into provided repository
        `repo'.
        """
        pattern = os.path.join(self.MOCK_RESULT % self._mockname, '*.rpm')
        for filepath in glob.glob(pattern):
            repo.add(RPM(filepath))
