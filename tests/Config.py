#
# Copyright (C) 2014-2018 CEA
#

import os.path
import os
import textwrap

from TestUtils import make_temp_file, make_temp_dir, RiftTestCase

from rift import DeclError
from rift.Config import Staff, Modules, Config, _DEFAULT_PKG_DIR, \
                         _DEFAULT_STAFF_FILE, _DEFAULT_MODULES_FILE, \
                         _DEFAULT_VM_CPUS, _DEFAULT_VM_ADDRESS, \
                         _DEFAULT_VM_PORT_RANGE_MIN, \
                         _DEFAULT_VM_PORT_RANGE_MAX, \
                         _DEFAULT_QEMU_CMD, _DEFAULT_REPO_CMD, \
                         _DEFAULT_SHARED_FS_TYPE, _DEFAULT_VIRTIOFSD

class ConfigTest(RiftTestCase):

    def test_get(self):
        """get() default values"""
        config = Config()

        # Default config value
        self.assertEqual(config.get('packages_dir'), _DEFAULT_PKG_DIR)
        self.assertEqual(config.get('staff_file'), _DEFAULT_STAFF_FILE)
        self.assertEqual(config.get('modules_file'), _DEFAULT_MODULES_FILE)
        self.assertEqual(config.get('vm_cpus'), _DEFAULT_VM_CPUS)
        self.assertEqual(config.get('vm_address'), _DEFAULT_VM_ADDRESS)
        self.assertEqual(config.get('shared_fs_type'), _DEFAULT_SHARED_FS_TYPE)
        self.assertEqual(config.get('virtiofsd'), _DEFAULT_VIRTIOFSD)
        self.assertEqual(
            config.get('vm_port_range'),
            {
                'min': _DEFAULT_VM_PORT_RANGE_MIN,
                'max': _DEFAULT_VM_PORT_RANGE_MAX
            }
        )

        # Default value argument
        self.assertEqual(config.get('doesnotexist', 'default value'),
                         'default value')
        # Default external tools path
        self.assertEqual(config.get('qemu'), _DEFAULT_QEMU_CMD)
        self.assertEqual(config.get('createrepo'), _DEFAULT_REPO_CMD)

        # Default gpg settings
        self.assertEqual(config.get('gpg'), None)

    def test_get_set(self):
        """simple set() and get()"""
        config = Config()
        # set an 'int'
        config.set('vm_cpus', 42)
        self.assertEqual(config.get('vm_cpus'), 42)

        # set a 'dict'
        config.set('repos', {'os': 'http://myserver/pub'})
        self.assertEqual(config.get('repos'), {'os': 'http://myserver/pub'})

        # set a 'list'
        config.set('arch', ['x86_64', 'aarch64'])
        self.assertEqual(config.get('arch'), ['x86_64', 'aarch64'])

        # set a 'enum'
        config.set('shared_fs_type', 'virtiofs')
        self.assertEqual(config.get('shared_fs_type'), 'virtiofs')

    def test_set_bad_type(self):
        """set() using wrong type raises an error"""
        self.assert_except(DeclError, "Bad data type str for 'vm_cpus'",
                           Config().set, 'vm_cpus', 'a string')
        self.assert_except(DeclError, "Bad data type str for 'repos'",
                           Config().set, 'repos', 'a string')
        # Default check is 'string'
        self.assert_except(DeclError, "Bad data type int for 'vm_image'",
                           Config().set, 'vm_image', 42)
        self.assert_except(DeclError,
                           "Bad data type str for 'arch'",
                           Config().set, 'arch', 'x86_64')
        # Check bad enum
        self.assertRaises(DeclError, Config().set, 'shared_fs_type', 'badtype')

    def test_set_bad_key(self):
        """set() an undefined key raises an error"""
        self.assert_except(DeclError, "Unknown 'myval' key",
                           Config().set, 'myval', 'value')
        self.assert_except(DeclError, "Unknown 'myval' key",
                           Config().set, 'myval', 'value')

    def test_get_arch_placeholder(self):
        """get() with $arch placeholder"""
        config = Config()

        # Declare supported architectures
        config.set('arch', ['x86_64', 'aarch64'])
        # $arch placeholder replacement with string
        config.set('vm_image', '/path/to/image-$arch.qcow2')
        self.assertEqual(
            config.get('vm_image', arch='x86_64'),
            '/path/to/image-x86_64.qcow2'
        )
        self.assertEqual(
            config.get('vm_image', arch='aarch64'),
            '/path/to/image-aarch64.qcow2'
        )
        # $arch placeholder replacement with dict
        config.set(
            'repos',
            {
                'os': {
                    'url': 'file:///rift/packages/$arch/os',
                    'priority': 90,
                },
                'extra': {
                    'url': 'file:///rift/packages/$arch/extra',
                    'priority': 90,
                },
            }
        )
        self.assertEqual(
            config.get('repos', arch='x86_64'),
            {
                'os': {
                    'url': 'file:///rift/packages/x86_64/os',
                    'priority': 90,
                },
                'extra': {
                    'url': 'file:///rift/packages/x86_64/extra',
                    'priority': 90,
                },
            }
        )
        self.assertEqual(
            config.get('repos', arch='aarch64'),
            {
                'os': {
                    'url': 'file:///rift/packages/aarch64/os',
                    'priority': 90,
                },
                'extra': {
                    'url': 'file:///rift/packages/aarch64/extra',
                    'priority': 90,
                },
            }
        )

    def test_get_arch_specific_override(self):
        """get() with specific arch override"""
        config = Config()

        # Declare supported architectures
        config.set('arch', ['x86_64', 'aarch64'])
        # Override with arch specific value
        config.set('vm_image', '/path/to/image-$arch.qcow2')
        config.set('vm_image', '/path/to/other-image.qcow2', arch='x86_64')
        self.assertEqual(
            config.get('vm_image', arch='aarch64'),
            '/path/to/image-aarch64.qcow2'
        )
        self.assertEqual(
            config.get('vm_image', arch='x86_64'),
            '/path/to/other-image.qcow2'
        )

    def test_get_unsupported_arch(self):
        """get() with unsupported arch"""
        config = Config()

        # Get with unsupported arch must fail
        with self.assertRaisesRegex(
            DeclError,
            "^Unable to get configuration option for unsupported architecture "
            "'fail'$"
        ):
            config.get('vm_image', arch='fail')

    def test_set_unsupported_arch(self):
        """set() with unsupported arch"""
        config = Config()

        with self.assertRaisesRegex(
            DeclError,
            "^Unable to set configuration option for unsupported architecture "
            "'fail'$"
        ):
            config.set('vm_image', '/path/to/image.qcow2', arch='fail')


    def test_load(self):
        """load() checks mandatory options are present"""
        emptyfile = make_temp_file("")
        self.assert_except(DeclError, "'annex' is not defined",
                           Config().load, emptyfile.name)

        cfgfile = make_temp_file("annex: /a/dir\nvm_image: /a/image.img")
        config = Config()
        # Simple filename
        config.load(cfgfile.name)

        config = Config()
        # List of filenames
        config.load([cfgfile.name])

        # Default config files
        self.assert_except(DeclError, "'annex' is not defined",
                           Config().load)

    def test_load_multiple_files(self):
        """load() loads multiple files"""
        conf_files = [
            make_temp_file(
                textwrap.dedent(
                    """
                    annex: /a/dir
                    vm_image: /a/image.img
                    """
                )
            ),
            make_temp_file(
                textwrap.dedent(
                    """
                    vm_image: /b/image.img
                    arch:
                    - x86_64
                    - aarch64
                    """
                )
            ),
        ]
        config = Config()
        config.load([conf_file.name for conf_file in conf_files])
        # Value from 1st file should be loaded
        self.assertEqual(config.get('annex'), '/a/dir')
        # Value from 2nd file should override value from 1st file
        self.assertEqual(config.get('vm_image'), '/b/image.img')
        # Value from 2nd file should be loaded
        self.assertEqual(config.get('arch'), ['x86_64', 'aarch64'])

    def test_load_arch_specific(self):
        """load() properly loads architecture specific options"""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm_image: /a/image.img
                arch:
                - x86_64
                - aarch64
                x86_64:
                    vm_image: /b/image.img
                aarch64:
                    vm_image: /c/image.img
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('vm_image'), '/a/image.img')
        self.assertEqual(config.get('vm_image', arch='x86_64'), '/b/image.img')
        self.assertEqual(config.get('vm_image', arch='aarch64'), '/c/image.img')

    def test_load_arch_specific_invalid_mapping(self):
        """load() fail with not mapping architecture specific options"""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm_image: /a/image.img
                x86_64: fail
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
            DeclError,
            '^Architecture specific override for x86_64 must be a mapping$',
        ):
            config.load(cfgfile.name)

    def test_load_arch_specific_invalid_key(self):
        """load() fail with architecture specific invalid key"""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm_image: /a/image.img
                x86_64:
                    fail: value
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
            DeclError,
            "^Unknown 'fail' key$",
        ):
            config.load(cfgfile.name)

    def test_load_missing_required_key(self):
        """load() fail when required key is missing"""
        contents = {
            # vm_image is not defined at all
            """
            annex: /a/dir
            """,
            # vm_image is not defined for aarch64
            """
            annex: /a/dir
            arch:
            - x86_64
            - aarch64
            x86_64:
              vm_image: /a/image.img
            """
        }
        for content in contents:
            cfgfile = make_temp_file(textwrap.dedent(content))
            config = Config()
            with self.assertRaisesRegex(
                DeclError,
                "^'vm_image' is not defined$",
            ):
                config.load(cfgfile.name)

    def test_load_required_key_in_archs_ok(self):
        """load() succeeds when required key is declared for all architectures."""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                arch:
                - x86_64
                - aarch64
                x86_64:
                    vm_image: /b/image.img
                aarch64:
                    vm_image: /c/image.img
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)

    def test_load_missing_file(self):
        """load() an non-existent file raises a nice error"""
        config = Config()
        config.ALLOW_MISSING = False
        self.assert_except(DeclError, "Could not find '/does/not/exist'",
                           config.load, "/does/not/exist")

        # Wrong file type
        self.assert_except(DeclError, "[Errno 21] Is a directory: '/'",
                           config.load, "/")

    def test_load_bad_syntax(self):
        """load() an bad YAML syntax file raises an error"""
        cfgfile = make_temp_file("[value= not really YAML] [ ]\n")
        self.assertRaises(DeclError, Config().load, cfgfile.name)

    def test_load_dict_merged(self):
        """load() merges dict from multiple files"""
        conf_files = [
            make_temp_file(
                textwrap.dedent(
                    """
                    annex: /a/dir
                    vm_image: /a/image.img
                    repos:
                      os:
                        url: https://os/url/file1
                      extra:
                        url: https://extra/url/file1
                    """
                )
            ),
            make_temp_file(
                textwrap.dedent(
                    """
                    repos:
                      os:
                        url: https://os/url/file2
                        modules_hotfixes: true
                      update:
                        url: https://update/url/file2
                    """
                )
            ),
        ]
        config = Config()
        config.load([conf_file.name for conf_file in conf_files])
        repos = config.get('repos')
        self.assertTrue('os' in repos)
        self.assertTrue('update' in repos)
        self.assertTrue('extra' in repos)
        self.assertEquals(repos['os']['url'], 'https://os/url/file2')
        self.assertTrue('modules_hotfixes' in repos['os'])
        self.assertEquals(repos['update']['url'], 'https://update/url/file2')
        self.assertEquals(repos['extra']['url'], 'https://extra/url/file1')

    def test_load_port_partial_port_range(self):
        """Load partial port range dict"""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm_image: /a/image.img
                vm_port_range:
                  min: 2000
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('vm_port_range').get('min'), 2000)
        self.assertEqual(
            config.get('vm_port_range').get('max'),
            _DEFAULT_VM_PORT_RANGE_MAX
        )
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm_image: /a/image.img
                vm_port_range:
                  max: 30000
                """
            )
        )
        config.load(cfgfile.name)
        self.assertEqual(
            config.get('vm_port_range').get('min'),
            _DEFAULT_VM_PORT_RANGE_MIN
        )
        self.assertEqual(config.get('vm_port_range').get('max'), 30000)

    def test_load_gpg(self):
        """Load gpg parameters"""
        # Check without passphrase
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm_image: /a/image.img
                gpg:
                  keyring: /path/to/keyring
                  key: rift
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('gpg').get('keyring'), '/path/to/keyring')
        self.assertEqual(config.get('gpg').get('key'), 'rift')
        self.assertEqual(config.get('gpg').get('passphrase'), None)

        # Check with passphrase
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm_image: /a/image.img
                gpg:
                  keyring: /path/to/keyring
                  key: rift
                  passphrase: secr3t
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('gpg').get('keyring'), '/path/to/keyring')
        self.assertEqual(config.get('gpg').get('key'), 'rift')
        self.assertEqual(config.get('gpg').get('passphrase'), 'secr3t')

    def test_load_gpg_missing_keyring_or_key(self):
        """Skip gpg parameters load if missing keyring or key"""
        # Check missing both key and keyring or one of them
        for gpg_config in ['{}', '{keyring: /path/to/keyring}', '{key: rift}']:
            cfgfile = make_temp_file(
                textwrap.dedent(
                    f"""
                    annex: /a/dir
                    vm_image: /a/image.img
                    gpg: {gpg_config}
                    """
                )
            )
            config = Config()
            with self.assertRaisesRegex(
                    DeclError,
                    '^Key (key|keyring) is required in dict parameter gpg$'
                ):
                config.load(cfgfile.name)
            self.assertEqual(config.get('gpg'), None)

    def test_load_gpg_unknown_key(self):
        """Load gpg parameters raise DeclError if unknown key"""
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                annex: /a/dir
                vm_image: /a/image.img
                gpg:
                  epic: fail
                  keyring: /path/to/keyring
                  key: rift
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(DeclError, '^Unknown gpg keys: epic$'):
            config.load(cfgfile.name)


class ConfigTestSyntax(RiftTestCase):
    """Test Config with modified syntax."""
    def setUp(self):
        # Save reference to original Config syntax class attribute. There is no
        # need to copy the dict as a new dict is allocated and assigned to class
        # attribute right after this.
        self.syntax_backup = Config.SYNTAX
        # Initialize syntax with arch which is the only hard requirement in
        # class logic.
        Config.SYNTAX = {
            'arch': {
                'check': 'list',
                'default': ['x86_64'],
            }
        }

    def tearDown(self):
        # Restore reference to original syntax dict in class attribute.
        Config.SYNTAX = self.syntax_backup

    def test_load_dict_without_syntax(self):
        """Load dict without syntax"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'dict',
            }
        })

        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1: value1
                  with: anything
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('param0').get('key1'), 'value1')
        self.assertEqual(config.get('param0').get('with'), 'anything')

    def test_load_dict_with_arch(self):
        """Load dict with archs"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'dict',
            }
        })

        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                arch:
                - x86_64
                - aarch64
                param0:
                  key1: value1
                  with: anything
                aarch64:
                    param0:
                        key1: value2
                        with: another
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('param0').get('key1'), 'value1')
        self.assertEqual(config.get('param0').get('with'), 'anything')
        self.assertEqual(
            config.get('param0', arch='x86_64').get('key1'), 'value1'
        )
        self.assertEqual(
            config.get('param0', arch='x86_64').get('with'), 'anything'
        )
        self.assertEqual(
            config.get('param0', arch='aarch64').get('key1'), 'value2'
        )
        self.assertEqual(
            config.get('param0', arch='aarch64').get('with'), 'another'
        )

    def _add_fake_dict_param_syntax(self):
        """Load dict with syntax"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'dict',
                'syntax': {
                    'key1': {
                        'required': True
                    },
                    'key2': {
                        'check': 'digit'
                    }
                }
            }
        })

    def test_load_dict_with_syntax(self):
        """Load dict with syntax"""
        self._add_fake_dict_param_syntax()
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1: value1
                  key2: 2
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('param0').get('key1'), 'value1')
        self.assertEqual(config.get('param0').get('key2'), 2)

        # Test with another value for key1 and key2 undefined.
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1: value2
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(config.get('param0').get('key1'), 'value2')
        self.assertEqual(config.get('param0').get('key2'), None)

    def test_load_dict_bad_subkey_type(self):
        """Load dict with bad subkey type"""
        self._add_fake_dict_param_syntax()
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1: value1
                  key2: fail
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
                DeclError,
                "^Bad data type str for 'key2'$"
            ):
            config.load(cfgfile.name)

    def test_load_dict_missing_subkey(self):
        """Load dict with missing subkey."""
        self._add_fake_dict_param_syntax()
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key2: 2
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
                DeclError,
                "^Key key1 is required in dict parameter param0$"
            ):
            config.load(cfgfile.name)

    def test_load_dict_unknown_subkey(self):
        """Load dict with unknown subkey."""
        self._add_fake_dict_param_syntax()
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1: value1
                  key3: value2
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
                DeclError,
                "^Unknown param0 keys: key3$"
            ):
            config.load(cfgfile.name)

    def test_load_dict_recursive_syntax(self):
        """Load dict with resursive syntax"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'dict',
                'syntax': {
                    'key1': {
                        'check': 'dict',
                        'syntax': {
                            'subkey2': {
                                'required': True
                            },
                            'subkey3': {
                                'check': 'digit'
                            },
                        },
                    },
                },
            },
        })
        # Check load of valid param0
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1:
                    subkey2: value2
                    subkey3: 5
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(
            config.get('param0').get('key1').get('subkey2'), 'value2'
        )
        self.assertEqual(
            config.get('param0').get('key1').get('subkey3'), 5
        )

        # Check syntax is really enforced on sub-sub-dict
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                  key1:
                    subkey2: value2
                    subkey3: fail
                """
            )
        )
        config = Config()
        with self.assertRaisesRegex(
                DeclError,
                "^Bad data type str for 'subkey3'$"
            ):
            config.load(cfgfile.name)

    def test_load_dict_with_syntax_default_value_partial_def(self):
        """Load dict with default value defined in syntax and partial definition"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'dict',
                'syntax': {
                    'key1': {
                        'default': 'default_key1',
                    },
                    'key2': {
                        'check': 'dict',
                        'syntax': {
                            'subkey2': {
                                'default': 'default_subkey2',
                            },
                            'subkey3': {
                                'default': 'default_subkey3',
                            }
                        }
                    },
                    'key3': {
                        'check': 'dict',
                        'default': {
                            'subkey5': 'default_subkey5',
                        },
                    },
                }
            }
        })
        cfgfile = make_temp_file(
            textwrap.dedent(
                """
                param0:
                    key2:
                        subkey3: overriden_subkey3
                """
            )
        )
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(
            config.get('param0'),
            {
                'key1': 'default_key1',
                'key2': {
                    'subkey2': 'default_subkey2',
                    # Value defined in config file must be properly loaded
                    'subkey3': 'overriden_subkey3',
                },
                'key3': {
                    'subkey5': 'default_subkey5',
                }
            }
        )


    def test_load_dict_with_syntax_default_value(self):
        """Load dict with default value defined in syntax"""
        Config.SYNTAX.update({
            'param0': {
                'check': 'dict',
                'syntax': {
                    'key1': {
                        'default': 'default_key1',
                    },
                    'key2': {
                        'check': 'dict',
                        'syntax': {
                            'subkey2': {
                                'default': 'default_subkey2',
                            },
                            'subkey3': {
                                'default': 'default_subkey3',
                            }
                        }
                    },
                    'key3': {
                        'check': 'dict',
                        'default': {
                            'subkey5': 'default_subkey5',
                        },
                        'syntax': {
                            'subkey4': {
                                'default': 'default_subkey4',
                            },
                            'subkey5': {}
                        },
                    },
                }
            }
        })
        cfgfile = make_temp_file('')
        config = Config()
        config.load(cfgfile.name)
        self.assertEqual(
            config.get('param0'),
            {
                'key1': 'default_key1',
                'key2': {
                    # Default values must be extracted from key2 syntax.
                    'subkey2': 'default_subkey2',
                    'subkey3': 'default_subkey3',
                },
                'key3': {
                    # Default value defined at key3 level has the priority over
                    # the default value defined at subkeys level in syntax.
                    'subkey5': 'default_subkey5',
                }
            }
        )

    def test_load_dict_merged_syntax(self):
        """load() merges dict from multiple files with syntax"""
        self._add_fake_dict_param_syntax()
        conf_files = [
            make_temp_file(
                textwrap.dedent(
                    """
                    param0:
                      key1: value1
                    """
                )
            ),
            make_temp_file(
                textwrap.dedent(
                    """
                    param0:
                      key1: value2
                      key2: 1
                    """
                )
            ),
        ]
        config = Config()
        config.load([conf_file.name for conf_file in conf_files])
        param0 = config.get('param0')
        self.assertTrue('key1' in param0)
        self.assertTrue('key2' in param0)
        self.assertEquals(param0['key1'], 'value2')
        self.assertEquals(param0['key2'], 1)



class ProjectConfigTest(RiftTestCase):

    def setUp(self):
        self.cwd = os.getcwd()
        self.projdir = make_temp_dir()
        self.packagesdir = os.path.join(self.projdir, 'packages')
        os.mkdir(self.packagesdir)
        self.foodir = os.path.join(self.projdir, 'packages', 'foo')
        os.mkdir(self.foodir)
        self.projectpath = os.path.join(self.projdir, Config._DEFAULT_FILES[0])
        os.mknod(self.projectpath)

    def tearDown(self):
        os.unlink(self.projectpath)
        os.rmdir(self.foodir)
        os.rmdir(self.packagesdir)
        os.rmdir(self.projdir)
        os.chdir(self.cwd)

    def test_find_project_dir(self):
        """find_project_dir() in sub-directories"""
        for path in (self.projdir, self.packagesdir, self.foodir):
            os.chdir(path)
            self.assertEqual(Config().find_project_dir(), self.projdir)

    def test_project_path_absolute(self):
        """project_path() using absolute path is ok"""
        absolutepath = os.path.abspath('foo')
        for path in (self.projdir, self.packagesdir, self.foodir):
            os.chdir(path)
            self.assertEqual(Config().project_path(absolutepath), absolutepath)

    def test_project_path_relative(self):
        """project_path() using project root relative dir is ok"""
        relativepath = os.path.join('relative', 'path')
        realpath = os.path.join(self.projdir, relativepath)
        os.chdir(self.projdir)
        self.assertEqual(Config().project_path(relativepath), realpath)


class StaffTest(RiftTestCase):

    def setUp(self):
        config = Config()
        self.staff = Staff(config)

    def test_empty(self):
        """create an empty Staff object"""
        self.assertEqual(self.staff._data, {})

    def test_load_ok(self):
        """load a staff file"""
        tmp = make_temp_file("{staff: {'J. Doe': {email: 'j.doe@rift.org'}} }")
        self.staff.load(tmp.name)
        self.assertEqual(self.staff.get('J. Doe'), {'email': 'j.doe@rift.org'})

    def test_load_default_ok(self):
        """load a staff file using default path"""
        self.assertFalse(self.staff.get('J. Doe'))

        tmp = make_temp_file("{staff: {'J. Doe': {email: 'j.doe@rift.org'}} }")
        self.staff.DEFAULT_PATH = tmp.name
        self.staff.load()
        self.assertEqual(self.staff.get('J. Doe'), {'email': 'j.doe@rift.org'})

    def test_load_missing_file(self):
        """load a missing staff file"""
        self.assert_except(DeclError, "Could not find '/tmp/does_not_exist'",
                           self.staff.load, '/tmp/does_not_exist')

    def test_load_unreadable_file(self):
        """load an unaccessible staff file"""
        tmp = make_temp_file("{staff: {'J. Doe': {email: 'j.doe@rift.org'}} }")
        self.staff.load(tmp.name)
        # Compat python2/3 syntax
        os.chmod(tmp.name, int(oct(0o200), 8))
        self.assertRaises(DeclError, self.staff.load, tmp.name)

    def test_load_error(self):
        """load a staff file with a bad yaml syntax"""
        tmp = make_temp_file("bad syntax: { , }")
        self.assertRaises(DeclError, self.staff.load, tmp.name)

    def test_load_bad_format(self):
        """load a staff file with a bad yaml structure (list instead of dict)"""
        tmp = make_temp_file("{staff: ['John Doe', 'Ben Harper']}")
        self.assert_except(DeclError, "Bad data format in staff file",
                           self.staff.load, tmp.name)

    def test_load_bad_syntax(self):
        """load a staff file with a bad yaml structure (missing 'staff')"""
        tmp = make_temp_file("{people: ['John Doe', 'Ben Harper']}")
        self.assert_except(DeclError, "Missing 'staff' at top level in staff file",
                           self.staff.load, tmp.name)

    def test_load_useless_items(self):
        """load a staff file with unknown items"""
        tmp = make_temp_file("""{staff:
           {'J. Doe': {email: 'john.doe@rift.org', id: 145, reg: 'foo'}} }""")
        self.assert_except(DeclError, "Unknown 'id', 'reg' item(s) for J. Doe",
                           self.staff.load, tmp.name)

    def test_load_missing_item(self):
        """load a staff file with missing items"""
        tmp = make_temp_file("""{staff: {'John Doe': {id: 145}} }""")
        self.assert_except(DeclError, "Missing 'email' item(s) for John Doe",
                           self.staff.load, tmp.name)


class ModulesTest(RiftTestCase):

    def setUp(self):
        config = Config()
        self.staff = Staff(config)
        self.modules = Modules(config, self.staff)

    def test_empty(self):
        """create an empty Modules object"""
        self.assertEqual(self.modules._data, {})

    def test_load_error(self):
        """load a modules file with a bad yaml syntax"""
        tmp = make_temp_file("bad syntax: { , }")
        self.assertRaises(DeclError, self.modules.load, tmp.name)

    def test_load_ok(self):
        """load a modules file"""
        self.staff._data['John Doe'] = {'email': 'john.doe@rift.org'}

        tmp = make_temp_file("{modules: {Kernel: {manager: 'John Doe'}} }")
        self.modules.load(tmp.name)
        self.assertEqual(self.modules.get('Kernel'), {'manager': ['John Doe']})

    def test_load_managers(self):
        """load a modules file with several managers"""
        self.staff._data['John Doe'] = {'email': 'john.doe@rift.org'}
        self.staff._data['Boo'] = {'email': 'boo@rift.org'}

        tmp = make_temp_file("""{modules: {Kernel:
                                {manager: ['John Doe', 'Boo']}} }""")
        self.modules.load(tmp.name)
        self.assertEqual(self.modules.get('Kernel'),
                         {'manager': ['John Doe', 'Boo']})

    def test_load_missing_managers(self):
        """load a modules file with a undeclared manager"""
        tmp = make_temp_file("{modules: {Kernel: {manager: 'John Doe'}} }")
        self.assert_except(DeclError,
                           "Manager 'John Doe' does not exist in staff list",
                           self.modules.load, tmp.name)
