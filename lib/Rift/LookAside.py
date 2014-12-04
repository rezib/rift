#
# Copyright (C) 2014 CEA
#

"""
Class and function to detect binary files and push them into a file repository
called an annex.
"""

import os
import string
import shutil
import hashlib
import logging

from Rift.TempDir import TempDir

# List of ASCII printable characters
_TEXTCHARS = bytearray([9, 10, 13] + range(32, 127))

# XXX: Add a function needs_annex() which checks filesize too.
# to avoid copying very short file.
# Or maybe we can count the number of non-ascii chars, if this number if very
# small, consider this file as not binary.

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


class Annex(object):
    """
    Repository of binary files.

    It simply adds and removes binary files addressed by their digest.
    When importing files, they are replaced by 'pointer files' containing
    only a digest or original file content.

    For now, files are stored in a flat namespace.
    """

    def __init__(self, config, path=None):
        self.path = path or config.get('annex')

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

    def get(self, identifier, destpath):
        """Get a file identified by identifier and copy it at destpath."""
        # Copy file from repository to destination path
        idpath = os.path.join(self.path, identifier)
        logging.debug('Extracting %s to %s', identifier, destpath)
        shutil.copyfile(idpath, destpath)

    def get_by_path(self, idpath, destpath):
        """Get a file identified by idpath content, and copy it at destpath."""
        identifier = open(idpath).read()
        self.get(identifier, destpath)

    def delete(self, identifier):
        """Remove a file from annex, whose ID is `identifier'"""
        idpath = os.path.join(self.path, identifier)
        logging.debug('Deleting from annex: %s', idpath)
        os.unlink(idpath)

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
        tmpdir = TempDir('sources')
        textfiles = []
        for filename in os.listdir(dirpath):
            filepath = os.path.join(dirpath, filename)

            # Is a pointer to a binary file?
            if self.is_pointer(filepath):

                # We have our first binary file, we need a temp directory
                if tmpdir.path is None:
                    tmpdir.create()
                    for txtpath in textfiles:
                        shutil.copy(txtpath, tmpdir.path)

                # Copy the real binary content
                self.get_by_path(filepath, os.path.join(tmpdir.path, filename))

            else:
                if tmpdir.path is None:
                    textfiles.append(filepath)
                else:
                    shutil.copy(filepath, tmpdir.path)
        return tmpdir

    def list(self):
        """
        Iterate over annex files, returning for them: filename, size and
        mtime.
        """
        for filename in os.listdir(self.path):
            meta = os.stat(os.path.join(self.path, filename))
            yield filename, meta.st_size, meta.st_mtime

    def push(self, filepath):
        """
        Copy file at `filepath' into this repository and replace the original
        file by a fake one pointed to it.
        """
        # Create hash
        digest = hashfile(filepath)

        # Verify permission are correct before copying
        os.chmod(filepath, 0644)

        # Move binary file to annex
        destpath = os.path.join(self.path, digest)
        logging.debug('Importing %s into annex (%s)', filepath, digest)
        shutil.copyfile(filepath, destpath)

        # Create fake pointer file
        with open(filepath, 'w') as fakefile:
            fakefile.write(digest)
