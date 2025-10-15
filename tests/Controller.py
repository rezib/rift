#
# Copyright (C) 2018 CEA
#

import os.path
import shutil
import atexit
from unittest.mock import patch, Mock
import subprocess
from io import StringIO

from TestUtils import (
    make_temp_dir, RiftTestCase, RiftProjectTestCase
)

from VM import GLOBAL_CACHE, VALID_IMAGE_URL, PROXY
from rift.Controller import (
    main,
    remove_packages,
    make_parser,
)
from rift.Package import Package
from rift.RPM import RPM
from rift.run import RunResult
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


class ControllerProjectActionQueryTest(RiftProjectTestCase):
    """
    Tests class for Controller action query
    """
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


class ControllerProjectActionValiddiffTest(RiftProjectTestCase):
    """
    Tests class for Controller action validdiff
    """
    @patch('rift.Controller.remove_packages')
    @patch('rift.Controller.validate_pkgs')
    @patch('rift.Controller.get_packages_from_patch')
    def test_action_validdiff(self, mock_get_packages_from_patch,
                              mock_validate_pkgs, mock_remove_packages):
        """ Test validdiff action calls expected functions """
        mock_get_packages_from_patch.return_value = (
            {'pkg': Package('pkg', self.config, self.staff, self.modules)}, {}
        )
        self.assertEqual(main(['validdiff', '/dev/null']), 0)
        mock_get_packages_from_patch.assert_called_once()
        mock_validate_pkgs.assert_called_once()
        mock_remove_packages.assert_called_once()

    @patch('rift.Controller.ProjectArchRepositories')
    def test_remove_packages(self, mock_parepository_class):
        """remove_packages() search, delete and update repository."""
        mock_parepository_objects = mock_parepository_class.return_value

        # Preparer Repository.search() return value
        rpm = RPM(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'materials',
                'pkg-1.0-1.src.rpm',
            )
        )
        mock_parepository_objects.working.search.return_value = [ rpm ]

        # Enable publish arg
        args = Mock()
        args.publish = True

        # Define a list of packages to remove
        pkgs_to_remove = [
            Package('pkg', self.config, self.staff, self.modules)
        ]

        # Define working_repo in configuration
        self.config.options['working_repo'] = '/path/to/working/repo'

        # Call remove_packages()
        remove_packages(self.config, args, pkgs_to_remove, 'x86_64')

        # Check Repository object has been instanciated
        mock_parepository_class.assert_called()
        # Check Repository.search() has been called
        mock_parepository_objects.working.search.assert_called_once_with(
            pkgs_to_remove[0].name
        )
        # Check Repository.delete() has been called
        mock_parepository_objects.working.delete.assert_called_once_with(rpm)
        # Check Repository.update() has been called
        mock_parepository_objects.working.update.assert_called_once()

    @patch('rift.Controller.ProjectArchRepositories')
    def test_remove_packages_noop(self, mock_parepository_class):
        """remove_packages() is noop if no publish arg or no working_repo"""
        pkgs_to_remove = []
        args = Mock()

        # publish is False, remove_packages() must be noop
        args.publish = False
        self.config.options['working_repo'] = '/path/to/working/repo'
        remove_packages(self.config, args, pkgs_to_remove, 'x86_64')
        mock_parepository_class.assert_called_once()
        mock_parepository_class.working.assert_not_called()

        # working_repo is not defined, remove_packages() must be noop
        args.publish = True
        del self.config.options['working_repo']
        mock_parepository_class.reset_mock()
        remove_packages(self.config, args, pkgs_to_remove, 'x86_64')
        mock_parepository_class.assert_called_once()
        mock_parepository_class.working.assert_not_called()


class ControllerProjectActionBuildTest(RiftProjectTestCase):
    """
    Tests class for Controller actions build and validate
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
        mock_vm_objects.run_test.return_value = RunResult(0, None, None)

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
        mock_vm_objects.run_test.return_value = RunResult(0, None, None)

        # Run validate on pkg
        main(['validate', 'pkg'])

        # Check two VM objects have been initialized for the two architectures.
        self.assertEqual(mock_vm_class.call_count, 2)
        # Check vm.run_test() has been called twice for basic tests on the two
        # architectures.
        self.assertEqual(mock_vm_objects.run_test.call_count, 2)

        # Remove mock build environments
        self.clean_mock_environments()


class ControllerProjectActionVMTest(RiftProjectTestCase):
    """
    Tests class for Controller action vm
    """
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
            'http://image', False, False, self.config.get('vm').get('image')
        )
        mock_vm_objects.build.reset_mock()
        main(['vm', 'build', 'http://image', '--deploy', '--force'])
        mock_vm_objects.build.assert_called_once_with(
            'http://image', True, False, self.config.get('vm').get('image')
        )
        mock_vm_objects.build.reset_mock()
        main(['vm', 'build', 'http://image', '--deploy', '--keep'])
        mock_vm_objects.build.assert_called_once_with(
            'http://image', False, True, self.config.get('vm').get('image')
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
        self.skipTest("Too much instability")
        if not os.path.exists("/usr/bin/qemu-img"):
            self.skipTest("qemu-img is not available")
        self.config.options['vm']['images_cache'] = GLOBAL_CACHE
        # Reduce memory size from default 8GB to 2GB because it is sufficient to
        # run this VM and it largely reduces storage required by virtiofs memory
        # backend file which is the same size as the VM memory, thus reducing
        # the risk to fill up small partitions when running the tests.
        self.config.options['vm']['memory'] = 2048
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


class ControllerProjectActionSignTest(RiftProjectTestCase):
    """
    Tests class for Controller action sign
    """
    def test_action_sign(self):
        """ Test sign package """
        gpg_home = os.path.join(self.projdir, '.gnupg')

        # Launch GPG agent for this test
        cmd = [
          'gpg-agent',
          '--homedir',
          gpg_home,
          '--daemon',
        ]
        subprocess.run(cmd)

        # Generate keyring
        gpg_key = 'rift'
        cmd = [
            'gpg',
            '--homedir',
            gpg_home,
            '--batch',
            '--passphrase',
            '',
            '--quick-generate-key',
            gpg_key,
        ]
        subprocess.run(cmd)

        # Update project configuration with generated key
        self.config.options.update(
            {
                'gpg': {
                    'keyring': gpg_home,
                    'key': gpg_key,
                }
            }
        )
        self.update_project_conf()

        # Path of RPM packages assets
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        original_bin_rpm = os.path.join(
            tests_dir, 'materials', 'pkg-1.0-1.noarch.rpm'
        )
        original_src_rpm = os.path.join(
            tests_dir, 'materials', 'pkg-1.0-1.src.rpm'
        )

        # Copy RPM packages assets in temporary project directory
        copy_bin_rpm = os.path.join(self.projdir, os.path.basename(original_bin_rpm))
        shutil.copy(original_bin_rpm, copy_bin_rpm)
        copy_src_rpm = os.path.join(self.projdir, os.path.basename(original_src_rpm))
        shutil.copy(original_src_rpm, copy_src_rpm)

        # Load packages and check they are not signed
        bin_rpm = RPM(copy_bin_rpm, self.config)
        src_rpm = RPM(copy_src_rpm, self.config)
        self.assertFalse(bin_rpm.is_signed)
        self.assertFalse(src_rpm.is_signed)

        # Launch rift sign
        os.environ['GNUPGHOME'] = gpg_home
        self.assertEqual(main(['sign', copy_bin_rpm, copy_src_rpm]), 0)
        del os.environ['GNUPGHOME']

        # Reload packages and check they are signed now
        bin_rpm._load()
        src_rpm._load()
        self.assertTrue(bin_rpm.is_signed)
        self.assertTrue(src_rpm.is_signed)

        # Kill GPG agent launched for the test
        cmd = ['gpgconf', '--homedir', gpg_home, '--kill', 'gpg-agent']
        subprocess.run(cmd)

        # Remove copy of packages assets
        os.unlink(copy_bin_rpm)
        os.unlink(copy_src_rpm)

        # Remove temporary GPG home with generated key
        shutil.rmtree(gpg_home)

class ControllerProjectActionSyncTest(RiftProjectTestCase):
    """
    Tests class for Controller action sync
    """
    @patch('rift.sync.RepoSyncBase.run')
    @patch('sys.stdout', new_callable=StringIO)
    def test_action_sync_skip_repo_wo_params(self, mock_stdout, mock_reposyncbase_run):
        """ Test rift runs sync action skips repo without synchronization parameters. """
        sync_parent = make_temp_dir()
        sync_output = os.path.join(sync_parent, 'output')
        self.config.set('arch', ['x86_64'])

        self.config.options['sync_output'] = sync_output
        self.config.options['repos'] = {
            'repo1': {
                'sync': {
                    'source': 'https://server1/repo1',
                    'subdir': '$arch',
                },
                'url': 'https://server1/repo1',
            },
            'repo2': {
                'url': 'https://server2/repo2',
            },
        }
        # Update project YAML configuration with new options defined above
        self.update_project_conf()
        # Run sync and check debug log is emited to indicate repo2 is skipped.
        with self.assertLogs(level='DEBUG') as log:
            main(['sync'])
            self.assertIn(
                'WARNING:root:x86_64: Skipping repository repo2: no '
                'synchronization parameters found',
                log.output
            )
        # RepoSyncBase.run() must have been called once for repo1.
        self.assertEqual(mock_reposyncbase_run.call_count, 1)
        self.assertIn(
            '** x86_64: Synchronizing repository repo1: '
            'https://server1/repo1/x86_64 **',
            mock_stdout.getvalue()
        )
        # Clean synchronization output parent
        shutil.rmtree(sync_parent)

    @patch('rift.Controller.RepoSyncFactory')
    def test_action_sync(self, mock_reposync):
        """ Test rift runs sync action with or without sync conf. """
        # First run sync without sync conf nor -o, --output argument.
        # Check warning message log is emitted
        with self.assertLogs(level='INFO') as log:
            main(['sync'])
            self.assertIn(
                'ERROR:root:Synchronization output directory must be defined '
                'with sync_output parameter in Rift configuration or -o, '
                '--output command line option to synchronize repositories',
                log.output
            )
        # Check factory is not called
        self.assertEqual(mock_reposync.get.call_count, 0)

        # Create temporary synchronization output parent directory
        sync_parent = make_temp_dir()
        sync_output = os.path.join(sync_parent, 'output')

        # Add repositories with synchronization parameters in conf.
        self.config.options['repos'] = {
            'repo1': {
                'sync': {
                    'source': 'https://server1/repo1',
                },
                'url': 'https://server1/repo1',
            },
            'repo2': {
                'sync': {
                    'source': 'https://server2/repo2',
                },
                'url': 'https://server2/repo2',
            },
        }
        # Update project YAML configuration with new options defined above
        self.update_project_conf()

        # Run with --output parameter (without sync_output in conf)
        main(['sync', '--output', sync_output])

        # Check factory has been called twice, for repo1 and repo2
        self.assertEqual(mock_reposync.get.call_count, 2)
        # Check output directory has been created
        self.assertTrue(os.path.isdir(sync_output))
        # Clean synchronization output directory
        shutil.rmtree(sync_output)

        # Reset mock to check the second run.
        mock_reposync.get.reset_mock()

        # Add sync_output parameter in conf.
        self.config.options['sync_output'] = sync_output
        self.update_project_conf()

        # Run sync without -o, --output parameter.
        main(['sync'])
        # Check factory has been called twice, for repo1 and repo2
        self.assertEqual(mock_reposync.get.call_count, 2)
        # Check output directory has been created
        self.assertTrue(os.path.isdir(sync_output))
        # Clean synchronization output parent
        shutil.rmtree(sync_parent)

    @patch('rift.sync.RepoSyncBase.run')
    @patch('sys.stdout', new_callable=StringIO)
    def test_action_sync_multiarch(self, mock_stdout, mock_reposyncbase_run):
        """ Test rift runs sync action with multiple architectures. """
        sync_parent = make_temp_dir()
        sync_output = os.path.join(sync_parent, 'output')
        self.config.set('arch', ['x86_64', 'aarch64'])

        self.config.options['sync_output'] = sync_output
        self.config.options['repos'] = {
            'repo1': {
                'sync': {
                    'source': 'https://server1/repo1',
                    'subdir': '$arch',
                },
                'url': 'https://server1/repo1',
            },
            'repo2': {
                'sync': {
                    'source': 'https://server2/$arch',
                },
                'url': 'https://server2/$arch',
            },
            'repo3': {
                'sync': {
                    'source': 'https://server3/repo3',
                },
                'url': 'https://server3/repo3',
            },
        }
        # Update project YAML configuration with new options defined above
        self.update_project_conf()
        # Run sync and check debug log is emited to indicate repo3 is skipped
        # with the 2nd architecture (as the URL is the same as for the 1st
        # arch).
        with self.assertLogs(level='DEBUG') as log:
            main(['sync'])
            self.assertIn(
                'DEBUG:root:Skipping already synchronized source '
                'https://server3/repo3/',
                log.output
            )
        # RepoSyncBase.run() must have been called 5 times:
        # - 2 calls for repo1
        # - 2 calls for repo2
        # - 1 call for repo3
        self.assertEqual(mock_reposyncbase_run.call_count, 5)
        self.assertIn(
            '** x86_64: Synchronizing repository repo1: '
            'https://server1/repo1/x86_64 **',
            mock_stdout.getvalue()
        )
        self.assertIn(
            '** aarch64: Synchronizing repository repo1: '
            'https://server1/repo1/aarch64 **',
            mock_stdout.getvalue()
        )
        self.assertIn(
            '** x86_64: Synchronizing repository repo2: '
            'https://server2/x86_64/ **',
            mock_stdout.getvalue()
        )
        self.assertIn(
            '** aarch64: Synchronizing repository repo2: '
            'https://server2/aarch64/ **',
            mock_stdout.getvalue()
        )
        self.assertIn(
            '** x86_64: Synchronizing repository repo3: '
            'https://server3/repo3/ **',
            mock_stdout.getvalue()
        )
        # Clean synchronization output parent
        shutil.rmtree(sync_parent)

    def test_action_sync_missing_output_parent(self):
        """ Test rift raises RiftError when sync output parent is not found. """
        sync_output = "/tmp/rift/output"
        self.config.options['sync_output'] = sync_output
        self.config.options['repos'] = {
            'repo1': {
                'sync': {
                    'source': 'https://server1/repo1',
                },
                'url': 'https://server1/repo1',
            },
            'repo2': {
                'sync': {
                    'source': 'https://server2/repo2',
                },
                'url': 'https://server2/repo2',
            },
        }
        # Update project YAML configuration with new options defined above
        self.update_project_conf()
        with self.assertRaisesRegex(
            RiftError,
            "Unable to create repositories synchronization directory "
            "/tmp/rift/output, parent directory /tmp/rift does not exist."
        ):
            main(['sync'])


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
        self.assertEqual(opts.command, 'vm')

        args = ['vm', 'connect']
        opts = parser.parse_args(args)
        self.assertEqual(opts.vm_cmd, 'connect')

        args = ['vm', '--arch', 'x86_64', 'connect']
        opts = parser.parse_args(args)
        self.assertEqual(opts.vm_cmd, 'connect')

        args = ['vm', 'build']
        # This must fail due to missing image URL
        with self.assertRaises(SystemExit):
            parser.parse_args(args)

        args = ['vm', 'build', 'http://image']
        opts = parser.parse_args(args)
        self.assertEqual(opts.vm_cmd, 'build')
        self.assertEqual(opts.url, 'http://image')
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
        self.assertEqual(opts.output, OUTPUT_IMG)

        args = ['vm', 'build', 'http://image', '--output', OUTPUT_IMG]
        opts = parser.parse_args(args)
        self.assertEqual(opts.output, OUTPUT_IMG)

        # This must fail due to missing output filename
        args = ['vm', 'build', 'http://image', '--output']
        with self.assertRaises(SystemExit):
            parser.parse_args(args)
