import os
import uuid
import random
import time
import asyncio
import json
from typing import Dict, Any
from sqlalchemy import select
from models.session import QuizSession

from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from utils.parser import parse_docx_to_json, ParserError
from constants.messages import Messages
from handlers.common import (
    get_main_keyboard, 
    get_contact_keyboard, 
    QuizStates, 
    get_shuffle_keyboard, 
    get_stop_keyboard,
    get_quizzes_keyboard,
    get_start_quiz_keyboard,
    get_inline_shuffle_keyboard,
    get_cancel_keyboard
)
from services.user_service import UserService
from services.quiz_service import QuizService
from services.session_service import SessionService
from core.config import settings
from core.logger import logger

router = Router()
# Only handle private chats - no keyboard buttons in groups
router.message.filter(F.chat.type == "private")


from aiogram.filters import BaseFilter

class IsPrivatePoll(BaseFilter):
    async def __call__(self, event: types.TelegramObject, redis) -> bool:
        """Filter to check if the poll belongs to a private quiz"""
        if not redis:
            return False
            
        poll_id = None
        if isinstance(event, types.PollAnswer):
            poll_id = event.poll_id
        elif isinstance(event, types.Poll):
            poll_id = event.id
            
        if poll_id is None:
            return False
            
        key = f"quizbot:poll:{poll_id}"
        mapping = await redis.get(key)
        
        # Log to track filter matching
        if mapping:
            logger.info("IsPrivatePoll filter MATCHED", poll_id=poll_id, key=key)
            return True
        else:
            # We don't want to spam for group polls, but it's okay for now
            # logger.debug("IsPrivatePoll filter MISSED", poll_id=poll_id, key=key)
            return False


@router.message(F.text.in_([Messages.get("CANCEL_BTN", "UZ"), Messages.get("CANCEL_BTN", "EN"), Messages.get("BACK_BTN", "UZ"), Messages.get("BACK_BTN", "EN")]))
async def cmd_cancel(message: types.Message, state: FSMContext, user_service: UserService):
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    await state.clear()
    await message.answer(
        Messages.get("SELECT_BUTTON", lang),
        reply_markup=get_main_keyboard(lang, telegram_id)
    )

@router.message(F.text.in_([Messages.get("CREATE_QUIZ_BTN", "UZ"), Messages.get("CREATE_QUIZ_BTN", "EN")]))
async def cmd_create_quiz(message: types.Message, state: FSMContext, user_service: UserService):
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    user = await user_service.get_or_create_user(telegram_id)
    if not user or not user.phone_number:
        await message.answer(
            Messages.get("SHARE_CONTACT_PROMPT", lang),
            reply_markup=get_contact_keyboard(lang)
        )
        return

    await state.set_state(QuizStates.WAITING_FOR_DOCX)
    combined_msg = f"{Messages.get('WELCOME', lang)}\n\n{Messages.get('FORMAT_INFO', lang)}"
    await message.answer(combined_msg, reply_markup=get_cancel_keyboard(lang))

@router.message(F.text.in_([Messages.get("MY_QUIZZES_BTN", "UZ"), Messages.get("MY_QUIZZES_BTN", "EN")]))
async def cmd_my_quizzes(message: types.Message, user_service: UserService, quiz_service: QuizService):
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    user = await user_service.get_or_create_user(telegram_id)
    if not user or not user.phone_number:
        await message.answer(
            Messages.get("SHARE_CONTACT_PROMPT", lang),
            reply_markup=get_contact_keyboard(lang)
        )
        return

    quizzes = await quiz_service.get_user_quizzes(telegram_id)
    if not quizzes:
        await message.answer(Messages.get("NO_QUIZZES", lang))
        return

    # Helper function to format list for keyboard
    quiz_list = [{"id": q.id, "title": q.title} for q in quizzes]
    await message.answer(
        Messages.get("MY_QUIZZES_BTN", lang),
        reply_markup=get_quizzes_keyboard(quiz_list, lang)
    )

@router.message(QuizStates.WAITING_FOR_DOCX, F.document)
async def handle_quiz_docx(message: types.Message, bot: Bot, state: FSMContext, user_service: UserService):
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    document = message.document
    if not document or not document.file_name or not document.file_name.endswith('.docx'):
        await message.answer(Messages.get("ONLY_DOCX", lang))
        return

    temp_dir = os.path.join(os.getcwd(), "temp")
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    file_info = await bot.get_file(document.file_id)
    local_path = os.path.join(temp_dir, f"{uuid.uuid4()}.docx")
    
    await bot.download_file(file_info.file_path, local_path)
    
    # Verify file exists and is not empty
    if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
        logger.error("File download failed or empty", path=local_path)
        await message.answer(Messages.get("FILE_DOWNLOAD_ERROR", lang))
        return

    try:
        # Offload parsing to thread to avoid blocking loop
        # Now returns tuple (questions, errors)
        questions, errors = await asyncio.to_thread(parse_docx_to_json, local_path, lang)
        
        if not questions:
             # All failed
             error_list = "\n".join(errors[:15])
             if len(errors) > 15:
                 error_list += f"\n... va yana {len(errors)-15} ta xatolik."
                 
             await message.answer(Messages.get("QUIZ_ALL_FAILED", lang).format(errors=error_list))
             return

        await state.update_data(questions=questions)
        await state.set_state(QuizStates.WAITING_FOR_TITLE)
        
        if errors:
             # Partial success
             error_list = "\n".join(errors[:10])
             if len(errors) > 10:
                 error_list += f"\n... (+{len(errors)-10})"
            
             await message.answer(
                Messages.get("QUIZ_PARTIAL_SUCCESS", lang).format(
                    count=len(questions),
                    errors_count=len(errors),
                    errors=error_list
                )
             )
        else:
             # Full success
             await message.answer(
                Messages.get("QUIZ_UPLOADED", lang).format(count=len(questions))
             )

    except ParserError as e:
        await message.answer(str(e))
    except Exception as e:
        logger.error("Error during docx parsing", error=str(e), user_id=telegram_id)
        await message.answer(Messages.get("ERROR", lang).format(error="Tizim xatoligi"))
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

@router.message(QuizStates.WAITING_FOR_TITLE, F.text)
async def handle_quiz_title(message: types.Message, state: FSMContext, user_service: UserService, quiz_service: QuizService):
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    title = message.text.strip()
    
    # Check if title already exists for this user
    if await quiz_service.is_title_taken(telegram_id, title):
        await message.answer(Messages.get("QUIZ_TITLE_EXISTS", lang))
        return

    await state.update_data(title=title)
    
    await state.set_state(QuizStates.WAITING_FOR_SHUFFLE)
    await message.answer(
        Messages.get("ASK_SHUFFLE", lang),
        reply_markup=get_shuffle_keyboard(lang)
    )

@router.message(QuizStates.WAITING_FOR_SHUFFLE, F.text.in_([Messages.get("SHUFFLE_YES", "UZ"), Messages.get("SHUFFLE_YES", "EN"), Messages.get("SHUFFLE_NO", "UZ"), Messages.get("SHUFFLE_NO", "EN")]))
async def handle_quiz_shuffle(message: types.Message, state: FSMContext, user_service: UserService, quiz_service: QuizService):
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    shuffle = message.text in [Messages.get("SHUFFLE_YES", "UZ"), Messages.get("SHUFFLE_YES", "EN")]
    
    data = await state.get_data()
    title = data.get("title")
    questions = data.get("questions")
    
    quiz = await quiz_service.save_quiz(telegram_id, title, questions, shuffle)
    
    shuffle_status = Messages.get("SHUFFLE_TRUE", lang) if shuffle else Messages.get("SHUFFLE_FALSE", lang)
    summary_text = Messages.get("QUIZ_READY_DETAILS", lang).format(
        title=title, count=len(questions), shuffle=shuffle_status
    )
    
    # Store quiz_id and set status
    await state.update_data(current_quiz_id=quiz.id)
    await state.set_state(QuizStates.QUIZ_READY)
    
    # Combined summary and action prompt
    combined_msg = f"{summary_text}\n\n{Messages.get('SELECT_BUTTON', lang)}"
    
    # Send all info in one message with the START keyboard
    await message.answer(
        combined_msg,
        reply_markup=get_start_quiz_keyboard(lang),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("start_quiz_"))
async def start_quiz_callback_handler(callback: types.CallbackQuery, state: FSMContext, 
                                     quiz_service: QuizService, session_service: SessionService, user_service: UserService):
    quiz_id = int(callback.data.split("_")[2])
    await process_start_quiz(callback.message, quiz_id, quiz_service, session_service, user_service)
    await callback.answer()

@router.message(QuizStates.QUIZ_READY, F.text.in_([Messages.get("START_QUIZ_BTN", "UZ"), Messages.get("START_QUIZ_BTN", "EN")]))
async def start_quiz_message_handler(message: types.Message, state: FSMContext, 
                                    quiz_service: QuizService, session_service: SessionService, user_service: UserService):
    data = await state.get_data()
    quiz_id = data.get("current_quiz_id")
    if not quiz_id:
        # We need language here, but state context implies user interact. 
        # Actually user_service is available.
        telegram_id = message.from_user.id
        lang = await user_service.get_language(telegram_id)
        await message.answer(Messages.get("ERROR_QUIZ_NOT_FOUND", lang))
        await state.clear()
        return
    
    await process_start_quiz(message, quiz_id, quiz_service, session_service, user_service)
    await state.clear()

async def process_start_quiz(message: types.Message, quiz_id: int, quiz_service: QuizService, 
                            session_service: SessionService, user_service: UserService):
    telegram_id = message.chat.id
    lang = await user_service.get_language(telegram_id)

    quiz = await quiz_service.get_quiz(quiz_id)
    if not quiz:
        await message.answer(Messages.get("ERROR_TEST_NOT_FOUND", lang))
        return
    questions = list(quiz.questions_json) # Copy to avoid mutating original if cached
    
    # Clear any lingering stop signals from previous abandoned sessions
    await session_service.clear_stop_signal(telegram_id)
    if quiz.shuffle_options:
        random.shuffle(questions)
        for q in questions:
            options = list(q['options'])
            correct_answer = options[q['correct_option_id']]
            random.shuffle(options)
            q['options'] = options
            q['correct_option_id'] = options.index(correct_answer)
    
    session = await session_service.create_session(
        user_id=telegram_id, 
        quiz_id=quiz_id, 
        total_questions=len(questions),
        session_data={'questions': questions}
    )
    
    await message.answer(
        Messages.get("QUIZ_START_MSG", lang).format(title=quiz.title), 
        reply_markup=get_stop_keyboard(lang),
        parse_mode="HTML"
    )
    
    await send_next_question(bot, telegram_id, session, session_service, lang)

async def send_next_question(bot: Bot, chat_id: int, session: Any, session_service: SessionService, lang: str):
    questions = session.session_data['questions']
    idx = session.current_index
    
    if idx >= session.total_questions:
        # This shouldn't happen here if handled in advance_session
        return

    q = questions[idx]
    question_text = f"{idx+1}/{session.total_questions}. {q['question']}"
    if len(question_text) > 300:
        question_text = question_text[:297] + "..."

    poll_msg = await bot.send_poll(
        chat_id=chat_id,
        question=question_text,
        options=q['options'],
        is_anonymous=False,
        type='quiz',
        correct_option_id=q['correct_option_id'],
        open_period=settings.POLL_DURATION_SECONDS
    )
    
    # Store mapping as JSON to include index for safe advancement
    mapping = json.dumps({"session_id": session.id, "index": idx})
    key = f"quizbot:poll:{poll_msg.poll.id}"
    await session_service.redis.set(key, mapping, ex=settings.POLL_MAPPING_TTL_SECONDS)
    await session_service.save_last_poll_id(session.id, poll_msg.message_id)
    logger.info("Private poll sent", user_id=session.user_id, poll_id=poll_msg.poll.id, index=idx, redis_key=key)

@router.poll_answer(IsPrivatePoll())
async def handle_poll_answer(poll_answer: types.PollAnswer, bot: Bot, session_service: SessionService, user_service: UserService, redis):
    try:
        # Get mapping
        logger.info("PRIVATE POLL ANSWER RECEIVED", poll_id=poll_answer.poll_id, user_id=poll_answer.user.id if poll_answer.user else "N/A")
        mapping_raw = await redis.get(f"quizbot:poll:{poll_answer.poll_id}")
        if not mapping_raw:
            logger.warning("Handler Error: Mapping not found in Redis", poll_id=poll_answer.poll_id)
            return
            
        try:
            mapping = json.loads(mapping_raw)
            if isinstance(mapping, dict):
                session_id = mapping["session_id"]
                mapped_index = mapping["index"]
            else:
                session_id = int(mapping)
                mapped_index = None
        except Exception as e:
            logger.error(f"Error parsing poll mapping: {e}", mapping_raw=mapping_raw)
            session_id = int(mapping_raw) if mapping_raw.isdigit() else None
            mapped_index = None

        if session_id is None:
            logger.error("Session ID is None in handle_poll_answer")
            return

        # Get session
        result = await session_service.db.execute(select(QuizSession).filter(QuizSession.id == session_id))
        session = result.scalar_one_or_none()
        
        if not session:
            logger.warning("Private poll answer ignored: session NOT FOUND in DB", session_id=session_id)
            return
            
        if not session.is_active:
            logger.info("Private poll answer ignored: session INACTIVE", session_id=session_id)
            return

        # Check if this answer matches the current session index
        if mapped_index is not None and session.current_index != mapped_index:
            logger.warning("Private poll answer ignored: INDEX MISMATCH", 
                           user_id=session.user_id, current=session.current_index, mapped=mapped_index)
            return

        logger.info("Private poll answer logic proceeding", user_id=session.user_id, session_id=session.id, index=session.current_index)

        # Get user language
        lang = await user_service.get_language(session.user_id)
        
        # Calculate correctness
        questions = session.session_data['questions']
        q = questions[session.current_index]
        is_correct = poll_answer.option_ids[0] == q['correct_option_id']
        
        updated_session = await session_service.advance_session(session.id, is_correct)
        if not updated_session:
            logger.warning("Failed to advance private session (advance_session returned None)", session_id=session.id)
            return

        logger.info("Private session advanced successfully", session_id=session.id, next_index=updated_session.current_index)

        # Check if finished
        if not updated_session.is_active:
            logger.info("Quiz finished for user", user_id=session.user_id)
            await bot.send_message(
                session.user_id, 
                Messages.get("QUIZ_FINISHED", lang), 
                reply_markup=get_main_keyboard(lang, session.user_id)
            )
            await show_stats(bot, updated_session, lang)
        else:
            await asyncio.sleep(3)
            # Re-verify session is still active and NOT hard-stopped after the delay
            if await session_service.is_stopped(session.user_id):
                logger.info("Private session hard-stopped during 3s delay", user_id=session.user_id)
                return

            current_session = await session_service.get_active_session(session.user_id)
            if not current_session or current_session.id != updated_session.id:
                logger.info("Session changed or terminated during 3s delay", user_id=session.user_id)
                return

            logger.info("Sending next question for user", user_id=session.user_id, index=current_session.current_index)
            await send_next_question(bot, session.user_id, current_session, session_service, lang)
    except Exception as e:
        logger.exception(f"Exception in handle_poll_answer: {e}")

@router.poll(IsPrivatePoll())
async def handle_private_poll_update(poll: types.Poll, bot: Bot, session_service: SessionService, user_service: UserService, redis):
    try:
        """Handle poll updates for private quizzes, advancing when a poll closes (timeout)"""
        if not poll.is_closed:
            return
            
        key = f"quizbot:poll:{poll.id}"
        mapping_raw = await redis.get(key)
        if not mapping_raw:
            logger.warning("Private poll update ignored: mapping disappeared", poll_id=poll.id, key=key)
            return
            
        try:
            mapping = json.loads(mapping_raw)
            if isinstance(mapping, dict):
                session_id = mapping["session_id"]
                mapped_index = mapping["index"]
            else:
                session_id = int(mapping)
                mapped_index = None
        except Exception as e:
            logger.error(f"Error parsing poll mapping in update: {e}", mapping_raw=mapping_raw)
            session_id = int(mapping_raw) if mapping_raw.isdigit() else None
            mapped_index = None

        if session_id is None:
            return

        # Get session via direct DB query to ensure we have the latest state
        result = await session_service.db.execute(select(QuizSession).filter(QuizSession.id == session_id))
        session = result.scalar_one_or_none()
        
        if not session or not session.is_active:
            return

        # If the user already answered, current_index will have moved past mapped_index
        if mapped_index is not None and session.current_index != mapped_index:
            logger.info("Private poll close ignored: already advanced", user_id=session.user_id, poll_id=poll.id)
            return

        # If we are here, it means the poll closed without an answer being processed
        logger.info("Private poll closed without answer (timeout)", user_id=session.user_id, poll_id=poll.id)

        # Advance without adding to correct count
        updated_session = await session_service.advance_session(session.id, is_correct=False)
        if not updated_session:
            return
            
        lang = await user_service.get_language(session.user_id)
        
        # Notify about timeout/no answer
        try:
            await bot.send_message(session.user_id, Messages.get("NO_ONE_ANSWERED", lang))
        except Exception as e:
            logger.warning(f"Failed to send timeout message: {e}")
            
        if not updated_session.is_active:
            await bot.send_message(
                session.user_id, 
                Messages.get("QUIZ_FINISHED", lang), 
                reply_markup=get_main_keyboard(lang, session.user_id)
            )
            await show_stats(bot, updated_session, lang)
        else:
            await asyncio.sleep(3)
            # Re-verify session is still active and NOT hard-stopped after the delay
            if await session_service.is_stopped(session.user_id):
                return

            current_session = await session_service.get_active_session(session.user_id)
            if not current_session or current_session.id != updated_session.id:
                return

            logger.info("Advancing private quiz after timeout", user_id=session.user_id, next_index=current_session.current_index)
            await send_next_question(bot, session.user_id, current_session, session_service, lang)
    except Exception as e:
        logger.exception(f"Exception in handle_private_poll_update: {e}")

async def show_stats(bot: Bot, session: Any, lang: str):
    total = session.total_questions
    correct = session.correct_count
    answered = session.answered_count
    
    # Use updated_at for inactive sessions if possible, or current time
    # updated_at is a datetime object, start_time is float
    import datetime
    if not session.is_active:
        # Assuming updated_at is when it was stopped/finished
        duration = (session.updated_at.replace(tzinfo=datetime.timezone.utc).timestamp() - session.start_time)
    else:
        duration = time.time() - session.start_time
    
    # If duration is negative or zero (e.g. very fast finish), set to 1
    duration = max(1.0, duration)
    avg_time = duration / answered if answered > 0 else 0
    percent = (correct / total * 100) if total > 0 else 0
    
    await bot.send_message(
        session.user_id,
        Messages.get("QUIZ_STATS", lang).format(
            total=total,
            correct=correct,
            wrong=answered - correct,
            avg_time=round(avg_time, 1),
            percent=round(percent, 1)
        ),
        parse_mode="HTML"
    )

@router.message(F.text.in_([Messages.get("STOP_QUIZ_BTN", "UZ"), Messages.get("STOP_QUIZ_BTN", "EN")]))
async def cmd_stop_quiz(message: types.Message, session_service: SessionService, user_service: UserService):
    telegram_id = message.from_user.id
    session = await session_service.get_active_session(telegram_id)
    lang = await user_service.get_language(telegram_id)
    
    if session:
        # Stop active poll if exists
        last_poll_msg_id = session.session_data.get('last_poll_message_id')
        if last_poll_msg_id:
            try:
                await message.bot.stop_poll(chat_id=telegram_id, message_id=last_poll_msg_id)
            except Exception as e:
                logger.warning(f"Failed to stop poll: {e}")

        # Set hard-stop signal in Redis
        await session_service.set_stop_signal(telegram_id)
        await session_service.stop_session(telegram_id)
        await message.answer(
            Messages.get("QUIZ_STOPPED", lang), 
            reply_markup=get_main_keyboard(lang, telegram_id)
        )
        # Refresh session object for stats
        from sqlalchemy import select
        result = await session_service.db.execute(select(session.__class__).filter_by(id=session.id))
        session = result.scalar_one()
        await show_stats(message.bot, session, lang)
    else:
        await message.answer(Messages.get("SELECT_BUTTON", lang), reply_markup=get_main_keyboard(lang, telegram_id))

@router.callback_query(F.data.startswith("delete_quiz_"))
async def delete_quiz_handler(callback: types.CallbackQuery, quiz_service: QuizService, user_service: UserService):
    quiz_id = int(callback.data.split("_")[2])
    telegram_id = callback.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    success = await quiz_service.delete_quiz(quiz_id, telegram_id)
    if success:
        await callback.answer(Messages.get("QUIZ_DELETED", lang))
        # Remove the info message (inline buttons message)
        await callback.message.delete()
        # Clean success message with main keyboard
        await callback.message.answer(
            Messages.get("QUIZ_DELETED", lang),
            reply_markup=get_main_keyboard(lang, telegram_id)
        )
    else:
        await callback.answer(Messages.get("ERROR_GENERIC", lang), show_alert=True)

async def show_quiz_info(bot: Bot, chat_id: int, quiz_id: int, lang: str, quiz_service: QuizService):
    """Show detailed info and buttons for a specific quiz"""
    quiz = await quiz_service.get_quiz(quiz_id)
    if not quiz:
        return
        
    builder = InlineKeyboardBuilder()
    builder.button(text=Messages.get("START_QUIZ_BTN", lang), callback_data=f"start_quiz_{quiz.id}")
    builder.button(text=Messages.get("START_IN_GROUP_BTN", lang), callback_data=f"start_group_quiz_{quiz.id}")
    builder.button(text="📤 Ulashish / Share", switch_inline_query=f"quiz_{quiz.id}")
    builder.button(text=Messages.get("QUIZ_DELETE_BTN", lang), callback_data=f"delete_quiz_{quiz.id}")
    builder.adjust(1)
    
    shuffle_status = Messages.get("SHUFFLE_TRUE", lang) if quiz.shuffle_options else Messages.get("SHUFFLE_FALSE", lang)
    
    info_text = Messages.get("QUIZ_INFO_MSG", lang).format(
        title=quiz.title, 
        count=len(quiz.questions_json),
        shuffle=shuffle_status
    )
    
    await bot.send_message(
        chat_id,
        f"{info_text}\n\n{Messages.get('SELECT_BUTTON', lang)}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.message(F.text)
async def handle_quiz_selection(message: types.Message, quiz_service: QuizService, user_service: UserService):
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    quizzes = await quiz_service.get_user_quizzes(telegram_id)
    selected_quiz = next((q for q in quizzes if q.title == message.text), None)
    
    if selected_quiz:
        await show_quiz_info(message.bot, message.chat.id, selected_quiz.id, lang, quiz_service)
    else:
        pass


@router.inline_query()
async def handle_inline_share(inline_query: types.InlineQuery, quiz_service: QuizService, user_service: UserService):
    """Handle quiz sharing via inline query"""
    query = inline_query.query
    telegram_id = inline_query.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    # If query matches quiz_ID, show that specific quiz
    if query.startswith("quiz_"):
        try:
            quiz_id = int(query.split("_")[1])
            quiz = await quiz_service.get_quiz(quiz_id)
            if quiz:
                bot_info = await inline_query.bot.get_me()
                
                builder = InlineKeyboardBuilder()
                builder.button(text=Messages.get("INLINE_START_BTN", lang), url=f"https://t.me/{bot_info.username}?start=quiz_{quiz_id}")
                builder.button(text=Messages.get("INLINE_START_GROUP_BTN", lang), url=f"https://t.me/{bot_info.username}?startgroup=quiz_{quiz_id}")
                builder.button(text=Messages.get("INLINE_SHARE_BTN", lang), switch_inline_query=f"quiz_{quiz_id}")
                builder.adjust(1)

                msg_text = Messages.get("INLINE_SHARE_MSG", lang).format(title=quiz.title, count=len(quiz.questions_json))

                results = [
                    types.InlineQueryResultArticle(
                        id=f"share_{quiz_id}",
                        title=quiz.title,
                        description=f"Savollar soni: {len(quiz.questions_json)}",
                        input_message_content=types.InputTextMessageContent(
                            message_text=msg_text,
                            parse_mode="HTML"
                        ),
                        reply_markup=builder.as_markup()
                    )
                ]
                await inline_query.answer(results, cache_time=300, is_personal=True)
                return
        except:
            pass

    # Otherwise show user's recent quizzes
    quizzes = await quiz_service.get_user_quizzes(telegram_id)
    results = []
    bot_info = await inline_query.bot.get_me()
    
    for q in quizzes[:10]:
        builder = InlineKeyboardBuilder()
        builder.button(text=Messages.get("INLINE_START_BTN", lang), url=f"https://t.me/{bot_info.username}?start=quiz_{q.id}")
        builder.button(text=Messages.get("INLINE_START_GROUP_BTN", lang), url=f"https://t.me/{bot_info.username}?startgroup=quiz_{q.id}")
        builder.button(text=Messages.get("INLINE_SHARE_BTN", lang), switch_inline_query=f"quiz_{q.id}")
        builder.adjust(1)
        
        msg_text = Messages.get("INLINE_SHARE_MSG", lang).format(title=q.title, count=len(q.questions_json))

        results.append(
            types.InlineQueryResultArticle(
                id=f"share_{q.id}",
                title=q.title,
                description=f"Savollar soni: {len(q.questions_json)}",
                input_message_content=types.InputTextMessageContent(
                    message_text=msg_text,
                    parse_mode="HTML"
                ),
                reply_markup=builder.as_markup()
            )
        )
    
    await inline_query.answer(results, cache_time=60, is_personal=True)
