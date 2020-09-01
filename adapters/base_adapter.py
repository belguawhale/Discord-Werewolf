class BaseAdapter:
    """Base class for the bot's external interface."""

    async def send_message(self, destination, message):
        """Sends a message to destination."""
        return NotImplemented

    async def get_user_destination(self, user_id):
        """Gets a destination for user_id that can be used in send_message"""
        return NotImplemented

    async def get_channel_destination(self, channel_id):
        """Gets a destination for channel_id that can be used in send_message"""
        return NotImplemented
    
    async def add_player_role(self, user_id):
        """Grants user_id Player role"""
        return NotImplemented
    
    async def remove_player_role(self, user_id):
        """Revokes user_id Player role"""
        return NotImplemented

    async def add_admin_role(self, user_id):
        """Grants user_id Admin role"""
        return NotImplemented
    
    async def remove_admin_role(self, user_id):
        """Revokes user_id Admin role"""
        return NotImplemented

    async def add_notify_role(self, user_id):
        """Grants user_id Werewolf Notify role"""
        return NotImplemented
    
    async def remove_notify_role(self, user_id):
        """Revokes user_id Werewolf Notify role"""
        return NotImplemented
    
    async def is_lobby_locked(self):
        """Returns the lock status of the lobby"""
        return NotImplemented

    async def lock_lobby(self):
        """Only allow alive players to chat"""
        return NotImplemented
    
    async def unlock_lobby(self):
        """Allow everyone to chat"""
        return NotImplemented

    async def log(self, loglevel, text):
        """Logs text with level loglevel"""
        return NotImplemented

    async def send_lobby(self, text):
        """Sends text to the game lobby"""
        return NotImplemented

    async def set_lobby_status(self, status):
        """Sets status of the lobby, using constants.LobbyStatus"""
        return NotImplemented

    # Helper methods

    async def send_player(self, player_id, message):
        """Sends a message to player_id"""
        return await self.send_message(await self.get_user_destination(player_id), message)

    async def send_channel(self, channel_id, message):
        """Sends a message to channel_id"""
        return await self.send_message(await self.get_channel_destination(channel_id), message)
