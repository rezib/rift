#
# Copyright (C) 2014-2018 CEA
#

import os.path

from TestUtils import make_temp_file, make_temp_dir, RiftTestCase

from rift import DeclError
from rift.Config import Staff, Modules, Config

class ConfigTest(RiftTestCase):

    def test_get(self):
        """get() default values"""
        config = Config()

        # Default value
        self.assertEqual(config.get('packages_dir'), 'packages')

        # Default value argument
        self.assertEqual(config.get('doesnotexist', 'default value'),
                         'default value')

    def test_get_set(self):
        """simple set() and get()"""
        config = Config()
        # set an 'int'
        config.set('vm_cpus', 42)
        self.assertEqual(config.get('vm_cpus'), 42)

        # set a 'dict'
        config.set('repos', {'os': 'http://myserver/pub'})
        self.assertEqual(config.get('repos'), {'os': 'http://myserver/pub'})

    def test_set_bad_type(self):
        """set() using wrong type raises an error"""
        self.assert_except(DeclError, "Bad data type str for 'vm_cpus'",
                           Config().set, 'vm_cpus', 'a string')
        self.assert_except(DeclError, "Bad data type str for 'repos'",
                           Config().set, 'repos', 'a string')
        # Default check is 'string'
        self.assert_except(DeclError, "Bad data type int for 'arch'",
                           Config().set, 'arch', 42)

    def test_set_bad_key(self):
        """set() an undefined key raises an error"""
        self.assert_except(DeclError, "Unknown 'myval' key",
                           Config().set, 'myval', 'value')
        self.assert_except(DeclError, "Unknown 'myval' key",
                           Config().set, 'myval', 'value')

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
        os.chmod(tmp.name, oct(0o200))
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
