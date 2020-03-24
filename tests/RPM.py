#
# Copyright (C) 2020 CEA
#
import os

from TestUtils import make_temp_dir, RiftTestCase
from rift import RiftError
from rift.RPM import Spec

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
        with open(self.spec, "w") as spec:
            spec.write("Name:    {0}\n".format(self.name))
            spec.write("Version:        {0}\n".format(self.version))
            spec.write("Release:        {0}\n".format(self.release))
            spec.write("Summary:        A package\n")
            spec.write("Group:          System Environment/Base\n")
            spec.write("License:        GPL\n")
            spec.write("URL:            http://nowhere.com/projects/%{name}/\n")
            spec.write("Source0:        https://nowhere.com/sources/%{name}-%{version}.tar.gz\n")
            spec.write("BuildArch:      {0}\n".format(self.arch))
            spec.write("BuildRequires:  br-package\n")
            spec.write("Requires:       another-package\n")
            spec.write("Provides:       {0}-provide\n".format(self.name))
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
                       " - {0}-{1}\n".format(self.version, self.release))
            spec.write("- Update to {0} release\n".format(self.version))

    def tearDown(self):
        os.unlink(self.spec)

    def test_init(self):
        """ Test Spec instanciation """
        spec = Spec(self.spec)
        self.assertTrue(self.name in spec.pkgnames)
        self.assertEqual(len(spec.pkgnames), 1)
        self.assertEqual(spec.arch, self.arch)
        self.assertTrue("{0}-{1}.tar.gz".format(self.name, self.version) in spec.sources)

    def test_init_fails(self):
        """ Test Spec instanciation with error """
        path = '/nowhere.spec'
        self.assert_except(RiftError, "{0} does not exist".format(path), Spec, path)

    def test_specfile_check(self):
        """ Test specfile check function """
        self.assertIsNone(Spec(self.spec).check())
