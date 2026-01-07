# QuizBot

Telegram bot to convert Word (.docx) test files into Telegram Polls and JSON.

## Features

- Parse `.docx` files with a specific format.
- Automatically create Telegram Polls (Quiz mode).
- Provide JSON output of parsed tests.
- Modular architecture based on `aiogram`.

## Test Format

The `.docx` file should contain tests in the following format:

```text
?Question text?
+Correct answer
=Wrong answer
=Wrong answer
```

Each question must start with `?`. Correct answers with `+` and incorrect answers with `=`.

## Setup

1. Clone the repository.
2. Open `QuizBot` directory.
3. Configure `.env` from `.env.example`.
4. Run `python run.py`.

## Requirements

- Python 3.8+
- `aiogram`
- `python-docx`
- `python-dotenv`
- `sqlalchemy`
