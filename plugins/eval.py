import io
import os
import sys
import traceback
from pyrogram import Client, filters
from plugins.config import Config
 
MAX_MESSAGE_LENGTH = 4096
 
 
@Client.on_message(filters.command("eval") & filters.user(Config.OWNER_ID))
async def eval(client, message):
    status_message = await message.reply_text("`Processing ...`")
    cmd = message.text.split(" ", maxsplit=1)[1]
 
    reply_to_ = message
    if message.reply_to_message:
        reply_to_ = message.reply_to_message
 
    old_stderr = sys.stderr
    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()
    redirected_error = sys.stderr = io.StringIO()
    stdout, stderr, exc = None, None, None
 
    try:
        await aexec(cmd, client, message)
    except Exception:
        exc = traceback.format_exc()
 
    stdout = redirected_output.getvalue()
    stderr = redirected_error.getvalue()
    sys.stdout = old_stdout
    sys.stderr = old_stderr
 
    evaluation = ""
    if exc:
        evaluation = exc
    elif stderr:
        evaluation = stderr
    elif stdout:
        evaluation = stdout
    else:
        evaluation = "Success"
 
    final_output = "<b>EVAL</b>: "
    final_output += f"<code>{cmd}</code>\n\n"
    final_output += "<b>OUTPUT</b>:\n"
    final_output += f"<code>{evaluation.strip()}</code> \n"
 
    if len(final_output) > MAX_MESSAGE_LENGTH:
        with io.BytesIO(str.encode(final_output)) as out_file:
            out_file.name = "eval.txt"
            await reply_to_.reply_document(
                document=out_file,
                caption=cmd[: MAX_MESSAGE_LENGTH // 4 - 1],
                disable_notification=True,
                quote=True,
            )
            os.remove("eval.txt")
    else:
        await reply_to_.reply_text(final_output, quote=True)
    await status_message.delete()
 
 
async def aexec(code, client, message):
    exec(
        "async def __aexec(client, message): "
        + "".join(f"\n {l_}" for l_ in code.split("\n"))
    )
    return await locals()["__aexec"](client, message)