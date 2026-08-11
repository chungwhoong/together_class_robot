from __future__ import annotations

import subprocess
import tempfile
import threading
import wave
from pathlib import Path

from .config import Config


class AudioRecorder:
    """Push-to-talk recorder.

    A future silence-detection recorder can implement the same start/stop/abort API.
    """

    def __init__(self, config: Config, temp_dir: Path) -> None:
        self.config = config
        self.temp_dir = temp_dir
        self._process: subprocess.Popen[bytes] | None = None
        self._path: Path | None = None
        self._lock = threading.Lock()

    @property
    def recording(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> Path:
        with self._lock:
            if self.recording:
                raise RuntimeError("이미 녹음 중입니다.")
            handle = tempfile.NamedTemporaryFile(
                prefix="input_", suffix=".wav", dir=self.temp_dir, delete=False
            )
            handle.close()
            self._path = Path(handle.name)
            command = [
                "arecord",
                "-q",
                "-D",
                self.config.mic_device,
                "-f",
                self.config.sample_format,
                "-r",
                str(self.config.sample_rate),
                "-c",
                str(self.config.channels),
                "-t",
                "wav",
                str(self._path),
            ]
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            return self._path

    def stop(self) -> Path | None:
        with self._lock:
            process, path = self._process, self._path
            self._process = None
            self._path = None
        stderr = b""
        if process:
            if process.poll() is None:
                process.terminate()
            try:
                _, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                _, stderr = process.communicate(timeout=1)
        if path and path.exists() and path.stat().st_size > 44:
            try:
                self._finalize_wav(path)
                return path
            except (OSError, EOFError, wave.Error, RuntimeError) as exc:
                path.unlink(missing_ok=True)
                raise RuntimeError(f"녹음 파일을 마감하지 못했습니다: {exc}") from exc
        if path:
            path.unlink(missing_ok=True)
        error = stderr.decode(errors="replace").strip()
        if error and "Interrupted system call" not in error:
            raise RuntimeError(f"arecord 오류: {error}")
        return None

    def _finalize_wav(self, path: Path) -> None:
        """Rewrite arecord's streaming WAV header with the real PCM length.

        arecord leaves 0x80000000 placeholder sizes when push-to-talk stops it
        with SIGTERM. Some STT requests accept that header and others reject it
        as an unsupported format, so always create a standards-compliant WAV.
        """
        frames = bytearray()
        with wave.open(str(path), "rb") as source:
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            sample_rate = source.getframerate()
            compression = source.getcomptype()
            compression_name = source.getcompname()
            while True:
                chunk = source.readframes(4096)
                if not chunk:
                    break
                frames.extend(chunk)
        bytes_per_second = channels * sample_width * sample_rate
        if bytes_per_second <= 0 or len(frames) < bytes_per_second // 5:
            raise RuntimeError("녹음 시간이 너무 짧습니다. 0.2초 이상 말해 주세요.")
        handle = tempfile.NamedTemporaryFile(
            prefix="final_", suffix=".wav", dir=self.temp_dir, delete=False
        )
        finalized = Path(handle.name)
        handle.close()
        try:
            with wave.open(str(finalized), "wb") as target:
                target.setnchannels(channels)
                target.setsampwidth(sample_width)
                target.setframerate(sample_rate)
                target.setcomptype(compression, compression_name)
                target.writeframes(frames)
            finalized.replace(path)
        finally:
            finalized.unlink(missing_ok=True)

    def abort(self) -> None:
        try:
            path = self.stop()
            if path:
                path.unlink(missing_ok=True)
        except RuntimeError:
            # Cleanup must remain best-effort during mode changes and shutdown.
            pass

    def close(self) -> None:
        self.abort()


class AudioPlayer:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.RLock()

    def play(self, path: Path) -> None:
        self.stop()
        with self._lock:
            process = subprocess.Popen(
                ["aplay", "-q", "-D", self.config.speaker_device, str(path)]
            )
            self._process = process
        return_code = process.wait()
        with self._lock:
            was_current = self._process is process
            if was_current:
                self._process = None
        # A newer announcement/answer intentionally stops the previous sound.
        # Only report failure when this process was still the active playback.
        if return_code and was_current:
            raise RuntimeError(f"aplay가 종료 코드 {return_code}로 실패했습니다.")

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

    def close(self) -> None:
        self.stop()
