import queue
import threading


class EventBroadcaster:
    def __init__(self):
        self._subscribers = []
        self._lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, snapshot):
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            q.put(snapshot)
