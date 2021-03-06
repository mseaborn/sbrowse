
# Copyright (C) 2007-2008 Mark Seaborn
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301 USA.

import os
import unittest
import subprocess
import sys

import sbrowse
import tempdir_test


SCRIPT_DIR = os.path.dirname(__file__)


def read_file(filename):
    fh = open(filename, "r")
    try:
        return fh.read()
    finally:
        fh.close()


def write_file(filename, data):
    fh = open(filename, "w")
    try:
        fh.write(data)
    finally:
        fh.close()


class TokenizerTest(unittest.TestCase):

    def test_tokenizer(self):
        self.assertEquals(list(sbrowse.tokens("  foo !! bar31 + _qux && ")),
                          [("  ", False), 
                           ("foo", True), 
                           (" !! ", False), 
                           ("bar31", True),
                           (" + ", False), 
                           ("_qux", True), 
                           (" && ", False)])


class FileSetTests(tempdir_test.TempDirTestCase):

    def example_tree(self):
        tempdir = self.make_temp_dir()
        write_file(os.path.join(tempdir, "foo"), "Hello world")
        write_file(os.path.join(tempdir, "bar"), "Hello, this is not listed")
        os.mkdir(os.path.join(tempdir, "mysubdir"))
        write_file(os.path.join(tempdir, "mysubdir", "jam"), "raspberry")
        return tempdir

    def check_file_set(self, fileset):
        self.assertEquals(list(fileset.grep_files("", "blah")), [])
        self.assertEquals(list(fileset.grep_files("", "world")), ["foo"])
        # Test subdir search
        self.assertEquals(list(fileset.list_files("mysubdir")),
                          ["jam"])
        self.assertEquals(list(fileset.grep_files("mysubdir", "berry")),
                          ["jam"])

    def test_fs_file_set(self):
        tempdir = self.example_tree()
        fileset = sbrowse.make_fileset(tempdir)
        self.assertEquals(
            list(fileset.list_files("")),
            ["bar", "foo", "mysubdir", "mysubdir/jam"])
        self.assertEquals(list(fileset.grep_files("", "blah")), [])
        self.assertEquals(list(fileset.grep_files("", "hello")),
                          ["foo", "bar"])
        self.check_file_set(fileset)

    def test_git_file_set(self):
        tempdir = self.example_tree()
        subprocess.check_call(["git", "init", "-q"], cwd=tempdir)
        subprocess.check_call(["git", "add", "foo"], cwd=tempdir)
        subprocess.check_call(["git", "add", "mysubdir/jam"], cwd=tempdir)
        fileset = sbrowse.make_fileset(tempdir)
        self.assertEquals(list(fileset.list_files("")),
                          ["foo", "mysubdir/jam"])
        # "bar" has not been git-added, so shouldn't be listed.
        self.assertEquals(list(fileset.grep_files("", "hello")), ["foo"])
        self.assertEquals(list(fileset.grep_files("", "Hello")), ["foo"])
        self.check_file_set(fileset)

    def test_svn_file_set(self):
        # Invoking SVN is slow compared with the rest of the tests.
        # I think it is because SVN sleeps for upto 1 second.
        repo_dir = self.make_temp_dir()
        subprocess.check_call(["svnadmin", "create", repo_dir])
        tempdir = self.example_tree()
        subprocess.check_call(["svn", "checkout", "-q",
                               "file://%s" % repo_dir, tempdir])
        subprocess.check_call(["svn", "add", "-q", "foo", "mysubdir"],
                              cwd=tempdir)
        fileset = sbrowse.make_fileset(tempdir)
        self.assertEquals(list(fileset.list_files("")),
                          ["mysubdir/jam", "mysubdir", "foo"])
        # "bar" has not been git-added, so shouldn't be listed.
        self.assertEquals(list(fileset.grep_files("", "hello")), ["foo"])
        self.assertEquals(list(fileset.grep_files("", "Hello")), ["foo"])
        self.check_file_set(fileset)

    def test_combined_file_set(self):
        tempdir1 = self.make_temp_dir()
        write_file(os.path.join(tempdir1, "foo"), "qux")
        os.mkdir(os.path.join(tempdir1, "subdir"))
        tempdir2 = self.make_temp_dir()
        write_file(os.path.join(tempdir2, "bar"), "quux")
        fileset = sbrowse.CombinedFileSet({
                "aa": sbrowse.make_fileset(tempdir1),
                "bb": sbrowse.make_fileset(tempdir2)})
        self.assertEquals(fileset.is_dir(""), True)
        self.assertEquals(fileset.is_dir("aa"), True)
        self.assertEquals(fileset.is_dir("aa/subdir"), True)
        self.assertEquals(fileset.is_dir("aa/foo"), False)
        self.assertEquals(fileset.list_dir(""), ["aa", "bb"])
        self.assertEquals(fileset.list_dir("aa"), ["foo", "subdir"])
        self.assertEquals(list(fileset.list_files("aa")), ["foo", "subdir"])
        self.assertEquals(list(fileset.grep_files("aa", "qu")), ["foo"])
        self.assertEquals(list(fileset.list_files("")),
                          ["aa", "aa/foo", "aa/subdir",
                           "bb", "bb/bar"])
        self.assertEquals(list(fileset.grep_files("", "qux")), ["aa/foo"])
        self.assertEquals(list(fileset.grep_files("", "quux")), ["bb/bar"])


class GoldenTest(object):

    update_golden = False

    def assert_golden(self, data, leafname):
        expect_file = os.path.join(SCRIPT_DIR, "testdata", leafname)
        if not (os.path.exists(expect_file) and
                data == read_file(expect_file)):
            if self.update_golden:
                write_file(expect_file, data)
                print "updated %s" % expect_file
            else:
                temp_file = os.path.join(self.make_temp_dir(), leafname)
                write_file(temp_file, data)
                proc = subprocess.Popen(["diff", "-u", expect_file, temp_file],
                                        stdout=subprocess.PIPE)
                diff = proc.communicate()[0]
                assert proc.wait() == 1, proc.wait()
                raise AssertionError(
                    "Actual output did not match expected file %r:\n%s"
                    % (expect_file, diff))


class RequestTests(GoldenTest, tempdir_test.TempDirTestCase):

    def get_response(self, fileset, uri, query=""):
        # TODO: Don't require monkey-patching
        sbrowse.stylesheet = \
            lambda: ['<link rel="stylesheet" href="../styles.css"/>']
        def start_response(response_code, headers):
            self.assertEquals(response_code, "200 OK")
        environ = {"SCRIPT_NAME": "script_name",
                   "PATH_INFO": uri,
                   "QUERY_STRING": query,
                   "HTTP_HOST": "localhost:8000"}
        iterable = sbrowse.handle_request(fileset, environ, start_response)
        return "\n".join(iterable)

    def example_input(self):
        tempdir = self.make_temp_dir()
        write_file(os.path.join(tempdir, "foofile"),
                   "foo data!\nmore data\nanother foo match\n")
        os.mkdir(os.path.join(tempdir, "foodir"))
        write_file(os.path.join(tempdir, "foodir/nested-file"), "nested")
        return sbrowse.FSFileSet(tempdir)

    def test_symbol_search(self):
        fileset = self.example_input()
        page = self.get_response(fileset, "/search", "sym=foo")
        self.assert_golden(page, "search.html")

    def test_symbol_search_substring(self):
        fileset = self.example_input()
        page = self.get_response(fileset, "/search", "sym=oo")
        self.assert_golden(page, "search-substring.html")

    def test_symbol_search_subdir(self):
        fileset = self.example_input()
        page = self.get_response(fileset, "/search", "sym=nested&dir=foodir")
        self.assert_golden(page, "search-subdir.html")

    def test_file_display(self):
        fileset = self.example_input()
        page = self.get_response(fileset, "/file/foofile")
        self.assert_golden(page, "file-display.html")

    def test_file_display_with_highlight(self):
        fileset = self.example_input()
        page = self.get_response(fileset, "/file/foofile", "sym=foo")
        self.assert_golden(page, "file-display-highlight.html")

    def test_file_display_nested(self):
        fileset = self.example_input()
        # TODO: Check the output
        self.get_response(fileset, "/file/foodir/nested-file")

    def test_directory_listing(self):
        fileset = self.example_input()
        page = self.get_response(fileset, "/file/")
        self.assert_golden(page, "dir-listing.html")

    def check_for_redirect(self, fileset, uri, dest, query=""):
        # TODO: Don't require monkey-patching
        sbrowse.stylesheet = lambda: ()
        def start_response(response_code, headers):
            self.assertEquals(response_code, "302 OK")
            self.assertEquals(headers, [("Location", "script_name" + dest)])
        environ = {"SCRIPT_NAME": "script_name",
                   "PATH_INFO": uri,
                   "QUERY_STRING": query,
                   "HTTP_HOST": "localhost:8000"}
        list(sbrowse.handle_request(fileset, environ, start_response))

    def test_root_redirect(self):
        fileset = self.example_input()
        self.check_for_redirect(fileset, "/", dest="/file/")

    def test_dir_redirect(self):
        fileset = self.example_input()
        self.check_for_redirect(fileset, "/file/foodir", dest="/file/foodir/")

    def test_security_initial_slash(self):
        fileset = self.example_input()
        self.assertRaises(
            AssertionError,
            lambda: self.get_response(fileset, "/file//etc/passwd"))

    def test_security_dotdot(self):
        fileset = self.example_input()
        self.assertRaises(
            AssertionError,
            lambda: self.get_response(fileset, "/file/../somefile"))

    def test_security_subdir_search(self):
        fileset = self.example_input()
        self.assertRaises(
            AssertionError,
            lambda: self.get_response(fileset, "/search", "sym=root&dir=/etc"))


if __name__ == "__main__":
    if "--update" in sys.argv:
        GoldenTest.update_golden = True
        sys.argv.remove("--update")
    unittest.main()
