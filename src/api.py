'''
Created on Apr 20, 2014

@author: ignacio
'''

import requests
from collections import namedtuple

_BASE_URL = "http://a.4cdn.org/"


def get_boards():
    api_url = "{}/boards.json".format(_BASE_URL)
    api_json = requests.get(api_url).json()
    return set(b['board'] for b in api_json['boards'])

ThreadData = namedtuple("ThreadData", ['no', 'com', 'sub', 'url',
                                       'semantic_url'])


class Catalog():

    def __init__(self, board):
        self._board = board
        api_url = "{}/{}/catalog.json".format(_BASE_URL, board)
        self._api_json = requests.get(api_url).json()

    def threads(self):
        for page in self._api_json:
            for thread in page['threads']:
                thread_no = thread.get('no')
                yield ThreadData(
                    no=thread_no,
                    com=thread.get('com', None),
                    sub=thread.get('sub', None),
                    url="http://boards.4chan.org/{}/thread/{}/{}".format(
                        self._board,
                        thread_no,
                        thread.get('semantic_url')
                    ),
                    semantic_url=thread.get('semantic_url'),
                )

    @property
    def board(self):
        return self._board


def get_threads_json(board):
    api_url = "{}/{}/threads.json".format(_BASE_URL, board)
    return requests.get(api_url).json()
