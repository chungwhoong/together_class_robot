from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import Config


@dataclass(frozen=True)
class DebateTopic:
    id: str
    title: str
    prompt: str
    unit_title: str
    activity_kind: str = "토론"
    textbook_id: str | None = None


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    description: str
    system_prompt: str
    unit_title: str
    textbook_id: str


FALLBACK_DEBATES = [
    DebateTopic(
        "world-culture-event",
        "세계 문화 행사는 늘려야 할까요?",
        "세계 문화 행사는 더 많이 열어야 한다.",
        "5학년 1학기 · 의논하며 토의해요",
        "토의",
    ),
    DebateTopic(
        "public-bike",
        "우리 동네에 공공 자전거를 늘려야 할까요?",
        "우리 동네에 공공 자전거를 더 많이 설치해야 한다.",
        "5학년 1학기 · 의논하며 토의해요",
        "토의",
    ),
    DebateTopic(
        "social-network-friendship",
        "SNS는 우정을 쌓는 데 도움이 될까요?",
        "누리소통망은 우정을 쌓는 데 도움이 된다.",
        "6학년 1학기 · 절차를 지키며 토론해요",
    ),
    DebateTopic(
        "school-disposables",
        "학교에서 일회용품 사용을 금지해야 할까요?",
        "환경을 위해 학교에서 일회용품 사용을 금지해야 한다.",
        "6학년 1학기 · 절차를 지키며 토론해요",
    ),
]


class SupabaseLearningService:
    def __init__(self, config: Config) -> None:
        self.url = config.supabase_url.rstrip("/")
        self.key = config.supabase_anon_key

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def _select(self, table: str, params: dict[str, str]) -> list[dict[str, object]]:
        if not self.configured:
            raise RuntimeError("Supabase 환경변수가 설정되지 않았습니다.")
        request = Request(
            f"{self.url}/rest/v1/{table}?{urlencode(params, safe='(),.*')}",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Accept": "application/json",
            },
        )
        with urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, list):
            raise RuntimeError("Supabase 응답 형식이 올바르지 않습니다.")
        return data

    def load_debates(self) -> list[DebateTopic]:
        try:
            rows = self._select(
                "textbooks",
                {
                    "select": "id,curriculum_unit_id,unit_title,activity_kind,topic",
                    "registration_kind": "eq.debate",
                    "order": "grade.asc,semester.asc,unit_number.asc",
                    "limit": "50",
                },
            )
            topics = [
                DebateTopic(
                    str(row.get("curriculum_unit_id") or row.get("id")),
                    str(row.get("topic") or row.get("unit_title") or "토론 주제"),
                    str(row.get("topic") or row.get("unit_title") or "토론 주제"),
                    str(row.get("unit_title") or "교사 등록 자료"),
                    str(row.get("activity_kind") or "토론"),
                    str(row.get("id")),
                )
                for row in rows
            ]
            return topics or list(FALLBACK_DEBATES)
        except Exception:
            return list(FALLBACK_DEBATES)

    def load_personas(self) -> list[Persona]:
        textbooks = self._select(
            "textbooks",
            {
                "select": "id,unit_title",
                "registration_kind": "eq.persona",
                "school_code": "is.null",
                "limit": "100",
            },
        )
        units = {str(row["id"]): str(row.get("unit_title") or "국어 교과서") for row in textbooks}
        if not units:
            return []
        rows = self._select(
            "personas",
            {
                "select": "id,character_name,textbook_id,description,system_prompt",
                "textbook_id": f"in.({','.join(units)})",
                "order": "character_name.asc",
                "limit": "100",
            },
        )
        return [
            Persona(
                str(row["id"]),
                str(row.get("character_name") or "인물"),
                str(row.get("description") or "교과서 속 인물"),
                str(row.get("system_prompt") or "교과서 속 인물로 1인칭으로 답하세요."),
                units.get(str(row.get("textbook_id")), "국어 교과서"),
                str(row.get("textbook_id")),
            )
            for row in rows
        ]
