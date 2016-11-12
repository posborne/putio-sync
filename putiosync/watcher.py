import logging
import os

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)


def is_torrent(ext):
    return ext in (".torrent", ".magnet")


class TorrentWatcherFilesystemEventHandler(FileSystemEventHandler):
    """This class handles filesystem changes to monitored directories

    This will filter events and queue up torrents to be downloaded
    if a new torrent or magnet file is added to the monitored directories.

    """

    def __init__(self, putio_client):
        FileSystemEventHandler.__init__(self)
        self._putio_client = putio_client

    def on_created(self, event):
        if not event.is_directory:
            basename = os.path.basename(event.src_path)
            _name, ext = os.path.splitext(basename)
            if is_torrent(ext):
                logger.info("Adding torrent from path '%s'", event.src_path)
                self._putio_client.Transfer.add_torrent(event.src_path)


class TorrentWatcher(object):

    def __init__(self, watch_directory, putio_client):
        self._watch_directory = watch_directory
        self._putio_client = putio_client
        self._observer = Observer()
        self._event_handler = TorrentWatcherFilesystemEventHandler(self._putio_client)

    def stop(self):
        self._observer.stop()

    def join(self, *args, **kwargs):
        self._observer.join(*args, **kwargs)

    def start(self):
        # TODO: add recursive option in future
        self._observer.schedule(self._event_handler,
                                self._watch_directory,
                                recursive=False)
        self._observer.start()
