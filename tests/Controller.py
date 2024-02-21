#
# Copyright (C) 2018 CEA
#

import os.path

from unidiff import parse_unidiff
from TestUtils import (
    make_temp_file, make_temp_dir, RiftTestCase, RiftProjectTestCase
)

from rift.Controller import (
    main, _validate_patch, get_packages_from_patch, parse_options
)
from rift import RiftError

class ControllerTest(RiftTestCase):

    def test_main_version(self):
        """simple 'rift --version'"""
        self.assert_except(SystemExit, "0", main, ['--version'])


class ControllerProjectTest(RiftProjectTestCase):
    """
    Tests class for Controller
    """

    def make_pkg(
        self,
        name='pkg',
        version='1.0',
        release='1',
        metadata={
            'module': 'Great module',
            'origin': 'Vendor',
            'reason': 'Missing feature'
        },
        build_requires=['br-package'],
        requires=['another-package']
    ):
        # ./packages/pkg
        self.pkgdirs[name] = os.path.join(self.packagesdir, name)
        os.mkdir(self.pkgdirs[name])
        # ./packages/pkg/info.yaml
        info = os.path.join(self.pkgdirs[name], 'info.yaml')
        with open(info, "w") as nfo:
            nfo.write("package:\n")
            nfo.write("    maintainers:\n")
            nfo.write("        - Myself\n")
            nfo.write("    module: {}\n".format(metadata.get('module', '')))
            nfo.write("    origin: {}\n".format(metadata.get('origin', '')))
            nfo.write("    reason: {}\n".format(metadata.get('reason', '')))

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
            for build_require in build_requires:
                spec.write(f"BuildRequires:  {build_require}\n")
            for require in requires:
                spec.write(f"Requires:       {require}\n")
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

        # ./packages/pkg/sources/pkg-version.tar.gz
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

    def test_action_query_on_bad_pkg(self):
        """ Test query on multiple packages with one errorneous package """
        self.make_pkg()
        ## A package with no name should be wrong but the command should not fail
        self.make_pkg(name='pkg2', metadata={})
        self.assertEqual(main(['query']), 0)

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

    def test_validdiff_binary(self):
        """ Should fail if source file is a binary file """
        pkgname = 'pkg'
        pkgvers = 1.0
        self.make_pkg(name=pkgname, version=pkgvers)
        pkgsrc = os.path.join('packages', 'pkgname', 'sources',
                              '{0}-{1}.tar.gz'.format(pkgname, pkgvers))
        patch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: update 'pkg' sources

diff --git /dev/null b/{0}
index fcd49dd..91ef207 100644
Binary files a/sources/a.tar.gz and b/sources/a.tar.gz differ
""".format(pkgsrc))
        self.assert_except(RiftError, "Binary file detected: {0}".format(pkgsrc),
                           main, ['validdiff', patch.name])

    def test_validdiff_binary_with_content(self):
        """ Should fail if source file is a binary file (diff --binary) """
        pkgname = 'pkg'
        pkgvers = 1.0
        self.make_pkg(name=pkgname, version=pkgvers)
        pkgsrc = os.path.join('packages', 'pkgname', 'sources',
                              '{0}-{1}.tar.gz'.format(pkgname, pkgvers))
        patch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: update 'pkg' sources

diff --git /dev/null b/{0}
index 6cd0ff6ec591f7f51a3479d7b66c6951a2b4afa9..91ef2076b67f3158ec1670fa7b88d88b2816aa91 100644
GIT binary patch
literal 8
PcmZQ%;Sf+z_{{#tQ1BL-x

literal 4
LcmZQ%;Sc}}-05kv|
""".format(pkgsrc))
        self.assert_except(RiftError, "Binary file detected: {0}".format(pkgsrc),
                           main, ['validdiff', patch.name])

    def test_remove_package(self):
        """ Test if removing a package doesn't trigger a build """
        pkgname = 'pkg'
        pkgvers = 1.0
        self.make_pkg(name=pkgname, version=pkgvers)
        pkgsrc = os.path.join('packages', 'pkgname', 'sources',
                              '{0}-{1}.tar.gz'.format(pkgname, pkgvers))
        patch = make_temp_file("""
diff --git a/packages/pkg/info.yaml b/packages/pkg/info.yaml
deleted file mode 100644
index 32ac08e..0000000
--- a/packages/pkg/info.yaml
+++ /dev/null
@@ -1,6 +0,0 @@
-package:
-    maintainers:
-        - Myself
-    module: Great module
-    origin: Vendor
-    reason: Missing feature
diff --git a/packages/pkg/pkg.spec b/packages/pkg/pkg.spec
deleted file mode 100644
index b92c49d..0000000
--- a/packages/pkg/pkg.spec
+++ /dev/null
@@ -1,24 +0,0 @@
-Name:    pkg
-Version:        1.0
-Release:        1
-Summary:        A package
-Group:          System Environment/Base
-License:        GPL
-URL:            http://nowhere.com/projects/%{{name}}/
-Source0:        %{{name}}-%{{version}}.tar.gz
-BuildArch:      noarch
-BuildRequires:  br-package
-Requires:       another-package
-Provides:       pkg-provide
-%description
-A package
-%prep
-%build
-# Nothing to build
-%install
-# Nothing to install
-%files
-# No files
-%changelog
-* Tue Feb 26 2019 Myself <buddy@somewhere.org> - 1.0-1
-- Update to 1.0 release
diff --git a/{0} b/{0}
deleted file mode 100644
index 43bf48d..0000000
--- a/{0}
+++ /dev/null
@@ -1 +0,0 @@
-ACACACACACACACAC
\ No newline at end of file
""".format(pkgsrc))

        self.assertEqual(main(['validdiff', patch.name]), 0)

    def test_validdiff_on_tests_directory(self):
        """ Test if package tests directory structure is fine """
        patch = make_temp_file("""
diff --git a/packages/pkg/tests/sources/deep/source.c b/packages/pkg/tests/sources/deep/source.c
new file mode 100644
index 0000000..68344bf
--- /dev/null
+++ b/packages/pkg/tests/sources/deep/source.c
@@ -0,0 +1,4 @@
+#include <stdlib.h>
+int main(int argc, char **argv){
+    exit(0);
+}
\ No newline at end of file
""")
        # Ensure package exists
        self.make_pkg('pkg')
        with open(patch.name, 'r') as f:
            patchedfiles = parse_unidiff(f)
        self.assertNotEqual(len(patchedfiles), 0)
        for patchedfile in patchedfiles:
            pkg = _validate_patch(patchedfile, self.config,
                                  modules=self.modules,
                                  staff=self.staff)
            self.assertIsNotNone(pkg)

    def test_validdiff_on_invalid_file(self):
        patch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: Wrong file

diff --git a/packages/pkg/wrong b/packages/pkg/wrong
new file mode 100644
index 0000000..68344bf
--- a/packages/pkg/wrong
+++ b/packages/pkg/wrong
@@ -0,0 +1 @@
+README
""")
        self.assert_except(RiftError, "Unknown file pattern in 'pkg' directory: packages/pkg/wrong",
                           main, ['validdiff', patch.name])

    def test_validdiff_on_info(self):
        patch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: update 'pkg' infos

diff --git a/packages/pkg/info.yaml b/packages/pkg/info.yaml
new file mode 100644
index 0000000..68344bf
--- a/packages/pkg/info.yaml
+++ b/packages/pkg/info.yaml
@@ -2,5 +2,5 @@ package:
   maintainers:
   - Myself
   module: Great module
-  origin: Somewhere
+  origin: Elsewhere
   reason: Missing feature
""")
        self.make_pkg()
        self.assertEqual(main(['validdiff', patch.name]), 0)

    def test_validdiff_on_modules(self):
        patch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    modules: add 'Section'

diff --git a/packages/modules.yaml b/packages/modules.yaml
new file mode 100644
index 0000000..68344bf
--- a/packages/modules.yaml
+++ b/packages/modules.yaml
@@ -0,0 +3 @@
+modules:
+  User Tools:
+    manager: John Doe
""")
        self.assertEqual(main(['validdiff', patch.name]), 0)


    def test_rename_package(self):
        """ Test if renaming a package trigger a build """
        pkgname = 'pkg'
        pkgvers = 1.0
        self.make_pkg(name=pkgname, version=pkgvers)
        patch = make_temp_file("""
diff --git a/packages/pkg/pkg.spec b/packages/pkgnew/pkgnew.spec
similarity index 100%
rename from packages/pkg/pkg.spec
rename to packages/pkgnew/pkgnew.spec
diff --git a/packages/pkg/info.yaml b/packages/pkgnew/info.yaml
similarity index 100%
rename from packages/pkg/info.yaml
rename to packages/pkgnew/info.yaml
diff --git a/packages/pkg/sources/pkg-1.0.tar.gz b/packages/pkgnew/sources/pkgnew-1.0.tar.gz
similarity index 100%
rename from packages/pkg/sources/pkg-1.0.tar.gz
rename to packages/pkgnew/sources/pkgnew-1.0.tar.gz
""")

        with open(patch.name, 'r') as p:
            pkgs = get_packages_from_patch(p, config=self.config,
                                           modules=self.modules, staff=self.staff)
        print("pkg: %s" % pkgs.keys())
        self.assertEqual(len(pkgs), 1)
        self.assertTrue('pkgnew' in pkgs.keys())

    def test_rename_and_update_package(self):
        """ Test if renaming and updating a package trigger a build """
        pkgname = 'pkg'
        pkgvers = 1.0
        self.make_pkg(name=pkgname, version=pkgvers)
        patch = make_temp_file("""
commit f8c1a88ea96adfccddab0bf43c0a90f05ab26dc5 (HEAD -> playground)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: rename 'pkg' to 'pkgnew'

diff --git a/packages/pkg/info.yaml b/packages/pkgnew/info.yaml
similarity index 100%
rename from packages/pkg/info.yaml
rename to packages/pkgnew/info.yaml
diff --git a/packages/pkg/pkg.spec b/packages/pkgnew/pkgnew.spec
similarity index 93%
rename from packages/pkg/pkg.spec
rename to packages/pkgnew/pkgnew.spec
index b92c49d..0fa690c 100644
--- a/packages/pkg/pkg.spec
+++ b/packages/pkgnew/pkgnew.spec
@@ -1,6 +1,6 @@
-Name:    pkg
+Name:    pkgnew
 Version:        1.0
-Release:        1
+Release:        2
 Summary:        A package
 Group:          System Environment/Base
 License:        GPL
diff --git a/packages/pkg/sources/pkg-1.0.tar.gz b/packages/pkgnew/sources/pkgnew-1.0.tar.gz
similarity index 100%
rename from packages/pkg/sources/pkg-1.0.tar.gz
rename to packages/pkgnew/sources/pkgnew-1.0.tar.gz
""")

        with open(patch.name, 'r') as p:
            pkgs = get_packages_from_patch(p, config=self.config,
                                           modules=self.modules, staff=self.staff)
        print("pkg: %s" % pkgs.keys())
        self.assertEqual(len(pkgs), 1)
        self.assertTrue('pkgnew' in pkgs.keys())


class ControllerSimpleTest(RiftTestCase):
    """ Simple test for Class Controler """

    def test_parse_options_updaterepo(self):
        """ Test option parsing """
        args = ["build", "a_package", "--dont-update-repo"]
        parser = parse_options(args)
        self.assertFalse(parser.updaterepo)
