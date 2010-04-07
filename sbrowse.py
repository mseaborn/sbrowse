
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

import cStringIO as StringIO
import cgi
import functools
import optparse
import os
import re
import subprocess
import sys
import wsgiref.simple_server


css_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "styles.css")


def not_found(start_response):
    start_response("404 Not found", [("Content-Type", "text/html")])
    return ["404 Not found"]


def handle_request(fileset, environ, start_response):
    path = environ.get("PATH_INFO", "/").lstrip("/")
    url_root = environ["SCRIPT_NAME"]
    query = dict(cgi.parse_qsl(environ["QUERY_STRING"]))
    host_url = "http://%s" % environ["HTTP_HOST"]
    if path == "":
        start_response("302 OK", [("Location", "%s/file/" % url_root)])
        return ()
    if path == "search":
        start_response("200 OK", [("Content-Type", "text/html")])
        subdir = query.get("dir", "")
        check_filename(subdir)
        return sym_search(fileset, url_root, subdir, query["sym"])
    if "/" not in path:
        return not_found(start_response)
    elt, rest = path.split("/", 1)
    if elt == "file":
        filename = rest
        check_filename(filename)
        if (filename != "" and not filename.endswith("/") and
            fileset.is_dir(filename)):
            start_response("302 OK",
                           [("Location", "%s/file/%s/" % (url_root, filename))])
            return ()
        else:
            start_response("200 OK", [("Content-Type", "text/html")])
            subdir = ""
            return show_file_or_dir(fileset, url_root, filename, subdir, query)
    else:
        return not_found(start_response)


def check_filename(filename):
    if filename.startswith("/"):
        raise AssertionError("Absolute pathname: %r" % filename)
    for part in filename.split("/"):
        if part == "..":
            raise AssertionError("Pathname %r contains '..'" % filename)


def stylesheet():
    fh = open(css_file, "r")
    try:
        yield "<style type='text/css'>\n"
        yield fh.read()
        yield "</style>\n"
    finally:
        fh.close()


class FileSetBase(object):

    def __init__(self, dir_path, case_sensitive=False):
        self._dir_path = dir_path
        # Setting case_sensitive to True is an optimisation, because
        # "grep -i" is significantly slower than case-sensitive grep.
        self._case_sensitive = case_sensitive

    def _get_path(self, filename):
        check_filename(filename)
        return os.path.join(self._dir_path, filename)

    def is_dir(self, filename):
        return os.path.isdir(self._get_path(filename))

    def list_dir(self, filename):
        return os.listdir(self._get_path(filename))

    def stat_path(self, filename):
        return os.stat(self._get_path(filename))

    def open_file(self, filename):
        return open(self._get_path(filename), "r")


def popen_filenames(args, **kwargs):
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, bufsize=1024,
                            **kwargs)
    for line in proc.stdout:
        yield line.rstrip("\n")


# Remove the "./" prefix that "find" outputs.
def tidy_filelist(iterable):
    for filename in iterable:
        if filename != ".":
            assert filename.startswith("./")
            yield filename[2:]


class FSFileSet(FileSetBase):

    def list_files(self, subdir):
        # Note that with the sorting there is no pipelining, so we may
        # as well do this in Python.
        return tidy_filelist(popen_filenames(
            ["sh", "-c", 'find -not -name "*.pyc" | sort'],
            cwd=self._get_path(subdir)))

    def grep_files(self, subdir, sym):
        # Note that using "-i" makes this go a lot slower.
        ci_arg = "" if self._case_sensitive else " -i"
        return tidy_filelist(popen_filenames(
            ["sh", "-c",
             'find -not -name "*.pyc" '
             '-and -not -name "*~" '
             '-and -not -name "#*#" '
             '-print0 | xargs --null grep -l "$1"' + ci_arg,
             "-", sym],
            cwd=self._get_path(subdir)))


class GitFileSet(FileSetBase):

    def list_files(self, subdir):
        return popen_filenames(["git", "ls-files"],
                               cwd=self._get_path(subdir))

    def grep_files(self, subdir, sym):
        ci_arg = [] if self._case_sensitive else ["-i"]
        return popen_filenames(
            ["git", "grep"] + ci_arg + ["--text", "-l", sym],
            cwd=self._get_path(subdir))


svn_find = os.path.join(os.path.abspath(os.path.dirname(__file__)), "svn-find")


class SVNFileSet(FileSetBase):

    def list_files(self, subdir):
        return popen_filenames([svn_find], cwd=self._get_path(subdir))

    def grep_files(self, subdir, sym):
        ci_arg = "" if self._case_sensitive else "-i"
        return popen_filenames(
            ["sh", "-c",
             '%s | xargs grep -l "$1" %s' % (svn_find, ci_arg),
             "-", sym],
            cwd=self._get_path(subdir))


def sym_search_in_filenames(fileset, url_root, subdir, sym):
    sym_regexp = re.compile(re.escape(sym), re.IGNORECASE)
    yield "<pre class=code>"
    for filename in fileset.list_files(subdir):
        match = sym_regexp.search(filename)
        if match:
            text = ("%s<strong>%s</strong>%s"
                    % (cgi.escape(filename[:match.start()]),
                       cgi.escape(match.group()),
                       cgi.escape(filename[match.end():])))
            yield ("<a href='%s/file/%s'>%s</a>\n"
                   % (url_root, os.path.join(subdir, filename), text))
    yield "</pre>"


class SymSearch(object):

    def __init__(self, subdir, sym):
        self._subdir = subdir
        self._sym = sym
        self._sym_regexp = re.compile(re.escape(sym))
        self._sym_regexp_ci = re.compile(re.escape(sym), re.IGNORECASE)
        self.syms_found = {}
        self.syms_found_ci = {}

    def match_line(self, url_root, line):
        """Tells you whether the line matches and returns a formatted version
        of the line with the matches highlighted."""
        does_match = False
        line_out = []
        for token, is_symbol in tokens(line):
            if token == self._sym:
                line_out.append("<strong>%s</strong>" % token)
                does_match = True
            elif is_symbol:
                line_out.append(link_token(url_root, self._subdir, token))
                if self._sym_regexp.search(token):
                    self.syms_found[token] = \
                        self.syms_found.get(token, 0) + 1
                elif self._sym_regexp_ci.search(token):
                    self.syms_found_ci[token] = \
                        self.syms_found_ci.get(token, 0) + 1
            else:
                line_out.append(cgi.escape(token))
        return (does_match, line_out)

    def match_lines(self, url_root, lines):
        for line_no, line in enumerate(lines):
            line = line.rstrip("\n\r")
            # Regexp search is an optimisation: could be removed
            if self._sym_regexp_ci.search(line):
                does_match, line_out = self.match_line(url_root, line)
                if does_match:
                    yield (line_no, line_out)


def sym_search(fileset, url_root, subdir, sym):
    for x in stylesheet():
        yield x
    yield output_tag([tag("title", "symbol: ", sym),
                      tagp("div", [("class", "box")],
                           tag("div", breadcrumb_path(url_root, "")),
                           tag("div", search_form(url_root, sym)))])
    for x in sym_search_in_filenames(fileset, url_root, subdir, sym):
        yield x
    matcher = SymSearch(subdir, sym)
    yield "<div class=all_matches>"
    for rel_filename in fileset.grep_files(subdir, sym):
        filename = os.path.join(subdir, rel_filename)
        file_matches = False
        fh = fileset.open_file(filename)
        for line_no, line_out in matcher.match_lines(url_root, fh):
            args = {"root": url_root,
                    "sym": sym,
                    "rel_file": rel_filename,
                    "file": filename,
                    "line_no": line_no + 1}
            if not file_matches:
                file_matches = True
                yield ("<a href='%(root)s/file/%(file)s?sym=%(sym)s"
                       "#line%(line_no)i'>%(rel_file)s</a>:"
                       % args)
            yield "<div class='code matches_in_file'>"
            yield ("<a href='%(root)s/file/%(file)s?sym=%(sym)s"
                   "#line%(line_no)i'>%(line_no)i</a>:"
                   % args)
            for x in line_out:
                yield x
            yield "</div>"
            yield "\n"
    yield "</div>"
    yield "<hr>Other symbols found:\n"
    if (len(matcher.syms_found) == 0 and
        len(matcher.syms_found_ci) == 0):
        yield "none"
    else:
        if len(matcher.syms_found) > 0:
            yield output_tag(format_sym_list(url_root, subdir,
                                             matcher.syms_found))
        if len(matcher.syms_found_ci) > 0:
            yield "with case relaxed:\n"
            yield output_tag(format_sym_list(url_root, subdir,
                                             matcher.syms_found_ci))

def format_sym_list(url_root, subdir, syms):
    body = []
    for symbol, count in sorted(syms.iteritems()):
        url = search_url(url_root, subdir, symbol)
        body.append(tag("li", tagp("a", [("href", url)], symbol),
                        " (%i)" % count))
    return tag("ul", body)

def show_file_or_dir(fileset, url_root, filename, subdir, query):
    if fileset.is_dir(filename):
        return show_dir(fileset, url_root, filename)
    else:
        return show_file(fileset, url_root, filename, subdir, query)

def show_file(fileset, url_root, filename, subdir, query):
    for x in stylesheet():
        yield x
    links = [tag("div", tagp("a", [("href", url)], name))
             for name, url in get_file_links(filename)]
    yield output_tag([tag("title", filename),
                      tagp("div", [("class", "box")],
                           tag("div", breadcrumb_path(url_root, filename)),
                           tag("div", search_form(url_root, "")),
                           links)])
    if "sym" in query:
        matcher = SymSearch(subdir, query["sym"])
        match_line_nos = []
        fh = fileset.open_file(filename)
        try:
            for line_no, line in enumerate(fh):
                does_match, line_out = matcher.match_line(url_root, line)
                if does_match:
                    match_line_nos.append(line_no)
        finally:
            fh.close()
        yield output_tag(tagp("div", [("class", "box")],
                              [[tagp("a", [("href", "#line%s" % (line_no + 1))],
                                     str(line_no)),
                                " "]
                               for line_no in match_line_nos]))

        matcher = SymSearch(subdir, query["sym"])
        fh = fileset.open_file(filename)
        try:
            yield "<pre class=code>"
            for line_no, line in enumerate(fh):
                line = line.rstrip("\n\r")
                does_match, line_out = matcher.match_line(url_root, line)
                if does_match:
                    yield "<span class=highlight>"
                else:
                    yield "<span>"
                yield "<a name='line%i'></a>" % (line_no + 1)
                for x in line_out:
                    yield x
                yield "</span>\n"
            yield "</pre>"
        finally:
            fh.close()
    else:
        fh = fileset.open_file(filename)
        try:
            yield "<pre class=code>"
            for line_no, line in enumerate(fh):
                yield "<a name='line%i'>" % (line_no + 1)
                for token, is_symbol in tokens(line):
                    if is_symbol:
                        yield link_token(url_root, subdir, token)
                    else:
                        yield cgi.escape(token)
            yield "</pre>"
        finally:
            fh.close()

def show_dir(fileset, url_root, path):
    title = path if path != "" else "[top]"
    for x in stylesheet():
        yield x
    yield output_tag([tag("title", title),
                      tagp("div", [("class", "box")],
                           tag("div", breadcrumb_path(url_root, path)),
                           tag("div", search_form(url_root, "")))])
    def format_entry(leafname):
        pathname = os.path.join(path, leafname)
        if fileset.is_dir(pathname):
            size = ""
            leafname += "/"
        else:
            st = fileset.stat_path(pathname)
            size = str(st.st_size)
        return tag("tr",
                   tagp("td", [("class", "file-size")], size),
                   tagp("td", [("class", "file-name")],
                        tagp("a", [("href", leafname)], leafname)))
    yield output_tag([breadcrumb_path(url_root, path),
                      tagp("table", [("class", "dirlist")],
                           tag("tr",
                               tagp("th", [("class", "file-size")], "size"),
                               tagp("th", [("class", "file-name")], "name")),
                           [format_entry(leafname)
                            for leafname in sorted(fileset.list_dir(path))
                            if not exclude(leafname)])])

def exclude(leafname):
    regexps = [r"\.pyc$",
               r"^#.*#$",
               r"~"]
    for regexp in regexps:
        if re.search(regexp, leafname):
            return True
    return False


def search_form(url_root, default_sym):
    script = """
window.onload = function () {
    document.getElementById("form_field").focus();
}
"""
    return tagp("form", [("action", "%s/search" % url_root),
                         ("method", "get")],
                tagp("input", [("id", "form_field"),
                               ("type", "text"),
                               ("name", "sym"),
                               ("value", default_sym)]),
                tagp("button", [("type", "submit")],
                     "Go"),
                tagp("script", [("language", "javascript")], script))

def breadcrumb_path(url_root, path):
    crumbs = [tagp("a", [("href", "%s/file/" % url_root)], "[top]")]
    path_got = ""
    for element in path.split("/"):
        path_got = os.path.join(path_got, element)
        crumbs.append(["/",
                       tagp("a", [("href", "%s/file/%s" % (url_root, path_got))],
                            cgi.escape(element))])
    return crumbs

def tokens(line):
    regexp = re.compile("(.*?)([A-Za-z0-9_]+)")
    i = 0
    while True:
        m = regexp.match(line, i)
        if m:
            yield (m.group(1), False)
            yield (m.group(2), True)
            i = m.end()
        else:
            yield (line[i:], False)
            return


def search_url(url_root, subdir, symbol):
    return "%s/search?dir=%s&sym=%s" % (url_root, subdir, symbol)


def link_token(url_root, subdir, token):
    url = search_url(url_root, subdir, token)
    return "<a href='%s'>%s</a>" % (url, token)


def tag(tag, *body):
    return ("<%s>" % tag,
            body,
            "</%s>" % tag)

def tagp(tag, attrs, *body):
    return ("<%s%s>" % (tag,
                        "".join(map(lambda (key, val):
                                        " %s='%s'" % (key, val),
                                    attrs))),
            body,
            "</%s>" % tag)

def output_tag(val):
    out = StringIO.StringIO()
    def f(x):
        if isinstance(x, str):
            out.write(x)
        elif isinstance(x, tuple) or isinstance(x, list):
            for y in x:
                f(y)
        else:
            raise TypeError(x)
    f(val)
    return out.getvalue()


def path_splits(filename):
    parts = filename.split("/")
    for i in range(len(parts)):
        yield ("/".join(parts[:i]),
               "/".join(parts[i:]))

def get_file_links(filename):
    for part1, part2 in path_splits(filename):
        link_file = os.path.join(part1, "crossrefs.sbrowse")
        if os.path.exists(link_file):
            for line in open(link_file, "r"):
                name, url_pattern = line.split(":", 1)
                yield (name, url_pattern % part2)


def make_fileset(dir_path, **kwargs):
    if os.path.exists(os.path.join(dir_path, ".svn")):
        return SVNFileSet(dir_path, **kwargs)
    elif os.path.exists(os.path.join(dir_path, ".git")):
        return GitFileSet(dir_path, **kwargs)
    else:
        return FSFileSet(dir_path, **kwargs)


def main(argv):
    parser = optparse.OptionParser()
    parser.add_option("--dir", "-d", dest="dir_path", default=".",
                      help="Directory to serve")
    parser.add_option("--port", "-p", dest="port", default=8000, type="int",
                      help="TCP port number to serve HTTP on")
    parser.add_option("--cgi", dest="do_cgi", action="store_true",
                      help="Act as a CGI script")
    parser.add_option("--once", dest="do_once", action="store_true",
                      help="Serve only one HTTP request (for debugging)")
    parser.add_option("--cs", "--case-sensitive", dest="case_sensitive",
                      action="store_true",
                      help="Grep for symbols case-sensitively (faster)")
    options, args = parser.parse_args(argv)
    if len(args) != 0:
        parser.error("Unexpected arguments")
    fileset = make_fileset(options.dir_path,
                           case_sensitive=options.case_sensitive)
    handler = functools.partial(handle_request, fileset)
    if options.do_cgi:
        wsgiref.handlers.CGIHandler().run(handler)
    else:
        httpd = wsgiref.simple_server.make_server("", options.port, handler)
        print "Listening on port %i" % options.port
        if options.do_once:
            httpd.handle_request()
        else:
            httpd.serve_forever()


if __name__ == "__main__":
    main(sys.argv[1:])
