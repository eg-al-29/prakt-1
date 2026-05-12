"""
Модульные тесты для RequestProcessor.

Тесты используют mock-объекты вместо реальных зависимостей.
Быстрые, надёжные, не требуют БД/сети/файлов.
"""

import pytest
from contracts import StudentRequest
from request_processor import RequestProcessor
from test_doubles import (
    InMemoryRequestRepository,
    InMemoryNotificationSender,
    NoOpLogger,
    FixedResponseGenerator,
    RejectDuplicatePolicy,
    SimpleRequestValidator
)


class TestRequestProcessorSuccess:
    """Тест успешной обработки нового обращения."""

    def setup_method(self):
        """Подготовить окружение для теста."""
        self.repo = InMemoryRequestRepository()
        self.notif = InMemoryNotificationSender()
        self.logger = NoOpLogger()
        self.response_gen = FixedResponseGenerator("Request accepted")
        self.dup_policy = RejectDuplicatePolicy()
        self.validator = SimpleRequestValidator()

        self.processor = RequestProcessor(
            repository=self.repo,
            notification_sender=self.notif,
            logger=self.logger,
            response_generator=self.response_gen,
            duplicate_policy=self.dup_policy,
            validator=self.validator
        )

    def test_successful_request_creation(self):
        """
        GIVEN: Студент создаёт новое обращение
        WHEN: process() вызывается с валидными данными
        THEN: обращение создаётся, уведомление отправляется, возвращается ответ
        """

        # Arrange
        request = StudentRequest(
            student_id="john_doe",
            topic="password",
            text="I forgot my password",
            channel="email",
            urgent=False
        )

        # Act
        response = self.processor.process(request)

        # Assert
        assert response == "Request accepted"
        assert len(self.repo.requests) == 1
        assert self.repo.requests[1].student_id == "john_doe"
        assert len(self.notif.sent_messages) == 1
        assert self.notif.sent_messages[0]["recipient"] == "john_doe"
        assert "john_doe" not in self.notif.sent_messages[0]["message"]  # не содержит ID в сообщении

    def test_urgent_flag_logged(self):
        """
        GIVEN: Срочное обращение студента
        WHEN: process() вызывается с urgent=True
        THEN: в логах появляется URGENT сообщение
        """

        # Arrange
        request = StudentRequest(
            student_id="jane_smith",
            topic="schedule",
            text="Schedule conflict",
            channel="email",
            urgent=True
        )

        # Act
        self.processor.process(request)

        # Assert
        urgent_logs = [m for m in self.logger.messages if m["level"] == "URGENT"]
        assert len(urgent_logs) >= 1
        assert "jane_smith" in urgent_logs[0]["message"]

    def test_response_generation_called(self):
        """
        GIVEN: Обращение с темой "schedule"
        WHEN: process() выполняется
        THEN: response_generator используется для формирования ответа
        """

        # Arrange - используем специальный generator для проверки
        class CheckedResponseGenerator(FixedResponseGenerator):
            def __init__(self):
                super().__init__("We will check schedule")
                self.called_with_topic = None

            def generate(self, topic: str) -> str:
                self.called_with_topic = topic
                return super().generate(topic)

        response_gen = CheckedResponseGenerator()
        processor = RequestProcessor(
            repository=self.repo,
            notification_sender=self.notif,
            logger=self.logger,
            response_generator=response_gen,
            duplicate_policy=self.dup_policy,
            validator=self.validator
        )

        request = StudentRequest(
            student_id="bob",
            topic="schedule",
            text="When is exam?",
            channel="email",
            urgent=False
        )

        # Act
        response = processor.process(request)

        # Assert
        assert response_gen.called_with_topic == "schedule"
        assert response == "We will check schedule"


class TestRequestProcessorDuplicate:
    """Тест обнаружения дублей."""

    def setup_method(self):
        """Подготовить окружение для теста."""
        self.repo = InMemoryRequestRepository()
        self.notif = InMemoryNotificationSender()
        self.logger = NoOpLogger()
        self.response_gen = FixedResponseGenerator()
        self.dup_policy = RejectDuplicatePolicy()
        self.validator = SimpleRequestValidator()

        self.processor = RequestProcessor(
            repository=self.repo,
            notification_sender=self.notif,
            logger=self.logger,
            response_generator=self.response_gen,
            duplicate_policy=self.dup_policy,
            validator=self.validator
        )

    def test_duplicate_detection(self):
        """
        GIVEN: В системе уже существует обращение от студента по теме "password"
        WHEN: Этот же студент отправляет похожее обращение
        THEN: система обнаруживает дубль и не создаёт новое обращение
        """

        # Arrange - создаём первое обращение
        first_request = StudentRequest(
            student_id="alice",
            topic="password",
            text="Forgot my password",
            channel="email",
            urgent=False
        )

        # Act - первое обращение обрабатывается успешно
        response1 = self.processor.process(first_request)
        assert len(self.repo.requests) == 1
        first_notification_count = len(self.notif.sent_messages)

        # Arrange - второе, похожее обращение
        second_request = StudentRequest(
            student_id="alice",
            topic="password",
            text="Still can't access",
            channel="email",
            urgent=False
        )

        # Act - второе обращение обнаруживается как дубль
        response2 = self.processor.process(second_request)

        # Assert
        assert response2 == "Already exists"
        assert len(self.repo.requests) == 1  # новое обращение не создано!
        assert len(self.notif.sent_messages) == first_notification_count  # новое уведомление не отправлено!

    def test_duplicate_logged(self):
        """
        GIVEN: Обнаружен дубль
        WHEN: duplicate_policy обрабатывает ситуацию
        THEN: событие попадает в логи
        """

        # Arrange
        first = StudentRequest(
            student_id="charlie",
            topic="schedule",
            text="When is midterm?",
            channel="email",
            urgent=False
        )
        self.processor.process(first)
        self.logger.messages.clear()  # очистить логи после первого обращения

        second = StudentRequest(
            student_id="charlie",
            topic="schedule",
            text="Still need to know",
            channel="email",
            urgent=False
        )

        # Act
        self.processor.process(second)

        # Assert
        duplicate_logs = [m for m in self.logger.messages if "Duplicate" in m["message"]]
        assert len(duplicate_logs) >= 1

    def test_different_students_no_duplicate(self):
        """
        GIVEN: Разные студенты отправляют обращения по одной теме
        WHEN: process() вызывается для каждого
        THEN: они не считаются дублями
        """

        # Arrange & Act
        request1 = StudentRequest(
            student_id="dave",
            topic="password",
            text="Forgot password",
            channel="email",
            urgent=False
        )
        response1 = self.processor.process(request1)

        request2 = StudentRequest(
            student_id="eve",  # другой студент!
            topic="password",
            text="Forgot password too",
            channel="email",
            urgent=False
        )
        response2 = self.processor.process(request2)

        # Assert
        assert response1 != "Already exists"
        assert response2 != "Already exists"
        assert len(self.repo.requests) == 2  # оба обращения созданы


# ===== Дополнительные тесты для валидации =====

class TestRequestProcessorValidation:
    """Тесты валидации входных данных."""

    def setup_method(self):
        self.repo = InMemoryRequestRepository()
        self.notif = InMemoryNotificationSender()
        self.logger = NoOpLogger()
        self.response_gen = FixedResponseGenerator()
        self.dup_policy = RejectDuplicatePolicy()
        self.validator = SimpleRequestValidator()

        self.processor = RequestProcessor(
            repository=self.repo,
            notification_sender=self.notif,
            logger=self.logger,
            response_generator=self.response_gen,
            duplicate_policy=self.dup_policy,
            validator=self.validator
        )

    def test_validation_missing_student_id(self):
        """Пустой student_id должен вызвать исключение."""
        request = StudentRequest(
            student_id="",
            topic="password",
            text="Help!",
            channel="email",
            urgent=False
        )

        with pytest.raises(ValueError):
            self.processor.process(request)

        assert len(self.repo.requests) == 0  # обращение не создано

    def test_validation_missing_topic(self):
        """Пустая topic должна вызвать исключение."""
        request = StudentRequest(
            student_id="frank",
            topic="",
            text="Help!",
            channel="email",
            urgent=False
        )

        with pytest.raises(ValueError):
            self.processor.process(request)

        assert len(self.repo.requests) == 0

    def test_validation_missing_text(self):
        """Пустой text должен вызвать исключение."""
        request = StudentRequest(
            student_id="grace",
            topic="password",
            text="",
            channel="email",
            urgent=False
        )

        with pytest.raises(ValueError):
            self.processor.process(request)

        assert len(self.repo.requests) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])