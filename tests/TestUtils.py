#
# Copyright (C) 2014-2018 CEA
#

"""
Helper module to write unit tests for Rift project.
It contains several helper methods or classes like temporary file management.
"""

import tempfile
import unittest
import os
from collections import OrderedDict

import yaml

from rift.Config import Config, Staff, Modules
from rift.Mock import Mock

MOCK_CONF = '''\
config_opts.setdefault('plugin_conf', {})
config_opts['plugin_conf']['ccache_enable'] = False
config_opts['root'] = '{{ name }}'
config_opts['target_arch'] = '{{ arch }}'
config_opts['legal_host_arches'] = ('{{ arch }}',)
config_opts['chroot_setup_cmd'] = 'install centos-release @base @development'
config_opts['dist'] = 'el8'
config_opts['releasever'] = '8'
config_opts['priorities.conf'] = "[main]\\nenabled = 1\\n"
config_opts['package_manager'] = 'dnf'
config_opts['bootstrap_image'] = 'centos:8'
config_opts['isolation'] = 'simple'
config_opts['chroot_setup_cmd'] = (
    'install tar gcc-c++ redhat-rpm-config redhat-release which xz sed make '
    'bzip2 gzip gcc coreutils unzip shadow-utils diffutils cpio bash gawk '
    'rpm-build info patch util-linux findutils grep autoconf automake libtool '
    'binutils bison flex gdb glibc-devel pkgconf pkgconf-m4 pkgconf-pkg-config '
    'rpm-sign byacc ctags diffstat intltool patchutils pesign source-highlight '
    'cmake rpmdevtools rpmlint libtirpc-devel kernel-rpm-macros'
)
config_opts['yum.conf'] = """
[main]
cachedir=/var/cache/yum
debuglevel=1
reposdir=/dev/null
logfile=/var/log/yum.log
retries=20
obsoletes=1
gpgcheck=0
assumeyes=1
syslog_ident=mock
syslog_device=
plugins=1
best=False

{% for repo in repos %}
[{{ repo.name }}]
name={{ repo.name }}
baseurl={{ repo.url }}
priority={{ repo.priority }}
{%if repo.module_hotfixes %}
module_hotfixes={{ repo.module_hotfixes }}
{% endif %}
{% endfor %}
"""
'''


class RiftTestCase(unittest.TestCase):
    """unittest.TestCase subclass with additional features"""

    def __init__(self, methodName='runTest'):
        unittest.TestCase.__init__(self, methodName)
        # Allow to show the full content of a diff
        self.maxDiff = None

    def assert_except(self, exc_cls, exc_str, callable_obj, *args, **kwargs):
        """
        Same as TestCase.assertRaises() but with an additional argument to
        verify raised exception string is correct.
        """
        try:
            callable_obj(*args, **kwargs)
        except exc_cls as exp:
            self.assertEqual(str(exp), exc_str)
        else:
            self.fail("%s not raised" % exc_cls.__name__)

class RiftProjectTestCase(RiftTestCase):
    """
    RiftTestCase that setup a dummy project tree filled with minimal
    requirements.
    """

    def setUp(self):
        self.cwd = os.getcwd()
        self.projdir = make_temp_dir()
        # ./packages/
        self.packagesdir = os.path.join(self.projdir, 'packages')
        os.mkdir(self.packagesdir)
        # ./packages/staff.yaml
        self.staffpath = os.path.join(self.packagesdir, 'staff.yaml')
        with open(self.staffpath, "w") as staff:
            staff.write('staff: {Myself: {email: buddy@somewhere.org}}')
        # ./packages/modules.yaml
        self.modulespath = os.path.join(self.packagesdir, 'modules.yaml')
        with open(self.modulespath, "w") as mod:
            mod.write('modules: {Great module: {manager: Myself}}')
        # ./annex/
        self.annexdir = os.path.join(self.projdir, 'annex')
        os.mkdir(self.annexdir)
        # ./project.conf
        self.projectconf = os.path.join(self.projdir, Config._DEFAULT_FILES[0])
        with open(self.projectconf, "w") as conf:
            conf.write("annex:           %s\n" % self.annexdir)
            conf.write("vm_image:        test.img\n")
            conf.write("repos:           {}\n")
        os.chdir(self.projdir)
        # Dict of created packages
        self.pkgdirs = {}
        self.pkgspecs = {}
        self.pkgsrc = {}
        # Load project/staff/modules
        self.config = Config()
        self.config.load()
        self.staff = Staff(config=self.config)
        self.staff.load(self.staffpath)
        self.modules = Modules(config=self.config, staff=self.staff)
        self.modules.load(self.modulespath)
        # ./mock.tpl
        self.mocktpl = os.path.join(self.projdir, Mock.MOCK_TEMPLATE)
        with open(self.mocktpl, "w") as fh:
            fh.write(MOCK_CONF)

    def tearDown(self):
        os.chdir(self.cwd)
        os.unlink(self.projectconf)
        os.unlink(self.staffpath)
        os.unlink(self.modulespath)
        os.unlink(self.mocktpl)
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

    def update_project_conf(self):
        """Update project YAML configuration file with new Config options."""
        class OrderedDumper(yaml.SafeDumper):
            pass
        def _dict_representer(dumper, data):
            return dumper.represent_mapping(
                yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                data.items()
            )
        OrderedDumper.add_representer(OrderedDict, _dict_representer)
        with open(self.projectconf, 'w') as fh:
            fh.write(yaml.dump(self.config.options, Dumper=OrderedDumper))

    def clean_mock_environments(self):
        """Remove mock build environments."""
        for arch in self.config.get('arch'):
            mock = Mock(self.config, arch)
            mock.scrub()

#
# Temp files
#
def make_temp_dir():
    """Create and return the name of a temporary directory."""
    return tempfile.mkdtemp(prefix='rift-test-')

def make_temp_filename():
    """Return a temporary name for a file."""
    return (tempfile.mkstemp(prefix='rift-test-'))[1]

def make_temp_file(text, delete=True):
    """ Create a temporary file with the provided text."""
    tmp = tempfile.NamedTemporaryFile(prefix='rift-test-', delete=delete)
    tmp.write(text.encode())
    tmp.flush()
    return tmp
