#
# Copyright (C) 2024 CEA
#

from rift.Config import Config, _DEFAULT_VM_ADDRESS, _DEFAULT_QEMU_CMD
from rift.VM import VM, ARCH_EFI_BIOS
from TestUtils import RiftTestCase

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
        vm = VM(self.config, None)
        self.assertEqual(vm.arch, 'x86_64')
        self.assertEqual(vm.cpu_type, 'host')
        self.assertEqual(vm.cpus, 4)
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
        vm = VM(self.config, None)
        self.assertEqual(vm.arch, 'aarch64')
        self.assertEqual(vm.cpu_type, 'cortex-a72')


        # custom
        self.config.set('arch', 'aarch64')
        self.config.set('vm_cpu', 'custom')
        self.config.set('vm_cpus', 32)
        self.config.set('arch_efi_bios', '/my_bios')
        self.config.set('vm_port', 12345)
        self.config.set('vm_image_copy', 1)
        self.config.set('vm_address', '192.168.0.5')
        self.config.set('vm_image', '/my_image')
        self.config.set('qemu', '/my_custom_qemu')

        vm = VM(self.config, None)
        self.assertEqual(vm.arch, 'aarch64')
        self.assertEqual(vm.cpu_type, 'custom')
        self.assertEqual(vm.cpus, 32)
        self.assertEqual(vm.arch_efi_bios, '/my_bios')
        self.assertEqual(vm.port, 12345)
        self.assertEqual(vm.address, '192.168.0.5')
        self.assertEqual(vm._image, '/my_image')
        self.assertEqual(vm.qemu, '/my_custom_qemu')
        self.assertTrue(vm.copymode)
        self.assertIsNone(vm._vm)
        self.assertIsNone(vm._tmpimg)
