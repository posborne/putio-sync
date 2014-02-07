import argparse
import sys
import threading
from putiosync.core import TokenManager, PutioSynchronizer, DatabaseManager
from putiosync.download_manager import DownloadManager
from putiosync.webif.webif import WebInterface

__author__ = 'Paul Osborne'


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-k", "--keep",
        action="store_true",
        default=False,
        help="Keep files on put.io; do not automatically delete")
    parser.add_argument(
        "-p", "--poll-frequency",
        default=60,
        type=int,
        help="Polling frequency in seconds (default: 1 minute)",
    )
    parser.add_argument(
        "download_directory",
        help="Directory into which files should be downloaded")
    args = parser.parse_args()
    return args


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
    db_manager = DatabaseManager()
    download_manager = DownloadManager(token=token)
    download_manager.start()
    synchronizer = PutioSynchronizer(
        token=token,
        download_directory=args.download_directory,
        db_manager=db_manager,
        download_manager=download_manager,
        keep_files=args.keep,
        poll_frequency=args.poll_frequency)
    t = threading.Thread(target=synchronizer.run_forever)
    t.setDaemon(True)
    t.start()
    web_interface = WebInterface(db_manager)
    web_interface.run()
    return 0

if __name__ == '__main__':
    sys.exit(main())
