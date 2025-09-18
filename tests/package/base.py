#
# Copyright (C) 2020 CEA
#
import os
import textwrap
from unittest.mock import patch

from rift import RiftError
from rift.package import Package
from rift.package._base import ActionableArchPackage, Test, _SOURCES_DIR, _META_FILE, _TESTS_DIR
from rift.repository.rpm import ArchRepositoriesRPM
from ..TestUtils import RiftProjectTestCase, make_temp_file
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

    def test_tests(self):
        """ Test Package tests method """
        self.make_pkg()
        pkg = Package('pkg', self.config, self.staff, self.modules, 'rpm', 'pkg.spec')
        pkg.load()
        tests = [test for test in pkg.tests()]
        self.assertEqual(len(tests), 1)
        self.assertIsInstance(tests[0], Test)
        self.assertEqual(tests[0].name, '0_test')

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


class ActionableArchPackageTest(RiftProjectTestCase):
    def setUp(self):
        super().setUp()
        pkgname = 'pkg'
        self._pkg = Package(pkgname, self.config, self.staff,
            self.modules, 'rpm', f"{pkgname}.spec")
        self.pkg = ActionableArchPackage(self._pkg, 'x86_64')

    def test_init(self):
        """ Test initializer set attributes """
        self.assertEqual(self.pkg.name, 'pkg')
        self.assertEqual(self.pkg.buildfile, self._pkg.buildfile)
        self.assertEqual(self.pkg.config, self.config)
        self.assertEqual(self.pkg.package, self._pkg)
        self.assertEqual(self.pkg.arch, 'x86_64')
        self.assertIsInstance(self.pkg.repos, ArchRepositoriesRPM)

    def test_build_not_implemented(self):
        """ Test build method not implemented on abstract class """
        with self.assertRaises(NotImplementedError):
            self.pkg.build()

    def test_test_not_implemented(self):
        """ Test test method not implemented on abstract class """
        with self.assertRaises(NotImplementedError):
            self.pkg.test()

    @patch('rift.package._base.run_command')
    def test_run_local_test(self, mock_run_command):
        command = make_temp_file(
            textwrap.dedent("""\
                #!/bin/sh
                /bin/true
                """),
            suffix='.sh'
        )
        test = Test(command.name)
        self.pkg.run_local_test(test)
        mock_run_command.assert_called_once_with(
            command.name, capture_output=True, shell=True)

    @patch('rift.package._base.run_command')
    def test_run_local_test_with_funcs(self, mock_run_command):
        command = make_temp_file(
            textwrap.dedent("""\
                #!/bin/sh
                /bin/true
                """),
            suffix='.sh'
        )
        test = Test(command.name)
        self.pkg.run_local_test(test, { 'hey': 'echo hey!'})
        mock_run_command.assert_called_once_with(
            f"hey() {{ echo hey!; }}; export -f hey; {command.name}",
            capture_output=True, shell=True)

    def test_publish_not_implemented(self):
        """ Test publish method not implemented on abstract class """
        with self.assertRaises(NotImplementedError):
            self.pkg.publish()

    def test_clean(self):
        """ Test clean method no-op on abstract class """
        self.pkg.clean()


class TestTest(RiftProjectTestCase):
    def test_init(self):
        """ Test with analyzed command """
        command = make_temp_file(
            textwrap.dedent("""\
                #!/bin/sh
                # fake test
                /bin/true
                """),
            suffix='.sh'
        )
        test = Test(command.name)
        self.assertEqual(test.command, command.name)
        self.assertFalse(test.local)
        self.assertEqual(
            test.name, os.path.splitext(os.path.basename(command.name))[0])

    def test_init_local(self):
        """ Test with analyzed command to run locally """
        command = make_temp_file(
            textwrap.dedent("""\
                #!/bin/sh
                #
                # *** RIFT LOCAL ***
                #
                /bin/true
                """),
            suffix='.sh'
        )
        with self.assertLogs(level='DEBUG') as logs:
            test = Test(command.name)
        self.assertTrue(test.local)
        self.assertIn(
            f"DEBUG:root:Test '{test.name}' detected as local", logs.output)
