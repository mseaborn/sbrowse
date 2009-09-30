
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
import optparse
import os
import re
import subprocess
import sys
import wsgiref.simple_server


css_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "styles.css")

def handle_request(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    url_root = environ["SCRIPT_NAME"]
    query = dict(cgi.parse_qsl(environ["QUERY_STRING"]))
    host_url = "http://%s" % environ["HTTP_HOST"]
    if path == "/":
        start_response("302 OK", [("Location", "%s/file/" % url_root)])
        return ()
    if path == "/search":
        start_response("302 OK",
                       [("Location", "%s/sym/%s"
                         % (url_root, query["sym"]))])
        return ()
    empty, elt, rest = path.split("/", 2)
    if elt == "sym":
        start_response("200 OK", [("Content-Type", "text/html")])
        return sym_search(url_root, rest)
    elif elt == "file":
        filename = rest
        if (filename != "" and not filename.endswith("/") and
            os.path.isdir(filename)):
            start_response("302 OK",
                           [("Location", "%s/file/%s/" % (url_root, filename))])
            return ()
        else:
            start_response("200 OK", [("Content-Type", "text/html")])
            return show_file_or_dir(url_root, filename, query)
    else:
        start_response("404 Not found", [("Content-Type", "text/html")])
        return ["404 Not found"]


def stylesheet():
    fh = open(css_file, "r")
    try:
        yield "<style type='text/css'>\n"
        yield fh.read()
        yield "</style>\n"
    finally:
        fh.close()

def sym_search_in_filenames(url_root, sym):
    proc = subprocess.Popen(
        ["sh", "-c", """ find -not -name "*.pyc" """],
        stdout=subprocess.PIPE, bufsize=1024)
    sym_regexp = re.compile(re.escape(sym), re.IGNORECASE)
    yield "<pre class=code>"
    for pipe_line in proc.stdout:
        filename = pipe_line.rstrip("\n")
        match = sym_regexp.search(filename)
        if match:
            text = ("%s<strong>%s</strong>%s"
                    % (cgi.escape(filename[:match.start()]),
                       cgi.escape(match.group()),
                       cgi.escape(filename[match.end():])))
            yield ("<a href='%s/file/%s'>%s</a>\n"
                   % (url_root, filename, text))
    yield "</pre>"


class SymSearch(object):

    def __init__(self, sym):
        self.sym = sym
        self.sym_regexp = re.compile(re.escape(sym))
        self.sym_regexp_ci = re.compile(re.escape(sym), re.IGNORECASE)
        self.syms_found = {}
        self.syms_found_ci = {}

    def match_line(self, url_root, line):
        """Tells you whether the line matches and returns a formatted version
        of the line with the matches highlighted."""
        does_match = False
        line_out = []
        for token, is_symbol in tokens(line):
            if token == self.sym:
                line_out.append("<strong>%s</strong>" % token)
                does_match = True
            elif is_symbol:
                line_out.append(link_token(url_root, token))
                if self.sym_regexp.search(token):
                    self.syms_found[token] = \
                        self.syms_found.get(token, 0) + 1
                elif self.sym_regexp_ci.search(token):
                    self.syms_found_ci[token] = \
                        self.syms_found_ci.get(token, 0) + 1
            else:
                line_out.append(cgi.escape(token))
        return (does_match, line_out)

    def match_file(self, url_root, filename):
        fh = open(filename, "r")
        try:
            for line_no, line in enumerate(fh):
                line = line.rstrip("\n\r")
                # Regexp search is an optimisation: could be removed
                if self.sym_regexp_ci.search(line):
                    does_match, line_out = self.match_line(url_root, line)
                    if does_match:
                        yield (line_no, line_out)
        finally:
            fh.close()


def sym_search(url_root, sym):
    for x in stylesheet():
        yield x
    yield output_tag([tag("title", "symbol: ", sym),
                      tagp("div", [("class", "box")],
                           tag("div", breadcrumb_path(url_root, "")),
                           tag("div", search_form(url_root, sym)))])
    for x in sym_search_in_filenames(url_root, sym):
        yield x
    proc = subprocess.Popen(
        ["sh", "-c",
         """ find -not -name "*.pyc" -and -not -name "*~" -and -not -name "#*#" -print0 | xargs --null grep -l -i "$1" """,
         "-", sym],
        stdout=subprocess.PIPE, bufsize=1024)
    matcher = SymSearch(sym)
    yield "<div class=all_matches>"
    for pipe_line in proc.stdout:
        filename = pipe_line.rstrip("\n\r")
        file_matches = False
        for line_no, line_out in matcher.match_file(url_root, filename):
            args = {"root": url_root,
                    "sym": sym,
                    "file": filename,
                    "line_no": line_no + 1}
            if not file_matches:
                file_matches = True
                yield ("<a href='%(root)s/file/%(file)s?sym=%(sym)s"
                       "#line%(line_no)i'>%(file)s:%(line_no)i</a>:"
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
            yield output_tag(format_sym_list(url_root, matcher.syms_found))
        if len(matcher.syms_found_ci) > 0:
            yield "with case relaxed:\n"
            yield output_tag(format_sym_list(url_root, matcher.syms_found_ci))

def format_sym_list(url_root, syms):
    body = []
    for symbol, count in sorted(syms.iteritems()):
        body.append(tag("li", 
                        tagp("a", [("href", "%s/sym/%s" % (url_root, symbol))],
                             symbol),
                        " (%i)" % count))
    return tag("ul", body)

def show_file_or_dir(url_root, filename, query):
    if os.path.isdir(fix_path(filename)):
        return show_dir(url_root, filename)
    else:
        return show_file(url_root, filename, query)

def show_file(url_root, filename, query):
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
        matcher = SymSearch(query["sym"])
        match_line_nos = []
        fh = open(filename, "r")
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

        matcher = SymSearch(query["sym"])
        fh = open(filename, "r")
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
        fh = open(filename, "r")
        try:
            yield "<pre class=code>"
            for line_no, line in enumerate(fh):
                yield "<a name='line%i'>" % (line_no + 1)
                for token, is_symbol in tokens(line):
                    if is_symbol:
                        yield link_token(url_root, token)
                    else:
                        yield cgi.escape(token)
            yield "</pre>"
        finally:
            fh.close()

def show_dir(url_root, path_orig):
    path = fix_path(path_orig)
    for x in stylesheet():
        yield x
    yield output_tag([tag("title", path),
                      tagp("div", [("class", "box")],
                           tag("div", breadcrumb_path(url_root, path_orig)),
                           tag("div", search_form(url_root, "")))])
    def format_entry(leafname):
        pathname = os.path.join(path, leafname)
        st = os.stat(pathname)
        if os.path.isdir(pathname):
            size = ""
        else:
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
                            for leafname in sorted(os.listdir(path))
                            if not exclude(leafname)])])

def exclude(leafname):
    regexps = [r"\.pyc$",
               r"^#.*#$",
               r"~"]
    for regexp in regexps:
        if re.search(regexp, leafname):
            return True
    return False

def fix_path(path):
    if path == "":
        return "."
    else:
        return path

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
                tagp("button", [("name", "search"),
                                ("type", "submit")],
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

def link_token(url_root, token):
    return "<a href='%(root)s/sym/%(sym)s'>%(sym)s</a>" % {"root": url_root,
                                                           "sym": token}


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
    options, args = parser.parse_args(argv)
    if len(args) != 0:
        parser.error("Unexpected arguments")
    os.chdir(options.dir_path)
    if options.do_cgi:
        wsgiref.handlers.CGIHandler().run(handle_request)
    else:
        httpd = wsgiref.simple_server.make_server("", options.port, handle_request)
        print "Listening on port %i" % options.port
        if options.do_once:
            httpd.handle_request()
        else:
            httpd.serve_forever()


if __name__ == "__main__":
    main(sys.argv[1:])
