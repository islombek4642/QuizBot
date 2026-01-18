import hmac
import hashlib
import json
import os
from typing import List, Optional
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.session import get_db
from services.quiz_service import QuizService
from core.logger import logger

app = FastAPI(title="QuizBot Editor API")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Question(BaseModel):
    question: str
    options: List[str]
    correct_option_id: int

class QuizUpdate(BaseModel):
    title: str
    questions: List[Question]

def verify_telegram_data(init_data: str) -> Optional[int]:
    """
    Verify Telegram WebApp initData and return the user ID.
    See: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        return None
        
    try:
        vals = dict(parse_qsl(init_data))
        hash_val = vals.pop('hash')
        
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

async def get_current_user(x_telegram_init_data: str = Header(None)):
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Missing Telegram initData")
    
    user_id = verify_telegram_data(x_telegram_init_data)
    if not user_id:
        raise HTTPException(status_code=403, detail="Invalid Telegram data")
    
    return user_id

@app.get("/api/quizzes")
async def list_quizzes(user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    service = QuizService(db)
    quizzes = await service.get_user_quizzes(user_id)
    return [{
        "id": q.id,
        "title": q.title,
        "questions_count": len(q.questions_json),
        "created_at": q.created_at
    } for q in quizzes]

@app.get("/api/quizzes/{quiz_id}")
async def get_quiz(quiz_id: int, user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    service = QuizService(db)
    quiz = await service.get_quiz_by_id_and_user(quiz_id, user_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return {
        "id": quiz.id,
        "title": quiz.title,
        "questions": quiz.questions_json
    }

@app.put("/api/quizzes/{quiz_id}")
async def update_quiz(
    quiz_id: int, 
    update: QuizUpdate, 
    user_id: int = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    service = QuizService(db)
    
    # Convert Question objects back to raw dicts for storage
    questions_list = [q.dict() for q in update.questions]
    
    success = await service.update_quiz(quiz_id, user_id, update.title, questions_list)
    if not success:
        raise HTTPException(status_code=404, detail="Quiz not found or unauthorized")
        
    return {"status": "success"}

# Serve the static files from /webapp folder
# In production, Nginx should serve this, but for simplicity we mount it here
if os.path.exists("webapp"):
    app.mount("/", StaticFiles(directory="webapp", html=True), name="webapp")
else:
    @app.get("/")
    def read_root():
        return {"message": "API is running. Please create the webapp folder."}
