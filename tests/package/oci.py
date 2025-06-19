#
# Copyright (C) 2025 CEA
#
import os
from unittest.mock import Mock, patch

from rift import RiftError
from rift.Config import Config, Staff, Modules
from rift.package.oci import PackageOCI
from .base import RiftPackageTestCase
from ..TestUtils import make_temp_file

class PackageOCITest(RiftPackageTestCase):
    """
    Tests class for PackageOCI
    """
    def setUp(self):
        self.init_config()

    def test_init(self):
        """ Test PackageRPM initialisation """
        pkgname = 'pkg'
        pkg = PackageOCI(pkgname, self.config, self.staff, self.modules)
        self.assertEqual(pkg.format, 'oci')
        self.assertEqual(pkg.buildfile, f"{pkg.dir}/Containerfile")

    def test_load(self):
        """ Test PackageRPM information loading """
        pkgfile = make_temp_file("""
package:
  maintainers:
  - J. Doe
  module: Tools
  reason: Missing package
  origin: Company
  oci:
    version: 0.0.1
    release: 1
        """)
        pkg = PackageOCI('pkg', self.config, self.staff, self.modules)
        pkg.load(infopath = pkgfile.name)

    # test load missing version / release
    # test load main source
    # test load source topdir
    # test load
    # test check
    # test supports_arch
    # test for_arch
