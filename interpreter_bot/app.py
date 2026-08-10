from __future__ import annotations

import shutil
import signal
import tempfile
from enum import Enum
from pathlib import Path

from .audio import AudioPlayer, AudioRecorder
from .config import Config
from .keyboard import KeyboardListener
from .openai_service import LANGUAGES, OpenAIVoiceService


class Mode(Enum):
    CHAT = "AI 대화"
    INTERPRET = "통역"


class VoiceCLI:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.temp_dir = Path(tempfile.mkdtemp(prefix="interpreter_bot_"))
        self.recorder = AudioRecorder(config, self.temp_dir)
        self.player = AudioPlayer(config)
        self.service = OpenAIVoiceService(config, self.temp_dir)
        self.mode = Mode.CHAT
        self.language: tuple[str, str] | None = None
        self.running = True

    def print_status(self) -> None:
        detail = (
            f" ({self.language[0]} ↔ 한국어)" if self.mode is Mode.INTERPRET else ""
        )
        print(f"\n[{self.mode.value}{detail}] Space: 녹음 시작/종료 | s: 모드 전환 | q/ESC: 종료")

    @staticmethod
    def _handle_sigterm(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    def select_language(self, keyboard: KeyboardListener) -> bool:
        print("\n통역 언어 선택: 1 영어 | 2 우즈베크어 | 3 중국어 간체 | 4 러시아어")
        print("번호를 누르세요. s를 누르면 취소합니다.")
        while self.running:
            key = keyboard.get()
            if key in LANGUAGES:
                self.language = LANGUAGES[key]
                self.mode = Mode.INTERPRET
                print(f"통역 언어: {self.language[0]}")
                return True
            if key in ("s", "S"):
                return False
            if key in ("q", "Q", "\x1b"):
                self.running = False
                return False
        return False

    def toggle_mode(self, keyboard: KeyboardListener) -> None:
        self.recorder.abort()
        if self.mode is Mode.INTERPRET:
            self.mode = Mode.CHAT
            self.language = None
            print("\nAI 대화 모드로 전환했습니다.")
        else:
            self.select_language(keyboard)
        if self.running:
            self.print_status()

    def process_audio(self, audio_path: Path) -> None:
        try:
            print("음성을 인식하는 중...")
            text = self.service.transcribe(audio_path)
            if not text:
                print("음성이 인식되지 않았습니다.")
                return
            print(f"나: {text}")
            if self.mode is Mode.CHAT:
                output = self.service.chat(text)
                label = "AI"
            else:
                assert self.language is not None
                output, spoken_language = self.service.translate_bidirectional(
                    text, self.language[0], self.language[1]
                )
                label = f"번역({spoken_language})"
            print(f"{label}: {output}")
            speech_path = self.service.synthesize(output)
            self.player.play(speech_path)
        except Exception as exc:
            print(f"[오류] 요청 처리에 실패했습니다: {exc}")
        finally:
            audio_path.unlink(missing_ok=True)

    def run(self) -> None:
        print("음성 대화/통역 프로그램을 시작합니다.")
        print("안내: 출력 음성은 AI가 생성한 음성입니다.")
        self.print_status()
        previous_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        try:
            with KeyboardListener() as keyboard:
                while self.running:
                    key = keyboard.get()
                    if key is None:
                        continue
                    if key in ("q", "Q", "\x1b"):
                        self.running = False
                        self.recorder.abort()
                    elif key in ("s", "S"):
                        self.toggle_mode(keyboard)
                    elif key == " ":
                        if not self.recorder.recording:
                            try:
                                self.recorder.start()
                                print("● 녹음 중... Space를 다시 누르면 완료합니다.")
                            except Exception as exc:
                                print(f"[오류] 녹음을 시작하지 못했습니다: {exc}")
                        else:
                            print("■ 녹음 완료")
                            try:
                                audio_path = self.recorder.stop()
                                if audio_path:
                                    self.process_audio(audio_path)
                                else:
                                    print("녹음된 오디오가 없습니다.")
                            except Exception as exc:
                                print(f"[오류] 녹음을 완료하지 못했습니다: {exc}")
        except KeyboardInterrupt:
            print("\n중단 신호를 받았습니다.")
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)
            self.close()

    def close(self) -> None:
        self.running = False
        self.recorder.close()
        self.player.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        print("\n안전하게 종료했습니다.")


def main() -> int:
    try:
        config = Config.from_env()
        VoiceCLI(config).run()
        return 0
    except Exception as exc:
        print(f"[시작 오류] {exc}")
        return 1
