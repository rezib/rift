#
# Copyright (C) 2014 CEA
#

"""
Class to manipulate packages and package tests with Rift.
"""

import os
import yaml
import glob
import logging

from Rift import RiftError
from Rift.LookAside import LookAside

_META_FILE = 'info.yaml'
_SOURCES_DIR = 'sources'
_TESTS_DIR = 'tests'

class Package(object):
    """
    Base object in Rift framework.

    It creates, load, check, build and test a package.
    """

    def __init__(self, name, config, staff, modules):
        self._config = config
        self._staff = staff
        self._modules = modules
        self.name = name
        self.module = None
        self.maintainers = None
        self.reason = None
        self.origin = None
        self.rpmnames = None

        self.dir = os.path.join(self._config.get('packages_dir'), self.name)
        self.sourcesdir = os.path.join(self.dir, _SOURCES_DIR)
        self.testsdir = os.path.join(self.dir, _TESTS_DIR)
        self.metafile = os.path.join(self.dir, _META_FILE)
        self.specfile = os.path.join(self.dir, '%s.spec' % self.name)

    def check_info(self):
        """
        Check info.yaml content is correct.
        
        This uses Staff and Modules content.
        """
        
        # Check maintainers
        if not self.maintainers:
            raise RiftError("Maintainers are missing")
        for maintainer in self.maintainers:
            if maintainer not in self._staff.people:
                raise RiftError("Maintainer '%s' is not defined" % maintainer)

        # Check module
        if not self.module:
            raise RiftError("Module is missing")
        if self.module not in self._modules.modules:
            raise RiftError("Module '%s' is not defined" % self.module)

        # Check reason
        if self.reason is None:
            raise RiftError("Missing reason")

    def create(self):
        """Create the file and directory structure for this package instance."""
        # Create package directory if needed
        if not os.path.isdir(self.dir):
            os.mkdir(self.dir)

        # Write meta information
        data = {}
        if self.module:
            data['module'] = self.module
        if self.reason:
            data['reason'] = self.reason
        if self.maintainers:
            data['maintainers'] = self.maintainers
        if self.origin:
            data['origin'] = self.origin

        with open(self.metafile, 'w') as fyaml:
            yaml.dump({'package': data}, fyaml, default_flow_style=False)

    def load(self, infopath=None):
        """Read package metadata 'info.yaml' and check its content."""
 
        if infopath is None:
            if not os.path.exists(self.dir):
                msg = "Package '%s' directory does not exist" % self.name
                raise RiftError(msg)
            infopath = self.metafile

        with open(infopath) as fyaml:
            data = yaml.load(fyaml)

        data = data.pop('package') or {}
        self.module = data.get('module')
        if type(data.get('maintainers')) is str:
            self.maintainers = [data['maintainers']]
        else:
            self.maintainers = data.get('maintainers')
        self.reason = data.get('reason')
        self.origin = data.get('origin')
        if type(data.get('rpm_names')) is str:
            self.rpmnames = [data.get('rpm_names')]
        else:
            self.rpmnames = data.get('rpm_names')

        self.check_info()

    def tests(self):
        """An iterator over Test objects for each test files."""
        testspattern = os.path.join(self.testsdir, '*.sh')
        for testpath in glob.glob(testspattern):
            yield Test(testpath)

    def build_srpm(self, mock):
        """
        Build package source RPM
        """
        tmpdir = LookAside(self._config).import_dir(self.sourcesdir)
        srpm = mock.build_srpm(self.specfile, tmpdir.path or self.sourcesdir)
        tmpdir.delete()
        return srpm

    def build_rpms(self, mock, srpm):
        """
        Build package RPMS using provided `srpm' and repository list for build
        requires.
        """
        return mock.build_rpms(srpm)


class Test(object):
    """
    Wrapper around test scripts or test commands.
    
    It analyzes if test script is flagged as local one or if it should be run
    inside the VM.
    """

    _LOCAL_PATTERN = '*** RIFT LOCAL ***'

    def __init__(self, command, name=None):
        self.command = command
        self.local = False
        self.name = name
        if os.path.exists(self.command):
            self.name = name or os.path.splitext(os.path.basename(command))[0]
            self._analyze()

    def _analyze(self, blocksize=4096):
        """
        Look for special LOCAL PATTERN in file header and flag the file
        accordingly.
        """
        with open(self.command, 'rb') as ftest:
            data = ftest.read(blocksize)
            if self._LOCAL_PATTERN in data:
                logging.debug("Test '%s' detected as local", self.name)
                self.local = True
