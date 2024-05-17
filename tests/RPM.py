#
# Copyright (C) 2020 CEA
#
import os
import time
import rpm

from TestUtils import make_temp_dir, gen_rpm_spec, RiftTestCase
from rift import RiftError
from rift.RPM import Spec, Variable, RPMLINT_CONFIG

class SpecTest(RiftTestCase):
    """
    Tests class for Spec
    """

    def setUp(self):
        self.name='pkg'
        self.version='1.0'
        self.release='1'
        self.arch='noarch'
        # /tmp/rift-*/pkg.spec
        self.directory = make_temp_dir()
        self.spec = os.path.join(self.directory, "{0}.spec".format(self.name))
        self.prepsteps = ""
        self.buildsteps = ""
        self.installsteps = ""
        self.files = ""
        self.update_spec()


    def update_spec(self):
        with open(self.spec, "w") as spec:
            spec.write(
                gen_rpm_spec(
                    name=self.name,
                    version=self.version,
                    release=self.release,
                    arch=self.arch,
                    prepsteps=self.prepsteps,
                    buildsteps=self.buildsteps,
                    installsteps=self.installsteps,
                    files=self.files
                )
            )

    def tearDown(self):
        os.unlink(self.spec)
        os.rmdir(self.directory)


    def test_init(self):
        """ Test Spec instanciation """
        spec = Spec(self.spec)
        self.assertTrue(self.name in spec.pkgnames)
        self.assertEqual(len(spec.pkgnames), 1)
        self.assertEqual(spec.exclusive_archs, [])
        self.assertEqual(spec.arch, self.arch)
        self.assertTrue("{0}-{1}.tar.gz".format(self.name, self.version) in spec.sources)
        self.assertEqual(len(spec.lines), 36)

    def test_init_fails(self):
        """ Test Spec instanciation with error """
        path = '/nowhere.spec'
        self.assert_except(RiftError, "{0} does not exist".format(path), Spec, path)


    def test_specfile_check(self):
        """ Test specfile check function """
        self.assertIsNone(Spec(self.spec).check())


    def test_specfile_check_with_rpmlint(self):
        """ Test specfile check function with a custom rpmlint file"""
        # Make an errorneous specfile with hardcoded /lib
        self.files = "/lib/test"
        self.update_spec()
        with self.assertRaisesRegex(RiftError, 'rpmlint reported errors'):
            Spec(self.spec).check()

        # Create rpmlintfile to ignore hardcoded library path
        rpmlintfile = os.sep.join([self.directory, RPMLINT_CONFIG])
        with open(rpmlintfile, "w") as rpmlint:
            rpmlint.write('addFilter("E: hardcoded-library-path")')
        self.assertIsNone(Spec(self.spec).check())
        os.unlink(rpmlintfile)


    def test_bump_release(self):
        """ Test bump_release """
        spec = Spec(self.spec)
        spec.release = '1'
        spec.bump_release()
        self.assertEqual(spec.release, '2')
        # Check with %dist macro
        dist = rpm.expandMacro('%dist')
        spec.release = "1{}".format(dist)
        spec.bump_release()
        self.assertEqual(spec.release, '2{}'.format(dist))
        # Check with prefix in release
        spec.release = "1.keyword1{}".format(dist)
        spec.bump_release()
        self.assertEqual(spec.release, '1.keyword2{}'.format(dist))
        # Check with invalid release
        spec.release = 'a'
        self.assert_except(RiftError,
                           'Cannot parse package release: {}'.format(spec.release),
                           spec.bump_release)

    def test_add_changelog_entry(self):
        """ Test add_changelog_entry """
        spec = Spec(self.spec)
        comment = "- New feature"
        userstr = "John Doe"
        date = time.strftime("%a %b %d %Y", time.gmtime())

        # Check adding changelog entry
        spec.add_changelog_entry(userstr, comment)
        with open(spec.filepath, 'r') as fspec:
            lines = fspec.readlines()
        self.assertTrue("* {} {} - {}\n".format(date, userstr, spec.evr) in lines)
        self.assertTrue("{}\n".format(comment) in lines)

    def test_add_changelog_entry_bump(self):
        """ Test add_changelog_entry with bump release"""
        spec = Spec(self.spec)
        comment = "- New feature (Bumped)"
        userstr = "John Doe"
        date = time.strftime("%a %b %d %Y", time.gmtime())

        spec.add_changelog_entry(userstr, comment, bump=True)
        with open(spec.filepath, 'r') as fspec:
            lines = fspec.readlines()
        self.assertTrue("Release:        {}\n".format(spec.release) in lines)
        self.assertTrue("* {} {} - {}\n".format(date, userstr, spec.evr) in lines)
        self.assertTrue("{}\n".format(comment) in lines)


    def test_parse_vars(self):
        """ Test spec variables parsing """
        spec = Spec(self.spec)
        self.assertTrue(str(spec.variables['foo']) == '1.%{bar}')
        self.assertTrue(spec.variables['foo'].value == '1.%{bar}')
        self.assertTrue(spec.variables['foo'].name == 'foo')
        self.assertTrue(spec.variables['foo'].index == 0)
        self.assertTrue(spec.variables['foo'].keyword == 'global')
        self.assertTrue(str(spec.variables['bar']) == '1')
        self.assertTrue(spec.variables['bar'].keyword == 'define')
        self.assertTrue(spec.variables['bar'].index == 1)

    def test_match_var(self):
        """ Tests variable detection in pattern """
        spec = Spec(self.spec)
        foo = spec.variables['foo']
        bar = spec.variables['bar']
        self.assertTrue(spec._match_var('%{foo}', r'^1') == foo)
        self.assertTrue(spec._match_var('%{foo}') == bar)
        self.assertTrue(spec._match_var('%{?foo}') == bar)
        self.assertTrue(spec._match_var('%{foo}%{bar}') == bar)
        self.assertTrue(spec._match_var('%{bar}') == bar)
        self.assertTrue(spec._match_var('%{notthere}') is None)
        self.assertTrue(spec._match_var('%{notthere}%{foo}') == bar)
        self.assertTrue(spec._match_var('%{foo}%{?dist}') == bar)
        self.assertTrue(spec._match_var('%{foo}%{bar}%{?dist}') == bar)
        self.assertTrue(spec._match_var('no vars inside') is None)


class VariableTest(RiftTestCase):
    """ Test Variable class """
    def test_str(self):
        """ Test string representation """
        var = Variable(index=3, name='foo', value='bar', keyword='define')
        self.assertTrue(str(var) == 'bar' )

    def test_spec_output(self):
        """ Test variable format output """
        var = Variable(index=0, name='foo', value='bar', keyword='define')
        self.assertTrue(var.spec_output() == '%define foo bar' )
        buff = ['']
        var.spec_output(buff)
        self.assertTrue(buff[0] == '%define foo bar\n')
