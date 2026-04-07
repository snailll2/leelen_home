import threading


class FrameIdSingleton:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._frame_id = 0

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_frame_id(self):
        return self._frame_id

    def set_frame_id(self, frame_id):
        self._frame_id = frame_id
