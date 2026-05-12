"""
ПЛОХОЙ КОД - Пример из кейса для диагностики.
Демонстрирует: смешение ответственности, жёсткие зависимости, проблемы тестируемости.
"""

class RequestProcessor:
    def process(self, student_id, topic, text, channel, urgent_flag):
        """
        Обработка обращения студента.

        Смешивает валидацию, БД, логирование, отправку уведомлений, выбор ответа.
        """

        # Валидация
        if not student_id or not topic or not text:
            raise ValueError("Bad request")

        # Создание зависимостей ВНУТРИ метода - жёсткая привязка к реализации
        db = DatabaseClient("postgresql://localhost/support", "user", "pass")
        logger = FileLogger("/var/log/app.log")

        # Логирование
        if urgent_flag:
            logger.write(f"URGENT: {student_id}")

        # Проверка дублей напрямую через SQL - уязвимо к SQL-injection!
        query = f"SELECT COUNT(*) FROM requests WHERE student_id='{student_id}' AND topic='{topic}'"
        existing = db.query(query)

        if existing > 0:
            logger.write(f"Duplicate request: {student_id}")
            return "Already exists"

        # Сохранение в БД
        insert_query = f"INSERT INTO requests(student_id, topic, text, status) VALUES ('{student_id}', '{topic}', '{text}', 'OPEN')"
        request_id = db.insert(insert_query)

        # Выбор канала и отправка уведомления - смешанная логика
        if channel == "email":
            smtp = SmtpClient("smtp.server", 25)
            smtp.send(f"{student_id}@mail.ru", "Support", f"Created request #{request_id}")
        elif channel == "messenger":
            msg_api = MessengerApiClient("token123")
            msg_api.send(student_id, f"Created request #{request_id}")
        else:
            # Default - снова email
            smtp = SmtpClient("smtp.server", 25)
            smtp.send(f"{student_id}@mail.ru", "Support", f"Created request #{request_id}")

        logger.write(f"Created request id={request_id}")

        # Выбор ответа по теме - ещё одна смешанная логика
        if "password" in topic.lower():
            return "Reset instruction sent"
        elif "schedule" in topic.lower():
            return "We will check schedule"
        else:
            return "Request accepted"


# ===== Инфраструктурные классы (hardcoded) =====

class DatabaseClient:
    """Жёсткая привязка к конкретной БД с hardcoded credentials."""

    def __init__(self, connection_string, user, password):
        self.connection_string = connection_string
        self.user = user
        self.password = password
        # Real connection happens here

    def query(self, sql):
        """Выполнить SELECT запрос."""
        # Реальное подключение к БД
        return 0  # stub

    def insert(self, sql):
        """Выполнить INSERT запрос, вернуть ID."""
        # Реальное подключение к БД
        return 1  # stub


class FileLogger:
    """Логирование только в файл, с hardcoded путём."""

    def __init__(self, file_path):
        self.file_path = file_path
        # Open file

    def write(self, message):
        """Записать сообщение в файл логов."""
        # Real file I/O
        pass


class SmtpClient:
    """Отправка по SMTP с hardcoded адресом сервера."""

    def __init__(self, host, port):
        self.host = host
        self.port = port
        # Real SMTP connection

    def send(self, to, subject, body):
        """Отправить email."""
        # Real network I/O
        pass


class MessengerApiClient:
    """API мессенджера с hardcoded токеном."""

    def __init__(self, token):
        self.token = token
        # Init API

    def send(self, user_id, message):
        """Отправить сообщение в мессенджер."""
        # Real API call
        pass