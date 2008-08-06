
import cStringIO as StringIO
import cgi
import os
import pprint
import re
import subprocess
import sys
import wsgiref.simple_server


css_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "styles.css")

def handle_request(environ, start_response):
    path = environ["PATH_INFO"]
    query_list = parse_query(environ["QUERY_STRING"])
    query = dict(query_list)
    host_url = "http://%s" % environ["HTTP_HOST"]
    if path == "/":
        start_response("200 OK", [("Content-Type", "text/html")])
        return ["<pre>", str(query), pprint.pformat(environ)]
    if path == "/search":
        start_response("302 OK",
                       [("Location", "%s/sym/%s"
                         % (host_url, query["sym"]))])
        return ()
    empty, elt, rest = path.split("/", 2)
    if elt == "sym":
        start_response("200 OK", [("Content-Type", "text/html")])
        return sym_search(rest)
    elif elt == "file":
        filename = rest
        if (filename != "" and not filename.endswith("/") and
            os.path.isdir(filename)):
            start_response("302 OK",
                           [("Location", "%s/file/%s/" % (host_url, filename))])
            return ()
        else:
            start_response("200 OK", [("Content-Type", "text/html")])
            return show_file_or_dir(filename)
    else:
        start_response("404 Not found", [("Content-Type", "text/html")])
        return ["404 Not found"]

# There must be a library function that does this and handles quoted
# chars properly...
def parse_query(query):
    if query == "":
        return []
    else:
        return [elt.split("=", 1) for elt in query.split("&")]

def stylesheet():
    fh = open(css_file, "r")
    try:
        yield "<style type='text/css'>\n"
        yield fh.read()
        yield "</style>\n"
    finally:
        fh.close()

def sym_search_in_filenames(sym):
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
            yield ("<a href='/file/%s'>%s</a>\n"
                   % (filename, text))
    yield "</pre>"

def sym_search(sym):
    for x in stylesheet():
        yield x
    yield output_tag([tag("title", "symbol: ", sym),
                      tagp("div", [("class", "box")],
                           tag("div", breadcrumb_path("")),
                           tag("div", search_form(sym)))])
    for x in sym_search_in_filenames(sym):
        yield x
    proc = subprocess.Popen(
        ["sh", "-c",
         """ find -not -name "*.pyc" | xargs grep -l -i "$1" """,
         "-", sym],
        stdout=subprocess.PIPE, bufsize=1024)
    sym_regexp = re.compile(re.escape(sym))
    sym_regexp_ci = re.compile(re.escape(sym), re.IGNORECASE)
    syms_found = {}
    syms_found_ci = {}
    yield "<pre class=code>"
    for pipe_line in proc.stdout:
        filename = pipe_line.rstrip("\n\r")
        fh = open(filename, "r")
        try:
            for line_no, line in enumerate(fh):
                line = line.rstrip("\n\r")
                # Regexp search is an optimisation: could be removed
                if sym_regexp.search(line):
                    does_match = False
                    line_out = []
                    for token, is_symbol in tokens(line):
                        if token == sym:
                            line_out.append("<strong>%s</strong>" % token)
                            does_match = True
                        elif is_symbol:
                            line_out.append(link_token(token))
                            if sym_regexp.search(token):
                                syms_found[token] = syms_found.get(token, 0) + 1
                            elif sym_regexp_ci.search(token):
                                syms_found_ci[token] = syms_found_ci.get(token, 0) + 1
                        else:
                            line_out.append(cgi.escape(token))
                    if does_match:
                        yield ("<a href='/file/%(file)s#line%(line_no)i'>"
                               "%(file)s:%(line_no)i</a>:"
                               % {"file": filename,
                                  "line_no": line_no + 1})
                        for x in line_out:
                            yield x
                        yield "\n"
        finally:
            fh.close()
    yield "</pre>"
    yield "<hr>Other symbols found:\n"
    if (len(syms_found) == 0 and
        len(syms_found_ci) == 0):
        yield "none"
    else:
        if len(syms_found) > 0:
            yield output_tag(format_sym_list(syms_found))
        if len(syms_found_ci) > 0:
            yield "with case relaxed:\n"
            yield output_tag(format_sym_list(syms_found_ci))

def format_sym_list(syms):
    body = []
    for symbol, count in sorted(syms.iteritems()):
        body.append(tag("li", 
                        tagp("a", [("href", "/sym/%s" % symbol)],
                             symbol),
                        " (%i)" % count))
    return tag("ul", body)

def show_file_or_dir(filename):
    if os.path.isdir(fix_path(filename)):
        return show_dir(filename)
    else:
        return show_file(filename)

def show_file(filename):
    for x in stylesheet():
        yield x
    links = [tag("div", tagp("a", [("href", url)], name))
             for name, url in get_file_links(filename)]
    yield output_tag([tag("title", filename),
                      tagp("div", [("class", "box")],
                           tag("div", breadcrumb_path(filename)),
                           tag("div", search_form("")),
                           links)])
    fh = open(filename, "r")
    try:
        yield "<pre class=code>"
        for line_no, line in enumerate(fh):
            yield "<a name='line%i'>" % (line_no + 1)
            for token, is_symbol in tokens(line):
                if is_symbol:
                    yield link_token(token)
                else:
                    yield cgi.escape(token)
        yield "</pre>"
    finally:
        fh.close()

def show_dir(path_orig):
    path = fix_path(path_orig)
    for x in stylesheet():
        yield x
    yield output_tag([tag("title", path),
                      tagp("div", [("class", "box")],
                           tag("div", breadcrumb_path(path_orig)),
                           tag("div", search_form("")))])
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
    yield output_tag([breadcrumb_path(path),
                      tagp("table", [("class", "dirlist")],
                           tag("tr",
                               tagp("th", [("class", "file-size")], "size"),
                               tagp("th", [("class", "file-name")], "name")),
                           [format_entry(leafname)
                            for leafname in sorted(os.listdir(path))
                            if not exclude(leafname)])])

def exclude(leafname):
    return re.search(r"\.pyc$", leafname)

def fix_path(path):
    if path == "":
        return "."
    else:
        return path

def search_form(default_sym):
    script = """
window.onload = function () {
    document.getElementById("form_field").focus();
}
"""
    return tagp("form", [("action", "/search"),
                         ("method", "get")],
                tagp("input", [("id", "form_field"),
                               ("type", "text"),
                               ("name", "sym"),
                               ("value", default_sym)]),
                tagp("button", [("name", "search"),
                                ("type", "submit")],
                     "Go"),
                tagp("script", [("language", "javascript")], script))

def breadcrumb_path(path):
    crumbs = [tagp("a", [("href", "/file/")], "[top]")]
    path_got = ""
    for element in path.split("/"):
        path_got = os.path.join(path_got, element)
        crumbs.append(["/",
                       tagp("a", [("href", "/file/%s" % path_got)],
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

def link_token(token):
    return "<a href='/sym/%(sym)s'>%(sym)s</a>" % {"sym": token}


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


def main(args):
    port = 8000
    once = False
    while len(args) > 0:
        arg = args.pop(0)
        if arg == "--dir":
            os.chdir(args.pop(0))
        elif arg == "--once":
            once = True
        elif arg == "--port":
            port = int(args.pop(0))
        else:
            raise Exception("Unknown argument: %s" % arg)
    httpd = wsgiref.simple_server.make_server('', port, handle_request)
    print "Listening on port %i" % port
    if once:
        httpd.handle_request()
    else:
        httpd.serve_forever()

if __name__ == "__main__":
    main(sys.argv[1:])
