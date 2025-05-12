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

def split_by_paragraphs(text: str) -> list[str]:
    return text.split("\n\n")

async def gemini_stream(bot:TeleBot, message:Message, m:str, model_type:str, photo_file:bytes=None):
    try:
        prev_msg = await bot.reply_to(message, "🤖 Generating answers...")

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

        buf = ""
        first = True
        for chunk in response:
            if hasattr(chunk, 'text') and chunk.text:
                buf += chunk.text
                paragraphs = split_by_paragraphs(buf)
                msg_buf = ""
                for i, p in enumerate(paragraphs):
                    test_buf = msg_buf + ("\n\n" if msg_buf else "") + p
                    if len(escape(test_buf)) > TG_MAX_LENGTH:
                        try:
                            if first:
                                await bot.edit_message_text(
                                    escape(msg_buf),
                                    chat_id=prev_msg.chat.id,
                                    message_id=prev_msg.message_id,
                                    parse_mode="MarkdownV2"
                                )
                                first = False
                            else:
                                prev_msg = await bot.send_message(
                                    prev_msg.chat.id,
                                    escape(msg_buf),
                                    reply_to_message_id=prev_msg.message_id,
                                    parse_mode="MarkdownV2"
                                )
                        except Exception as e:
                            if "parse markdown" in str(e).lower():
                                if first:
                                    await bot.edit_message_text(
                                        msg_buf,
                                        chat_id=prev_msg.chat.id,
                                        message_id=prev_msg.message_id
                                    )
                                    first = False
                                else:
                                    prev_msg = await bot.send_message(
                                        prev_msg.chat.id,
                                        msg_buf,
                                        reply_to_message_id=prev_msg.message_id
                                    )
                            else:
                                print(f"Error sending message: {e}")
                        msg_buf = p
                    else:
                        msg_buf = test_buf
                buf = msg_buf
        if buf.strip():
            try:
                if first:
                    await bot.edit_message_text(
                        escape(buf),
                        chat_id=prev_msg.chat.id,
                        message_id=prev_msg.message_id,
                        parse_mode="MarkdownV2"
                    )
                else:
                    await bot.send_message(
                        prev_msg.chat.id,
                        escape(buf),
                        reply_to_message_id=prev_msg.message_id,
                        parse_mode="MarkdownV2"
                    )
            except Exception as e:
                if "parse markdown" in str(e).lower():
                    if first:
                        await bot.edit_message_text(
                            buf,
                            chat_id=prev_msg.chat.id,
                            message_id=prev_msg.message_id
                        )
                    else:
                        await bot.send_message(
                            prev_msg.chat.id,
                            buf,
                            reply_to_message_id=prev_msg.message_id
                        )
                else:
                    print(f"Error sending message: {e}")
    except Exception as e:
        traceback.print_exc()
        await bot.reply_to(message, f"{error_info}\nError details: {str(e)}")
