#
# Copyright (C) 2026 CEA
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

"""Jobs and threads classes and utilities to run jobs in parallel."""

import contextlib
import heapq
import io
import sys
import threading
import time
import traceback

from rift import RiftError
from rift.test_results import TestResults
from rift.utils import banner, message

# Python provides standards context managers contextlib.redirect_{stdout,stderr}
# but they are not thread-safe unfortunately. For redirecting threads
# stdout/stderr in a buffer, Rift uses a combination of:
#
# - stdout/stderr proxy that tries to use thread local stream before fallback to
#   default process stdout/stderr
# - thread-safe context manager which sets up a thread local stream.


class _ThreadLocalStream:
    """Rift stdout/stderr proxies, to support threads local buffering."""

    def __init__(self, default):
        # Store the original global stream (real sys.stdout / sys.stderr)
        self._default = default

        # Thread-local storage: each thread gets its own independent "stream"
        self.local = threading.local()

    def write(self, data):
        """
        Write data to stream. First look up the stream for the current thread.
        If none is set, fall back to the original global stream.
        """
        stream = getattr(self.local, "stream", self._default)

        # Delegate the write to the selected stream
        stream.write(data)

    def flush(self):
        """
        Flush stream. First look up the stream for the current thread. If none
        is set, fall back to the original global stream.
        """
        stream = getattr(self.local, "stream", self._default)

        # Delegate flush to that stream
        stream.flush()


def _install_proxy():
    """Install stdout/stderr proxies if not installed yet."""
    if not isinstance(sys.stdout, _ThreadLocalStream):
        sys.stdout = _ThreadLocalStream(sys.stdout)

    if not isinstance(sys.stderr, _ThreadLocalStream):
        sys.stderr = _ThreadLocalStream(sys.stderr)


# Install stdout/stderr proxies at import time so logging handlers can use them
# as soon as they are initialized.
_install_proxy()


@contextlib.contextmanager
def redirect_output_threadsafe(output):
    """
    Temporarily redirect stdout and/or stderr for the current thread only.

    Unlike contextlib.redirect_stdout, this does NOT modify global sys.stdout.
    Instead, it sets a thread-local override used by our proxy streams.
    """

    # Make sure stdout/stderr proxies are installed
    _install_proxy()

    # Set provided output stream for local thread
    sys.stdout.local.stream = sys.stderr.local.stream = output

    try:
        # Execute the block with redirected output
        yield
    finally:
        # Remove thread local attributes to fall back to default stdout/stderr
        del sys.stdout.local.stream
        del sys.stderr.local.stream


class SlotPool:
    """
    Bounded pool of integer slots, used to cap concurrent tests.

    Slots are integers in range [0, size). The lowest free one is always handed
    out so that resources derived from a slot (eg. VM identity, ports and
    sockets) stay in a small, predictable set.
    """

    def __init__(self, size):
        if size < 1:
            raise RiftError(f"Slot pool size must be at least 1, got {size}")
        self._free = list(range(size))
        self._available = threading.Condition()

    @contextlib.contextmanager
    def slot(self):
        """Block until a slot is free, yield it and release it on exit."""
        with self._available:
            while not self._free:
                self._available.wait()
            slot = heapq.heappop(self._free)
        try:
            yield slot
        finally:
            with self._available:
                heapq.heappush(self._free, slot)
                self._available.notify()


class Job:
    """
    Unit of work to run: a target callable with its arguments. Running the job
    returns TestResults.
    """

    def __init__(self, name, target, args, case):
        self.name = name  # name of the job, also used as thread name
        self.target = target  # callable which returns job TestResults
        self.args = args  # tuple of arguments for the target
        self.case = case  # TestCase reported as failed if the target crashes

    def run(self):
        """
        Run the target with the job arguments and return its TestResults. If the
        target crashes, its traceback is printed on stderr and the crash is
        reported as a failure of the job case.
        """
        now = time.time()
        try:
            return self.target(*self.args)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            traceback.print_exc(file=sys.stderr)
            results = TestResults()
            results.add_failure(self.case, time.time() - now, err=str(exc))
            return results


class RiftThread(threading.Thread):
    """Thread to run a Rift job in parallel with buffered output."""

    def __init__(self, job):
        # Initializing the Thread class
        super().__init__(name=job.name)
        self.job = job
        self.output = io.StringIO()  # output buffer, for stdout/stderr
        self.results = TestResults()  # job tests results

    def run(self):
        """
        Run the job and bufferize its stdout/stderr in output attribute.
        """
        with redirect_output_threadsafe(self.output):
            try:
                self.results = self.job.run()
            except Exception:
                # Avoid threading.Thread to catch the Exception and report the
                # stacktrace out of thread buffered output. Force print of
                # exception in sys.stderr here to make it land in thread local
                # buffer.
                traceback.print_exc(file=sys.stderr)


def run_jobs(jobs, label, seq=False, quiet=False):
    """
    Run the given jobs and return their merged TestResults in jobs order.

    Each job runs in its own RiftThread with its output bufferized, then printed
    with label in its banner when thread is joined. When quiet is True, output
    of succeeding jobs is omitted. When seq is True, jobs run one after the
    other in the current thread with live output. In both cases, crash of a job
    is reported as a failure of its case.
    """
    results = TestResults()

    if seq:
        for job in jobs:
            results.extend(job.run())
        return results

    threads = [RiftThread(job) for job in jobs]
    for thread in threads:
        message(f"Starting {label} thread {thread.name}")
        thread.start()
    for thread in threads:
        thread.join()
        results.extend(thread.results)
        if not quiet or not thread.results.global_result:
            banner(f"{label.capitalize()} thread {thread.name} output:")
            print(thread.output.getvalue(), end="")
    return results
