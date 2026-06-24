import re
import asyncio
from .utils import STS
from database import db
from config import temp
from .test import CLIENT, start_clone_bot
from translation import Translation
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)

CLIENT = CLIENT()

SOURCE_PROMPT = (
    "<b>❪ SOURCE CHANNEL ❫</b>\n\n"
    "Channel ki <b>ID</b> ya <b>username</b> bhejo:\n\n"
    "• Public channel → <code>@channelusername</code> ya <code>https://t.me/channelusername</code>\n"
    "• Private channel → <code>-100xxxxxxxxxx</code> (numeric ID)\n\n"
    "<i>Public ke liye automatically Bot use hoga, private ke liye Userbot.</i>\n"
    "/cancel - cancel this process"
)

LIMIT_PROMPT = (
    "<b>❪ HOW MANY MESSAGES ❫</b>\n\n"
    "Kitne messages forward karne hai?\n"
    "- Number bhejo (jaise <code>500</code>)\n"
    "- <code>all</code> likho - pura channel forward karne ke liye\n"
    "- <code>live</code> likho - existing + naye aane wale messages continuously forward karne ke liye\n"
    "/cancel - cancel this process"
)


def parse_source(text):
    """Returns (identifier, is_public) or (None, None) if invalid."""
    text = text.strip()

    link_match = re.match(
        r"(https?://)?(t\.me/|telegram\.me/|telegram\.dog/)([a-zA-Z][a-zA-Z0-9_]{3,})/?$",
        text
    )
    if link_match:
        return "@" + link_match.group(3), True

    if text.startswith('@'):
        return text, True

    if re.fullmatch(r"-100\d+", text):
        return int(text), False

    return None, None


@Client.on_message(filters.private & filters.command("quickfwd"))
async def quickfwd(bot, message):
    user_id = message.from_user.id

    if temp.lock.get(user_id) and str(temp.lock.get(user_id)) == "True":
        return await message.reply("<code>please wait until previous task complete</code>")

    channels = await db.get_user_channels(user_id)
    if not channels:
        return await message.reply_text("please set a target channel in /settings before forwarding")

    src_msg = await bot.ask(message.chat.id, SOURCE_PROMPT)
    if src_msg.text and src_msg.text.startswith('/'):
        return await message.reply(Translation.CANCEL)

    identifier, is_public = parse_source(src_msg.text or "")
    if identifier is None:
        return await message.reply_text(
            "<b>Invalid input.</b>\nUse <code>@username</code> for public channel "
            "or <code>-100xxxxxxxxxx</code> for private channel.\nRun /quickfwd again."
        )

    need_bot_type = is_public  # True -> need Bot, False -> need Userbot
    client_doc = await db.get_bot(user_id, is_bot=need_bot_type)
    if not client_doc:
        kind = "Bot" if need_bot_type else "Userbot"
        return await message.reply_text(
            f"<b>You need a {kind} for this.</b>\n"
            f"Public channel ke liye Bot chahiye, private channel ke liye Userbot.\n"
            f"/settings ➜ Bots ➜ Add {kind} se add karo."
        )

    verifying = await message.reply_text("<code>verifying access, please wait...</code>")
    try:
        client = await start_clone_bot(CLIENT.client(client_doc))
    except Exception as e:
        return await verifying.edit(f"<b>Client error:</b> <code>{e}</code>")

    title = str(identifier)
    try:
        try:
            chat = await client.get_chat(identifier)
            title = chat.title or title
        except Exception:
            pass
        await client.get_messages(identifier, 1)
    except Exception as e:
        await verifying.edit(
            f"<b>Could not access this channel.</b>\n<code>{e}</code>\n\n"
            + (
                f"Make sure your [Bot](t.me/{client_doc['username']}) is admin in the source channel."
                if need_bot_type else
                "Make sure your Userbot account is a member of the source channel."
            )
        )
        return await client.stop()
    await client.stop()

    if len(channels) > 1:
        buttons, btn_data = [], {}
        for channel in channels:
            buttons.append([KeyboardButton(f"{channel['title']}")])
            btn_data[channel['title']] = channel['chat_id']
        buttons.append([KeyboardButton("cancel")])
        to_msg = await bot.ask(
            message.chat.id, Translation.TO_MSG.format(client_doc['name'], client_doc['username']),
            reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
        )
        if to_msg.text.startswith(('/', 'cancel')):
            return await message.reply_text(Translation.CANCEL, reply_markup=ReplyKeyboardRemove())
        toid = btn_data.get(to_msg.text)
        to_title = to_msg.text
        if not toid:
            return await message.reply_text("wrong channel choosen !", reply_markup=ReplyKeyboardRemove())
    else:
        toid = channels[0]['chat_id']
        to_title = channels[0]['title']

    limit_msg = await bot.ask(message.chat.id, LIMIT_PROMPT, reply_markup=ReplyKeyboardRemove())
    if limit_msg.text.startswith('/'):
        return await message.reply(Translation.CANCEL)

    continuous = False
    raw = limit_msg.text.strip().lower()
    if raw == "live":
        continuous = True
        limit = 1000000
    elif raw == "all":
        limit = 10000000
    elif raw.isdigit():
        limit = int(raw)
    else:
        return await message.reply_text("<b>Invalid input.</b> Run /quickfwd again.")

    skip_msg = await bot.ask(message.chat.id, Translation.SKIP_MSG)
    if skip_msg.text.startswith('/'):
        return await message.reply(Translation.CANCEL)
    if not skip_msg.text.isdigit():
        return await message.reply_text("<b>Invalid number.</b> Run /quickfwd again.")

    forward_id = f"{user_id}-{skip_msg.id}"
    buttons = [[
        InlineKeyboardButton('Yes', callback_data=f"start_public_{forward_id}"),
        InlineKeyboardButton('No', callback_data="close_btn")
    ]]
    await message.reply_text(
        text=Translation.DOUBLE_CHECK.format(
            botname=client_doc['name'], botuname=client_doc['username'],
            from_chat=title, to_chat=to_title, skip=skip_msg.text
        ),
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    STS(forward_id).store(
        identifier, toid, int(skip_msg.text), int(limit),
        continuous=continuous, client_type=need_bot_type
    )
