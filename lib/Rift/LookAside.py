#
# Copyright (C) 2014 CEA
#

"""
Class and function to detect binary files and push them into a file repository
called a lookaside.
"""

import os
import string
import shutil
import hashlib
import logging

from Rift.TempDir import TempDir

# List of ASCII printable characters
_TEXTCHARS = bytearray([9, 10, 13] + range(32, 127))

def is_binary(filepath, blocksize=65536):
    """
    Look for non printable characters in the first blocksize bytes of filepath.

    Note it only looks for the first bytes. If binary data appeared farther in
    that file, it will be wrongly detected as a non-binary one.
    """
    with open(filepath, 'rb') as srcfile:
        data = srcfile.read(blocksize)
        result = bool(data.translate(None, _TEXTCHARS))
    return result

def hashfile(filepath, iosize=65536):
    """Compute a digest of filepath content."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as srcfile:
        buf = srcfile.read(iosize)
        while len(buf) > 0:
            hasher.update(buf)
            buf = srcfile.read(iosize)
    return hasher.hexdigest()


class LookAside(object):
    """
    Repository of binary files.

    It simply adds and removes binary files addressed by their digest.
    When importing files, they are replaced by 'pointer files' containing
    only a digest or original file content.

    For now, files are stored in a flat namespace.
    """

    def __init__(self, config, path=None):
        self.path = path or config.get('lookaside')

    @classmethod
    def is_pointer(cls, filepath):
        """
        Return true if content of file at filepath looks like a valid digest
        identifier.
        """
        meta = os.stat(filepath)
        if meta.st_size == 32:
            identifier = open(filepath).read(32)
            return all(byte in string.hexdigits for byte in identifier)
        return False

    def get(self, idpath, destpath):
        """Get a file identified by idpath content, and copy it at destpath."""
        # Copy file from repository to destination path
        identifier = open(idpath).read()
        idpath = os.path.join(self.path, identifier)
        logging.debug('Extracting %s to %s', identifier, destpath)
        shutil.copyfile(idpath, destpath)

    def import_dir(self, dirpath):
        """
        Look for identifier files in `dirpath' directory and setup a usable
        directory.

        It returns a TempDir instance.
        If `dirpath' does not contain any identifier file, this temporary
        directory is not created.

        If it does, this temporary directory is created and text files from
        dirpath and identified ones are copied into it. It is caller
        responsability to delete it when it does not need it anymore.
        """
        tmpdir = TempDir()
        textfiles = []
        for filename in os.listdir(dirpath):
            filepath = os.path.join(dirpath, filename)

            # Is a pointer to a binary file?
            if self.is_pointer(filepath):

                # We have our first binary file, we need a temp directory
                if tmpdir.path is None:
                    tmpdir.create()
                    for filepath in textfiles:
                        shutil.copy(filepath, tmpdir.path)

                # Copy the real binary content
                self.get(filepath, os.path.join(tmpdir.path, filename))

            else:
                if tmpdir.path is None:
                    textfiles.append(filepath)
                else:
                    shutil.copy(filepath, tmpdir.path)
        return tmpdir

    def push(self, filepath):
        """
        Copy file at `filepath' into this repository and replace the original
        file by a fake one pointed to it.
        """
        # Create hash
        digest = hashfile(filepath)

        # Move binary file to lookaside
        destpath = os.path.join(self.path, digest)
        logging.debug('Importing %s into lookaside (%s)', filepath, digest)
        shutil.copyfile(filepath, destpath)

        # Create fake pointer file
        with open(filepath, 'w') as fakefile:
            fakefile.write(digest)
