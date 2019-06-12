from unidiff import parse_unidiff
from TestUtils import make_temp_file, make_temp_dir, RiftTestCase

class UnidiffTest(RiftTestCase):
    """
    Test class for unidiff
    """

    def testMultiFilePatch(self):
        """ Test if unidiff parse correctly a patch with mutliple files """
        unifiedpatch = make_temp_file("""
commit 0ac8155e2655321ceb28bbf716ff66d1a9e30f29 (HEAD -> master)
Author: Myself <buddy@somewhere.org>
Date:   Thu Apr 25 14:30:41 2019 +0200

    packages: add 'foo'

diff --git a/file1 b/file1
new file mode 100644
index 0000000..32ac08e
--- /dev/null
+++ b/file1
@@ -0,0 +1 @@
+foo
diff --git a/file2 b/file2
new file mode 100644
index 0000000..257cc56
--- /dev/null
+++ b/file2
@@ -0,0 +1 @@
+bar
diff --git a/file3 b/file3
new file mode 100644
index 0000000..257cc56
--- /dev/null
+++ b/file3
@@ -0,0 +1 @@
+pub
""")


        with open(unifiedpatch.name, 'r') as f:
            patchedfiles = parse_unidiff(f)
        self.assertEqual(len(patchedfiles), 3)
        filenames = []
        for patchedfile in patchedfiles:
            filenames.append(patchedfile.path)
        self.assertTrue("file1" in filenames)
        self.assertTrue("file2" in filenames)
        self.assertTrue("file3" in filenames)
