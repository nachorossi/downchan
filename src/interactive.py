from __future__ import unicode_literals
from common import MAIN_DIRECTORY
from data import DataStorage
from chanthread import FourChanThread
import os
import time
import api

DATA_DIRECTORY = os.path.join(MAIN_DIRECTORY, 'data')


class TimeDict(dict):

    def touch(self, key):
        self[key] = time.time()

    def newest(self, keys=None):
        return self._sorted(keys, reverse=True)

    def oldest(self, keys=None):
        print "oldest:{}".format(keys)
        return self._sorted(keys, reverse=False)

    def _sorted(self, keys, reverse):
        keys = keys if keys is not None else self.keys()
        return sorted(keys, key=lambda k: self.get(k, -1), reverse=reverse)


class LastSeen(DataStorage):

    def __init__(self, path):
        DataStorage.__init__(self, path, TimeDict())


def _select_board(last_runs):
    valid_boards = api.get_boards()
    try:
        last_board = last_runs.newest(last_runs)[0]
    except IndexError:
        last_board = None

    while True:
        last_board_label = " ({})".format(last_board) if last_board else ""
        board = raw_input("Please select a 4chan board{}: "
                          .format(last_board_label))
        lboard = board.lower()
        if lboard == '' and last_board:
            board = last_board
            break
        elif lboard in valid_boards:
            board = lboard
            break
        else:
            print "'{}' is not a valid board!".format(board)
            print "Valid boards: {}".format(", ".join(sorted(valid_boards)))
            print
    last_runs.touch(board)
    return board


def main():
    import logging
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    print "Initializing..."
    last_runs_file = os.path.join(DATA_DIRECTORY, 'last_runs')
    with LastSeen(last_runs_file) as last_runs:
        board = _select_board(last_runs)
    data_dir = os.path.join(DATA_DIRECTORY, board)
    discarded_file = os.path.join(data_dir, 'discarded')
    last_seen_file = os.path.join(data_dir, 'last_seen')
    with LastSeen(discarded_file) as discarded, \
            LastSeen(last_seen_file) as last_seen:
        run_interactive(board, discarded, last_seen)


def _visit(thread):
    print "Visiting..."
    os.system("chromium-browser --incognito {}".format(thread.url))
    return False


def _queue(board, thread):
    print "Queueing for download..."
    FourChanThread(board, thread.no, slug=thread.semantic_url).init()
    return True


def _discard(thread, discarded):
    print "Thrashing..."
    discarded.touch(thread.no)
    return True


def _skip(_thread):
    print "Skipping..."
    return True


def run_interactive(board, discarded, last_seen):
    _trash = lambda t: _discard(t, discarded)
    _download = lambda t: _queue(board, t)
    quit_ = []
    _quit = quit_.append
    actions = {
        'V': _visit,
        'D': _download,
        'T': _trash,
        'S': _skip,
        'Q': _quit,
    }
    print "Loading current threads:"
    queued = set((t.board, t.thread_no) for t in FourChanThread.all())
    print "Loaded {} current threads".format(len(queued))
    print "Requesting catalog for {}".format(board)
    discarded_count = 0
    queued_count = 0
    thread_count = 0
    threads = {}
    threads_no = []
    for thread in api.Catalog(board).threads():
        thread_count += 1
        if thread.no in discarded:
            discarded_count += 1
        elif (board, thread.no) in queued:
            queued_count += 1
        else:
            threads_no.append(thread.no)
            threads[thread.no] = thread

    print ("Got {} threads in total, {} are queued, {} are discarded."
           .format(thread_count, queued_count, discarded_count))
    new_threads = [threads[tno] for tno in threads_no if tno not in last_seen]
    print 5871965 in threads
    old_thread_nums = last_seen.oldest([tnum for tnum in threads if tnum in last_seen])
    print threads.keys()
    old_threads = [threads[tnum] for tnum in old_thread_nums]
    for state, state_threads in [('new', new_threads), ('old', old_threads)]:
        if state_threads:

            print "Got {} {} threads!:".format(len(state_threads), state)
            for thread in state_threads:
                print " - {}.{}: {} - {}".format(board, thread.no, thread.sub,
                                                 thread.semantic_url)
            print
            option = raw_input("Do you want to open all of them? [Y/n]: ")
            if option.lower() in ["", "y"]:
                for thread in state_threads:
                    _visit(thread)
            else:
                print " Not opening!"

    print "Do you want to open old threads?"

    for index, thread_no in enumerate(last_seen.oldest(threads_no)):
        thread = threads[thread_no]
        print
        title = "{1}/{2}: {0.no} - {0.sub}".format(thread, index + 1,
                                                   len(threads))
        print "=" * len(title)
        print title
        print "=" * len(title)
        print
        print thread.com
        print
        done = False
        while not done:
            print "What do you want to do?"
            option = raw_input("[V]isit, [D]ownload, [T]rash, [S]kip, "
                               "[Q]uit: ")
            try:
                action = actions[option.upper()]
            except KeyError:
                print "Unknown action '{}'. Try again".format(option)
                continue
            done = action(thread)
            if quit_:
                print "Quitting..."
                break
            last_seen.touch(thread.no)
        if quit_:
            break

if __name__ == "__main__":
    main()
