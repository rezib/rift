#
# Copyright (C) 2014-2024 CEA
#
# This file is part of Rift project.
#
# This software is governed by the CeCILL license under French law and
# abiding by the rules of distribution of free software.  You can  use,
# modify and/ or redistribute the software under the terms of the CeCILL
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or
# data to be ensured and,  more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.
#
"""
Controler.py:
    Core package to manage rift actions
"""
import re
import os
import argparse
import logging
from operator import attrgetter
import random
import time
import textwrap
# Since pylint can not found rpm.error, disable this check
from rpm import error as RpmError # pylint: disable=no-name-in-module
from unidiff import parse_unidiff

from rift import RiftError, __version__
from rift.Annex import Annex, is_binary
from rift.Config import Config, Staff, Modules
from rift.Gerrit import Review
from rift.Mock import Mock
from rift.Package import Package, Test
from rift.Repository import LocalRepository, ProjectArchRepositories
from rift.RPM import RPM, Spec, RPMLINT_CONFIG_V1, RPMLINT_CONFIG_V2
from rift.TempDir import TempDir
from rift.TestResults import TestCase, TestResults
from rift.TextTable import TextTable
from rift.VM import VM
from rift.sync import RepoSyncFactory
from rift.utils import message, banner


def make_parser():
    """Create command line parser"""

    parser = argparse.ArgumentParser()
    # Generic options
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="increase output verbosity (twice for debug)")
    parser.add_argument('--version', action='version',
                        version=f"%%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest='command', metavar='COMMAND')

    # Create options
    subprs = subparsers.add_parser('create', help='create a new package')
    subprs.add_argument('name', metavar='PKGNAME',
                        help='package name to be created')
    subprs.add_argument('-m', '--module', dest='module', required=True,
                        help='module name this package will belong to')
    subprs.add_argument('-r', '--reason', dest='reason', required=True,
                        help='reason this package is added to project')
    subprs.add_argument('-o', '--origin', dest='origin',
                        help='source of original package')
    subprs.add_argument('-t', '--maintainer', dest='maintainer',
                        help='maintainer name from staff.yaml')

    # Import options
    subprs = subparsers.add_parser('import',
                                   help='import a SRPM and create a package')
    subprs.add_argument('file', metavar='FILE', help='source RPM to import')
    subprs.add_argument('-m', '--module', dest='module', required=True,
                        help='module name this package will belong to')
    subprs.add_argument('-r', '--reason', dest='reason', required=True,
                        help='reason this package is added to project')
    subprs.add_argument('-o', '--origin', dest='origin',
                        help='source of original package')
    subprs.add_argument('-t', '--maintainer', dest='maintainer',
                        help='maintainer name from staff.yaml')

    # Reimport options
    subprs = subparsers.add_parser('reimport',
                                   help='update an existing package with a SRPM')
    subprs.add_argument('file', metavar='FILE', help='source RPM to import')
    subprs.add_argument('-m', '--module', dest='module',
                        help='module name this package will belong to')
    subprs.add_argument('-r', '--reason', dest='reason',
                        help='reason this package is added to project')
    subprs.add_argument('-o', '--origin', dest='origin',
                        help='source of original package')
    subprs.add_argument('-t', '--maintainer', dest='maintainer',
                        help='maintainer name from staff.yaml')

    # Check options
    subprs = subparsers.add_parser('check',
                                   help='verify various config file syntaxes')
    subprs.add_argument('type', choices=['staff', 'modules', 'info', 'spec'],
                        metavar='CHKTYPE', help='type of check')
    subprs.add_argument('-f', '--file', metavar='FILE',
                        help='path of file to check')

    # Build options
    subprs = subparsers.add_parser('build', help='build source RPM and RPMS')
    subprs.add_argument('packages', metavar='PACKAGE', nargs='*',
                        help='package name to build')
    subprs.add_argument('-p', '--publish', action='store_true',
                        help='publish build RPMS to repository')
    subprs.add_argument('-s', '--sign', action='store_true',
                        help='sign built packages with GPG key '
                             '(implies -p, --publish)')
    subprs.add_argument('--junit', metavar='FILENAME',
                        help='write junit result file')
    subprs.add_argument('--dont-update-repo', dest='updaterepo', action='store_false',
                        help='do not update repository metadata when publishing a package')

    # Sign options
    subprs = subparsers.add_parser('sign', help='Sign RPM package with GPG key.')
    subprs.add_argument('packages', metavar='PACKAGE', nargs='*',
                        help='package to sign.')

    # Test options
    subprs = subparsers.add_parser('test', help='execute package tests')
    subprs.add_argument('packages', metavar='PACKAGE', nargs='*',
                        help='package name to test')
    subprs.add_argument('--noquit', action='store_true',
                        help='do not stop VM at the end')
    subprs.add_argument('--noauto', action='store_true',
                        help='do not run auto tests')
    subprs.add_argument('--junit', metavar='FILENAME',
                        help='write junit result file')

    # Validate options
    subprs = subparsers.add_parser('validate', help='Fully validate package')
    subprs.add_argument('packages', metavar='PACKAGE', nargs='*',
                        help='package name to validate')
    subprs.add_argument('-s', '--sign', action='store_true',
                        help='sign built packages with GPG key '
                             '(implies -p, --publish)')
    subprs.add_argument('--noquit', action='store_true',
                        help='do not stop VM at the end')
    subprs.add_argument('--noauto', action='store_true',
                        help='do not run auto tests')
    subprs.add_argument('--notest', dest='test', action='store_false', default=True,
                        help='do not run ANY tests')
    subprs.add_argument('--junit', metavar='FILENAME',
                        help='write junit result file')
    subprs.add_argument('-p', '--publish', action='store_true',
                        help='publish build RPMS to repository')

    # Validate diff
    subprs = subparsers.add_parser('validdiff')
    subprs.add_argument('patch', metavar='PATCH', type=argparse.FileType('r'))
    subprs.add_argument('-s', '--sign', action='store_true',
                        help='sign built packages with GPG key '
                             '(implies -p, --publish)')
    subprs.add_argument('--noquit', action='store_true',
                        help='do not stop VM at the end')
    subprs.add_argument('--noauto', action='store_true',
                        help='do not run auto tests')
    subprs.add_argument('--notest', dest='test', action='store_false', default=True,
                        help='do not run ANY tests')
    subprs.add_argument('--junit', metavar='FILENAME',
                        help='write junit result file')
    subprs.add_argument('-p', '--publish', action='store_true',
                        help='publish build RPMS to repository')

    # Annex options
    subprs = subparsers.add_parser('annex', help='Manipulate annex cache')

    subprs_annex = subprs.add_subparsers(dest='annex_cmd',
                                         title='possible commands')
    subsubprs_annex_backup = subprs_annex.add_parser(
        'backup', help='backup the annex to a tar.gz archive'
    )
    subsubprs_annex_backup.add_argument(
        '--output-file', metavar='PATH', required=False,
        help='annex backup output file'
    )

    subprs_annex.add_parser('list', help='list cache content')
    subsubprs = subprs_annex.add_parser('push', help='move a file into cache')
    subsubprs.add_argument('files', metavar='FILENAME', nargs='+',
                           help='file path to be move')
    subsubprs = subprs_annex.add_parser('restore',
                                        help='restore file content previously pushed to annex')
    subsubprs.add_argument('files', metavar='FILENAME', nargs='+',
                           help='file path to be restored')
    subsubprs = subprs_annex.add_parser('delete',
                                        help='remove a file from cache')
    subsubprs.add_argument('id', metavar='ID', help='digest ID to delete')
    subsubprs = subprs_annex.add_parser('get', help='Copy a file from cache')
    subsubprs.add_argument('--id', metavar='DIGEST', required=True,
                           help='digest ID to read')
    subsubprs.add_argument('--dest', metavar='PATH', required=True,
                           help='destination path')

    # VM options
    subprs = subparsers.add_parser('vm', help='Manipulate VM process')
    subprs.add_argument('-a', '--arch', help='CPU architecture of the VM')
    subprs_vm = subprs.add_subparsers(dest='vm_cmd', title='possible commands')
    subprs_vm.add_parser('connect', help='connect to running VM')
    subsubprs = subprs_vm.add_parser('start', help='launch a new VM')
    subsubprs.add_argument('--notemp', action='store_false', dest='tmpimg',
                           default=True, help='modify the real VM image')
    subprs_vm.add_parser('stop', help='stop the running VM')
    subprs_vm.add_parser('console', help='console of the running VM')
    subsubprs = subprs_vm.add_parser('cmd', help='run a command inside the VM')
    subsubprs.add_argument('commandline', help='command line arguments',
                           nargs=argparse.REMAINDER)
    subsubprs = subprs_vm.add_parser('copy', help='copy files with VM')
    subsubprs.add_argument('source', help='source files')
    subsubprs.add_argument('dest', help='destination files')
    subsubprs = subprs_vm.add_parser('build', help='build image of test VM')
    subsubprs.add_argument('url', help='URL of base cloud image')
    subsubprs.add_argument('--force', action='store_true',
                           help='ignore cache and force download of cloud image')
    subsubprs.add_argument('-o', '--output',
                           help='path of generated virtual machine image')
    subsubprs.add_argument('--deploy', action='store_true',
                           help='deploy project image defined in configuration')
    subsubprs.add_argument('--keep', action='store_true',
                           help='keep virtual machine alive in case of boot failure')

    # query
    subprs = subparsers.add_parser('query', help='Show packages metadata')
    subprs.add_argument('packages', metavar='PACKAGE', nargs='*',
                        help='package name to validate')
    subprs.add_argument('--format', dest='fmt', help='Display format')
    subprs.add_argument('--nospec', dest='spec',
                        action='store_false', help="Don't load specfile info")
    subprs.add_argument('-H', '--no-header', dest='headers',
                        action='store_false', help='Hide table headers')

    # Add changelog entry
    subprs = subparsers.add_parser('changelog',
                                   help='Add a new changelog entry')
    subprs.add_argument('package', metavar='PACKAGE',
                        help='package name to add changelog entry to')
    subprs.add_argument('-c', '--comment', metavar='COMMENT', required=True,
                        help='Changelog comment')
    subprs.add_argument('-t', '--maintainer', dest='maintainer',
                        help='maintainer name from staff.yaml')
    subprs.add_argument('--bump', dest='bump', action='store_true',
                        help='also bump the release number')

    # Gerrit review
    subprs = subparsers.add_parser('gerrit', add_help=False,
                                   help='Make Gerrit automatic review')
    subprs.add_argument('--change', help="Gerrit Change-Id", required=True)
    subprs.add_argument('--patchset', help="Gerrit patchset ID", required=True)
    subprs.add_argument('patch', metavar='PATCH', type=argparse.FileType('r'))

    # sync
    subprs = subparsers.add_parser('sync', help='Synchronize remote repositories')
    subprs.add_argument('-o', '--output', help='Synchronization output directory')
    subprs.add_argument('repositories', metavar='REPOSITORY', nargs='*',
                        help='repositories to synchronize (default: all)')

    # Parse options
    return parser

def action_check(args, config):
    """Action for 'check' sub-commands."""

    if args.type == 'staff':

        staff = Staff(config)
        staff.load(args.file or config.get('staff_file'))
        logging.info('Staff file is OK.')

    elif args.type == 'modules':

        staff = Staff(config)
        staff.load(config.get('staff_file'))
        modules = Modules(config, staff)
        modules.load(args.file or config.get('modules_file'))
        logging.info('Modules file is OK.')

    elif args.type == 'info':

        staff = Staff(config)
        staff.load(config.get('staff_file'))
        modules = Modules(config, staff)
        modules.load(config.get('modules_file'))

        if args.file is None:
            raise RiftError("You must specifiy a file path (-f)")

        pkg = Package('dummy', config, staff, modules)
        pkg.sourcesdir = '/'
        pkg.load(args.file)
        logging.info('Info file is OK.')

    elif args.type == 'spec':

        if args.file is None:
            raise RiftError("You must specifiy a file path (-f)")

        spec = Spec(args.file, config=config)
        spec.check()
        logging.info('Spec file is OK.')


def action_annex(args, config, staff, modules):
    """Action for 'annex' sub-commands."""
    annex = Annex(config)

    assert args.annex_cmd in (
        'backup', 'list', 'get',
        'push', 'delete', 'restore'
    )
    if args.annex_cmd == 'list':
        fmt = "%-32s %10s  %-18s %s"
        print(fmt % ('ID', 'SIZE', 'DATE', 'FILENAMES'))
        print(fmt % ('--', '----', '----', '---------'))
        for filename, size, mtime, names in annex.list():
            timestr = time.strftime('%x %X', time.localtime(mtime))
            print(fmt % (filename, size, timestr, ','.join(names)))

    elif args.annex_cmd == 'push':
        for srcfile in args.files:
            if Annex.is_pointer(srcfile):
                message(f"{srcfile}: already pointing to annex")
            elif is_binary(srcfile):
                annex.push(srcfile)
                message(f"{srcfile}: moved and replaced")
            else:
                message(f"{srcfile}: not binary, ignoring")

    elif args.annex_cmd == 'restore':
        for srcfile in args.files:
            if Annex.is_pointer(srcfile):
                annex.get_by_path(srcfile, srcfile)
                message(f"{srcfile}: fetched from annex")
            else:
                message(f"{srcfile}: not an annex pointer, ignoring")

    elif args.annex_cmd == 'delete':
        annex.delete(args.id)
        message(f"{args.id} has been deleted")

    elif args.annex_cmd == 'get':
        annex.get(args.id, args.dest)
        message(f"{args.dest} has been created")

    elif args.annex_cmd == 'backup':
        message("Annex backup in progress...")
        output_file = annex.backup(
            Package.list(config, staff, modules), args.output_file
        )
        message(f"Annex backup is available here: {output_file}")

def _vm_start(vm):
    if vm.running():
        message('VM is already running')
        return False

    message('Launching VM ...')
    vm.spawn()
    vm.ready()
    vm.prepare()
    return True


class BasicTest(Test):
    """
    Auto-generated test for a Package.
    Setup a test to install a package and its dependencies.
        - pkg: package to test
        - config: rift configuration
    """

    def __init__(self, pkg, config=None):
        if pkg.rpmnames:
            rpmnames = pkg.rpmnames
        else:
            rpmnames = Spec(pkg.specfile, config=config).pkgnames

        try:
            for name in pkg.ignore_rpms:
                rpmnames.remove(name)
        except ValueError as exc:
            raise RiftError(f"'{name}' is not in RPMS list") from exc

        # Avoid always processing the rpm list in the same order
        random.shuffle(rpmnames)

        cmd = textwrap.dedent(f"""
        if [ -x /usr/bin/dnf ] ; then
            YUM="dnf"
        else
            YUM="yum"
        fi
        i=0
        for pkg in {' '.join(rpmnames)}; do
            i=$(( $i + 1 ))
            echo -e "[Testing '${{pkg}}' (${{i}}/{len(rpmnames)})]"
            rm -rf /var/lib/${{YUM}}/history*
            if rpm -q --quiet $pkg; then
              ${{YUM}} -y -d1 upgrade $pkg || exit 1
            else
              ${{YUM}} -y -d1 install $pkg || exit 1
            fi
            if [ -n "$(${{YUM}} history | tail -n +3)" ]; then
                echo '> Cleanup last transaction'
                ${{YUM}} -y -d1 history undo last || exit 1
            else
                echo '> Warning: package already installed and up to date !'
            fi
        done""")
        Test.__init__(self, cmd, "basic_install")
        self.local = False

def build_pkg(config, args, pkg, arch):
    """
    Build a package for a specific architecture
      - config: rift configuration
      - pkg: package to build
      - repo: rpm repositories to use
      - suppl_repos: optional additional repositories
    """
    repos = ProjectArchRepositories(config, arch)
    if args.publish and not repos.can_publish():
        raise RiftError("Cannot publish if 'working_repo' is undefined")

    message('Preparing Mock environment...')
    mock = Mock(config, arch, config.get('version'))
    mock.init(repos.all)

    message("Building SRPM...")
    srpm = pkg.build_srpm(mock, args.sign)
    logging.info("Built: %s", srpm.filepath)

    message("Building RPMS...")
    for rpm in pkg.build_rpms(mock, srpm, args.sign):
        logging.info('Built: %s', rpm.filepath)
    message("RPMS successfully built")

    # Publish
    if args.publish:
        message("Publishing RPMS...")
        mock.publish(repos.working)

        if args.updaterepo:
            message("Updating repository...")
            repos.working.update()
    else:
        logging.info("Skipping publication")

    mock.clean()

def test_one_pkg(config, args, pkg, vm, arch, repos, results):
    """
    Launch tests on a given package on a specific VM and a set of repositories.
    """
    message(f"Preparing {arch} test environment")
    _vm_start(vm)
    if repos.working is None:
        disablestr = '--disablerepo=working'
    else:
        disablestr = ''
    vm.cmd(f"yum -y -d0 {disablestr} update")

    banner(f"Starting tests of package {pkg.name} on architecture {arch}")

    rc = 0

    tests = list(pkg.tests())
    if not args.noauto:
        tests.insert(0, BasicTest(pkg, config=config))
    for test in tests:
        case = TestCase(test.name, pkg.name, arch)
        now = time.time()
        message(f"Running test '{case.fullname}' on architecture '{arch}'")
        proc = vm.run_test(test)
        if proc.returncode == 0:
            results.add_success(case, time.time() - now, out=proc.out, err=proc.err)
            message(f"Test '{case.fullname}' on architecture {arch}: OK")
        else:
            rc = 1
            results.add_failure(case, time.time() - now, out=proc.out, err=proc.err)
            message(f"Test '{case.fullname}' on architecture {arch}: ERROR")

    if not getattr(args, 'noquit', False):
        message(f"Cleaning {arch} test environment")
        vm.cmd("poweroff")
        time.sleep(5)
        vm.stop()

    return rc

def test_pkgs(config, args, results, pkgs, arch, extra_repos=None):
    """Test a list of packages on a specific architecture."""

    if extra_repos is None:
        extra_repos = []

    vm = VM(config, arch, extra_repos=extra_repos)
    repos = ProjectArchRepositories(config, arch)

    if vm.running():
        raise RiftError('VM is already running')

    rc = 0

    for pkg in pkgs:

        now = time.time()
        try:
            spec = Spec(pkg.specfile, config=config)
        except RiftError as ex:
            # Create a dummy parse test case to report specifically the spec
            # parsing error. When parsing succeed, this test case is not
            # reported in test results.
            case = TestCase("parse", pkg.name, arch)
            logging.error("Unable to load spec file: %s", str(ex))
            results.add_failure(case, time.time() - now, err=str(ex))
            continue

        if not spec.supports_arch(arch):
            logging.info(
                "Skipping test on architecture %s not supported by "
                "package %s",
                arch,
                pkg.name
            )
            continue

        pkg.load()
        rc += test_one_pkg(config, args, pkg, vm, arch, repos, results)

    if getattr(args, 'noquit', False):
        message("Not stopping the VM. Use: rift vm connect")

    return rc

def validate_pkgs(config, args, results, pkgs, arch):
    """
    Validate packages on a specific architecture:
        - rpmlint on specfile
        - check file patterns
        - build it
        - lauch tests
    """

    repos = ProjectArchRepositories(config, arch)

    if args.publish and not repos.can_publish():
        raise RiftError("Cannot publish if 'working_repo' is undefined")

    for pkg in pkgs:

        case = TestCase('build', pkg.name, arch)
        now = time.time()

        try:
            spec = Spec(pkg.specfile, config=config)
        except RiftError as ex:
            logging.error("Unable to load spec file: %s", str(ex))
            results.add_failure(case, time.time() - now, err=str(ex))
            continue  # skip current package

        if not spec.supports_arch(arch):
            logging.info(
                "Skipping validation on architecture %s not supported by "
                "package %s",
                arch,
                pkg.name
            )
            continue

        banner(f"Checking package '{pkg.name}' on architecture {arch}")

        # Check info
        message('Validate package info...')
        pkg.load()
        pkg.check_info()

        # Check spec
        message('Validate specfile...')
        spec.check(pkg)

        (staging, stagedir) = create_staging_repo(config)

        message('Preparing Mock environment...')
        mock = Mock(config, arch, config.get('version'))
        mock.init(repos.all)

        try:
            now = time.time()
            # Check build SRPM
            message('Validate source RPM build...')
            srpm = pkg.build_srpm(mock, args.sign)

            # Check build RPMS
            message('Validate RPMS build...')
            pkg.build_rpms(mock, srpm, args.sign)
        except RiftError as ex:
            logging.error("Build failure: %s", str(ex))
            results.add_failure(case, time.time() - now, err=str(ex))
            continue  # skip current package
        else:
            results.add_success(case, time.time() - now)

        # Check tests
        mock.publish(staging)
        staging.update()

        rc = 0
        if args.test:
            rc = test_pkgs(
                config,
                args,
                results,
                [pkg],
                arch,
                [staging.consumables[arch]]
            )

        # Also publish on working repo if requested
        # XXX: All RPMs should be published when all of them have been validated
        if rc == 0 and args.publish:
            message("Publishing RPMS...")
            mock.publish(repos.working)

            message("Updating repository...")
            repos.working.update()

        if getattr(args, 'noquit', False):
            message("Keep environment, VM is running. Use: rift vm connect")
        else:
            mock.clean()
            stagedir.delete()

    banner(f"All packages checked on architecture {arch}")

def vm_build(vm, args, config):
    """Build VM image."""
    if not args.deploy and args.output is None:
        raise RiftError(
            "Either --deploy or -o,--output option must be used"
        )
    if args.deploy and args.output is not None:
        raise RiftError(
            "Both --deploy and -o,--output options cannot be used together"
        )
    if args.deploy:
        output = config.get('vm_image')
    else:
        output = args.output
    message(f"Building new vm image {output}")
    vm.build(args.url, args.force, args.keep, output)
    banner(f"New vm image {output} is ready")
    return 0

def remove_packages(config, args, pkgs_to_remove, arch):
    """
    If publish arg is enabled and working_repo is defined, remove packages
    deleted by patch that are present in this working_repo.
    """
    repos = ProjectArchRepositories(config, arch)

    if not args.publish or not repos.can_publish():
        return

    for pkg in pkgs_to_remove:
        found_pkgs = repos.working.search(pkg.name)
        for found_pkg in found_pkgs:
            repos.working.delete(found_pkg)

    # Update repository metadata
    repos.working.update()

def action_vm(args, config):
    """Action for 'vm' sub-commands."""

    ret = 1

    assert args.vm_cmd in ('connect', 'console', 'start', 'stop', 'cmd', 'copy', 'build')
    supported_archs = config.get('arch')
    if args.arch is None:
        # If --arch argument is not set and there is more than one supported
        # architecture, raise error to ask user to set the argument. If only one
        # architecture is supported, use this architecture by default.
        if len(supported_archs) > 1:
            raise RiftError(
                "VM architecture must be defined with --arch argument "
                f"(possible values: {', '.join(supported_archs)})"
            )
        args.arch = supported_archs[0]
    if args.arch not in config.get('arch'):
        raise RiftError(f"Project does not support architecture '{args.arch}'")
    vm = VM(config, args.arch)
    if args.vm_cmd == 'connect':
        ret = vm.cmd(options=None).returncode
    elif args.vm_cmd == 'console':
        ret = vm.console()
    elif args.vm_cmd == 'cmd':
        ret = vm.cmd(' '.join(args.commandline), options=None).returncode
    elif args.vm_cmd == 'copy':
        ret = vm.copy(args.source, args.dest)
    elif args.vm_cmd == 'start':
        vm.tmpmode = args.tmpimg
        if _vm_start(vm):
            message("VM started. Use: rift vm connect")
            ret = 0
    elif args.vm_cmd == 'stop':
        ret = vm.cmd('poweroff').returncode
    elif args.vm_cmd == 'build':
        ret = vm_build(vm, args, config)
    return ret

def action_build(args, config):
    """Action for 'build' command."""

    # Option --sign implies --publish.
    if args.sign:
        args.publish = True

    # Check working repo is properly defined if publish arg is used or raise
    # RiftError
    if args.publish and config.get('working_repo') is None:
        raise RiftError("Cannot publish if 'working_repo' is undefined")

    results = TestResults('build')

    staff, modules = staff_modules(config)

    # Build all packages for all project supported architectures
    for arch in config.get('arch'):

        for pkg in Package.list(config, staff, modules, args.packages):

            case = TestCase('build', pkg.name, arch)
            now = time.time()
            try:
                spec = Spec(pkg.specfile, config=config)
            except RiftError as ex:
                logging.error("Unable to load spec file: %s", str(ex))
                results.add_failure(case, time.time() - now, err=str(ex))
                continue  # skip current package

            if not spec.supports_arch(arch):
                logging.info(
                    "Skipping build on architecture %s not supported by "
                    "package %s",
                    arch,
                    pkg.name
                )
                continue

            banner(f"Building package '{pkg.name}' for architecture {arch}")
            now = time.time()
            try:
                pkg.load()
                build_pkg(config, args, pkg, arch)
            except RiftError as ex:
                logging.error("Build failure: %s", str(ex))
                results.add_failure(case, time.time() - now, err=str(ex))
            else:
                results.add_success(case, time.time() - now)

        if getattr(args, 'junit', False):
            logging.info('Writing test results in %s', args.junit)
            results.junit(args.junit)

        banner(f"All packages processed for architecture {arch}")

    banner('All architectures processed')

    if len(results) > 1:
        print(results.summary())

    if not results.global_result:
        return 2
    return 0

def action_sign(args, config):
    """Action for 'sign' command."""
    for package in args.packages:
        banner(f"Signing package {package} with GPG key")
        rpm = RPM(package, config)
        rpm.sign()
    return 0

def action_test(args, config):
    """Action for 'test' command."""
    staff, modules = staff_modules(config)
    results = TestResults('test')
    # Test package on all project supported architectures
    for arch in config.get('arch'):
        test_pkgs(
            config,
            args,
            results,
            Package.list(config, staff, modules, args.packages),
            arch
        )
    if getattr(args, 'junit', False):
        logging.info('Writing test results in %s', args.junit)
        results.junit(args.junit)

    if len(results) > 1:
        print(results.summary())

    if results.global_result:
        banner("Test suite SUCCEEDED")
        return 0
    banner("Test suite FAILED!")
    return 2

def action_validate(args, config):
    """Action for 'validate' command."""

    # Option --sign implies --publish.
    if args.sign:
        args.publish = True

    staff, modules = staff_modules(config)
    results = TestResults('validate')
    # Validate packages on all project supported architectures
    for arch in config.get('arch'):
        validate_pkgs(
            config,
            args,
            results,
            Package.list(config, staff, modules, args.packages),
            arch
        )
    banner('All packages checked on all architectures')

    if getattr(args, 'junit', False):
        logging.info('Writing test results in %s', args.junit)
        results.junit(args.junit)

    if len(results) > 1:
        print(results.summary())

    if results.global_result:
        banner("Test suite SUCCEEDED")
        return 0
    banner("Test suite FAILED!")
    return 2

def action_validdiff(args, config):
    """Action for 'validdiff' command."""

    # Option --sign implies --publish.
    if args.sign:
        args.publish = True

    staff, modules = staff_modules(config)
    # Get updated and removed packages from patch
    (updated, removed) = get_packages_from_patch(
        args.patch, config=config, modules=modules, staff=staff
    )
    results = TestResults('validate')
    # Re-validate all updated packages for all architectures supported by the
    # project.
    for arch in config.get('arch'):
        validate_pkgs(config, args, results, updated.values(), arch)


    if getattr(args, 'junit', False):
        logging.info('Writing test results in %s', args.junit)
        results.junit(args.junit)

    if len(results) > 1:
        print(results.summary())

    if results.global_result:
        rc = 0
        banner("Test suite SUCCEEDED")
    else:
        rc = 1
        banner("Test suite FAILED!")

    # Remove from working repository packages detected as removed in patch for
    # all architectures supported by the project.
    for arch in config.get('arch'):
        remove_packages(config, args, removed.values(), arch)

    return rc

def action_gerrit(args, config, staff, modules):
    """Review a patchset for Gerrit (specfiles)"""

    review = Review()

    # Parse matching diff and specfiles in it
    for patchedfile in parse_unidiff(args.patch):
        filepath = patchedfile.path
        names = filepath.split(os.path.sep)
        if names[0] == config.get('packages_dir'):
            pkg = Package(names[1], config, staff, modules)
            if filepath == pkg.specfile and not patchedfile.is_deleted_file:
                Spec(pkg.specfile, config=config).analyze(review, pkg.dir)

    # Push review
    review.msg_header = 'rpmlint analysis'
    review.push(config, args.change, args.patchset)

def action_sync(args, config):
    """Action for 'sync' command."""
    synchronized_sources = []

    # If output is set in command line arguments, use it or use sync_output
    # configuration parameter as default value.
    if args.output:
        output = args.output
    else:
        output = config.get('sync_output')
    if output is None:
        raise RiftError(
            "Synchronization output directory must be defined with "
            "sync_output parameter in Rift configuration or -o, --output "
            "command line option to synchronize repositories"
        )
    # Check output directory exists or can be created.
    output = os.path.expanduser(output)
    if not os.path.exists(output):
        try:
            os.mkdir(output)
        except FileNotFoundError as exc:
            raise RiftError(
                "Unable to create repositories synchronization directory "
                f"{output}, parent directory {os.path.dirname(output)} does "
                "not exist."
            ) from exc
    for arch in config.get('arch'):
        for name, repo in config.get('repos', default={}, arch=arch).items():
            if args.repositories and name not in args.repositories:
                logging.info(
                    "%s: Skipping repository %s not selected by user",
                    arch, name,
                )
                continue
            sync = repo.get('sync')
            if sync is None:
                logging.warning(
                        "%s: Skipping repository %s: no synchronization "
                        "parameters found", arch, name
                )
                continue
            synchronizer = RepoSyncFactory.get(config, name, output, sync)
            if synchronizer.source in synchronized_sources:
                logging.debug(
                    "Skipping already synchronized source %s",
                    synchronizer.source.geturl()
                )
                continue
            synchronized_sources.append(synchronizer.source)
            banner(
                f"{arch}: Synchronizing repository {name}: "
                f"{synchronizer.source.geturl()}"
            )
            synchronizer.run()


def get_packages_from_patch(patch, config, modules, staff):
    """
    Return 2-tuple of dicts of updated and removed packages extracted from given
    patch.
    """
    updated = {}
    removed = {}
    patchedfiles = parse_unidiff(patch)
    if not patchedfiles:
        raise RiftError("Invalid patch detected (empty commit ?)")

    for patchedfile in patchedfiles:
        modifies_packages = _validate_patched_file(
            patchedfile,
            config=config,
            modules=modules,
            staff=staff
        )
        if not modifies_packages:
            continue
        pkg = _patched_file_updated_package(
            patchedfile,
            config=config,
            modules=modules,
            staff=staff
        )
        if pkg is not None and pkg not in updated:
            logging.info('Patch updates package %s', pkg.name)
            updated[pkg.name] = pkg
        pkg = _patched_file_removed_package(
            patchedfile,
            config=config,
            modules=modules,
            staff=staff
        )
        if pkg is not None and pkg not in removed:
            logging.info('Patch deletes package %s', pkg.name)
            removed[pkg.name] = pkg

    return updated, removed

def create_staging_repo(config):
    """
    Create and return staging temporary repository with a 2-tuple containing
    (Repository, TempDir) objects.
    """
    logging.info('Creating temporary repository')
    stagedir = TempDir('stagedir')
    stagedir.create()
    staging_repo_options = {'module_hotfixes': "true"}
    staging = LocalRepository(
        path=stagedir.path,
        config=config,
        name='staging',
        options=staging_repo_options,
    )
    staging.create()
    return (staging, stagedir)

def staff_modules(config):
    """
    Return tuple with staff and modules objects.
    """
    staff = Staff(config)
    staff.load(config.get('staff_file'))

    modules = Modules(config, staff)
    modules.load(config.get('modules_file'))

    return staff, modules

def action(config, args):
    """
    Manage rift actions on annex, vm, packages or repositories
    """

    if getattr(args, 'file', None) is not None:
        args.file = os.path.abspath(args.file)

    # CHECK
    if args.command == 'check':
        action_check(args, config)
        return

    # ANNEX
    if args.command == 'annex':
        action_annex(args, config, *staff_modules(config))
        return

    # VM
    if args.command == 'vm':
        return action_vm(args, config)

    # CREATE/IMPORT/REIMPORT
    if args.command in ['create', 'import', 'reimport']:

        if args.command == 'create':
            pkgname = args.name
        elif args.command in ('import', 'reimport'):
            rpm = RPM(args.file, config)
            if not rpm.is_source:
                raise RiftError(f"{args.file} is not a source RPM")
            pkgname = rpm.name

        if args.maintainer is None:
            raise RiftError("You must specify a maintainer")

        pkg = Package(pkgname, config, *staff_modules(config))
        if args.command == 'reimport':
            pkg.load()

        if args.module:
            pkg.module = args.module
        if args.maintainer not in pkg.maintainers:
            pkg.maintainers.append(args.maintainer)
        if args.reason:
            pkg.reason = args.reason
        if args.origin:
            pkg.origin = args.origin

        pkg.check_info()
        pkg.write()

        if args.command in ('create', 'import'):
            message(f"Package '{pkg.name}' has been created")

        if args.command in ('import', 'reimport'):
            rpm.extract_srpm(pkg.dir, pkg.sourcesdir)
            message(f"Package '{pkg.name}' has been {args.command}ed")

    # BUILD
    elif args.command == 'build':
        return action_build(args, config)

    # SIGN
    elif args.command == 'sign':
        return action_sign(args, config)

    # TEST
    elif args.command == 'test':
        return action_test(args, config)

    # VALIDATE
    elif args.command == 'validate':
        return action_validate(args, config)

    # VALIDDIFF
    elif args.command == 'validdiff':
        return action_validdiff(args, config)

    elif args.command == 'query':

        staff, modules = staff_modules(config)
        pkglist = sorted(Package.list(config, staff, modules, args.packages),
                         key=attrgetter('name'))

        tbl = TextTable()
        tbl.fmt = args.fmt or '%name %module %maintainers %version %release '\
                              '%modulemanager'
        tbl.show_header = args.headers
        tbl.color = True

        supported_keys = set(('name', 'module', 'origin', 'reason', 'tests',
                              'version', 'arch', 'release', 'changelogname',
                              'changelogtime', 'maintainers', 'modulemanager',
                              'buildrequires'))
        diff_keys = set(tbl.pattern_fields()) - supported_keys
        if diff_keys:
            raise RiftError(f"Unknown placeholder(s): {', '.join(diff_keys)} "
                            f"(supported keys are: {', '.join(supported_keys)})")

        for pkg in pkglist:
            logging.debug('Loading package %s', pkg.name)
            try:
                pkg.load()
                spec = Spec(config=config)
                if args.spec:
                    spec.filepath = pkg.specfile
                    spec.load()
            except RiftError as exp:
                logging.error("%s: %s", pkg.name, str(exp))
                continue

            date = str(time.strftime("%Y-%m-%d", time.localtime(spec.changelog_time)))
            modulemanager = staff.get(modules.get(pkg.module).get('manager')[0])
            tbl.append({'name': pkg.name,
                        'module': pkg.module,
                        'origin': pkg.origin,
                        'reason': pkg.reason,
                        'tests': str(len(list(pkg.tests()))),
                        'version': spec.version,
                        'arch': spec.arch,
                        'release': spec.release,
                        'changelogname': spec.changelog_name,
                        'changelogtime': date,
                        'buildrequires': spec.buildrequires,
                        'modulemanager': modulemanager['email'],
                        'maintainers': ', '.join(pkg.maintainers)})
        print(tbl)

    elif args.command == 'changelog':

        staff, modules = staff_modules(config)
        if args.maintainer is None:
            raise RiftError("You must specify a maintainer")

        pkg = Package(args.package, config, staff, modules)
        pkg.load()

        author = f"{args.maintainer} <{staff.get(args.maintainer)['email']}>"

        # Format comment.
        # Grab bullet, insert one if not found.
        bullet = "-"
        match = re.search(r'^([^\s\w])\s', args.comment, re.UNICODE)
        if match:
            bullet = match.group(1)
        else:
            args.comment = bullet + " " + args.comment

        if args.comment.find("\n") == -1:
            wrapopts = {"subsequent_indent": (len(bullet) + 1) * " ",
                        "break_long_words": False,
                        "break_on_hyphens": False}
            args.comment = textwrap.fill(args.comment, 80, **wrapopts)

        logging.info("Adding changelog record for '%s'", author)
        Spec(pkg.specfile,
             config=config).add_changelog_entry(author, args.comment,
                                                bump=getattr(args, 'bump', False))

    # GERRIT
    elif args.command == 'gerrit':
        return action_gerrit(args, config, *staff_modules(config))

    # SYNC
    elif args.command == 'sync':
        return action_sync(args, config)

    return 0

def _validate_patched_file(patched_file, config, modules, staff):
    """
    Raise RiftError if patched_file is a binary file or does not match any known
    file path in Rift project tree.

    Return True if the patched_file modifies a package or False otherwise.
    """
    filepath = patched_file.path
    names = filepath.split(os.path.sep)

    if filepath == config.get('staff_file'):
        staff = Staff(config)
        staff.load(filepath)
        logging.info('Staff file is OK.')
        return False

    if filepath == config.get('modules_file'):
        modules = Modules(config, staff)
        modules.load(filepath)
        logging.info('Modules file is OK.')
        return False

    if filepath == 'mock.tpl':
        logging.debug('Ignoring mock template file: %s', filepath)
        return False

    if filepath == '.gitignore':
        logging.debug('Ignoring git file: %s', filepath)
        return False

    if filepath == 'project.conf':
        logging.debug('Ignoring project config file: %s', filepath)
        return False

    if patched_file.binary:
        raise RiftError(f"Binary file detected: {filepath}")

    if names[0] != config.get('packages_dir'):
        raise RiftError(f"Unknown file pattern: {filepath}")

    return True

def _patched_file_updated_package(patched_file, config, modules, staff):
    """
    Return Package updated by patched_file, or None if either:

    - The patched_file modifies a package file that does not impact package
      build result.
    - The pached_file is removed.

    Raise RiftError if patched_file path does not match any known
    packaging code file path.
    """
    filepath = patched_file.path
    names = filepath.split(os.path.sep)
    fullpath = config.project_path(filepath)
    pkg = None

    if patched_file.is_deleted_file:
        logging.debug('Ignoring removed file: %s', filepath)
        return None

    # Drop config.get('packages_dir') from list
    names.pop(0)

    pkg = Package(names.pop(0), config, staff, modules)

    # info.yaml
    if fullpath == pkg.metafile:
        logging.info('Ignoring meta file')
        return None

    # README file
    if fullpath in pkg.docfiles:
        logging.debug('Ignoring documentation file: %s', fullpath)
        return None

    # backup specfile
    if fullpath == f"{pkg.specfile}.orig":
        logging.debug('Ignoring backup specfile')
        return None

    # specfile
    if fullpath == pkg.specfile:
        logging.info('Detected spec file')

    # rpmlint config file
    elif names in [RPMLINT_CONFIG_V1, RPMLINT_CONFIG_V2]:
        logging.debug('Detecting rpmlint config file')

    # sources/
    elif fullpath.startswith(pkg.sourcesdir) and len(names) == 2:
        logging.debug('Detecting source file: %s', names[1])

    # tests/
    elif fullpath.startswith(pkg.testsdir):
        logging.debug('Detecting test script: %s', filepath)

    else:
        raise RiftError(
            f"Unknown file pattern in '{pkg.name}' directory: {filepath}"
        )

    return pkg

def _patched_file_removed_package(patched_file, config, modules, staff):
    """
    Return Package removed by the patched_file or None if patched_file does not
    remove any package.
    """
    filepath = patched_file.path
    names = filepath.split(os.path.sep)
    fullpath = config.project_path(filepath)

    if not patched_file.is_deleted_file:
        logging.debug('Ignoring not removed file: %s', filepath)
        return None

    pkg = Package(names[1], config, staff, modules)

    if fullpath == pkg.metafile:
        return pkg

    return None

def main(args=None):
    """Main code of 'rift'"""

    # Parse options
    args = make_parser().parse_args(args)

    logging.basicConfig(format="%(levelname)-8s %(message)s",
                        level=logging.WARNING - args.verbose * 10)

    try:
        # Load configuration
        config = Config()
        config.load()
        if hasattr(args, 'maintainer'):
            args.maintainer = args.maintainer or config.get('maintainer')

        # Do the job
        return action(config, args)

    except (RpmError, RiftError, IOError, OSError) as exp:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            raise
        logging.error(str(exp))
        return 1
    except KeyboardInterrupt:
        message('Keyboard interrupt. Exiting...')
        return 1

    return 0
