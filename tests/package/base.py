#
# Copyright (C) 2020 CEA
#
import os

from rift import RiftError
from rift.Config import Config, Staff, Modules
from rift.package import Package
from rift.package._base import _SOURCES_DIR, _DOC_FILES, _META_FILE, _TESTS_DIR
from ..TestUtils import make_temp_file, make_temp_dir, gen_rpm_spec, RiftTestCase

class RiftPackageTestCase(RiftTestCase):

    def init_config(self):
        self.config = Config()
        self.staff = Staff(config = self.config)
        self.staff_file = make_temp_file("""
staff:
  'J. Doe':
    email: 'j.doe@rift.org'
""")
        self.staff.load(self.staff_file.name)
        self.config_file = make_temp_file("""
modules:
  'Tools':
    manager: 'J. Doe'
""")
        self.modules = Modules(config = self.config, staff = self.staff)
        self.modules.load(self.config_file.name)


class PackageTest(RiftPackageTestCase):
    """
    Tests class for Package
    """
    def setUp(self):
        self.init_config()

    def test_init(self):
        """ Test Package initialisation """
        pkgname = 'pkg'
        self.config.project_dir = '/'
        pkg = Package(pkgname, self.config, self.staff, self.modules, 'rpm', f"{pkgname}.spec")
        self.assertEqual(pkg.dir, '/{0}/{1}'.format(self.config.get('packages_dir'), pkgname))
        self.assertEqual(pkg.sourcesdir, os.path.join(pkg.dir, _SOURCES_DIR))
        self.assertEqual(pkg.testsdir, os.path.join(pkg.dir, _TESTS_DIR))
        self.assertEqual(pkg.metafile, os.path.join(pkg.dir, _META_FILE))
        self.assertEqual(pkg.format, 'rpm')
        self.assertEqual(pkg.buildfile, '{0}/{1}.spec'.format(pkg.dir, pkgname))

    def test_init_invalid_format(self):
        with self.assertRaisesRegex(RiftError, "^Unsupported package format fail$"):
            Package('pkg', self.config, self.staff, self.modules, 'fail', 'build.fail')

    def test_load(self):
        """ Test Package information loading """
        pkgfile = make_temp_file("""
package:
  maintainers:
  - J. Doe
  module: Tools
  reason: Missing package
  origin: Company
        """)
        pkg = Package('pkg', self.config, self.staff, self.modules, 'rpm', 'pkg.spec')
        pkg.load(infopath = pkgfile.name)
        self.assertEqual(pkg.module, 'Tools')
        self.assertEqual(pkg.maintainers, ['J. Doe'])
        self.assertEqual(pkg.reason, 'Missing package')
        self.assertEqual(pkg.origin, 'Company')
