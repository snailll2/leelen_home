# 模拟 message 类（简单版）
class Message:
    def __init__(self, what, arg1=0, obj=None):
        self.what = what
        self.arg1 = arg1
        self.obj = obj
