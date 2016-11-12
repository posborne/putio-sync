import argparse
import shlex
import sys
import threading
import subprocess
import putio
from putiosync.core import TokenManager, PutioSynchronizer, DatabaseManager
from putiosync.download_manager import DownloadManager
from putiosync.watcher import TorrentWatcher
from putiosync.webif.webif import WebInterface

__author__ = 'Paul Osborne'


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-k", "--keep",
        action="store_true",
        default=False,
        help="Keep files on put.io; do not automatically delete"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        default=False,
        help="Prevent browser from launching on start."
    )
    parser.add_argument(
        "-p", "--poll-frequency",
        default=60 * 3,
        type=int,
        help="Polling frequency in seconds (default: 1 minute)",
    )
    parser.add_argument(
        "-c", "--post-process-command",
        default=None,
        type=str,
        help=(
            "Command to be executed after the completion of every download.  "
            "The command will be executed with the path to the file that has "
            "just been completed as an argument.  "
            "Example: putio-sync -c 'python /path/to/postprocess.py' /path/to/Downloads"
        ),
    )
    parser.add_argument(
        "-w", "--watch-directory",
        default=None,
        type=str,
        help=(
            "Directory to watch for torrent or magnet files.  If this option is"
            "present and new files are added, they will be added to put.io and"
            "automatically downloaded by the daemon when complete."
        )
    )
    parser.add_argument(
        "download_directory",
        help="Directory into which files should be downloaded"
    )
    args = parser.parse_args()
    return args


def build_postprocess_download_completion_callback(postprocess_command):
    def download_completed(download):
        print(repr(postprocess_command))
        args = shlex.split(postprocess_command)
        args.append(download.get_filename())
        subprocess.call(args, shell=True)

    return download_completed

def main():
    args = parse_arguments()

    # Restore or obtain a valid token
    token_manager = TokenManager()
    token = token_manager.get_token()
    while not token_manager.is_valid_token(token):
        print("No valid token found!  Please provide one.")
        token = token_manager.obtain_token()
    token_manager.save_token(token)

    # Let's start syncing!
    putio_client = putio.Client(token)
    db_manager = DatabaseManager()
    download_manager = DownloadManager(token=token)
    if args.post_process_command is not None:
        download_manager.add_download_completion_callback(
            build_postprocess_download_completion_callback(args.post_process_command))

    if args.watch_directory is not None:
        torrent_watcher = TorrentWatcher(args.watch_directory, putio_client)
        torrent_watcher.start()

    download_manager.start()
    synchronizer = PutioSynchronizer(
        download_directory=args.download_directory,
        putio_client=putio_client,
        db_manager=db_manager,
        download_manager=download_manager,
        keep_files=args.keep,
        poll_frequency=args.poll_frequency)
    t = threading.Thread(target=synchronizer.run_forever)
    t.setDaemon(True)
    t.start()
    web_interface = WebInterface(db_manager, download_manager, putio_client, synchronizer, launch_browser=(not args.quiet))
    web_interface.run()
    return 0

if __name__ == '__main__':
    sys.exit(main())
