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
    """

    def __init__(self):
        self.path = None

    def create(self):
        """Create a unique temporary directory."""
        self.path = tempfile.mkdtemp(prefix='rift-')
        logging.debug('Creating temporary directory %s', self.path)

    def delete(self):
        """Recursively delete the temporary directory."""
        if self.path:
            logging.debug('Deleting temporary directory %s', self.path)
            shutil.rmtree(self.path)
