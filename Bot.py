import discord
from discord.ext import commands
import google.generativeai as genai
import os
import json
from datetime import datetime
import aiohttp
from PIL import Image
import io
import PyPDF2

# Load environment variables
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '0'))  # Specific channel ID

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Chat history storage
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
            # Initialize Gemini model
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            
            # Build conversation history for context
            conversation_context = "You are a helpful Discord bot assistant. Be friendly and concise.\n\n"
            
            # Add last 10 messages from history
            for hist in chat_histories[user_id][-10:]:
                conversation_context += f"User: {hist['user']}\nBot: {hist['bot']}\n\n"
            
            # Prepare content parts for current message
            content_parts = []
            
            # Add text message
            if message.content:
                content_parts.append(conversation_context + f"User: {message.content}\nBot:")
            else:
                content_parts.append(conversation_context + "User: [Sent attachment(s)]\nBot:")
            
            # Handle attachments
            for attachment in message.attachments:
                # Handle images
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(attachment.url) as resp:
                            image_data = await resp.read()
                            img = Image.open(io.BytesIO(image_data))
                            content_parts.append(img)
                
                # Handle text files
                elif attachment.filename.endswith(('.txt', '.py', '.js', '.html', '.css', '.json')):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(attachment.url) as resp:
                            file_content = await resp.text()
                            content_parts[0] += f"\n\n[File: {attachment.filename}]\n{file_content[:3000]}"
                
                # Handle PDF files
                elif attachment.filename.endswith('.pdf'):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(attachment.url) as resp:
                            pdf_data = await resp.read()
                            pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_data))
                            pdf_text = ""
                            for page in pdf_reader.pages[:5]:  # First 5 pages
                                pdf_text += page.extract_text()
                            content_parts[0] += f"\n\n[PDF: {attachment.filename}]\n{pdf_text[:3000]}"
            
            # Generate response from Gemini
            response = model.generate_content(content_parts)
            bot_response = response.text
            
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
