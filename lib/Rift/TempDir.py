#
# Copyright (C) 2014 CEA
#

"""
Help working with temporary directories.
"""

import shutil
import logging
import tempfile

class TempDir(object):
    """
    Create and manipulate a temporary directory.
    
    `object.path' points to the created directory.
    `object.name' is used for dir prefix and messages.
    """

    def __init__(self, name=None):
        self.name = name
        self.path = None

    def create(self):
        """Create a unique temporary directory."""
        prefix = 'rift-' + (self.name and '%s-' % self.name or '')
        self.path = tempfile.mkdtemp(prefix=prefix)
        name = self.name and ' %s' % self.name or ''
        logging.debug('Creating%s temporary directory %s', name, self.path)

    def delete(self):
        """Recursively delete the temporary directory."""
        if self.path:
            name = self.name and ' %s' % self.name or ''
            logging.debug('Deleting%s temporary directory %s', name, self.path)
            shutil.rmtree(self.path)
            self.path = None

    def __del__(self):
        self.delete()
