from __future__ import annotations

import shutil
import signal
import tempfile
import textwrap
import re
from pathlib import Path

from .audio import AudioPlayer, AudioRecorder
from .config import Config
from .keyboard import KeyboardListener
from .openai_service import OpenAIVoiceService


RESET = "\033[0m"
BOLD = "\033[1m"
WHITE = "\033[97m"
MUTED = "\033[90m"
BLUE = "\033[44;97m"
PURPLE = "\033[45;97m"
GREEN = "\033[42;30m"
RED = "\033[41;97m"
CYAN = "\033[96m"
PANEL = "\033[48;5;17m"

CHAT_LANGUAGES = {
    "k": ("한국어", "Korean"),
    "c": ("중국어", "Simplified Chinese"),
    "v": ("베트남어", "Vietnamese"),
    "r": ("러시아어", "Russian"),
}

INTERPRET_LANGUAGES = [
    ("한국어", "Korean"),
    ("러시아어", "Russian"),
    ("영어", "English"),
    ("베트남어", "Vietnamese"),
    ("중국어", "Simplified Chinese"),
    ("카자흐스탄어", "Kazakh"),
]

GREETINGS = {
    "Korean": "반가워요. 어떤 내용이 궁금한가요?",
    "Simplified Chinese": "很高兴见到你。你想了解什么？",
    "Vietnamese": "Rất vui được gặp bạn. Bạn muốn biết điều gì?",
    "Russian": "Рад познакомиться. Что вы хотите узнать?",
}

FOLLOWUPS = {
    "Korean": "다른 질문이 있으면 스페이스 키를 눌러주세요.",
    "Simplified Chinese": "如果还有其他问题，请按空格键。",
    "Vietnamese": "Nếu bạn có câu hỏi khác, hãy nhấn phím cách.",
    "Russian": "Если у вас есть другой вопрос, нажмите пробел.",
}


class VoiceTUI:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dahamkke_tui_"))
        self.recorder = AudioRecorder(config, self.temp_dir)
        self.player = AudioPlayer(config)
        self.service = OpenAIVoiceService(config, self.temp_dir)
        self.screen = "home"
        self.running = True
        self.status = "S 키를 눌러 시작하세요"
        self.output = ""
        self.selected_chat: tuple[str, str] | None = None
        self.source_index = 0
        self.target_index = 2
        self.active_dropdown: str | None = None
        self.talking = False

    @staticmethod
    def _handle_sigterm(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    @staticmethod
    def _center(text: str, width: int) -> str:
        visible = re.sub(r"\x1b\[[0-9;]*m", "", text)
        padding = max(0, (width - len(visible)) // 2)
        return " " * padding + text

    @staticmethod
    def _button(text: str, color: str = BLUE) -> str:
        return f"{color}{BOLD}  {text}  {RESET}"

    def _robot_lines(self, width: int, height: int) -> list[str]:
        face_width = max(34, min(68, width - 4))
        face_height = max(7, height - 2)
        inner = face_width - 2
        lines = ["╭" + "─" * inner + "╮"]
        eye_row = max(2, face_height // 2 - 1)
        mouth_row = min(face_height - 2, eye_row + 2)
        for row in range(1, face_height - 1):
            content = [" "] * inner
            if row == eye_row:
                left = inner // 3
                right = inner * 2 // 3
                content[left] = "●"
                content[right] = "●"
            if row == mouth_row:
                mouth = "◯" if self.talking else "⌣"
                content[inner // 2] = mouth
            lines.append("│" + "".join(content) + "│")
        lines.append("╰" + "─" * inner + "╯")
        return [self._center(line, width) for line in lines]

    def _bottom_lines(self, width: int) -> list[str]:
        if self.screen == "home":
            return [
                self._center(self._button("S  시작하기"), width),
                self._center(f"{MUTED}키보드: S{RESET}", width),
            ]
        if self.screen == "selection":
            buttons = (
                self._button("D  대화하기")
                + "    "
                + self._button("T  통역하기", PURPLE)
            )
            return [
                self._center(buttons, width),
                self._center(f"{MUTED}Backspace: 뒤로가기{RESET}", width),
            ]
        if self.screen == "language_select":
            rows: list[str] = []
            pairs = [("k", "c"), ("v", "r")]
            for left, right in pairs:
                parts = []
                for key in (left, right):
                    display = CHAT_LANGUAGES[key][0]
                    selected = self.selected_chat == CHAT_LANGUAGES[key]
                    parts.append(self._button(f"{key.upper()} {display}", GREEN if selected else BLUE))
                rows.append(self._center("    ".join(parts), width))
            selected_text = self.selected_chat[0] if self.selected_chat else "없음"
            rows.append(self._center(f"선택한 언어: {selected_text}  |  Enter: 선택  X: 취소", width))
            return rows
        if self.screen == "conversation":
            button = self._button(
                "SPACE  ■ 듣기 종료" if self.recorder.recording else "SPACE  ● 마이크",
                RED if self.recorder.recording else BLUE,
            )
            return [self._center(button, width)] + self._wrapped_output(width)
        if self.screen == "interpret":
            source = INTERPRET_LANGUAGES[self.source_index][0]
            target = INTERPRET_LANGUAGES[self.target_index][0]
            source_color = GREEN if self.active_dropdown == "source" else BLUE
            target_color = GREEN if self.active_dropdown == "target" else PURPLE
            selectors = (
                self._button(f"O 원본: {source}", source_color)
                + "  "
                + self._button(f"T 통역: {target}", target_color)
            )
            mic = self._button(
                "SPACE  ■ 듣기 종료" if self.recorder.recording else "SPACE  ● 마이크",
                RED if self.recorder.recording else BLUE,
            )
            return [self._center(selectors, width), self._center(mic, width)] + self._wrapped_output(width)
        return []

    def _wrapped_output(self, width: int) -> list[str]:
        if not self.output:
            return []
        return [self._center(line, width) for line in textwrap.wrap(self.output, max(20, width - 8))[:3]]

    def render(self) -> None:
        columns, rows = shutil.get_terminal_size((80, 24))
        columns = max(48, columns)
        top_height = max(9, int(rows * 0.70))
        print("\033[2J\033[H", end="")
        title = {
            "home": "다함께 봇 · 시작 화면",
            "selection": "다함께 봇 · 선택 화면",
            "language_select": "대화 언어 선택",
            "conversation": "AI 대화하기",
            "interpret": "통역하기",
        }[self.screen]
        print(f"{PANEL}{BOLD}{WHITE}{self._center(title, columns)}{RESET}")
        if self.screen in {"home", "selection", "conversation"}:
            for line in self._robot_lines(columns, top_height - 1):
                print(f"{CYAN}{line}{RESET}")
        else:
            blank_count = max(1, top_height - 6)
            if self.screen == "language_select":
                print(self._center("[ 한국어 K ]   [ 중국어 C ]", columns))
                print(self._center("[ 베트남어 V ] [ 러시아어 R ]", columns))
            else:
                print(self._center("원본 언어와 통역할 언어를 선택해 주세요", columns))
                print(self._center("O/T → ↑/↓ → Enter", columns))
            print("\n" * blank_count, end="")
        print(f"{PANEL}{WHITE}{'─' * columns}{RESET}")
        for line in self._bottom_lines(columns):
            print(line)
        print(self._center(f"{BOLD}{self.status}{RESET}", columns))
        print(self._center(f"{MUTED}Backspace: 뒤로 | ESC/Q: 종료{RESET}", columns))
        print(flush=True)

    def _speak(self, text: str) -> None:
        try:
            speech = self.service.synthesize(text)
            self.talking = True
            self.render()
            self.player.play(speech)
        except Exception as exc:
            self.status = f"음성 안내 오류: {exc}"
        finally:
            self.talking = False
            self.render()

    def _go_home(self) -> None:
        self.recorder.abort()
        self.screen = "home"
        self.status = "S 키를 눌러 시작하세요"
        self.output = ""

    def _go_selection(self, announce: bool = True) -> None:
        self.recorder.abort()
        self.screen = "selection"
        self.status = "D: 대화하기 | T: 통역하기"
        self.output = ""
        self.render()
        if announce:
            self._speak(
                "AI와 대화하며 국어공부를 하고 싶으면 대화하기 버튼을 눌러주세요. "
                "언어가 다른 친구와 이야기하고 싶으면 통역하기 버튼을 눌러주세요"
            )

    def _go_language_select(self) -> None:
        self.recorder.abort()
        self.screen = "language_select"
        self.selected_chat = None
        self.status = "K/C/V/R로 언어 선택 · Enter로 확정"
        self.output = ""

    def _go_conversation(self) -> None:
        if not self.selected_chat:
            self.status = "먼저 언어를 선택하세요"
            return
        self.screen = "conversation"
        self.status = "Space를 눌러 질문하세요"
        self.output = ""
        self.render()
        self._speak(GREETINGS[self.selected_chat[1]])

    def _go_interpret(self) -> None:
        self.recorder.abort()
        self.screen = "interpret"
        self.active_dropdown = None
        self.status = "O/T 선택 · ↑/↓ 이동 · Enter 확정"
        self.output = ""
        self.render()
        self._speak("원본 언어와 통역할 언어를 선택해 주세요")

    def _toggle_conversation(self) -> None:
        if not self.recorder.recording:
            self.recorder.start()
            self.status = "듣는 중 · Space를 다시 누르면 완료"
            return
        audio = self.recorder.stop()
        if not audio:
            self.status = "녹음된 음성이 없습니다"
            return
        self.status = "AI가 질문을 분석 중"
        self.render()
        try:
            assert self.selected_chat is not None
            text = self.service.transcribe(audio)
            answer = self.service.chat_in_language(text, self.selected_chat[1])
            self.output = f"나: {text} | AI: {answer}"
            self.status = "AI 답변 중"
            self.render()
            self._speak(f"{answer} {FOLLOWUPS[self.selected_chat[1]]}")
            self.status = "다른 질문은 Space를 누르세요"
        except Exception as exc:
            self.status = f"오류: {exc}"
        finally:
            audio.unlink(missing_ok=True)

    def _toggle_interpret(self) -> None:
        if self.source_index == self.target_index:
            self.status = "서로 다른 두 언어를 선택하세요"
            return
        if not self.recorder.recording:
            self.recorder.start()
            self.status = "듣는 중 · Space를 다시 누르면 완료"
            return
        audio = self.recorder.stop()
        if not audio:
            self.status = "녹음된 음성이 없습니다"
            return
        self.status = "AI가 통역 중"
        self.render()
        try:
            source = INTERPRET_LANGUAGES[self.source_index]
            target = INTERPRET_LANGUAGES[self.target_index]
            text = self.service.transcribe(audio)
            translated = self.service.translate(text, source[1], target[1])
            self.output = f"원문: {text} | {target[0]}: {translated}"
            self.status = "통역 음성 출력 중"
            self.render()
            self._speak(translated)
            self.status = "다시 통역하려면 Space를 누르세요"
        except Exception as exc:
            self.status = f"오류: {exc}"
        finally:
            audio.unlink(missing_ok=True)

    def _back(self) -> None:
        routes = {
            "selection": self._go_home,
            "language_select": lambda: self._go_selection(False),
            "conversation": self._go_language_select,
            "interpret": lambda: self._go_selection(False),
        }
        route = routes.get(self.screen)
        if route:
            route()

    def handle_key(self, key: str) -> None:
        lowered = key.lower() if len(key) == 1 else key
        if key in ("\x1b",) or lowered == "q":
            self.running = False
            self.recorder.abort()
            return
        if key in ("\x7f", "\x08"):
            self._back()
        elif self.screen == "home" and lowered == "s":
            self._go_selection()
        elif self.screen == "selection" and lowered == "d":
            self._go_language_select()
        elif self.screen == "selection" and lowered == "t":
            self._go_interpret()
        elif self.screen == "language_select":
            if lowered in CHAT_LANGUAGES:
                self.selected_chat = CHAT_LANGUAGES[lowered]
                self.status = f"{self.selected_chat[0]}를 선택했습니다"
                self.render()
                self._speak(f"{self.selected_chat[0]}를 선택하였습니다.")
            elif key in ("\r", "\n"):
                self._go_conversation()
            elif lowered == "x":
                self.selected_chat = None
                self.status = "언어 선택을 취소했습니다"
        elif self.screen == "conversation" and key == " ":
            self._toggle_conversation()
        elif self.screen == "interpret":
            if lowered == "o":
                self.active_dropdown = "source"
                self.status = "원본 언어: ↑/↓ 후 Enter"
            elif lowered == "t":
                self.active_dropdown = "target"
                self.status = "통역 언어: ↑/↓ 후 Enter"
            elif key in ("UP", "DOWN"):
                if not self.active_dropdown:
                    self.status = "먼저 O 또는 T를 누르세요"
                else:
                    step = -1 if key == "UP" else 1
                    if self.active_dropdown == "source":
                        self.source_index = (self.source_index + step) % len(INTERPRET_LANGUAGES)
                    else:
                        self.target_index = (self.target_index + step) % len(INTERPRET_LANGUAGES)
            elif key in ("\r", "\n"):
                self.status = "언어 선택을 확정했습니다"
                self.active_dropdown = None
            elif key == " ":
                self._toggle_interpret()

    def run(self) -> None:
        previous_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        self.render()
        self._speak(
            "안녕하세요. 다함께 봇입니다. 저와 대화를 하면서 국어를 공부해요"
        )
        try:
            with KeyboardListener() as keyboard:
                while self.running:
                    key = keyboard.get()
                    if key is None:
                        continue
                    self.handle_key(key)
                    if self.running:
                        self.render()
        except KeyboardInterrupt:
            pass
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)
            self.close()

    def close(self) -> None:
        self.running = False
        self.recorder.close()
        self.player.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        print(f"{RESET}\033[2J\033[H안전하게 종료했습니다.")


def main() -> int:
    try:
        VoiceTUI(Config.from_env()).run()
        return 0
    except Exception as exc:
        print(f"[시작 오류] {exc}")
        return 1
