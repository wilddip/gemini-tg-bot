import io
import time
import traceback
import sys
from PIL import Image
from telebot.types import Message
from md2tgmd import escape
from telebot import TeleBot
from config import conf
from google import genai

gemini_chat_dict = {}
gemini_pro_chat_dict = {}
default_model_dict = {}

model_1                 =       conf["model_1"]
model_2                 =       conf["model_2"]
error_info              =       conf["error_info"]
before_generate_info    =       conf["before_generate_info"]
download_pic_notify     =       conf["download_pic_notify"]

TG_MAX_LENGTH = 4000  # Using 4000 to have some buffer for markdown

search_tool = {'google_search': {}}

client = genai.Client(api_key=sys.argv[2])

async def trim_to_last_paragraph(text: str) -> tuple[str, str]:
    parts = text.split("\n\n")
    if len(parts) <= 1:
        return text, ""
    
    return "\n\n".join(parts[:-1]), parts[-1]

async def should_split_message(text: str) -> bool:
    return len(escape(text)) >= TG_MAX_LENGTH

async def gemini_stream(bot:TeleBot, message:Message, m:str, model_type:str, photo_file:bytes=None):
    sent_message = None
    next_part = ""
    try:
        sent_message = await bot.reply_to(message, "🤖 Generating answers...")

        chat = None
        if model_type == model_1:
            chat_dict = gemini_chat_dict
        else:
            chat_dict = gemini_pro_chat_dict

        if str(message.from_user.id) not in chat_dict:
            chat = client.aio.chats.create(model=model_type, config={'tools': [search_tool]})
            chat_dict[str(message.from_user.id)] = chat
        else:
            chat = chat_dict[str(message.from_user.id)]

        if photo_file:
            image = Image.open(io.BytesIO(photo_file))
            response = await chat.send_message_stream([m, image])
        else:
            response = await chat.send_message_stream(m)

        full_response = ""
        last_update = time.time()
        update_interval = conf["streaming_update_interval"]
        current_msg = sent_message

        async for chunk in response:
            if hasattr(chunk, 'text') and chunk.text:
                if next_part:
                    full_response = next_part + "\n\n"
                    next_part = ""
                full_response += chunk.text
                current_time = time.time()

                if current_time - last_update >= update_interval:
                    if await should_split_message(full_response):
                        current_text, next_part = await trim_to_last_paragraph(full_response)
                        try:
                            await bot.edit_message_text(
                                escape(current_text),
                                chat_id=current_msg.chat.id,
                                message_id=current_msg.message_id,
                                parse_mode="MarkdownV2"
                            )
                        except Exception as md_e:
                            if "parse markdown" in str(md_e).lower():
                                await bot.edit_message_text(
                                    current_text,
                                    chat_id=current_msg.chat.id,
                                    message_id=current_msg.message_id
                                )
                            current_msg = await bot.reply_to(message, next_part)
                            full_response = next_part
                    else:
                        try:
                            await bot.edit_message_text(
                                escape(full_response),
                                chat_id=current_msg.chat.id,
                                message_id=current_msg.message_id,
                                parse_mode="MarkdownV2"
                            )
                        except Exception as e:
                            if "parse markdown" in str(e).lower():
                                await bot.edit_message_text(
                                    full_response,
                                    chat_id=current_msg.chat.id,
                                    message_id=current_msg.message_id
                                )
                            elif "message is not modified" not in str(e).lower():
                                print(f"Error updating message: {e}")
                    last_update = current_time

        if await should_split_message(full_response):
            current_text, next_part = await trim_to_last_paragraph(full_response)
            try:
                await bot.edit_message_text(
                    escape(current_text),
                    chat_id=current_msg.chat.id,
                    message_id=current_msg.message_id,
                    parse_mode="MarkdownV2"
                )
            except Exception as md_e:
                if "parse markdown" in str(md_e).lower():
                    await bot.edit_message_text(
                        current_text,
                        chat_id=current_msg.chat.id,
                        message_id=current_msg.message_id
                    )
            if next_part:
                await bot.reply_to(message, next_part)
        else:
            try:
                await bot.edit_message_text(
                    escape(full_response),
                    chat_id=current_msg.chat.id,
                    message_id=current_msg.message_id,
                    parse_mode="MarkdownV2"
                )
            except Exception as e:
                if "parse markdown" in str(e).lower():
                    await bot.edit_message_text(
                        full_response,
                        chat_id=current_msg.chat.id,
                        message_id=current_msg.message_id
                    )

    except Exception as e:
        traceback.print_exc()
        if sent_message:
            await bot.edit_message_text(
                f"{error_info}\nError details: {str(e)}",
                chat_id=sent_message.chat.id,
                message_id=sent_message.message_id
            )
        else:
            await bot.reply_to(message, f"{error_info}\nError details: {str(e)}")
