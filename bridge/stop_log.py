"""Best-effort stderr JSON. Safety callers never wait for the sink or queue space.

A stuck sink can lose lines once the bounded queue fills; shutdown never joins the
writer. No file opens, rotation, retries or other I/O belong on the safety path.
"""
from datetime import datetime, timezone
import json
from queue import Queue
import sys
from threading import Thread


class StopLog:
    def __init__(self, stream=None, capacity=4096):
        self.stream = stream
        self.queue = Queue(maxsize=capacity)
        try:
            Thread(target=self._write, name='stop-log', daemon=True).start()
        except Exception:
            pass  # Logging must not prevent safety startup if a thread cannot start.

    def __call__(self, event, **fields):
        try:
            line = json.dumps(dict(timestamp=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                                   event=event, **fields), separators=(',', ':'), allow_nan=False) + '\n'
            self.queue.put_nowait(line)
        except Exception:
            pass

    def _write(self):
        while True:
            line = self.queue.get()
            try:
                stream = self.stream if self.stream is not None else sys.stderr
                stream.write(line)
                stream.flush()
            except Exception:
                pass
            finally:
                self.queue.task_done()


stop_log = StopLog()
