#
# Copyright (C) 2014-2018 CEA
#

"""
Helper module to write unit tests for Rift project.
It contains several helper methods or classes like temporary file management.
"""

import tempfile
import unittest
import os

from rift.Config import Config, Staff, Modules


class RiftTestCase(unittest.TestCase):
    """unittest.TestCase subclass with additional features"""

    def __init__(self, methodName='runTest'):
        unittest.TestCase.__init__(self, methodName)
        # Allow to show the full content of a diff
        self.maxDiff = None

    def assert_except(self, exc_cls, exc_str, callable_obj, *args, **kwargs):
        """
        Same as TestCase.assertRaises() but with an additional argument to
        verify raised exception string is correct.
        """
        try:
            callable_obj(*args, **kwargs)
        except exc_cls as exp:
            self.assertEqual(str(exp), exc_str)
        else:
            self.fail("%s not raised" % exc_cls.__name__)

class RiftProjectTestCase(RiftTestCase):
    """
    RiftTestCase that setup a dummy project tree filled with minimal
    requirements.
    """

    def setUp(self):
        self.cwd = os.getcwd()
        self.projdir = make_temp_dir()
        # ./packages/
        self.packagesdir = os.path.join(self.projdir, 'packages')
        os.mkdir(self.packagesdir)
        # ./packages/staff.yaml
        self.staffpath = os.path.join(self.packagesdir, 'staff.yaml')
        with open(self.staffpath, "w") as staff:
            staff.write('staff: {Myself: {email: buddy@somewhere.org}}')
        # ./packages/modules.yaml
        self.modulespath = os.path.join(self.packagesdir, 'modules.yaml')
        with open(self.modulespath, "w") as mod:
            mod.write('modules: {Great module: {manager: Myself}}')
        # ./annex/
        self.annexdir = os.path.join(self.projdir, 'annex')
        os.mkdir(self.annexdir)
        # ./project.conf
        self.projectconf = os.path.join(self.projdir, Config._DEFAULT_FILES[0])
        with open(self.projectconf, "w") as conf:
            conf.write("annex:           %s\n" % self.annexdir)
            conf.write("vm_image:        test.img\n")
            conf.write("repos:           {}\n")
        os.chdir(self.projdir)
        # Dict of created packages
        self.pkgdirs = {}
        self.pkgspecs = {}
        self.pkgsrc = {}
        # Load project/staff/modules
        self.config = Config()
        self.config.load()
        self.staff = Staff(config=self.config)
        self.staff.load(self.staffpath)
        self.modules = Modules(config=self.config, staff=self.staff)
        self.modules.load(self.modulespath)

    def tearDown(self):
        os.chdir(self.cwd)
        os.unlink(self.projectconf)
        os.unlink(self.staffpath)
        os.unlink(self.modulespath)
        os.rmdir(self.annexdir)
        for spec in self.pkgspecs.values():
            os.unlink(spec)
        for src in self.pkgsrc.values():
            os.unlink(src)
        for pkgdir in self.pkgdirs.values():
            os.unlink(os.path.join(pkgdir, 'info.yaml'))
            os.rmdir(os.path.join(pkgdir, 'sources'))
            os.rmdir(pkgdir)
        os.rmdir(self.packagesdir)
        os.rmdir(self.projdir)


#
# Temp files
#
def make_temp_dir():
    """Create and return the name of a temporary directory."""
    return tempfile.mkdtemp(prefix='rift-test-')

def make_temp_filename():
    """Return a temporary name for a file."""
    return (tempfile.mkstemp(prefix='rift-test-'))[1]

def make_temp_file(text):
    """ Create a temporary file with the provided text."""
    tmp = tempfile.NamedTemporaryFile(prefix='rift-test-')
    tmp.write(text.encode())
    tmp.flush()
    return tmp
