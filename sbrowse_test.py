
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

import sbrowse
import tempdir_test


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


class RequestTests(tempdir_test.TempDirTestCase):

    def get_response(self, uri):
        # TODO: Don't require monkey-patching
        sbrowse.stylesheet = lambda: ()
        def start_response(response_code, headers):
            self.assertEquals(response_code, "200 OK")
        environ = {"SCRIPT_NAME": "script_name",
                   "PATH_INFO": uri,
                   "QUERY_STRING": "",
                   "HTTP_HOST": "localhost:8000"}
        return "\n".join(sbrowse.handle_request(environ, start_response))

    def example_input(self):
        tempdir = self.make_temp_dir()
        write_file(os.path.join(tempdir, "foofile"), "foo data!")
        # TODO: Pass directory as argument
        os.chdir(tempdir)

    def test_symbol_search(self):
        self.example_input()
        # TODO: Check the output
        self.get_response("/sym/foo")

    def test_file_display(self):
        self.example_input()
        # TODO: Check the output
        self.get_response("/file/foofile")

    def test_directory_listing(self):
        self.example_input()
        # TODO: Check the output
        self.get_response("/file/")


if __name__ == "__main__":
    unittest.main()
