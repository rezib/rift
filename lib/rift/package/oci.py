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
import os
import shutil
import time
import subprocess
import tempfile
import tarfile
import glob
import logging

from rift import RiftError
from rift.package._base import Package, ActionableArchPackage, Test
from rift.Annex import Annex
from rift.TestResults import TestCase, TestResults
from rift.utils import message, banner

class PackageOCI(Package):
    """Handle rift project package in OCI format."""

    def __init__(self, name, config, staff, modules):
        super().__init__(name, config, staff, modules, 'oci', 'Containerfile')
        self.version = None
        self.release = None
        self.main_source = None
        self.source_topdir = None

    def _serialize_specific_metadata(self):
        """Return dict of format specific metadata to write in metadata file."""
        data = {}
        data['oci'] = {
            'version': self.version,
            'release': self.release
        }
        if self.main_source:
            data['oci']['main_source'] = self.main_source
        if self.source_dir:
            data['oci']['source_topdir'] = self.source_topdir
        return data

    def _deserialize_specific_metadata(self, data):
        """Set format specific object attribute with values in metadata dict."""
        oci = data.get('oci')
        if oci:
            self.version = str(oci.get('version'))
            self.release = str(oci.get('release'))
            self.main_source = oci.get('main_source')
            self.source_topdir = oci.get('source_topdir')

    def _check_specific_info(self):
        """Check info.yaml OCI specific content is correct."""
        if not self.version:
            raise RiftError("Unable to load oci version from metadata")
        if not self.release:
            raise RiftError("Unable to load oci release from metadata")

    def supports_arch(self, arch):
        """
        Return True if arch is the same as host as building container image
        without foreign architecture is not supported.
        """
        return arch in ActionableArchPackageOCI.ARCHS_MAP.keys()

    def for_arch(self, arch):
        """
        Return OCI package specialized for a given architecture.
        """
        return ActionableArchPackageOCI(self, arch)


class ActionableArchPackageOCI(ActionableArchPackage):
    """Handle rift project package in OCI format for a specific architecture."""
    ARCHS_MAP = {
        'x86_64': 'amd64',
        'aarch64': 'arm64'
    }

    def __init__(self, package, arch):
        super().__init__(package, arch)
        self.rootdir = f"/tmp/rift-containers-{os.getlogin()}"
        self.tempdir = tempfile.TemporaryDirectory(prefix='rift-container-setup-')

    @property
    def default_source_topdir(self):
        return f"{self.name}-{self.package.version}"

    @property
    def default_main_source_glob(self):
        return f"{self.name}?{self.package.version}.*"

    @property
    def manifest(self):
        return f"{self.name}:{self.package.version}-{self.package.release}"

    @property
    def tag(self):
        return f"{self.manifest}-{self.arch}"

    def build(self, **kwargs):
        sources_topdir = self._setup_sources()
        message(f"Building container image '{self.name}' on architecture {self.arch}")
        cmd = [
            self.config.get('containers').get('command'),
            '--root', self.rootdir, 'build',
            '--arch', self.ARCHS_MAP[self.arch],
            '--manifest', self.manifest,
            '--annotation', f"org.opencontainers.image.version={self.package.version}-{self.package.release}",
            '--annotation', f"org.opencontainers.image.title={self.name}",
            '--annotation', f"org.opencontainers.image.vendir=rift",
            '--tag', self.tag ,
            sources_topdir ]
        try:
            proc = subprocess.run(cmd, check=True)
            message("Container image successfully built")
        except subprocess.CalledProcessError as err:
            logging.error("Container image build error: exit code %d", err.returncode)

    def _setup_sources(self):
        extracted_archive = None
        tmp_sourcesdir = Annex(self.config).import_dir(self.package.sourcesdir,
                                               force_temp=True)
        if not self.package.sources:
            raise RiftError(f"Unable to find sources for package {self.name}")
        if len(self.package.sources) == 1:
            _main_source = os.path.join(tmp_sourcesdir.path, self.package.sources.pop())
            self._extract_archive(_main_source)
            extracted_archive = _main_source
        else:
            # If main source is defined, check it is an archive and use it.
            if self.package.main_source:
                _main_source = os.path.join(tmp_sourcesdir.path, self.package.main_source)
                if _main_source not in self.packages.sources:
                    raise RiftError(f"Unable to find main source {self.main_source} among available package sources: {self.package.sources}")
                self._extract_archive(_main_source)
                extracted_archive = _main_source
            else:
                # Search archive matching default glob
                found_sources = glob.glob(os.path.join(tmp_sourcesdir.path, self.default_main_source_glob))
                if len(found_sources) != 1:
                    raise RiftError(f"Unable to determine main package source among available package sources: {self.package.sources}")
                self._extract_archive(found_sources[0])
                extracted_archive = found_sources[0]
        # Determine top dir
        topdir = os.path.join(self.tempdir.name, self.package.source_topdir or self.default_source_topdir)
        if not os.path.isdir(topdir):
            raise RiftError(f"Unable to find package source top directory {topdir}")
        # Copy all other sources
        for source in self.package.sources:
            _source = os.path.join(tmp_sourcesdir.path, source)
            if _source != extracted_archive:
                shutil.copy(_source, topdir)
        # Copy container file
        shutil.copy(self.buildfile, topdir)
        tmp_sourcesdir.delete()
        return topdir

    def _extract_archive(self, tarball):
        try:
            logging.info("Extracting source tarball %s", tarball)
            with tarfile.open(tarball) as _tarball:
                for member in self._safe_members(_tarball):
                    logging.debug("Extracting file %s", member.name)
                    _tarball.extract(member, path=self.tempdir.name)
        except (tarfile.ReadError, tarfile.CompressionError) as err:
            raise RiftError(f"Unable to extract source tarball {tarball}: {err}")

    def _safe_members(self, tarball):
        for member in tarball.getmembers():
            if os.path.isabs(member.name):
                raise RiftError(f"Source archive contains file {member.name} with absolute path")
            target = os.path.realpath(os.path.join(self.tempdir.name, member.name))
            if os.path.commonpath([target, self.tempdir.name]) != self.tempdir.name:
                raise RiftError(f"Source archive contains file {target} outside file tree")
            yield member

    def test(self, **kwargs):
        """Execute test and return TestResults"""
        results = TestResults('test')
        banner(f"Starting tests of package {self.name} on architecture {self.arch}")

        tests = list(self.package.tests())
        for test in tests:
            case = TestCase(test.name, self.name, self.arch)
            now = time.time()
            message("Running test '%s' on architecture '%s'" % (case.fullname, self.arch))
            cmd = [
                self.config.get('containers').get('command'),
                '--root', self.rootdir,
                'run', '--rm', '-i',
                '--mount', f"type=bind,src={test.command},dst=/run/{os.path.basename(test.command)},ro=true",
                '--arch', self.ARCHS_MAP[self.arch],
                f"localhost/{self.tag}",
                f"/run/{os.path.basename(test.command)}"
            ]
            run = subprocess.run(cmd)
            if run.returncode == 0:
                results.add_success(case, time.time() - now)
                message("Test '%s' on architecture %s: OK" % (case.fullname, self.arch))
            else:
                results.add_failure(case, time.time() - now)
                message("Test '%s' on architecture %s: ERROR" % (case.fullname, self.arch))
        return results

    def publish(self, **kwargs):
        # No notion of staging repository in OCI format, no-op in this case.
        if kwargs.get('staging', False):
            return
        message("Publishing container image...")
        self.repos.ensure_created()
        archive_path = os.path.join(self.repos.path,
            f"{self.name}_{self.package.version}-{self.package.release}.tar")
        cmd = [
            self.config.get('containers').get('command'),
            '--root', self.rootdir,
            'manifest', 'push', self.manifest,
            #'--compression-format', 'zstd',
            f"oci-archive:{archive_path}:{self.manifest}"
        ]
        run = subprocess.run(cmd)
        # podman --root /tmp/rift-containers-palancherr manifest push --all \
        # hellorust:0.0.1-1 oci-arch:hellorust_0.0.1-1.tar
