import asyncio
import discord
from discord.ext import commands

class Meta:
    '''Cog for all bot-related stuff'''
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command()
    async def ping(self, ctx):
        await ctx.send('Pong!')

def setup(bot):
    bot.add_cog(Meta(bot))