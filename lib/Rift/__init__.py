#
# Copyright (C) 2014 CEA
#

class RiftError(Exception):
    """Generic error in Rift"""

class DeclError(RiftError):
    """A configuration file has a declaration error"""

