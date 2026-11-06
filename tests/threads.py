#
# Copyright (C) 2026 CEA
#
import sys
import threading
from io import StringIO
from unittest.mock import patch

from rift import RiftError
from rift.config import _DEFAULT_VARIANT
from rift.test_results import TestCase, TestResults
from rift.threads import Job, RiftThread, SlotPool, run_jobs

from .test_utils import RiftTestCase


class SlotPoolTest(RiftTestCase):
    """Tests class for SlotPool"""

    def test_invalid_size(self):
        """Test SlotPool refuses a size lower than 1"""
        with self.assertRaisesRegex(RiftError, "^Slot pool size must be at least 1"):
            SlotPool(0)

    def test_lowest_free_slot(self):
        """Test SlotPool always gives the lowest free slot"""
        pool = SlotPool(3)
        with pool.slot() as first:
            self.assertEqual(first, 0)
            with pool.slot() as second:
                self.assertEqual(second, 1)
            # Slot 1 has been released, it must be given again.
            with pool.slot() as third:
                self.assertEqual(third, 1)

    def test_released_on_exception(self):
        """Test SlotPool releases the slot when an exception is raised"""
        pool = SlotPool(1)
        with self.assertRaises(ValueError):
            with pool.slot():
                raise ValueError
        with pool.slot() as slot:
            self.assertEqual(slot, 0)

    def test_blocks_when_exhausted(self):
        """Test SlotPool blocks until a slot is released"""
        pool = SlotPool(1)
        acquired = threading.Event()

        def waiter():
            with pool.slot():
                acquired.set()

        thread = threading.Thread(target=waiter)
        with pool.slot():
            thread.start()
            self.assertFalse(acquired.wait(0.1))
        self.assertTrue(acquired.wait(10))
        thread.join()


class JobTest(RiftTestCase):
    """Tests class for Job"""

    CASE = TestCase("build", "pkg", _DEFAULT_VARIANT, "x86_64", "rpm")

    def test_run(self):
        """Test Job run calls target with its arguments and returns its results"""
        results = TestResults()
        received = []

        def target(*args):
            received.append(args)
            return results

        job = Job("build-x86_64-main", target, ("a", "b"), self.CASE)
        self.assertIs(job.run(), results)
        self.assertEqual(received, [("a", "b")])

    @patch("sys.stderr", new_callable=StringIO)
    def test_run_crash(self, mock_stderr):
        """Test Job run reports target crash as failure of its case with traceback"""

        def target():
            raise RiftError("fail")

        results = Job("build-x86_64-main", target, (), self.CASE).run()
        self.assertFalse(results.global_result)
        self.assertEqual(len(results), 1)
        result = results.results[0]
        self.assertEqual(result.value, "Failure")
        self.assertIs(result.case, self.CASE)
        self.assertEqual(result.err, "fail")
        self.assertIn("rift.RiftError: fail", mock_stderr.getvalue())


class RiftThreadTest(RiftTestCase):
    """Tests class for RiftThread"""

    CASE = TestCase("build", "pkg", _DEFAULT_VARIANT, "x86_64", "rpm")

    def test_run_job(self):
        """Test RiftThread runs job, keeps its results and buffers its output"""
        results = TestResults()

        def target():
            print("target output")
            return results

        job = Job("build-x86_64-main", target, (), self.CASE)
        thread = RiftThread(job)
        self.assertEqual(thread.name, "build-x86_64-main")
        self.assertIs(thread.job, job)
        thread.start()
        thread.join()
        self.assertIs(thread.results, results)
        self.assertEqual(thread.output.getvalue(), "target output\n")

    def test_run_job_crash(self):
        """Test RiftThread buffers traceback of crashed job and its failure"""

        def target():
            raise RiftError("fail")

        thread = RiftThread(Job("build-x86_64-main", target, (), self.CASE))
        thread.start()
        thread.join()
        self.assertFalse(thread.results.global_result)
        self.assertIn("rift.RiftError: fail", thread.output.getvalue())


class RunJobsTest(RiftTestCase):
    """Tests class for run_jobs()"""

    @staticmethod
    def _case(name):
        return TestCase(name, "pkg", _DEFAULT_VARIANT, "x86_64", "rpm")

    def _job(self, name, target=None, success=True):
        """Return job with default target reporting one result."""

        def default_target():
            sys.stdout.write(f"output of {name}\n")
            results = TestResults()
            if success:
                results.add_success(self._case(name), 1)
            else:
                results.add_failure(self._case(name), 1)
            return results

        return Job(name, target or default_target, (), self._case(name))

    def test_no_job(self):
        """Test run_jobs without any job"""
        results = run_jobs([], "test")
        self.assertEqual(len(results), 0)
        self.assertTrue(results.global_result)

    def test_concurrent_and_ordered(self):
        """Test jobs overlap and results follow jobs order, not completion order"""
        barrier = threading.Barrier(2, timeout=30)
        second_done = threading.Event()

        def first():
            barrier.wait()
            second_done.wait(30)
            results = TestResults()
            results.add_success(self._case("first"), 1)
            return results

        def second():
            barrier.wait()
            results = TestResults()
            results.add_success(self._case("second"), 1)
            second_done.set()
            return results

        results = run_jobs(
            [self._job("first", first), self._job("second", second)], "t"
        )
        self.assertEqual(
            [result.case.name for result in results.results], ["first", "second"]
        )

    def test_crash(self):
        """Test crash of job target is reported as a failure of its case"""

        def crash():
            raise RuntimeError("crash")

        results = run_jobs([self._job("ko", crash), self._job("ok")], "test")
        self.assertFalse(results.global_result)
        self.assertEqual(
            [(result.case.name, result.value) for result in results.results],
            [("ko", "Failure"), ("ok", "Success")],
        )
        self.assertEqual(results.results[0].err, "crash")

    def test_args(self):
        """Test target receives job arguments, with and without thread"""

        def target(first, second):
            results = TestResults()
            results.add_success(self._case(f"{first}-{second}"), 1)
            return results

        job = Job("args", target, ("a", "b"), self._case("args"))
        for seq in (False, True):
            results = run_jobs([job], "test", seq=seq)
            self.assertEqual(results.results[0].case.name, "a-b")

    @patch("rift.threads.RiftThread")
    @patch("sys.stderr", new_callable=StringIO)
    def test_seq(self, mock_stderr, mock_thread):
        """Test seq runs jobs in current thread and reports crash as failure"""

        def crash():
            raise RuntimeError("crash")

        results = run_jobs(
            [self._job("a"), self._job("ko", crash), self._job("b")], "test", seq=True
        )
        mock_thread.assert_not_called()
        self.assertEqual(
            [(result.case.name, result.value) for result in results.results],
            [("a", "Success"), ("ko", "Failure"), ("b", "Success")],
        )
        self.assertIn("RuntimeError: crash", mock_stderr.getvalue())

    @patch("builtins.print")
    @patch("rift.threads.banner")
    def test_output(self, mock_banner, mock_print):
        """Test jobs output is printed with label in banner"""
        run_jobs([self._job("a")], "build")
        mock_banner.assert_called_once_with("Build thread a output:")
        mock_print.assert_any_call("output of a\n", end="")

    @patch("rift.threads.banner")
    def test_quiet(self, mock_banner):
        """Test quiet omits output of succeeding and keeps failing or crashed jobs"""

        def crash():
            raise RuntimeError("crash")

        run_jobs(
            [
                self._job("ok"),
                self._job("ko", success=False),
                self._job("crash", crash),
            ],
            "test",
            quiet=True,
        )
        self.assertEqual(
            [call_.args[0] for call_ in mock_banner.call_args_list],
            ["Test thread ko output:", "Test thread crash output:"],
        )
