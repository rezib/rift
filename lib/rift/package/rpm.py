#
# Copyright (C) 2025 CEA
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
"""Manage packages in RPM format."""

import os
import shutil
import random
import textwrap
import time
import re
import logging

from rift import RiftError
from rift.package._base import Package, ActionableArchPackage, Test
from rift.Annex import Annex
from rift.Repository import ProjectArchRepositories, LocalRepository
from rift.Mock import Mock
from rift.RPM import Spec
from rift.TestResults import TestCase, TestResults
from rift.VM import VM
from rift.TempDir import TempDir
from rift.utils import message, banner

class PackageRPM(Package):
    """Handle rift project package in RPM format."""

    def __init__(self, name, config, staff, modules):
        super().__init__(name, config, staff, modules, 'rpm', f"{name}.spec")

        # Attribytes assigned in load()
        # Extracted from infos.yaml
        self.ignore_rpms = None
        self.rpmnames = None
        # Spec object
        self.spec = None

    def _serialize_specific_metadata(self):
        """Return dict of format specific metadata to write in metadata file."""
        data = {}
        if self.rpmnames:
            data['rpm_names'] = self.rpmnames
        if self.ignore_rpms:
            data['ignore_rpms'] = self.ignore_rpms
        return data

    def _deserialize_specific_metadata(self, data):
        """Set format specific object attribute with values in metadata dict."""
        if isinstance(data.get('rpm_names'), str):
            self.rpmnames = [data.get('rpm_names')]
        else:
            self.rpmnames = data.get('rpm_names')
        if isinstance(data.get('ignore_rpms'), str):
            self.ignore_rpms = [data.get('ignore_rpms')]
        else:
            self.ignore_rpms = data.get('ignore_rpms', [])

    def load(self, infopath=None):
        """Load package metadata, check its content and load RPM spec file."""
        # load infos.yaml with parent class
        super().load(infopath)
        self.spec = Spec(self.buildfile, config=self._config)

    def check(self):
        # Check generic package metadata
        super().check()

        # Check spec
        assert self.spec is not None
        message('Validate specfile...')
        self.spec.check(self)

    def add_changelog_entry(self, maintainer, comment, bump):
        """Add entry in RPM spec changelog."""
        # Check spec is already loaded
        assert self.spec is not None

        author = f"{maintainer} <{self._staff.get(maintainer)['email']}>"
        # Format comment.
        # Grab bullet, insert one if not found.
        bullet = "-"
        match = re.search(r'^([^\s\w])\s', comment, re.UNICODE)
        if match:
            bullet = match.group(1)
        else:
            comment = bullet + " " + comment

        if comment.find("\n") == -1:
            wrapopts = {"subsequent_indent": (len(bullet) + 1) * " ",
                        "break_long_words": False,
                        "break_on_hyphens": False}
            comment = textwrap.fill(comment, 80, **wrapopts)

        logging.info("Adding changelog record for '%s'", author)
        self.spec.add_changelog_entry(author, comment, bump)

    def supports_arch(self, arch):
        """
        Returns True is package spec file does not restrict ExclusiveArch or if
        the arch in argument is explicitely set in package ExclusiveArch.
        """
        assert self.spec is not None
        return not self.spec.exclusive_archs or arch in self.spec.exclusive_archs

    def for_arch(self, arch):
        """
        Return RPM package specialized for a given architecture.
        """
        return ActionableArchPackageRPM(self, arch)


class ActionableArchPackageRPM(ActionableArchPackage):
    """Handle rift project package in RPM format for a specific architecture."""

    def __init__(self, package, arch):
        super().__init__(package, arch)
        self.mock = Mock(self.config, arch, self.config.get('version'))
        self.repos = ProjectArchRepositories(self.config, self.arch)
        self.staging = None
        self.stagedir = None

    def build(self, **kwargs):
        message(f"Building package '{self.name}' on architecture {self.arch}")
        message('Preparing Mock environment...')
        self.mock.init(self.repos.all)

        message("Building SRPM...")
        sign = kwargs.get('sign', False)
        srpm = self._build_srpm(sign)
        logging.info("Built: %s", srpm.filepath)

        message("Building RPMS...")
        for rpm in self._build_rpms(srpm, sign):
            logging.info('Built: %s', rpm.filepath)
        message("RPMS successfully built")

    def test(self, **kwargs):
        """Execute test and return TestResults"""

        results = TestResults('test')
        if kwargs.get('staging', False):
            self._ensure_staging_repo()
            extra_repos=[self.staging.consumables[self.arch]]
        else:
            extra_repos=[]
        vm = VM(self.config, self.arch, extra_repos=extra_repos)

        if vm.running():
            raise RiftError('VM is already running')

        message(f"Preparing {self.arch} test environment")
        vm.start()
        if self.repos.working is None:
            disablestr = '--disablerepo=working'
        else:
            disablestr = ''
        vm.cmd(f"yum -y -d0 {disablestr} update")

        banner(f"Starting tests of package {self.name} on architecture {self.arch}")

        tests = list(self.package.tests())
        if not kwargs.get('noauto', False):
            tests.insert(0, BasicTest(self.package, config=self.config))
        for test in tests:
            case = TestCase(test.name, self.name, self.arch)
            now = time.time()
            message(f"Running test '{case.fullname}' on architecture '{self.arch}'")
            proc = vm.run_test(test)
            if proc.returncode == 0:
                results.add_success(case, time.time() - now, out=proc.out, err=proc.err)
                message(f"Test '{case.fullname}' on architecture {self.arch}: OK")
            else:
                results.add_failure(case, time.time() - now, out=proc.out,  err=proc.err)
                message(f"Test '{case.fullname}' on architecture {self.arch}: ERROR")

        if not kwargs.get('noquit', False):
            message(f"Cleaning {self.arch} test environment")
            vm.cmd("poweroff")
            time.sleep(5)
            vm.stop()

        return results

    def _ensure_staging_repo(self):
        """
        Ensure staging temporary repository directory is created, set staging
        and stagedir attributes with LocalRepository and TempDir objects
        respectively.
        """
        # Staging already defined, nothing more to do.
        if self.staging:
            return
        logging.info('Creating temporary repository')
        self.stagedir = TempDir('stagedir')
        self.stagedir.create()
        self.staging = LocalRepository(
            path=self.stagedir.path,
            config=self.config,
            name='staging',
            options={'module_hotfixes': "true"},
        )
        self.staging.create()

    def publish(self, **kwargs):
        if kwargs.get('staging', False):
            self._ensure_staging_repo()
            repo = self.staging
        else:
            repo = self.repos.working

        assert repo is not None

        message("Publishing RPMS...")
        self.mock.publish(repo)

        if kwargs.get('updaterepo', True):
            message("Updating repository...")
            repo.update()

    def clean(self, **kwargs):
        # Delete staging repository if defined and testing environment was
        # stopped.
        if not kwargs.get('noquit', False) and self.stagedir:
            self.stagedir.delete()
            self.staging = self.stagedir = None
        self.mock.clean()

    def _build_srpm(self, sign):
        """
        Build package source RPM
        """
        tmpdir = Annex(self.config).import_dir(self.package.sourcesdir,
                                               force_temp=True)

        # To avoid root_squash issue, also copy the specfile in the temp dir
        tmpspec = os.path.join(tmpdir.path, os.path.basename(self.buildfile))
        shutil.copyfile(self.buildfile, tmpspec)

        srpm = self.mock.build_srpm(tmpspec, tmpdir.path or self.package.sourcesdir, sign)
        tmpdir.delete()
        return srpm

    def _build_rpms(self, srpm, sign):
        """
        Build package RPMS using provided `srpm' and repository list for build
        requires.
        """
        return self.mock.build_rpms(srpm, sign)


class BasicTest(Test):
    """
    Auto-generated test for a Package.
    Setup a test to install a package and its dependencies.
        - pkg: package to test
        - config: rift configuration
    """

    def __init__(self, pkg, config=None):
        if pkg.rpmnames:
            rpmnames = pkg.rpmnames
        else:
            rpmnames = Spec(pkg.buildfile, config=config).pkgnames

        try:
            for name in pkg.ignore_rpms:
                rpmnames.remove(name)
        except ValueError as exc:
            raise RiftError(f"'{name}' is not in RPMS list") from exc

        # Avoid always processing the rpm list in the same order
        random.shuffle(rpmnames)

        cmd = textwrap.dedent(f"""
        if [ -x /usr/bin/dnf ] ; then
            YUM="dnf"
        else
            YUM="yum"
        fi
        i=0
        for pkg in {' '.join(rpmnames)}; do
            i=$(( $i + 1 ))
            echo -e "[Testing '${{pkg}}' (${{i}}/{len(rpmnames)})]"
            rm -rf /var/lib/${{YUM}}/history*
            if rpm -q --quiet $pkg; then
              ${{YUM}} -y -d1 upgrade $pkg || exit 1
            else
              ${{YUM}} -y -d1 install $pkg || exit 1
            fi
            if [ -n "$(${{YUM}} history | tail -n +3)" ]; then
                echo '> Cleanup last transaction'
                ${{YUM}} -y -d1 history undo last || exit 1
            else
                echo '> Warning: package already installed and up to date !'
            fi
        done""")
        Test.__init__(self, cmd, "basic_install")
        self.local = False
