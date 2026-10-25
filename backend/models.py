from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Password(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=12, max_length=128)


class Item(Model):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["할 일", "일정"] = "할 일"
    original_text: str = Field(default="", max_length=6000)
    category: Literal["구매", "집안일", "업무", "건강", "개인", "기타"] = "기타"
    description: str = Field(default="", max_length=5000)
    status: Literal["미시작", "진행중", "완료"] = "미시작"
    flag: Literal["없음", "대기중", "나중에"] = "없음"
    importance: Literal["보통", "중요"] = "보통"
    planned_date: date | None = None
    deadline: date | None = None
    time_mode: Literal["미정", "시간 확정", "종일"] = "미정"
    start_time: time | None = None
    end_time: time | None = None
    location: str = Field(default="", max_length=300)

    @field_validator("start_time", "end_time")
    @classmethod
    def local_minute_time(cls, value):
        if value is not None and (value.tzinfo is not None or value.second or value.microsecond):
            raise ValueError("시각은 한국 시간의 시·분으로 입력해 주세요.")
        return value

    @model_validator(mode="after")
    def valid_time(self):
        if self.time_mode == "시간 확정":
            if self.planned_date is None or self.start_time is None:
                raise ValueError("시간을 정할 때는 날짜와 시작 시각이 필요합니다.")
            if self.end_time and self.end_time <= self.start_time:
                raise ValueError("종료 시각은 시작 시각보다 늦어야 합니다. 여러 날 일정은 아직 지원하지 않습니다.")
        elif self.start_time or self.end_time:
            raise ValueError("시간 미정·종일 항목에는 임의의 시각을 넣을 수 없습니다.")
        if self.time_mode == "종일" and not self.planned_date:
            raise ValueError("종일 일정의 날짜를 선택해 주세요.")
        if self.kind == "일정" and self.deadline:
            raise ValueError("일정 날짜와 할 일의 마감일은 별개입니다.")
        return self


class CreateItem(Item):
    request_id: str = Field(min_length=16, max_length=80)


class UpdateItem(Item):
    revision: int = Field(ge=1)


class Feedback(Model):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["질문", "오류", "기능 제안"]
    content: str = Field(min_length=1, max_length=10000)
    page: str = Field(default="", max_length=100)
    request_id: str = Field(min_length=16, max_length=80)


class Message(Model):
    content: str = Field(min_length=1, max_length=10000)
    request_id: str = Field(min_length=16, max_length=80)


class FeedbackUpdate(Model):
    status: Literal["접수", "검토 중", "예정", "작업 중", "확인 요청", "반영 완료", "보류"]
    priority: Literal["보통", "높음", "낮음"] = "보통"
    resolution: str = Field(default="", max_length=5000)
    release_version: str = Field(default="", max_length=80)
    revision: int = Field(ge=1)

    @model_validator(mode="after")
    def completion_evidence(self):
        if self.status in ("확인 요청", "반영 완료") and (not self.resolution or not self.release_version):
            raise ValueError("반영 내용과 적용 버전을 기록해 주세요.")
        return self


class ExportSelection(Model):
    ids: list[str] = Field(min_length=1, max_length=100)



