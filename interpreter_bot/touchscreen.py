from __future__ import annotations

from array import array
import json
import math
import os
import re
import signal
import shutil
import socket
import sys
import tempfile
import threading
import time
import tkinter as tk
import wave
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from .audio import AudioPlayer, AudioRecorder
from .config import Config
from .openai_service import OpenAIVoiceService


BG = "#07162f"
PANEL = "#10294c"
BLUE = "#1687ff"
CYAN = "#3be3ff"
WHITE = "#f7fbff"
MUTED = "#a9c2df"
RED = "#ef476f"
GREEN = "#28c76f"
CONTROL_SOCKET_PATH = Path("/tmp/dahamkke-bot-control.sock")

HOME_GUIDE = (
    "대화를 원하시면 '대화'이라고 말씀해 주세요.\n"
    "통역을 원하시면 '통역'이라고 말씀해 주세요."
)
CHAT_GUIDE = (
    "대화를 시작하려면 '시작'이라고 말씀해 주세요.\n"
    "본인의 발언이 끝나면 '오버'라고 말씀해 주세요.\n"
    "대화를 끝내고 시작화면으로 돌아가려면 '종료'라고 말씀해 주세요."
)
INTERPRET_GUIDE = (
    "통역할 언어를 선택해 주세요. 러시아어, 중국어, 우즈베키스탄어, "
    "카자흐스탄어, 영어를 선택할 수 있습니다."
)
START_ANNOUNCEMENT = (
    "안녕하세요. 다함께 봇입니다. 저와 대화를 하면서 국어를 공부해요"
)
SELECTION_ANNOUNCEMENT = (
    "AI와 대화하며 국어공부를 하고 싶으면 대화하기 버튼을 눌러주세요. "
    "언어가 다른 친구와 이야기하고 싶으면 통역하기 버튼을 눌러주세요"
)

TOUCH_LANGUAGES = [
    ("러시아어", "Russian"),
    ("중국어", "Simplified Chinese"),
    ("우즈베키스탄어", "Uzbek"),
    ("카자흐스탄어", "Kazakh"),
    ("영어", "English"),
]

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

CHAT_GREETINGS = {
    "Korean": "반가워요. 어떤 내용이 궁금한가요?",
    "Simplified Chinese": "很高兴见到你。你想了解什么？",
    "Vietnamese": "Rất vui được gặp bạn. Bạn muốn biết điều gì?",
    "Russian": "Рад познакомиться. Что вы хотите узнать?",
}

CHAT_FOLLOWUPS = {
    "Korean": "다른 질문이 있으면 마이크 버튼을 눌러주세요.",
    "Simplified Chinese": "如果还有其他问题，请按麦克风按钮。",
    "Vietnamese": "Nếu bạn có câu hỏi khác, hãy nhấn nút micrô.",
    "Russian": "Если у вас есть другой вопрос, нажмите кнопку микрофона.",
}


class TouchscreenApp:
    def __init__(self, root: tk.Tk, config: Config) -> None:
        self.root = root
        self.config = config
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dahamkke_touch_"))
        self.recorder = AudioRecorder(config, self.temp_dir)
        self.player = AudioPlayer(config)
        self.service = OpenAIVoiceService(config, self.temp_dir)
        self.screen = ""
        self.screen_token = 0
        self.selected_language: tuple[str, str] | None = None
        self.selected_chat_language: tuple[str, str] | None = None
        self.language_buttons: dict[str, tk.Button] = {}
        self.language_selected_label: tk.Label | None = None
        self.source_combo: ttk.Combobox | None = None
        self.target_combo: ttk.Combobox | None = None
        self.active_dropdown: str | None = None
        self.control_source_language: str | None = None
        self.control_target_language: str | None = None
        self.robot_talking = False
        self.status_text = ""
        self.display_result = ""
        self.control_socket: socket.socket | None = None
        self.control_stop = threading.Event()
        self.control_thread: threading.Thread | None = None
        self.mic_button: tk.Button | None = None
        self.mic_icon: tk.PhotoImage | None = None
        self.mic_icon_active: tk.PhotoImage | None = None
        self.status_label: tk.Label | None = None
        self.result_text: tk.Text | None = None
        self.robot_canvas: tk.Canvas | None = None
        self.robot_source = Image.open(
            Path(__file__).resolve().parent.parent
            / "assets"
            / "bmo_style_face_animated_base.png"
        )
        self.robot_photo: ImageTk.PhotoImage | None = None
        self.robot_bounds = (0.0, 0.0, 1.0, 1.0)
        self.animation_phase = 0
        self.busy = False
        self.greeted = False

        self.root.title("다함께 봇")
        self.root.configure(bg=BG)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.attributes("-fullscreen", True)
        # The dedicated framebuffer X server has no window manager, so the
        # fullscreen hint alone is ignored.  Force the root window to cover
        # every physical LCD pixel and remove server-side decorations.
        self.root.overrideredirect(True)
        self.root.geometry(f"{screen_width}x{screen_height}+0+0")
        self.compact = (
            screen_width <= 640
            or screen_height <= 400
        )
        if not self.compact:
            self.root.minsize(800, 480)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _event: self.close())
        self.root.bind_all("<KeyPress>", self._on_keypress)
        self.root.focus_force()
        signal.signal(signal.SIGTERM, self._request_close)
        signal.signal(signal.SIGINT, self._request_close)
        self.show_home()
        self._start_control_server()

    def _request_close(self, _signum: int, _frame: object) -> None:
        self.root.after(0, self.close)

    def _on_keypress(self, event: tk.Event) -> None:
        self._handle_key_name(str(event.keysym).lower())

    def _handle_key_name(self, key: str) -> None:
        key = key.lower()
        if key == "backspace":
            back_routes = {
                "selection": self.show_home,
                "language_select": self.show_selection,
                "conversation": self.show_language_select,
                "interpret": self.show_selection,
            }
            route = back_routes.get(self.screen)
            if route:
                route()
            return
        if self.screen == "home" and key == "s":
            self.show_selection()
        elif self.screen == "selection" and key == "d":
            self.show_language_select()
        elif self.screen == "selection" and key == "t":
            self.show_interpret()
        elif self.screen == "language_select" and key in CHAT_LANGUAGES:
            self._select_chat_language(key)
        elif self.screen == "language_select" and key in {"return", "kp_enter"}:
            self._confirm_chat_language()
        elif self.screen == "conversation" and key == "space":
            self.toggle_conversation_recording()
        elif self.screen == "conversation" and key in {"up", "down"}:
            self._scroll_result(-1 if key == "up" else 1)
        elif self.screen == "interpret":
            if key in {"o", "t"}:
                self._activate_dropdown("source" if key == "o" else "target")
            elif key in {"up", "down"}:
                # Once a result is displayed, the arrow keys scroll the result
                # box.  Press O or T again to resume keyboard language selection.
                if self.display_result and self.active_dropdown is None:
                    self._scroll_result(-1 if key == "up" else 1)
                else:
                    self._move_dropdown(-1 if key == "up" else 1)
            elif key in {"return", "kp_enter"}:
                self._confirm_dropdown()
            elif key == "space":
                self.toggle_interpret_recording()

    def _start_control_server(self) -> None:
        CONTROL_SOCKET_PATH.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        server.bind(str(CONTROL_SOCKET_PATH))
        os.chmod(CONTROL_SOCKET_PATH, 0o666)
        server.settimeout(0.5)
        self.control_socket = server
        self.control_thread = threading.Thread(
            target=self._control_server_loop,
            daemon=True,
            name="local-control-server",
        )
        self.control_thread.start()

    def _control_server_loop(self) -> None:
        server = self.control_socket
        if not server:
            return
        while not self.control_stop.is_set():
            try:
                payload, client = server.recvfrom(4096)
                request = json.loads(payload.decode("utf-8"))
                if request.get("type") == "key":
                    key = str(request.get("key", ""))
                    if key:
                        self.root.after(0, lambda value=key: self._handle_key_name(value))
                response = json.dumps(
                    self._control_state(), ensure_ascii=False
                ).encode("utf-8")
                server.sendto(response, client)
            except socket.timeout:
                continue
            except (OSError, ValueError, json.JSONDecodeError):
                if not self.control_stop.is_set():
                    continue

    def _control_state(self) -> dict[str, object]:
        chat_language = (
            self.selected_chat_language[0] if self.selected_chat_language else None
        )
        return {
            "screen": self.screen,
            "status": self.status_text,
            "result": self.display_result,
            "recording": self.recorder.recording,
            "busy": self.busy,
            "chat_language": chat_language,
            "source_language": self.control_source_language,
            "target_language": self.control_target_language,
            "active_dropdown": self.active_dropdown,
            "talking": self.robot_talking,
        }

    def _new_screen(self, name: str) -> int:
        self.recorder.abort()
        self.player.stop()
        self.screen = name
        self.screen_token += 1
        self.busy = False
        self.status_text = ""
        self.display_result = ""
        for child in self.root.winfo_children():
            child.destroy()
        return self.screen_token

    def _top_bar(self, parent: tk.Widget, title: str, show_back: bool = True) -> None:
        bar_height = 46 if self.compact else 72
        bar = tk.Frame(parent, bg=BG, height=bar_height)
        bar.pack(
            fill="x",
            padx=8 if self.compact else 24,
            pady=(4, 2) if self.compact else (14, 4),
        )
        bar.pack_propagate(False)
        tk.Label(
            bar,
            text=title,
            bg=BG,
            fg=WHITE,
            font=("Noto Sans CJK KR", 17 if self.compact else 25, "bold"),
        ).pack(side="left", padx=8)
        if show_back:
            self._button(
                bar,
                "← 뒤로",
                self.show_home,
                width=7 if self.compact else 12,
                bg="#334d70",
                font_size=12 if self.compact else 18,
            ).pack(side="right", padx=4 if self.compact else 8, pady=4)

    def _button(
        self,
        parent: tk.Widget,
        text: str,
        command: object,
        *,
        width: int = 14,
        bg: str = BLUE,
        font_size: int = 18,
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            bg=bg,
            fg=WHITE,
            activebackground=CYAN,
            activeforeground=BG,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=(
                "Noto Sans CJK KR",
                min(font_size, 13) if self.compact else font_size,
                "bold",
            ),
            padx=5 if self.compact else 12,
            pady=4 if self.compact else 10,
        )

    @staticmethod
    def _make_mic_icon(color: str) -> tk.PhotoImage:
        icon = tk.PhotoImage(width=28, height=28)
        icon.put(color, to=(10, 3, 18, 17))
        icon.put(color, to=(7, 10, 10, 18))
        icon.put(color, to=(18, 10, 21, 18))
        icon.put(color, to=(9, 18, 19, 21))
        icon.put(color, to=(13, 20, 16, 25))
        icon.put(color, to=(9, 24, 20, 27))
        return icon

    def show_home(self) -> None:
        token, lower = self._build_robot_menu("home")
        self.status_text = "S 키 또는 시작하기 버튼"
        start_button = self._button(
            lower,
            "▶  시작하기",
            self.show_selection,
            width=16 if self.compact else 20,
            bg=BLUE,
            font_size=20,
        )
        start_button.pack(expand=True, pady=(10, 2))
        tk.Label(
            lower,
            text="키보드: S",
            bg=PANEL,
            fg=MUTED,
            font=("Noto Sans CJK KR", 10 if self.compact else 14),
        ).pack(pady=(0, 8))
        self._announce_screen(token, START_ANNOUNCEMENT)

    def show_selection(self) -> None:
        token, lower = self._build_robot_menu(
            "selection", show_back=True, back_command=self.show_home
        )
        self.status_text = "D 대화하기 · T 통역하기"
        buttons = tk.Frame(lower, bg=PANEL)
        buttons.pack(fill="both", expand=True, padx=14, pady=(12, 2))
        self._button(
            buttons,
            "대화하기",
            self.show_language_select,
            width=12 if self.compact else 16,
            bg=BLUE,
            font_size=18,
        ).pack(side="left", expand=True, padx=8)
        self._button(
            buttons,
            "통역하기",
            self.show_interpret,
            width=12 if self.compact else 16,
            bg="#7357e8",
            font_size=18,
        ).pack(side="left", expand=True, padx=8)
        tk.Label(
            lower,
            text="키보드: D 대화하기  ·  T 통역하기",
            bg=PANEL,
            fg=MUTED,
            font=("Noto Sans CJK KR", 9 if self.compact else 14),
        ).pack(pady=(0, 6))
        self._announce_screen(token, SELECTION_ANNOUNCEMENT)

    def _build_robot_menu(
        self,
        name: str,
        *,
        show_back: bool = False,
        back_command: object | None = None,
    ) -> tuple[int, tk.Frame]:
        token = self._new_screen(name)
        root_frame = tk.Frame(self.root, bg=BG)
        root_frame.pack(fill="both", expand=True)
        root_frame.grid_rowconfigure(0, weight=7, uniform="menu")
        root_frame.grid_rowconfigure(1, weight=3, uniform="menu")
        root_frame.grid_columnconfigure(0, weight=1)

        self.robot_canvas = tk.Canvas(
            root_frame, bg=BG, highlightthickness=0, bd=0
        )
        self.robot_canvas.grid(row=0, column=0, sticky="nsew")
        self.robot_canvas.bind("<Configure>", self._draw_robot)
        self._animate_robot()

        if show_back:
            self._button(
                root_frame,
                "← 뒤로가기",
                back_command or self.show_home,
                width=9,
                bg="#334d70",
                font_size=11,
            ).place(relx=0.985, y=6, anchor="ne")

        lower = tk.Frame(root_frame, bg=PANEL)
        lower.grid(row=1, column=0, sticky="nsew")
        return token, lower

    def _announce_screen(self, token: int, text: str) -> None:
        threading.Thread(
            target=self._speak_for_screen,
            args=(token, text),
            daemon=True,
            name="screen-announcement",
        ).start()

    def _speak_for_screen(self, token: int, text: str) -> None:
        try:
            speech_path = self.service.synthesize(text)
            if token == self.screen_token:
                self.robot_talking = True
                try:
                    self.player.play(speech_path)
                finally:
                    self.robot_talking = False
        except Exception:
            self.robot_talking = False
            pass

    def _home_voice_loop(self, token: int, greet: bool) -> None:
        try:
            if greet:
                self._speak(
                    "안녕하세요. 다함께 봇입니다. "
                    + HOME_GUIDE.replace("\n", " ")
                )
            else:
                self._speak(HOME_GUIDE.replace("\n", " "))
        except Exception:
            pass
        time.sleep(0.4)

        while token == self.screen_token and self.screen == "home":
            try:
                command = self._listen_for_text(token, "home")
                if not command:
                    continue
                compact_command = command.replace(" ", "")
                if "통역" in compact_command:
                    self.root.after(0, self.show_interpret)
                    return
                if "대화" in compact_command:
                    self.root.after(0, self.show_chat)
                    return
            except Exception:
                time.sleep(0.5)

    def _listen_for_text(self, token: int, screen: str) -> str | None:
        audio_path: Path | None = None
        try:
            self.recorder.start()
            for _ in range(32):
                if token != self.screen_token or self.screen != screen:
                    self.recorder.abort()
                    return None
                time.sleep(0.1)
            audio_path = self.recorder.stop()
            if not audio_path or not self._has_audible_speech(audio_path):
                return None
            text = self.service.transcribe(audio_path).strip()
            return text or None
        finally:
            if audio_path:
                audio_path.unlink(missing_ok=True)

    @staticmethod
    def _has_audible_speech(audio_path: Path) -> bool:
        try:
            with wave.open(str(audio_path), "rb") as source:
                if source.getsampwidth() != 2:
                    return True
                samples = array("h", source.readframes(source.getnframes()))
            if sys.byteorder == "big":
                samples.byteswap()
            if not samples:
                return False
            rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
            peak = max(abs(sample) for sample in samples)
            # A short command occupies only a small fraction of a 3.2-second
            # chunk.  Peak detection keeps words such as "오버" from being
            # discarded even when the whole-chunk RMS is low.
            return rms >= 150 or peak >= 900
        except (OSError, wave.Error):
            return True

    def _draw_robot(self, _event: object | None = None) -> None:
        canvas = self.robot_canvas
        if not canvas or not canvas.winfo_exists():
            return
        width = max(canvas.winfo_width(), 2)
        height = max(canvas.winfo_height(), 2)
        fitted = self.robot_source.convert("RGB").resize(
            (width, height), Image.Resampling.LANCZOS
        )
        self.robot_bounds = (0.0, 0.0, float(width), float(height))
        self.robot_photo = ImageTk.PhotoImage(fitted)
        canvas.delete("all")
        canvas.create_image(0, 0, image=self.robot_photo, anchor="nw", tags="robot")

    def _animate_robot(self) -> None:
        canvas = self.robot_canvas
        if (
            self.screen not in {"home", "selection", "conversation"}
            or not canvas
            or not canvas.winfo_exists()
        ):
            return
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width > 10 and height > 10:
            canvas.delete("animated-face")
            phase = self.animation_phase / 9.0

            # The BMO-like base intentionally has no baked-in eyes.  Simple
            # black vertical ovals are animated over the pale green screen.
            left, top, robot_width, robot_height = self.robot_bounds
            gaze_x = math.sin(phase * 0.72) * robot_width * 0.014
            gaze_y = math.sin(phase * 0.43) * robot_height * 0.012
            eye_y = top + robot_height * 0.438
            eye_rx = max(5, robot_width * 0.027)
            eye_ry = max(10, robot_height * 0.083)
            blink_frame = self.animation_phase % 82
            blinking = blink_frame in (0, 1, 2, 3)

            for eye_x in (
                left + robot_width * 0.302,
                left + robot_width * 0.688,
            ):
                if blinking:
                    canvas.create_line(
                        eye_x - eye_rx,
                        eye_y,
                        eye_x + eye_rx,
                        eye_y,
                        fill="#000000",
                        width=max(3, int(robot_height * 0.012)),
                        capstyle="round",
                        tags="animated-face",
                    )
                else:
                    pupil_x = eye_x + gaze_x
                    pupil_y = eye_y + gaze_y
                    canvas.create_oval(
                        pupil_x - eye_rx,
                        pupil_y - eye_ry,
                        pupil_x + eye_rx,
                        pupil_y + eye_ry,
                        fill="#000000",
                        outline="",
                        tags="animated-face",
                    )
            if self.robot_talking:
                mouth_x = left + robot_width * 0.5
                mouth_y = top + robot_height * 0.625
                mouth_width = robot_width * 0.065
                mouth_height = robot_height * (
                    0.025 + 0.025 * (1 + math.sin(phase * 2.4))
                )
                canvas.create_oval(
                    mouth_x - mouth_width,
                    mouth_y - mouth_height,
                    mouth_x + mouth_width,
                    mouth_y + mouth_height,
                    fill="#000000",
                    outline="",
                    tags="animated-face",
                )
            self.animation_phase = (self.animation_phase + 1) % 1000
        self.root.after(70, self._animate_robot)

    def show_language_select(self) -> None:
        self._new_screen("language_select")
        self.status_text = "K/C/V/R 언어 선택 · Enter 확정"
        self.selected_chat_language = None
        self.language_buttons = {}
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill="both", expand=True)
        frame.grid_rowconfigure(0, weight=7, uniform="language")
        frame.grid_rowconfigure(1, weight=3, uniform="language")
        frame.grid_columnconfigure(0, weight=1)

        upper = tk.Frame(frame, bg=BG)
        upper.grid(row=0, column=0, sticky="nsew", padx=8, pady=5)
        upper.grid_rowconfigure(0, weight=0)
        upper.grid_rowconfigure(1, weight=1)
        upper.grid_rowconfigure(2, weight=1)
        upper.grid_columnconfigure(0, weight=1)
        upper.grid_columnconfigure(1, weight=1)

        tk.Label(
            upper,
            text="대화 언어 선택",
            bg=BG,
            fg=WHITE,
            font=("Noto Sans CJK KR", 14 if self.compact else 22, "bold"),
        ).grid(row=0, column=0, columnspan=2, pady=(0, 3))
        self._button(
            upper,
            "← 뒤로가기",
            self.show_selection,
            width=9,
            bg="#334d70",
            font_size=10,
        ).place(relx=1.0, y=0, anchor="ne")

        for index, (key, (display, _language)) in enumerate(CHAT_LANGUAGES.items()):
            button = self._button(
                upper,
                f"{display}  [{key.upper()}]",
                lambda selected=key: self._select_chat_language(selected),
                width=14,
                bg="#385d8a",
                font_size=14,
            )
            button.grid(
                row=1 + index // 2,
                column=index % 2,
                sticky="nsew",
                padx=6,
                pady=5,
            )
            self.language_buttons[key] = button

        lower = tk.Frame(frame, bg=PANEL)
        lower.grid(row=1, column=0, sticky="nsew")
        self.language_selected_label = tk.Label(
            lower,
            text="선택한 언어: 없음",
            bg=PANEL,
            fg=WHITE,
            anchor="w",
            font=("Noto Sans CJK KR", 12 if self.compact else 18, "bold"),
        )
        self.language_selected_label.pack(
            side="left", fill="both", expand=True, padx=14
        )
        actions = tk.Frame(lower, bg=PANEL)
        actions.pack(side="right", padx=8)
        self._button(
            actions,
            "선택",
            self._confirm_chat_language,
            width=7,
            bg=GREEN,
            font_size=12,
        ).pack(side="left", padx=3)
        self._button(
            actions,
            "취소",
            self._cancel_chat_language,
            width=7,
            bg="#596b83",
            font_size=12,
        ).pack(side="left", padx=3)

    def _select_chat_language(self, key: str) -> None:
        if key not in CHAT_LANGUAGES:
            return
        self.selected_chat_language = CHAT_LANGUAGES[key]
        for candidate, button in self.language_buttons.items():
            button.configure(bg=GREEN if candidate == key else "#385d8a")
        display, _language = self.selected_chat_language
        if self.language_selected_label and self.language_selected_label.winfo_exists():
            self.language_selected_label.configure(text=f"선택한 언어: {display}")
        self.player.stop()
        self._announce_screen(self.screen_token, f"{display}를 선택하였습니다.")

    def _cancel_chat_language(self) -> None:
        self.selected_chat_language = None
        for button in self.language_buttons.values():
            button.configure(bg="#385d8a")
        if self.language_selected_label and self.language_selected_label.winfo_exists():
            self.language_selected_label.configure(
                text="선택한 언어: 없음", fg=WHITE
            )

    def _confirm_chat_language(self) -> None:
        if not self.selected_chat_language:
            if self.language_selected_label and self.language_selected_label.winfo_exists():
                self.language_selected_label.configure(
                    text="먼저 언어를 선택해 주세요", fg=RED
                )
            return
        self.show_conversation()

    def show_chat(self) -> None:
        self.show_language_select()

    def show_conversation(self) -> None:
        if not self.selected_chat_language:
            self.show_language_select()
            return
        token = self._new_screen("conversation")
        self.status_text = "Space 또는 마이크 버튼을 눌러 질문하세요"
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill="both", expand=True)
        frame.grid_rowconfigure(0, weight=7, uniform="conversation")
        frame.grid_rowconfigure(1, weight=3, uniform="conversation")
        frame.grid_columnconfigure(0, weight=1)

        upper = tk.Frame(frame, bg=BG)
        upper.grid(row=0, column=0, sticky="nsew")
        self.robot_canvas = tk.Canvas(upper, bg=BG, highlightthickness=0, bd=0)
        self.robot_canvas.pack(fill="both", expand=True)
        self.robot_canvas.bind("<Configure>", self._draw_robot)
        self._animate_robot()
        self._button(
            upper,
            "← 뒤로가기",
            self.show_language_select,
            width=9,
            bg="#334d70",
            font_size=10,
        ).place(relx=0.985, y=6, anchor="ne")

        panel = tk.Frame(frame, bg=PANEL)
        panel.grid(row=1, column=0, sticky="nsew")
        self.status_label = tk.Label(
            panel,
            text="Space 또는 마이크 버튼을 눌러 질문하세요",
            bg=PANEL,
            fg=CYAN,
            justify="center",
            font=("Noto Sans CJK KR", 9 if self.compact else 15, "bold"),
            pady=0,
        )
        self.status_label.pack(fill="x")
        content = tk.Frame(panel, bg=PANEL)
        content.pack(fill="both", expand=True)
        self.mic_icon = self._make_mic_icon(WHITE)
        self.mic_icon_active = self._make_mic_icon("#ffd166")
        self.mic_button = self._button(
            content,
            "마이크",
            self.toggle_conversation_recording,
            width=11,
            bg=BLUE,
            font_size=14,
        )
        self.mic_button.configure(
            image=self.mic_icon, compound="left", width=120, height=42
        )
        self.mic_button.pack(side="left", padx=8, pady=5)
        self.result_text = tk.Text(
            content, height=2, bg="#091b33", fg=WHITE, relief="flat",
            wrap="word", state="disabled",
            font=("Noto Sans CJK KR", 9 if self.compact else 14), padx=5, pady=2,
        )
        result_scrollbar = ttk.Scrollbar(
            content, orient="vertical", command=self.result_text.yview
        )
        self.result_text.configure(yscrollcommand=result_scrollbar.set)
        result_scrollbar.pack(side="right", fill="y", padx=(0, 5), pady=4)
        self.result_text.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=4)

        greeting = CHAT_GREETINGS[self.selected_chat_language[1]]
        self._announce_screen(token, greeting)

    def toggle_conversation_recording(self) -> None:
        if self.busy or self.screen != "conversation":
            return
        if not self.recorder.recording:
            try:
                self.recorder.start()
                self._set_status("듣는 중", RED)
                if self.mic_button:
                    self.mic_button.configure(
                        bg=RED, text="듣기 종료", image=self.mic_icon_active
                    )
            except Exception as exc:
                self._show_error(f"녹음을 시작하지 못했습니다: {exc}")
            return

        try:
            audio_path = self.recorder.stop()
            if self.mic_button:
                self.mic_button.configure(
                    bg=BLUE, text="마이크", image=self.mic_icon
                )
            if not audio_path:
                self._set_status("음성이 녹음되지 않았습니다", RED)
                return
            self.busy = True
            self._set_mic_enabled(False)
            self._set_status("AI가 질문을 분석 중", CYAN)
            token = self.screen_token
            self._run_worker(
                token,
                lambda: self._process_conversation(audio_path, token),
            )
        except Exception as exc:
            self._show_error(f"녹음을 완료하지 못했습니다: {exc}")

    def _process_conversation(self, audio_path: Path, token: int) -> None:
        try:
            if not self.selected_chat_language:
                raise RuntimeError("대화 언어가 선택되지 않았습니다.")
            text = self.service.transcribe(audio_path)
            if not text:
                raise RuntimeError("음성이 인식되지 않았습니다.")
            display, language = self.selected_chat_language
            answer = self.service.chat_in_language(text, language)
            followup = CHAT_FOLLOWUPS[language]
            if token != self.screen_token:
                return
            self.root.after(
                0,
                lambda: self._set_result(
                    f"나: {text}\nAI ({display}): {answer}"
                ),
            )
            self.root.after(0, lambda: self._set_status("AI가 답변 중", GREEN))
            self._speak(f"{answer} {followup}")
            if token == self.screen_token:
                self.root.after(
                    0,
                    lambda: self._set_status(
                        "다른 질문은 Space 또는 마이크 버튼", CYAN
                    ),
                )
        finally:
            audio_path.unlink(missing_ok=True)

    def _chat_voice_loop(self, token: int) -> None:
        started = False
        utterance_parts: list[str] = []
        recording_started_at = 0.0
        start_message = (
            "이제 대화를 시작하겠습니다. 교과서 내용 중 궁금한 내용이 있으면 "
            "말씀해 주세요."
        )

        try:
            self.root.after(0, lambda: self._set_status("대화 방법 안내 중", CYAN))
            self._speak(CHAT_GUIDE.replace("\n", " "))
        except Exception:
            pass
        if token != self.screen_token or self.screen != "chat":
            return
        self.root.after(0, lambda: self._set_status("'시작' 음성 대기 중", CYAN))

        while token == self.screen_token and self.screen == "chat":
            audio_path: Path | None = None
            try:
                if not self.recorder.recording:
                    self.recorder.start()
                    recording_started_at = time.monotonic()

                while time.monotonic() - recording_started_at < 3.2:
                    if token != self.screen_token or self.screen != "chat":
                        self.recorder.abort()
                        return
                    time.sleep(0.1)

                audio_path = self.recorder.stop()
                if token != self.screen_token or self.screen != "chat":
                    if audio_path:
                        audio_path.unlink(missing_ok=True)
                    return

                # Start the next capture before STT.  Speech spoken while the
                # previous chunk is being transcribed is therefore not lost.
                self.recorder.start()
                recording_started_at = time.monotonic()

                if not audio_path or not self._has_audible_speech(audio_path):
                    continue
                text = self.service.transcribe(audio_path).strip()
                if not text:
                    continue
                compact_text = "".join(
                    character for character in text.lower() if character.isalnum()
                )
                over_detected = any(
                    marker in compact_text for marker in ("오버", "오바", "over")
                )
                self.root.after(
                    0,
                    lambda heard=text: self._set_result(f"인식: {heard}"),
                )

                if "종료" in compact_text:
                    self.recorder.abort()
                    self.root.after(0, self.show_home)
                    return

                if not started:
                    if over_detected:
                        self.recorder.abort()
                        guidance = "먼저 시작이라고 말씀해 주세요."
                        self.root.after(
                            0,
                            lambda: self._set_status(
                                "먼저 '시작'이라고 말씀해 주세요", RED
                            ),
                        )
                        self._speak(guidance)
                        if token != self.screen_token:
                            return
                        self.recorder.start()
                        recording_started_at = time.monotonic()
                        continue
                    if "시작" not in compact_text:
                        self.root.after(
                            0,
                            lambda: self._set_status(
                                "'시작' 음성 대기 중", CYAN
                            ),
                        )
                        continue
                    started = True
                    self.recorder.abort()
                    self.root.after(0, lambda: self._set_status("대화 시작 안내", CYAN))
                    self._speak(start_message)
                    if token != self.screen_token:
                        return
                    self.root.after(0, lambda: self._set_status("듣는 중", RED))
                    self.recorder.start()
                    recording_started_at = time.monotonic()
                    continue

                if over_detected:
                    before_over = re.split(
                        r"오\s*[버바]|over", text, maxsplit=1, flags=re.IGNORECASE
                    )[0].strip(" ,.!?")
                    if before_over:
                        utterance_parts.append(before_over)
                    question = " ".join(utterance_parts).strip()
                    utterance_parts.clear()
                    if not question:
                        self.recorder.abort()
                        self.root.after(0, lambda: self._set_status("질문을 말씀해 주세요", RED))
                        self._speak("질문을 말씀해 주세요.")
                        if token != self.screen_token:
                            return
                        self.recorder.start()
                        recording_started_at = time.monotonic()
                        continue

                    self.recorder.abort()
                    self.root.after(
                        0,
                        lambda q=question: self._set_result(
                            f"나: {q}\nAI가 답변 생성 중..."
                        ),
                    )
                    self.root.after(0, lambda: self._set_status("AI가 답변 생성 중", CYAN))
                    answer = self.service.chat(question)
                    if token != self.screen_token:
                        return
                    self.root.after(
                        0,
                        lambda q=question, a=answer: self._set_result(
                            f"나: {q}\nAI: {a}"
                        ),
                    )
                    self.root.after(0, lambda: self._set_status("AI 답변 중", GREEN))
                    self._speak(answer)
                    if token != self.screen_token:
                        return
                    self.root.after(0, lambda: self._set_status("듣는 중", RED))
                    self.recorder.start()
                    recording_started_at = time.monotonic()
                    continue

                utterance_parts.append(text)
                heard = " ".join(utterance_parts)
                self.root.after(
                    0,
                    lambda value=heard: self._set_result(f"듣는 중\n나: {value}"),
                )
                self.root.after(0, lambda: self._set_status("듣는 중", RED))
            except Exception:
                if token == self.screen_token:
                    self.root.after(0, lambda: self._set_status("음성을 다시 말씀해 주세요", RED))
                time.sleep(0.5)
            finally:
                if audio_path:
                    audio_path.unlink(missing_ok=True)

    def show_interpret(self) -> None:
        token = self._new_screen("interpret")
        self.status_text = "O/T 선택 · ↑↓ 이동 · Enter 확정 · Space 녹음"
        self.active_dropdown = None
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill="both", expand=True)
        frame.grid_rowconfigure(0, weight=7, uniform="interpret")
        frame.grid_rowconfigure(1, weight=3, uniform="interpret")
        frame.grid_columnconfigure(0, weight=1)

        upper = tk.Frame(frame, bg=BG)
        upper.grid(row=0, column=0, sticky="nsew", padx=8, pady=6)
        upper.grid_columnconfigure(0, weight=1)
        upper.grid_columnconfigure(1, weight=1)
        upper.grid_rowconfigure(1, weight=1)
        self._button(
            upper, "← 뒤로가기", self.show_selection, width=9,
            bg="#334d70", font_size=10,
        ).place(relx=1.0, y=0, anchor="ne")
        tk.Label(
            upper, text="통역 언어 설정", bg=BG, fg=WHITE,
            font=("Noto Sans CJK KR", 14 if self.compact else 22, "bold"),
        ).grid(row=0, column=0, columnspan=2, pady=(0, 10))

        values = [display for display, _language in INTERPRET_LANGUAGES]
        source_box = tk.Frame(upper, bg=PANEL)
        target_box = tk.Frame(upper, bg=PANEL)
        source_box.grid(row=1, column=0, sticky="nsew", padx=(0, 5), pady=5)
        target_box.grid(row=1, column=1, sticky="nsew", padx=(5, 0), pady=5)
        tk.Label(
            source_box, text="원본 언어 선택 [O]", bg=PANEL, fg=WHITE,
            font=("Noto Sans CJK KR", 11 if self.compact else 17, "bold"),
        ).pack(pady=(20, 8))
        tk.Label(
            target_box, text="통역 언어 선택 [T]", bg=PANEL, fg=WHITE,
            font=("Noto Sans CJK KR", 11 if self.compact else 17, "bold"),
        ).pack(pady=(20, 8))
        self.source_combo = ttk.Combobox(
            source_box, values=values, state="readonly", width=14,
            font=("Noto Sans CJK KR", 11),
        )
        self.target_combo = ttk.Combobox(
            target_box, values=values, state="readonly", width=14,
            font=("Noto Sans CJK KR", 11),
        )
        self.source_combo.current(0)
        self.target_combo.current(2)
        self.control_source_language = INTERPRET_LANGUAGES[0][0]
        self.control_target_language = INTERPRET_LANGUAGES[2][0]
        self.source_combo.pack(pady=4)
        self.target_combo.pack(pady=4)
        self.source_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._confirm_combo_mouse("source"),
        )
        self.target_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._confirm_combo_mouse("target"),
        )

        lower = tk.Frame(frame, bg=PANEL)
        lower.grid(row=1, column=0, sticky="nsew")
        self.status_label = tk.Label(
            lower,
            text="O/T 선택 · ↑↓ 이동 · Enter 확정 · Space 녹음",
            bg=PANEL, fg=CYAN,
            font=("Noto Sans CJK KR", 9 if self.compact else 14, "bold"),
        )
        self.status_label.pack(fill="x")
        content = tk.Frame(lower, bg=PANEL)
        content.pack(fill="both", expand=True)
        self.mic_icon = self._make_mic_icon(WHITE)
        self.mic_icon_active = self._make_mic_icon("#ffd166")
        self.mic_button = self._button(
            content, "마이크", self.toggle_interpret_recording,
            width=11, bg=BLUE, font_size=14,
        )
        self.mic_button.configure(
            image=self.mic_icon, compound="left", width=120, height=42
        )
        self.mic_button.pack(side="left", padx=8, pady=5)
        self.result_text = tk.Text(
            content, height=2, bg="#091b33", fg=WHITE, relief="flat",
            wrap="word", state="disabled",
            font=("Noto Sans CJK KR", 9 if self.compact else 14), padx=5, pady=2,
        )
        result_scrollbar = ttk.Scrollbar(
            content, orient="vertical", command=self.result_text.yview
        )
        self.result_text.configure(yscrollcommand=result_scrollbar.set)
        result_scrollbar.pack(side="right", fill="y", padx=(0, 5), pady=4)
        self.result_text.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=4)
        self._announce_screen(token, "원본 언어와 통역할 언어를 선택해 주세요")

    def _active_combo(self) -> ttk.Combobox | None:
        if self.active_dropdown == "source":
            return self.source_combo
        if self.active_dropdown == "target":
            return self.target_combo
        return None

    def _confirm_combo_mouse(self, which: str) -> None:
        self.active_dropdown = which
        self._confirm_dropdown()

    def _activate_dropdown(self, which: str) -> None:
        self.active_dropdown = which
        combo = self._active_combo()
        if combo:
            combo.focus_set()
            label = "원본 언어" if which == "source" else "통역 언어"
            self._set_status(f"{label}: ↑↓ 이동 후 Enter", GREEN)

    def _move_dropdown(self, direction: int) -> None:
        combo = self._active_combo()
        if not combo:
            self._set_status("먼저 O 또는 T를 누르세요", RED)
            return
        count = len(INTERPRET_LANGUAGES)
        current = combo.current()
        combo.current((current + direction) % count)
        if self.active_dropdown == "source":
            self.control_source_language = combo.get()
        else:
            self.control_target_language = combo.get()
        self._set_status(f"선택 후보: {combo.get()} · Enter로 확정", CYAN)

    def _confirm_dropdown(self) -> None:
        combo = self._active_combo()
        if combo:
            label = "원본" if self.active_dropdown == "source" else "통역"
            if self.active_dropdown == "source":
                self.control_source_language = combo.get()
            else:
                self.control_target_language = combo.get()
            self._set_status(f"{label} 언어: {combo.get()} 선택", GREEN)
        self.active_dropdown = None

    def _interpret_language_pair(
        self,
    ) -> tuple[tuple[str, str], tuple[str, str]] | None:
        if not self.source_combo or not self.target_combo:
            return None
        source_index = self.source_combo.current()
        target_index = self.target_combo.current()
        if source_index < 0 or target_index < 0:
            return None
        return (
            INTERPRET_LANGUAGES[source_index],
            INTERPRET_LANGUAGES[target_index],
        )

    def toggle_interpret_recording(self) -> None:
        if self.busy or self.screen != "interpret":
            return
        pair = self._interpret_language_pair()
        if not pair:
            self._set_status("원본 언어와 통역 언어를 선택하세요", RED)
            return
        if pair[0][1] == pair[1][1]:
            self._set_status("서로 다른 두 언어를 선택하세요", RED)
            return

        if not self.recorder.recording:
            try:
                self.recorder.start()
                self._set_status("듣는 중", RED)
                if self.mic_button:
                    self.mic_button.configure(
                        bg=RED, text="듣기 종료", image=self.mic_icon_active
                    )
            except Exception as exc:
                self._show_error(f"녹음을 시작하지 못했습니다: {exc}")
            return

        try:
            audio_path = self.recorder.stop()
            if self.mic_button:
                self.mic_button.configure(
                    bg=BLUE, text="마이크", image=self.mic_icon
                )
            if not audio_path:
                self._set_status("음성이 녹음되지 않았습니다", RED)
                return
            self.busy = True
            self._set_mic_enabled(False)
            self._set_status("AI가 통역 중", CYAN)
            token = self.screen_token
            self._run_worker(
                token,
                lambda: self._process_interpretation(audio_path, token, pair),
            )
        except Exception as exc:
            self._show_error(f"녹음을 완료하지 못했습니다: {exc}")

    def _process_interpretation(
        self,
        audio_path: Path,
        token: int,
        pair: tuple[tuple[str, str], tuple[str, str]],
    ) -> None:
        try:
            text = self.service.transcribe(audio_path)
            if not text:
                raise RuntimeError("음성이 인식되지 않았습니다.")
            source, target = pair
            translation = self.service.translate(text, source[1], target[1])
            if token != self.screen_token:
                return
            self.root.after(
                0,
                lambda: self._set_result(
                    f"원문 ({source[0]}): {text}\n통역 ({target[0]}): {translation}"
                ),
            )
            self.root.after(0, lambda: self._set_status("통역 음성 출력 중", GREEN))
            self._speak(translation)
            if token == self.screen_token:
                self.root.after(
                    0,
                    lambda: self._set_status(
                        "다시 통역하려면 Space 또는 마이크 버튼", CYAN
                    ),
                )
        finally:
            audio_path.unlink(missing_ok=True)

    def _build_voice_panel(self, parent: tk.Widget, initial_status: str) -> None:
        panel = tk.Frame(parent, bg=PANEL)
        panel.pack(
            fill="both",
            expand=True,
            padx=8 if self.compact else 30,
            pady=(3, 6) if self.compact else (12, 24),
        )
        self.status_label = tk.Label(
            panel,
            text=initial_status,
            bg=PANEL,
            fg=CYAN,
            font=("Noto Sans CJK KR", 13 if self.compact else 20, "bold"),
        )
        self.status_label.pack(pady=(5, 2) if self.compact else (18, 8))
        content = tk.Frame(panel, bg=PANEL)
        content.pack(fill="both", expand=True, padx=5 if self.compact else 0)
        self.mic_button = self._button(
            content,
            "🎙\n마이크",
            self.toggle_recording,
            width=7 if self.compact else 10,
            font_size=15 if self.compact else 22,
        )
        self.mic_button.pack(
            side="left" if self.compact else "top",
            padx=(3, 7) if self.compact else 0,
            pady=4 if self.compact else 10,
        )
        self.result_text = tk.Text(
            content,
            height=5 if self.compact else 8,
            bg="#091b33",
            fg=WHITE,
            insertbackground=WHITE,
            relief="flat",
            wrap="word",
            state="disabled",
            font=("Noto Sans CJK KR", 12 if self.compact else 18),
            padx=7 if self.compact else 18,
            pady=5 if self.compact else 14,
        )
        result_scrollbar = ttk.Scrollbar(
            content, orient="vertical", command=self.result_text.yview
        )
        self.result_text.configure(yscrollcommand=result_scrollbar.set)
        result_scrollbar.pack(
            side="right" if self.compact else "top",
            fill="y" if self.compact else "x",
            padx=3 if self.compact else 24,
            pady=4 if self.compact else 0,
        )
        self.result_text.pack(
            side="left" if self.compact else "top",
            fill="both",
            expand=True,
            padx=3 if self.compact else 24,
            pady=4 if self.compact else (8, 22),
        )

    def _select_language(self, display: str, language: str) -> None:
        self.selected_language = (display, language)
        self._set_status(f"{display} ↔ 한국어 통역 준비", GREEN)
        if self.mic_button:
            self.mic_button.configure(state="normal")

    def toggle_recording(self) -> None:
        if self.busy:
            return
        if not self.recorder.recording:
            try:
                self.recorder.start()
                self._set_status("녹음중", RED)
                if self.mic_button:
                    self.mic_button.configure(bg=RED, text="■\n녹음 종료")
            except Exception as exc:
                self._show_error(f"녹음을 시작하지 못했습니다: {exc}")
            return

        try:
            audio_path = self.recorder.stop()
            self._set_status("녹음완료", GREEN)
            if self.mic_button:
                self.mic_button.configure(bg=BLUE, text="🎙\n마이크")
            if not audio_path:
                self._show_error("녹음된 음성이 없습니다.")
                return
            token = self.screen_token
            mode = self.screen
            language = self.selected_language
            self.busy = True
            self._set_mic_enabled(False)
            self.root.after(450, lambda: self._set_status_if(token, "AI가 답변 생성 중"))
            self._run_worker(
                token,
                lambda: self._process_voice(audio_path, mode, language, token),
            )
        except Exception as exc:
            self._show_error(f"녹음을 완료하지 못했습니다: {exc}")

    def _process_voice(
        self,
        audio_path: Path,
        mode: str,
        language: tuple[str, str] | None,
        token: int,
    ) -> None:
        try:
            text = self.service.transcribe(audio_path)
            if not text:
                raise RuntimeError("음성이 인식되지 않았습니다.")
            if mode == "chat":
                answer = self.service.chat(text)
                heading = f"나: {text}\n\nAI: {answer}"
            else:
                if language is None:
                    raise RuntimeError("통역 언어를 선택하세요.")
                answer, spoken_language = self.service.translate_bidirectional(
                    text, language[0], language[1]
                )
                heading = f"원문: {text}\n\n번역 ({spoken_language}): {answer}"
            if token != self.screen_token:
                return
            self.root.after(0, lambda: self._set_result(heading))
            self.root.after(0, lambda: self._set_status("음성 출력 중", CYAN))
            self._speak(answer)
            self.root.after(0, lambda: self._set_status("완료", GREEN))
        finally:
            audio_path.unlink(missing_ok=True)

    def _speak(self, text: str) -> None:
        speech_path = self.service.synthesize(text)
        self.robot_talking = True
        try:
            self.player.play(speech_path)
        finally:
            self.robot_talking = False

    def _run_worker(
        self,
        token: int,
        work: object,
        *,
        report_errors: bool = True,
    ) -> None:
        def runner() -> None:
            try:
                work()  # type: ignore[operator]
            except Exception as exc:
                if report_errors and token == self.screen_token:
                    self.root.after(0, lambda err=exc: self._show_error(str(err)))
            finally:
                if token == self.screen_token:
                    self.root.after(0, self._worker_finished)

        threading.Thread(target=runner, daemon=True, name="voice-worker").start()

    def _worker_finished(self) -> None:
        self.busy = False
        if self.screen in {"conversation", "interpret"}:
            self._set_mic_enabled(True)

    def _set_status_if(self, token: int, text: str) -> None:
        if token == self.screen_token:
            self._set_status(text, CYAN)

    def _set_status(self, text: str, color: str = CYAN) -> None:
        self.status_text = text
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=text, fg=color)

    def _set_result(self, text: str) -> None:
        self.display_result = text
        if not self.result_text or not self.result_text.winfo_exists():
            return
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self.result_text.configure(state="disabled")
        self.result_text.yview_moveto(0.0)

    def _scroll_result(self, direction: int) -> None:
        """Scroll the visible result box one line with the keyboard."""
        if not self.result_text or not self.result_text.winfo_exists():
            return
        self.result_text.yview_scroll(direction, "units")

    def _set_mic_enabled(self, enabled: bool) -> None:
        if self.mic_button and self.mic_button.winfo_exists():
            self.mic_button.configure(state="normal" if enabled else "disabled")

    def _show_error(self, message: str) -> None:
        self.busy = False
        self._set_status("오류가 발생했습니다", RED)
        self._set_mic_enabled(True)
        messagebox.showerror("다함께 봇", message, parent=self.root)

    def close(self) -> None:
        self.screen_token += 1
        self.control_stop.set()
        if self.control_socket:
            try:
                self.control_socket.close()
            except OSError:
                pass
            self.control_socket = None
        CONTROL_SOCKET_PATH.unlink(missing_ok=True)
        self.recorder.close()
        self.player.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.root.destroy()


def main() -> int:
    try:
        config = Config.from_env()
        root = tk.Tk()
        TouchscreenApp(root, config)
        root.mainloop()
        return 0
    except Exception as exc:
        print(f"[시작 오류] {exc}")
        return 1
