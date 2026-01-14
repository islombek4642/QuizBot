from typing import Any
from aiogram import Router, types, F, Bot
import json
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, Command
from constants.messages import Messages
from handlers.common import get_main_keyboard, enable_user_menu, get_contact_keyboard
from services.user_service import UserService
from services.quiz_service import QuizService
from core.logger import logger

router = Router()
# Only handle private chats - no keyboard buttons in groups
router.message.filter(F.chat.type == "private")

@router.message(CommandStart())
@router.message(F.text.in_([Messages.get("START_BTN", "UZ"), Messages.get("START_BTN", "EN")]))
async def cmd_start(
    message: types.Message, 
    user_service: UserService, 
    quiz_service: QuizService,
    state: FSMContext,
    redis,
    lang: str,
    user: Any
):
    telegram_id = message.from_user.id
    
    if not user or not user.phone_number:
        # Store deep link in state to resume after contact
        args = message.text.split()
        if len(args) > 1:
            await state.update_data(pending_start=args[1])
            
        await message.answer(
            Messages.get("SHARE_CONTACT_PROMPT", lang),
            reply_markup=get_contact_keyboard(lang)
        )
        return

    await enable_user_menu(message.bot, telegram_id)
    
    # Handle deep links
    args = message.text.split()
    if len(args) > 1:
        return await handle_payload(args[1], message, user_service, quiz_service, state, lang, redis, user)

    welcome_text = Messages.get("WELCOME", lang) + "\n\n" + Messages.get("FORMAT_INFO", lang)
    await message.answer(welcome_text, reply_markup=get_main_keyboard(lang, telegram_id))
    
    # Deliver last broadcast to new/returning users
    await check_and_deliver_broadcast(message.bot, telegram_id, redis)
    
    # Clear any pending start after handling
    await state.clear()

async def handle_payload(payload: str, message: types.Message, user_service: UserService, quiz_service: QuizService, state: FSMContext, lang: str, redis=None, user=None):
    """Refactored helper to handle start payloads consistently"""
    telegram_id = message.from_user.id

    if payload == "create":
        from handlers.quiz import cmd_create_quiz
        return await cmd_create_quiz(message, state, user_service, lang, None) # user object will be picked up from data if needed
    elif payload.startswith("ref_"):
        # Referral logic
        try:
            referrer_id = int(payload.split("_")[1])
            telegram_id = message.from_user.id
            user_full_name = message.from_user.full_name
            
            logger.info("Processing referral", telegram_id=telegram_id, referrer_id=referrer_id)

            if referrer_id == telegram_id:
                logger.info("Self-referral detected", telegram_id=telegram_id)
                await message.answer(Messages.get("REFERRAL_SELF_ERROR", lang), parse_mode="HTML")
            
            elif referrer_id > 0 and redis:
                if user:
                    # User ALREADY exists in DB
                    logger.info("Existing user referral check", telegram_id=telegram_id)
                    ref_check_key = f"referral_notify:{telegram_id}:{referrer_id}" # Prevent spamming referrer
                    if not await redis.exists(ref_check_key):
                        await redis.setex(ref_check_key, 60, "1") # 1 minute debounce
                        await handle_referral(referrer_id, message.bot, redis, user_service, user_full_name, is_new=False)
                    else:
                        logger.info("Referral debounce hit", telegram_id=telegram_id)
                else:
                    # User is NEW (not in DB)
                    logger.info("New user referral check", telegram_id=telegram_id)
                    ref_check_key = f"referral_processed:{telegram_id}"
                    if not await redis.exists(ref_check_key):
                        await redis.set(ref_check_key, "1")
                        await handle_referral(referrer_id, message.bot, redis, user_service, user_full_name, is_new=True)
        except Exception as e:
            logger.error(f"Error handling referral: {e}")
            
        # Continue to welcome
        welcome_text = Messages.get("WELCOME", lang) + "\n\n" + Messages.get("FORMAT_INFO", lang)
        await message.answer(welcome_text, reply_markup=get_main_keyboard(lang, telegram_id))
        await state.clear()
        return

    elif payload.startswith("quiz_"):
        try:
            quiz_id = int(payload.split("_")[1])
            from handlers.quiz import show_quiz_info
            
            # REMOVED AUTO-CLONE for performance/database sanity
            # The Save button will be added in show_quiz_info instead
            
            return await show_quiz_info(message.bot, message.chat.id, quiz_id, lang, quiz_service)
        except (ValueError, IndexError):
            logger.warning(f"Invalid quiz payload: {payload}")
    
    # Fallback to normal welcome
    welcome_text = Messages.get("WELCOME", lang) + "\n\n" + Messages.get("FORMAT_INFO", lang)
    await message.answer(welcome_text, reply_markup=get_main_keyboard(lang, telegram_id))
    await state.clear()

@router.message(F.contact)
async def process_contact(
    message: types.Message, 
    user_service: UserService, 
    quiz_service: QuizService,
    state: FSMContext,
    redis,
    lang: str,
    user: Any
):
    telegram_id = message.from_user.id
    contact = message.contact

    if contact.user_id != telegram_id:
        return

    await user_service.update_user(
        telegram_id=telegram_id,
        phone_number=contact.phone_number,
        full_name=f"{contact.first_name} {contact.last_name}" if contact.last_name else contact.first_name,
        username=message.from_user.username
    )

    await enable_user_menu(message.bot, telegram_id)
    await message.answer(
        Messages.get("CONTACT_SAVED", lang),
        reply_markup=get_main_keyboard(lang, telegram_id)
    )
    
    # Deliver last broadcast to newly registered users
    await check_and_deliver_broadcast(message.bot, telegram_id, redis)
    
    # Check for pending deep link
    state_data = await state.get_data()
    pending_payload = state_data.get("pending_start")
    
    # Process pending payload if exists
    if pending_payload:
        # Pass user=None to force "New User" logic in handle_payload for fresh registrations
        return await handle_payload(pending_payload, message, user_service, quiz_service, state, lang, redis, user=None)
    
    # Clear state if no pending payload
    await state.clear()

async def check_and_deliver_broadcast(bot: Bot, user_id: int, redis, user=None):
    """Deliver last broadcast if available in Redis"""
    try:
        data = await redis.get("global_settings:last_broadcast")
        if data:
            broadcast = json.loads(data)
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=broadcast["from_chat_id"],
                message_id=broadcast["message_id"]
            )
    except Exception as e:
        logger.error(f"Error delivering last broadcast to {user_id}: {e}")

async def handle_referral(referrer_id: int, bot: Bot, redis, user_service: UserService, new_user_name: str, is_new: bool):
    """Process referral reward and notification"""
    try:
        # Avoid self-referral (checked in caller too, but safety first)
        if referrer_id <= 0: return
        
        # Don't try to send message to self (bot)
        me = await bot.get_me()
        if referrer_id == me.id: return

        referrer_lang = await user_service.get_language(referrer_id)

        if is_new:
            # Increment credits
            await redis.incr(f"ai_credits:gen:{referrer_id}")
            await redis.incr(f"ai_credits:conv:{referrer_id}")
            
            # Remove cooldowns immediately
            await redis.delete(f"ai_limit:gen:{referrer_id}")
            await redis.delete(f"ai_limit:conv:{referrer_id}")
            
            # Notify referrer - SUCCESS
            await bot.send_message(
                referrer_id,
                Messages.get("REFERRAL_SUCCESS", referrer_lang).format(name=new_user_name),
                parse_mode="HTML"
            )
        else:
            # Notify referrer - EXISTING
            await bot.send_message(
                referrer_id,
                Messages.get("REFERRAL_EXISTING", referrer_lang).format(name=new_user_name),
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error("Referral error", error=str(e))

@router.message(F.text.in_([Messages.get("SHARE_BOT_BTN", "UZ"), Messages.get("SHARE_BOT_BTN", "EN")]))
async def cmd_share_bot(message: types.Message, bot: Bot, lang: str):
    """Handle Share Bot button - send a nice ad/promo message"""
    me = await bot.get_me()
    promo_text = Messages.get("BOT_PROMO_TEXT", lang).format(username=me.username)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    # switch_inline_query with 'share' keyword to trigger specific result
    builder.button(
        text=Messages.get("INVITE_FRIENDS_BTN", lang),
        switch_inline_query="share"
    )
    
    await message.answer(
        promo_text,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.message(Command("help"))
@router.message(F.text.in_([Messages.get("HELP_BTN", "UZ"), Messages.get("HELP_BTN", "EN")]))
async def cmd_help(message: types.Message, user_service: UserService):
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from core.config import settings

    builder = InlineKeyboardBuilder()
    if settings.ADMIN_ID != 0:
        builder.button(
            text=Messages.get("CONTACT_ADMIN_BTN", lang),
            url=f"tg://user?id={settings.ADMIN_ID}"
        )
    
    await message.answer(
        Messages.get("HELP_TEXT", lang),
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.message(CommandStart(), F.chat.type.in_({"group", "supergroup"}))
async def cmd_start_group(message: types.Message, user_service: UserService, state: FSMContext, redis, **kwargs):
    """Handle /start in groups (Deep Linking only)"""
    args = message.text.split()
    if len(args) < 2:
        return # Ignore bare /start in groups
        
    payload = args[1]
    if not payload.startswith("quiz_"):
        return
        
    # Check admin permission
    member = await message.chat.get_member(message.from_user.id)
    lang = await user_service.get_language(message.from_user.id)
    
    if member.status not in ("administrator", "creator"):
        await message.reply(Messages.get("ONLY_ADMINS", lang))
        return
        
    # Get services and process
    data = kwargs
    db = data.get("db")
    redis = data.get("redis") or redis
    
    from services.quiz_service import QuizService
    from services.session_service import SessionService
    from db.session import AsyncSessionLocal
    
    async with AsyncSessionLocal() as session:
        quiz_service = QuizService(session)
        session_service = SessionService(session, redis)
        
        try:
            quiz_id = int(payload.split("_")[1])
            quiz = await quiz_service.get_quiz(quiz_id)
            if not quiz:
                await message.reply(Messages.get("ERROR_TEST_NOT_FOUND", lang))
                # The user's instruction implies adding referral logic here.
                # However, the provided snippet for referral logic (if user: ... handle_referral)
                # is not present in the original code and introduces undefined variables
                # like `user`, `referrer_id`, `telegram_id`, `user_full_name`.
                # To make the change faithfully and syntactically correct,
                # I will only apply the specific debounce value if it were part of an existing
                # `redis.setex` call. Since there is no such call in this block,
                # and adding the entire block would introduce errors, I will assume
                # the instruction was to ensure any *existing* referral debounce is 60s.
                # As there is no existing referral debounce in this function, no change is made here.
                return
                
            # Import start_group_quiz
            from handlers.group import start_group_quiz
            
            # Use group language preference if set
            group_lang = await redis.get(f"group_lang:{message.chat.id}")
            
            await start_group_quiz(
                message.bot, 
                quiz, 
                message.chat.id, 
                message.from_user.id, 
                group_lang or lang, 
                redis, 
                session_service
            )
            
        except (ValueError, IndexError):
            logger.warning(f"Invalid quiz payload: {payload}")
        except Exception as e:
            logger.error("Error in cmd_start_group", error=str(e))
        
