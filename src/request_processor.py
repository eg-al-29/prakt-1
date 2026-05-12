"""
Новый дизайн RequestProcessor - чистая доменная логика.
Зависит только от контрактов (интерфейсов), реализации подменяются.
"""

from contracts import (
    StudentRequest, RequestResult,
    IRequestRepository, INotificationSender, ILogger,
    IResponseGenerator, IDuplicatePolicy, IRequestValidator
)


class RequestProcessor:
    """
    Обработчик обращений студентов.

    Отвечает ТОЛЬКО за бизнес-логику:
    1. Валидировать входные данные
    2. Проверить дубли
    3. Создать обращение
    4. Отправить уведомление
    5. Сформировать ответ

    Все зависимости подменяются через конструктор.
    """

    def __init__(
        self,
        repository: IRequestRepository,
        notification_sender: INotificationSender,
        logger: ILogger,
        response_generator: IResponseGenerator,
        duplicate_policy: IDuplicatePolicy,
        validator: IRequestValidator
    ):
        self.repository = repository
        self.notification_sender = notification_sender
        self.logger = logger
        self.response_generator = response_generator
        self.duplicate_policy = duplicate_policy
        self.validator = validator

    def process(self, request: StudentRequest) -> str:
        """
        Обработать обращение студента.

        Args:
            request: Обращение студента

        Returns:
            Текст ответа студенту

        Raises:
            ValidationError: Если данные некорректны
        """

        # Шаг 1: Валидация
        self.validator.validate(request)

        # Шаг 2: Логирование если срочно
        if request.urgent:
            self.logger.write("URGENT", f"Urgent request from {request.student_id}")

        # Шаг 3: Проверка дублей
        existing = self.repository.find_duplicate(request.student_id, request.topic)
        if existing:
            self.logger.write("INFO", f"Duplicate request from {request.student_id}")
            result = self.duplicate_policy.handle(existing, request)
            if not result.success:
                return result.message
            # Если policy вернул success, продолжаем (merge сценарий)

        # Шаг 4: Создание обращения
        request_id = self.repository.create(
            request.student_id,
            request.topic,
            request.text
        )
        self.logger.write("INFO", f"Request created: id={request_id}, student={request.student_id}")

        # Шаг 5: Отправка уведомления
        message = f"Your request #{request_id} has been created"
        try:
            self.notification_sender.send(request.student_id, message)
            self.logger.write("INFO", f"Notification sent for request {request_id}")
        except Exception as e:
            self.logger.write("ERROR", f"Failed to send notification: {e}")
            # Не прерываем процесс, обращение всё равно создано

        # Шаг 6: Формирование ответа
        response = self.response_generator.generate(request.topic)
        self.logger.write("INFO", f"Response generated: {response}")

        return response