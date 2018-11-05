import importlib
import os
import sys
import traceback
from datetime import datetime
import asyncio
import discord
from discord.ext import commands

class WerewolfBot(commands.Bot):
    @staticmethod
    def __prefix(bot: commands.Bot, message: discord.Message):
        prefixes = [bot.config.BOT_PREFIX]
        if not message.guild:
            prefixes.append('') # can just say the command "kill player"
        return prefixes

    @property
    def invite_url(self):
        return discord.utils.oauth_url(
            self._app_info.id if self._app_info else '<insert bot client id>',
            268536848)

    def __init__(self, config, *args, **kwargs):
        self.config = config
        self.restart = kwargs.get('restart', False)
        self._app_info = None
        self.uptime = None
        self.WEREWOLF_SERVER = None
        self.GAME_CHANNEL = None
        self.DEBUG_CHANNEL = None
        self.ADMIN_ROLE = None
        self.PLAYERS_ROLE = None

        super().__init__(self.__prefix)
        extensions = self.get_extensions()
        for extension in extensions:
            self.load_extension(extension)
        print(f'Loaded {", ".join(extensions)}')
        print('Done init')

    async def on_ready(self):
        print('on_ready triggered!')
        if self.uptime is None:
            await self.async_init()
        print('Done on_ready!')
    
    async def async_init(self):
        print('Starting async init')
        self.uptime = datetime.now()
        self._app_info = await self.application_info()
        self.WEREWOLF_SERVER = self.get_guild(self.config.WEREWOLF_SERVER_ID)
        if not self.WEREWOLF_SERVER:
            await self.shutdown(f'Error: could not find guild with id {self.config.WEREWOLF_SERVER_ID}. '
                                f'Perhaps you forgot to invite the bot?\n{self.invite_url}')
        self.GAME_CHANNEL = self.WEREWOLF_SERVER.get_channel(self.config.GAME_CHANNEL_ID)
        self.DEBUG_CHANNEL = self.WEREWOLF_SERVER.get_channel(self.config.DEBUG_CHANNEL_ID)
        self.ADMINS_ROLE = self.WEREWOLF_SERVER.get_role(self.config.ADMINS_ROLE_ID)
        self.PLAYERS_ROLE = self.WEREWOLF_SERVER.get_role(self.config.PLAYERS_ROLE_ID)
        required_fields = ('GAME_CHANNEL', 'DEBUG_CHANNEL', 'ADMINS_ROLE', 'PLAYERS_ROLE')
        #TODO: prompt for the fields instead?
        for field in required_fields:
            if not getattr(self, field):
                await self.shutdown(f'Error: could not find {field}. '
                                    f'Please double-check {field}_ID in config.py.')

    def get_extensions(self):
        # change cogs/cogname.py to cogs.cogname
        cog_files = [f'cogs.{cog[:-3]}' for cog in os.listdir('cogs') if cog.endswith('.py') and not cog == '__init__.py']
        # TODO: role commands
        return cog_files

    def reload_extension(self, name):
        extension = self.extensions.get(name)
        if not extension:
            return
        importlib.reload(extension)
        self.unload_extension(name)
        self.load_extension(name)
    
    async def on_message(self, message):
        await super().on_message(message)
    
    def run(self):
        super().run(self.config.TOKEN)
    
    async def shutdown(self, reason='', restart=False):
        print(f'Shutting down due to {reason}')
        self.restart = restart
        await super().logout()

    async def on_command_error(self, ctx, error): 
        '''The event triggered when an error is raised while invoking a command. 
        ctx   : Context 
        error : Exception'''

        # This prevents any commands with local handlers being handled here in on_command_error. 
        if hasattr(ctx.command, 'on_error'): 
            return 
        
        ignored = (commands.CommandNotFound,)
        no_print = (commands.UserInputError,)
        
        # Allows us to check for original exceptions raised and sent to CommandInvokeError. 
        # If nothing is found. We keep the exception passed to on_command_error. 
        error = getattr(error, 'original', error) 
        
        # Anything in ignored will return and prevent anything happening. 
        if isinstance(error, ignored): 
            return 

        elif isinstance(error, commands.DisabledCommand): 
            return await ctx.send(f'{ctx.command.qualified_name} has been disabled.') 

        elif isinstance(error, commands.NoPrivateMessage): 
            try: 
                return await ctx.author.send(f'{ctx.command.qualified_name} can not be used in Private Messages.') 
            except: 
                pass 

        # All other errors not returned come here... And we can just print the default traceback. 
        if not isinstance(error, no_print):
            print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr) 
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        await ctx.send(f'`{error.__class__.__name__}: {error}`')