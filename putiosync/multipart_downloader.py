"""Implementation for multi-segment file downloader

This can sometimes significiantly increase the overall speed of a download
and is a technique commonly used by download managers (like DownThemAll)
to get better download performance.  Robustness can also be increased
(although this implementation is pretty simple).

Also, it should be noted that this has been tested with downloads provided
by put.io, but your mileage may vary for other servers.

"""
import Queue
import threading
from requests import Request
import requests

__author__ = "Paul Osborne"


class _MultiSegmentDownloadWorker(threading.Thread):
    """Worker thread responsible for carrying out smaller chunks of work"""

    def __init__(self, url, worker_num, work_queue, completion_queue, request_kwargs):
        threading.Thread.__init__(self, name="Worker on {} #{}".format(url, worker_num))
        self.setDaemon(True)
        self._url = url
        self._worker_num = worker_num
        self._told_to_stop = False
        self._work_queue = work_queue
        self._completion_queue = completion_queue
        self._request_kwargs = request_kwargs

    def stop(self):
        self._told_to_stop = True

    def _download_segment(self, segment):
        kwds = self._request_kwargs.copy()
        response = requests.request(
            method="GET",
            url=self._url,
            headers={
                "Range": segment.build_range_header()
            },
            stream=True,
            **self._request_kwargs)

        offset = segment.offset
        for chunk in response.iter_content(chunk_size=2 * 1024):
            if chunk:
                self._completion_queue.put((offset, chunk))
                offset += len(chunk)

    def run(self):
        while not self._told_to_stop:
            segment = self._work_queue.get()
            if segment is None:
                break
            else:
                self._download_segment(segment)
        self._completion_queue.put(None)


class _Segment(object):
    """Model information about a segment that a worker will need"""

    def __init__(self, offset, size, is_last_segment):
        self.offset = offset
        self.size = size
        self.is_last_segment = is_last_segment

    def build_range_header(self):
        """Build an http range header for this segment"""
        if self.is_last_segment:
            return "bytes={}-{}".format(self.offset, "")
        else:
            return "bytes={}-{}".format(self.offset, self.offset + self.size - 1)


def download(url, size, transfer_callback, num_workers=4, segment_size_bytes=200 * 1024 * 1024, **kwargs):
    """Start the download with this downloads settings

    As multi-segment downloads are really only useful for very large
    downloads, we provide a callback that will be called whenever we
    have finished downloading a chunk of data.  The callback will be
    called with the following form::

        transfer_callback(offset, data)

    Where offset is the byte offset into the file being downloaded
    and data is the data for that chunk.

    """
    work_queue = Queue.Queue()
    completion_queue = Queue.Queue()

    num_workers = min(num_workers, int(size / segment_size_bytes) + 1)

    # create workers and start them
    workers = [_MultiSegmentDownloadWorker(url, i + 1, work_queue, completion_queue, kwargs)
               for i in xrange(num_workers)]
    for worker in workers:
        worker.start()

    # create each segment and put it in the queue
    pos = 0
    while pos + segment_size_bytes < size:
        # Note that math on pos is exclusive, on segment in inclusive.  That means that downloading
        # a segment of size 1000 is range 0-999.  This detail is accounted for in the _Segment
        # implementation itself (build_range_header).
        seg = _Segment(offset=pos, size=segment_size_bytes, is_last_segment=False)
        work_queue.put(seg)
        pos += segment_size_bytes
    if pos < size:
        seg = _Segment(offset=pos, size=size - pos, is_last_segment=True)
        work_queue.put(seg)

    # queue up one None for each worker to let it know that things are complete
    for _ in xrange(num_workers):
        work_queue.put(None)

    error_occurred = False
    workers_completed = 0
    while not error_occurred:
        msg = completion_queue.get()
        if msg is None:  # a worker just finished
            workers_completed += 1
            if workers_completed == num_workers:
                break
        else:
            offset, chunk = msg
            try:
                transfer_callback(offset, chunk)
            except:
                error_occurred = True

    if error_occurred:
        for worker in workers:
            worker.stop()  # halt now

    for worker in workers:
        worker.join()

    success = not error_occurred
    return success
