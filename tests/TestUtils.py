#
# Copyright (C) 2014-2018 CEA
#

"""
Helper module to write unit tests for Rift project.
It contains several helper methods or classes like temporary file management.
"""

import logging
import tempfile
import unittest
import os
import tarfile
import time
import io
from collections import OrderedDict

import shutil
import jinja2
import yaml
from collections import namedtuple
from contextlib import contextmanager

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
config_opts['use_bootstrap_image'] = False
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

SPEC_TPL = """\
%global foo 1.%{bar}
%define bar 1
Name:           {{ name }}
Version:        {{ version }}
Release:        {{ release }}
Summary:        A package
Group:          System Environment/Base
License:        GPL
URL:            http://nowhere.com/projects/%{name}/
Source0:        https://nowhere.com/sources/%{name}-%{version}.tar.gz
{% if exclusive_arch %}
ExclusiveArch:  {{ exclusive_arch }}
{% endif -%}
{% if arch == 'noarch' -%}
BuildArch:      {{ arch }}
{% endif -%}
{% for build_require in build_requires | default(['br-package']) %}
BuildRequires:  {{ build_require }}
{% endfor %}
{% for require in requires | default(['another-package']) %}
Requires:       {{ require}}
{% endfor %}
Provides:       {{ name }}-provide

%description
A package

{% for subpackage in subpackages | default([]) %}
%package -n {{ subpackage.name }}
Summary: Sub-package {{ subpackage.name }}
%description -n {{ subpackage.name }}
Description for package {{ subpackage.name }}
{% endfor %}

%prep
{{ prepsteps | default("") }}

%build
# Nothing to build
{{ buildsteps | default("") }}

%install
# Nothing to install
{{ installsteps | default("") }}

%files
# No files
{{ files | default("") }}

%changelog
* Tue Feb 26 2019 Myself <buddy@somewhere.org> {{ version }}-{{release}}
- Update to {{ version }} release
"""

SubPackage = namedtuple("SubPackage", ["name"])


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
            conf.write("vm:\n")
            conf.write("  image:         test.img\n")
            conf.write("repos:           {}\n")
        os.chdir(self.projdir)
        # Dict of created packages
        self.pkgdirs = {}
        self.buildfiles = []
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
        for buildfile in self.buildfiles:
            os.unlink(buildfile)
        for src in self.pkgsrc.values():
            try:
                os.unlink(src)
            except FileNotFoundError:
                pass  # ignore deletion error if file is not found
        for pkgdir in self.pkgdirs.values():
            os.unlink(os.path.join(pkgdir, 'info.yaml'))
            os.rmdir(os.path.join(pkgdir, 'sources'))
            os.unlink(os.path.join(pkgdir, 'tests', '0_test.sh'))
            os.rmdir(os.path.join(pkgdir, 'tests'))
            os.rmdir(pkgdir)
        # Remove potentially generated files for VM related tests
        for path in [
            self.config.project_path(
                self.config.get('vm').get('cloud_init_tpl')
            ),
            self.config.project_path(
                self.config.get('vm').get('build_post_script')
            ),
            self.config.project_path(self.config.get('vm').get('image')),
        ]:
            if os.path.exists(path):
                os.unlink(path)
        shutil.rmtree(self.projdir)

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

    def make_pkg(
        self,
        name='pkg',
        formats=None,
        version='1.0',
        release='1',
        metadata=None,
        build_requires=['br-package'],
        requires=['another-package'],
        subpackages=[],
        src_top_dir=None,
    ):
        # By default, make package in RPM format
        if formats is None:
            formats = ['rpm']
        # Check provide package formats are supported
        for _format in formats:
            assert(_format in ['rpm'])
        # Set default source top dir name
        if src_top_dir is None:
            src_top_dir = f"{name}-{version}"
        # ./packages/pkg
        self.pkgdirs[name] = os.path.join(self.packagesdir, name)
        os.mkdir(self.pkgdirs[name])
        # ./packages/pkg/info.yaml
        info = os.path.join(self.pkgdirs[name], 'info.yaml')
        if metadata is None:
            metadata = {}
        with open(info, "w") as nfo:
            nfo.write("package:\n")
            nfo.write("    maintainers:\n")
            nfo.write("        - Myself\n")
            nfo.write(
                "    module: {}\n".format(
                    metadata.get('module', 'Great module')
                )
            )
            nfo.write(
                "    origin: {}\n".format(metadata.get('origin', 'Vendor'))
            )
            nfo.write(
                "    reason: {}\n".format(
                    metadata.get('reason', 'Missing feature')
                )
            )

        # ./packages/pkg/pkg.spec
        if 'rpm' in formats:
            buildfile = os.path.join(self.pkgdirs[name], "{0}.spec".format(name))
            with open(buildfile, "w") as spec:
                spec.write(
                    gen_rpm_spec(name=name, version=version, release=release,
                                 build_requires=build_requires, requires=requires,
                                 arch='noarch', subpackages=subpackages))
            self.buildfiles.append(buildfile)

        # ./packages/pkg/sources
        srcdir = os.path.join(self.pkgdirs[name], 'sources')
        os.mkdir(srcdir)

        # ./packages/pkg/sources/pkg-version.tar.gz
        self.pkgsrc[name] = os.path.join(srcdir,
                                         "{0}-{1}.tar.gz".format(name, version))
        with tarfile.open(self.pkgsrc[name], "w:gz") as tar:
            # Add folder in archive
            dir_info = tarfile.TarInfo(name=f"{src_top_dir}/")
            dir_info.type = tarfile.DIRTYPE
            dir_info.mode = 0o755
            dir_info.mtime = int(time.time())
            tar.addfile(dir_info)

            # Add dummy source file in archive folder
            data = b"# dummy source code\n"
            file_info = tarfile.TarInfo(name=f"{src_top_dir}/source.sh")
            file_info.size = len(data)
            file_info.mode = 0o644
            file_info.mtime = int(time.time())
            tar.addfile(file_info, io.BytesIO(data))

        # ./tests
        testsdir = os.path.join(self.pkgdirs[name], 'tests')
        os.mkdir(testsdir)

        # ./tests/0_test.sh
        test_file = os.path.join(testsdir, "0_test.sh")
        with open(test_file, "w") as fh:
            fh.write("#!/bin/sh\ntrue")

    def clean_mock_environments(self):
        """Remove mock build environments."""
        for arch in self.config.get('arch'):
            mock = Mock(self.config, arch)
            mock.scrub()

    def copy_cloud_init_tpl(self):
        """Copy cloud-init template in project tree."""
        shutil.copy(
            os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                '..',
                'template',
                'cloud-init.tpl',
            ),
            self.config.project_path(
                self.config.get('vm').get('cloud_init_tpl')
            ),
        )

    def copy_build_post_script(self):
        """Copy example build post script in project tree."""
        shutil.copy(
            os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                '..',
                'template',
                'build-post.sh',
            ),
            self.config.project_path(
                self.config.get('vm').get('build_post_script')
            ),
        )

    def ensure_vm_images_cache_dir(self):
        """Ensure VM images cache directory exists."""
        cache_dir =  self.config.project_path(
            self.config.get('vm').get('images_cache')
        )
        if not os.path.exists(cache_dir):
            os.mkdir(cache_dir)

#
# RPM spec file
#
def gen_rpm_spec(**kwargs):
    return jinja2.Template(SPEC_TPL).render(**kwargs)


#
# Temp files
#
def make_temp_dir():
    """Create and return the name of a temporary directory."""
    return tempfile.mkdtemp(prefix='rift-test-')

def make_temp_filename():
    """Return a temporary name for a file."""
    return (tempfile.mkstemp(prefix='rift-test-'))[1]

def make_temp_file(text, delete=True, suffix=None):
    """ Create a temporary file with the provided text."""
    tmp = tempfile.NamedTemporaryFile(prefix='rift-test-', delete=delete,
                                      suffix=suffix)
    tmp.write(text.encode())
    tmp.flush()
    return tmp
