import os
import sys 
import math
import time
import asyncio 
import logging
from .utils import STS
from database import db 
from .test import CLIENT , start_clone_bot
from config import Config, temp
from translation import Translation
from pyrogram import Client, filters 
#from pyropatch.utils import unpack_new_file_id
from pyrogram.errors import FloodWait, MessageNotModified, RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message 

CLIENT = CLIENT()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
TEXT = Translation.TEXT

@Client.on_callback_query(filters.regex(r'^start_public'))
async def pub_(bot, message):
    user = message.from_user.id
    temp.CANCEL[user] = False
    frwd_id = message.data.split("_")[2]
    if temp.lock.get(user) and str(temp.lock.get(user))=="True":
      return await message.answer("please wait until previous task complete", show_alert=True)
    sts = STS(frwd_id)
    if not sts.verify():
      await message.answer("your are clicking on my old button", show_alert=True)
      return await message.message.delete()
    i = sts.get(full=True)
    if i.TO in temp.IS_FRWD_CHAT:
      return await message.answer("In Target chat a task is progressing. please wait until task complete", show_alert=True)
    m = await msg_edit(message.message, "<code>verifying your data's, please wait.</code>")
    _bot, caption, forward_tag, data, protect, button = await sts.get_data(user)
    if not _bot:
      return await msg_edit(m, "<code>You didn't added any bot. Please add a bot using /settings !</code>", wait=True)
    try:
      client = await start_clone_bot(CLIENT.client(_bot))
    except Exception as e:  
      return await m.edit(e)
    await msg_edit(m, "<code>processing..</code>")
    try: 
       # Just check if we can access messages. If continuous, limit might be huge.
       await client.get_messages(sts.get("FROM"), 1)
    except:
       await msg_edit(m, f"**Source chat may be a private channel / group. Use userbot (user must be member over there) or  if Make Your [Bot](t.me/{_bot['username']}) an admin over there**", retry_btn(frwd_id), True)
       return await stop(client, user)
    try:
       k = await client.send_message(i.TO, "Testing")
       await k.delete()
    except:
       await msg_edit(m, f"**Please Make Your [UserBot / Bot](t.me/{_bot['username']}) Admin In Target Channel With Full Permissions**", retry_btn(frwd_id), True)
       return await stop(client, user)
    temp.forwardings += 1
    await db.add_frwd(user)
    await send(client, user, "<b>ғᴏʀᴡᴀʀᴅɪɴɢ sᴛᴀʀᴛᴇᴅ <a href=https://t.me/dev_gagan>Dev Gagan</a></b>")
    sts.add(time=True)
    sleep = 1 if _bot['is_bot'] else 1
    await msg_edit(m, "<code>Processing...</code>") 
    temp.IS_FRWD_CHAT.append(i.TO)
    temp.lock[user] = locked = True
    if locked:
        try:
          MSG = []
          pling=0
          await edit(m, 'Progressing', 10, sts)
          print(f"Starting Forwarding Process... From :{sts.get('FROM')} To: {sts.get('TO')} Totel: {sts.get('limit')} stats : {sts.get('skip')})")

          # Use getattr to safely check for 'continuous' attribute since old STS objects might not have it
          is_continuous = getattr(sts, 'continuous', False)

          async for message in client.iter_messages(
            client,
            chat_id=sts.get('FROM'), 
            limit=int(sts.get('limit')), 
            offset=int(sts.get('skip')) if sts.get('skip') else 0,
            continuous=is_continuous
            ):
                if await is_cancelled(client, user, m, sts):
                   return
                if pling %20 == 0: 
                   await edit(m, 'Progressing', 10, sts)
                pling += 1
                sts.add('fetched')
                if message == "DUPLICATE":
                   sts.add('duplicate')
                   continue 
                elif message == "FILTERED":
                   sts.add('filtered')
                   continue 
                if message.empty or message.service:
                   sts.add('deleted')
                   continue
                # Apply user-configured filters
                disabled_filters = data.get('filters', [])
                if is_message_filtered(message, disabled_filters):
                   sts.add('filtered')
                   continue
                # Apply keyword filter
                keywords = data.get('keywords')
                if keywords and not keyword_match(message, keywords):
                   sts.add('filtered')
                   continue
                # Apply file size filter
                media_size = data.get('media_size')
                if media_size and not size_match(message, media_size):
                   sts.add('filtered')
                   continue
                # Apply extension filter
                extensions = data.get('extensions')
                if extensions and not extension_match(message, extensions):
                   sts.add('filtered')
                   continue
                if forward_tag:
                   MSG.append(message.id)
                   notcompleted = len(MSG)
                   completed = sts.get('total') - sts.get('fetched')
                   if ( notcompleted >= 100 
                        or completed <= 100): 
                      await forward(client, MSG, m, sts, protect)
                      sts.add('total_files', notcompleted)
                      await asyncio.sleep(10)
                      MSG = []
                else:
                   new_caption = custom_caption(message, caption)
                   details = {"msg_id": message.id, "media": media(message), "caption": new_caption, 'button': button, "protect": protect}
                   await copy(client, details, m, sts)
                   sts.add('total_files')
                   await asyncio.sleep(sleep)
                   await asyncio.sleep(0)  # yield control to event loop
        except Exception as e:
            await msg_edit(m, f'<b>ERROR:</b>\n<code>{e}</code>', wait=True)
            temp.IS_FRWD_CHAT.remove(sts.TO)
            return await stop(client, user)
        temp.IS_FRWD_CHAT.remove(sts.TO)
        await send(client, user, "<b>🎉 ғᴏʀᴡᴀᴅɪɴɢ ᴄᴏᴍᴘʟᴇᴛᴇᴅ 🥀 <a href=https://t.me/dev_gagan>SUPPORT</a>🥀</b>")
        await edit(m, 'Completed', "completed", sts) 
        await stop(client, user)
            
def is_message_filtered(message, disabled_filters):
    """Return True if message should be SKIPPED based on disabled filters list."""
    if not disabled_filters:
        return False
    if message.text and 'text' in disabled_filters:
        return True
    if message.photo and 'photo' in disabled_filters:
        return True
    if message.video and 'video' in disabled_filters:
        return True
    if message.document and 'document' in disabled_filters:
        return True
    if message.audio and 'audio' in disabled_filters:
        return True
    if message.voice and 'voice' in disabled_filters:
        return True
    if message.animation and 'animation' in disabled_filters:
        return True
    if message.sticker and 'sticker' in disabled_filters:
        return True
    if message.poll and 'poll' in disabled_filters:
        return True
    return False

def keyword_match(message, keywords):
    """Return True if message filename contains any keyword (or no media)."""
    if not keywords:
        return True
    if message.media:
        media_obj = getattr(message, message.media.value, None)
        file_name = getattr(media_obj, 'file_name', '') or ''
        for kw in keywords:
            if kw.lower() in file_name.lower():
                return True
        return False
    return True

def size_match(message, media_size):
    """Return True if message passes the size filter."""
    if not media_size:
        return True
    limit_mb, above = media_size[0], media_size[1]
    if not limit_mb:
        return True
    if message.media:
        media_obj = getattr(message, message.media.value, None)
        file_size = getattr(media_obj, 'file_size', 0) or 0
        file_size_mb = file_size / (1024 * 1024)
        if above is True:   # forward files > limit
            return file_size_mb >= limit_mb
        elif above is False:  # forward files < limit
            return file_size_mb <= limit_mb
    return True

def extension_match(message, extensions):
    """Return True if message does NOT have a blocked extension."""
    if not extensions:
        return True
    if message.document:
        file_name = getattr(message.document, 'file_name', '') or ''
        ext = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''
        if ext in [e.lower().strip('.') for e in extensions]:
            return False
    return True


async def copy(bot, msg, m, sts, retries=3):
   for attempt in range(retries):
     try:                                  
       if msg.get("media") and msg.get("caption"):
          await bot.send_cached_media(
                chat_id=sts.get('TO'),
                file_id=msg.get("media"),
                caption=msg.get("caption"),
                reply_markup=msg.get('button'),
                protect_content=msg.get("protect"))
       else:
          await bot.copy_message(
                chat_id=sts.get('TO'),
                from_chat_id=sts.get('FROM'),    
                caption=msg.get("caption"),
                message_id=msg.get("msg_id"),
                reply_markup=msg.get('button'),
                protect_content=msg.get("protect"))
       return  # success
     except FloodWait as e:
       await edit(m, 'Progressing', e.value, sts)
       await asyncio.sleep(e.value + 2)
       await edit(m, 'Progressing', 10, sts)
     except Exception as e:
       print(f"Copy attempt {attempt+1} failed for msg {msg.get('msg_id')}: {e}")
       if attempt < retries - 1:
           await asyncio.sleep(3)
       else:
           sts.add('deleted')
        
async def forward(bot, msg, m, sts, protect, retries=3):
   for attempt in range(retries):
     try:                             
       await bot.forward_messages(
             chat_id=sts.get('TO'),
             from_chat_id=sts.get('FROM'), 
             protect_content=protect,
             message_ids=msg)
       return  # success
     except FloodWait as e:
       await edit(m, 'Progressing', e.value, sts)
       await asyncio.sleep(e.value + 2)
       await edit(m, 'Progressing', 10, sts)
     except Exception as e:
       print(f"Forward attempt {attempt+1} failed for msgs {msg}: {e}")
       if attempt < retries - 1:
           await asyncio.sleep(3)
       else:
           sts.add('deleted')

PROGRESS = """
📈 Percetage: {0} %

♻️ Feched: {1}

♻️ Fowarded: {2}

♻️ Remaining: {3}

♻️ Stataus: {4}

⏳️ ETA: {5}
"""

async def msg_edit(msg, text, button=None, wait=None):
    try:
        return await msg.edit(text, reply_markup=button)
    except MessageNotModified:
        pass 
    except FloodWait as e:
        if wait:
           await asyncio.sleep(e.value)
           return await msg_edit(msg, text, button, wait)
        
async def edit(msg, title, status, sts):
   i = sts.get(full=True)
   status = 'Forwarding' if status == 10 else f"Sleeping {status} s" if str(status).isnumeric() else status
   # Handle division by zero if total is 0 (which happens if infinite/continuous without known total)
   total = float(i.total) if float(i.total) > 0 else 1.0
   percentage = "{:.0f}".format(float(i.fetched)*100/total)
   
   now = time.time()
   diff = int(now - i.start)
   speed = sts.divide(i.fetched, diff)
   elapsed_time = round(diff) * 1000
   time_to_completion = round(sts.divide(i.total - i.fetched, int(speed))) * 1000
   estimated_total_time = elapsed_time + time_to_completion  
   progress = "◉{0}{1}".format(
       ''.join(["◉" for i in range(math.floor(int(percentage) / 10))]),
       ''.join(["◎" for i in range(10 - math.floor(int(percentage) / 10))]))
   button =  [[InlineKeyboardButton(title, f'fwrdstatus#{status}#{estimated_total_time}#{percentage}#{i.id}')]]
   estimated_total_time = TimeFormatter(milliseconds=estimated_total_time)
   estimated_total_time = estimated_total_time if estimated_total_time != '' else '0 s'

   text = TEXT.format(i.fetched, i.total_files, i.duplicate, i.deleted, i.skip, status, percentage, estimated_total_time, progress)
   if status in ["cancelled", "completed"]:
      button.append(
         [InlineKeyboardButton('Support', url='https://t.me/dev_gagan'),
         InlineKeyboardButton('Updates', url='https://t.me/dev_gagan')]
         )
   else:
      button.append([InlineKeyboardButton('• ᴄᴀɴᴄᴇʟ', 'terminate_frwd')])
   await msg_edit(msg, text, InlineKeyboardMarkup(button))
   
async def is_cancelled(client, user, msg, sts):
   if temp.CANCEL.get(user)==True:
      temp.IS_FRWD_CHAT.remove(sts.TO)
      await edit(msg, "Cancelled", "completed", sts)
      await send(client, user, "<b>❌ Forwarding Process Cancelled</b>")
      await stop(client, user)
      return True 
   return False 

async def stop(client, user):
   try:
     await client.stop()
   except:
     pass 
   await db.rmve_frwd(user)
   temp.forwardings -= 1
   temp.lock[user] = False 
    
async def send(bot, user, text):
   try:
      await bot.send_message(user, text=text)
   except:
      pass 
     
def custom_caption(msg, caption):
  if msg.media:
    if (msg.video or msg.document or msg.audio or msg.photo):
      media = getattr(msg, msg.media.value, None)
      if media:
        file_name = getattr(media, 'file_name', '')
        file_size = getattr(media, 'file_size', '')
        fcaption = getattr(msg, 'caption', '')
        if fcaption:
          fcaption = fcaption.html
        if caption:
          return caption.format(filename=file_name, size=get_size(file_size), caption=fcaption)
        return fcaption
  return None

def get_size(size):
  units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
  size = float(size)
  i = 0
  while size >= 1024.0 and i < len(units):
     i += 1
     size /= 1024.0
  return "%.2f %s" % (size, units[i]) 

def media(msg):
  if msg.media:
     media = getattr(msg, msg.media.value, None)
     if media:
        return getattr(media, 'file_id', None)
  return None 

def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + "d, ") if days else "") + \
        ((str(hours) + "h, ") if hours else "") + \
        ((str(minutes) + "m, ") if minutes else "") + \
        ((str(seconds) + "s, ") if seconds else "") + \
        ((str(milliseconds) + "ms, ") if milliseconds else "")
    return tmp[:-2]

def retry_btn(id):
    return InlineKeyboardMarkup([[InlineKeyboardButton('♻️ RETRY ♻️', f"start_public_{id}")]])

@Client.on_callback_query(filters.regex(r'^terminate_frwd$'))
async def terminate_frwding(bot, m):
    user_id = m.from_user.id 
    temp.lock[user_id] = False
    temp.CANCEL[user_id] = True 
    await m.answer("Forwarding cancelled !", show_alert=True)
          
@Client.on_callback_query(filters.regex(r'^fwrdstatus'))
async def status_msg(bot, msg):
    _, status, est_time, percentage, frwd_id = msg.data.split("#")
    sts = STS(frwd_id)
    if not sts.verify():
       fetched, forwarded, remaining = 0
    else:
       fetched, forwarded = sts.get('fetched'), sts.get('total_files')
       remaining = fetched - forwarded 
    est_time = TimeFormatter(milliseconds=est_time)
    est_time = est_time if (est_time != '' or status not in ['completed', 'cancelled']) else '0 s'
    return await msg.answer(PROGRESS.format(percentage, fetched, forwarded, remaining, status, est_time), show_alert=True)
                  
@Client.on_callback_query(filters.regex(r'^close_btn$'))
async def close(bot, update):
    await update.answer()
    await update.message.delete()
