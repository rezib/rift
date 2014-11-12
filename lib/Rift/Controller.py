#
# Copyright (C) 2014 CEA
#

import argparse
import logging

from Rift import RiftError
from Rift.Config import Config, Staff, Modules
from Rift.Package import Package
from Rift.RPM import RPM, Spec
from Rift.Repository import Repository
from Rift.Mock import Mock

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
    parser_check.add_argument('package', metavar='PACKAGE',
                              help='package name to validate')

    # Parse options
    return parser.parse_args()

def action_check(args, config):

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

def action_test(config, args, pkg, repos):

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
        import time
        time.sleep(5)
        vm.stop()

    if results.global_result:
        banner("Test suite SUCCEEDED")
        return 0
    else:
        banner("Test suite FAILED!")
        return 1


def action(config, args):

    # CHECK
    if args.command == 'check':
        action_check(args, config)
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
                raise ValueError(args.file)
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

        message('Preparing Mock environment...')
        mock = Mock()
        mock.init([repo])

        message("Building SRPM...")
        srpm = pkg.build_srpm(mock)
        logging.info("Built: %s", srpm.filepath)

        message("Building RPMS...")
        pkg.build_rpms(mock, srpm)
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

        pkg = Package(args.package, config, staff, modules)

        # Check info
        message('Validate package info...')
        pkg.load()
        pkg.check_info()

        # Check spec
        message('Validate specfile...')
        spec = Spec(pkg.specfile)
        spec.check()

        logging.info('Creating temporary repository')
        from Rift.TempDir import TempDir
        stagedir = TempDir()
        stagedir.create()
        staging = Repository(stagedir.path, 'staging')
        staging.create()

        message('Preparing Mock environment...')
        mock = Mock()
        mock.init([repo])

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

        mock.clean()

        stagedir.delete()

        return rc

    return 0

def main():

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
    
    except RiftError as exp:
        logging.error(str(exp))
        return 1
    except IOError as exp:
        logging.error(str(exp))
        return 1

    return 0
