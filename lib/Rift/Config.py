#
# Copyright (C) 2014 CEA
#

import os
import yaml
import errno

from Rift import DeclError

try:
    # included in standard lib from Python 2.7
    from collections import OrderedDict
except ImportError:
    # try importing the backported drop-in replacement, it's available on PyPI
    from ordereddict import OrderedDict

# Very simplified version of
# http://stackoverflow.com/questions/5121931/in-python-how-can-you-load-yaml-mappings-as-ordereddicts
# This does not implement the matching dumper.
class OrderedLoader(yaml.SafeLoader):
    """Specific yaml SafeLoader which imports yaml mapping using OrderedDict"""

def _construct_mapping(loader, node):
    loader.flatten_mapping(node)
    return OrderedDict(loader.construct_pairs(node))

OrderedLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping)


_DEFAULT_STAFF_FILE = 'packages/staff.yaml'
_STAFF_KEYS = ['email']

_DEFAULT_MODULES_FILE = 'packages/modules.yaml'
_MODULES_KEYS = ['manager']


class Config(object):

    # XXX: Support hierarchical configuration (vm.image = ...)

    _DEFAULT_FILE = 'project.conf'

    def __init__(self):
        self.options = {
            'staff_file':    _DEFAULT_STAFF_FILE,
            'modules_file':  _DEFAULT_MODULES_FILE,
            'packages_dir':  'packages',
            # 'annex'
            # 'repo_os_url'
            # 'repo_base'
            'repos':         {},
            # 'maintainer'
            'qemu':          'qemu-system-x86_64',
            # 'vm_image'
            # 'vm_port'
            'vm_address':    '10.0.2.15',

            # XXX?: 'mock.name' ?
            # XXX?: 'mock.template' ?
            # XXX?: default vm_image ?
            }

    def get(self, option, default=None):
        return self.options.get(option, default)

    def load(self, filepath=None):
        if filepath is None:
            filepath = self._DEFAULT_FILE

        if not os.path.exists(filepath):
            return

        try:
            with open(filepath) as fyaml:
                data = yaml.load(fyaml, Loader=OrderedLoader)

            self.options.update(data)

        except yaml.error.YAMLError as exp:
            raise DeclError(str(exp))


class Staff(object):
    """
    List of staff members of a rift project.

    This class helps loading and checking the underlying yaml file content.
    """

    def __init__(self):
        self.people = {}

    def load(self, filepath=None):
        """
        Load yaml file content.
        
        If filepath is not defined, the default file path for staff.yaml is
        used.
        """
        if filepath is None:
            filepath = _DEFAULT_STAFF_FILE

        try:
            with open(filepath) as fyaml:
                data = yaml.load(fyaml)

            self.people = data.pop('staff') or {}

            self._check()
        
        except AttributeError as exp:
            raise DeclError("Bad data format in staff file")
        except KeyError as exp:
            raise DeclError("Missing %s at top level in staff file" % exp)
        except yaml.error.YAMLError as exp:
            raise DeclError(str(exp))
        except IOError as exp:
            if exp.errno == errno.ENOENT:
                raise DeclError("Could not find '%s'" % filepath)
            else:
                raise DeclError(str(exp))

    def _check(self):
        """
        Verify staff declaration is correct. 
        
        No missing element, no unnecessary one.
        """
        if not self.people:
            return

        for people, data in self.people.items():
            # Missing elements
            missing = set(_STAFF_KEYS) - set(data.keys())
            if missing:
                items = ', '.join(["'%s'" % item for item in missing])
                raise DeclError("Missing %s item(s) for %s" % (items, people))

            # Unnecessary elements
            not_needed = set(data.keys()) - set(_STAFF_KEYS)
            if not_needed:
                items = ', '.join(["'%s'" % item for item in not_needed])
                raise DeclError("Unknown %s item(s) for %s" % (items, people))

#
# XXX: Factorize with Staff later
#

class Modules(object):
    """
    List of project modules.

    This class helps loading and checking the underlying yaml file content.
    """

    def __init__(self, staff):
        self.staff = staff
        self.modules = {}

    def load(self, filepath=None):
        """
        Load yaml file content.
        
        If filepath is not defined, the default file path for modules.yaml is
        used.
        """
        if filepath is None:
            filepath = _DEFAULT_MODULES_FILE

        try:
            with open(filepath) as fyaml:
                data = yaml.load(fyaml)

            self.modules = data.pop('modules') or {}

            self._check()
        
        except AttributeError as exp:
            raise DeclError("Bad data format in modules file")
        except KeyError as exp:
            raise DeclError("Missing %s at top level in modules file" % exp)
        except yaml.error.YAMLError as exp:
            raise DeclError(str(exp))
        except IOError as exp:
            if exp.errno == errno.ENOENT:
                raise DeclError("Could not find '%s'" % filepath)
            else:
                raise DeclError(str(exp))

    def _check(self):
        """
        Verify modules declaration is correct.
        
        No missing element, no unnecessary one.
        """
        if not self.modules:
            return

        for modules, data in self.modules.items():
            # Missing elements
            missing = set(_MODULES_KEYS) - set(data.keys())
            if missing:
                items = ', '.join(["'%s'" % item for item in missing])
                raise DeclError("Missing %s item(s) for %s" % (items, modules))

            # Unnecessary elements
            not_needed = set(data.keys()) - set(_MODULES_KEYS)
            if not_needed:
                items = ', '.join(["'%s'" % item for item in not_needed])
                raise DeclError("Unknown %s item(s) for %s" % (items, modules))

            # Maintainer exists
            if type(data['manager']) is str:
                data['manager'] = [ data['manager'] ]
            for mngr in data['manager']:
                if mngr not in self.staff.people:
                    msg = "Manager '%s' does not exist in staff list" % mngr
                    raise DeclError(msg)
            
