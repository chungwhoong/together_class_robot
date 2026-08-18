from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    api_key: str
    mic_device: str = "plughw:CARD=Device,DEV=0"
    speaker_device: str = "plughw:CARD=Device,DEV=0"
    sample_rate: int = 16_000
    channels: int = 1
    sample_format: str = "S16_LE"
    llm_model: str = "gpt-5.6-luna"
    stt_model: str = "gpt-4o-transcribe"
    tts_model: str = "tts-1"
    tts_voice: str = "nova"
    tts_leading_silence_ms: int = 300
    max_history_turns: int = 12
    supabase_url: str = ""
    supabase_anon_key: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY가 없습니다. .env.example을 복사해 .env를 설정하세요."
            )
        return cls(
            api_key=api_key,
            mic_device=os.getenv(
                "ALSA_MIC_DEVICE", "plughw:CARD=Device,DEV=0"
            ),
            speaker_device=os.getenv(
                "ALSA_SPEAKER_DEVICE", "plughw:CARD=Device,DEV=0"
            ),
            sample_rate=int(os.getenv("AUDIO_SAMPLE_RATE", "16000")),
            channels=int(os.getenv("AUDIO_CHANNELS", "1")),
            sample_format=os.getenv("AUDIO_FORMAT", "S16_LE"),
            llm_model=os.getenv("OPENAI_LLM_MODEL", "gpt-5.6-luna"),
            stt_model=os.getenv("OPENAI_STT_MODEL", "gpt-4o-transcribe"),
            tts_model=os.getenv("OPENAI_TTS_MODEL", "tts-1"),
            tts_voice=os.getenv("OPENAI_TTS_VOICE", "nova"),
            tts_leading_silence_ms=max(
                0, int(os.getenv("TTS_LEADING_SILENCE_MS", "300"))
            ),
            max_history_turns=max(1, int(os.getenv("MAX_HISTORY_TURNS", "12"))),
            supabase_url=os.getenv("SUPABASE_URL", "").strip(),
            supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", "").strip(),
        )
