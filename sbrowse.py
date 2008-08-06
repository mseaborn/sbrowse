
import cStringIO as StringIO
import cgi
import os
import pprint
import re
import subprocess
import sys
import wsgiref.simple_server


def handle_request(environ, start_response):
    path = environ["PATH_INFO"]
    empty, elt, rest = path.split("/", 2)
    if elt == "sym":
        start_response("200 OK", [("Content-Type", "text/html")])
        return sym_search(rest)
    elif elt == "file":
        start_response("200 OK", [("Content-Type", "text/html")])
        return show_file(rest)
    else:
        start_response("404 Not found", [("Content-Type", "text/html")])
        return ["404 Not found"]

def sym_search(sym):
    proc = subprocess.Popen(
        ["sh", "-c",
         """ find -not -name "*.pyc" | xargs grep -l -i "$1" """,
         "-", sym],
        stdout=subprocess.PIPE)
    sym_regexp = re.compile(re.escape(sym))
    sym_regexp_ci = re.compile(re.escape(sym), re.IGNORECASE)
    syms_found = {}
    syms_found_ci = {}
    yield "<pre>"
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

def show_file(filename):
    fh = open(filename, "r")
    try:
        yield "<pre>"
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


if __name__ == "__main__":
    httpd = wsgiref.simple_server.make_server('', 9000, handle_request)
    print "Listening on port 9000"
    os.chdir("/home/mseaborn/data/cvs/grieg/conductor/src")
    if "--once" in sys.argv:
        httpd.handle_request()
    else:
        httpd.serve_forever()
