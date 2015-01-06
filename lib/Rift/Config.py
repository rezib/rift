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
_DEFAULT_MODULES_FILE = 'packages/modules.yaml'

class Config(object):

    # XXX: Support hierarchical configuration (vm.image = ...)

    _DEFAULT_FILES = ['project.conf', 'local.conf']
    ALLOW_MISSING  = True

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

    def get_project_dir(self, filenames=None):
        """
        Look for project base directory looking for configuration filenames.

        It will recursively look for name from filenames, starting from
        name directory and going up if file is not found.

        If found, it returns a tuple for the matching file directory and file
        name, if never found, it returns (None, None).
        """
        if filenames is None:
            filenames = self._DEFAULT_FILES
        if isinstance(filenames, basestring):
            filenames = [filenames]

        for filepath in filenames:
            filepath = os.path.abspath(filepath)
            dirname, filename = os.path.split(filepath)
            if os.path.exists(filepath):
                return dirname, filename

            while dirname != '/':
                dirname = os.path.split(dirname)[0]
                filepath = os.path.join(dirname, filename)
                if os.path.exists(filepath):
                    return dirname, filename

        return None, None

    def get(self, option, default=None):
        if option in self.options:
            return self.options[option]
        elif option in self.SYNTAX:
            return self.SYNTAX[option].get('default', default)
        else:
            return default

    def load(self, filenames=None):
        """
        Read and parse the list of named configuration files, given by name. A
        single filename is also allowed. Non-existing files are ignored.

        If filenames is not omited, self._DEFAULT_FILES is used.
        """
        if filenames is None:
            filenames = self._DEFAULT_FILES
        if isinstance(filenames, basestring):
            filenames = [filenames]

        for filepath in filenames:
            try:
                filedir, filename = self.get_project_dir(filepath)
                if filedir and filename:
                    filepath = os.path.join(filedir, filename)

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

    DEFAULT_PATH = _DEFAULT_STAFF_FILE
    DATA_NAME    = 'staff'
    ITEMS_HEADER = 'staff'
    ITEMS_KEYS   = ['email']

    def __init__(self):
        self._data = {}

    def __contains__(self, item):
        return item in self._data

    def load(self, filepath=None):
        """
        Load yaml file content.
        
        If filepath is not defined, the default file path is used.
        """
        if filepath is None:
            filepath = self.DEFAULT_PATH

        try:
            with open(filepath) as fyaml:
                data = yaml.load(fyaml)

            self._data = data.pop(self.ITEMS_HEADER) or {}

            self._check()
        
        except AttributeError as exp:
            raise DeclError("Bad data format in %s file" % self.DATA_NAME)
        except KeyError as exp:
            raise DeclError("Missing %s at top level in %s file" %
                            (exp, self.DATA_NAME))
        except yaml.error.YAMLError as exp:
            raise DeclError(str(exp))
        except IOError as exp:
            if exp.errno == errno.ENOENT:
                raise DeclError("Could not find '%s'" % filepath)
            else:
                raise DeclError(str(exp))

    def _check(self):
        """
        Verify declaration is correct.
        
        No missing element, no unnecessary one.
        """
        for people, data in self._data.items():
            # Missing elements
            missing = set(self.ITEMS_KEYS) - set(data.keys())
            if missing:
                items = ', '.join(["'%s'" % item for item in missing])
                raise DeclError("Missing %s item(s) for %s" % (items, people))

            # Unnecessary elements
            not_needed = set(data.keys()) - set(self.ITEMS_KEYS)
            if not_needed:
                items = ', '.join(["'%s'" % item for item in not_needed])
                raise DeclError("Unknown %s item(s) for %s" % (items, people))


class Modules(Staff):
    """
    List of project modules.

    This class helps loading and checking the underlying yaml file content.
    """

    DEFAULT_PATH = _DEFAULT_MODULES_FILE
    DATA_NAME    = 'modules'
    ITEMS_HEADER = 'modules'
    ITEMS_KEYS   = ['manager']

    def __init__(self, staff):
        Staff.__init__(self)
        self.staff = staff

    def _check(self):
        """
        Verify modules declaration is correct.
        
        No missing element, no unnecessary one.
        """
        Staff._check(self)

        for module in self._data.values():
            # Maintainer exists
            if type(module['manager']) is str:
                module['manager'] = [ module['manager'] ]
            for mngr in module['manager']:
                if mngr not in self.staff:
                    msg = "Manager '%s' does not exist in staff list" % mngr
                    raise DeclError(msg)
