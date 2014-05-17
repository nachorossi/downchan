# Used to parse thread urls
import logging
import os
import re
from common import THREADS_DIRECTORY, STATIC_DIRECTORY, STATIC_NAMESPACES

RE_BOARD_THREAD_URL = "http://boards.4chan.org/(\w+)/res/(\d+)"


class FourChanThread():
    TOKEN_FNAME = '.downchan.thread.token'

    def __init__(self, board, thread_no, subdir=None, slug=None):
        self._board = board
        self._thread_no = thread_no
        self._thread_id = "%s.%s" % (self._board, self._thread_no)
        self._path = os.path.join(THREADS_DIRECTORY,
                                  subdir or self._get_default_dir(slug))

    def init(self):
        if not os.path.isdir(self._path):
            logging.info("%s: Making directory '%s'", self._thread_id,
                         self._path)
            os.makedirs(self._path)
        thread_file = self._token_file(self._path)
        if not os.path.isfile(thread_file):
            logging.info("%s: Writing thread_id file '%s'", self._thread_id,
                         thread_file)
            with open(thread_file, 'w') as fout:
                print >> fout, self._thread_id
        for namespace in STATIC_NAMESPACES:
            static_dir = os.path.join(self._path, namespace)
            if not os.path.exists(static_dir):
                source = os.path.join(STATIC_DIRECTORY, namespace)
                if not os.path.isdir(source):
                    logging.info("Creating global static directory: '%s'",
                                 source)
                    os.makedirs(source)
                logging.info("Linking static dir: %s -> %s", source,
                             static_dir)
                os.symlink(source, static_dir)

    @property
    def path(self):
        return self._path

    @property
    def board(self):
        return self._board

    @property
    def thread_no(self):
        return self._thread_no

    def url(self):
        return ("http://boards.4chan.org/{0.board}/thread/"
                "{0.thread_no}".format(self))

    def _get_default_dir(self, slug):
        thread_dir = ("{}-{}".format(self._thread_no, slug) if slug
                      else str(self._thread_no))
        return os.path.join(self._board, thread_dir)

    @classmethod
    def _token_file(cls, path):
        return os.path.join(path, cls.TOKEN_FNAME)

    @staticmethod
    def _parse_token(token):
        """ Parse a thread_id in one of the following formats:
         - URL: http://boards.4chan.org/<board>/res/<thread_id>
         - <board>.<thread_id>
         - <board>/<thread_id>

        <thread_id> should be an integer
        """
        mobj = re.search(RE_BOARD_THREAD_URL, token)
        if mobj:
            return mobj.group(1), int(mobj.group(2))
        else:
            board, thread = re.split("[./]", token, 1)
            return board, int(thread)

    @classmethod
    def from_subdir(cls, subdir):
        path = os.path.join(THREADS_DIRECTORY, subdir)
        if not os.path.isdir(path):
            raise ValueError("'%s' is not a valid directory" % (path,))
        thread_file = cls._token_file(path)
        if not os.path.isfile(thread_file):
            raise ValueError("'%s' is not a valid file " % (thread_file,))
        token = open(thread_file).read().strip()
        board, thread_no = cls._parse_token(token)
        return cls(board, thread_no, subdir=path)

    @classmethod
    def from_token(cls, token):
        try:
            board, thread_no = cls._parse_token(token)
        except Exception:
            raise ValueError("Invalid thread token: '%s'" % (token,))
        return cls(board, thread_no)

    @classmethod
    def all(cls):
        return cls._extract_threads(THREADS_DIRECTORY)

    @classmethod
    def _extract_threads(cls, root_dir):
        if os.path.isfile(cls._token_file(root_dir)):
            yield cls.from_subdir(root_dir)
        else:
            for subdir in os.listdir(root_dir):
                path = os.path.join(root_dir, subdir)
                if os.path.isdir(path):
                    for thread in cls._extract_threads(path):
                        yield thread
