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
            staff.write('staff: {Myself: {email: buddy@somewhere.org}}')
        # ./packages/modules.yaml
        self.modules = os.path.join(self.packagesdir, 'modules.yaml')
        with open(self.modules, "w") as staff:
            staff.write('modules: {Great module: {manager: Myself}}')
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
        # Dict of created packages
        self.pkgdirs = {}
        self.pkgspecs = {}

    def tearDown(self):
        os.chdir(self.cwd)
        os.unlink(self.projectconf)
        os.unlink(self.staff)
        os.unlink(self.modules)
        os.rmdir(self.annexdir)
        for spec in self.pkgspecs.values():
            os.unlink(spec)
        for pkgdir in self.pkgdirs.values():
            os.unlink(os.path.join(pkgdir, 'info.yaml'))
            os.rmdir(pkgdir)
        os.rmdir(self.packagesdir)
        os.rmdir(self.projdir)

    def make_pkg(self, name='pkg'):
        # ./packages/pkg
        self.pkgdirs[name] = os.path.join(self.packagesdir, name)
        os.mkdir(self.pkgdirs[name])
        # ./packages/pkg/info.yaml
        info = os.path.join(self.pkgdirs[name], 'info.yaml')
        with open(info, "w") as nfo:
            nfo.write("package:\n")
            nfo.write("    maintainers:\n")
            nfo.write("        - Myself\n")
            nfo.write("    module: Great module\n")
            nfo.write("    origin: Vendor\n")
            nfo.write("    reason: Missing feature\n")

        # ./packages/pkg/pkg.spec
        self.pkgspecs[name] = os.path.join(self.pkgdirs[name],
                                           "{0}.spec".format(name))
        with open(self.pkgspecs[name], "w") as spec:
            spec.write("Name:    {0}\n".format(name))
            spec.write("Version:        1.0\n")
            spec.write("Release:        1\n")
            spec.write("Summary:        A package\n")
            spec.write("Group:          System Environment/Base\n")
            spec.write("License:        GPL\n")
            spec.write("URL:            http://nowhere.com/projects/%{name}/\n")
            spec.write("Source0:        %{name}-%{version}.tar.gz\n")
            spec.write("BuildArch:      noarch\n")
            spec.write("BuildRequires:  br-package\n")
            spec.write("Requires:       another-package\n")
            spec.write("Provides:       {0}-provide\n".format(name))
            spec.write("%description\n")
            spec.write("A package\n")
            spec.write("%prep\n")
            spec.write("%build\n")
            spec.write("# Nothing to build\n")
            spec.write("%install\n")
            spec.write("# Nothing to install\n")
            spec.write("%files\n")
            spec.write("# No files\n")



    def test_action_query(self):
        """simple 'rift query' is ok """
        self.assertEqual(main(['query']), 0)

    def test_action_query_on_pkg(self):
        """ Test query on one package """
        self.make_pkg()
        self.assertEqual(main(['query', 'pkg']), 0)
