from . import BaseAdapter

import discord
import traceback
from datetime import datetime

from constants import LobbyStatus

class DiscordAsyncAdapter(BaseAdapter):
    """Adapter for async branch of discord.py."""

    MAX_MESSAGE_LEN = 2000

    def __init__(self, client, config):
        self.client = client
        self.config = config
        self.initialized = False

        # discord.py objects
        self.WEREWOLF_SERVER = None
        self.PLAYERS_ROLE = None
        self.ADMINS_ROLE = None
        self.WEREWOLF_NOTIFY_ROLE = None
        self.GAME_CHANNEL = None
        self.DEBUG_CHANNEL = None
        self.BOT_NAME = None

    async def async_init(self):
        """This should run before anything else."""
        await self.set_lobby_status(LobbyStatus.READY)
        if self.initialized:
            return
        self.initialized = True
        self.WEREWOLF_SERVER = self.client.get_server(self.config.WEREWOLF_SERVER)
        self.GAME_CHANNEL = self.client.get_channel(self.config.GAME_CHANNEL)
        self.DEBUG_CHANNEL = self.client.get_channel(self.config.DEBUG_CHANNEL)
        self.BOT_NAME = self.client.user.display_name

        for role in self.WEREWOLF_SERVER.role_hierarchy:
            if role.name == self.config.PLAYERS_ROLE_NAME:
                self.PLAYERS_ROLE = role
            if role.name == self.config.ADMINS_ROLE_NAME:
                self.ADMINS_ROLE = role
            if role.name == self.config.WEREWOLF_NOTIFY_ROLE_NAME:
                self.WEREWOLF_NOTIFY_ROLE = role
        if self.PLAYERS_ROLE:
            await self.log(0, "Players role id: " + self.PLAYERS_ROLE.id)
        else:
            await self.log(3, "Could not find players role " + self.config.PLAYERS_ROLE_NAME)
        if self.ADMINS_ROLE:
            await self.log(0, "Admins role id: " + self.ADMINS_ROLE.id)
        else:
            await self.log(3, "Could not find admins role " + self.config.ADMINS_ROLE_NAME)
        if self.WEREWOLF_NOTIFY_ROLE:
            await self.log(0, "Werewolf Notify role id: " + self.WEREWOLF_NOTIFY_ROLE.id)
        else:
            await self.log(2, "Could not find Werewolf Notify role " + self.config.WEREWOLF_NOTIFY_ROLE_NAME)
        sync_players = False
        sync_lobby = False
        for member in self.WEREWOLF_SERVER.members:
            if self.PLAYERS_ROLE in member.roles:
                if not sync_players:
                    await self.send_lobby("{}, the bot has restarted, so the game has been cancelled. Type `{}join` to start a new game.".format(
                        self.PLAYERS_ROLE.mention, self.config.BOT_PREFIX))
                    sync_players = True
                await self.remove_player_role(member.id)
        if await self.is_lobby_locked():
            await self.unlock_lobby()
            sync_lobby = True
        if sync_players or sync_lobby:
            await self.log(2, "SYNCED UPON BOT RESTART")


    async def send_message(self, destination, message):
        """Sends a message to destination."""
        if destination:
            return await self.client.send_message(destination, message)

    async def get_user_destination(self, user_id):
        """Gets a destination for user_id that can be used in send_message"""
        return self.WEREWOLF_SERVER.get_member(user_id)

    async def get_channel_destination(self, channel_id):
        """Gets a destination for channel_id that can be used in send_message"""
        return self.client.get_channel(channel_id)
    
    async def wait_for_message(self, author=None, channel=None, timeout=None, check=None):
        """Waits for a message satisfying the requirements, and either returns it or None if it times out"""
        return await self.client.wait_for_message(author=author, channel=channel, timeout=timeout, check=check)
    
    async def delete_message(self, message):
        """Deletes a message"""
        return await self.client.delete_message(message)

    async def add_player_role(self, user_id):
        """Grants user_id Player role"""
        member = await self.get_user_destination(user_id)
        if member:
            await self.client.add_roles(member, self.PLAYERS_ROLE)
    
    async def remove_player_role(self, user_id):
        """Revokes user_id Player role"""
        member = await self.get_user_destination(user_id)
        if member:
            await self.client.remove_roles(member, self.PLAYERS_ROLE)

    async def has_player_role(self, user_id):
        """Returns whether user_id has the Player role"""
        member = await self.get_user_destination(user_id)
        return member and self.PLAYERS_ROLE in member.roles

    async def add_admin_role(self, user_id):
        """Grants user_id Admin role"""
        member = await self.get_user_destination(user_id)
        if member:
            await self.client.add_roles(member, self.ADMINS_ROLE)
    
    async def remove_admin_role(self, user_id):
        """Revokes user_id Admin role"""
        member = await self.get_user_destination(user_id)
        if member:
            await self.client.remove_roles(member, self.ADMINS_ROLE)

    async def add_notify_role(self, user_id):
        """Grants user_id Werewolf Notify role"""
        member = await self.get_user_destination(user_id)
        if member:
            await self.client.add_roles(member, self.WEREWOLF_NOTIFY_ROLE)
    
    async def remove_notify_role(self, user_id):
        """Revokes user_id Werewolf Notify role"""
        member = await self.get_user_destination(user_id)
        if member:
            await self.client.remove_roles(member, self.WEREWOLF_NOTIFY_ROLE)

    async def is_lobby_locked(self):
        """Returns the lock status of the lobby"""
        perms = self.GAME_CHANNEL.overwrites_for(self.WEREWOLF_SERVER.default_role)
        # @everyone cannot chat
        return not perms.send_messages

    async def lock_lobby(self):
        """Only allow alive players to chat"""
        perms = self.GAME_CHANNEL.overwrites_for(self.WEREWOLF_SERVER.default_role)
        perms.send_messages = False
        await self.client.edit_channel_permissions(self.GAME_CHANNEL, self.WEREWOLF_SERVER.default_role, perms)
    
    async def unlock_lobby(self):
        """Allow everyone to chat"""
        perms = self.GAME_CHANNEL.overwrites_for(self.WEREWOLF_SERVER.default_role)
        perms.send_messages = True
        await self.client.edit_channel_permissions(self.GAME_CHANNEL, self.WEREWOLF_SERVER.default_role, perms)

    async def log(self, loglevel, text):
        # loglevels
        # 0 = DEBUG
        # 1 = INFO
        # 2 = WARNING
        # 3 = ERROR
        levelmsg = {0 : '[DEBUG] ',
                    1 : '[INFO] ',
                    2 : '**[WARNING]** ',
                    3 : '**[ERROR]** <@' + self.config.OWNER_ID + '> '
                    }
        logmsg = levelmsg[loglevel] + str(text)
        with open(self.config.LOG_FILE, 'a', encoding='utf-8') as f:
            f.write("[{}] {}\n".format(datetime.now(), logmsg))
        if loglevel >= self.config.MIN_LOG_LEVEL:
            await self._send_log(logmsg)

    async def _send_log(self, logmsg, depth=0):
        """Handles sending the debug log"""
        max_len = self.MAX_MESSAGE_LEN - 50  # Some breathing room for security
        if len(logmsg) <= max_len:
            if depth:
                await self.send_message(self.DEBUG_CHANNEL, "[CONTINUED] " + "```py\n" + logmsg[:max_len])
            else:
                await self.send_message(self.DEBUG_CHANNEL, logmsg)
                return
        else:
            if depth:
                await self.send_message(self.DEBUG_CHANNEL, "[CONTINUED] " + "```py\n" + post[:max_len] + "```")
            else:
                await self.send_message(self.DEBUG_CHANNEL, logmsg[:max_len] + "```")
            await self._send_log(logmsg[max_len:], depth + 1)

    async def send_lobby(self, text):
        for i in range(3):
            try:
                return await self._send_long_post(self.GAME_CHANNEL, text)
            except:
                await self.log(3, "Error in sending message `{}` to lobby: ```py\n{}\n```".format(
                    text, traceback.format_exc()))
                await asyncio.sleep(5)
        else:
            await self.log(3, "Unable to send message `{}` to lobby: ```py\n{}\n```".format(
                text, traceback.format_exc()))

    async def _send_long_post(self, channel, post):
        if len(post) <= self.MAX_MESSAGE_LEN:
            return await self.send_message(channel, post)
        else:
            await self.send_message(channel, post[:self.MAX_MESSAGE_LEN])
            await self._send_long_post(channel, post[self.MAX_MESSAGE_LEN:])

    async def set_lobby_status(self, status):
        """Sets status of the lobby, using constants.LobbyStatus"""
        lobby_discord_status_mapping = {
            LobbyStatus.READY: discord.Status.online,
            LobbyStatus.WAITING_TO_START: discord.Status.idle,
            LobbyStatus.IN_GAME: discord.Status.dnd
        }
        discord_status = lobby_discord_status_mapping.get(status, discord.Status.online)
        await self.client.change_presence(status=discord_status, game=discord.Game(name=self.config.PLAYING_MESSAGE))

    async def send_user(self, user_id, message, Raise=False):
        """Sends a message to user_id"""
        try:
            return await self.send_message(await self.get_user_destination(user_id), message)
        except discord.Forbidden:
            if Raise:
                raise

    async def reply(self, message, text, cleanmessage=True, mentionauthor=False):
        """Sends a reply in the same channel as the message object"""
        if cleanmessage:
            text = text.replace('@', '@\u200b')
        if mentionauthor:
            text = "{0}, {1}".format(message.author.mention, text)
        return await self._send_long_post(message.channel, text)
