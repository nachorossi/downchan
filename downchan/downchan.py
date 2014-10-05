r'''
Created on Mar 27, 2014

@author: ignacio

4chan thread downloader.

Each thread has its own folder under MAIN_DIRECTORY/threads.

Example directory structure for thread an.1615086

threads/an.1615086
|-thread: This file contains the thread id (an.1615086)
|         This allows the folder to be renamed to something more human readable
|         (i.e. cute-animals) and still knowing where the thread came from
|-original: The original thread as downloaded from 4chan
|-1615086: The local thread with the links updated to work locally
|-images.html: A simple html with all the images from the thread
|-images: subfolder for images
|-thumbs: subfolder for thumbs
|-css: subfolder for css
\-js: subfolder for js

'''
import collections
import datetime
import logging
import os
import requests
import shutil
import tempfile
import time
import sys
from argparse import ArgumentParser
from BeautifulSoup import BeautifulSoup

from .data import DataStorage
from .common import MAIN_DIRECTORY, THREADS_DIRECTORY
from .chanthread import FourChanThread

NOT_FOUND_FILE = os.path.join(MAIN_DIRECTORY, "404")


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

    For example url: http://example.com/this/is/a/image.jpg with namespace
    photos would be paired with local path photos/image.jpg.
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
    for image in soup.findAll('a', {'class': 'fileThumb'}):
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
                        eta_line = ("ETA: %s, (%s/s)" % (
                            datetime.timedelta(seconds=eta),
                            _nice_size(speed)
                        ))
                    else:
                        eta_line = ""
                    pct = 100. * dl / total_length
                    sys.stdout.write("\r%s: %.3f%% of %s. %s" % (
                        url, pct, _nice_size(total_length),
                        eta_line
                    ))
                    sys.stdout.flush()
                    last_show = now
            total_time = time.time() - start_time
            total_speed = total_length / total_time
            eta_line = ("TOTAL TIME: %s, (%s/s)" % (
                datetime.timedelta(seconds=total_time),
                _nice_size(total_speed)
            ))
            pct = 100. * dl / total_length
            print ("\r%s: %.3f%% of %s. %s" % (
                url, pct, _nice_size(total_length), eta_line
            ))
            sys.stdout.flush()

        # Sync the temporal file buffer before copying
        fout.flush()
        os.fsync(fout)
        logging.info("Copying temp file to final destination")
        shutil.copy(fout.name, dest)
        os.chmod(dest, 0664)  # Make file readable for apache (default is 0600)


def _embed(filename, alt=None):
    if filename.endswith(".webm"):
        return '<video src="%s" controls></video>' % filename
    else:
        alt_text = 'alt="%s"' % alt if alt else ''
        return '<img src="%s" %s />' % (filename, alt_text)


def _write_images_file(fname, images, line_break=False):
    with open(fname, 'w') as fout:
        for src in images:
            print >> fout, _embed(src),
            if line_break:
                print >> fout, "<br />"
            else:
                print >> fout


def _original_file(thread):
    return os.path.join(thread.path, 'original')


def update_original(thread):
    url = thread.url()
    label = os.path.basename(thread.path)
    logging.info("Downloading url '%s'", url)
    response = requests.get(_norm_url(url))
    logging.info("Downloaded")

    if response.status_code == 404:
        logging.info("%s: '%s' NOT FOUND", label, thread.url())
    else:
        logging.info("%s: thread is alive. Saving original...", label)
        original = response.text
        with open(_original_file(thread), 'w') as fout:
            # Encoding for unicode characters
            fout.write(original.encode('ascii', 'xmlcharrefreplace'))
    return response.status_code


def update_thread_file(thread):
    label = os.path.basename(thread.path)
    with open(_original_file(thread)) as original:
        soup = BeautifulSoup(original.read())

    data = _extract_downloads(soup)

    logging.info("%s: Saving thread index file", label)
    with open(os.path.join(thread.path, str(thread.thread_no)), 'w') as fout:
        print >> fout, soup.prettify()

    return data


def download_thread(thread):
    label = os.path.basename(thread.path)

    data = update_thread_file(thread)

    for image_type in ['images', 'thumbs']:
        logging.info("%s: Saving %s file", label, image_type)
        fname = os.path.join(thread.path, '%s.html' % (image_type,))
        images = [src for url, src in data[image_type]]
        _write_images_file(fname, images, line_break=image_type == 'images')

    to_download = []
    total_downloads = 0
    namespaces = collections.defaultdict(int)
    for namespace, downloads in data.items():
        total_downloads += len(downloads)
        for url, outfile in downloads:
            fulldest = os.path.join(thread.path, outfile)
            if not os.path.isfile(fulldest):
                to_download.append((url, fulldest))
                namespaces[namespace] += 1
    logging.info("%s downloads: %s were already downloaded, %s are missing "
                 "(%s)", total_downloads, total_downloads - len(to_download),
                 len(to_download), dict(namespaces))

    for i, (url, outfile) in enumerate(to_download):
        logging.info("%s: Downloads %s/%s: '%s'", label, i + 1,
                     len(to_download), url)
        _download(url, outfile)


def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    # Kill request info logging
    logging.getLogger('requests').setLevel(logging.WARN)

    if not os.path.isdir(THREADS_DIRECTORY):
        os.makedirs(THREADS_DIRECTORY)

    options = _parse_args()

    if not (options.thread or options.update or options.list):
        _get_arg_parser().print_help()
        sys.exit(1)

    if options.list:
        logging.info("Current threads:")
        threads = FourChanThread.all()
        if threads:
            max_len = max(len(os.path.basename(t.path)) for t in threads)
            format_str = " - %%%ds - %%s" % (max_len)
            for thread in threads:
                logging.info(format_str, os.path.basename(thread.path),
                             thread.url())
    else:
        with NotFound(os.path.join(NOT_FOUND_FILE)) as not_found:
            new_threads = []
            for token in options.thread:
                logging.info("Initializing thread: '%s'", token)
                thread = FourChanThread.from_token(token)
                thread.init()
                new_threads.append(thread)

            threads_to_update = (list(FourChanThread.all()) if options.update
                                 else new_threads)

            live_threads = [thread for thread in threads_to_update if
                            (thread.board, thread.thread_no) not in not_found]

            logging.info("I have %s/%s threads to update", len(live_threads),
                         len(threads_to_update))
            for thread in live_threads:
                if update_original(thread) == 404:
                    not_found.add((thread.board, thread.thread_no))
                download_thread(thread)


if __name__ == "__main__":
    main()
