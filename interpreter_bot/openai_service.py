from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI

from .config import Config


LANGUAGES = {
    "1": ("영어", "English"),
    "2": ("우즈베크어", "Uzbek"),
    "3": ("중국어 간체", "Simplified Chinese"),
    "4": ("러시아어", "Russian"),
}


class OpenAIVoiceService:
    def __init__(self, config: Config, temp_dir: Path) -> None:
        self.config = config
        self.temp_dir = temp_dir
        self.client = OpenAI(api_key=config.api_key)
        self.history: list[dict[str, str]] = []
        self.mode_histories: dict[str, list[dict[str, str]]] = {}

    def transcribe(self, audio_path: Path) -> str:
        with audio_path.open("rb") as audio:
            result = self.client.audio.transcriptions.create(
                model=self.config.stt_model,
                file=audio,
            )
        return result.text.strip()

    def chat(self, user_text: str) -> str:
        instructions = (
            "당신은 라즈베리파이 음성 비서입니다. 항상 자연스럽고 명확한 한국어로 "
            "답하세요. 음성으로 듣기 좋게 간결하게 답하고 마크다운 표기는 피하세요."
        )
        messages = [
            {"role": "developer", "content": instructions},
            *self.history,
            {"role": "user", "content": user_text},
        ]
        response = self.client.responses.create(
            model=self.config.llm_model,
            input=messages,
        )
        answer = response.output_text.strip()
        self.history.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": answer},
            ]
        )
        max_messages = self.config.max_history_turns * 2
        self.history = self.history[-max_messages:]
        return answer

    def chat_in_language(self, user_text: str, language: str) -> str:
        instructions = (
            f"You are a friendly school study assistant. Reply only in {language}. "
            "Give a clear, age-appropriate, concise spoken answer. Help the learner "
            "understand language arts and textbook topics. Avoid markdown."
        )
        messages = [
            {"role": "developer", "content": instructions},
            *self.history,
            {"role": "user", "content": user_text},
        ]
        response = self.client.responses.create(
            model=self.config.llm_model,
            input=messages,
        )
        answer = response.output_text.strip()
        self.history.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": answer},
            ]
        )
        self.history = self.history[-self.config.max_history_turns * 2 :]
        return answer

    def guided_chat(
        self,
        user_text: str,
        instructions: str,
        history_key: str,
    ) -> str:
        """Run a separate, prompt-guided conversation for debate or persona mode."""
        history = self.mode_histories.setdefault(history_key, [])
        response = self.client.responses.create(
            model=self.config.llm_model,
            input=[
                {"role": "developer", "content": instructions},
                *history,
                {"role": "user", "content": user_text},
            ],
        )
        answer = response.output_text.strip()
        if not answer:
            raise ValueError("AI 답변이 비어 있습니다.")
        history.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": answer},
            ]
        )
        self.mode_histories[history_key] = history[-self.config.max_history_turns * 2 :]
        return answer

    def translate(self, text: str, source_language: str, target_language: str) -> str:
        prompt = f"""
You are a strict interpreter from {source_language} to {target_language}.
Translate the input only into {target_language}.
Preserve meaning, names, numbers, and tone. Do not answer the content.
Return only the translated text without labels, notes, or markdown.
Input: {json.dumps(text, ensure_ascii=False)}
"""
        response = self.client.responses.create(
            model=self.config.llm_model,
            input=prompt,
        )
        translation = response.output_text.strip()
        if not translation:
            raise ValueError("번역 결과가 비어 있습니다.")
        return translation

    def translate_bidirectional(
        self, text: str, target_display_name: str, target_language: str
    ) -> tuple[str, str]:
        prompt = f"""
You are a strict two-way interpreter between Korean and {target_language}.
Detect whether the input is Korean or {target_language}.
- Korean input: translate only into {target_language}.
- {target_language} input: translate only into Korean.
- If ambiguous, infer the most likely direction from its language and script.
- Preserve meaning, names, numbers, and tone. Do not answer the content.
Return JSON only: {{"direction":"to_target" or "to_korean","translation":"..."}}.
Input: {json.dumps(text, ensure_ascii=False)}
"""
        response = self.client.responses.create(
            model=self.config.llm_model,
            input=prompt,
            text={"format": {"type": "json_object"}},
        )
        data = json.loads(response.output_text)
        direction = data.get("direction")
        translation = str(data.get("translation", "")).strip()
        if direction not in {"to_target", "to_korean"} or not translation:
            raise ValueError("번역 응답 형식이 올바르지 않습니다.")
        spoken_language = target_display_name if direction == "to_target" else "한국어"
        return translation, spoken_language

    def synthesize(self, text: str) -> Path:
        output_path = self.temp_dir / "response.wav"
        with self.client.audio.speech.with_streaming_response.create(
            model=self.config.tts_model,
            voice=self.config.tts_voice,
            input=text,
            response_format="wav",
        ) as response:
            response.stream_to_file(output_path)
        return output_path
