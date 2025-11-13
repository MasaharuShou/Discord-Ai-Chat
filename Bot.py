import discord
from discord.ext import commands
import openai
import os
import json
from datetime import datetime
import aiohttp
from PIL import Image
import io
import PyPDF2

# Load environment variables
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '0'))  # Specific channel ID

openai.api_key = OPENAI_API_KEY

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Chat history storage (use database for production)
chat_histories = {}

def load_history():
    global chat_histories
    try:
        with open('chat_history.json', 'r') as f:
            chat_histories = json.load(f)
    except FileNotFoundError:
        chat_histories = {}

def save_history():
    with open('chat_history.json', 'w') as f:
        json.dump(chat_histories, f, indent=2)

@bot.event
async def on_ready():
    load_history()
    print(f'{bot.user} is online and ready!')
    print(f'Monitoring channel ID: {CHANNEL_ID}')

@bot.event
async def on_message(message):
    # Ignore bot's own messages
    if message.author == bot.user:
        return
    
    # Only respond in specific channel (or all channels if CHANNEL_ID is 0)
    if CHANNEL_ID != 0 and message.channel.id != CHANNEL_ID:
        return
    
    # Initialize user history
    user_id = str(message.author.id)
    if user_id not in chat_histories:
        chat_histories[user_id] = []
    
    # Process the message
    async with message.channel.typing():
        try:
            # Build conversation context
            messages = [
                {"role": "system", "content": "You are a helpful Discord bot assistant. You can view images and read files. Be friendly and concise."}
            ]
            
            # Add chat history (last 10 messages)
            for hist in chat_histories[user_id][-10:]:
                messages.append({"role": "user", "content": hist["user"]})
                messages.append({"role": "assistant", "content": hist["bot"]})
            
            # Current message content
            current_content = []
            current_content.append({"type": "text", "text": message.content or "No text provided"})
            
            # Handle image attachments
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    current_content.append({
                        "type": "image_url",
                        "image_url": {"url": attachment.url}
                    })
                    
                # Handle text files
                elif attachment.filename.endswith(('.txt', '.py', '.js', '.html', '.css', '.json')):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(attachment.url) as resp:
                            file_content = await resp.text()
                            current_content.append({
                                "type": "text",
                                "text": f"\n\n[File: {attachment.filename}]\n{file_content[:2000]}"
                            })
                
                # Handle PDF files
                elif attachment.filename.endswith('.pdf'):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(attachment.url) as resp:
                            pdf_data = await resp.read()
                            pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_data))
                            pdf_text = ""
                            for page in pdf_reader.pages[:5]:  # First 5 pages
                                pdf_text += page.extract_text()
                            current_content.append({
                                "type": "text",
                                "text": f"\n\n[PDF: {attachment.filename}]\n{pdf_text[:2000]}"
                            })
            
            messages.append({"role": "user", "content": current_content})
            
            # Call OpenAI API
            response = openai.chat.completions.create(
                model="gpt-4-vision-preview" if any(c.get("type") == "image_url" for c in current_content) else "gpt-4-turbo-preview",
                messages=messages,
                max_tokens=1000
            )
            
            bot_response = response.choices[0].message.content
            
            # Save to history
            chat_histories[user_id].append({
                "timestamp": datetime.now().isoformat(),
                "user": message.content or "[Image/File]",
                "bot": bot_response
            })
            save_history()
            
            # Send response (split if too long)
            if len(bot_response) > 2000:
                chunks = [bot_response[i:i+2000] for i in range(0, len(bot_response), 2000)]
                for chunk in chunks:
                    await message.reply(chunk)
            else:
                await message.reply(bot_response)
                
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
            print(f"Error: {e}")
    
    await bot.process_commands(message)

# Optional: Clear history command
@bot.command()
async def clearhistory(ctx):
    user_id = str(ctx.author.id)
    if user_id in chat_histories:
        chat_histories[user_id] = []
        save_history()
        await ctx.send("✅ Your chat history has been cleared!")
    else:
        await ctx.send("You don't have any chat history yet!")

bot.run(DISCORD_TOKEN)
