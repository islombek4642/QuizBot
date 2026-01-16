"""
Group Quiz Handler Module

Handles:
- Bot membership in groups (my_chat_member updates)
- Group quiz initiation and flow
- Individual user tracking in group quizzes
"""

import asyncio
import time
import json
from typing import Optional, Dict, Any
from sqlalchemy import select

from aiogram import Router, types, F, Bot
from aiogram.types import ChatMemberUpdated
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER, Command

from constants.messages import Messages
from handlers.common import get_main_keyboard
from services.user_service import UserService
from services.quiz_service import QuizService
from services.session_service import SessionService
from services.group_service import GroupService
from core.config import settings
from core.logger import logger

router = Router()

# Redis keys for group tracking
GROUP_MEMBERS_KEY = "bot_groups"  # Set of group_ids where bot is member
GROUP_QUIZ_KEY = "group_quiz:{chat_id}"  # Active quiz in a group
GROUP_USER_ANSWER_KEY = "group_answer:{chat_id}:{quiz_id}:{user_id}"  # Individual user answers


from aiogram.filters import BaseFilter

class IsGroupPoll(BaseFilter):
    async def __call__(self, event: types.TelegramObject, redis) -> bool:
        if isinstance(event, types.PollAnswer):
            poll_id = event.poll_id
        elif isinstance(event, types.Poll):
            poll_id = event.id
        else:
            return False
            
        if not redis:
            logger.warning("IsGroupPoll: redis not available")
            return False
            
        exists = await redis.exists(f"group_poll:{poll_id}")
        if not exists:
            pass
            
        logger.info("IsGroupPoll check", poll_id=poll_id, exists=exists, event_type=type(event).__name__)
        return bool(exists)


async def get_bot_groups(redis) -> list:
    """Get list of groups where bot is a member"""
    groups = await redis.smembers(GROUP_MEMBERS_KEY)
    return list(groups) if groups else []


async def add_bot_group(redis, chat_id: int, chat_title: str, username: str = None):
    """Add a group to bot's group list"""
    await redis.sadd(GROUP_MEMBERS_KEY, str(chat_id))
    # Store group title and username
    mapping = {"title": chat_title}
    if username:
        mapping["username"] = username
    await redis.hset(f"group_info:{chat_id}", mapping=mapping)


async def remove_bot_group(redis, chat_id: int):
    """Remove a group from bot's group list"""
    await redis.srem(GROUP_MEMBERS_KEY, str(chat_id))
    await redis.delete(f"group_info:{chat_id}")


async def get_group_title(redis, chat_id: int) -> str:
    """Get group title by chat_id"""
    title = await redis.hget(f"group_info:{chat_id}", "title")
    return title or f"Group {chat_id}"


@router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_bot_added_to_group(event: ChatMemberUpdated, user_service: UserService, group_service: GroupService, redis):
    """Handle bot being added to a group"""
    chat = event.chat
    user = event.from_user
    
    if chat.type not in ("group", "supergroup"):
        return
    
    # Get user language for response
    lang = await user_service.get_language(user.id)
    
    # Store group in Database
    await group_service.get_or_create_group(
        telegram_id=chat.id,
        title=chat.title or f"Group {chat.id}",
        username=chat.username,
        language=lang
    )
    
    # Keep in Redis for backward compatibility if needed, though GroupService should be primary
    if redis:
        await add_bot_group(redis, chat.id, chat.title or f"Group {chat.id}", chat.username)
    
    logger.info("Bot added to group", chat_id=chat.id, chat_title=chat.title, added_by=user.id)
    
    # Send confirmation to the group
    try:
        await event.bot.send_message(
            chat.id,
            Messages.get("BOT_ADDED_TO_GROUP", lang),
            reply_markup=types.ReplyKeyboardRemove()
        )
    except Exception as e:
        logger.error("Failed to send group welcome message", error=str(e), chat_id=chat.id)


@router.my_chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER))
async def on_bot_removed_from_group(event: ChatMemberUpdated, group_service: GroupService, redis):
    """Handle bot being removed from a group"""
    chat = event.chat
    
    if chat.type not in ("group", "supergroup"):
        return
    
    # Remove group from Database
    await group_service.remove_group(chat.id)
    
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
                                   group_service: GroupService, quiz_service: QuizService, session_service: SessionService, redis, lang: str):
    """Refactored: Handle 'Start in Group' button - show group selection"""
    quiz_id = int(callback.data.split("_")[3])
    telegram_id = callback.from_user.id
    
    # Get available groups
    if not redis:
        await callback.answer(Messages.get("ERROR_GENERIC", lang), show_alert=True)
        return
    
    groups = await get_bot_groups(redis)
    # Filter groups where user is admin
    user_admin_groups = []
    for group_id in groups:
        try:
            member = await callback.bot.get_chat_member(chat_id=int(group_id), user_id=telegram_id)
            if member.status in ('administrator', 'creator'):
                user_admin_groups.append(group_id)
        except Exception as e:
            logger.warning(f"Could not check member status for {group_id}: {e}")
            continue

    if not user_admin_groups:
        # If no groups found where user is admin, show "Add to Group" button
        bot_username = settings.BOT_USERNAME
        if not bot_username:
            try:
                bot_info = await callback.bot.get_me()
                bot_username = bot_info.username
            except:
                bot_username = ""
        
        if bot_username:
            builder = InlineKeyboardBuilder()
            builder.button(
                text=Messages.get("ADD_TO_GROUP_BTN", lang),
                url=f"https://t.me/{bot_username}?startgroup&admin=post_messages+delete_messages+restrict_members+pin_messages+manage_topics"
            )
            await callback.message.answer(
                Messages.get("NO_GROUPS", lang),
                reply_markup=builder.as_markup()
            )
            await callback.answer()
            return
        else:
            await callback.answer(Messages.get("NO_GROUPS", lang), show_alert=True)
            return

    # Build group selection keyboard
    builder = InlineKeyboardBuilder()
    for group_id in user_admin_groups:
        # Try to get title from DB first
        res = await session_service.db.execute(select(Group.title).filter(Group.telegram_id == int(group_id)))
        title = res.scalar() or await get_group_title(redis, int(group_id))
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
async def confirm_group_quiz_callback(callback: types.CallbackQuery,
                                      quiz_service: QuizService, session_service: SessionService, redis, lang: str):
    """Confirm and start quiz in selected group"""
    parts = callback.data.split("_")
    quiz_id = int(parts[3])
    chat_id = int(parts[4])
    telegram_id = callback.from_user.id
    
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
    
    # Start group quiz lobby instead of immediate start
    # Use group preference if stored for the start logic
    group_lang = await redis.get(f"group_lang:{chat_id}")
    await announce_group_quiz(callback.bot, quiz, chat_id, telegram_id, group_lang or lang, redis)
    
    # Notify user
    await callback.message.edit_text(Messages.get("GROUP_QUIZ_STARTED", lang)) # "Started in group" message
    await callback.answer()


async def announce_group_quiz(bot: Bot, quiz, chat_id: int, owner_id: int, lang: str, redis):
    """Send quiz announcement and wait for players"""
    # Create lobby state
    lobby_key = f"quiz_lobby:{chat_id}"
    users_key = f"quiz_lobby_users:{chat_id}"
    
    # Clear old users set
    await redis.delete(users_key)
    
    active_quiz = await redis.get(GROUP_QUIZ_KEY.format(chat_id=chat_id))
    if active_quiz:
        pass

    lobby_state = {
        "quiz_id": quiz.id,
        "owner_id": owner_id,
        "min_players": 2,
        "status": "waiting",
        "quiz_title": quiz.title,
        "questions_count": len(quiz.questions_json)
    }
    
    msg_text = Messages.get("QUIZ_LOBBY_MSG", lang).format(
        title=quiz.title,
        count=len(quiz.questions_json),
        ready_count=0
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text=Messages.get("I_AM_READY_BTN", lang), callback_data="join_lobby")
    
    msg = await bot.send_message(chat_id, msg_text, parse_mode="HTML", reply_markup=builder.as_markup())
    
    lobby_state["message_id"] = msg.message_id
    await redis.set(lobby_key, json.dumps(lobby_state), ex=3600)


@router.callback_query(F.data == "join_lobby")
async def on_join_lobby(callback: types.CallbackQuery, redis, session_service: SessionService, lang: str):
    """Refactored: Handle user joining the lobby"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    lobby_key = f"quiz_lobby:{chat_id}"
    users_key = f"quiz_lobby_users:{chat_id}"
    
    state_raw = await redis.get(lobby_key)
    if not state_raw:
        await callback.answer(Messages.get("NO_ACTIVE_QUIZ", lang), show_alert=True)
        return
        
    state = json.loads(state_raw)
    
    # Check status
    if state.get("status") != "waiting":
        await callback.answer(Messages.get("GAME_ALREADY_STARTING", lang), show_alert=True)
        return
        
    # Atomic add to set
    is_new = await redis.sadd(users_key, str(user_id))
    if not is_new:
        await callback.answer(Messages.get("ALREADY_READY", lang), show_alert=True)
        return
        
    # Get count
    join_count = await redis.scard(users_key)
    
    group_lang = await redis.get(f"group_lang:{chat_id}")
    display_lang = group_lang or lang
    
    await callback.answer(Messages.get("LOBBY_JOINED", display_lang))
    
    # Update message
    msg_text = Messages.get("QUIZ_LOBBY_MSG", display_lang).format(
        title=state["quiz_title"],
        count=state["questions_count"],
        ready_count=join_count
    )
    
    # Check if ready to start
    if join_count >= state["min_players"]:
        # Only start if we are the one tipping the scale
        # Start countdown
        # Update status first to prevent double start
        state["status"] = "starting"
        await redis.set(lobby_key, json.dumps(state), ex=3600)
        
        await run_countdown_and_start(callback.bot, chat_id, state, redis, session_service, display_lang)
    else:
        builder = InlineKeyboardBuilder()
        builder.button(text=Messages.get("I_AM_READY_BTN", display_lang), callback_data="join_lobby")
        try:
            await callback.message.edit_text(msg_text, parse_mode="HTML", reply_markup=builder.as_markup())
        except Exception as e:
            # message not modified or other error
            pass


async def run_countdown_and_start(bot: Bot, chat_id: int, lobby_state: dict, redis, session_service, lang: str):
    """Run 3-2-1 countdown and start quiz"""
    msg_id = lobby_state.get("message_id")
    users_key = f"quiz_lobby_users:{chat_id}"
    
    for i in range(3, 0, -1):
        text = Messages.get("STARTING_IN", lang).format(seconds=i)
        try:
            await bot.edit_message_text(text=text, chat_id=chat_id, message_id=msg_id)
            logger.info("Countdown", i=i, chat_id=chat_id)
        except Exception as e:
            logger.warning("Countdown edit failed", error=str(e), chat_id=chat_id)
        await asyncio.sleep(1)
        
    # Start quiz
    quiz_service = QuizService(session_service.db)
    quiz = await quiz_service.get_quiz(lobby_state["quiz_id"])
    
    if quiz:
        try:
            await bot.delete_message(chat_id, msg_id)
        except:
            pass
        await start_group_quiz(bot, quiz, chat_id, lobby_state["owner_id"], lang, redis, session_service)
    
    # Cleanup lobby
    await redis.delete(f"quiz_lobby:{chat_id}")
    await redis.delete(users_key)


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
        "title": quiz.title,
        "questions": questions,
        "participants": {},  # user_id -> {correct: X, answered: Y}
        "start_time": time.time(),
        "is_active": True
    }
    
    await redis.set(
        GROUP_QUIZ_KEY.format(chat_id=chat_id),
        json.dumps(quiz_state),
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

    # Reset vote count for current question and record start time
    quiz_state["current_question_votes"] = 0
    quiz_state["question_start_time"] = time.time()
    
    q = questions[current_index]
    question_text = f"{current_index+1}/{len(questions)}. {q['question']}"
    if len(question_text) > 300:
        question_text = question_text[:297] + "..."

    poll_message = await bot.send_poll(
        chat_id=chat_id,
        question=question_text,
        options=q['options'][:10],
        type='quiz',
        correct_option_id=q['correct_option_id'],
        is_anonymous=False,
        open_period=settings.POLL_DURATION_SECONDS,
        reply_markup=types.ReplyKeyboardRemove() # Ensure no keyboard appears
    )
    
    # Store poll message id to stop it if needed
    quiz_state["active_poll_message_id"] = poll_message.message_id
    await redis.set(
        GROUP_QUIZ_KEY.format(chat_id=chat_id),
        json.dumps(quiz_state),
        ex=14400
    )
    
    # Store poll mapping
    poll_mapping = {
        "chat_id": chat_id,
        "quiz_id": quiz_state["quiz_id"],
        "question_index": current_index
    }
    await redis.set(
        f"group_poll:{poll_message.poll.id}",
        json.dumps(poll_mapping),
        ex=settings.POLL_MAPPING_TTL_SECONDS
    )
    
    # Spawn failsafe task to ensure advancement if Telegram update is missed
    asyncio.create_task(
        _failsafe_advance_quiz(bot, chat_id, quiz_state["quiz_id"], current_index, redis)
    )

async def _failsafe_advance_quiz(bot: Bot, chat_id: int, quiz_id: int, question_index: int, redis):
    """Wait for poll duration + buffer, then force advance if not already done"""
    await asyncio.sleep(settings.POLL_DURATION_SECONDS + 2)
    # Try to advance
    await _advance_group_quiz(bot, chat_id, quiz_id, question_index, redis)

async def _advance_group_quiz(bot: Bot, chat_id: int, quiz_id: int, question_index: int, redis):
    """Shared logic to advance quiz to next question safely"""
    try:
        # Get quiz state
        quiz_state_raw = await redis.get(GROUP_QUIZ_KEY.format(chat_id=chat_id))
        if not quiz_state_raw:
            return
        
        quiz_state = json.loads(quiz_state_raw)
        if not quiz_state.get("is_active"):
            return
            
        # Only advance if this is the current active question and matching quiz
        if quiz_state["quiz_id"] != quiz_id or quiz_state["current_index"] != question_index:
            return

        # Check advancement lock to prevent race conditions
        advancement_lock_key = f"quiz_advancing:{chat_id}:{question_index}"
        if await redis.set(advancement_lock_key, "1", nx=True, ex=10):
            logger.info("Advancing quiz triggered", chat_id=chat_id, index=question_index)
            
            # Stop the specific poll message just in case it's still open
            poll_msg_id = quiz_state.get("active_poll_message_id")
            if poll_msg_id:
                try:
                    await bot.stop_poll(chat_id, poll_msg_id)
                except:
                    pass

            # Notify if no one answered
            group_lang = await redis.get(f"group_lang:{chat_id}")
            lang = group_lang or "UZ"
            if quiz_state.get("current_question_votes", 0) == 0:
                try:
                    logger.info("Sending no-answer notification (Group)", chat_id=chat_id, index=question_index + 1)
                    await bot.send_message(chat_id, Messages.get("NO_ONE_ANSWERED", lang).format(index=question_index + 1))
                except Exception as e:
                    logger.warning(f"Failed to send timeout message (Group): {e}")

            quiz_state["current_index"] += 1
            logger.info("Advancing group quiz to next index", chat_id=chat_id, next_index=quiz_state["current_index"])
            
            # Save state
            await redis.set(
                GROUP_QUIZ_KEY.format(chat_id=chat_id),
                json.dumps(quiz_state),
                ex=14400
            )
            
            # Wait 2 seconds then send next question
            await asyncio.sleep(2)
            
            # Re-fetch state to check if still active
            quiz_state_raw = await redis.get(GROUP_QUIZ_KEY.format(chat_id=chat_id))
            if quiz_state_raw:
                quiz_state = json.loads(quiz_state_raw)
                if quiz_state.get("is_active"):
                    # Use group language if set
                    group_lang = await redis.get(f"group_lang:{chat_id}")
                    await send_group_question(bot, chat_id, quiz_state, redis, group_lang or "UZ")
    except Exception as e:
        logger.error("Error in _advance_group_quiz", error=str(e), chat_id=chat_id)


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
        # Sort by correct then total_time (less is better)
        # We use -stats['correct'] for descending and stats.get('total_time', 0) for ascending
        sorted_p = sorted(
            participants.items(), 
            key=lambda x: (-x[1]['correct'], x[1].get('total_time', 999999))
        )
        
        leaderboard = f"🏁 <b>{quiz_title}</b>\n\n"
        leaderboard += Messages.get("FINAL_LEADERBOARD", lang) + "\n"
        
        def format_duration(seconds: float, lang: str) -> str:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            if lang == "UZ":
                res = []
                if mins > 0: res.append(f"{mins} daqiqa")
                if secs > 0 or not res: res.append(f"{secs} soniya")
                return " ".join(res)
            else:
                res = []
                if mins > 0: res.append(f"{mins} minute{'s' if mins > 1 else ''}")
                if secs > 0 or not res: res.append(f"{secs} second{'s' if secs > 1 else ''}")
                return " ".join(res)

        for i, (uid, stats) in enumerate(sorted_p[:15], 1):
            try:
                member = await bot.get_chat_member(chat_id, int(uid))
                name = member.user.full_name
            except:
                name = f"User {uid}"
            
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            rank_str = medals.get(i, f"{i}.")
            
            total_time_str = format_duration(stats.get('total_time', 0), lang)
            leaderboard += f"{rank_str} <a href='tg://user?id={uid}'>{name}</a> – <b>{stats['correct']}</b>/{stats['answered']} ({total_time_str})\n"
        
        # Summary footer
        answered_count = quiz_state.get("current_index", 0)
        
        summary = Messages.get("GROUP_QUIZ_SUMMARY", lang).format(
            count=len(participants),
            answered_count=answered_count
        )
        await bot.send_message(chat_id, leaderboard + summary, parse_mode="HTML")
    
    # Clean up
    await redis.delete(GROUP_QUIZ_KEY.format(chat_id=chat_id))
    
    logger.info("Group quiz finished", chat_id=chat_id, participants=len(participants))



@router.message(Command("stop_quiz"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_stop_group_quiz(message: types.Message, redis, lang: str):
    """Refactored: Stop active quiz in group (only owner or admin)"""
    try:
        chat_id = message.chat.id
        # Use group preference if stored for local lang context
        group_lang = await redis.get(f"group_lang:{chat_id}")
        if group_lang:
            lang = group_lang
        
        quiz_state_raw = await redis.get(GROUP_QUIZ_KEY.format(chat_id=chat_id))
        if not quiz_state_raw:
            await message.reply(Messages.get("NO_ACTIVE_QUIZ", lang))
            return
            
        quiz_state = json.loads(quiz_state_raw)
        
        # Check permission
        is_owner = message.from_user.id == quiz_state.get("owner_id")
        member = await message.chat.get_member(message.from_user.id)
        is_admin = member.status in ("administrator", "creator")
        
        if not (is_owner or is_admin):
            # Notify that only admins can stop
            await message.reply(Messages.get("ONLY_ADMINS", lang))
            return
            
        quiz_state["is_active"] = False
        await redis.set(GROUP_QUIZ_KEY.format(chat_id=chat_id), json.dumps(quiz_state), ex=3600)
        
        # Stop the active poll timer
        poll_message_id = quiz_state.get("active_poll_message_id")
        if poll_message_id:
            try:
                await message.bot.stop_poll(chat_id, poll_message_id)
            except Exception as e:
                # Ignore common poll errors
                if "poll has already been closed" not in str(e) and "poll can't be stopped" not in str(e):
                    logger.warning("Failed to stop poll", error=str(e), chat_id=chat_id)
                    
        # Show statistics before finishing
        await finish_group_quiz(message.bot, chat_id, quiz_state, redis, lang)
        
    except Exception as e:
        logger.error("Error stopping group quiz", error=str(e), chat_id=message.chat.id)
        await message.reply(Messages.get("ERROR_GENERIC", lang))


@router.message(Command("set_language"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_group_set_language(message: types.Message, user_service: UserService):
    """Set language for the group (Admins only)"""
    lang = await user_service.get_language(message.from_user.id)
    member = await message.chat.get_member(message.from_user.id)
    if member.status not in ("administrator", "creator"):
        await message.reply(Messages.get("ONLY_ADMINS", lang))
        return
        
    lang = await user_service.get_language(message.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.button(text="O'zbekcha 🇺🇿", callback_data="set_group_lang_UZ")
    builder.button(text="English 🇬🇧", callback_data="set_group_lang_EN")
    builder.adjust(2)
    
    await message.answer(
        Messages.get("CHOOSE_LANGUAGE", lang), 
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("set_group_lang_"))
async def cb_set_group_lang(callback: types.CallbackQuery, group_service: GroupService, redis, lang: str):
    """Refactored: Handle group language selection"""
    member = await callback.message.chat.get_member(callback.from_user.id)
    if member.status not in ("administrator", "creator"):
        await callback.answer(Messages.get("ERROR_GENERIC", lang), show_alert=True)
        return
        
    new_lang = callback.data.split("_")[-1]
    # Store group language in Database
    await group_service.update_language(callback.message.chat.id, new_lang)
    
    # Store group language in Redis
    await redis.set(f"group_lang:{callback.message.chat.id}", new_lang)
    
    await callback.message.edit_text(Messages.get("LANGUAGE_SET", new_lang))
    await callback.answer()


@router.message(Command("create_quiz"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_group_create_quiz(message: types.Message, lang: str):
    """Refactored: Redirect to bot to create a quiz"""
    member = await message.chat.get_member(message.from_user.id)
    if member.status not in ("administrator", "creator"):
        await message.reply(Messages.get("ONLY_ADMINS", lang))
        return
    bot_info = await message.bot.get_me()
    
    builder = InlineKeyboardBuilder()
    builder.button(text=Messages.get("CREATE_QUIZ_BTN", lang), url=f"https://t.me/{bot_info.username}?start=create")
    
    await message.answer(
        Messages.get("CREATE_QUIZ_REDIRECT", lang).format(username=bot_info.username),
        reply_markup=builder.as_markup()
    )


@router.message(Command("quiz_stats"))
async def cmd_group_quiz_stats(message: types.Message, redis, lang: str):
    """Show current group quiz statistics"""
    chat_id = message.chat.id
    
    member = await message.chat.get_member(message.from_user.id)
    if member.status not in ("administrator", "creator"):
        await message.reply(Messages.get("ONLY_ADMINS", lang))
        return
    
    # Use preference if stored
    group_lang = await redis.get(f"group_lang:{chat_id}")
    if group_lang:
        lang = group_lang
    
    quiz_state_raw = await redis.get(GROUP_QUIZ_KEY.format(chat_id=chat_id))
    if not quiz_state_raw:
        await message.answer(Messages.get("NO_ACTIVE_QUIZ", lang))
        return
        
    quiz_state = json.loads(quiz_state_raw)
    participants = quiz_state.get("participants", {})
    
    if not participants:
        await message.answer(Messages.get("NO_PARTICIPANTS", lang))
        return
        
    # Sort by correct then total_time
    sorted_p = sorted(
        participants.items(), 
        key=lambda x: (-x[1]['correct'], x[1].get('total_time', 999999))
    )
    
    leaderboard = Messages.get("LEADERBOARD_TITLE", lang).format(title=quiz_state.get('title', 'Quiz')) + "\n\n"
    
    def format_duration(seconds: float, lang: str) -> str:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        if lang == "UZ":
            res = []
            if mins > 0: res.append(f"{mins} daqiqa")
            if secs > 0 or not res: res.append(f"{secs} soniya")
            return " ".join(res)
        else:
            res = []
            if mins > 0: res.append(f"{mins} minute{'s' if mins > 1 else ''}")
            if secs > 0 or not res: res.append(f"{secs} second{'s' if secs > 1 else ''}")
            return " ".join(res)

    for i, (uid, stats) in enumerate(sorted_p[:15], 1):
        try:
            member = await message.chat.get_member(int(uid))
            name = member.user.full_name
        except:
            name = f"User {uid}"
            
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        rank_str = medals.get(i, f"{i}.")
        
        total_time_str = format_duration(stats.get('total_time', 0), lang)
        leaderboard += f"{rank_str} <a href='tg://user?id={uid}'>{name}</a> – <b>{stats['correct']}</b>/{stats['answered']} ({total_time_str})\n"
        
    # Summary footer
    answered_count = quiz_state.get("current_index", 0)
    
    summary = Messages.get("GROUP_QUIZ_SUMMARY", lang).format(
        count=len(participants),
        answered_count=answered_count
    )
        
    await message.answer(leaderboard + summary, parse_mode="HTML", reply_markup=types.ReplyKeyboardRemove())


@router.message(Command("quiz_help"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_group_quiz_help(message: types.Message, redis, lang: str):
    """Refactored: Show help for group quizzes (available to everyone)"""
    member = await message.chat.get_member(message.from_user.id)
    if member.status not in ("administrator", "creator"):
        await message.reply(Messages.get("ONLY_ADMINS", lang))
        return
        
    group_lang = await redis.get(f"group_lang:{message.chat.id}")
    if group_lang:
        lang = group_lang
        
    help_text = Messages.get("GROUP_HELP_TEXT", lang)
    
    builder = InlineKeyboardBuilder()
    builder.button(text=Messages.get("CONTACT_ADMIN_BTN", lang), url=f"tg://user?id={settings.ADMIN_ID}")
    
    await message.answer(help_text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.poll_answer(IsGroupPoll())
async def handle_group_poll_answer(poll_answer: types.PollAnswer, bot: Bot, 
                                   session_service: SessionService, user_service: UserService, redis):
    """Handle poll answers for group quizzes"""
    try:
        logger.info("Entering handle_group_poll_answer", user_id=poll_answer.user.id, poll_id=poll_answer.poll_id)
        key = f"group_poll:{poll_answer.poll_id}"
        # Filter already checked via is_group_poll
            
        poll_mapping_raw = await redis.get(key)
        if not poll_mapping_raw:
            logger.warning("Group answer ignored: mapping not found", poll_id=poll_answer.poll_id)
            return

        poll_mapping = json.loads(poll_mapping_raw)
        chat_id = poll_mapping["chat_id"]
        question_index = poll_mapping["question_index"]
        
        # Get quiz state
        quiz_state_raw = await redis.get(GROUP_QUIZ_KEY.format(chat_id=chat_id))
        if not quiz_state_raw:
            logger.warning("Group answer ignored: state not found", chat_id=chat_id)
            return
        
        quiz_state = json.loads(quiz_state_raw)
        if not quiz_state.get("is_active"):
            logger.warning("Group answer ignored: quiz inactive", chat_id=chat_id)
            return
        
        # Idempotency check - don't process same answer twice
        user_id = poll_answer.user.id
        # Use poll_id to enable multiple quizzes in same group without index collision
        answer_key = f"group_answered:{poll_answer.poll_id}:{user_id}"
        if await redis.exists(answer_key):
            logger.info("Group answer ignored: duplicate", user_id=user_id, poll_id=poll_answer.poll_id)
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
            participants[user_key] = {"correct": 0, "answered": 0, "total_time": 0.0}
        
        # Calculate time taken for this answer
        question_start_time = quiz_state.get("question_start_time", time.time())
        time_taken = time.time() - question_start_time
        # Cap time taken at poll duration plus a small buffer
        time_taken = min(time_taken, settings.POLL_DURATION_SECONDS + 2)
        
        participants[user_key]["answered"] += 1
        participants[user_key]["total_time"] += time_taken
        if is_correct:
            participants[user_key]["correct"] += 1
        
        quiz_state["participants"] = participants
        
        # Increment vote count for current question
        quiz_state["current_question_votes"] = quiz_state.get("current_question_votes", 0) + 1
        
        # Just save the updated stats. Advancement now happens when poll closes.
        logger.info("Group poll answer recorded", chat_id=chat_id, user_id=user_id, question_index=question_index)
        await redis.set(
            GROUP_QUIZ_KEY.format(chat_id=chat_id),
            json.dumps(quiz_state),
            ex=14400
        )
    except Exception as e:
        logger.error("Error in handle_group_poll_answer", error=str(e), poll_id=poll_answer.poll_id)


@router.poll(IsGroupPoll())
async def handle_group_poll_update(poll: types.Poll, bot: Bot, redis):
    """Handle poll updates, specifically closing, to advance the quiz"""
    try:
        logger.info("Group poll update received", poll_id=poll.id, closed=poll.is_closed)
        if not poll.is_closed:
            return
            
        # Key existence is guaranteed by filter
        key = f"group_poll:{poll.id}"
        poll_mapping_raw = await redis.get(key)
        if not poll_mapping_raw:
            logger.warning("Group poll update ignored: mapping not found", poll_id=poll.id)
            return
            
        poll_mapping = json.loads(poll_mapping_raw)
        chat_id = poll_mapping["chat_id"]
        question_index = poll_mapping["question_index"]
        logger.info("Processing closed group poll", chat_id=chat_id, question_index=question_index)
        
        # Get quiz state
        quiz_state_raw = await redis.get(GROUP_QUIZ_KEY.format(chat_id=chat_id))
        if not quiz_state_raw:
            logger.warning("Group poll update ignored: quiz state not found", chat_id=chat_id)
            return
        
        quiz_state = json.loads(quiz_state_raw)
        if not quiz_state.get("is_active"):
            logger.warning("Group poll update ignored: quiz not active", chat_id=chat_id)
            return
            
        # Only advance if this is the current active question
        if question_index != quiz_state["current_index"]:
            logger.warning("Group poll update ignored: index mismatch", current=quiz_state["current_index"], received=question_index)
            return

        # Use shared advancement logic
        await _advance_group_quiz(bot, chat_id, quiz_state["quiz_id"], question_index, redis)

    except Exception as e:
        logger.error("Error in handle_group_poll_update", error=str(e), poll_id=poll.id)
