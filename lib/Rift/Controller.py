#
# Copyright (C) 2014 CEA
#

import argparse
import logging
import time
from rpm import error as RpmError

from Rift import RiftError
from Rift.Config import Config, Staff, Modules
from Rift.Package import Package
from Rift.RPM import RPM, Spec
from Rift.Repository import RemoteRepository, Repository
from Rift.Mock import Mock
from Rift.LookAside import LookAside

def message(msg):
    print "> %s" % msg

def banner(title):
    print "** %s **" % title

def parse_options():
    """Parse command line options"""

    parser = argparse.ArgumentParser()
    # Generic options
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="increase output verbosity (twice for debug)")

    subparsers = parser.add_subparsers(dest='command', metavar='COMMAND')

    # Create options
    parser_import = subparsers.add_parser('create',
                                          help='create a new package')
    parser_import.add_argument('name', metavar='PKGNAME',
                               help='package name to be created')
    parser_import.add_argument('-m', '--module', dest='module', required=True,
                               help='module name this package will belong to')
    parser_import.add_argument('-r', '--reason', dest='reason', required=True,
                               help='reason this package is added to project')
    parser_import.add_argument('-o', '--origin', dest='origin',
                               help='source of original package')
    parser_import.add_argument('-t', '--maintainer', dest='maintainer',
                               help='maintainer name from staff.yaml')

    # Import options
    parser_import = subparsers.add_parser('import',
                               help='import a SRPM and create a package')
    parser_import.add_argument('file', metavar='FILE',
                               help='source RPM to import')
    parser_import.add_argument('-m', '--module', dest='module', required=True,
                               help='module name this package will belong to')
    parser_import.add_argument('-r', '--reason', dest='reason', required=True,
                               help='reason this package is added to project')
    parser_import.add_argument('-o', '--origin', dest='origin',
                               help='source of original package')
    parser_import.add_argument('-t', '--maintainer', dest='maintainer',
                               help='maintainer name from staff.yaml')

    # Check options
    parser_check = subparsers.add_parser('check',
                              help='verify various config file syntaxes')
    parser_check.add_argument('type', metavar='CHKTYPE',
                              choices=['staff','modules', 'info', 'spec'],
                              help='type of check')
    parser_check.add_argument('-f', '--file', metavar='FILE',
                              help='path of file to check')

    # Build options
    parser_check = subparsers.add_parser('build',
                        help='build source RPM and RPMS')
    parser_check.add_argument('package', metavar='PACKAGE',
                        help='package name to build')
    parser_check.add_argument('-p', '--publish', action='store_true',
                        help='publish build RPMS to repository')

    # Test options
    parser_check = subparsers.add_parser('test',
                        help='execute package tests')
    parser_check.add_argument('package', metavar='PACKAGE',
                        help='package name to test')
    parser_check.add_argument('--noquit', action='store_true',
                        help='do not stop VM at the end')

    # Validate options
    parser_check = subparsers.add_parser('validate',
                              help='Fully validate package')
    parser_check.add_argument('packages', metavar='PACKAGE', nargs='+',
                              help='package name to validate')

    # XXX: Validate diff
    parser_check = subparsers.add_parser('validdiff')
    parser_check.add_argument('patch', metavar='PATCH',
                              type=argparse.FileType('r'))
    parser_check.add_argument('--noquit', action='store_true',
                               help='do not stop VM at the end')

    # LookAside options
    parser_la = subparsers.add_parser('lookaside',
                              help='Manipulate lookaside cache')
    subparsers_la = parser_la.add_subparsers(dest='la_cmd',
                              title='possible commands')
    subparsers_la.add_parser('list', help='list cache content')
    parser_la_push = subparsers_la.add_parser('push',
                                              help='move a file into cache')
    parser_la_push.add_argument('file', metavar='FILENAME',
                                help='file path to be move')
    parser_la_del = subparsers_la.add_parser('delete',
                                              help='remove a file from cache')
    parser_la_del.add_argument('id', metavar='ID',
                               help='digest ID to delete')
    parser_la_get = subparsers_la.add_parser('get',
                                              help='Copy a file from cache')
    parser_la_get.add_argument('--id', metavar='DIGEST', required=True,
                               help='digest ID to read')
    parser_la_get.add_argument('--dest', metavar='PATH', required=True,
                               help='destination path')

    # Parse options
    return parser.parse_args()

def action_check(args, config):
    """Action for 'check' sub-commands."""

    if args.type == 'staff':

        staff = Staff()
        staff.load(args.file or config.get('staff_file'))
        logging.info('Staff file is OK.')

    elif args.type == 'modules':

        staff = Staff()
        staff.load(config.get('staff_file'))
        modules = Modules(staff)
        modules.load(args.file or config.get('modules_file'))
        logging.info('Modules file is OK.')

    elif args.type == 'info':

        staff = Staff()
        staff.load(config.get('staff_file'))
        modules = Modules(staff)
        modules.load(config.get('modules_file'))

        if args.file is None:
            raise RiftError("You must specifiy a file path (-f)")

        pkg = Package("check", config, staff, modules)
        pkg.load(args.file)
        logging.info('Info file is OK.')

    elif args.type == 'spec':

        if args.file is None:
            raise RiftError("You must specifiy a file path (-f)")

        spec = Spec(args.file)
        spec.check()
        logging.info('Spec file is OK.')


def action_la(args, config):
    """Action for 'lookaside' sub-commands."""
    lookaside = LookAside(config)

    assert args.la_cmd in ('list', 'get', 'push', 'delete')
    if args.la_cmd == 'list':
        fmt = "%-32s %10s  %s"
        print fmt % ('ID', 'SIZE', 'DATE')
        print fmt % ('--', '----', '----')
        for filename, size, mtime in lookaside.list():
            timestr = time.strftime('%x %X', time.localtime(mtime))
            print fmt % (filename, size, timestr)

    elif args.la_cmd == 'push':
        lookaside.push(args.file)
        message('%s moved and replaced' % args.file)

    elif args.la_cmd == 'delete':
        lookaside.delete(args.id)
        message('%s has been deleted' % args.id)

    elif args.la_cmd == 'get':
        lookaside.get(args.id, args.dest)
        message('%s has been created' % args.dest)

def action_test(config, args, pkg, repos):
    """Process 'test' command."""

    from Rift.VM import VM
    vm = VM(config, repos)
    message("Preparing test environment")
    vm.spawn()
    vm.ready()
    vm.prepare()

    banner("Starting tests")

    from Rift.Package import Test
    cmd = "yum -d1 -y install %s && yum -d1 -y remove %s" % (pkg.name, pkg.name)
    tst = Test(cmd, "basic install")

    from Rift.TestResults import TestResults
    results = TestResults()
    tests = list(pkg.tests())
    tests.insert(0, tst)
    for test in tests:
        message("Running test '%s'" % test.name)
        if vm.run_test(test) == 0:
            results.add_success(test.name)
            message("Test '%s': OK" % test.name)
        else:
            results.add_failure(test.name)
            message("Test '%s': ERROR" % test.name)

    # XXX: Add a way to start a VM without stopping it (vm command?)
    if not getattr(args, 'noquit', False):
        vm.cmd("poweroff")
        time.sleep(5)
        vm.stop()

    if results.global_result:
        banner("Test suite SUCCEEDED")
        return 0
    else:
        banner("Test suite FAILED!")
        return 1

def action_validate(config, args, pkgs, repo):
    rcs = 0

    for pkg in pkgs:

        banner("Checking package '%s'" % pkg.name)

        # Check info
        message('Validate package info...')
        pkg.load()
        pkg.check_info()

        # Check spec
        message('Validate specfile...')
        spec = Spec(pkg.specfile)
        spec.check(pkg.dir)

        logging.info('Creating temporary repository')
        from Rift.TempDir import TempDir
        stagedir = TempDir()
        stagedir.create()
        staging = Repository(stagedir.path, 'staging')
        staging.create()

        message('Preparing Mock environment...')
        os_repo = RemoteRepository(config.get('repo_os_url'), 'os')
        mock = Mock()
        mock.init([os_repo, repo])

        # Check build SRPM
        message('Validate source RPM build...')
        srpm = pkg.build_srpm(mock)

        # Check build RPMS
        message('Validate RPMS build...')
        pkg.build_rpms(mock, srpm)

        # Check tests
        mock.publish(staging)
        staging.update()
        rc = action_test(config, args, pkg, [repo, staging])
        rcs = rcs or rc

        mock.clean()

        stagedir.delete()

    banner('All packages checked')
    return rcs

def action(config, args):

    # CHECK
    if args.command == 'check':
        action_check(args, config)
        return
    elif args.command == 'lookaside':
        action_la(args, config)
        return

    # Now, other commands..

    staff = Staff()
    staff.load(config.get('staff_file'))

    modules = Modules(staff)
    modules.load(config.get('modules_file'))

    repo = Repository(config.get('repo_base'))

    # CREATE/IMPORT
    if args.command in ['create', 'import']:

        if args.command == 'create':
            pkgname = args.name
        elif args.command == 'import':
            rpm = RPM(args.file, config)
            if not rpm.is_source:
                raise RiftError("%s is not a source RPM" % args.file)
            pkgname = rpm.name

        pkg = Package(pkgname, config, staff, modules)
        pkg.module = args.module
        pkg.maintainers = [args.maintainer]
        pkg.reason = args.reason
        pkg.origin = args.origin
        pkg.check_info()
        pkg.create()
        message("Package '%s' has been created" % pkg.name)

        if args.command == 'import':
            rpm.extract_srpm(pkg.dir, pkg.sourcesdir)
            message("Package '%s' has been imported" % pkg.name)

    # BUILD
    elif args.command == 'build':

        pkg = Package(args.package, config, staff, modules)
        pkg.load()

        os_repo = RemoteRepository(config.get('repo_os_url'), 'os')
        message('Preparing Mock environment...')
        mock = Mock()
        mock.init([os_repo, repo])

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

    # TEST
    elif args.command == 'test':

        pkg = Package(args.package, config, staff, modules)
        pkg.load()

        action_test(config, args, pkg, [repo])

    # VALIDATE
    elif args.command == 'validate':

        pkgs = [Package(pkg, config, staff, modules) for pkg in args.packages]
        return action_validate(config, args, pkgs, repo)

    elif args.command == 'validdiff':

        from unidiff import parse_unidiff

        pkglist = {}
        for patchedfile in parse_unidiff(args.patch):

            import os
            filepath = patchedfile.path
            names = filepath.split(os.path.sep)

            if filepath == config.get('staff_file'):

                staff = Staff()
                staff.load(filepath)
                logging.info('Staff file is OK.')

            elif filepath == config.get('modules_file'):

                staff = Staff()
                staff.load(config.get('staff_file'))

                modules = Modules(staff)
                modules.load(filepath)
                logging.info('Modules file is OK.')

            elif names[0] == config.get('packages_dir'):

                # Drop config.get('packages_dir') from list
                names.pop(0)

                pkg = Package(names.pop(0), config, staff, modules)
                if pkg not in pkglist:
                    # If this patch removes a file for this package,
                    # do not check it if the whole package is no more there.
                    if not patchedfile.is_deleted_file or os.path.exists(pkg.dir):
                        pkglist[pkg.name] = pkg

                # info.yaml
                if filepath == pkg.metafile:
                    logging.info('Detected meta file')

                # specfile
                elif filepath == pkg.specfile:
                    logging.info('Detected spec file')

                # backup specfile
                elif filepath == '%s.orig' % pkg.specfile:
                    logging.debug('Ignoring backup specfile')

                # sources/
                elif filepath.startswith(pkg.sourcesdir) and len(names) == 2:
                    # XXX: Check binary/no binary
                    logging.debug('Ignoring source file: %s', names[1])

                # tests/
                elif filepath.startswith(pkg.testsdir) and len(names) == 2:
                    logging.debug('Ignoring test script: %s', names[1])

                else:
                    raise RiftError("Unknown file pattern: %s" % filepath)

            elif filepath == '.gitignore':
                logging.debug('Ignoring git file: %s', filepath)

            else:
                raise RiftError("Unknown file pattern: %s" % filepath)

        # Re-validate each package
        return action_validate(config, args, pkglist.values(), repo)

    return 0

def main():
    """Main code of 'rift'"""

    # Parse options
    args = parse_options()

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

    except (RpmError, RiftError) as exp:
        logging.error(str(exp))
        return 1
    except IOError as exp:
        logging.error(str(exp))
        return 1

    return 0
