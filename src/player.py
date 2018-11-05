from .roles import role


class Player:
    def __init__(self, bot, id, role):
        self.bot = bot
        self.id = id  # player id
        self._roles = [role]  # list of all roles player had
        self._name = None
        self._nickname = None
        self._discriminator = None

    @property
    def role(self):
        return self._roles[-1]  # most recent role

    @property
    def orig_role(self):
        return self._roles[0]  # original role

    @property
    def name(self):
        return self._name or f'player with id {self.id}'

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def nickname(self):
        return self._nickname or self.name

    @nickname.setter
    def nickname(self, value):
        self._nickname = value

    @property
    def discriminator(self):
        return self._discriminator or '0000'

    @discriminator.setter
    def discriminator(self, value):
        self._discriminator = value
