#
# Copyright (C) 2014-2018 CEA
#

"""
Helper module to write unit tests for Rift project.
It contains several helper methods or classes like temporary file management.
"""

import tempfile
import unittest

class RiftTestCase(unittest.TestCase):
    """unittest.TestCase subclass with additional features"""

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

#
# Temp files
#
def make_temp_dir():
    """Create and return the name of a temporary directory."""
    return tempfile.mkdtemp(prefix='rift-test-')

def make_temp_filename():
    """Return a temporary name for a file."""
    return (tempfile.mkstemp(prefix='rift-test-'))[1]

def make_temp_file(text):
    """ Create a temporary file with the provided text."""
    tmp = tempfile.NamedTemporaryFile(prefix='rift-test-')
    tmp.write(text.encode())
    tmp.flush()
    return tmp
