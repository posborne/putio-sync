import argparse
import sys
from putiosync.core import TokenManager, PutioSynchronizer

__author__ = 'Paul Osborne'


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
