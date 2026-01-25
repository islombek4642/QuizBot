from fastapi import FastAPI, HTTPException, Depends, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlalchemy import select
from contextlib import asynccontextmanager
import os
import hmac
import hashlib
import structlog
import json
import time
from urllib.parse import parse_qs, unquote, parse_qsl
from db.session import get_db
from models.user import User
from models.quiz import Quiz
from services.quiz_service import QuizService
from pydantic import BaseModel, Field
from typing import List, Optional
from core.config import settings
from datetime import datetime
from db.session import get_db, get_redis

logger = structlog.get_logger()

# API Documentation
API_DESCRIPTION = """
## QuizBot Editor API

REST API for managing quizzes in QuizBot Telegram application.

### Authentication

All endpoints require authentication via one of the following methods:

1. **Telegram WebApp initData** (recommended):
   - Header: `X-Telegram-Init-Data: <initData>`
   - Or: `Authorization: tma <initData>`

2. **Token Authentication** (legacy):
   - Header: `X-Auth-Token: <token>`

### Rate Limits

- No explicit rate limits, but excessive usage may be throttled.
- Telegram initData expires after 1 hour.
- Auth tokens expire after 30 days.
"""

TAGS_METADATA = [
    {
        "name": "quizzes",
        "description": "Quiz CRUD operations - create, read, update, delete quizzes.",
    },
    {
        "name": "info",
        "description": "Public information endpoints.",
    },
]

app = FastAPI(
    title="QuizBot Editor API",
    description=API_DESCRIPTION,
    version="1.0.0",
    openapi_tags=TAGS_METADATA,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "QuizBot Support",
        "url": "https://t.me/quizbot_support",
    },
    license_info={
        "name": "MIT",
    },
)


@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response = await call_next(request)

    # Prevent caching of the HTML entrypoint (especially when it contains token in query)
    if request.url.path == "/":
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Pragma", "no-cache")
        response.headers.setdefault("Expires", "0")

    return response

# Enable CORS for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://xamidullayevi.uz",
        "https://www.xamidullayevi.uz",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Pydantic Models with Documentation ===

class Question(BaseModel):
    """A single quiz question with options."""
    question: str = Field(..., description="The question text", max_length=500, examples=["What is 2+2?"])
    options: List[str] = Field(..., description="List of answer options (2-10 items)", min_length=2, max_length=10)
    correct_option_id: int = Field(..., description="Index of the correct answer (0-based)", ge=0)

    class Config:
        json_schema_extra = {
            "example": {
                "question": "What is the capital of Uzbekistan?",
                "options": ["Tashkent", "Samarkand", "Bukhara", "Khiva"],
                "correct_option_id": 0
            }
        }


class QuizUpdate(BaseModel):
    """Request body for updating a quiz."""
    title: str = Field(..., description="Quiz title", max_length=255, examples=["Geography Quiz"])
    questions: List[Question] = Field(..., description="List of quiz questions")


class QuizListItem(BaseModel):
    """Quiz item in list response."""
    id: int = Field(..., description="Unique quiz ID")
    title: str = Field(..., description="Quiz title")
    questions_count: int = Field(..., description="Number of questions in the quiz")
    created_at: datetime = Field(..., description="Quiz creation timestamp")


class QuizDetail(BaseModel):
    """Detailed quiz response with questions."""
    id: int = Field(..., description="Unique quiz ID")
    title: str = Field(..., description="Quiz title")
    questions: List[Question] = Field(..., description="List of quiz questions")


class BotStats(BaseModel):
    """Bot statistics."""
    users: int = Field(..., description="Total registered users")
    quizzes: int = Field(..., description="Total quizzes created")
    questions: int = Field(..., description="Total questions across all quizzes")


class BotInfo(BaseModel):
    """Bot information response."""
    bot_username: str = Field(..., description="Bot username without @")
    bot_link: str = Field(..., description="Direct link to the bot")
    stats: BotStats = Field(..., description="Bot statistics")


class SuccessResponse(BaseModel):
    """Generic success response."""
    status: str = Field(default="success", description="Operation status")

def verify_telegram_data(init_data: str, max_age_seconds: int = 3600) -> Optional[int]:
    """
    Verify Telegram WebApp initData and return the user ID.
    See: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        return None
        
    try:
        vals = dict(parse_qsl(init_data))
        hash_val = vals.pop('hash', None)
        if not hash_val:
            return None

        # TTL check via auth_date (recommended)
        auth_date_raw = vals.get('auth_date')
        if auth_date_raw:
            try:
                auth_date = int(auth_date_raw)
                if int(time.time()) - auth_date > max_age_seconds:
                    logger.warning("InitData expired", auth_date=auth_date)
                    return None
            except Exception:
                return None
        
        # Data check string is alphabetically sorted keys
        data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(vals.items())])
        
        # Secret key is HMAC_SHA256(data_check_string, WebAppData)
        # where WebAppData is HMAC_SHA256(bot_token, "WebAppData")
        web_app_data_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(web_app_data_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash != hash_val:
            logger.warning("Telegram data verification failed", init_data=init_data)
            return None
            
        user_data = json.loads(vals.get('user', '{}'))
        return user_data.get('id')
    except Exception as e:
        logger.error("Error verifying telegram data", error=str(e))
        return None

def verify_token(token: str) -> Optional[int]:
    """
    Verify the signed token generated by the bot.
    Format: {user_id}:{timestamp}:{signature}
    """
    if not token:
        return None
        
    try:
        parts = token.split(':')
        if len(parts) != 3:
            return None
            
        user_id_str, timestamp_str, signature = parts
        
        # Check expiration
        if int(time.time()) - int(timestamp_str) > int(getattr(settings, "TOKEN_TTL_SECONDS", 3600)):
            logger.warning("Token expired", user_id=user_id_str)
            return None
            
        # Reconstruct data to sign
        data = f"{user_id_str}:{timestamp_str}"
        
        # Calculate expected signature
        secret = settings.BOT_TOKEN.encode()
        expected_signature = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
        
        if hmac.compare_digest(expected_signature, signature):
            return int(user_id_str)
            
        logger.warning("Token signature mismatch", user_id=user_id_str)
        return None
    except Exception as e:
        logger.error("Error verifying token", error=str(e))
        return None

def get_current_user(
    request: Request, 
    x_telegram_init_data: str = Header(None),
    x_auth_token: str = Header(None),
    authorization: str = Header(None),
):
    user_id = None

    # 0. Docs-compatible: Authorization: tma <initData>
    if authorization and authorization.lower().startswith('tma '):
        tma_data = authorization.split(' ', 1)[1].strip()
        user_id = verify_telegram_data(tma_data, max_age_seconds=int(getattr(settings, "INITDATA_TTL_SECONDS", 3600)))
        if user_id:
            return user_id
    
    # 1. Try Token Auth (Priority for this fallback)
    if x_auth_token:
        user_id = verify_token(x_auth_token)
        if user_id:
            return user_id
            
    # 2. Try InitData Auth
    if x_telegram_init_data:
        user_id = verify_telegram_data(x_telegram_init_data, max_age_seconds=int(getattr(settings, "INITDATA_TTL_SECONDS", 3600)))
        if user_id:
            return user_id

    # Reference for debugging
    headers = dict(request.headers)
    logger.warning("Auth failed: Missing or invalid credentials", headers=headers)
    raise HTTPException(status_code=401, detail="Unauthorized")

@app.get(
    "/api/quizzes",
    response_model=List[QuizListItem],
    tags=["quizzes"],
    summary="List all quizzes",
    description="Returns a list of all quizzes owned by the authenticated user.",
    responses={
        200: {"description": "List of quizzes"},
        401: {"description": "Authentication required"},
    },
)
async def list_quizzes(user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get all quizzes for the current user."""
    service = QuizService(db) # redis not needed for listing
    quizzes = await service.get_user_quizzes(user_id)
    return [{
        "id": q.id,
        "title": q.title,
        "questions_count": len(q.questions_json),
        "created_at": q.created_at
    } for q in quizzes]


@app.get(
    "/api/quizzes/{quiz_id}",
    response_model=QuizDetail,
    tags=["quizzes"],
    summary="Get quiz details",
    description="Returns detailed information about a specific quiz, including all questions.",
    responses={
        200: {"description": "Quiz details with questions"},
        401: {"description": "Authentication required"},
        404: {"description": "Quiz not found"},
    },
)
async def get_quiz(quiz_id: int, user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get a specific quiz by ID."""
    service = QuizService(db)
    quiz = await service.get_quiz_by_id_and_user(quiz_id, user_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return {
        "id": quiz.id,
        "title": quiz.title,
        "questions": quiz.questions_json
    }


@app.put(
    "/api/quizzes/{quiz_id}",
    response_model=SuccessResponse,
    tags=["quizzes"],
    summary="Update quiz",
    description="Updates the title and questions of an existing quiz.",
    responses={
        200: {"description": "Quiz updated successfully"},
        401: {"description": "Authentication required"},
        404: {"description": "Quiz not found or not owned by user"},
    },
)
async def update_quiz(
    quiz_id: int, 
    update: QuizUpdate, 
    user_id: int = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis)
):
    """Update an existing quiz."""
    service = QuizService(db, redis=redis)
    
    # Convert Question objects back to raw dicts for storage
    questions_list = [q.model_dump() for q in update.questions]
    
    success = await service.update_quiz(quiz_id, user_id, update.title, questions_list)
    if not success:
        raise HTTPException(status_code=404, detail="Quiz not found or unauthorized")
        
    return {"status": "success"}
class QuizSplitRequest(BaseModel):
    """Request body for splitting a quiz."""
    parts: Optional[int] = Field(None, description="Number of parts to split into", ge=1)
    size: Optional[int] = Field(None, description="Number of questions per part", ge=1)


from db.session import get_db, get_redis


@app.post(
    "/api/quizzes/{quiz_id}/split",
    response_model=List[QuizListItem],
    tags=["quizzes"],
    summary="Split quiz",
    description="Splits a quiz into multiple smaller quizzes by parts or questions per part. Max 50 parts allowed. Rate limited to 3 actions per minute.",
    responses={
        200: {"description": "List of new quiz parts"},
        401: {"description": "Authentication required"},
        400: {"description": "Invalid parameters or quiz not found"},
        429: {"description": "Too many requests. Please wait."},
    },
)
async def split_quiz(
    quiz_id: int, 
    split_req: QuizSplitRequest, 
    user_id: int = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis)
):
    """Split an existing quiz into multiple parts with rate limiting."""
    # 1. Rate Limiting: 3 splits per 60 seconds per user
    rate_key = f"rl:split:{user_id}"
    current_count = await redis.get(rate_key)
    if current_count and int(current_count) >= 3:
        raise HTTPException(status_code=429, detail="Too many split actions. Please wait a minute.")
    
    # 2. Hard Limits: Max 50 parts
    if split_req.parts and split_req.parts > 50:
        raise HTTPException(status_code=400, detail="Cannot split into more than 50 parts.")

    service = QuizService(db, redis=redis)
    
    new_quizzes = await service.split_quiz(quiz_id, user_id, parts=split_req.parts, size=split_req.size)
    if not new_quizzes:
        raise HTTPException(status_code=400, detail="Could not split quiz. Limit reached or invalid parameters.")
        
    # Increment rate limit counter
    await redis.incr(rate_key)
    if not current_count:
        await redis.expire(rate_key, 60)

    return [{
        "id": q.id,
        "title": q.title,
        "questions_count": len(q.questions_json),
        "created_at": q.created_at
    } for q in new_quizzes]


@app.get(
    "/api/bot-info",
    response_model=BotInfo,
    tags=["info"],
    summary="Get bot information",
    description="Returns public information about the bot including username, link, and statistics.",
)
async def get_bot_info(db: AsyncSession = Depends(get_db)):
    """Return bot information for redirect links"""
    bot_username = (settings.BOT_USERNAME or "quizbot_example_bot").strip()
    if bot_username.startswith("@"): 
        bot_username = bot_username[1:]
    logger.info(f"Bot username from settings: {bot_username}")

    users_count = 0
    quizzes_count = 0
    questions_count = 0
    try:
        users_count = int((await db.execute(select(func.count(User.telegram_id)))).scalar() or 0)
        quizzes_count = int((await db.execute(select(func.count(Quiz.id)))).scalar() or 0)

        result = await db.execute(select(Quiz.questions_json))
        questions_count = sum(len(q or []) for q in result.scalars().all())
    except Exception as e:
        logger.warning("Failed to compute public stats", error=str(e))

    return {
        "bot_username": bot_username,
        "bot_link": f"https://t.me/{bot_username}"
        ,
        "stats": {
            "users": users_count,
            "quizzes": quizzes_count,
            "questions": questions_count,
        },
    }

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

# Serve the static files from /webapp folder
# In production, Nginx should serve this, but for simplicity we mount it here
if os.path.exists("webapp"):
    app.mount("/", StaticFiles(directory="webapp", html=True), name="webapp")
else:
    @app.get("/")
    def read_root():
        return {"message": "API is running. Please create the webapp folder."}
