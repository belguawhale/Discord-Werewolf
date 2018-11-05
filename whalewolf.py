import traceback

import discord

from src.bot import WerewolfBot

try:
    import config
except ImportError:
    print('Error: No config.py file. Please make sure you rename config.py.example and fill out the fields.')
    exit(1)
bot = WerewolfBot(config)

try:
    bot.run()
except discord.LoginFailure:
    traceback.print_exc()
    exit(1)
except KeyboardInterrupt:
    exit(2)
else:
    if bot.restart:
        exit(16)
