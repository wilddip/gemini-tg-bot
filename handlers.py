from telebot import TeleBot
from telebot.types import Message
from md2tgmd import escape
import traceback
from config import conf
import gemini
from i18n import get_text

model_1                 =       conf["model_1"]
model_2                 =       conf["model_2"]

gemini_chat_dict        = gemini.gemini_chat_dict
gemini_pro_chat_dict    = gemini.gemini_pro_chat_dict
default_model_dict      = gemini.default_model_dict

async def start(message: Message, bot: TeleBot) -> None:
    lang = getattr(message.from_user, 'language_code', 'en')
    try:
        if str(message.from_user.id) not in default_model_dict:
            default_model_dict[str(message.from_user.id)] = True
            model = model_1
        else:
            model = model_1 if default_model_dict[str(message.from_user.id)] else model_2
        await bot.reply_to(message, escape(f"{get_text('welcome', lang)}\nCurrent model: `{model}`\nFor example: `Who is john lennon?`"), parse_mode="MarkdownV2")
    except IndexError:
        await bot.reply_to(message, get_text('error', lang))

async def gemini_stream_handler(message: Message, bot: TeleBot) -> None:
    lang = getattr(message.from_user, 'language_code', 'en')
    try:
        m = message.text.strip().split(maxsplit=1)[1].strip()
    except IndexError:
        await bot.reply_to(message, escape(get_text('add_after_flash', lang)), parse_mode="MarkdownV2")
        return
    await gemini.gemini_stream(bot, message, m, model_1)

async def gemini_pro_stream_handler(message: Message, bot: TeleBot) -> None:
    lang = getattr(message.from_user, 'language_code', 'en')
    try:
        m = message.text.strip().split(maxsplit=1)[1].strip()
    except IndexError:
        await bot.reply_to(message, escape(get_text('add_after_pro', lang)), parse_mode="MarkdownV2")
        return
    await gemini.gemini_stream(bot, message, m, model_2)

async def clear(message: Message, bot: TeleBot) -> None:
    lang = getattr(message.from_user, 'language_code', 'en')
    if (str(message.from_user.id) in gemini_chat_dict):
        del gemini_chat_dict[str(message.from_user.id)]
    if (str(message.from_user.id) in gemini_pro_chat_dict):
        del gemini_pro_chat_dict[str(message.from_user.id)]
    await bot.reply_to(message, get_text('history_cleared', lang))

async def switch(message: Message, bot: TeleBot) -> None:
    lang = getattr(message.from_user, 'language_code', 'en')
    if message.chat.type != "private":
        await bot.reply_to(message, get_text('only_private', lang))
        return
    if str(message.from_user.id) not in default_model_dict:
        default_model_dict[str(message.from_user.id)] = False
        await bot.reply_to(message, get_text('now_using', lang) + model_2)
        return
    if default_model_dict[str(message.from_user.id)] == True:
        default_model_dict[str(message.from_user.id)] = False
        await bot.reply_to(message, get_text('now_using', lang) + model_2)
    else:
        default_model_dict[str(message.from_user.id)] = True
        await bot.reply_to(message, get_text('now_using', lang) + model_1)

async def gemini_private_handler(message: Message, bot: TeleBot) -> None:
    lang = getattr(message.from_user, 'language_code', 'en')
    m = message.text.strip()
    if str(message.from_user.id) not in default_model_dict:
        default_model_dict[str(message.from_user.id)] = True
        await gemini.gemini_stream(bot,message,m,model_1)
    else:
        if default_model_dict[str(message.from_user.id)]:
            await gemini.gemini_stream(bot,message,m,model_1)
        else:
            await gemini.gemini_stream(bot,message,m,model_2)

async def gemini_photo_handler(message: Message, bot: TeleBot) -> None:
    lang = getattr(message.from_user, 'language_code', 'en')
    if message.chat.type != "private":
        s = message.caption or ""
        if not s:
            return
        try:
            file_path = await bot.get_file(message.photo[-1].file_id)
            photo_file = await bot.download_file(file_path.file_path)
        except Exception:
            traceback.print_exc()
            await bot.reply_to(message, get_text('error', lang))
            return
        await gemini.gemini_stream(bot, message, s, model_1, photo_file)
    else:
        s = message.caption or ""
        try:
            file_path = await bot.get_file(message.photo[-1].file_id)
            photo_file = await bot.download_file(file_path.file_path)
        except Exception:
            traceback.print_exc()
            await bot.reply_to(message, get_text('error', lang))
            return
        if str(message.from_user.id) not in default_model_dict:
            default_model_dict[str(message.from_user.id)] = True
            await gemini.gemini_stream(bot, message, s, model_1, photo_file)
        else:
            if default_model_dict[str(message.from_user.id)]:
                await gemini.gemini_stream(bot, message, s, model_1, photo_file)
            else:
                await gemini.gemini_stream(bot, message, s, model_2, photo_file)
