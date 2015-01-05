#
# Copyright (C) 2014-2016 CEA
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
    ALLOW_MISSING = False

    SYNTAX = {
        'staff_file': {
            'default':   _DEFAULT_STAFF_FILE,
        },
        'modules_file': {
            'default':   _DEFAULT_MODULES_FILE,
        },
        'packages_dir': {
            'default':  'packages',
        },
        'annex': {
            'required': True,
        },
        'repo_os_url': { },
        'working_repo': {
            'required': True,
        },
        'repos': {
            'check':    'dict',
        },
        'arch': {
            'default':  'x86_64',
        },
        'maintainer':  { },
        'qemu': {
            'default':  'qemu-system-x86_64',
        },
        'vm_image':    {
            'required': True,
            # XXX?: default value?
        },
        'vm_port': {
            'check':    'digit',
        },
        'vm_address': {
            'default':  '10.0.2.15',
        },
        # XXX?: 'mock.name' ?
        # XXX?: 'mock.template' ?
    }

    def __init__(self):
        self.options = { }

    def _find_root_dir(self, filepath=None):
        """
        Look for project base directory using main configuration file.

        It will recursively look for filename from `filepath', starting from
        directory from `filepath' and going up if file is not found.

        If found, it returns the matching filepath, if never found, it returns
        None.
        """
        filepath = os.path.realpath(filepath or self._DEFAULT_FILE)

        dirname, filename = os.path.split(filepath)
        if os.path.exists(filepath):
            return filepath

        while dirname != '/':
            dirname = os.path.split(dirname)[0]
            filepath = os.path.join(dirname, filename)
            if os.path.exists(filepath):
                return filepath

        return None

    def get(self, option, default=None):
        if option in self.options:
            return self.options[option]
        elif option in self.SYNTAX:
            return self.SYNTAX[option].get('default', default)
        else:
            return default

    def load(self, filepath=None):
        """
        Load yaml file content.

        If filepath is not defined, the _DEFAULT_FILE is used.
        """
        if filepath is None:
            filepath = self._DEFAULT_FILE

        filepath = self._find_root_dir(filepath) or filepath

        try:
            with open(filepath) as fyaml:
                data = yaml.load(fyaml, Loader=OrderedLoader)

            self.update(data)

        except yaml.error.YAMLError as exp:
            raise DeclError(str(exp))
        except IOError as exp:
            if exp.errno == errno.ENOENT:
                if not self.ALLOW_MISSING:
                    raise DeclError("Could not find '%s'" % filepath)
            else:
                raise DeclError(str(exp))

        self._check()

    def set(self, key, value):

        # Key is known
        if key not in self.SYNTAX:
            raise DeclError("Unknown '%s' key" % key)

        # Check type
        check = self.SYNTAX[key].get('check', 'string')
        assert check in ('string', 'dict', 'digit')
        if check == 'string':
            if not isinstance(value, str):
                raise DeclError("Bad data type for '%s'" % key)
            self.options[key] = str(value)
        elif check == 'dict':
            if not isinstance(value, dict):
                raise DeclError("Bad data type for '%s'" % key)
            self.options[key] = value
        elif check == 'digit':
            if not isinstance(value, int):
                raise DeclError("Bad data type for '%s'" % key)
            self.options[key] = int(value)


    def update(self, data):
        """
        Update config content with data dict, checking data content respect
        SYNTAX spec.
        """
        for key, value in data.items():
            self.set(key, value)

    def _check(self):
        """Checks for mandatory options."""
        for key in self.SYNTAX:
            if self.SYNTAX[key].get('required', False) and \
               not 'default' in self.SYNTAX[key]:
                if key not in self.options:
                    raise DeclError("'%s' is not defined" % key)


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
            
