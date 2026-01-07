"""
Group Quiz Handler Module

Handles:
- Bot membership in groups (my_chat_member updates)
- Group quiz initiation and flow
- Individual user tracking in group quizzes
"""

import asyncio
import time
from typing import Optional, Dict, Any

from aiogram import Router, types, F, Bot
from aiogram.types import ChatMemberUpdated
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER, Command

from constants.messages import Messages
from handlers.common import get_main_keyboard
from services.user_service import UserService
from services.quiz_service import QuizService
from services.session_service import SessionService
from core.config import settings
from core.logger import logger

router = Router()

# Redis keys for group tracking
GROUP_MEMBERS_KEY = "bot_groups"  # Set of group_ids where bot is member
GROUP_QUIZ_KEY = "group_quiz:{chat_id}"  # Active quiz in a group
GROUP_USER_ANSWER_KEY = "group_answer:{chat_id}:{quiz_id}:{user_id}"  # Individual user answers


async def is_group_poll(poll_answer: types.PollAnswer, redis) -> bool:
    """Filter to check if the poll belongs to a group quiz"""
    if not redis:
        return False
    return await redis.exists(f"group_poll:{poll_answer.poll_id}")


async def get_bot_groups(redis) -> list:
    """Get list of groups where bot is a member"""
    groups = await redis.smembers(GROUP_MEMBERS_KEY)
    return list(groups) if groups else []


async def add_bot_group(redis, chat_id: int, chat_title: str):
    """Add a group to bot's group list"""
    await redis.sadd(GROUP_MEMBERS_KEY, str(chat_id))
    # Store group title for display
    await redis.hset(f"group_info:{chat_id}", "title", chat_title)


async def remove_bot_group(redis, chat_id: int):
    """Remove a group from bot's group list"""
    await redis.srem(GROUP_MEMBERS_KEY, str(chat_id))
    await redis.delete(f"group_info:{chat_id}")


async def get_group_title(redis, chat_id: int) -> str:
    """Get group title by chat_id"""
    title = await redis.hget(f"group_info:{chat_id}", "title")
    return title or f"Group {chat_id}"


@router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_bot_added_to_group(event: ChatMemberUpdated, user_service: UserService, redis):
    """Handle bot being added to a group"""
    chat = event.chat
    user = event.from_user
    
    if chat.type not in ("group", "supergroup"):
        return
    
    # Get user language for response
    lang = await user_service.get_language(user.id)
    
    # Store group in Redis
    if redis:
        await add_bot_group(redis, chat.id, chat.title or f"Group {chat.id}")
    
    logger.info("Bot added to group", chat_id=chat.id, chat_title=chat.title, added_by=user.id)
    
    # Send confirmation to the group
    try:
        await event.bot.send_message(
            chat.id,
            Messages.get("BOT_ADDED_TO_GROUP", lang)
        )
    except Exception as e:
        logger.error("Failed to send group welcome message", error=str(e), chat_id=chat.id)


@router.my_chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER))
async def on_bot_removed_from_group(event: ChatMemberUpdated, redis):
    """Handle bot being removed from a group"""
    chat = event.chat
    
    if chat.type not in ("group", "supergroup"):
        return
    
    # Remove group from Redis
    if redis:
        await remove_bot_group(redis, chat.id)
    
    logger.info("Bot removed from group", chat_id=chat.id, chat_title=chat.title)


@router.message(F.text.in_([Messages.get("ADD_TO_GROUP_BTN", "UZ"), Messages.get("ADD_TO_GROUP_BTN", "EN")]))
async def cmd_add_to_group(message: types.Message, user_service: UserService):
    """Handle 'Add to Group' button - show inline button with group add link"""
    # Only work in private chats
    if message.chat.type != "private":
        return
    
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    bot_username = settings.BOT_USERNAME
    if not bot_username:
        # Try to get username from bot info
        try:
            bot_info = await message.bot.get_me()
            bot_username = bot_info.username
        except:
            bot_username = ""
    
    if not bot_username:
        await message.answer(Messages.get("ERROR_GENERIC", lang))
        return
    
    # Use startgroup with admin rights request
    # The admin parameter requests specific permissions
    builder = InlineKeyboardBuilder()
    builder.button(
        text=Messages.get("ADD_TO_GROUP_BTN", lang),
        url=f"https://t.me/{bot_username}?startgroup&admin=post_messages+delete_messages+restrict_members+pin_messages+manage_topics"
    )
    
    await message.answer(
        Messages.get("SELECT_GROUP", lang),
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("start_group_quiz_"))
async def start_group_quiz_callback(callback: types.CallbackQuery, user_service: UserService, 
                                   quiz_service: QuizService, session_service: SessionService, redis):
    """Handle 'Start in Group' button - show group selection"""
    quiz_id = int(callback.data.split("_")[3])
    telegram_id = callback.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    # Get available groups
    if not redis:
        await callback.answer(Messages.get("ERROR_GENERIC", lang), show_alert=True)
        return
    
    groups = await get_bot_groups(redis)
    if not groups:
        await callback.answer(Messages.get("NO_GROUPS", lang), show_alert=True)
        return
    
    # Build group selection keyboard
    builder = InlineKeyboardBuilder()
    for group_id in groups:
        title = await get_group_title(redis, int(group_id))
        builder.button(
            text=title,
            callback_data=f"confirm_group_quiz_{quiz_id}_{group_id}"
        )
    builder.adjust(1)
    
    await callback.message.answer(
        Messages.get("SELECT_GROUP", lang),
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_group_quiz_"))
async def confirm_group_quiz_callback(callback: types.CallbackQuery, user_service: UserService,
                                      quiz_service: QuizService, session_service: SessionService, redis):
    """Confirm and start quiz in selected group"""
    parts = callback.data.split("_")
    quiz_id = int(parts[3])
    chat_id = int(parts[4])
    telegram_id = callback.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    # Check if bot is admin in the group
    try:
        bot_member = await callback.bot.get_chat_member(chat_id, callback.bot.id)
        if bot_member.status not in ("administrator", "creator"):
            await callback.answer(Messages.get("BOT_NEEDS_ADMIN", lang), show_alert=True)
            return
    except Exception as e:
        logger.error("Failed to check bot admin status", error=str(e), chat_id=chat_id)
        await callback.answer(Messages.get("ERROR_GENERIC", lang), show_alert=True)
        return
    
    # Get quiz
    quiz = await quiz_service.get_quiz(quiz_id)
    if not quiz:
        await callback.answer(Messages.get("ERROR_GENERIC", lang), show_alert=True)
        return
    
    # Start group quiz session
    await start_group_quiz(callback.bot, quiz, chat_id, telegram_id, lang, redis, session_service)
    
    # Notify user
    await callback.message.edit_text(Messages.get("GROUP_QUIZ_STARTED", lang))
    await callback.answer()


async def start_group_quiz(bot: Bot, quiz, chat_id: int, owner_id: int, lang: str, 
                           redis, session_service: SessionService):
    """Start a quiz in a group chat"""
    import random
    
    questions = quiz.questions_json.copy()
    if quiz.shuffle_options:
        for q in questions:
            options = q['options']
            correct_answer = options[q['correct_option_id']]
            random.shuffle(options)
            q['correct_option_id'] = options.index(correct_answer)
    
    # Store group quiz state in Redis
    quiz_state = {
        "quiz_id": quiz.id,
        "owner_id": owner_id,
        "chat_id": chat_id,
        "current_index": 0,
        "total_questions": len(questions),
        "questions": questions,
        "participants": {},  # user_id -> {correct: X, answered: Y}
        "start_time": time.time(),
        "is_active": True
    }
    
    await redis.set(
        GROUP_QUIZ_KEY.format(chat_id=chat_id),
        __import__('json').dumps(quiz_state),
        ex=14400  # 4 hours TTL
    )
    
    # Send start message to group
    await bot.send_message(
        chat_id,
        Messages.get("QUIZ_START_MSG", lang).format(title=quiz.title),
        parse_mode="HTML"
    )
    
    # Send first question
    await send_group_question(bot, chat_id, quiz_state, redis, lang)


async def send_group_question(bot: Bot, chat_id: int, quiz_state: dict, redis, lang: str):
    """Send the next question to the group"""
    current_index = quiz_state["current_index"]
    questions = quiz_state["questions"]
    
    if current_index >= len(questions):
        # Quiz finished
        await finish_group_quiz(bot, chat_id, quiz_state, redis, lang)
        return
    
    q = questions[current_index]
    
    poll_message = await bot.send_poll(
        chat_id=chat_id,
        question=q['question'][:300],
        options=q['options'][:10],
        type='quiz',
        correct_option_id=q['correct_option_id'],
        is_anonymous=False,
        open_period=settings.POLL_DURATION_SECONDS
    )
    
    # Store poll mapping
    poll_mapping = {
        "chat_id": chat_id,
        "quiz_id": quiz_state["quiz_id"],
        "question_index": current_index
    }
    await redis.set(
        f"group_poll:{poll_message.poll.id}",
        __import__('json').dumps(poll_mapping),
        ex=settings.POLL_MAPPING_TTL_SECONDS
    )
    
    logger.info("Group poll sent", chat_id=chat_id, poll_id=poll_message.poll.id, question_index=current_index)


async def finish_group_quiz(bot: Bot, chat_id: int, quiz_state: dict, redis, lang: str):
    """Finish group quiz and show results"""
    participants = quiz_state.get("participants", {})
    quiz_title = quiz_state.get("title", "Quiz")
    
    # Use preference if stored
    group_lang = await redis.get(f"group_lang:{chat_id}")
    if group_lang:
        lang = group_lang

    if not participants:
        await bot.send_message(chat_id, Messages.get("QUIZ_FINISHED", lang))
    else:
        # Sort by correct then total
        sorted_p = sorted(participants.items(), key=lambda x: (x[1]['correct'], x[1]['answered']), reverse=True)
        
        leaderboard = f"🏁 <b>{quiz_title} - {Messages.get('QUIZ_FINISHED', lang)}</b>\n\n"
        leaderboard += "🏆 <b>Final Leaderboard:</b>\n"
        
        for i, (uid, stats) in enumerate(sorted_p[:15], 1):
            try:
                member = await bot.get_chat_member(chat_id, int(uid))
                name = member.user.full_name
            except:
                name = f"User {uid}"
            leaderboard += f"{i}. {name}: <b>{stats['correct']}</b>/{stats['answered']} ✅\n"
        
        # Summary footer
        total_correct = sum(p.get("correct", 0) for p in participants.values())
        total_answered = sum(p.get("answered", 0) for p in participants.values())
        avg_score = (total_correct / total_answered * 100) if total_answered > 0 else 0
        
        summary = f"\n👥 Qatnashchilar: {len(participants)}\n📊 O'rtacha natija: {avg_score:.1f}%"
        await bot.send_message(chat_id, leaderboard + summary, parse_mode="HTML")
    
    # Clean up
    await redis.delete(GROUP_QUIZ_KEY.format(chat_id=chat_id))
    
    logger.info("Group quiz finished", chat_id=chat_id, participants=len(participants))



@router.message(Command("stop_quiz"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_stop_group_quiz(message: types.Message, user_service: UserService, redis):
    """Stop active quiz in group (only owner or admin)"""
    chat_id = message.chat.id
    lang = await user_service.get_language(message.from_user.id)
    
    quiz_state_raw = await redis.get(GROUP_QUIZ_KEY.format(chat_id=chat_id))
    if not quiz_state_raw:
        return
        
    quiz_state = __import__('json').loads(quiz_state_raw)
    
    # Check permission
    is_owner = message.from_user.id == quiz_state.get("owner_id")
    member = await message.chat.get_member(message.from_user.id)
    is_admin = member.status in ("administrator", "creator")
    
    if not (is_owner or is_admin):
        # Notify that only admins can stop
        await message.reply(Messages.get("ERROR_GENERIC", lang))
        return
        
    quiz_state["is_active"] = False
    await redis.set(GROUP_QUIZ_KEY.format(chat_id=chat_id), __import__('json').dumps(quiz_state), ex=3600)
    
    # Show statistics before finishing
    await finish_group_quiz(message.bot, chat_id, quiz_state, redis, lang)


@router.message(Command("set_language"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_group_set_language(message: types.Message, user_service: UserService):
    """Set language for the group (Admins only)"""
    member = await message.chat.get_member(message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return
        
    lang = await user_service.get_language(message.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.button(text="O'zbekcha 🇺🇿", callback_data="set_group_lang_UZ")
    builder.button(text="English 🇬🇧", callback_data="set_group_lang_EN")
    builder.adjust(2)
    
    await message.answer(Messages.get("CHOOSE_LANGUAGE", lang), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("set_group_lang_"))
async def cb_set_group_lang(callback: types.CallbackQuery, user_service: UserService, redis):
    """Handle group language selection"""
    member = await callback.message.chat.get_member(callback.from_user.id)
    if member.status not in ("administrator", "creator"):
        await callback.answer(Messages.get("ERROR_GENERIC", "UZ"), show_alert=True)
        return
        
    new_lang = callback.data.split("_")[-1]
    # Store group language in Redis
    await redis.set(f"group_lang:{callback.message.chat.id}", new_lang)
    
    await callback.message.edit_text(Messages.get("LANGUAGE_SET", new_lang))
    await callback.answer()


@router.message(Command("create_quiz"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_group_create_quiz(message: types.Message, user_service: UserService):
    """Redirect to bot to create a quiz"""
    lang = await user_service.get_language(message.from_user.id)
    bot_info = await message.bot.get_me()
    
    builder = InlineKeyboardBuilder()
    builder.button(text=Messages.get("CREATE_QUIZ_BTN", lang), url=f"https://t.me/{bot_info.username}?start=create")
    
    await message.answer(
        "📝 Test yaratish uchun botning o'ziga o'ting / To create a quiz, go to the bot's private chat.",
        reply_markup=builder.as_markup()
    )


@router.message(Command("quiz_stats"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_group_quiz_stats(message: types.Message, user_service: UserService, redis):
    """Show current quiz stats/leaderboard"""
    chat_id = message.chat.id
    lang = await user_service.get_language(message.from_user.id)
    
    # Use preference if stored
    group_lang = await redis.get(f"group_lang:{chat_id}")
    if group_lang:
        lang = group_lang
    
    quiz_state_raw = await redis.get(GROUP_QUIZ_KEY.format(chat_id=chat_id))
    if not quiz_state_raw:
        await message.answer(Messages.get("NO_ACTIVE_QUIZ", lang))
        return
        
    quiz_state = __import__('json').loads(quiz_state_raw)
    participants = quiz_state.get("participants", {})
    
    if not participants:
        await message.answer(Messages.get("NO_PARTICIPANTS", lang))
        return
        
    # Sort by correct then total
    sorted_p = sorted(participants.items(), key=lambda x: (x[1]['correct'], x[1]['answered']), reverse=True)
    
    leaderboard = f"🏆 <b>{quiz_state.get('title', 'Quiz')} - Leaderboard</b>\n\n"
    for i, (uid, stats) in enumerate(sorted_p[:15], 1):
        try:
            member = await message.chat.get_member(int(uid))
            name = member.user.full_name
        except:
            name = f"User {uid}"
        leaderboard += f"{i}. {name}: <b>{stats['correct']}</b>/{stats['answered']} ✅\n"
        
    await message.answer(leaderboard, parse_mode="HTML")


@router.message(Command("quiz_help"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_group_quiz_help(message: types.Message, user_service: UserService, redis):
    """Show help for group quizzes (available to everyone)"""
    lang = await user_service.get_language(message.from_user.id)
    group_lang = await redis.get(f"group_lang:{message.chat.id}")
    if group_lang:
        lang = group_lang
        
    help_text = (
        "🤖 <b>Group Quiz Help</b>\n\n"
        "/quiz_stats - Leaderboard\n"
        "/stop_quiz - Stop current quiz (Admins only)\n"
        "/set_language - Change group language (Admins only)\n"
        "/create_quiz - Create a new quiz via bot\n"
        "/quiz_help - This help message\n\n"
        "To start a quiz, select 'Start in Group' in the bot's private chat."
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text=Messages.get("CONTACT_ADMIN_BTN", lang), url=f"tg://user?id={settings.ADMIN_ID}")
    
    await message.answer(help_text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.poll_answer(is_group_poll)
async def handle_group_poll_answer(poll_answer: types.PollAnswer, bot: Bot, 
                                   session_service: SessionService, user_service: UserService, redis):
    """Handle poll answers for group quizzes"""
    key = f"group_poll:{poll_answer.poll_id}"
    # Filter already checked via is_group_poll
        
    poll_mapping_raw = await redis.get(key)
    poll_mapping = __import__('json').loads(poll_mapping_raw)
    chat_id = poll_mapping["chat_id"]
    question_index = poll_mapping["question_index"]
    
    # Get quiz state
    quiz_state_raw = await redis.get(GROUP_QUIZ_KEY.format(chat_id=chat_id))
    if not quiz_state_raw:
        return
    
    quiz_state = __import__('json').loads(quiz_state_raw)
    if not quiz_state.get("is_active"):
        return
    
    # Idempotency check - don't process same answer twice
    user_id = poll_answer.user.id
    answer_key = f"group_answered:{chat_id}:{question_index}:{user_id}"
    if await redis.exists(answer_key):
        return
    await redis.set(answer_key, "1", ex=settings.POLL_MAPPING_TTL_SECONDS)
    
    # Get user language
    lang = await user_service.get_language(user_id)
    
    # Track user answer
    questions = quiz_state["questions"]
    q = questions[question_index]
    is_correct = poll_answer.option_ids[0] == q['correct_option_id']
    
    # Update participant stats
    participants = quiz_state.get("participants", {})
    user_key = str(user_id)
    if user_key not in participants:
        participants[user_key] = {"correct": 0, "answered": 0}
    
    participants[user_key]["answered"] += 1
    if is_correct:
        participants[user_key]["correct"] += 1
    
    quiz_state["participants"] = participants
    
    # Check if this is the current question and we should advance
    if question_index == quiz_state["current_index"]:
        # Atomically check if we already started advancing for this question
        advancement_lock_key = f"quiz_advancing:{chat_id}:{question_index}"
        if await redis.set(advancement_lock_key, "1", nx=True, ex=10):
            quiz_state["current_index"] += 1
            
            # Save state
            await redis.set(
                GROUP_QUIZ_KEY.format(chat_id=chat_id),
                __import__('json').dumps(quiz_state),
                ex=14400
            )
            
            # Wait 3 seconds then send next question
            await asyncio.sleep(3)
            
            # Re-fetch state to check if still active
            quiz_state_raw = await redis.get(GROUP_QUIZ_KEY.format(chat_id=chat_id))
            if quiz_state_raw:
                quiz_state = __import__('json').loads(quiz_state_raw)
                if quiz_state.get("is_active"):
                    # Use group language if set
                    group_lang = await redis.get(f"group_lang:{chat_id}")
                    await send_group_question(bot, chat_id, quiz_state, redis, group_lang or lang)
    else:
        # Just save the updated stats if it's an old question answer
        await redis.set(
            GROUP_QUIZ_KEY.format(chat_id=chat_id),
            __import__('json').dumps(quiz_state),
            ex=14400
        )
