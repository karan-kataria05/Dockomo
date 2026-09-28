from PyQt5.QtCore import QThread, pyqtSignal


class Worker(QThread):
    """Runs `fn(*args, progress_cb=self._emit_progress, **kwargs)` off the GUI thread.
    Pass with_log=True if fn also accepts a `log_cb` kwarg for live line-by-line output."""

    progress = pyqtSignal(int, int, str)   # done, total, current item label
    log_line = pyqtSignal(str)             # live output line (only if with_log=True)
    finished_ok = pyqtSignal(object)       # fn's return value
    failed = pyqtSignal(str)               # error message

    def __init__(self, fn, *args, with_log=False, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.with_log = with_log

    def _emit_progress(self, done, total, label):
        self.progress.emit(done, total, label)

    def _emit_log(self, line):
        self.log_line.emit(line)

    def run(self):
        try:
            if self.with_log:
                result = self.fn(*self.args, progress_cb=self._emit_progress,
                                  log_cb=self._emit_log, **self.kwargs)
            else:
                result = self.fn(*self.args, progress_cb=self._emit_progress, **self.kwargs)
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
