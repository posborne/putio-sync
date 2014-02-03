#!/usr/bin/env python
#
# Program for automatically downloading and removing files that are
# successfully downloaded from put.io.
#
import collections
import json
import datetime
import logging
import progressbar
from putiosync import multipart_downloader
from putiosync.dbmodel import DBModelBase, DownloadRecord
import re
import webbrowser
import time
import os
import putio
from sqlalchemy import create_engine, exists
from sqlalchemy.orm.session import sessionmaker


logger = logging.getLogger("putiosync")

CLIENT_ID = 6017
HOME_DIR = os.path.expanduser("~")
SETTINGS_DIR = os.path.join(HOME_DIR, ".putiosync")
SYNC_FILE = os.path.join(SETTINGS_DIR, "putiosync.json")
DATABASE_FILE = os.path.join(SETTINGS_DIR, "putiosync.db")
CHECK_PERIOD_SECONDS = 10


class DatabaseManager(object):

    def __init__(self):
        self._db_engine = None
        self._db = None
        self._ensure_database_exists()

    def _ensure_database_exists(self):
        if not os.path.exists(SETTINGS_DIR):
            os.makedirs(SETTINGS_DIR)
        self._db_engine = create_engine("sqlite:///{}".format(DATABASE_FILE))
        self._db_engine.connect()
        self._db = sessionmaker(self._db_engine)()
        DBModelBase.metadata.create_all(self._db_engine)

    def get_db(self):
        return self._db


class TokenManager(object):
    """Object responsible for providing access to API token"""

    def is_valid_token(self, token):
        return (token is not None and len(token) > 0)

    def save_token(self, token):
        """Save the provided token to disk"""
        if not os.path.exists(SETTINGS_DIR):
            os.makedirs(SETTINGS_DIR)
        with open(SYNC_FILE, "w") as f:
            f.write(json.dumps({"token": token}))

    def get_token(self):
        """Restore token from disk or return None if not present"""
        try:
            with open(SYNC_FILE, "r") as f:
                jsondata = f.read()
                return json.loads(jsondata)["token"]
        except (OSError, IOError):
            return None

    def obtain_token(self):
        """Obtain token from the user using put.io apptoken URL

        This URL wasn't explicitly mentioned in the API docs, but it is what
        the XBMC app from put.io uses and seems to work

        """
        apptoken_url = "http://put.io/v2/oauth2/apptoken/{}".format(CLIENT_ID)
        print "Opening {}".format(apptoken_url)
        webbrowser.open(apptoken_url)
        token = raw_input("Enter token: ").strip()
        return token


class DownloadQueue(object):
    """Store queued downloads"""

    def __init__(self):
        self._queue = collections.deque()

    def add(self, putio_file):
        """Add the specified file to the download queue"""
        self._queue.append(putio_file)

    def __iter__(self):
        return iter(list(self._queue))


class PutioSynchronizer(object):
    """Object encapsulating core synchronization logic and state"""

    def __init__(self, token, download_directory, db_manager, keep_files=False, poll_frequency=60):
        self._token = token
        self._download_directory = download_directory
        self._db_manager = db_manager
        self._putio_client = putio.Client(token)
        self._poll_frequency = poll_frequency
        self._keep_files = keep_files
        self._download_queue = DownloadQueue()

    def _is_directory(self, putio_file):
        return (putio_file.content_type == 'application/x-directory')

    def _already_downloaded(self, putio_file, dest):
        if os.path.exists(os.path.join(dest, "{}.part".format(putio_file.name))):
            return True  # TODO: check size and/or crc32 checksum?
        matching_rec_exists = self._db_manager.get_db().query(exists().where(DownloadRecord.file_id == putio_file.id)).scalar()
        return matching_rec_exists

    def _record_downloaded(self, putio_file):
        matching_rec_exists = self._db_manager.get_db().query(exists().where(DownloadRecord.file_id == putio_file.id)).scalar()
        if not matching_rec_exists:
            download_record = DownloadRecord(
                file_id=putio_file.id,
                size=putio_file.size,
                timestamp=datetime.datetime.now(),
                name=putio_file.name)
            self._db_manager.get_db().add(download_record)
            self._db_manager.get_db().commit()
        else:
            logger.warn("File with id %r already marked as downloaded!", putio_file.id)

    def _do_download(self, putio_file, dest, delete_after_download=False):
        if dest.endswith("..."):
            dest = dest[:-3]

        if not self._already_downloaded(putio_file, dest):
            print "Downloading {}".format(putio_file)
            if not os.path.exists(dest):
                os.makedirs(dest)

            total = putio_file.size
            widgets = [
                progressbar.Percentage(), ' ',
                progressbar.Bar(), ' ',
                progressbar.ETA(), ' ',
                progressbar.FileTransferSpeed()]
            pbar = progressbar.ProgressBar(widgets=widgets, maxval=total).start()

            # Helper to get the filename in the form that we need for the full multi-segment download
            response = putio_file.client.request('/files/%s/download' % putio_file.id, raw=True, stream=True)
            filename = re.match('attachment; filename=(.*)',
                                response.headers['content-disposition']).groups()[0].strip('"')
            response.close()

            final_path = os.path.join(dest, filename)
            download_path = "{}.part".format(final_path)
            with open(download_path, 'wb') as f:
                download_info = {"downloaded": 0}

                def transfer_callback(offset, chunk):
                    download_info["downloaded"] += len(chunk)
                    pbar.update(download_info["downloaded"])
                    f.seek(offset)
                    f.write(chunk)
                    f.flush()
                multipart_downloader.download(
                    putio.BASE_URL + '/files/{}/download'.format(putio_file.id),
                    putio_file.size,
                    transfer_callback,
                    params={'oauth_token': self._token})


            # download to part file is complete.  Now move to its final destination
            if os.path.exists(final_path):
                os.remove(final_path)
            os.rename(download_path, download_path[:-5])  # same but without '.part'

            # and write a record of the download to the database
            self._record_downloaded(putio_file)
            if delete_after_download:
                putio_file.delete()

    def _download_and_delete(self, putio_file, relpath="", level=0):
        # add this file (or files in this directory) to the queue
        if not self._is_directory(putio_file):
            target_dir = os.path.join(self._download_directory, relpath)
            self._do_download(putio_file, target_dir, delete_after_download=(not self._keep_files))
        else:
            for child in putio_file.dir():
                self._download_and_delete(
                    child, os.path.join(relpath, putio_file.name), level + 1)
            if not self._keep_files:
                putio_file.delete()  # children already downloaded

    def _perform_single_check(self):
        try:
            # Perform a single check for updated files to download
            for putio_file in self._putio_client.File.list():
                self._download_and_delete(putio_file)
        except:
            logger.exception("Unexpected error while performing check/download")

    def run_forever(self):
        """Run the synchronizer until killed"""
        while True:
            self._perform_single_check()
            time.sleep(self._poll_frequency)
