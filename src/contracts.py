"""
Контракты (интерфейсы) для целевого дизайна.
Определяют границы ответственности и позволяют подменять реализации.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class StudentRequest:
    """Доменная модель обращения студента."""
    student_id: str
    topic: str
    text: str
    channel: str
    urgent: bool = False


@dataclass
class Request:
    """Сохранённое обращение в системе."""
    id: int
    student_id: str
    topic: str
    text: str
    status: str = "OPEN"


@dataclass
class RequestResult:
    """Результат обработки обращения."""
    success: bool
    message: str
    request_id: Optional[int] = None


# ===== Контракты для зависимостей =====

class IRequestRepository(ABC):
    """Контракт для хранилища обращений (доступ к данным)."""

    @abstractmethod
    def create(self, student_id: str, topic: str, text: str) -> int:
        """Создать обращение, вернуть его ID."""
        pass

    @abstractmethod
    def find_duplicate(self, student_id: str, topic: str) -> Optional[Request]:
        """Найти существующее обращение от студента по теме."""
        pass


class INotificationSender(ABC):
    """Контракт для отправки уведомлений."""

    @abstractmethod
    def send(self, recipient: str, message: str) -> None:
        """Отправить уведомление."""
        pass


class ILogger(ABC):
    """Контракт для логирования."""

    @abstractmethod
    def write(self, level: str, message: str) -> None:
        """Записать логическое сообщение."""
        pass


class IResponseGenerator(ABC):
    """Контракт для формирования ответа студенту."""

    @abstractmethod
    def generate(self, topic: str) -> str:
        """Сформировать ответ на основе темы обращения."""
        pass


class IDuplicatePolicy(ABC):
    """Контракт для политики обработки дублей."""

    @abstractmethod
    def handle(self, existing: Request, incoming: StudentRequest) -> RequestResult:
        """Обработать ситуацию с дублем."""
        pass


class IRequestValidator(ABC):
    """Контракт для валидации обращений."""

    @abstractmethod
    def validate(self, request: StudentRequest) -> None:
        """Проверить корректность обращения. Raise exception если ошибка."""
        pass