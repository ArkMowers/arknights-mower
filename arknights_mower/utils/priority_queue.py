import heapq


class PriorityQueue(object):
    """
    基于 heapq 实现的优先队列
    """

    def __init__(self):
        self.queue = []

    def push(self, data):
        heapq.heappush(self.queue, data)

    def pop(self):
        if len(self.queue) == 0:
            return None
        return heapq.heappop(self.queue)
