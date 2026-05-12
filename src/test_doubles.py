"""
Реализации контрактов для тестирования (mock-объекты).
Используются в unit тестах для подмены реальных зависимостей.
"""

from typing import Dict, List, Optional
from contracts import (
    Request, RequestResult, StudentRequest,
    IRequestRepository, INotificationSender, ILogger,
    IResponseGenerator, IDuplicatePolicy, IRequestValidator
)


# ===== Mock реализации для тестирования =====

class InMemoryRequestRepository(IRequestRepository):
    """Хранилище в памяти - для тестов."""

    def __init__(self):
        self.requests: Dict[int, Request] = {}
        self.next_id = 1

    def create(self, student_id: str, topic: str, text: str) -> int:
        request_id = self.next_id
        self.requests[request_id] = Request(
            id=request_id,
            student_id=student_id,
            topic=topic,
            text=text
        )
        self.next_id += 1
        return request_id

    def find_duplicate(self, student_id: str, topic: str) -> Optional[Request]:
        for req in self.requests.values():
            if req.student_id == student_id and req.topic == topic:
                return req
        return None


class InMemoryNotificationSender(INotificationSender):
    """Отправитель уведомлений в памяти - для тестов."""

    def __init__(self):
        self.sent_messages: List[Dict] = []

    def send(self, recipient: str, message: str) -> None:
        self.sent_messages.append({
            "recipient": recipient,
            "message": message
        })


class NoOpLogger(ILogger):
    """Logger без операций - для тестов когда логи не нужны."""

    def __init__(self):
        self.messages: List[Dict] = []

    def write(self, level: str, message: str) -> None:
        self.messages.append({"level": level, "message": message})


class FixedResponseGenerator(IResponseGenerator):
    """Генератор ответов с фиксированным ответом - для тестов."""

    def __init__(self, fixed_response: str = "Test response"):
        self.fixed_response = fixed_response

    def generate(self, topic: str) -> str:
        return self.fixed_response


class RejectDuplicatePolicy(IDuplicatePolicy):
    """Политика: отклонить дубль."""

    def handle(self, existing: Request, incoming: StudentRequest) -> RequestResult:
        return RequestResult(
            success=False,
            message="Already exists"
        )


class SimpleRequestValidator(IRequestValidator):
    """Простая валидация - для тестов."""

    def validate(self, request: StudentRequest) -> None:
        if not request.student_id:
            raise ValueError("student_id is required")
        if not request.topic:
            raise ValueError("topic is required")
        if not request.text:
            raise ValueError("text is required")