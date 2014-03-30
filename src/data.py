import logging
import cPickle
import os

_LOG = logging.getLogger('downchan.data')

def _mkparent_and_open(fname, mode=None):
    dirname = os.path.dirname(fname)
    mode = mode or 'w'
    if not os.path.isdir(dirname):
        _LOG.info("Making directory: '%s'", dirname)
        try:
            os.makedirs(dirname)
        except OSError:
            _LOG.exception("Problems making directory '%s'", dirname)
    return open(fname, mode)

class DataStorage():
    """
    Class for persisting data in a file.

    Sample usage:

    >>> with DataStorage('/path/to/file', {}) as data:
    >>>     data['key'] = 'value'

    Data will be persisted when the `with` block finishes its execution, or
    it can be forced via the `save` method

    If the with statement block does not suit your needs, loading and saving
    can be done by hand:

    >>> storage = DataStorage('path/to/file', collections.defaultdict(int))
    >>> data = storage.data
    >>> data['test'] += 10
    >>> count_things(data)
    >>> data.save()

    If the file does not exist, the second argument will be assigned as default.

    WARNING: data is persisted with the `cPickle` module, so some types cannot be
    persisted. Refer to the `pickle docs <http://docs.python.org/2/library/pickle.html>`_
    for further information.

    """

    def __init__(self, path, default):
        """

        Create a new data Storage

        @param path: where to persist the data
        @param default: value to assign if file is missing

        """
        self._path = path
        self._default = default
        self._data = self._load()

    @property
    def data(self):
        return self._data

    def __enter__(self):
        return self._data

    def __exit__(self, _type, _value, _traceback):
        self.exit()

    def exit(self):
        _LOG.info("Saving on DataStorage deletion")
        self.save()

    def _load(self):
        ''' Load data from file '''
        if not os.path.isfile(self._path):
            _LOG.info("'%s' is not a valid file. Returning default", self._path)
            return self._default

        try:
            _LOG.info("Unpickling data from '%s'", self._path)
            with open(self._path) as fin:
                return cPickle.load(fin)
        except (IOError, ValueError):
            _LOG.exception("Problems loading file '%s'", self._path)
            return None

    def save(self):
        """ Save the data to disk """
        if self._data is None:
            return
        _LOG.info("Saving DataStorage to '%s'...", self._path)
        with _mkparent_and_open(self._path) as fout:
            cPickle.dump(self._data, fout)
        _LOG.info("Saved.")
