#
# Copyright (C) 2020 CEA
#
import os

from rift import RiftError
from rift.package import Package
from rift.package._base import _SOURCES_DIR, _META_FILE, _TESTS_DIR
from ..TestUtils import RiftProjectTestCase
from rift.Gerrit import Review


class PackageTest(RiftProjectTestCase):
    """
    Tests class for Package
    """
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
        self.make_pkg()
        pkg = Package('pkg', self.config, self.staff, self.modules, 'rpm', 'pkg.spec')
        pkg.load()
        self.assertEqual(pkg.module, 'Great module')
        self.assertEqual(pkg.maintainers, ['Myself'])
        self.assertEqual(pkg.reason, 'Missing feature')
        self.assertEqual(pkg.origin, 'Vendor')

    def test_subpackages(self):
        """ Test Package subpackages (not implemented) """
        pkgname = 'pkg'
        pkg = Package(pkgname, self.config, self.staff, self.modules, 'rpm',
                      f"{pkgname}.spec")
        with self.assertRaises(NotImplementedError):
            pkg.subpackages()

    def test_build_requires(self):
        """ Test Package build requires (not implemented) """
        pkgname = 'pkg'
        pkg = Package(pkgname, self.config, self.staff, self.modules, 'rpm',
                      f"{pkgname}.spec")
        with self.assertRaises(NotImplementedError):
            pkg.build_requires()

    def test_add_changelog_entry(self):
        """ Test Package add changelog entry (not implemented) """
        pkgname = 'pkg'
        pkg = Package(pkgname, self.config, self.staff, self.modules, 'rpm',
                      f"{pkgname}.spec")
        with self.assertRaises(NotImplementedError):
            pkg.add_changelog_entry("Myself", "Package modification", False)

    def test_analyze(self):
        """ Test Package analyze (not implemented) """
        pkgname = 'pkg'
        pkg = Package(pkgname, self.config, self.staff, self.modules, 'rpm',
                      f"{pkgname}.spec")
        with self.assertRaises(NotImplementedError):
            pkg.analyze(Review(), pkg.dir)
