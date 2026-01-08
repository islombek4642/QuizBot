# 🤖 QuizBot

**Advanced Telegram Bot for converting Word documents into interactive Quizzes.**

QuizBot simplifies the process of creating quizzes by letting you upload a `.docx` file, which it then parses and converts into structured tests. You can take these tests yourself or run them in groups with a leaderboard!

---

## ✨ Features

- **🚀 Easy Setup**: Just upload a formatted `.docx` file.
- **👥 Group Support**: Run quizzes in groups with automatic leaderboards.
- **📊 Admin Panel**: Manage users, groups, and view detailed statistics.
- **⏱ Timer Logic**: Configurable timer for questions (default: 30s).
- **🔒 Persistence**: Data is stored securely in PostgreSQL and Redis.
- **🐳 Docker Ready**: Fully containerized for easy deployment.

---

## 📝 Quiz Format Guide

To create a quiz, prepare a Microsoft Word (`.docx`) file. Each question block should follow this format:

```text
?Question text starts with a question mark
+The correct answer starts with a plus
=Wrong answer starts with an equals sign
=Another wrong answer
```

**Example:**

```text
?What is the capital of Uzbekistan?
+Tashkent
=Samarkand
=Bukhara
=Khiva
```

---

## 🛠 Installation & Deployment

### Prerequisities

- Docker & Docker Compose
- Git

### Quick Start (Docker)

1. **Clone the repository:**

   ```bash
   git clone https://github.com/islombek4642/QuizBot.git
   cd QuizBot
   ```

2. **Configure Environment:**

   ```bash
   cp .env.example .env
   # Edit .env and set your BOT_TOKEN and ADMIN_ID
   nano .env
   ```

3. **Run with Docker Compose:**

   ```bash
   sudo docker compose up -d --build
   ```

The bot will start and be available on Telegram!

---

## ⚙️ Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_TOKEN` | Your Telegram Bot Token directly from BotFather | - |
| `ADMIN_ID` | Telegram ID of the admin user | - |
| `DATABASE_URL` | PostgreSQL connection string | ... |
| `REDIS_URL` | Redis connection string | ... |
| `POLL_DURATION_SECONDS` | Time per question in seconds | `30` |
| `BOT_USERNAME` | Username of your bot (without @) | `QuizBot` |

---

## 🤝 Contributing

Contributions are welcome! Please fork the repository and submit a Pull Request.

## 📄 License

This project is open-source.
