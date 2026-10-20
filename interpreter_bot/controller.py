from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import textwrap
from pathlib import Path

from .keyboard import KeyboardListener


SERVER_PATH = "/tmp/dahamkke-bot-control.sock"
RESET = "\033[0m"
BOLD = "\033[1m"
WHITE = "\033[97m"
MUTED = "\033[90m"
CYAN = "\033[96m"
BLUE = "\033[44;97m"
PURPLE = "\033[45;97m"
GREEN = "\033[42;30m"
RED = "\033[41;97m"
PANEL = "\033[48;5;17m"


class SharedController:
    def __init__(self) -> None:
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.settimeout(1.0)
        handle = tempfile.NamedTemporaryFile(
            prefix="dahamkke-controller-", suffix=".sock", delete=True
        )
        handle.close()
        self.client_path = Path(handle.name)
        self.client_path.unlink(missing_ok=True)
        self.socket.bind(str(self.client_path))
        self.running = True
        self.last_state: dict[str, object] = {}

    @staticmethod
    def _center(text: str, width: int) -> str:
        import re

        visible = re.sub(r"\x1b\[[0-9;]*m", "", text)
        return " " * max(0, (width - len(visible)) // 2) + text

    @staticmethod
    def _button(text: str, color: str = BLUE) -> str:
        return f"{color}{BOLD}  {text}  {RESET}"

    def request(self, key: str | None = None) -> dict[str, object]:
        request: dict[str, object] = {"type": "state"}
        if key is not None:
            request = {"type": "key", "key": key}
        self.socket.sendto(
            json.dumps(request, ensure_ascii=False).encode("utf-8"), SERVER_PATH
        )
        payload = self.socket.recv(8192)
        return json.loads(payload.decode("utf-8"))

    @staticmethod
    def _map_key(key: str) -> str | None:
        if key in ("\x7f", "\x08"):
            return "backspace"
        if key in ("\r", "\n"):
            return "return"
        if key == " ":
            return "space"
        if key == "UP":
            return "up"
        if key == "DOWN":
            return "down"
        if len(key) == 1:
            return key.lower()
        return None

    def _robot(self, width: int, height: int, talking: bool) -> list[str]:
        face_width = max(34, min(68, width - 4))
        inner = face_width - 2
        face_height = max(7, height - 2)
        eye_row = max(2, face_height // 2 - 1)
        mouth_row = min(face_height - 2, eye_row + 2)
        lines = ["╭" + "─" * inner + "╮"]
        for row in range(1, face_height - 1):
            content = [" "] * inner
            if row == eye_row:
                content[inner // 3] = "●"
                content[inner * 2 // 3] = "●"
            if row == mouth_row:
                content[inner // 2] = "◯" if talking else "⌣"
            lines.append("│" + "".join(content) + "│")
        lines.append("╰" + "─" * inner + "╯")
        return [self._center(line, width) for line in lines]

    def _bottom(self, state: dict[str, object], width: int) -> list[str]:
        screen = str(state.get("screen", "home"))
        recording = bool(state.get("recording"))
        if screen == "home":
            return [
                self._center(
                    self._button("S  시작하기")
                    + "    "
                    + self._button("W  Wi-Fi", GREEN),
                    width,
                )
            ]
        if screen == "selection":
            return [
                self._center(
                    self._button("D  대화하기")
                    + "    "
                    + self._button("T  통역하기", PURPLE),
                    width,
                ),
                self._center(
                    self._button("C  토론하기", GREEN)
                    + "    "
                    + self._button("I  인터뷰하기", PURPLE),
                    width,
                ),
            ]
        if screen == "language_select":
            selected = state.get("chat_language") or "없음"
            return [
                self._center("[K 한국어] [C 중국어] [V 베트남어] [R 러시아어]", width),
                self._center(f"선택: {selected} · Enter 확정", width),
            ]
        if screen == "conversation":
            mic = self._button(
                "SPACE  ■ 듣기 종료" if recording else "SPACE  ● 마이크",
                RED if recording else BLUE,
            )
            return [self._center(mic, width)] + self._result_lines(state, width)
        if screen == "interpret":
            source = state.get("source_language") or "-"
            target = state.get("target_language") or "-"
            active = state.get("active_dropdown")
            selectors = self._button(
                f"O 원본: {source}", GREEN if active == "source" else BLUE
            ) + "  " + self._button(
                f"T 통역: {target}", GREEN if active == "target" else PURPLE
            )
            mic = self._button(
                "SPACE  ■ 듣기 종료" if recording else "SPACE  ● 마이크",
                RED if recording else BLUE,
            )
            return [self._center(selectors, width), self._center(mic, width)] + self._result_lines(state, width)
        if screen == "debate":
            return [self._center("숫자 1~8로 토론 주제를 선택하세요", width)]
        if screen == "interview":
            return [self._center("숫자 1~8로 인터뷰 인물을 선택하세요", width)]
        if screen in {"debate_chat", "interview_chat"}:
            label = state.get("debate_topic") if screen == "debate_chat" else state.get("persona")
            mic = self._button(
                "SPACE  ■ 듣기 종료" if recording else "SPACE  ● 마이크",
                RED if recording else BLUE,
            )
            return [self._center(str(label or "학습 대화"), width), self._center(mic, width)] + self._result_lines(state, width)
        return []

    def _result_lines(self, state: dict[str, object], width: int) -> list[str]:
        result = str(state.get("result") or "")
        return [
            self._center(line, width)
            for line in textwrap.wrap(result, max(20, width - 8))[:3]
        ]

    def render(self, state: dict[str, object]) -> None:
        columns, rows = shutil.get_terminal_size((80, 24))
        columns = max(48, columns)
        top_height = max(9, int(rows * 0.70))
        screen = str(state.get("screen", "home"))
        titles = {
            "home": "다함께 봇 · 시작 화면",
            "selection": "다함께 봇 · 선택 화면",
            "language_select": "대화 언어 선택",
            "conversation": "AI 대화하기",
            "interpret": "통역하기",
            "debate": "토론 주제 선택",
            "debate_chat": "AI 토론하기",
            "interview": "인터뷰 인물 선택",
            "interview_chat": "인물 인터뷰하기",
        }
        print("\033[2J\033[H", end="")
        print(
            f"{PANEL}{BOLD}{WHITE}"
            f"{self._center(titles.get(screen, screen), columns)}{RESET}"
        )
        if screen in {"home", "selection", "conversation"}:
            for line in self._robot(
                columns, top_height - 1, bool(state.get("talking"))
            ):
                print(f"{CYAN}{line}{RESET}")
        else:
            if screen == "language_select":
                print(self._center("[ 한국어 K ]   [ 중국어 C ]", columns))
                print(self._center("[ 베트남어 V ] [ 러시아어 R ]", columns))
            elif screen in {"debate", "interview"}:
                label = "토론 주제" if screen == "debate" else "인터뷰 인물"
                print(self._center(f"{label}를 터치하거나 숫자 1~8을 누르세요", columns))
            elif screen in {"debate_chat", "interview_chat"}:
                print(self._center("AI 답변은 왼쪽 · 내 답변은 오른쪽", columns))
            else:
                print(self._center("원본 언어와 통역할 언어를 선택해 주세요", columns))
                print(self._center("O/T → ↑/↓ → Enter", columns))
            print("\n" * max(1, top_height - 6), end="")
        print(f"{PANEL}{WHITE}{'─' * columns}{RESET}")
        for line in self._bottom(state, columns):
            print(line)
        status = str(state.get("status") or "준비")
        print(self._center(f"{BOLD}{status}{RESET}", columns))
        print(
            self._center(
                f"{MUTED}공유 제어 중 · Backspace 뒤로 · Q CLI 종료{RESET}",
                columns,
            )
        )
        print(flush=True)

    def run(self) -> None:
        if not Path(SERVER_PATH).exists():
            raise RuntimeError(
                "GUI 제어 소켓이 없습니다. dahamkke-touchscreen 서비스를 먼저 시작하세요."
            )
        state = self.request()
        self.last_state = state
        self.render(state)
        try:
            with KeyboardListener() as keyboard:
                while self.running:
                    key = keyboard.get(timeout=0.15)
                    if key is not None:
                        if key.lower() == "q" or key == "\x1b":
                            self.running = False
                            break
                        mapped = self._map_key(key)
                        if mapped:
                            state = self.request(mapped)
                    else:
                        state = self.request()
                    if state != self.last_state:
                        self.last_state = state
                        self.render(state)
        finally:
            self.close()

    def close(self) -> None:
        self.socket.close()
        self.client_path.unlink(missing_ok=True)
        print(f"{RESET}\033[2J\033[HCLI 공유 제어를 종료했습니다.")


def main() -> int:
    try:
        SharedController().run()
        return 0
    except Exception as exc:
        print(f"[공유 제어 시작 오류] {exc}")
        return 1
