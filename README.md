# Практическая работа: Диагностика и рефакторинг системы обработки обращений студентов

## 1. Описание проекта

Учебный проект для демонстрации типовых проблем проектирования на примере системы обработки обращений студентов в службу поддержки университета. 

**Исходный код демонстрирует:**
- Смешение ответственности в одном классе
- Жёсткие зависимости на конкретные реализации
- Невозможность модульного тестирования
- Отсутствие контрактов и интерфейсов

## 2. ДИАГНОСТИЧЕСКАЯ ЗАПИСКА

### 2.1 Выделение смешанных ответственностей

Класс `RequestProcessor` нарушает принцип единственной ответственности (SRP). В нём смешаны **минимум 8 разных причин для изменения**:

1. **Валидация входных данных**
   - Проверка null/пустых значений
   - Правила валидации может потребоваться расширить (макс. длина текста, формат studentId и т.д.)
   - При изменении правил — нужно менять метод `process()`

2. **Доступ к базе данных и запросы**
   - Создание подключения к БД
   - Формирование SQL-запросов (уязвимо к SQL-injection)
   - Логика проверки дублей
   - При смене БД или схемы — нужны изменения в методе

3. **Журналирование и аудит**
   - Создание FileLogger с жёсткой путём
   - Логирование разных событий (URGENT, дубль, создание)
   - При смене способа логирования (файл → БД → облако) — меняется код `process()`

4. **Выбор и отправка уведомлений**
   - Проверка канала (email, messenger, default)
   - Создание SMTP-клиента
   - Создание Messenger API клиента
   - При добавлении нового канала (SMS, Telegram, вебхук) — усложняется условная логика

5. **Форматирование сообщений**
   - Текст сообщения собирается ad-hoc ("Created request #" + id)
   - При требовании изменить формат, добавить переводы или шаблоны — нужны изменения

6. **Правила формирования ответа студенту**
   - Логика выбора ответа по теме (password → одно, schedule → другое)
   - При добавлении новых типов обращений — разрастается условная логика

7. **Обработка дублей и конфликтов**
   - Проверка существующих обращений
   - Политика обработки дублей (сейчас просто reject)
   - При изменении политики (merge, update, notify) — меняется логика

8. **Конфигурирование и инициализация ресурсов**
   - Жёсткие строки подключения к БД
   - Жёсткие адреса SMTP-сервера
   - При изменении конфигурации — нужны изменения кода

### 2.2 Анализ связности и сцепления

#### Жёсткие зависимости (tight coupling)

| Зависимость | Проблема | Последствие при расширении |
|---|---|---|
| `new DatabaseClient("jdbc:...", "user", "pass")` | Создание БД-клиента прямо в методе с hardcoded credentials | Невозможно подменить реализацию на тесте; невозможно переключаться на другую БД |
| `new FileLogger("c:/logs/app.log")` | Жёсткий путь до файла логов | Не работает на Linux/Mac; нельзя перенаправить логи; нельзя использовать другой способ логирования |
| `new SmtpClient("smtp.server", 25)` | Hardcoded адрес SMTP-сервера | При смене провайдера почты или добавлении SSL — нужны изменения кода |
| `new MessengerApiClient("token123")` | Секретный ключ в коде | Уязвимость; при смене токена нужны изменения кода |
| SQL-запросы строками | Уязвимость к SQL-injection | `"where student_id=" + studentId` — атака возможна |

#### Протечки доменной логики

- **Доменная логика** (что хочет бизнес): создать обращение, проверить дубль, отправить уведомление
- **Инфраструктурные детали** (как это реализуется), смешанные в методе:
  - JDBC подключение
  - Файловая система (логи)
  - SMTP протокол
  - Specific API токены

**Последствие:** нельзя переиспользовать доменную логику; нельзя менять реализацию без правки метода.

#### Риск при расширении

Если потребуется:
- ✗ Добавить новый канал уведомления → большой if-else, новые импорты, новые клиенты
- ✗ Переключиться на другую БД → если сейчас MongoDB, нужно переписать весь класс
- ✗ Добавить метрики и tracing → нужны изменения везде, где есть вызовы клиентов
- ✗ Написать модульный тест → невозможно без mock-объектов на уровне файловой системы, сети, БД

### 2.3 Диагностика тестируемости

Модульное тестирование класса `RequestProcessor` **невозможно** по минимум трём причинам:

1. **Создание зависимостей внутри метода (Hidden Dependencies)**
   ```
   db = new DatabaseClient("jdbc:...","user","pass")
   logger = new FileLogger("c:/logs/app.log")
   smtp = new SmtpClient("smtp.server", 25)
   ```
   - Тест не может подменить `DatabaseClient` на mock
   - Тест не может перехватить реальное подключение к БД
   - Тест создаёт реальное подключение при каждом запуске → медленно и нестабильно

2. **Реальный I/O и побочные эффекты**
   - Реально пишет в файл логов: `logger.write("URGENT: ...")`
   - Реально подключается к SMTP: `smtp.send(...)`
   - Реально выполняет SQL запросы: `db.insert(...)`
   - Тест загрязняет файловую систему, сеть, БД
   - Результат теста зависит от внешнего состояния (интернет доступен? БД работает?)

3. **Отсутствие контрактов (интерфейсов)**
   - Нет `IDatabase`, `ILogger`, `INotificationSender`
   - Нельзя создать mock-объект, потому что нет контракта для подмены
   - Даже с dependency injection пришлось бы менять приватные реализации

4. **Смешанная логика (難 难отделить)**
   - Валидация → условный вывод → БД → логирование → выбор канала → отправка → выбор ответа
   - Нельзя изолировать один аспект для теста
   - Пример: для теста проверки дубля нужно создать реальную БД, заполнить её, вызвать метод, проверить результат
   - Это уже не модульный тест, а интеграционный

5. **Отсутствие разделения на чистые функции**
   - Функция `process()` не чистая (есть побочные эффекты)
   - Нельзя предсказать результат без запуска реального кода
   - Нельзя покрыть все ветвления (что если SMTP недоступен на этапе отправки? exception затирает результат).

**Вывод:** Тест для `RequestProcessor.process()` **неизбежно становится интеграционным**, требует реальной БД, реального логирования, реальной отправки — это медленно, нестабильно, и не даёт уверенности в корректности доменной логики.

### 2.4 Выделение точек изменчивости

Минимум **4 точки изменчивости**, которые вероятнее всего будут меняться требованиями:

1. **Каналы уведомлений (HIGH)**
   - Текущие: Email, Messenger
   - Вероятные добавления: SMS, Telegram, Discord, Webhook, Push-notification
   - Каждый канал имеет свой API, формат сообщения, конфигурацию
   - **Решение:** Contract `INotificationSender`; factory для выбора реализации

2. **Формат и содержание уведомления (HIGH)**
   - Текущий: "Created request #123"
   - Требования могут измениться: шаблоны, переводы, расширенная информация, HTML-формат
   - **Решение:** Отдельный компонент `NotificationMessageFormatter` или `IMessageTemplate`

3. **Политика обработки дублей (MEDIUM)**
   - Текущая: просто reject ("Already exists")
   - Варианты: merge с существующей, update timestamp, notify студента о статусе, дать возможность обновить
   - **Решение:** Strategy pattern; отдельный `DuplicatePolicy` компонент

4. **Правила формирования ответа по теме (MEDIUM)**
   - Текущие правила: password → "Reset", schedule → "We will check", default → "Accepted"
   - При росте типов обращений: FAQ, маршрутизация на специалистов, автоматические actions
   - **Решение:** Отдельный `ResponseGenerator` с rule engine или chain of responsibility

5. **Источники данных и хранилище (MEDIUM)**
   - Текущее: JDBC + конкретная БД
   - Варианты: другая РСБД, NoSQL, микросервисный API, кэш
   - **Решение:** Repository pattern; contract `IRequestRepository`

6. **Логирование и аудит (LOW-MEDIUM)**
   - Текущее: файлы на диске
   - Варианты: БД, облачные логи (CloudWatch, Datadog), метрики, трейсинг
   - **Решение:** Contract `ILogger`/`IAuditLog`

7. **Конфигурирование (MEDIUM)**
   - JDBC connection string, SMTP адрес, токены — все hardcoded
   - Требуется external config (properties, environment variables, config server)
   - **Решение:** Configuration object, dependency injection контейнер

---

## 3. ЦЕЛЕВОЙ ДИЗАЙН (UML)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Граница доменной логики                         │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    RequestProcessor (Service)                   │    │
│  │  - process(request: StudentRequest): String                     │    │
│  │  + зависит от контрактов (interfaces)                           │    │
│  │  - чистая доменная логика, легко тестировать                   │    │
│  └──────────┬────┬──────────┬───────────┬──────────┬──────────────┘    │
│             │    │          │           │          │                    │
│             │    │          │           │          │                    │
│          (uses) (uses)     (uses)     (uses)      (uses)                │
│             │    │          │           │          │                    │
│             ▼    ▼          ▼           ▼          ▼                    │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │
│  │IRequestRepository│  │INotificationSender│  │ResponseGenerator │    │
│  │ (interface)      │  │ (interface)      │  │ (interface)      │    │
│  │ - create()       │  │ - send(msg)      │  │ - generate(...)  │    │
│  │ - findDuplicate()│  │                  │  │                  │    │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘    │
│             │                 │                      │                  │
│             └─────────────────┴──────────────────────┘                  │
│                          ▲                                             │
└──────────────────────────┼─────────────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────────────┐
│                          │ Инфраструктурный слой                       │
├──────────────────────────┼──────────────────────────────────────────────┤
│                          │                                              │
│                     (реализации)                                        │
│       ┌────────────────────────────────────┐                           │
│       │   Логирование и аудит              │                           │
│       ├────────────────────────────────────┤                           │
│       │ ILogger (interface)                │                           │
│       │ - FileLogger (реализация)          │                           │
│       │ - DatabaseLogger (реализация)      │                           │
│       │ - CloudLogger (реализация)         │                           │
│       └────────────────────────────────────┘                           │
│                                                                         │
│   ┌──────────────────────┐  ┌──────────────────────┐                  │
│   │ RequestRepository    │  │ NotificationSender   │                  │
│   │ Impl (JDBC)          │  │ Impl (Strategy)      │                  │
│   │ - database           │  │ - emailSender        │                  │
│   │ - queries            │  │ - messengerSender    │                  │
│   │                      │  │ - smsSender (future) │                  │
│   └──────────────────────┘  └──────────────────────┘                  │
│                                                                         │
│   ┌────────────────────────┐                                          │
│   │ ResponseGenerator      │                                          │
│   │ Impl (Rules-based)     │                                          │
│   │ - rules (map)          │                                          │
│   │ - templates            │                                          │
│   └────────────────────────┘                                          │
│                                                                         │
│   ┌────────────────────────┐                                          │
│   │ Validation             │                                          │
│   │ - RequestValidator     │                                          │
│   │ - DuplicatePolicy      │                                          │
│   └────────────────────────┘                                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

Composition Root / DI Container (конфигурирование):
  - ApplicationConfiguration
    - создаёт экземпляры компонентов
    - подбирает нужные реализации интерфейсов
    - управляет жизненным циклом

Для тестов:
  - TestConfiguration или mock objects вместо реальных реализаций
```

---

## 4. ПЛАН РЕФАКТОРИНГА (6-10 шагов)

### Шаг 1: Выделение контрактов (interfaces)
**Цель:** Разорвать прямые зависимости на реализации.

- Создать `IRequestRepository` с методами `create()`, `findDuplicate()`
- Создать `INotificationSender` с методом `send(message: String, recipient: String): void`
- Создать `ILogger` с методом `write(level: String, message: String): void`
- Создать `IResponseGenerator` с методом `generate(topic: String): String`
- Создать `IDuplicatePolicy` с методом `handle(existing: Request): RequestResult`

**Результат:** RequestProcessor зависит только от интерфейсов, реализации остаются в инфраструктурном слое.

### Шаг 2: Внедрение зависимостей через конструктор (Dependency Injection)
**Цель:** Избавиться от `new` внутри метода.

```java
class RequestProcessor {
    private IRequestRepository repository;
    private INotificationSender notificationSender;
    private ILogger logger;
    private IResponseGenerator responseGenerator;
    private IDuplicatePolicy duplicatePolicy;
    
    RequestProcessor(IRequestRepository repo, INotificationSender sender, 
                     ILogger log, IResponseGenerator respGen, IDuplicatePolicy dupPolicy) {
        this.repository = repo;
        this.notificationSender = sender;
        this.logger = log;
        this.responseGenerator = respGen;
        this.duplicatePolicy = dupPolicy;
    }
    
    function process(studentId, topic, text, channel, urgentFlag) { ... }
}
```

**Результат:** Зависимости передаются снаружи, ничего не создаётся внутри метода.

### Шаг 3: Извлечение валидации в отдельный компонент
**Цель:** Отделить проверку входных данных от бизнес-логики.

```java
class RequestValidator {
    void validate(StudentRequest request) throws ValidationException {
        if (request.studentId == null) throw new ValidationException("...");
        if (request.topic.isEmpty()) throw new ValidationException("...");
        // ... остальные правила
    }
}
```

**Результат:** `RequestProcessor.process()` начинает с `validator.validate(request)`, валидация переиспользуема.

### Шаг 4: Выделение логики обработки дублей
**Цель:** Распределить ответственность за策略 обработки дублей.

```java
interface IDuplicatePolicy {
    RequestResult handle(Request existing, Request incoming);
}

class RejectDuplicatePolicy implements IDuplicatePolicy {
    public RequestResult handle(Request existing, Request incoming) {
        return RequestResult.rejected("Already exists");
    }
}

class MergeDuplicatePolicy implements IDuplicatePolicy {
    public RequestResult handle(Request existing, Request incoming) {
        // обновить существующую, return success
    }
}
```

**Результат:** `RequestProcessor` просто вызывает `duplicatePolicy.handle()`, не содержит условной логики.

### Шаг 5: Отделение логики выбора ответа
**Цель:** Централизовать правила формирования ответа.

```java
interface IResponseGenerator {
    String generate(String topic);
}

class TopicBasedResponseGenerator implements IResponseGenerator {
    private Map<String, String> rules; // password -> "Reset instruction", schedule -> "We will check"
    
    public String generate(String topic) {
        return rules.getOrDefault(topic.toLowerCase(), "Request accepted");
    }
}
```

**Результат:** `RequestProcessor` просто вызывает `responseGenerator.generate(topic)`.

### Шаг 6: Отделение логики отправки уведомлений
**Цель:** Выбор канала → отдельный компонент, каждый канал → отдельная реализация.

```java
interface INotificationSender {
    void send(String recipient, String message) throws NotificationException;
}

class EmailNotificationSender implements INotificationSender {
    private SmtpClient smtp;
    public void send(String email, String message) { smtp.send(email, message); }
}

class MessengerNotificationSender implements INotificationSender {
    private MessengerApiClient api;
    public void send(String userId, String message) { api.send(userId, message); }
}

class CompositeNotificationSender implements INotificationSender {
    private Map<String, INotificationSender> senders;
    public void send(String recipient, String message) {
        String channel = determineChannel(recipient);
        senders.get(channel).send(recipient, message);
    }
}
```

**Результат:** `RequestProcessor` просто вызывает `notificationSender.send()`, не знает о каналах.

### Шаг 7: Создание конфигурационного слоя (Composition Root)
**Цель:** Централизовать создание объектов и выбор реализаций.

```java
class ApplicationConfiguration {
    static RequestProcessor createRequestProcessor() {
        IRequestRepository repo = new JdbcRequestRepository(
            connectionString, username, password
        );
        ILogger logger = new FileLogger(logFilePath);
        INotificationSender notif = new CompositeNotificationSender(
            Map.of(
                "email", new EmailNotificationSender(smtpConfig),
                "messenger", new MessengerNotificationSender(messengerToken)
            )
        );
        IResponseGenerator respGen = new TopicBasedResponseGenerator(rulesMap);
        IDuplicatePolicy dupPolicy = new RejectDuplicatePolicy();
        
        return new RequestProcessor(repo, notif, logger, respGen, dupPolicy);
    }
    
    static RequestProcessor createForTesting() {
        // мокируем всё
        return new RequestProcessor(
            new InMemoryRequestRepository(),
            new NoOpNotificationSender(),
            new NoOpLogger(),
            new FixedResponseGenerator("Test response"),
            new RejectDuplicatePolicy()
        );
    }
}
```

**Результат:** Вся конфигурация в одном месте, легко менять реализации.

### Шаг 8: Написание модульных тестов
**Цель:** Покрыть доменную логику быстрыми, надёжными тестами.

```java
@Test
void testSuccessfulRequestCreation() {
    // Arrange
    InMemoryRequestRepository repo = new InMemoryRequestRepository();
    InMemoryNotificationSender notif = new InMemoryNotificationSender();
    RequestProcessor proc = new RequestProcessor(repo, notif, ...);
    StudentRequest req = new StudentRequest("john", "password", "forgot pwd");
    
    // Act
    String response = proc.process(req);
    
    // Assert
    assertEquals("Reset instruction sent", response);
    assertEquals(1, repo.count());
    assertEquals(1, notif.sentMessages.size());
}

@Test
void testDuplicateDetection() {
    // Arrange
    InMemoryRequestRepository repo = new InMemoryRequestRepository();
    repo.create(new Request("john", "password", "..."));
    RequestProcessor proc = new RequestProcessor(repo, ...);
    StudentRequest newReq = new StudentRequest("john", "password", "...");
    
    // Act
    String response = proc.process(newReq);
    
    // Assert
    assertEquals("Already exists", response);
    assertEquals(1, repo.count()); // не добавилось
}
```

**Результат:** Тесты быстрые (нет I/O), надёжные (нет зависимостей), читаемые (ясная структура).

### Шаг 9: Миграция к новому дизайну
**Цель:** Постепенно переключить production код на новый дизайн.

- Обновить точку входа (контроллер, API endpoint) использовать новый `RequestProcessor`
- Создать мокируемые реализации для интеграционных тестов (БД, логирование)
- Запустить регрессионные тесты на production-like конфигурации

**Результат:** Весь код работает, тесты зелёные.

### Шаг 10: Документирование и рефлексия
**Цель:** Зафиксировать паттерны и выводы.

- Документировать архитектурные решения (ADR)
- Подготовить примеры расширения (добавление нового канала)
- Обновить диаграммы

---

## 5. СТРУКТУРА ПРОЕКТА

```
prakt-1/
├── README.md (этот файл)
├── docs/
│   ├── DIAGNOSTICS.md (расширенная диагностика)
│   ├── uml_target_design.puml (PlantUML диаграмма)
│   └── uml_target_design.png (PNG диаграмма)
├── src/
│   ├── main/ (Java/C#/Python)
│   │   ├── Original.java (исходный "плохой" код)
│   │   ├── Domain/
│   │   │   ├── StudentRequest.java
│   │   │   ├── Request.java
│   │   │   └── RequestResult.java
│   │   ├── Services/
│   │   │   └── RequestProcessor.java (новый дизайн)
│   │   ├── Contracts/
│   │   │   ├── IRequestRepository.java
│   │   │   ├── INotificationSender.java
│   │   │   ├── ILogger.java
│   │   │   ├── IResponseGenerator.java
│   │   │   └── IDuplicatePolicy.java
│   │   ├── Infrastructure/
│   │   │   ├── JdbcRequestRepository.java
│   │   │   ├── EmailNotificationSender.java
│   │   │   ├── MessengerNotificationSender.java
│   │   │   ├── FileLogger.java
│   │   │   └── TopicBasedResponseGenerator.java
│   │   └── Configuration/
│   │       └── ApplicationConfiguration.java
│   └── test/
│       ├── RequestProcessorSuccessTest.java
│       └── RequestProcessorDuplicateTest.java
├── pom.xml (для Maven)
└── .gitignore
```

---

## 6. ИНСТРУКЦИЯ ПО ЗАПУСКУ

### Требования
- Java 11+ (или ваш язык)
- Maven 3.6+ (или Gradle/pip)
- Git

### Установка и запуск тестов

```bash
cd prakt-1
git clone <repo> .
mvn clean test
```

**Ожидаемый результат:**
- 2 теста-заготовки, помеченные как `@Ignore` или в статусе `PENDING`
- Сообщение: "2 tests pending" или аналогичное

### Запуск всей сборки

```bash
mvn clean verify
```

---

## 7. РЕЗЮМЕ РЕЗУЛЬТАТОВ

### Диагностика: Выявлено
✗ 8 смешанных ответственностей
✗ 5+ жёстких зависимостей на инфраструктуру
✗ 5 причин невозможности модульного тестирования
✗ 4+ точки изменчивости

### Целевой дизайн: Спроектирован
✓ Разделение на доменный и инфраструктурный слои
✓ Контракты (интерфейсы) для всех зависимостей
✓ Dependency Injection для подмены реализаций
✓ Чистая доменная логика в `RequestProcessor`

### План рефакторинга: Составлен
✓ 10 пошаговых этапов с минимальным риском
✓ Ясная последовательность: контракты → DI → извлечение логики → конфигурация → тесты

### Каркас проекта: Создан
✓ Структура с разделением на слои
✓ 2 теста-заготовки (success + duplicate)
✓ Mock-объекты для подмены зависимостей

---

**Автор:** Практическая работа в рамках курса "Проектные паттерны"  
**Дата:** 2026-05-12  
**Статус:** Диагностика и проектирование завершены; готово к рефакторингу