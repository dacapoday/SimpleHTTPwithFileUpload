#!/usr/bin/env python3

"""Simple HTTP Server With Upload.

Modified from the standard library http.server
Added file upload function

"""

__version__ = "0.1"
__all__ = ["SimpleHTTPwithUploadRequestHandler"]
__author__ = "dacapoday"

import argparse
import html
import io
import mimetypes
import os
import posixpath
import re
import shutil
import sys
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer


class SimpleHTTPwithUploadRequestHandler(BaseHTTPRequestHandler):

    """Simple HTTP request handler with GET/POST/HEAD commands.

    This serves files from the current directory and any of its
    subdirectories.  The MIME type for files is determined by
    calling the .guess_type() method. And can reveive file 
    uploaded by client.

    The GET and HEAD requests are identical except that the HEAD
    request omits the actual contents of the file.

    """

    server_version = "SimpleHTTPwithUpload/" + __version__

    def do_GET(self):
        """Serve a GET request."""
        f = self.send_head()
        if f:
            try:
                self.copyfile(f, self.wfile)
            finally:
                f.close()

    def do_HEAD(self):
        """Serve a HEAD request."""
        f = self.send_head()
        if f:
            f.close()

    def do_POST(self):
        """Serve a POST request."""
        result, info = self.handle_upload()
        f = self.send_result_head(result, info)
        if f:
            try:
                self.copyfile(f, self.wfile)
            finally:
                f.close()

    def handle_upload(self):
        """Handling POST request. Only accept file upload, and only the first file will be saved.
        """
        content_type = self.headers['content-type']
        if not content_type:
            return (False, "Missing Content-Type header")

        isUploadFile = False
        boundary = bytes()
        for item in content_type.split(";"):
            if "multipart/form-data" in item:
                isUploadFile = True
                continue

            kv = item.split("=")
            if len(kv) != 2:
                continue

            if "boundary" in kv[0]:
                boundary = kv[1].encode("ascii")

        if not isUploadFile:
            return (False, "Content-Type header should be multipart/form-data")

        if not boundary:
            return (False, "Content-Type header missing boundary")

        remainder = int(self.headers['content-length'])

        line = self.rfile.readline()
        remainder -= len(line)
        if not boundary in line:
            return (False, "Content missing boundary")

        line = self.rfile.readline()
        remainder -= len(line)
        lined = line.decode()
        filename = re.findall(
            r'Content-Dispo\w+.*name="file";\s?fil\w+="(.+)"', lined)
        if not filename:
            return (False, "Unable to determine file name...")
        path = self.translate_path(self.path)
        path = os.path.join(path, filename[0])

        line = self.rfile.readline()
        remainder -= len(line)
        # TODO check file's Content-Type.

        line = self.rfile.readline()
        remainder -= len(line)
        # just a CRLF .
        # TODO make sure it is a CRLF and use it as file begin flag.

        buffer = io.BytesIO()
        line = self.rfile.readline()
        remainder -= len(line)
        if boundary not in line:
            while True:
                nextline = self.rfile.readline()
                remainder -= len(nextline)
                if boundary in nextline:
                    line = line[0:-1]
                    if line.endswith(b'\r'):
                        line = line[0:-1]
                    buffer.write(line)
                    break
                else:
                    buffer.write(line)
                    line = nextline

                if remainder <= 0:
                    buffer.close()
                    return (False, " Unexpected end of data.")

        buffer.seek(0)

        try:
            out = open(path, 'wb')
        except OSError:
            return (False, "Unable to create file in %s ." % path)

        try:
            self.copyfile(buffer, out)
        finally:
            buffer.close()
            out.close()

        return (True, "Upload success! File save in %s ." % path)

    def send_result_head(self, result, info):
        """Responses to the upload results
        """
        title = "Failed"
        if result:
            title = "Success"
            print("Success uploaded by: {}".format(self.client_address))

        r = []
        r.append('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
                 '"http://www.w3.org/TR/html4/strict.dtd">')
        r.append('<html>\n<head>')
        r.append('<meta http-equiv="Content-Type" '
                 'content="text/html; charset="utf-8">')
        r.append('<title>%s</title>\n</head>' % title)
        r.append('<body>\n<h1>%s</h1>' % title)
        r.append('<hr>\n<strong>%s</strong>' % info)
        r.append('</body>\n</html>\n')

        encoded = '\n'.join(r).encode("utf-8", "surrogateescape")
        f = io.BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-type", "text/html;charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f

    def send_head(self):
        """Common code for GET and HEAD commands.

        This sends the response code and MIME headers.

        Return value is either a file object (which has to be copied
        to the outputfile by the caller unless the command was HEAD,
        and must be closed by the caller under all circumstances), or
        None, in which case the caller has nothing further to do.

        """
        path = self.translate_path(self.path)
        f = None
        if os.path.isdir(path):
            parts = urllib.parse.urlsplit(self.path)
            if not parts.path.endswith('/'):
                # redirect browser - doing basically what apache does
                self.send_response(HTTPStatus.MOVED_PERMANENTLY)
                new_parts = (parts[0], parts[1], parts[2] + '/',
                             parts[3], parts[4])
                new_url = urllib.parse.urlunsplit(new_parts)
                self.send_header("Location", new_url)
                self.end_headers()
                return None
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
            else:
                return self.list_directory(path)
        ctype = self.guess_type(path)
        try:
            f = open(path, 'rb')
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-type", ctype)
            fs = os.fstat(f.fileno())
            self.send_header("Content-Length", str(fs[6]))
            self.send_header(
                "Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()
            return f
        except:
            f.close()
            raise

    def list_directory(self, path):
        """Helper to produce a directory listing (absent index.html).

        Return value is either a file object, or None (indicating an
        error).  In either case, the headers are sent, making the
        interface the same as for send_head().

        """
        try:
            list = os.listdir(path)
        except OSError:
            self.send_error(
                HTTPStatus.NOT_FOUND,
                "No permission to list directory")
            return None
        list.sort(key=lambda a: a.lower())
        r = []
        try:
            displaypath = urllib.parse.unquote(self.path,
                                               errors='surrogatepass')
        except UnicodeDecodeError:
            displaypath = urllib.parse.unquote(path)
        displaypath = html.escape(displaypath, quote=False)
        enc = sys.getfilesystemencoding()
        title = 'Directory listing for %s' % displaypath
        r.append('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
                 '"http://www.w3.org/TR/html4/strict.dtd">')
        r.append('<html>\n<head>')
        r.append('<meta http-equiv="Content-Type" '
                 'content="text/html; charset=%s">' % enc)
        r.append('<title>%s</title>\n</head>' % title)
        r.append('<body>\n<h1>%s</h1>' % title)
        r.append('<hr>\n<form ENCTYPE="multipart/form-data" method="post">')
        r.append('<input name="file" type="file"/>')
        r.append('<input type="submit" value="upload"/>\n</form>')
        r.append('<hr>\n<ul>')
        for name in list:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            # Append / for directories or @ for symbolic links
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = name + "/"
            if os.path.islink(fullname):
                displayname = name + "@"
                # Note: a link to a directory displays with @ and links with /
            r.append('<li><a href="%s">%s</a></li>'
                     % (urllib.parse.quote(linkname,
                                           errors='surrogatepass'),
                        html.escape(displayname, quote=False)))
        r.append('</ul>\n<hr>\n</body>\n</html>\n')
        encoded = '\n'.join(r).encode(enc, 'surrogateescape')
        f = io.BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-type", "text/html; charset=%s" % enc)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f

    def translate_path(self, path):
        """Translate a /-separated PATH to the local filename syntax.

        Components that mean special things to the local file system
        (e.g. drive or directory names) are ignored.  (XXX They should
        probably be diagnosed.)

        """
        # abandon query parameters
        path = path.split('?', 1)[0]
        path = path.split('#', 1)[0]
        # Don't forget explicit trailing slash when normalizing. Issue17324
        trailing_slash = path.rstrip().endswith('/')
        try:
            path = urllib.parse.unquote(path, errors='surrogatepass')
        except UnicodeDecodeError:
            path = urllib.parse.unquote(path)
        path = posixpath.normpath(path)
        words = path.split('/')
        words = filter(None, words)
        path = os.getcwd()
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                # Ignore components that are not a simple file/directory name
                continue
            path = os.path.join(path, word)
        if trailing_slash:
            path += '/'
        return path

    def copyfile(self, source, outputfile):
        """Copy all data between two file objects.

        The SOURCE argument is a file object open for reading
        (or anything with a read() method) and the DESTINATION
        argument is a file object open for writing (or
        anything with a write() method).

        The only reason for overriding this would be to change
        the block size or perhaps to replace newlines by CRLF
        -- note however that this the default server uses this
        to copy binary data as well.

        """
        shutil.copyfileobj(source, outputfile)

    def guess_type(self, path):
        """Guess the type of a file.

        Argument is a PATH (a filename).

        Return value is a string of the form type/subtype,
        usable for a MIME Content-type header.

        The default implementation looks the file's extension
        up in the table self.extensions_map, using application/octet-stream
        as a default; however it would be permissible (if
        slow) to look inside the data to make a better guess.

        """

        base, ext = posixpath.splitext(path)
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        ext = ext.lower()
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        else:
            return self.extensions_map['']

    if not mimetypes.inited:
        mimetypes.init()  # try to read system mime.types
    extensions_map = mimetypes.types_map.copy()
    extensions_map.update({
        '': 'application/octet-stream',  # Default
        '.py': 'text/plain',
        '.c': 'text/plain',
        '.h': 'text/plain',
    })


def test(HandlerClass, ServerClass=HTTPServer, protocol="HTTP/1.0", port=8000, bind=""):
    """Test the HTTP request handler class.

    This runs an HTTP server on port 8000 (or the port argument).

    """
    server_address = (bind, port)

    HandlerClass.protocol_version = protocol
    httpd = ServerClass(server_address, HandlerClass)
    sa = httpd.socket.getsockname()
    serve_message = "Serving HTTP on {host} port {port} (http://{host}:{port}/) ..."
    print(serve_message.format(host=sa[0], port=sa[1]))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, exiting.")
        sys.exit(0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', '-b', default='', metavar='ADDRESS',
                        help='Specify alternate bind address '
                             '[default: all interfaces]')
    parser.add_argument('port', action='store',
                        default=8000, type=int,
                        nargs='?',
                        help='Specify alternate port [default: 8000]')
    args = parser.parse_args()
    handler_class = SimpleHTTPwithUploadRequestHandler
    test(HandlerClass=handler_class, port=args.port, bind=args.bind)
