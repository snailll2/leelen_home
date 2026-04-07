import logging
import os
import queue
import threading
import time
import traceback
import uuid
from typing import Optional, Callable, Dict

from ..utils.LogUtils import LogUtils


class _ThreadPoolFuture:
    """表示线程池任务的结果，支持取消和状态查询"""
    def __init__(self, task_id: str):
        self._task_id = task_id
        self._is_cancelled = False
        self._is_done = False
        self._result = None
        self._exception = None
        self._condition = threading.Condition()

    def cancel(self) -> bool:
        """尝试取消任务"""
        with self._condition:
            if self._is_done:
                return False
            self._is_cancelled = True
            self._condition.notify_all()
            return True

    def cancelled(self) -> bool:
        """检查任务是否已取消"""
        return self._is_cancelled

    def done(self) -> bool:
        """检查任务是否已完成"""
        return self._is_done or self._is_cancelled

    def result(self, timeout: Optional[float] = None) -> any:
        """获取任务结果，阻塞直到任务完成"""
        with self._condition:
            if not self._is_done and not self._is_cancelled:
                if not self._condition.wait(timeout):
                    raise TimeoutError("Future result timeout")
            if self._is_cancelled:
                raise Exception("Task was cancelled")
            if self._exception:
                raise self._exception
            return self._result

    def exception(self, timeout: Optional[float] = None) -> Optional[Exception]:
        """获取任务异常，阻塞直到任务完成"""
        with self._condition:
            if not self._is_done and not self._is_cancelled:
                if not self._condition.wait(timeout):
                    raise TimeoutError("Future exception timeout")
            if self._is_cancelled:
                return None
            return self._exception

    def set_result(self, result: any) -> None:
        """设置任务结果"""
        with self._condition:
            if self._is_done or self._is_cancelled:
                return
            self._result = result
            self._is_done = True
            self._condition.notify_all()

    def set_exception(self, exception: Exception) -> None:
        """设置任务异常"""
        with self._condition:
            if self._is_done or self._is_cancelled:
                return
            self._exception = exception
            self._is_done = True
            self._condition.notify_all()


class _WorkerThread(threading.Thread):
    """可中断的工作线程"""
    def __init__(self, pool_name: str, thread_id: int, task_queue: queue.Queue):
        super().__init__()
        self._pool_name = pool_name
        self._thread_id = thread_id
        self._task_queue = task_queue
        self._is_running = True
        self._current_task = None
        self._current_future = None
        self.name = f"{self._pool_name}_{self._thread_id}"
        self.daemon = True

    def run(self) -> None:
        """线程主循环，处理任务"""
        LogUtils.d(f"Worker thread {self.name} started")
        while self._is_running:
            try:
                # 获取任务，超时检查是否需要退出
                task_data = self._task_queue.get(timeout=0.1)
                if task_data is None:
                    # 收到退出信号
                    self._task_queue.task_done()
                    break

                self._current_task, self._current_future = task_data
                
                # 检查任务是否已取消
                if self._current_future.cancelled():
                    LogUtils.d(f"Task {self._current_future._task_id} already cancelled")
                    self._task_queue.task_done()
                    continue

                # 执行任务 - 这里需要处理可中断的情况
                # 由于Python的GIL限制，我们无法强制中断正在运行的线程
                # 但我们可以定期检查任务是否被取消
                try:
                    result = self._current_task()
                    # 检查任务是否在执行过程中被取消
                    if not self._current_future.cancelled():
                        self._current_future.set_result(result)
                except Exception as e:
                    # 检查任务是否在执行过程中被取消
                    if not self._current_future.cancelled():
                        self._current_future.set_exception(e)
                    raise
                
            except queue.Empty:
                # 检查是否需要退出
                continue
            except Exception as e:
                # 记录异常
                if self._current_future and not self._current_future.done():
                    self._current_future.set_exception(e)
                LogUtils.e(f"Error in worker thread {self.name}: {e}")
            finally:
                self._current_task = None
                self._current_future = None
                try:
                    self._task_queue.task_done()
                except Exception:
                    pass
        LogUtils.d(f"Worker thread {self.name} exited")

    def terminate(self) -> bool:
        """终止线程"""
        self._is_running = False
        # 如果有当前任务且任务还没有完成，尝试取消
        if self._current_future and not self._current_future.done():
            return self._current_future.cancel()
        return True


class DefaultThreadPool:
    _instance = None
    _lock = threading.Lock()

    BLOCKING_QUEUE_SIZE = 20

    def __init__(self):
        cpu_count = os.cpu_count()
        self.THREAD_POOL_SIZE = cpu_count + 1
        self.THREAD_POOL_MAX_SIZE = cpu_count * 2 + 1
        
        # 生成随机字符串用于区分不同的线程池实例
        self._random_suffix = uuid.uuid4().hex[:8]
        self._pool_name = f"DefaultThreadPool_{self._random_suffix}"

        # 任务队列
        self._task_queue = queue.Queue(maxsize=self.BLOCKING_QUEUE_SIZE)
        
        # 工作线程列表
        self._workers: Dict[str, _WorkerThread] = {}
        self._worker_count = 0
        
        # 任务ID计数器
        self._task_counter = 0
        
        # 线程池状态
        self._is_running = True
        
        # 初始化工作线程
        self._initialize_workers(self.THREAD_POOL_SIZE)

    def _initialize_workers(self, count: int) -> None:
        """初始化指定数量的工作线程"""
        for i in range(count):
            self._worker_count += 1
            worker = _WorkerThread(self._pool_name, self._worker_count, self._task_queue)
            self._workers[worker.name] = worker
            worker.start()
        LogUtils.d(f"Initialized {count} worker threads")

    def _get_next_task_id(self) -> str:
        """生成唯一的任务ID"""
        self._task_counter += 1
        return f"task_{self._random_suffix}_{self._task_counter}"

    @classmethod
    def get_instance(cls) -> 'DefaultThreadPool':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例，允许重新初始化线程池"""
        with cls._lock:
            if cls._instance is not None:
                # 确保旧实例已关闭
                try:
                    cls._instance.shutdown_now()
                except Exception:
                    pass
                cls._instance = None
            LogUtils.i("ThreadPool instance reset")

    def execute(self, task: Optional[Callable]) -> Optional[_ThreadPoolFuture]:
        """提交任务到线程池"""
        if task is None or not self._is_running:
            if not self._is_running:
                LogUtils.w("ThreadPool already shutdown, task rejected")
            return None

        try:
            # 创建Future对象
            task_id = self._get_next_task_id()
            future = _ThreadPoolFuture(task_id)
            
            # 将任务和Future放入队列
            self._task_queue.put((task, future), block=False)
            return future
        except queue.Full:
            LogUtils.w("Task queue is full, task rejected")
            return None
        except Exception as e:
            traceback.print_exc()
            LogUtils.e(f"Error executing task: {e}")
            return None

    def clear_queue(self) -> None:
        """清空等待队列中的所有任务"""
        try:
            # 清空队列
            while not self._task_queue.empty():
                task_data = self._task_queue.get(block=False)
                if task_data is not None:
                    task, future = task_data
                    future.cancel()
                self._task_queue.task_done()
            LogUtils.d("Task queue cleared")
        except queue.Empty:
            pass
        except Exception as e:
            logging.exception(f"Error clearing task queue: {e}")

    def shutdown(self) -> None:
        """安全关闭线程池，等待队列中的任务完成"""
        self._is_running = False
        
        # 等待所有任务完成
        self._task_queue.join()
        
        # 停止所有工作线程
        for worker in self._workers.values():
            worker.terminate()
        
        # 等待所有工作线程退出
        # for worker in self._workers.values():
        #     worker.join(timeout=1.0)
        
        self._workers.clear()
        LogUtils.d("ThreadPool shutdown completed")

    def shutdown_now(self) -> None:
        """立即关闭线程池，终止所有正在运行的任务并清空队列"""
        self._is_running = False
        
        # 清空队列
        self.clear_queue()
        
        # 终止所有工作线程
        for worker in self._workers.values():
            worker.terminate()
        
        # 等待所有工作线程退出
        # for worker in self._workers.values():
        #     worker.join(timeout=0.5)
        
        self._workers.clear()
        LogUtils.d("ThreadPool shutdown now completed")

    def shutdown_right_now(self) -> None:
        """立即关闭线程池（旧方法保留兼容性）"""
        self.shutdown_now()

    def terminate_all_threads(self) -> None:
        """立即终止所有工作线程"""
        LogUtils.d("Terminating all worker threads")
        for worker in self._workers.values():
            worker.terminate()
        self._workers.clear()
        self._is_running = False
        LogUtils.d("All worker threads terminated")

    def size(self) -> int:
        """获取线程池中的工作线程数量"""
        return len(self._workers)

    def queue_size(self) -> int:
        """获取等待队列中的任务数量"""
        return self._task_queue.qsize()

