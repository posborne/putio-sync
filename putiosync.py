#!/usr/bin/env python
#
# Program for automatically downloading and removing files that are
# successfully downloaded from put.io.
#
import Queue
import collections
import json
import progressbar
import re
import webbrowser
import time
import sys
import os
import putio
import argparse

CLIENT_ID = 6017
THIS_DIR = os.path.dirname(__file__)
SYNC_FILE = os.path.join(THIS_DIR, "putiosync.json")
CHECK_PERIOD_SECONDS = 10


class TokenManager(object):
    """Object responsible for providing access to API token"""

    def is_valid_token(self, token):
        return (token is not None and len(token) > 0)

    def save_token(self, token):
        """Save the provided token to disk"""
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


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-k", "--keep",
        action="store_true",
        default=False,
        help="Keep files on put.io; do not automatically delete")
    parser.add_argument(
        "download_directory",
        help="Directory into which files should be downloaded")
    args = parser.parse_args()
    return args


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

    def __init__(self, token, download_directory):
        self._token = token
        self._download_directory = download_directory
        self._putio_client = putio.Client(token)
        self._download_queue = DownloadQueue()

    def _is_directory(self, putio_file):
        return (putio_file.content_type == 'application/x-directory')

    def _do_download(self, putio_file, dest, delete_after_download=False):
        if not os.path.exists(dest):
            os.makedirs(dest)
        response = putio_file.client.request(
            '/files/%s/download' % putio_file.id,
            raw=True, stream=True)
        filename = re.match(
            'attachment; filename=(.*)',
            response.headers['content-disposition']).groups()[0]
        filename = filename.strip('"')

        total = putio_file.size
        downloaded = 0
        widgets = [
            progressbar.Percentage(), ' ',
            progressbar.Bar(), ' ',
            progressbar.ETA(), ' ',
            progressbar.FileTransferSpeed()]
        pbar = progressbar.ProgressBar(widgets=widgets, maxval=total).start()
        with open(os.path.join(dest, filename), 'wb') as f:
            for chunk in response.iter_content(chunk_size=256):
                if chunk:  # filter out keep-alive new chunks
                    downloaded += len(chunk)
                    pbar.update(downloaded)
                    f.write(chunk)
                    f.flush()

        if delete_after_download:
            putio_file.delete()

    def _download_and_delete(self, putio_file, relpath="", level=0):
        print "Downloading {}{}".format("  " * level, putio_file)
        # add this file (or files in this directory) to the queue
        if not self._is_directory(putio_file):
            target_dir = os.path.join(self._download_directory, relpath)
            self._do_download(putio_file, target_dir, delete_after_download=True)
        else:
            for child in putio_file.dir():
                self._download_and_delete(
                    child, os.path.join(relpath, putio_file.name), level + 1)
            putio_file.delete()  # children already downloaded

    def _perform_single_check(self):
        # Perform a single check for updated files to download
        for putio_file in self._putio_client.File.list():
            self._download_and_delete(putio_file)

    def run_forever(self):
        """Run the synchronizer until killed"""
        while True:
            self._perform_single_check()
            time.sleep(CHECK_PERIOD_SECONDS)


def main():
    args = parse_arguments()

    # Restore or obtain a valid token
    token_manager = TokenManager()
    token = token_manager.get_token()
    while not token_manager.is_valid_token(token):
        print "No valid token found!  Please provide one."
        token = token_manager.obtain_token()
    token_manager.save_token(token)

    # Let's start syncing!
    synchronizer = PutioSynchronizer(token, args.download_directory)
    synchronizer.run_forever()
    return 0

if __name__ == '__main__':
    sys.exit(main())
