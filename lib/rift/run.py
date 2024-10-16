#
# Copyright (C) 2024 CEA
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

"""
Function to run a command with possibility to capture output while streaming
live output on stdout/stderr.
"""

import sys
import io
import collections
import selectors
import subprocess

RunResult = collections.namedtuple(
    'RunResult', ['returncode', 'out', 'err']
)

def _handle_process_output(process, selector):
    """Handle process output events with registered selectors."""
    # Loop until subprocess is terminated
    while process.poll() is None:
        # Wait for events and handle them with their registered callbacks
        events = selector.select()
        for key, _ in events:
            callback = key.data
            callback(key.fileobj)

def run_command(
        cmd,
        live_output=True,
        capture_output=False,
        merged_capture=False,
        **kwargs
    ):
    """
    Run a command and return RunResult named tuple. When live_output is True,
    command stdout/stderr are streamed in live in current process stdout/stderr.
    When capture_output is True, command stdout/stderr are available in out/err
    attributes of RunResult namedtuple. When merged_capture is True as well,
    command stderr is merged with stdout in out attribute of RunResult named
    tuple. In this case, err attribute is None.

    Initially based on:
    https://gist.github.com/nawatts/e2cdca610463200c12eac2a14efc0bfb
    """
    if capture_output:
        channel = subprocess.PIPE
    elif live_output:
        channel = None
    else:
        channel = subprocess.DEVNULL

    # Launch the command
    # bufsize = 1 means output is line buffered
    # universal_newlines = True is required for line buffering
    process = subprocess.Popen(
        cmd,
        bufsize=1,
        stdout=channel,
        stderr=channel,
        universal_newlines=True,
        **kwargs
    )

    # If capture is disabled, just return the command result with the return
    # code and None values for output.
    if not capture_output:
        return RunResult(process.wait(), None, None)

    # Initialize string buffers to store process output in memory
    buf_out = io.StringIO()
    if not merged_capture:
        buf_err = io.StringIO()

    # Process output lines handlers
    def handle_stdout(stream):
        line = stream.readline()
        buf_out.write(line)
        if live_output:
            sys.stdout.write(line)
    def handle_stderr(stream):
        line = stream.readline()
        if merged_capture:
            buf_out.write(line)
        else:
            buf_err.write(line)
        if live_output:
            sys.stderr.write(line)

    # Register callback for read events from subprocess stdout/stderr streams
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, handle_stdout)
    selector.register(process.stderr, selectors.EVENT_READ, handle_stderr)

    # Handle process output with registered selectors
    _handle_process_output(process, selector)

    # _handle_process_output stops processing output as soon as the process is
    # terminated. However, there may still be buffered output to flush.
    for line in process.stdout:
        buf_out.write(line)
        if live_output:
            sys.stdout.write(line)
    for line in process.stderr:
        if merged_capture:
            buf_out.write(line)
        else:
            buf_err.write(line)
        if live_output:
            sys.stdout.write(line)

    # Ensure process is terminated
    process.wait()

    # Store buffered output
    selector.close()
    out = buf_out.getvalue()
    buf_out.close()
    if merged_capture:
        err = None
    else:
        err = buf_err.getvalue()
        buf_err.close()

    return RunResult(process.returncode, out, err)
