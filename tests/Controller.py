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
        self.pkgsrc = {}

    def tearDown(self):
        os.chdir(self.cwd)
        os.unlink(self.projectconf)
        os.unlink(self.staff)
        os.unlink(self.modules)
        os.rmdir(self.annexdir)
        for spec in self.pkgspecs.values():
            os.unlink(spec)
        for src in self.pkgsrc.values():
            os.unlink(src)
        for pkgdir in self.pkgdirs.values():
            os.unlink(os.path.join(pkgdir, 'info.yaml'))
            os.rmdir(os.path.join(pkgdir, 'sources'))
            os.rmdir(pkgdir)
        os.rmdir(self.packagesdir)
        os.rmdir(self.projdir)

    def make_pkg(self, name='pkg', version='1.0', release='1'):
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
            spec.write("Version:        {0}\n".format(version))
            spec.write("Release:        {0}\n".format(release))
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
            spec.write("%changelog\n")
            spec.write("* Tue Feb 26 2019 Myself <buddy@somewhere.org>"
                       " - {0}-{1}\n".format(version, release))
            spec.write("- Update to {0} release\n".format(version))

        # ./packages/pkg/sources
        srcdir = os.path.join(self.pkgdirs[name], 'sources')
        os.mkdir(srcdir)

        # ./packages/pkg/sources/pkg-version-release.tar.gz
        self.pkgsrc[name] = os.path.join(srcdir,
                                         "{0}-{1}.tar.gz".format(name, version))
        with open(self.pkgsrc[name], "w") as src:
            src.write("ACACACACACACACAC")


    def test_action_query(self):
        """simple 'rift query' is ok """
        self.assertEqual(main(['query']), 0)


    def test_action_query_on_pkg(self):
        """ Test query on one package """
        self.make_pkg()
        self.assertEqual(main(['query', 'pkg']), 0)

    def test_validdiff_readme(self):
        """ Should allow README files """
        self.make_pkg()
        patch_template = """
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: document 'pkg'

diff --git a/packages/pkg/{0} b/packages/pkg/{0}
new file mode 100644
index 0000000..e845566
--- /dev/null
+++ b/packages/pkg/{0}
@@ -0,0 +1 @@
+README
"""

        for fmt in '', 'rst', 'md', 'txt':
            filename = 'README'
            if fmt:
                filename = "{0}.{1}".format(filename, fmt)
            patch = make_temp_file(patch_template.format(filename))
            self.assertEqual(main(['validdiff', patch.name]), 0)

