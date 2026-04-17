# Gettik MVP

MVP для создания групповых поездок с современным UI и базовой системой аккаунтов:

- регистрация и вход пользователя;
- личный кабинет с историей поездок;
- создание новой поездки;
- мгновенный пересчет стоимости через HTMX;
- просмотр детальной страницы поездки и ссылки для шаринга.

## Stack

- FastAPI
- Jinja2 Templates
- SQLAlchemy Async
- SQLite (по умолчанию, можно переключить на PostgreSQL через `DATABASE_URL`)
- HTMX
- Bootstrap + custom CSS

## Запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Откройте `http://127.0.0.1:8000`.
