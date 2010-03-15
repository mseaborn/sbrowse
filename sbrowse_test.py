
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

    def test_git_file_set(self):
        tempdir = self.make_temp_dir()
        write_file(os.path.join(tempdir, "foo"), "Hello world")
        write_file(os.path.join(tempdir, "bar"), "Hello, this is not listed")
        subprocess.check_call(["git", "init", "-q"], cwd=tempdir)
        subprocess.check_call(["git", "add", "foo"], cwd=tempdir)
        fileset = sbrowse.make_fileset(tempdir)
        self.assertEquals(list(fileset.list_files()), ["foo"])
        self.assertEquals(list(fileset.grep_files("blah")), [])
        # "bar" has not been git-added, so shouldn't be listed.
        self.assertEquals(list(fileset.grep_files("hello")), ["foo"])


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
        page = self.get_response(fileset, "/sym/foo")
        self.assert_golden(page, "search.html")

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

    def test_search_redirect(self):
        fileset = self.example_input()
        self.check_for_redirect(fileset, "/search", query="sym=shoe",
                                dest="/sym/shoe")

    def test_dir_redirect(self):
        fileset = self.example_input()
        self.check_for_redirect(fileset, "/file/foodir", dest="/file/foodir/")


if __name__ == "__main__":
    if "--update" in sys.argv:
        GoldenTest.update_golden = True
        sys.argv.remove("--update")
    unittest.main()
