from collections import deque
import threading
import time
import datetime
import putio
import re
import os
from putiosync import multipart_downloader


class Download(object):
    """Object containing information about a download to be performed"""

    def __init__(self, putio_file, destination_path):
        self._putio_file = putio_file
        self._destination_directory = destination_path
        self._progress_callbacks = set()
        self._start_callbacks = set()
        self._completion_callbacks = set()
        self._downloaded = 0
        self._start_datetime = None
        self._finish_datetime = None

    def _fire_progress_callbacks(self):
        for cb in list(self._progress_callbacks):
            cb(self)

    def _fire_start_callbacks(self):
        for cb in list(self._start_callbacks):
            cb(self)

    def _fire_completion_callbacks(self):
        for cb in list(self._completion_callbacks):
            cb(self)

    def get_putio_file(self):
        return self._putio_file

    def get_destination_directory(self):
        return self._destination_directory

    def get_filename(self):
        return self.get_putio_file().name.encode('ascii', 'ignore')

    def get_destination_path(self):
        return os.path.join(os.path.abspath(self._destination_directory),
                            self.get_filename())

    def get_downloaded(self):
        return self._downloaded

    def get_size(self):
        return self._putio_file.size

    def get_start_datetime(self):
        return self._start_datetime

    def get_finish_datetime(self):
        return self._finish_datetime

    def add_start_callback(self, start_callback):
        """Add a callback to be called when there is new progress to report on a download

        The callback will be called as follows::

            progress_callback(download)

        Information about the progress itself will be stored with the download.

        """
        self._start_callbacks.add(start_callback)

    def add_progress_callback(self, progress_callback):
        """Add a callback to be called whenever a new download is started

        The callback will be called as follows::

            start_callback(download)

        """
        self._progress_callbacks.add(progress_callback)

    def add_completion_callback(self, completion_callback):
        """Add a callback to be called whenever a download completes

        The callback will be called as follows::

            completion_callback(download)

        """
        self._completion_callbacks.add(completion_callback)

    def perform_download(self, token):
        self._start_datetime = datetime.datetime.now()
        self._fire_start_callbacks()
        putio_file = self.get_putio_file()
        dest = self.get_destination_directory()
        filename = self.get_filename()

        final_path = os.path.join(dest, filename)
        download_path = "{}.part".format(final_path)
        with open(download_path, 'wb') as f:
            def transfer_callback(offset, chunk):
                self._downloaded += len(chunk)
                f.seek(offset)
                f.write(chunk)
                f.flush()
                self._fire_progress_callbacks()

            multipart_downloader.download(
                putio.BASE_URL + '/files/{}/download'.format(putio_file.id),
                self.get_size(),
                transfer_callback,
                params={'oauth_token': token})

        # download to part file is complete.  Now move to its final destination
        if os.path.exists(final_path):
            os.remove(final_path)
        os.rename(download_path, download_path[:-5])  # same but without '.part'
        self._finish_datetime = datetime.datetime.now()
        self._fire_completion_callbacks()


class DownloadManager(threading.Thread):
    """Component responsible for managing the queue of things to be downloaded"""

    def __init__(self, token):
        threading.Thread.__init__(self, name="DownloadManager")
        self.setDaemon(True)
        self._token = token
        self._download_queue_lock = threading.RLock()  # also used for locking calllback lists
        self._download_queue = deque()
        self._progress_callbacks = set()
        self._start_callbacks = set()
        self._completion_callbacks = set()
        self._has_exit = False

    def _build_callback(self, callbacks):
        def callback(*args, **kwargs):
            with self._download_queue_lock:
                for cb in callbacks:
                    cb(*args, **kwargs)
        return callback

    def start(self):
        """Start this donwload manager"""
        threading.Thread.start(self)

    def add_download(self, download):
        """Add a download to be performed by this download manager"""
        if not isinstance(download, Download):
            raise TypeError("download must be of type QueuedDownload")
        with self._download_queue_lock:
            download.add_start_callback(self._build_callback(self._start_callbacks))
            download.add_progress_callback(self._build_callback(self._progress_callbacks))
            download.add_completion_callback(self._build_callback(self._completion_callbacks))
            self._download_queue.append(download)

    def add_download_start_progress(self, start_callback):
        """Add a callback to be called whenever a new download is started

        The callback will be called as follows::

            start_callback(download)

        """
        with self._start_callbacks:
            self._start_callbacks.add(start_callback)

    def add_download_progress_callback(self, progress_callback):
        """Add a callback to be called when there is new progress to report on a download

        The callback will be called as follows::

            progress_callback(download)

        Information about the progress itself will be stored with the download.

        """
        with self._download_queue_lock:
            self._progress_callbacks.add(progress_callback)

    def add_download_completion_callback(self, completion_callback):
        """Add a callback to be called whenever a download completes

        The callback will be called as follows::

            completion_callback(download)

        """
        with self._download_queue_lock:
            self._completion_callbacks.add(completion_callback)

    def get_downloads(self):
        """Get a list of the downloads active at this time"""
        with self._download_queue_lock:
            return list(self._download_queue)

    def is_empty(self):
        """Return True if there are no queued downloads"""
        with self._download_queue_lock:
            return len(self._download_queue) == 0

    def run(self):
        """Main loop for the download manager"""
        while not self._has_exit:
            try:
                download = self._download_queue[0]  # keep in queue until complete
            except IndexError:
                time.sleep(0.5)  # don't busily spin
            else:
                download.perform_download(self._token)
                self._download_queue.popleft()
