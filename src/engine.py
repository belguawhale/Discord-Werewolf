from datetime import datetime, timedelta
from collections import OrderedDict
from enum import Enum, auto

class GameState(Enum):
    INIT = 'init'
    LOBBY = 'lobby'
    GAME_SETUP = 'game_setup'
    SUNSET = 'sunset' # day -> night transition
    NIGHT = 'night'
    SUNRISE = 'sunrise' # night -> day transition
    DAY = 'day'
    GAME_TEARDOWN = 'game_teardown'

class EventType(Enum):
    LOBBY_JOIN = 'lobby_join'
    LOBBY_LEAVE = 'lobby_leave'
    GAME_SETUP = 'game_setup'
    GAME_TEARDOWN = 'game_teardown'
    SUNSET_TRANSITION = 'sunset_transition'
    SUNRISE_TRANSITION = 'sunrise_transition'
    PLAYER_DEATH = 'player_death'
    PLAYER_IDLE = 'player_idle'
    PLAYER_LYNCH = 'player_lynch' # not to be confused by PLAYER_DEATH with DeathType LYNCH
    PLAYER_ABSTAIN = 'player_abstain'

class GameEngine:
    def __init__(self, bot):
        self.bot = bot
        self.setup()
         
    def setup(self):
        self.phase = GameState.INIT
        self.players = OrderedDict()
        self.night_start = datetime.now()
        self.night_elapsed = timedelta(0)
        self.nights = 0 # nights completed
        self.day_start = datetime.now()
        self.day_elapsed = timedelta(0)
        self.days = 0 # days completed
        self.phase = GameState.LOBBY
        self.gamemode = 'default'
        self.events = {}

    def teardown(self):
        self.phase = GameState.GAME_TEARDOWN
        # queue removing player roles
        self.players.clear()
        self.nights = 0
        self.days = 0
        # wait for player roles to be removed
        self.phase = GameState.LOBBY
    
    def start(self):
        self.phase = GameState.GAME_SETUP
        self.dispatch(EventType.GAME_SETUP, {'gamemode': self.gamemode})
    
    def add_event_listener(self, event_type: EventType, callback):
        # callback takes arguments (engine, event_type, data?)
        try:
            self.events[event_type].append(callback)
        except KeyError:
            self.events[event_type] = [callback]
        
    def dispatch(self, event_type, data):
        for callback in self.events[event_type]:
            callback(self, event_type, data)
    

class WinState(Enum):
    NO_WIN = auto()
    VILLAGE_WIN = auto()
    WOLF_WIN = auto()

class DeathType(Enum):
    WOLF_KILL = auto()
    LYNCH = auto()
    IDLE = auto()