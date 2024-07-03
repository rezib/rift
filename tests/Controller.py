#
# Copyright (C) 2018 CEA
#

import os.path
import shutil
import atexit
from unittest.mock import patch

from unidiff import parse_unidiff
from TestUtils import (
    make_temp_file, make_temp_dir, RiftTestCase, RiftProjectTestCase
)

from VM import GLOBAL_CACHE, VALID_IMAGE_URL, PROXY
from rift.Controller import (
    main, _validate_patch, get_packages_from_patch, make_parser
)
from rift import RiftError

VALID_REPOS = {
    'os': {
        'url': 'https://repo.almalinux.org/almalinux/8/BaseOS/$arch/os/',
    },
    'appstream': {
        'url': 'https://repo.almalinux.org/almalinux/8/AppStream/$arch/os/',
    },
    'powertools': {
        'url': 'https://repo.almalinux.org/almalinux/8/PowerTools/$arch/os/',
    },
}


class ControllerTest(RiftTestCase):

    def test_main_version(self):
        """simple 'rift --version'"""
        self.assert_except(SystemExit, "0", main, ['--version'])


class ControllerProjectTest(RiftProjectTestCase):
    """
    Tests class for Controller
    """

    def _check_qemuuserstatic(self):
        """Skip the test if none qemu-$arch-static executable is found for all
        architectures declared in project configuration."""
        if not any(
            [
                os.path.exists(f"/usr/bin/qemu-{arch}-static")
                for arch in self.config.get('arch')
            ]
        ):
            self.skipTest("qemu-user-static is not available")

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

    @patch('rift.Controller.VM')
    def test_action_build_test(self, mock_vm_class):

        # Declare supported archs and check qemu-user-static is available for
        # these architectures or skip the test.
        self.config.set('arch', ['x86_64', 'aarch64'])
        self._check_qemuuserstatic()

        # Create temporary working repo and register its deletion at exit
        working_repo = make_temp_dir()
        atexit.register(shutil.rmtree, working_repo)

        self.config.set('working_repo', working_repo)
        self.config.options['repos'] = VALID_REPOS
        self.update_project_conf()

        # Create fake package without build requirement
        self.make_pkg(build_requires=[])

        main(['build', 'pkg', '--publish'])
        for arch in self.config.get('arch'):
            self.assertTrue(
                os.path.exists(f"{working_repo}/{arch}/pkg-1.0-1.noarch.rpm")
            )

        # Fake stopped VM and successful tests
        mock_vm_objects = mock_vm_class.return_value
        mock_vm_objects.running.return_value = False
        mock_vm_objects.run_test.return_value = 0

        # Run test on package
        main(['test', 'pkg'])

        # Check two VM objects have been initialized for the two architectures.
        self.assertEqual(mock_vm_class.call_count, 2)
        # Check vm.run_test() has been called twice for basic tests on the two
        # architectures.
        self.assertEqual(mock_vm_objects.run_test.call_count, 2)

        # Remove temporary working repo and unregister its deletion at exit
        shutil.rmtree(working_repo)
        atexit.unregister(shutil.rmtree)

        # Remove mock build environments
        self.clean_mock_environments()

    @patch('rift.Controller.VM')
    def test_action_validate(self, mock_vm_class):
        # Declare supported archs and check qemu-user-static is available for
        # these architectures or skip the test.
        self.config.set('arch', ['x86_64', 'aarch64'])
        self._check_qemuuserstatic()
        self.config.options['repos'] = VALID_REPOS
        self.update_project_conf()

        # Create fake package without build requirement
        self.make_pkg(build_requires=[])

        # Fake stopped VM and successful tests
        mock_vm_objects = mock_vm_class.return_value
        mock_vm_objects.running.return_value = False
        mock_vm_objects.run_test.return_value = 0

        # Run validate on pkg
        main(['validate', 'pkg'])

        # Check two VM objects have been initialized for the two architectures.
        self.assertEqual(mock_vm_class.call_count, 2)
        # Check vm.run_test() has been called twice for basic tests on the two
        # architectures.
        self.assertEqual(mock_vm_objects.run_test.call_count, 2)

        # Remove mock build environments
        self.clean_mock_environments()

    @patch('rift.Controller.VM')
    def test_vm_arch_option(self, mock_vm_class):
        """Test vm --arch option required with multiple supported archs."""
        # With only one supported architecture in project, --arch argument must
        # not be required.
        main(['vm', 'connect'])

        # Define multiple supported architectures.
        self.config.set('arch', ['x86_64', 'aarch64'])
        self.update_project_conf()

        # With multiple supported architectures, --arch argument must be
        # required.
        with self.assertRaisesRegex(
            RiftError,
            "^VM architecture must be defined with --arch argument.*$"
        ):
            main(['vm', 'connect'])

        # It should run without error with --arch.
        main(['vm', '--arch', 'x86_64', 'connect'])

        # Test invalid value of --arch argument is reported.
        with self.assertRaisesRegex(
            RiftError,
            "^Project does not support architecture 'fail'$"
        ):
            main(['vm', '--arch', 'fail', 'connect'])

        # Remove mock build environment
        self.clean_mock_environments()

    @patch('rift.Controller.VM')
    def test_action_vm_build(self, mock_vm_class):
        """simple 'rift vm build' is ok """

        mock_vm_objects = mock_vm_class.return_value

        main(['vm', 'build', 'http://image', '--deploy'])
        # check VM class has been instanciated
        mock_vm_class.assert_called()

        mock_vm_objects.build.assert_called_once_with(
            'http://image', False, False, self.config.get('vm_image')
        )
        mock_vm_objects.build.reset_mock()
        main(['vm', 'build', 'http://image', '--deploy', '--force'])
        mock_vm_objects.build.assert_called_once_with(
            'http://image', True, False, self.config.get('vm_image')
        )
        mock_vm_objects.build.reset_mock()
        main(['vm', 'build', 'http://image', '--deploy', '--keep'])
        mock_vm_objects.build.assert_called_once_with(
            'http://image', False, True, self.config.get('vm_image')
        )
        mock_vm_objects.build.reset_mock()
        main(
            ['vm', 'build', 'http://image', '--output', 'OUTPUT.img', '--force']
        )
        mock_vm_objects.build.assert_called_once_with(
            'http://image', True, False, 'OUTPUT.img'
        )
        mock_vm_objects.build.reset_mock()
        with self.assertRaisesRegex(
            RiftError, "^Either --deploy or -o,--output option must be used$"
        ):
            main(['vm', 'build', 'http://image'])
        with self.assertRaisesRegex(
            RiftError,
            "^Both --deploy and -o,--output options cannot be used together$",
        ):
            main(
                [
                    'vm',
                    'build',
                    'http://image',
                    '--deploy',
                    '--output',
                    'OUTPUT.img',
                ]
            )

    def test_vm_build_and_validate(self):
        """Test VM build and validate package"""
        if not os.path.exists("/usr/bin/qemu-img"):
            self.skipTest("qemu-img is not available")
        self.config.options['vm_images_cache'] = GLOBAL_CACHE
        # Reduce memory size from default 8GB to 2GB because it is sufficient to
        # run this VM and it largely reduces storage required by virtiofs memory
        # backend file which is the same size as the VM memory, thus reducing
        # the risk to fill up small partitions when running the tests.
        self.config.options['vm_memory'] = 2048
        self.config.options['proxy'] = PROXY
        self.config.options['repos'] = {
            'os': {
                'url': (
                    'https://repo.almalinux.org/almalinux/8/BaseOS/x86_64/os/'
                ),
                'priority': 90
            },
            'updates': {
                'url': (
                    'https://repo.almalinux.org/almalinux/8/AppStream/x86_64/'
                    'os/'
                ),
                'priority': 90
            },
            'extras':  {
                'url': (
                    'https://repo.almalinux.org/almalinux/8/PowerTools/x86_64/'
                    'os/'
                ),
                'priority': 90
            }
        }
        # Enable virtiofs that is natively supported by Alma without requirement
        # of additional RPM.
        self.config.options['shared_fs_type'] = 'virtiofs'
        # Update project YAML configuration with new options defined above
        self.update_project_conf()
        # Copy example cloud-init template
        self.copy_cloud_init_tpl()
        # Copy example build post script
        self.copy_build_post_script()
        # Ensure cache directory exists
        self.ensure_vm_images_cache_dir()
        # Build virtual machine image
        main(['vm', 'build', VALID_IMAGE_URL['x86_64'], '--deploy'])
        # Create source package and launch validation on fresh VM image
        pkg = 'pkg'
        self.make_pkg(name=pkg, build_requires=[], requires=[])
        main(['validate', pkg])
        # Remove mock build environments
        self.clean_mock_environments()


class ControllerArgumentsTest(RiftTestCase):
    """ Arguments parsing tests for Controller module"""

    def test_make_parser_updaterepo(self):
        """ Test option parsing """
        args = ["build", "a_package", "--dont-update-repo"]
        parser = make_parser()
        opts = parser.parse_args(args)
        self.assertFalse(opts.updaterepo)

    def test_make_parser_vm(self):
        """ Test vm command options parsing """
        parser = make_parser()

        args = ['vm', '--arch', 'x86_64']
        opts = parser.parse_args(args)
        self.assertEquals(opts.command, 'vm')

        args = ['vm', 'connect']
        opts = parser.parse_args(args)
        self.assertEquals(opts.vm_cmd, 'connect')

        args = ['vm', '--arch', 'x86_64', 'connect']
        opts = parser.parse_args(args)
        self.assertEquals(opts.vm_cmd, 'connect')

        args = ['vm', 'build']
        # This must fail due to missing image URL
        with self.assertRaises(SystemExit):
            parser.parse_args(args)

        args = ['vm', 'build', 'http://image']
        opts = parser.parse_args(args)
        self.assertEquals(opts.vm_cmd, 'build')
        self.assertEquals(opts.url, 'http://image')
        self.assertFalse(opts.force)

        args = ['vm', 'build', 'http://image', '--force']
        opts = parser.parse_args(args)
        self.assertTrue(opts.force)

        args = ['vm', 'build', 'http://image', '--deploy']
        opts = parser.parse_args(args)
        self.assertTrue(opts.deploy)

        OUTPUT_IMG = 'OUTPUT'

        args = ['vm', 'build', 'http://image', '-o', OUTPUT_IMG]
        opts = parser.parse_args(args)
        self.assertEquals(opts.output, OUTPUT_IMG)

        args = ['vm', 'build', 'http://image', '--output', OUTPUT_IMG]
        opts = parser.parse_args(args)
        self.assertEquals(opts.output, OUTPUT_IMG)

        # This must fail due to missing output filename
        args = ['vm', 'build', 'http://image', '--output']
        with self.assertRaises(SystemExit):
            parser.parse_args(args)
