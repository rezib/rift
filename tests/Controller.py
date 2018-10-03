#
# Copyright (C) 2018 CEA
#

import os.path

from TestUtils import make_temp_file, make_temp_dir, RiftTestCase

from rift.Controller import Config, main


class ControllerTest(RiftTestCase):

    def test_main_version(self):
        """simple 'rift --version'"""
        self.assert_except(SystemExit, "0", main, ['--version'])


class ControllerProjectTest(RiftTestCase):
    """
    Tests class for Controller where a dummy project tree is setup
    """

    def setUp(self):
        self.cwd = os.getcwd()
        self.projdir = make_temp_dir()
        # ./packages/
        self.packagesdir = os.path.join(self.projdir, 'packages')
        os.mkdir(self.packagesdir)
        # ./packages/staff.yaml
        self.staff = os.path.join(self.packagesdir, 'staff.yaml')
        with open(self.staff, "w") as staff:
            staff.write('staff: {}')
        # ./packages/modules.yaml
        self.modules = os.path.join(self.packagesdir, 'modules.yaml')
        with open(self.modules, "w") as staff:
            staff.write('modules: {}')
        # ./annex/
        self.annexdir = os.path.join(self.projdir, 'annex')
        os.mkdir(self.annexdir)
        # ./project.conf
        self.projectconf = os.path.join(self.projdir, Config._DEFAULT_FILES[0])
        with open(self.projectconf, "w") as conf:
           conf.write("annex:    %s\n" % self.annexdir)
           conf.write("vm_image: fake_img.img\n")
           conf.write("repos:    {}\n")
        os.chdir(self.projdir)

    def tearDown(self):
        os.chdir(self.cwd)
        os.unlink(self.projectconf)
        os.unlink(self.staff)
        os.unlink(self.modules)
        os.rmdir(self.annexdir)
        os.rmdir(self.packagesdir)
        os.rmdir(self.projdir)

    def test_action_query(self):
        """simple 'rift query' is ok"""
        self.assertEqual(main(['query']), 0)
