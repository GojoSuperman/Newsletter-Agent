"""OpenAI 구조화 출력 헬퍼. 노드는 이 함수 하나만 안다."""
import os
from functools import lru_cache

from openai import OpenAI
from pydantic import BaseModel


@lru_cache
def get_client() -> OpenAI:
    return OpenAI()                                   # OPENAI_API_KEY 환경 변수 사용


def model_name() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def ask_structured(system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    last: Exception | None = None
    for _ in range(2):                                # 1회 재시도
        try:
            r = get_client().chat.completions.parse(
                model=model_name(),
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format=schema,
            )
            parsed = r.choices[0].message.parsed
            if parsed is None:
                raise RuntimeError("모델이 스키마에 맞는 응답을 주지 않았습니다")
            return parsed
        except Exception as e:                        # noqa: BLE001
            last = e
    raise RuntimeError(f"LLM 호출 실패: {last!r}")
