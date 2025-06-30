#
# Copyright (C) 2025 CEA
#

import os

#from rift import RiftError
from rift.Config import Config#, Staff, Modules
from rift.package._virtual import PackageVirtual
from rift.package.rpm import PackageRPM
from rift.package import ProjectPackages
from .base import RiftPackageTestCase
#from ..TestUtils import make_temp_file, make_temp_dir, gen_rpm_spec
from ..TestUtils import make_temp_dir

class ProjectPackagesTest(RiftPackageTestCase):
    """
    Tests class for ProjectPackages
    """
    def setUp(self):
        self.init_config()
        self.project_dir = make_temp_dir()
        self.cwd = os.getcwd()
        os.chdir(self.project_dir)

    def tearDown(self):
        os.chdir(self.cwd)

    def fill_project_dir(self, packages):
        open(os.path.join(self.project_dir, Config._DEFAULT_FILES[0]), 'a').close()
        packages_dir = os.path.join(self.project_dir, self.config.get('packages_dir'))
        os.mkdir(packages_dir)
        for package, formats in packages.items():
            os.mkdir(os.path.join(packages_dir, package))
            if 'rpm' in formats:
                open(os.path.join(packages_dir, package, f"{package}.spec"), 'a').close()

    def test_list(self):
        """ Test ProjectPackages list() """
        packages_names = {'foo': ['rpm'], 'bar': ['rpm']}
        self.fill_project_dir(packages_names)
        packages = list(ProjectPackages.list(self.config, self.staff, self.modules))
        for package in packages:
            self.assertIsInstance(package, PackageRPM)
            self.assertIn(package.name, packages_names)
        self.assertEqual(len(packages), 2)

    def test_list_empty(self):
        """ Test ProjectPackages list() empty """
        self.fill_project_dir({})
        self.assertCountEqual(ProjectPackages.list(self.config, self.staff, self.modules), [])

    def test_list_with_names(self):
        """ Test ProjectPackages list() with names"""
        packages_names = {'foo': ['rpm'], 'bar': ['rpm']}
        list_names = ['bar', 'baz']
        self.fill_project_dir(packages_names)
        packages = list(ProjectPackages.list(self.config, self.staff, self.modules, list_names))
        self.assertEqual(len(packages), 2)
        for package in packages:
            self.assertIn(package.name, list_names)
            if package.name == 'bar':
                self.assertIsInstance(package, PackageRPM)
            else:
                self.assertIsInstance(package, PackageVirtual)

    def test_get_virtual(self):
        """ Test ProjectPackages get() virtual package"""
        packages = ProjectPackages.get('pkg', self.config, self.staff, self.modules)
        self.assertIsInstance(packages, list)
        self.assertEqual(len(packages), 1)
        self.assertIsInstance(packages[0], PackageVirtual)
        self.assertEqual(packages[0].name, 'pkg')

    def test_get_rpm(self):
        """ Test ProjectPackages get() RPM package"""
        self.fill_project_dir({'pkg': ['rpm']})
        packages = ProjectPackages.get('pkg', self.config, self.staff, self.modules)
        self.assertIsInstance(packages, list)
        self.assertEqual(len(packages), 1)
        self.assertIsInstance(packages[0], PackageRPM)
        self.assertEqual(packages[0].name, 'pkg')
