class FrameIdSingleton:
    """帧号计数器 —— 模块级单例实例,字段即状态,直接属性读写。

    由基类 BaseLanProtocol.get_frame_id() 负责实际自增;本实例仅在响应处理时
    读取记录当前帧号。已去除 Java 单例样板与 getter/setter 包装。
    """

    def __init__(self):
        self.frame_id = 0


frame_id_counter = FrameIdSingleton()