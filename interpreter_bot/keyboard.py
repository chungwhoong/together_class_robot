from __future__ import annotations

import os
import queue
import select
import sys
import termios
import threading
import tty


class KeyboardListener:
    """Read single keys without blocking the main/audio loop."""

    def __init__(self) -> None:
        self.keys: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fd: int | None = None
        self._old_settings: list | None = None

    def start(self) -> None:
        if not sys.stdin.isatty():
            raise RuntimeError("키보드 제어에는 터미널(TTY)이 필요합니다.")
        self._fd = sys.stdin.fileno()
        self._old_settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        self._thread = threading.Thread(
            target=self._read_loop, name="keyboard-listener", daemon=True
        )
        self._thread.start()

    def _read_loop(self) -> None:
        assert self._fd is not None
        while not self._stop.is_set():
            ready, _, _ = select.select([self._fd], [], [], 0.1)
            if ready:
                try:
                    raw = os.read(self._fd, 1)
                    if raw == b"\x1b":
                        sequence = raw
                        for _ in range(2):
                            more, _, _ = select.select([self._fd], [], [], 0.03)
                            if not more:
                                break
                            sequence += os.read(self._fd, 1)
                        arrows = {
                            b"\x1b[A": "UP",
                            b"\x1b[B": "DOWN",
                            b"\x1b[C": "RIGHT",
                            b"\x1b[D": "LEFT",
                        }
                        key = arrows.get(sequence, "\x1b")
                    else:
                        key = raw.decode(errors="ignore")
                    if key:
                        self.keys.put(key)
                except OSError:
                    break

    def get(self, timeout: float = 0.1) -> str | None:
        try:
            return self.keys.get(timeout=timeout)
        except queue.Empty:
            return None

    def clear(self) -> None:
        while True:
            try:
                self.keys.get_nowait()
            except queue.Empty:
                return

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        if self._fd is not None and self._old_settings is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)

    def __enter__(self) -> "KeyboardListener":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()
