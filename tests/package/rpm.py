#
# Copyright (C) 2025 CEA
#

import os
import textwrap
import threading
from unittest.mock import ANY, Mock, patch

from rift import RiftError
from rift.config import _DEFAULT_VARIANT
from rift.gerrit import Review
from rift.package.rpm import (
    ActionableArchPackageRPM,
    BasicTest,
    PackageRPM,
    basic_test_rpmnames,
)
from rift.repository import StagingRepository
from rift.run import RunResult
from rift.test_results import TestResults
from rift.threads import SlotPool

from ..test_utils import (
    PackageTestDef,
    RiftProjectTestCase,
    gen_rpm_spec,
    host_rpmlint,
    make_temp_file,
    nullcontext,
    read_file,
)


class PackageRPMTest(RiftProjectTestCase):
    """
    Tests class for PackageRPM
    """

    def test_init(self):
        """Test PackageRPM initialisation"""
        pkgname = "pkg"
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        self.assertEqual(pkg.format, "rpm")
        self.assertEqual(pkg.buildfile, "{0}/{1}.spec".format(pkg.dir, pkgname))
        self.assertIsNone(pkg.ignore_rpms)
        self.assertIsNone(pkg.rpmnames)
        self.assertCountEqual(pkg.variants, [_DEFAULT_VARIANT])

    def test_load(self):
        """Test PackageRPM information loading"""
        pkgname = "pkg"
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(
            textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
                rpm_names:
                - pkg
                - pkg-devel
                ignore_rpms:
                - pkg-debuginfos
                variants:
                - variant1
                - variant2
            """)
        )
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load(infopath=pkgfile.name)
        self.assertEqual(pkg.rpmnames, ["pkg", "pkg-devel"])
        self.assertEqual(pkg.ignore_rpms, ["pkg-debuginfos"])
        self.assertCountEqual(pkg.variants, ["variant1", "variant2"])

    def test_check(self):
        """Test PackageRPM.check() does not fail with error"""
        pkgname = "pkg"
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(
            textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """)
        )
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        # Create sources dir and source
        sources_dir = os.path.join(pkg.dir, "sources")
        os.makedirs(sources_dir)
        with open(os.path.join(sources_dir, "pkg-1.0.tar.gz"), "w+") as fh:
            fh.write("data")
        pkg.buildfile = spec_file.name
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec.return_value = open(spec_file.name).read()
            pkg.load(infopath=pkgfile.name)
        with patch.object(pkg.spec.mock, "rpmlint", host_rpmlint):
            pkg.check()

    def test_check_missing_source(self):
        """Test PackageRPM.check() detect missing source"""
        pkgname = "pkg"
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(
            textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """)
        )
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load(infopath=pkgfile.name)
        with patch.object(pkg.spec.mock, "rpmlint", host_rpmlint):
            with self.assertRaisesRegex(
                RiftError, r"Missing source file\(s\): pkg-1.0.tar.gz"
            ):
                pkg.check()

    def test_check_unused_source(self):
        """Test PackageRPM.check() detect unused source"""
        pkgname = "pkg"
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(
            textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """)
        )
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        # Create sources dir, source and unused source
        sources_dir = os.path.join(pkg.dir, "sources")
        os.makedirs(sources_dir)
        with open(os.path.join(sources_dir, "pkg-1.0.tar.gz"), "w+") as fh:
            fh.write("data")
        with open(os.path.join(sources_dir, "unused-1.0.tar.gz"), "w+") as fh:
            fh.write("data")
        pkg.buildfile = spec_file.name
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load(infopath=pkgfile.name)
        with patch.object(pkg.spec.mock, "rpmlint", host_rpmlint):
            with self.assertRaisesRegex(
                RiftError, r"Unused source file\(s\): unused-1.0.tar.gz"
            ):
                pkg.check()

    def test_subpackages(self):
        """Test PackageRPM.subpackages() returns list of provides"""
        self.make_pkg()
        pkg = PackageRPM("pkg", self.config, self.staff, self.modules)
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load()
        self.assertCountEqual(pkg.subpackages(), ["pkg", "pkg-provide"])

    def test_build_requires(self):
        """Test PackageRPM.build_requires() returns list of build requirements"""
        self.make_pkg()
        pkg = PackageRPM("pkg", self.config, self.staff, self.modules)
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load()
        self.assertCountEqual(pkg.build_requires(), ["br-package"])

    def test_build_requires_explicit_versions(self):
        """
        Test PackageRPM.build_requires() returns list of build requirements with
        explicit versioning.
        """
        self.make_pkg(
            build_requires=["lib1-devel", "lib2-devel >= 3.4", "lib3-devel < 6.0.0"]
        )
        pkg = PackageRPM("pkg", self.config, self.staff, self.modules)
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load()
        self.assertCountEqual(
            pkg.build_requires(), ["lib1-devel", "lib2-devel", "lib3-devel"]
        )

    def test_add_changelog_entry(self):
        """Test PackageRPM add changelog entry"""
        pkgname = "pkg"
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(
            textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """)
        )
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load(infopath=pkgfile.name)
        pkg.add_changelog_entry("Myself", "Package modification", False)
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load(infopath=pkgfile.name)
        self.assertEqual(
            pkg.spec.changelog_name, "Myself <buddy@somewhere.org> - 1.0-1"
        )

    def test_add_changelog_entry_bump(self):
        """Test PackageRPM add changelog entry with release bump"""
        pkgname = "pkg"
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(
            textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """)
        )
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load(infopath=pkgfile.name)
        pkg.add_changelog_entry("Myself", "Package modification", True)
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load(infopath=pkgfile.name)
        self.assertEqual(
            pkg.spec.changelog_name, "Myself <buddy@somewhere.org> - 1.0-2"
        )

    def test_add_changelog_entry_unknown_maintainer(self):
        """Test PackageRPM add changelog entry with unknown maintainer"""
        pkgname = "pkg"
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(
            textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """)
        )
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load(infopath=pkgfile.name)
        with self.assertRaisesRegex(
            RiftError, "Unknown maintainer Unknown, cannot be found in staff"
        ):
            pkg.add_changelog_entry("Unknown", "Package modification", False)

    def test_has_real_variants(self):
        """Test PackageRPM has_real_variants()"""
        pkg = PackageRPM("pkg", self.config, self.staff, self.modules)
        self.assertFalse(pkg.has_real_variants())
        pkg.variants = ["variant1"]
        self.assertTrue(pkg.has_real_variants())
        pkg.variants = [_DEFAULT_VARIANT, "variant2"]
        self.assertTrue(pkg.has_real_variants())
        pkg.variants = ["variant1", "variant2"]
        self.assertTrue(pkg.has_real_variants())

    def test_supports_arch_w_exclusive_arch(self):
        """Test PackageRPM supports_arch() method with ExclusiveArch"""
        pkgname = "pkg"
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(
            textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """)
        )
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                exclusive_arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load(infopath=pkgfile.name)
        self.assertTrue(pkg.supports_arch("x86_64"))
        self.assertFalse(pkg.supports_arch("aarch64"))

    def test_supports_arch_wo_exclusive_arch(self):
        """Test PackageRPM supports_arch() method without ExclusiveArch"""
        pkgname = "pkg"
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(
            textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """)
        )
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
            )
        )
        pkg.buildfile = spec_file.name
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load(infopath=pkgfile.name)
        self.assertTrue(pkg.supports_arch("x86_64"))
        self.assertTrue(pkg.supports_arch("aarch64"))

    def test_analyze(self):
        """Test PackageRPM analyze success"""
        pkgname = "pkg"
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(
            textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """)
        )
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
            ),
            suffix=".spec",
        )
        pkg.buildfile = spec_file.name
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load(infopath=pkgfile.name)
        review = Mock(spec=Review)
        with patch.object(pkg.spec.mock, "rpmlint", host_rpmlint):
            pkg.analyze(review, pkg.dir)
        review.invalidate.assert_not_called()

    def test_analyze_invalidate(self):
        """Test PackageRPM analyze failure"""
        pkgname = "pkg"
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkgfile = make_temp_file(
            textwrap.dedent("""
            package:
                maintainers:
                - Myself
                module: Great module
                reason: Missing package
                origin: Company
            """)
        )
        # Use $$RPM_SOURCE_DIR and $RPM_BUILD_ROOT in build steps in order to
        # produce error in both rpmlint v1 and v2.
        spec_file = make_temp_file(
            gen_rpm_spec(
                name=pkgname,
                version="1.0",
                release="1",
                arch="x86_64",
                buildsteps="$RPM_SOURCE_DIR\n$RPM_BUILD_ROOT",
            ),
            suffix=".spec",
        )
        pkg.buildfile = spec_file.name
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            pkg.load(infopath=pkgfile.name)
        review = Mock(spec=Review)
        with patch.object(pkg.spec.mock, "rpmlint", host_rpmlint):
            pkg.analyze(review, pkg.dir)
        review.invalidate.assert_called_once()

    def test_for_arch(self):
        """Test PackageRPM for_arch() returns ActionableArchPackageRPM object."""
        pkgname = "pkg"
        pkg = PackageRPM(pkgname, self.config, self.staff, self.modules)
        pkg_arch = pkg.for_arch("x86_64", _DEFAULT_VARIANT)
        self.assertIsInstance(pkg_arch, ActionableArchPackageRPM)
        self.assertEqual(pkg_arch.name, pkg.name)
        self.assertEqual(pkg_arch.buildfile, pkg.buildfile)
        self.assertEqual(pkg_arch.config, pkg._config)
        self.assertEqual(pkg_arch.package, pkg)
        self.assertEqual(pkg_arch.arch, "x86_64")
        self.assertEqual(pkg_arch.variant, _DEFAULT_VARIANT)


class ActionableArchPackageRPMTest(RiftProjectTestCase):
    """
    Tests class for ActionableArchPackageRPM
    """

    def setup_package(self, variants=None, tests=None):
        self.make_pkg(variants=variants, tests=tests)
        _pkg = PackageRPM("pkg", self.config, self.staff, self.modules)
        # mock Mock.read_spec to return spec file content directly read on host
        with patch("rift.package.rpm.Mock") as mock_mock:
            mock_mock.return_value.read_spec = read_file
            _pkg.load()
        self.pkg = ActionableArchPackageRPM(_pkg, "x86_64", _pkg.variants[0])
        self.pkg.mock.read_spec = read_file

    @patch("rift.package.rpm.message")
    @patch("rift.package.rpm.Mock.build_rpms")
    @patch("rift.package.rpm.Mock.build_srpm")
    @patch("rift.package.rpm.Mock.init")
    def test_build(
        self, mock_mock_init, mock_mock_build_srpm, mock_mock_build_rpms, mock_message
    ):
        """Test ActionableArchPackageRPM build"""
        self.setup_package()
        self.pkg.build(variant=_DEFAULT_VARIANT)
        # Check build() has called expected Mock methods.
        mock_mock_init.assert_called_once_with([])
        mock_mock_build_srpm.assert_called_once()
        mock_mock_build_rpms.assert_any_call(
            mock_mock_build_srpm.return_value, _DEFAULT_VARIANT, self.pkg.repos, False
        )
        mock_message.assert_any_call("Building RPMS...")

    @patch("rift.package.rpm.Mock.build_rpms")
    @patch("rift.package.rpm.Mock.build_srpm")
    @patch("rift.package.rpm.Mock.init")
    def test_build_sign(
        self, mock_mock_init, mock_mock_build_srpm, mock_mock_build_rpms
    ):
        """Test ActionableArchPackageRPM build with sign enabled"""
        self.setup_package()
        self.pkg.build(sign=True, variant=_DEFAULT_VARIANT)
        # Check build() has called expected Mock methods.
        mock_mock_init.assert_called_once_with([])
        mock_mock_build_srpm.assert_called_once()
        mock_mock_build_rpms.assert_any_call(
            mock_mock_build_srpm.return_value, _DEFAULT_VARIANT, self.pkg.repos, True
        )

    @patch("rift.package.rpm.Mock.build_rpms")
    @patch("rift.package.rpm.Mock.build_srpm")
    @patch("rift.package.rpm.Mock.init")
    def test_build_staging(
        self, mock_mock_init, mock_mock_build_srpm, mock_mock_build_rpms
    ):
        """Test ActionableArchPackageRPM build with staging repository"""
        self.setup_package()
        staging = StagingRepository(self.config)
        self.pkg.build(staging=staging, variant=_DEFAULT_VARIANT)
        staging.delete()
        # Check build() has called expected Mock methods.
        mock_mock_init.assert_called_once_with(
            [staging.for_format("rpm").repo.consumables["x86_64"]]
        )
        mock_mock_build_srpm.assert_called_once()
        mock_mock_build_rpms.assert_any_call(
            mock_mock_build_srpm.return_value, _DEFAULT_VARIANT, self.pkg.repos, False
        )

    @patch("rift.package.rpm.Mock.clean")
    @patch("rift.package.rpm.Mock.init")
    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_local(
        self, mock_vm, mock_time_sleep, mock_mock_init, mock_mock_clean
    ):
        """Test ActionableArchPackageRPM local test"""
        # mock time.sleep() to avoid waiting sleep timeout when VM is stopped
        mock_vm_obj = mock_vm.return_value
        mock_vm_obj.running.return_value = False
        mock_vm_obj.run_test.return_value = RunResult(0, None, None)
        self.setup_package(
            tests=[PackageTestDef(name="0_test.sh", local=True, formats=[])]
        )
        self.pkg.run_local_test = Mock(return_value=RunResult(0, None, None))
        results = self.pkg.test(variant=_DEFAULT_VARIANT)
        self.assertIsInstance(results, TestResults)
        self.assertEqual(len(results), 2)
        self.assertEqual(results.global_result, True)
        # Check run_local_test() has been called once for local dummy test
        self.pkg.run_local_test.assert_called_once()
        # Check vm.run_test has been called once for basic test
        mock_vm_obj.run_test.assert_called_once_with(ANY, _DEFAULT_VARIANT)
        # Check VMs of both tests are stopped after the tests
        self.assertEqual(mock_vm_obj.stop.call_count, 2)

    @patch("rift.package.rpm.Mock.clean")
    @patch("rift.package.rpm.Mock.init")
    @patch("rift.package._base.banner")
    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_vm(
        self, mock_vm, mock_time_sleep, mock_banner, mock_mock_init, mock_mock_clean
    ):
        """Test ActionableArchPackageRPM test in VM"""
        # mock time.sleep() to avoid waiting sleep timeout when VM is stopped
        mock_vm_obj = mock_vm.return_value
        mock_vm_obj.running.return_value = False
        mock_vm_obj.run_test.return_value = RunResult(0, None, None)
        self.setup_package(tests=[])
        self.pkg.run_local_test = Mock(return_value=RunResult(0, None, None))
        results = self.pkg.test(variant=_DEFAULT_VARIANT)
        self.assertIsInstance(results, TestResults)
        self.assertEqual(len(results), 1)
        self.assertEqual(results.global_result, True)
        # Check run_local_test() has not been called.
        self.pkg.run_local_test.assert_not_called()
        # Check VM initialized (w/o extra repository)
        mock_vm.assert_called_once_with(self.config, "x86_64", extra_repos=[], slot=0)
        # Check VM run_test() called once for basic test
        mock_vm_obj.run_test.assert_called_once_with(ANY, _DEFAULT_VARIANT)
        # Check VM is stopped after the tests
        mock_vm_obj.stop.assert_called_once()
        mock_banner.assert_any_call(
            "Starting tests of package pkg on architecture x86_64"
        )

    @patch("rift.package.rpm.Mock.clean")
    @patch("rift.package.rpm.Mock.init")
    @patch("rift.package._base.banner")
    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_staging(
        self, mock_vm, mock_time_sleep, mock_banner, mock_mock_init, mock_mock_clean
    ):
        """Test ActionableArchPackageRPM test with staging repository"""
        # mock time.sleep() to avoid waiting sleep timeout when VM is stopped
        mock_vm_obj = mock_vm.return_value
        mock_vm_obj.running.return_value = False
        mock_vm_obj.run_test.return_value = RunResult(0, None, None)
        self.setup_package()
        staging = StagingRepository(self.config)
        results = self.pkg.test(staging=staging, variant=_DEFAULT_VARIANT)
        staging.delete()
        self.assertIsInstance(results, TestResults)
        self.assertEqual(len(results), 2)
        self.assertEqual(results.global_result, True)
        # Check both VMs initialized with staging extra repository
        self.assertEqual(mock_vm.call_count, 2)
        mock_vm.assert_called_with(
            self.config,
            "x86_64",
            extra_repos=[staging.for_format("rpm").repo.consumables["x86_64"]],
            slot=ANY,
        )
        # Check VMs are stopped after the tests
        self.assertEqual(mock_vm_obj.stop.call_count, 2)
        mock_banner.assert_any_call(
            "Starting tests of package pkg on architecture x86_64"
        )

    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_vm_running(self, mock_vm, mock_time_sleep):
        """Test ActionableArchPackageRPM test error VM running"""
        # mock time.sleep() to avoid waiting sleep timeout when VM is stopped
        mock_vm_obj = mock_vm.return_value
        mock_vm_obj.running.return_value = True
        self.setup_package()
        self._mock_spec_read()
        results = self.pkg.test(variant=_DEFAULT_VARIANT)
        # Every test is reported as failed with the error
        self.assertEqual(len(results), 2)
        self.assertFalse(results.global_result)
        for result in results.results:
            self.assertEqual(result.err, "VM is already running")
        # VM that was not started by this test must not be stopped
        mock_vm_obj.stop.assert_not_called()
        mock_vm_obj.start.assert_not_called()

    @patch("rift.package.rpm.VM")
    def test_test_vm_running_noquit(self, mock_vm):
        """Test ActionableArchPackageRPM test noquit error VM running"""
        mock_vm.return_value.running.return_value = True
        self.setup_package()
        with self.assertRaisesRegex(RiftError, "^VM is already running$"):
            self.pkg.test(noquit=True)

    def _mock_spec_read(self):
        """Mock Mock.read_spec() so BasicTest can extract rpm packages from spec."""
        self.pkg.mock = Mock()
        self.pkg.mock.lock.side_effect = lambda: nullcontext()
        with open(self.buildfiles["pkg:rpm"], encoding="utf-8") as fh:
            self.pkg.mock.read_spec.return_value = fh.read()

    def _setup_parallel(self, mock_vm, tests_count):
        """Prepare package with given number of tests on top of basic test."""
        mock_vm.return_value.running.return_value = False
        mock_vm.return_value.run_test.return_value = RunResult(0, None, None)
        self.setup_package(
            tests=[
                PackageTestDef(name=f"{i}_test.sh", local=False, formats=[])
                for i in range(tests_count)
            ]
        )
        self._mock_spec_read()

    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_parallel(self, mock_vm, mock_time_sleep):
        """Test tests run concurrently, each one in its own VM"""
        self._setup_parallel(mock_vm, 2)
        # Barrier is released only if the 3 tests overlap.
        barrier = threading.Barrier(3, timeout=30)

        def run_test(*_):
            barrier.wait()
            return RunResult(0, None, None)

        mock_vm.return_value.run_test.side_effect = run_test
        results = self.pkg.test()
        self.assertTrue(results.global_result)
        # basic test always reported first, whatever threads completion order.
        self.assertEqual(
            [result.case.name for result in results.results][0], "basic_install.pkg"
        )
        self.assertCountEqual(
            [result.case.name for result in results.results],
            ["basic_install.pkg", "0_test", "1_test"],
        )
        # One VM per test on distinct slots, all of them are stopped.
        self.assertCountEqual(
            [vm_call.kwargs["slot"] for vm_call in mock_vm.call_args_list], [0, 1, 2]
        )
        self.assertEqual(mock_vm.return_value.start.call_count, 3)
        self.assertEqual(mock_vm.return_value.stop.call_count, 3)

    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_slots_limit(self, mock_vm, mock_time_sleep):
        """Test concurrent tests do not exceed the slot pool"""
        self._setup_parallel(mock_vm, 4)
        lock = threading.Lock()
        running = [0]
        peak = [0]

        def run_test(*_):
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            threading.Event().wait(0.02)
            with lock:
                running[0] -= 1
            return RunResult(0, None, None)

        mock_vm.return_value.run_test.side_effect = run_test
        results = self.pkg.test(slots=SlotPool(2))
        self.assertEqual(len(results), 5)
        self.assertEqual(peak[0], 2)
        self.assertLessEqual(
            {vm_call.kwargs["slot"] for vm_call in mock_vm.call_args_list}, {0, 1}
        )

    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_config_jobs(self, mock_vm, mock_time_sleep):
        """Test limit of concurrent tests is read from configuration by default"""
        self._setup_parallel(mock_vm, 3)
        self.config.set("test_jobs", 1)
        results = self.pkg.test()
        self.assertEqual(len(results), 4)
        self.assertEqual(
            {vm_call.kwargs["slot"] for vm_call in mock_vm.call_args_list}, {0}
        )

    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_setup_failure(self, mock_vm, mock_time_sleep):
        """Test VM setup failure only fails the related test and stops its VM"""
        self._setup_parallel(mock_vm, 2)
        mock_vm.return_value.start.side_effect = [RiftError("no boot"), True, True]
        results = self.pkg.test()
        self.assertEqual(len(results), 3)
        self.assertFalse(results.global_result)
        self.assertEqual(
            [result.value for result in results.results].count("Failure"), 1
        )
        self.assertIn("no boot", [result.err for result in results.results])
        self.assertEqual(mock_vm.return_value.run_test.call_count, 2)
        self.assertEqual(mock_vm.return_value.stop.call_count, 3)

    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_crash(self, mock_vm, mock_time_sleep):
        """Test unexpected error is reported as test failure"""
        self._setup_parallel(mock_vm, 0)
        mock_vm.return_value.run_test.side_effect = RuntimeError("crash")
        results = self.pkg.test()
        self.assertEqual(len(results), 1)
        self.assertFalse(results.global_result)
        self.assertEqual(results.results[0].err, "crash")
        mock_vm.return_value.stop.assert_called_once()

    @patch("rift.threads.RiftThread")
    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_seq(self, mock_vm, mock_time_sleep, mock_thread):
        """Test seq runs tests without thread, each one still in its own VM"""
        self._setup_parallel(mock_vm, 2)
        results = self.pkg.test(seq=True)
        self.assertEqual(len(results), 3)
        mock_thread.assert_not_called()
        self.assertEqual(mock_vm.call_count, 3)
        self.assertEqual(mock_vm.return_value.stop.call_count, 3)

    @patch("rift.threads.banner")
    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_quiet(self, mock_vm, mock_time_sleep, mock_banner):
        """Test quiet omits output of succeeding tests only"""
        self._setup_parallel(mock_vm, 0)
        self.pkg.test(quiet=True)
        mock_banner.assert_not_called()
        mock_vm.return_value.run_test.return_value = RunResult(1, None, None)
        self.pkg.test(quiet=True)
        mock_banner.assert_called_once_with(
            "Test thread test-x86_64-main-basic_install.pkg output:"
        )

    def test_basic_test_keeps_rpmnames(self):
        """Test RPM names of basic tests do not modify package RPM names"""
        self.setup_package()
        self.pkg.package.rpmnames = ["pkg", "pkg-devel", "pkg-debug"]
        self.pkg.package.ignore_rpms = ["pkg-debug"]
        for _ in range(2):
            self.assertEqual(
                basic_test_rpmnames(
                    self.pkg.package, Mock(), [], _DEFAULT_VARIANT, config=self.config
                ),
                ["pkg", "pkg-devel"],
            )
        self.assertEqual(self.pkg.package.rpmnames, ["pkg", "pkg-devel", "pkg-debug"])

    def test_basic_test_command(self):
        """Test BasicTest installs or upgrades its RPM only, without cleanup"""
        test = BasicTest("pkg-devel")
        self.assertEqual(test.name, "basic_install.pkg-devel")
        self.assertFalse(test.local)
        self.assertIn("rpm -q --quiet pkg-devel", test.command)
        self.assertIn("${YUM} -y -d1 upgrade pkg-devel", test.command)
        self.assertIn("${YUM} -y -d1 install pkg-devel", test.command)
        self.assertNotIn("history", test.command)
        # RPM name is quoted in shell command
        self.assertIn("install 'pkg;reboot'", BasicTest("pkg;reboot").command)

    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_basic_per_rpm(self, mock_vm, mock_time_sleep):
        """Test one basic test per RPM, each one in its own VM concurrently"""
        self._setup_parallel(mock_vm, 1)
        self.pkg.package.rpmnames = ["a", "b", "c"]
        self.pkg.package.ignore_rpms = ["b"]
        # Barrier is released only if the 3 tests overlap.
        barrier = threading.Barrier(3, timeout=30)

        def run_test(test, _):
            barrier.wait()
            # Installation of RPM a fails
            return RunResult(int(test.name == "basic_install.a"), None, None)

        mock_vm.return_value.run_test.side_effect = run_test
        results = self.pkg.test()
        self.assertEqual(
            [(result.case.name, result.value) for result in results.results],
            [
                ("basic_install.a", "Failure"),
                ("basic_install.c", "Success"),
                ("0_test", "Success"),
            ],
        )
        self.assertCountEqual(
            [vm_call.kwargs["slot"] for vm_call in mock_vm.call_args_list], [0, 1, 2]
        )

    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_basic_all_ignored(self, mock_vm, mock_time_sleep):
        """Test no basic test when all RPMs are ignored"""
        self._setup_parallel(mock_vm, 1)
        self.pkg.package.rpmnames = ["a"]
        self.pkg.package.ignore_rpms = ["a"]
        results = self.pkg.test()
        self.assertEqual([result.case.name for result in results.results], ["0_test"])

    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_failure(self, mock_vm, mock_time_sleep):
        """Test ActionableArchPackageRPM test failure"""
        # mock time.sleep() to avoid waiting sleep timeout when VM is stopped
        mock_vm_obj = mock_vm.return_value
        mock_vm_obj.running.return_value = False
        mock_vm_obj.run_test.return_value = RunResult(1, None, None)
        self.setup_package()
        # mock Mock.read_spec() so BasicTest can extract rpm packages from spec file
        self.pkg.mock = Mock()
        self.pkg.mock.lock.return_value = nullcontext()
        self.pkg.mock.read_spec.return_value = open(self.buildfiles["pkg:rpm"]).read()
        results = self.pkg.test(variant=_DEFAULT_VARIANT)
        self.assertIsInstance(results, TestResults)
        self.assertEqual(len(results), 2)
        self.assertEqual(results.global_result, False)

    @patch("rift.package.rpm.time.sleep")
    @patch("rift.package.rpm.VM")
    def test_test_noauto(self, mock_vm, mock_time_sleep):
        """Test ActionableArchPackageRPM test noauto"""
        # mock time.sleep() to avoid waiting sleep timeout when VM is stopped
        mock_vm_obj = mock_vm.return_value
        mock_vm_obj.running.return_value = False
        self.setup_package(tests=[])
        results = self.pkg.test(noauto=True, variant=_DEFAULT_VARIANT)
        # Check empty TestResults
        self.assertIsInstance(results, TestResults)
        self.assertEqual(len(results), 0)
        self.assertEqual(results.global_result, True)

    @patch("rift.package.rpm.VM")
    def test_test_noquit(self, mock_vm):
        """Test ActionableArchPackageRPM test noquit"""
        mock_vm_obj = mock_vm.return_value
        mock_vm_obj.running.return_value = False
        mock_vm_obj.run_test.return_value = RunResult(0, None, None)
        self.setup_package()
        # mock Mock.read_spec() so BasicTest can extract rpm packages from spec file
        self.pkg.mock = Mock()
        self.pkg.mock.lock.return_value = nullcontext()
        self.pkg.mock.read_spec.return_value = open(self.buildfiles["pkg:rpm"]).read()
        results = self.pkg.test(noquit=True, variant=_DEFAULT_VARIANT)
        self.assertEqual(len(results), 2)
        # Check all tests run in one VM on the slot of the variant
        mock_vm.assert_called_once_with(self.config, "x86_64", extra_repos=[], slot=0)
        self.assertEqual(mock_vm_obj.run_test.call_count, 2)
        # Check VM is NOT stopped after the tests
        mock_vm_obj.stop.assert_not_called()

    @patch("rift.package.rpm.Mock.publish")
    def test_publish_working_repo(self, mock_mock_publish):
        """Test ActionableArchPackageRPM publish in working repository"""
        mock_repository = Mock()
        self.setup_package()
        self.pkg.repos.working = mock_repository
        self.pkg.publish()
        mock_mock_publish.assert_called_once_with(mock_repository)
        mock_repository.update.assert_called_once()

    @patch("rift.package.rpm.Mock.publish")
    def test_publish_staging_repo(self, mock_mock_publish):
        """Test ActionableArchPackageRPM publish in staging repository"""
        mock_staging_repo = Mock()
        self.setup_package()
        self.pkg.publish(staging=mock_staging_repo)
        mock_mock_publish.assert_called_once_with(mock_staging_repo.for_format().repo)
        mock_staging_repo.for_format().repo.update.assert_called_once()

    @patch("rift.package.rpm.Mock.publish")
    def test_publish_no_update(self, mock_mock_publish):
        """Test ActionableArchPackageRPM publish"""
        mock_repository = Mock()
        self.setup_package()
        self.pkg.repos.working = mock_repository
        self.pkg.publish(updaterepo=False)
        mock_mock_publish.assert_called_once_with(mock_repository)
        # Check repo is NOT uppdated
        mock_repository.update.assert_not_called()

    @patch("rift.package.rpm.Mock.clean")
    def test_clean(self, mock_mock_clean):
        """Test ActionableArchPackageRPM clean"""
        self.setup_package()
        self.pkg.clean()
        # Check clean() has called expected Mock method.
        mock_mock_clean.assert_called_once()
