'''
Created on Mar 27, 2014

@author: ignacio

4chan thread downloader.

Each thread has its own folder under MAIN_DIRECTORY/threads.

Example directory structure for thread an.1615086

threads/an.1615086
|-thread: This file contains the thread id (an.1615086)
|         This allows the folder to be renamed to something more human readable
|         (cute-animals for example) and still knowing where the thread came from
|-original: The original thread as downloaded from 4chan
|-1615086: The local thread with the links updated to work locally
|-images.html: A simple html with all the images from the thread
|-images: subfolder for images
|-thumbs: subfolder for thumbs
|-css: subfolder for css
\-js: subfolder for js

'''
from BeautifulSoup import BeautifulSoup
from argparse import ArgumentParser
from data import DataStorage
import logging
import os
import requests
import sys
import time
import tempfile
import shutil
import collections
import re
import datetime
import sys

MAIN_DIRECTORY = '/home/ignacio/misc/4chan/downchan'
THREADS_DIRECTORY = os.path.join(MAIN_DIRECTORY, "threads")
NOT_FOUND_FILE = os.path.join(MAIN_DIRECTORY, "404")

# Used to parse thread urls
RE_BOARD_THREAD_URL = "http://boards.4chan.org/(\w+)/res/(\d+)"

def _thread_url(board, thread):
    return "http://boards.4chan.org/%s/res/%s" % (board, thread)

def _parse_thread(thread_id):
    """ Parse a thread_id in one of the following formats:
     - URL: http://boards.4chan.org/<board>/res/<thread_id>
     - <board>.<thread_id>
     - <board>/<thread_id>

    <thread_id> should be an integer
    """
    mobj = re.search(RE_BOARD_THREAD_URL, thread_id)
    if mobj:
        return mobj.group(1), int(mobj.group(2))
    else:
        board, thread = re.split("[./]", thread_id, 1)
        return board, int(thread)

class NotFound(DataStorage):
    """ Class for persisting the list of threads which already died """
    def __init__(self, path):
        DataStorage.__init__(self, path, set())

def _get_arg_parser():
    parser = ArgumentParser()
    parser.add_argument("thread", type=str, nargs='*',
                        help='threads to download')
    parser.add_argument("-u", '--update',
                        action="store_true", default=False,
                        help='update current threads')
    parser.add_argument("-l", '--list',
                        action="store_true", default=False,
                        help='list current threads')
    return parser

def _parse_args():
    parser = _get_arg_parser()
    return parser.parse_args()

def _thread_file(output_dir):
    return os.path.join(output_dir, 'thread')

def _norm_url(url):
    """ Normalize a url, adding missing http scheme if needed. """
    if url.startswith('//'):
        url = 'http:%s' % url
    if not url.startswith('http://'):
        url = 'http://%s' % url
    return url

class DataExtractor():
    """ This class stores (url, local_file) pairs for downloading later.

    It supports the use of namespaces to separate different filetypes.

    For example url: http://example.com/this/is/a/image.jpg with namespace photos
    would be paired with local path photos/image.jpg.
    """

    def __init__(self):
        self._data = collections.defaultdict(list)

    def extract(self, url, namespace):
        """ Store the url and return the associated local path. """
        fname = url.rsplit("/", 1)[-1]
        outfile = os.path.join(namespace, fname)
        self._data[namespace].append((url, outfile))
        return outfile

    @property
    def data(self):
        return self._data

def _extract_downloads(soup):
    """ Extract downloads from a given parsed HTML thread. """
    extractor = DataExtractor()

    # Extract css stylesheets
    for link in soup.findAll('link'):
        if not link['href'].endswith('.rss'):  # rss file break things
            link['href'] = extractor.extract(link['href'], 'css')

    # Extract javascript files
    for script in soup.findAll('script'):
        try:
            script['src'] = extractor.extract(script['src'], 'js')
        except KeyError:
            pass

    # Extract thumbs and images
    for image in soup.findAll('a', {'class':'fileThumb'}):
        image.img['src'] = extractor.extract(image.img['src'], "thumbs")
        image['href'] = extractor.extract(image['href'], "images")

    return extractor.data

def _nice_size(size):
    UNITS = ['', 'K', 'M', 'G', 'T', 'P']
    index = 0
    while size > 1024 and index + 1 < len(UNITS):
        size /= 1024.0
        index += 1
    return "%.2f %sb" % (size, UNITS[index])

def _download(url, dest):
    """ Download the given url to the given destination.
    With progress line and everything.
    Destination file will be created only if download was completed.
    """
    parent = os.path.dirname(dest)
    if not os.path.isdir(parent):
        os.makedirs(parent)

    if os.path.isfile(dest):
        logging.info("'%s' is already downloaded", dest)
        return

    response = requests.get(_norm_url(url), stream=True)
    total_length = response.headers.get('content-length')

    with tempfile.NamedTemporaryFile("wb") as fout:
        if total_length is None:  # no content length header
            logging.info('No size received from response.')
            fout.write(response.content)
        else:
            dl = 0
            last_show = 0
            progress_data = []
            total_length = int(total_length)
            start_time = time.time()
            for data in response.iter_content():
                dl += len(data)
                fout.write(data)
                now = time.time()
                if now - last_show > 0.1:
                    progress_data.append((time.time(), dl))
                    progress_data = progress_data[-20:]
                    if len(progress_data) > 1:
                        st_time, st_size = progress_data[0]
                        en_time, en_size = progress_data[-1]
                        speed = (en_size - st_size) / (en_time - st_time)
                        eta = (total_length - dl) / speed
                        eta_line = "ETA: %s, (%s/s)" % (datetime.timedelta(seconds=eta), _nice_size(speed))
                    else:
                        eta_line = ""
                    pct = 100. * dl / total_length
                    sys.stdout.write("\r%s: %.3f%% of %s. %s" % (url, pct, _nice_size(total_length), eta_line))
                    sys.stdout.flush()
                    last_show = now
            total_time = time.time() - start_time
            total_speed = total_length / total_time
            eta_line = "TOTAL TIME: %s, (%s/s)" % (datetime.timedelta(seconds=total_time), _nice_size(total_speed))
            pct = 100. * dl / total_length
            print "\r%s: %.3f%% of %s. %s" % (url, pct, _nice_size(total_length), eta_line)
            sys.stdout.flush()

        # Sync the temporal file buffer before copying
        fout.flush()
        os.fsync(fout)
        logging.info("Copying temp file to final destination")
        shutil.copy(fout.name, dest)
        os.chmod(dest, 0664)  # Make file readable for apache (mode is 0600 by default)

def _embed(filename, alt=None):
    if filename.endswith(".webm"):
        return '<video src="%s" controls></video>' % filename;
    else:
        alt_text = 'alt="%s"' % alt if alt else ''
        return '<img src="%s" %s />' % (filename, alt_text)


def _process(thread_id, not_found, output_dir=None):
    """ Given a thread_id, download thread and missing files."""

    try:
        parsed = _parse_thread(thread_id)
    except:
        logging.exception("Problems parsing thread '%s'", thread_id)
        return

    if parsed in not_found:
        logging.info("'%s' has 404ed in the past. Skipping", parsed)
        return

    board, thread = parsed
    url = _thread_url(board, thread)

    logging.info("Downloading url '%s'", url)
    response = requests.get(_norm_url(url))
    logging.info("Downloaded")

    if response.status_code == 404:
        logging.info("%s: NOT FOUND", parsed)
        not_found.add(parsed)
    else:
        thread_id = "%s.%s" % (board, thread)

        # Set default output directory if missing
        if output_dir is None:
            output_dir = os.path.join(THREADS_DIRECTORY, thread_id)

        # Create output directory if missing
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir)

        # Write thread_id file
        with open(_thread_file(output_dir), 'w') as fout:
            fout.write(thread_id)


        logging.info("%s: thread is alive. Saving original...", parsed)
        original = response.text
        with open(os.path.join(output_dir, "original"), 'w') as fout:
            fout.write(original.encode('ascii', 'xmlcharrefreplace'))  # Encoding for unicode characters
        soup = BeautifulSoup(original)


        # Remove ads, TODO: FIX, not working right now
        for img in soup.findAll('img'):
            try:
                if '4chan-ads' in img['src']:
                    img['src'] = ''
            except KeyError:
                pass

        data = _extract_downloads(soup)

        logging.info("%s: Saving thread index file", parsed)
        with open(os.path.join(output_dir, str(thread)), 'w') as fout:
            print >> fout, soup.prettify()

        logging.info("%s: Saving images file", parsed)
        with open(os.path.join(output_dir, 'images.html'), 'w') as fout:
            for url, outfile in data['images']:
                print >> fout, _embed(outfile), "<br />"

        logging.info("%s: Saving thumbs file", parsed)
        with open(os.path.join(output_dir, 'thumbs.html'), 'w') as fout:
            for url, outfile in data['thumbs']:
                print >> fout, _embed(outfile)

        for namespace, downloads in data.items():
            logging.info("%s: Got %s things to download in namespace '%s'", parsed, len(downloads), namespace)
            to_download = []
            for url, outfile in downloads:
                fulldest = os.path.join(output_dir, outfile)
                if not os.path.isfile(fulldest):
                    to_download.append((url, fulldest))
            logging.info("%s: %s were already downloaded, %s are missing", parsed, len(downloads) - len(to_download), len(to_download))

            for i, (url, outfile) in enumerate(to_download):
                logging.info("%s: Downloads %s/%s: '%s'", parsed, i + 1, len(to_download), url)
                _download(url, os.path.join(output_dir, outfile))

class FourChanThread():
    def __init__(self, thread_id, subdir=None):
        try:
            parsed = _parse_thread(thread_id)
        except:
            logging.exception("Problems parsing thread '%s'", thread_id)
            raise ValueError("Invalid threadid : '%s'" % thread_id)

        self.board, self.thread = parsed
        self.thread_id = "%s.%s" % (self.board, self.thread)
        self.path = os.path.join(THREADS_DIRECTORY, subdir or self.thread_id)
        self.url = _thread_url(self.board, self.thread)

        if not os.path.isdir(self.path):
            logging.info("%s: Making directory '%s'", self.thread_id, self.path)
            os.makedirs(self.path)
        thread_file = _thread_file(self.path)
        if not os.path.isfile(thread_file):
            logging.info("%s: Writing thread_id file '%s'", self.thread_id, thread_file)
            with open(thread_file, 'w') as fout:
                print >> fout, self.thread_id


    @classmethod
    def from_subdir(cls, subdir):
        path = os.path.join(THREADS_DIRECTORY, subdir)
        if not os.path.isdir(path):
            raise ValueError("'%s' is not a valid directory" % (path,))
        thread_file = _thread_file(path)
        if not os.path.isfile(thread_file):
            raise ValueError("'%s' is not a valid file " % (thread_file,))
        return cls(open(thread_file).read().strip(), subdir=path)

    @classmethod
    def from_token(cls, token):
        try:
            board, thread = _parse_thread(token)
        except Exception:
            raise ValueError("Invalid thread token: '%s'" % (token,))
        thread_id = "%s.%s" % (board, thread)
        return cls(thread_id)

    def _original_file(self):
        return os.path.join(self.path, 'original')

    def update_original(self):
        logging.info("Downloading url '%s'", self.url)
        response = requests.get(_norm_url(self.url))
        logging.info("Downloaded")

        if response.status_code == 404:
            logging.info("%s: '%s' NOT FOUND", self.thread_id, self.url)
        else:
            logging.info("%s: thread is alive. Saving original...", self.thread_id)
            original = response.text
            with open(self._original_file(), 'w') as fout:
                fout.write(original.encode('ascii', 'xmlcharrefreplace'))  # Encoding for unicode characters
        return response.status_code

    def _write_images_file(self, fname, images, line_break=False):
        with open(fname, 'w') as fout:
            for src in images:
                print >> fout, _embed(src),
                if line_break:
                    print >> fout, "<br />"
                else:
                    print >> fout


    def download(self):
        with open(self._original_file()) as original:
            soup = BeautifulSoup(original.read())

        data = _extract_downloads(soup)

        logging.info("%s: Saving thread index file", self.thread_id)
        with open(os.path.join(self.path, str(self.thread)), 'w') as fout:
            print >> fout, soup.prettify()

        for image_type in ['images', 'thumbs']:
            logging.info("%s: Saving %s file", self.thread_id, image_type)
            fname = os.path.join(self.path, '%s.html' % (image_type,))
            images = [src for url, src in data[image_type]]
            self._write_images_file(fname, images, line_break=image_type == 'images')

        for namespace, downloads in data.items():
            logging.info("%s: Got %s things to download in namespace '%s'", self.thread_id, len(downloads), namespace)
            to_download = []
            for url, outfile in downloads:
                fulldest = os.path.join(self.path, outfile)
                if not os.path.isfile(fulldest):
                    to_download.append((url, fulldest))
            logging.info("%s: %s were already downloaded, %s are missing", self.thread_id, len(downloads) - len(to_download), len(to_download))

            for i, (url, outfile) in enumerate(to_download):
                logging.info("%s: Downloads %s/%s: '%s'", self.thread_id, i + 1, len(to_download), url)
                _download(url, os.path.join(self.path, outfile))

def _get_all_threads():
    return [FourChanThread.from_subdir(subdir) for subdir in sorted(os.listdir(THREADS_DIRECTORY))]

def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    logging.getLogger('requests').setLevel(logging.WARN)  # Kill request info logging

    if not os.path.isdir(THREADS_DIRECTORY):
        os.makedirs(THREADS_DIRECTORY)

    options = _parse_args()

    if not (options.thread or options.update or options.list):
        _get_arg_parser().print_help()
        sys.exit(1)

    if options.list:
        logging.info("Current threads:")
        threads = _get_all_threads()
        if threads:
            max_len = max(len(os.path.basename(t.path)) for t in threads)
            format_str = " - %%%ds - %%s" % (max_len)
            for thread in threads:
                logging.info(format_str, os.path.basename(thread.path), thread.url)
    else:
        with NotFound(os.path.join(NOT_FOUND_FILE)) as not_found:
            new_threads = []
            for token in options.thread:
                logging.info("Initializing thread: '%s'" % token)
                thread = FourChanThread(token)
                new_threads.append(thread)

            threads_to_update = _get_all_threads() if options.update else new_threads

            live_threads = [thread for thread in threads_to_update if not thread.thread_id in not_found]

            logging.info("I have %s/%s threads to update", len(live_threads), len(threads_to_update))
            for thread in live_threads:
                if thread.update_original() == 404:
                    not_found.add(thread.thread_id)
                thread.download()



if __name__ == "__main__":
    main()
