#
# Copyright (C) 2014-2019 CEA
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
import subprocess
import time
import textwrap
from rpm import error as RpmError
from unidiff import parse_unidiff

from rift import RiftError, __version__
from rift.Annex import Annex, is_binary
from rift.Config import Config, Staff, Modules
from rift.Gerrit import Review
from rift.Mock import Mock
from rift.Package import Package, Test
from rift.Repository import RemoteRepository, Repository
from rift.RPM import RPM, Spec, RPMLINT_CONFIG
from rift.TempDir import TempDir
from rift.TestResults import TestResults
from rift.TextTable import TextTable
from rift.VM import VM


def message(msg):
    """
    helper function to print a log message
    """
    print("> %s" % msg)

def banner(title):
    """
    helper function to print a banner
    """
    print("** %s **" % title)

def parse_options(args=None):
    """Parse command line options"""

    parser = argparse.ArgumentParser()
    # Generic options
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="increase output verbosity (twice for debug)")
    parser.add_argument('--version', action='version',
                        version='%%(prog)s %s' % __version__)

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
    subprs.add_argument('--junit', metavar='FILENAME',
                        help='write junit result file')

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
    subprs.add_argument('--noquit', action='store_true',
                        help='do not stop VM at the end')
    subprs.add_argument('--noauto', action='store_true',
                        help='do not run auto tests')
    subprs.add_argument('-p', '--publish', action='store_true',
                        help='publish build RPMS to repository')

    # XXX: Validate diff
    subprs = subparsers.add_parser('validdiff')
    subprs.add_argument('patch', metavar='PATCH', type=argparse.FileType('r'))
    subprs.add_argument('--noquit', action='store_true',
                        help='do not stop VM at the end')
    subprs.add_argument('--noauto', action='store_true',
                        help='do not run auto tests')
    subprs.add_argument('-p', '--publish', action='store_true',
                        help='publish build RPMS to repository')

    # Annex options
    subprs = subparsers.add_parser('annex', help='Manipulate annex cache')

    subprs_annex = subprs.add_subparsers(dest='annex_cmd',
                                         title='possible commands')
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

    # Parse options
    return parser.parse_args(args)

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


def action_annex(args, config):
    """Action for 'annex' sub-commands."""
    annex = Annex(config)

    assert args.annex_cmd in ('list', 'get', 'push', 'delete', 'restore')
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
                message('%s: already pointing to annex' % srcfile)
            elif is_binary(srcfile):
                annex.push(srcfile)
                message('%s: moved and replaced' % srcfile)
            else:
                message('%s: not binary, ignoring' % srcfile)

    elif args.annex_cmd == 'restore':
        for srcfile in args.files:
            if Annex.is_pointer(srcfile):
                annex.get_by_path(srcfile, srcfile)
                message('%s: fetched from annex' % srcfile)
            else:
                message('%s: not an annex pointer, ignoring' % srcfile)

    elif args.annex_cmd == 'delete':
        annex.delete(args.id)
        message('%s has been deleted' % args.id)

    elif args.annex_cmd == 'get':
        annex.get(args.id, args.dest)
        message('%s has been created' % args.dest)


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
        except ValueError:
            raise RiftError("'%s' is not in RPMS list" % name)

        # Avoid always processing the rpm list in the same order
        random.shuffle(rpmnames)

        cmd = textwrap.dedent("""
        if [ -x /usr/bin/dnf ] ; then
            YUM="dnf"
        else
            YUM="yum"
        fi
        i=0
        for pkg in %s; do
            i=$(( $i + 1 ))
            echo -e "[Testing '${pkg}' (${i}/%d)]"
            rm -rf /var/lib/${YUM}/history*
            if rpm -q --quiet $pkg; then
              ${YUM} -y -d1 upgrade $pkg || exit 1
            else
              ${YUM} -y -d1 install $pkg || exit 1
            fi
            if [ -z "$(${YUM} history 2<&1| awk '/No transactions/')" ]; then
                echo '> Cleanup last transaction'
                ${YUM} -y -d1 history undo last || exit 1
            else
                echo '> Warning: package already installed and up to date !'
            fi
        done""" % (' '.join(rpmnames), len(rpmnames)))
        Test.__init__(self, cmd, "basic_install")
        self.local = False

def action_build(config, args, pkg, repo, suppl_repos):
    """
    Build a package
      - config: rift configuration
      - pkg: package to build
      - repo: rpm repositories to use
      - suppl_repos: optional additional repositories
    """

    message('Preparing Mock environment...')
    mock = Mock(config, config.get('version'))
    if repo:
        suppl_repos = suppl_repos + [repo]
    mock.init(suppl_repos)

    message("Building SRPM...")
    srpm = pkg.build_srpm(mock)
    logging.info("Built: %s", srpm.filepath)

    message("Building RPMS...")
    for rpm in pkg.build_rpms(mock, srpm):
        logging.info('Built: %s', rpm.filepath)
    message("RPMS successfully built")

    # Publish
    if args.publish:
        message("Publishing RPMS...")
        mock.publish(repo)

        message("Updating repository...")
        repo.update()
    else:
        logging.info("Skipping publication")

    mock.clean()

def action_test_one(args, pkg, vm, results, disable, config=None):
    """
    Launch tests on given packages
    """
    message("Preparing test environment")
    _vm_start(vm)
    if disable:
        disablestr = '--disablerepo=working'
    else:
        disablestr = ''
    vm.cmd('yum -y -d0 %s update' % disablestr)

    banner("Starting tests")

    tests = list(pkg.tests())
    if not args.noauto:
        tests.insert(0, BasicTest(pkg, config=config))
    for test in tests:
        testname = '%s.%s' % (pkg.name, test.name)
        now = time.time()
        message("Running test '%s'" % testname)
        if vm.run_test(test) == 0:
            results.add_success(test.name, pkg.name, time.time() - now)
            message("Test '%s': OK" % testname)
        else:
            results.add_failure(test.name, pkg.name, time.time() - now)
            message("Test '%s': ERROR" % testname)

    if not getattr(args, 'noquit', False):
        message("Cleaning test environment")
        vm.cmd("poweroff")
        time.sleep(5)
        vm.stop()


def action_test(config, args, pkgs, repos, disable=False):
    """Process 'test' command."""

    results = TestResults('test')
    vm = VM(config, repos)
    if vm.running():
        message('VM is already running')
        return 1

    for pkg in pkgs:
        pkg.load()
        action_test_one(args, pkg, vm, results, disable, config=config)

    if getattr(args, 'noquit', False):
        message("Not stopping the VM. Use: rift vm connect")

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

def action_validate(config, args, pkgs, wkrepo, suppl_repos):
    """
    Validate a package:
        - rpmlint on specfile
        - check file patterns
        - build it
        - lauch tests
    """
    if args.publish and not wkrepo:
        raise RiftError("Cannot publish if 'working_repo' is undefined")

    if wkrepo:
        suppl_repos.append(wkrepo)

    rc = 0
    for pkg in pkgs:

        banner("Checking package '%s'" % pkg.name)

        # Check info
        message('Validate package info...')
        pkg.load()
        pkg.check_info()

        # Check spec
        message('Validate specfile...')
        spec = Spec(pkg.specfile, config=config)
        spec.check(pkg.dir)

        if spec.basename != pkg.name:
            msg = "name '%s' does not match '%s' in spec file" % (pkg.name, spec.basename)
            raise RiftError(msg)

        # Changelog section is mandatory
        if not (spec.changelog_name or spec.changelog_time):
            raise RiftError('Proper changelog section is needed in specfile')

        # This should be more generic and moved into rift.Package/rift.RPM
        if pkg.sources - set(spec.sources):
            msg = "Unused source file(s): %s" % ' '.join(pkg.sources - set(spec.sources))
            raise RiftError(msg)
        if set(spec.sources) - pkg.sources:
            msg = "Missing source file(s): %s" % ' '.join(set(spec.sources) - pkg.sources)
            raise RiftError(msg)

        logging.info('Creating temporary repository')
        stagedir = TempDir('stagedir')
        stagedir.create()
        staging = Repository(stagedir.path, config.get('arch'), 'staging')
        staging.create()

        message('Preparing Mock environment...')
        mock = Mock(config, config.get('version'))
        mock.init(suppl_repos)

        # Check build SRPM
        message('Validate source RPM build...')
        srpm = pkg.build_srpm(mock)

        # Check build RPMS
        message('Validate RPMS build...')
        pkg.build_rpms(mock, srpm)

        # Check tests
        mock.publish(staging)
        staging.update()
        rc = action_test(config, args, [pkg], suppl_repos + [staging],
                         wkrepo is not None) or rc

        # Also publish on working repo if requested
        # XXX: All RPMs should be published when all of them have been validated
        if rc == 0 and args.publish:
            message("Publishing RPMS...")
            mock.publish(wkrepo)

            message("Updating repository...")
            wkrepo.update()

        if getattr(args, 'noquit', False):
            message("Keep environment, VM is running. Use: rift vm connect")
        else:
            mock.clean()
            stagedir.delete()

    banner('All packages checked')
    return rc

def action_vm(config, args, repos):
    """Action for 'vm' sub-commands."""

    vm = VM(config, repos)
    ret = 1

    assert args.vm_cmd in ('connect', 'console', 'start', 'stop', 'cmd', 'copy')
    if args.vm_cmd == 'connect':
        ret = vm.cmd(options=None)
    elif args.vm_cmd == 'console':
        ret = vm.console()
    elif args.vm_cmd == 'cmd':
        ret = vm.cmd(' '.join(args.commandline), options=None)
    elif args.vm_cmd == 'copy':
        ret = vm.copy(args.source, args.dest)
    elif args.vm_cmd == 'start':
        vm.tmpmode = args.tmpimg
        if _vm_start(vm):
            message("VM started. Use: rift vm connect")
            ret = 0
    elif args.vm_cmd == 'stop':
        ret = vm.cmd('poweroff')
    return ret

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
        action_annex(args, config)
        return

    # Repo objects
    if config.get('working_repo'):
        repo = Repository(config.get('working_repo'), config.get('arch'), 'working')
        repos = [repo]
    else:
        repo = None
        repos = []
    suppl_repos = []
    for name, data in config.get('repos').items():
        if isinstance(data, str):
            suppl_repos.append(RemoteRepository(data, name))
        else:
            remote = RemoteRepository(data['url'], name, data.get('priority'))
            suppl_repos.append(remote)

    # VM
    if args.command == 'vm':
        return action_vm(config, args, suppl_repos + repos)

    # Now, package related commands..

    staff = Staff(config)
    staff.load(config.get('staff_file'))

    modules = Modules(config, staff)
    modules.load(config.get('modules_file'))

    # CREATE/IMPORT/REIMPORT
    if args.command in ['create', 'import', 'reimport']:

        if args.command == 'create':
            pkgname = args.name
        elif args.command in ('import', 'reimport'):
            rpm = RPM(args.file, config)
            if not rpm.is_source:
                raise RiftError("%s is not a source RPM" % args.file)
            pkgname = rpm.name

        if args.maintainer is None:
            raise RiftError("You must specify a maintainer")

        pkg = Package(pkgname, config, staff, modules)
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
            message("Package '%s' has been created" % pkg.name)

        if args.command in ('import', 'reimport'):
            rpm.extract_srpm(pkg.dir, pkg.sourcesdir)
            message("Package '%s' has been %sed" % (pkg.name, args.command))

    # BUILD
    elif args.command == 'build':

        if args.publish and not repo:
            raise RiftError("Cannot publish if 'working_repo' is undefined")

        results = TestResults('build')

        for pkg in Package.list(config, staff, modules, args.packages):
            banner("Building package '%s'" % pkg.name)

            pkg.load()
            now = time.time()
            try:
                action_build(config, args, pkg, repo, suppl_repos)
            except RiftError as ex:
                results.add_failure('build', pkg.name, time.time() - now, str(ex))
            else:
                results.add_success('build', pkg.name, time.time() - now)

        if getattr(args, 'junit', False):
            logging.info('Writing test results in %s', args.junit)
            results.junit(args.junit)

        banner('All packages processed')

        if len(results) > 1:
            print(results.summary())

        if results.global_result:
            return 0
        return 2

    # TEST
    elif args.command == 'test':

        pkgs = Package.list(config, staff, modules, args.packages)
        return action_test(config, args, pkgs, suppl_repos + repos,
                           repo is not None)

    # VALIDATE
    elif args.command == 'validate':

        pkgs = Package.list(config, staff, modules, args.packages)
        return action_validate(config, args, pkgs, repo, suppl_repos)

    elif args.command == 'validdiff':

        pkglist = {}
        patchedfiles = parse_unidiff(args.patch)

        if not patchedfiles:
            raise RiftError("Invalid patch detected (empty commit ?)")

        for patchedfile in patchedfiles:

            filepath = patchedfile.path
            names = filepath.split(os.path.sep)
            fullpath = config.project_path(filepath)
            ignored = False

            if filepath == config.get('staff_file'):

                staff = Staff(config)
                staff.load(filepath)
                logging.info('Staff file is OK.')

            elif filepath == config.get('modules_file'):

                staff = Staff(config)
                staff.load(config.get('staff_file'))

                modules = Modules(config, staff)
                modules.load(filepath)
                logging.info('Modules file is OK.')

            elif names[0] == config.get('packages_dir'):

                # Drop config.get('packages_dir') from list
                names.pop(0)

                pkg = Package(names.pop(0), config, staff, modules)

                if patchedfile.is_deleted_file:
                    logging.debug('Ignoring removed file: %s', filepath)
                    ignored = True

                # info.yaml
                if fullpath == pkg.metafile:
                    logging.info('Ignoring meta file')
                    ignored = True

                # specfile
                elif fullpath == pkg.specfile:
                    logging.info('Detected spec file')

                # backup specfile
                elif fullpath == '%s.orig' % pkg.specfile:
                    logging.debug('Ignoring backup specfile')
                    ignored = True

                # rpmlint config file
                elif names == [RPMLINT_CONFIG]:
                    logging.debug('Detecting rpmlint config file')

                # README file
                elif fullpath in pkg.docfiles:
                    logging.debug('Ignoring documentation file: %s', fullpath)
                    ignored = True

                # sources/
                elif fullpath.startswith(pkg.sourcesdir) and len(names) == 2:
                    if not ignored and patchedfile.binary:
                        raise RiftError("Binary file detected: %s" % filepath)
                    logging.debug('Detecting source file: %s', names[1])

                # tests/
                elif fullpath.startswith(pkg.testsdir) and len(names) == 2:
                    logging.debug('Detecting test script: %s', names[1])

                else:
                    raise RiftError("Unknown file pattern: %s" % filepath)

                if pkg not in pkglist:
                    # Do not check if:
                    # * this patch removes a file for this package and the
                    #   whole package is no more there.
                    # * this patch only modify a file that doesn't need a build (like spec.orig)
                    if not ignored and os.path.exists(pkg.dir):
                        pkglist[pkg.name] = pkg

            elif filepath == 'mock.tpl':
                logging.debug('Ignoring mock template file: %s', filepath)

            elif filepath == '.gitignore':
                logging.debug('Ignoring git file: %s', filepath)

            elif filepath == 'project.conf':
                logging.debug('Ignoring project config file: %s', filepath)

            elif patchedfile.is_deleted_file:
                logging.debug('Ignoring removed file: %s', filepath)

            else:
                raise RiftError("Unknown file pattern: %s" % filepath)

        # Re-validate each package
        return action_validate(config, args, pkglist.values(), repo, suppl_repos)

    elif args.command == 'query':


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
            raise RiftError('Unknown placeholder(s): %s '\
                            '(supported keys are: %s)' % (', '.join(diff_keys),
                                                          ', '.join(supported_keys)))

        for pkg in pkglist:
            logging.debug('Loading package %s', pkg.name)
            pkg.load()
            spec = Spec(config=config)
            if args.spec:
                spec.filepath = pkg.specfile
                try:
                    spec.load()
                except RiftError as exp:
                    logging.error(str(exp))
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

        if args.maintainer is None:
            raise RiftError("You must specify a maintainer")

        pkg = Package(args.package, config, staff, modules)
        pkg.load()

        author = '%s <%s>' % (args.maintainer, staff.get(args.maintainer)['email'])

        if getattr(args, 'bump', False):
            cmd = "rpmdev-bumpspec -u '%s' -c '%s' %s" % \
                  (author, args.comment, pkg.specfile)

            popen = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)
            stdout = popen.communicate()[0]
            if popen.returncode != 0:
                raise RiftError(stdout)

        else:

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
                 config=config).add_changelog_entry(author, args.comment)

    # GERRIT
    elif args.command == 'gerrit':
        return action_gerrit(args, config, staff, modules)

    return 0

def main(args=None):
    """Main code of 'rift'"""

    # Parse options
    args = parse_options(args)

    logging.basicConfig(format="%(levelname)-8s %(message)s",
                        level=(logging.WARNING - args.verbose * 10))

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
