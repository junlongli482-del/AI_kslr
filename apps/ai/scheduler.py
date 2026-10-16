"""Live configurable, FIFO task admission. Zero means no local concurrency cap."""
from __future__ import annotations

import threading
from collections import deque


class TaskScheduler:
    def __init__(self, limit=0):
        self.condition = threading.Condition()
        self.limit = limit
        self.waiting = deque()
        self.running = set()
        self.registered = set()

    def register(self, task_id):
        with self.condition:
            if task_id in self.registered:
                return False
            self.registered.add(task_id)
            self.waiting.append(task_id)
            self.condition.notify_all()
            return True

    def acquire(self, task_id):
        with self.condition:
            self.condition.wait_for(lambda: self.waiting[0] == task_id and
                                    (self.limit == 0 or len(self.running) < self.limit))
            self.waiting.popleft()
            self.running.add(task_id)
            self.condition.notify_all()

    def release(self, task_id):
        with self.condition:
            self.running.discard(task_id)
            self.registered.discard(task_id)
            if task_id in self.waiting:
                self.waiting.remove(task_id)
            self.condition.notify_all()

    def contains(self, task_id):
        with self.condition:
            return task_id in self.registered

    def configure(self, limit):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError('并发数必须是非负整数，0 表示无本地上限')
        with self.condition:
            self.limit = limit
            self.condition.notify_all()
            return self.snapshot()

    def snapshot(self):
        with self.condition:
            return {'max_concurrency': self.limit, 'unlimited': self.limit == 0,
                    'running': len(self.running), 'queued': len(self.waiting)}
