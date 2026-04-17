# Gettik MVP

MVP для создания групповых поездок:

- организатор выбирает направление;
- указывает количество людей;
- включает опции (транспорт, еда, активности);
- видит мгновенный пересчет стоимости через HTMX;
- создает страницу поездки и делится ссылкой.

## Stack

- FastAPI
- Jinja2 Templates
- SQLAlchemy Async
- SQLite (по умолчанию, можно переключить на PostgreSQL через `DATABASE_URL`)
- HTMX
- Bootstrap

## Запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Откройте `http://127.0.0.1:8000`.
