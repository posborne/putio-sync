#!/usr/bin/env python
#
# Program for automatically downloading and removing files that are
# successfully downloaded from put.io.
#
import json
import datetime
import logging
import traceback
import progressbar
from putiosync.dbmodel import DBModelBase, DownloadRecord
from putiosync.download_manager import Download
import webbrowser
import time
import os
import sys
from sqlalchemy import create_engine, exists
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm.session import sessionmaker

logger = logging.getLogger("putiosync")


CLIENT_ID = 1067
HOME_DIR = os.path.expanduser("~")
SETTINGS_DIR = os.path.join(HOME_DIR, ".putiosync")
SYNC_FILE = os.path.join(SETTINGS_DIR, "putiosync.json")
DATABASE_FILE = os.path.join(SETTINGS_DIR, "putiosync.db")
CHECK_PERIOD_SECONDS = 10


class DatabaseManager(object):

    def __init__(self):
        self._db_engine = None
        self._scoped_session = None
        self._ensure_database_exists()

    def _ensure_database_exists(self):
        if not os.path.exists(SETTINGS_DIR):
            os.makedirs(SETTINGS_DIR)
        self._db_engine = create_engine("sqlite:///{}".format(DATABASE_FILE))
        self._db_engine.connect()
        self._scoped_session = scoped_session(sessionmaker(self._db_engine))
        DBModelBase.metadata.create_all(self._db_engine)

    def get_db_session(self):
        return self._scoped_session()


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
        print("Opening {}".format(apptoken_url))
        webbrowser.open(apptoken_url)
        if sys.version[0]=="2":
            input=raw_input
        else:
            input=input
        token = input("Enter token: ").strip()
        return token


class PutioSynchronizer(object):
    """Object encapsulating core synchronization logic and state"""

    def __init__(self, download_directory, putio_client, db_manager, download_manager, keep_files=False, poll_frequency=60,
                 download_filter=None, force_keep=None, disable_progress=False):
        self._putio_client = putio_client
        self._download_directory = download_directory
        self._db_manager = db_manager
        self._poll_frequency = poll_frequency
        self._keep_files = keep_files
        self._download_manager = download_manager
        # This regex is already compiled
        self.download_filter = download_filter
        self.force_keep = force_keep
        self.disable_progress = disable_progress

    def get_download_directory(self):
        return self._download_directory

    def _is_directory(self, putio_file):
        return (putio_file.content_type == 'application/x-directory')

    def _already_downloaded(self, putio_file, dest):
        filename = putio_file.name.encode('utf-8', 'ignore')
        logger.warn("File name check: %r", putio_file.name)

        if os.path.exists(os.path.join(dest, "{}".format(filename))):
            return True  # TODO: check size and/or crc32 checksum?
        matching_rec_exists = self._db_manager.get_db_session().query(exists().where(DownloadRecord.file_id == putio_file.id)).scalar()
        return matching_rec_exists

    def is_already_downloaded(self, putio_file):
        return self._already_downloaded(putio_file, self._download_directory)

    def _record_downloaded(self, putio_file):
        filename = putio_file.name.encode('utf-8', 'ignore')
        matching_rec_exists = self._db_manager.get_db_session().query(exists().where(DownloadRecord.file_id == putio_file.id)).scalar()
        if not matching_rec_exists:
            download_record = DownloadRecord(
                file_id=putio_file.id,
                size=putio_file.size,
                timestamp=datetime.datetime.now(),
                name=filename)
            self._db_manager.get_db_session().add(download_record)
            self._db_manager.get_db_session().commit()
        else:
            logger.warn("File with id %r already marked as downloaded!", putio_file.id)

    def _do_queue_download(self, putio_file, dest, delete_after_download=False):
        if dest.endswith("..."):
            dest = dest[:-3]

        if not self._already_downloaded(putio_file, dest):
            if not os.path.exists(dest):
                os.makedirs(dest)

            download = Download(putio_file, dest)
            total = putio_file.size
            if not self.disable_progress:
                widgets = [
                    progressbar.Percentage(), ' ',
                    progressbar.Bar(), ' ',
                    progressbar.ETA(), ' ',
                    progressbar.FileTransferSpeed()]
                pbar = progressbar.ProgressBar(widgets=widgets, maxval=total)

            def start_callback(_download):
                logger.info("Starting download {}".format(putio_file))
                if not self.disable_progress:
                    pbar.start()

            def progress_callback(_download):
                try:
                    pbar.update(download.get_downloaded())
                except AssertionError:
                    pass  # ignore, has happened

            def completion_callback(_download):
                # and write a record of the download to the database
                self._record_downloaded(putio_file)
                logger.info("Download finished: {}".format(putio_file.name))
                if delete_after_download:
                    try:
                        putio_file.delete()
                    except:
                        logger.error("Error deleting file {}. Assuming all is well but may require manual cleanup".format(putio_file.name))
                        traceback.print_exc()

            download.add_start_callback(start_callback)
            if self.disable_progress is False:
                download.add_progress_callback(progress_callback)
            download.add_completion_callback(completion_callback)
            self._download_manager.add_download(download)
        else:
            logger.debug("Already downloaded: '{}'".format(putio_file.name))
            if delete_after_download:
                try:
                    putio_file.delete()
                except:
                    logger.error("Error deleting file... assuming all is well but may require manual cleanup")
                    traceback.print_exc()



    def _queue_download(self, putio_file, relpath="", level=0):
        # add this file (or files in this directory) to the queue

        full_path = os.path.sep + os.path.join(relpath, putio_file.name)
        logger.error("File path: {}".format(full_path))
        full_path = full_path.replace("\\", "/")
        logger.error("File path after replace: {}".format(full_path))
        if not self._is_directory(putio_file):
            if self.download_filter is not None and self.download_filter.match(full_path) is None:
                logger.debug("Skipping '{0}' because it does not match the provided filter".format(full_path))
            else:
                logger.debug("Adding download to queue: '{0}'".format(full_path))
                target_dir = os.path.join(self._download_directory, relpath)
                delete_file = not self._keep_files and (self.force_keep is None or  self.force_keep.match(full_path) is None)
                self._do_queue_download(putio_file, target_dir, delete_after_download=delete_file)
        else:
            children = putio_file.dir()
            if not children:
                # this is a directory with no children, it must be destroyed
                if self.force_keep is None or self.force_keep.match(full_path) is None:
                    putio_file.delete()
            else:
                for child in children:
                    self._queue_download(child, os.path.join(relpath, putio_file.name), level + 1)

    def _perform_single_check(self):
        try:
            # Perform a single check for updated files to download
            for putio_file in self._putio_client.File.list():
                self._queue_download(putio_file)
        except Exception as ex:
            logger.error("Unexpected error while performing check/download: {}".format(ex))
            logger.error("File checked: {}".format(putio_file))

    def _wait_until_downloads_complete(self):
        while not self._download_manager.is_empty():
            time.sleep(0.5)

    def run_forever(self):
        """Run the synchronizer until killed"""
        logger.warn("Starting main application")
        while True:
            self._perform_single_check()
            last_check = datetime.datetime.now()
            self._wait_until_downloads_complete()
            time_since_last_check = datetime.datetime.now() - last_check
            if time_since_last_check < datetime.timedelta(seconds=self._poll_frequency):
                time.sleep(self._poll_frequency - time_since_last_check.total_seconds())

