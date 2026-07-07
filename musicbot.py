import discord
from discord.ext import commands
from quart import Quart
import asyncio
import re
import traceback
import sys
import os
from dotenv import load_dotenv

# Import the Google Drive Manager from your other file
from drive_utils import GoogleDriveManager

# --- Load environment variables from botdetails.env ---
load_dotenv("botdetails.env")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")

if not TOKEN:
    raise ValueError("❌ DISCORD_BOT_TOKEN is missing in botdetails.env")
if not FOLDER_ID:
    raise ValueError("❌ DRIVE_FOLDER_ID is missing in botdetails.env")

# --- Discord Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize Google Drive Manager
drive_manager = GoogleDriveManager()


@bot.event
async def on_ready():
    print(f"✅ Logged in successfully as {bot.user.name}!")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    print(f"📩 [RAW MESSAGE] Author: {message.author} | Content: '{message.content}'")
    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    print(f"❌ [COMMAND ERROR] Triggered by '{ctx.message.content}': {error}", file=sys.stderr)
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
    await ctx.send(f"⚠️ An internal error occurred: `{error}`")


# --- Commands ---
@bot.command(name="join")
async def join(ctx, *, user_input: str = None):
    print("📥 !join command triggered")

    if not user_input:
        return await ctx.send("Please provide a track number or search term. Example: `!join 1` or `!join rock`")

    # Fixed: check the actual Drive service, not the truthy manager object
    if not drive_manager.service:
        return await ctx.send(
            "Google Drive system is misconfigured. Check credentials.json / GOOGLE_CREDENTIALS_JSON."
        )

    # Voice channel connection
    if not ctx.voice_client:
        if ctx.author.voice:
            print(f"Connecting to channel: {ctx.author.voice.channel.name}")
            await ctx.author.voice.channel.connect()
        else:
            return await ctx.send("You need to be in a voice channel so I know where to join!")
    else:
        if ctx.author.voice and ctx.voice_client.channel != ctx.author.voice.channel:
            await ctx.voice_client.move_to(ctx.author.voice.channel)

    # Search for files
    files = drive_manager.list_audio_files(FOLDER_ID)
    if not files:
        return await ctx.send("The Google Drive music folder is empty.")

    target_file = None

    if user_input.isdigit():
        track_number = int(user_input)
        if 1 <= track_number <= len(files):
            target_file = files[track_number - 1]
        else:
            return await ctx.send(f"Invalid track number. Choose 1 to {len(files)}.")
    else:
        query = user_input.lower().strip()
        # Fixed: plain substring match so "track" matches "track1.mp3"
        matches = [f for f in files if query in f['name'].lower()]

        if not matches:
            return await ctx.send(f"🔍 No tracks found matching: `{user_input}`.")
        elif len(matches) == 1:
            target_file = matches[0]
        else:
            response = f"🔍 Multiple matches found for `{user_input}`. Choose a track number:\n\n"
            for f in matches:
                orig_index = files.index(f) + 1
                response += f"**[{orig_index}]** {f['name']}\n"
            return await ctx.send(response)

    await ctx.send(f"Processing: `{target_file['name']}`...")

    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()

    # Download and Play
    # Fixed: use get_running_loop() since we're already inside a running loop
    loop = asyncio.get_running_loop()
    local_path, success = await loop.run_in_executor(
        None, drive_manager.get_or_download_track, target_file['id'], target_file['name']
    )

    if success and local_path:
        try:
            audio_source = discord.FFmpegPCMAudio(local_path)
            ctx.voice_client.play(
                audio_source, after=lambda e: print(f"Finished playing. Errors: {e}")
            )
            await ctx.send(f"🎶 Now playing: `{target_file['name']}`")
        except Exception as e:
            await ctx.send(f"Failed to play audio stream via FFmpeg: {e}")
    else:
        await ctx.send("Could not retrieve track from Google Drive.")


@bot.command(name="leave")
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from the voice channel.")
    else:
        await ctx.send("I am not currently in a voice channel.")


# --- Web Server Setup ---
web_app = Quart(__name__)


@web_app.route('/')
async def home():
    return "Bot is alive and running!"


async def main():
    port = int(os.getenv("PORT", 10000))
    loop = asyncio.get_running_loop()

    loop.create_task(web_app.run_task(host="0.0.0.0", port=port))

    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot application terminated locally.")