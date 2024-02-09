#
# Copyright (C) 2024 CEA
#

import platform
from TestUtils import RiftTestCase
from rift.Config import Config, _DEFAULT_VM_ADDRESS, _DEFAULT_QEMU_CMD, \
                        _DEFAULT_VM_MEMORY, _DEFAULT_VIRTIOFSD
from rift.Repository import RemoteRepository
from rift.VM import VM, ARCH_EFI_BIOS, gen_virtiofs_args

class VMTest(RiftTestCase):
    """
    Tests class for VMs
    """
    def setUp(self):
        self.config = Config()
        self.config.project_dir = '/'

    def test_init(self):
        """ Test VM initialisation """
        # default
        vm = VM(self.config)
        self.assertEqual(vm.arch, 'x86_64')
        self.assertEqual(vm.cpu_type, 'host')
        self.assertEqual(vm.cpus, 4)
        self.assertEqual(vm.memory, _DEFAULT_VM_MEMORY)
        self.assertEqual(vm.arch_efi_bios, ARCH_EFI_BIOS)
        self.assertEqual(vm.address, _DEFAULT_VM_ADDRESS)
        self.assertEqual(vm._image, None)
        self.assertEqual(vm.qemu, _DEFAULT_QEMU_CMD)
        self.assertEqual(vm._repos, [])
        self.assertTrue(vm.tmpmode)
        self.assertFalse(vm.copymode)
        self.assertIsNone(vm._vm)
        self.assertIsNone(vm._tmpimg)

        # arch specific
        self.config.set('arch', 'aarch64')
        vm = VM(self.config)
        self.assertEqual(vm.arch, 'aarch64')
        self.assertEqual(vm.cpu_type, 'cortex-a72')

        vm_custom_memory = 4096

        # custom
        self.config.set('arch', 'aarch64')
        self.config.set('vm_cpu', 'custom')
        self.config.set('vm_cpus', 32)
        self.config.set('vm_memory', vm_custom_memory)
        self.config.set('arch_efi_bios', '/my_bios')
        self.config.set('vm_port', 12345)
        self.config.set('vm_image_copy', 1)
        self.config.set('vm_address', '192.168.0.5')
        self.config.set('vm_image', '/my_image')
        self.config.set('qemu', '/my_custom_qemu')

        vm = VM(self.config)
        self.assertEqual(vm.arch, 'aarch64')
        self.assertEqual(vm.cpu_type, 'custom')
        self.assertEqual(vm.cpus, 32)
        self.assertEqual(vm.memory, vm_custom_memory)
        self.assertEqual(vm.arch_efi_bios, '/my_bios')
        self.assertEqual(vm.port, 12345)
        self.assertEqual(vm.address, '192.168.0.5')
        self.assertEqual(vm._image, '/my_image')
        self.assertEqual(vm.qemu, '/my_custom_qemu')
        self.assertTrue(vm.copymode)
        self.assertIsNone(vm._vm)
        self.assertIsNone(vm._tmpimg)

    def test_gen_virtiofs_args(self):
        """
        Check virtiofsd args generator
        """
        # test default values non qemu mode
        args = gen_virtiofs_args('/socket', '/source', False)
        self.assertEqual(args, [_DEFAULT_VIRTIOFSD, '--socket-path', '/socket',
                                '--sandbox=none', '--shared-dir', '/source',
                                '--cache', 'auto'])
        # test default values qemu mode
        args = gen_virtiofs_args('/socket', '/source', True)
        self.assertEqual(args, ['sudo', _DEFAULT_VIRTIOFSD,
                                '--socket-path=/socket',
                                '-o', 'source=/source',
                                '-o', 'cache=auto', '--syslog', '--daemonize'])
        # test custom values
        args = gen_virtiofs_args('/socket', '/source', False, '/virtiofsd')
        self.assertEqual(args, ['/virtiofsd', '--socket-path', '/socket',
                               '--sandbox=none', '--shared-dir', '/source',
                               '--cache', 'auto'])

    def test_make_drive_cmd_nine_p(self):
        """
        Check drive command line generation for 9p
        """
        vm = VM(self.config, None)

        # Test 9p configuration without any repos
        vm.shared_fs_type = '9p'
        vm._project_dir = '/somewhere'
        args, helper_args = vm._make_drive_cmd()
        nine_p_args = ['-virtfs',
                       f"local,id=project,path={vm._project_dir},mount_tag=project,"
                       'security_model=none']
        self.assertEqual(args, nine_p_args)
        self.assertEqual(helper_args, [])

        # Test 9p configuration with repos
        # Use RemoteRepostory to avoid any createrepo stuff in tests
        reponame = 'custom'
        vm._repos = [RemoteRepository(url='/tmp', name=reponame)]

        repo_args = ['-virtfs',
                     f'local,id={reponame},path=/tmp,mount_tag={reponame},security_model=none']

        args, helper_args = vm._make_drive_cmd()
        self.assertEqual(args, nine_p_args + repo_args)
        self.assertEqual(helper_args, [])

    def test_make_drive_cmd_vitiofs(self):
        """
        Check drive command line generation for virtiofs
        """
        vm = VM(self.config, None)
        # Test virtiofs configuration without any repos
        vm.shared_fs_type = 'virtiofs'
        vm._project_dir = '/somewhere/else'
        vm.arch = platform.processor()
        args, helper_args = vm._make_drive_cmd()
        virtiofs_same_arch = ['-object',
                              f'memory-backend-file,id=mem,size={str(vm.memory)}M,'
                              'mem-path=/tmp,share=on',
                              '-machine', 'memory-backend=mem,accel=kvm',
                              '-chardev',
                              'socket,id=project,path=/tmp/.virtio_fs_project',
                              '-device',
                              'vhost-user-fs-pci,queue-size=1024,chardev=project,'
                              'tag=project']
        self.assertEqual(args, virtiofs_same_arch)
        self.assertNotEqual(helper_args, [])
        vm.arch = 'not_the_same_arch'
        args, helper_args = vm._make_drive_cmd()
        virtiofs_diff_arch = ['-object',
                              f'memory-backend-file,id=mem,size={str(vm.memory)}M,'
                              'mem-path=/tmp,share=on',
                              '-machine', 'memory-backend=mem',
                              '-chardev',
                              'socket,id=project,path=/tmp/.virtio_fs_project',
                              '-device',
                              'vhost-user-fs-pci,queue-size=1024,chardev=project,'
                              'tag=project']
        self.assertEqual(args, virtiofs_diff_arch)
        # Content of helper_args is not tested here see test_gen_virtiofs_args
        self.assertNotEqual(helper_args, [])

        # Test virtiofs configuration with repos
        # Use RemoteRepostory to avoid any createrepo stuff in tests
        reponame = 'custom'
        vm._repos = [RemoteRepository(url='/tmp', name=reponame)]

        repo_args = ['-chardev',
                     f'socket,id={reponame},path=/tmp/.virtio_fs_{reponame}',
                     '-device',
                     f'vhost-user-fs-pci,queue-size=1024,chardev={reponame},'
                     f'tag={reponame}']
        args, helper_args = vm._make_drive_cmd()
        self.assertEqual(args, virtiofs_diff_arch + repo_args)
        # Content of helper_args is not tested here see test_gen_virtiofs_args
        self.assertNotEqual(helper_args, [])


    def test_gen_qemu_args(self):
        """
        Check qemu args generator
        """
        vm = VM(self.config, None)
        vm.arch = platform.processor()
        vm.consolesock = '/console'
        image_path = '/my_image'
        args = vm._gen_qemu_args(image_path)
        expected_args = [ vm.qemu, '-enable-kvm', '-cpu', vm.cpu_type,
                          '-name', 'rift', '-display', 'none',
                          '-m', str(vm.memory), '-smp', str(vm.cpus),
                          '-drive',
                          f"file={image_path},if=virtio,format=qcow2,cache=unsafe",
                          '-chardev', f"socket,id=charserial0,path={vm.consolesock},"
                          'server=on,wait=off',
                          '-device', 'isa-serial,chardev=charserial0,id=serial0',
                          '-netdev', f"user,id=hostnet0,hostname={vm.NAME},"
                          f"hostfwd=tcp::{vm.port}-:22",
                          '-device',
                          'virtio-net-pci,netdev=hostnet0,bus=pci.0,addr=0x3']
        self.assertEqual(args, expected_args)
        vm.arch = 'aarch64'
        args = vm._gen_qemu_args(image_path)
        expected_args_aarch64 = [ vm.qemu, '-machine', 'virt', '-cpu', vm.cpu_type,
                          '-name', 'rift', '-display', 'none',
                          '-m', str(vm.memory), '-smp', str(vm.cpus),
                          '-bios', vm.arch_efi_bios,
                          '-drive',
                          f"file={image_path},if=virtio,format=qcow2,cache=unsafe",
                          '-chardev', f"socket,id=charserial0,path={vm.consolesock},"
                          'server=on,wait=off',
                          '-device', 'virtio-serial,id=ser0,max_ports=8',
                          '-serial', 'chardev:charserial0',
                          '-netdev', f"user,id=hostnet0,hostname={vm.NAME},"
                          f"hostfwd=tcp::{vm.port}-:22",
                          '-device',
                          'virtio-net-device,netdev=hostnet0']
        self.assertEqual(args, expected_args_aarch64)
