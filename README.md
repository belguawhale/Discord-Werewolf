# Discord Werewolf
Discord Werewolf is a bot that runs the game Werewolf (Mafia) on Discord. It is written in Python using discord.py. You can find me on Discord as belungawhale#4813.

## Setting the bot up
Clone this repository and fill in the fields inside config.py. To change some settings, edit settings.py.

## Running the bot
You must first create a new bot account at https://discordapp.com/developers/applications/me. Put the bot's token inside config.py. If you are running on Windows, run `python bot.py` or double-click run.bat to launch the auto-restarter (it will restart the bot if it crashes for whatever reason). If you are running on a UNIX-based system, run either `python3 bot.py` or `python3.5 bot.py`.

## Changelog

1/18/2017 - Added !totem command to list totems/display a totem's description

1/17/2017 - Redid how votes are counted in preparation for impatience and pacifism totems; Impatience and pacifism totems work :smile:; Fixed a small bug with checking win condition in preparation for crazed shaman

1/16/2017 - Added !refresh command to sync language files with github

1/15/2017 - Lynch messages are taken from language file, as they should be; Made higher player games more fun (and hopefully somewhat balanced)

1/14/2017 - Added support for languages; bot changes status depending on what state the game is (no lobby is Online, join phase is Idle, in game is Do Not Disturb); Spectators can now use !v in pm to view current votes

1/13/2017 - Fixed game start timeout not working

1/11/2017 - Fixed idlewolf not causing traitor to turn

1/10/2017 - You can now use !v in pm; Village can now abstain from voting using !abstain (!abs and !nl are aliases); !v has more information; Added support for gamemodes :wink:; Revealroles now shows alive/dead people; Fixed a stupid off-by-one error with joining

1/8/2017 - Added number of players to !join, !leave; Fixed a bug where traitor would not appear in endgame stats and redid endgame stats; All stats (!stats, endgame) have a consistent ordering now; Fixed a stupid bug that caused win messages to error; Fixed a bug where new player count would show after !fleave during a game

1/5/2017 - Fixed dead players' votes displaying; Fixed a major bug with stats in games without traitor; Admins can use !force and !frole but only in channel

1/3/2017 - Massive update! Fixed a minor bug where dead wolfteam players would still receive wolfchat; Fixed a minor grammar problem in death totem's message; Influence totem is hidden from !v now; Fixed non-players using see, kill, etc. in pm causing an error; Re-did how roles are displayed from scratch; !stats has colours and is easier to see; Added harlot and traitor at 8p!!!; Added some filler stuff in for everything up to 16p; hopefully it's balanced

12/28/2016 - Added timeout before game start; Added a new !notify command to notify online users who have added themselves to the notify list. For backwards compatibility, the old !notify was renamed to !notify_role.

12/22/2016 - Fixed cursed villager being displayed on idle; Fixed a small visual bug with seeing/killing dead players; Added influence totem!

12/21/2016 - Fixed a bug with logging lynch (this is what happens when you copy paste)

12/20/2016 - Added messages for death and protection totems taking effect; Added a -force flag to !fstop to forcibly stop the game if !fstop gives an error; Added some more debug messages; Wolf can now retract kills; Fixed a bug where you could still join past MAX_PLAYERS

12/19/2016 - Fixed a stupid bug where trying to lynch using the middle of a nickname would try lynching that exact string, not the player; Added rate limiting users and the ability to ignore users; admins can use the !ignore command

12/17/2016 - Added a much-needed !info command; Added a !notify command to give or take the werewolf notify role; Fixed a bug where nicknames that started with capital letters couldn't be targeted; You can now target a player based on a string inside their username/nick (usernames take priority). E.g. if i want to kill belungawhale, i can say kill whale or kill gaw; Changed Available targets to Living players since it was confusing; Fixed a bug where wolf couldn't kill cultist

12/16/2016 - Fixed a bug where cultist could talk to wolf through wolfchat but not other way around (they shouldn't be able to communicate at all); Fixed a formatting bug with one of the lynch messages

12/15/2016 - Shaman has death, protection, and revealing totems. Cultist is a wolf team that counts as a villager for winning conditions but has no abilities; Added some !leave messages; display_name is now used instead of username; Fixed some hideous, hilarious, and stupid bugs like infinite totems with shaman, 2 players dying displays first player, revealing totems stay forever, players don't get their roles told to them, and cultist being told all wolf roles

12/14/2016 - Redid how kills were processed; Shaman's death and protection totems work; Fixed a small timing issue with !fstop; You are only told your role once now, on the first night. Use the command !myrole if you forgot.

12/13/2016 - Changed how templates work in preparation for future ones like gunner; Added !t as an alias for !time.

12/12/2016 - Fixed bot screwing up if a player blocks the bot; Fixed fleave outputting a number instead of a player's name; Fixed !myrole pming all players their role instead of just the person who used it

12/11/2016 - Added nick and discriminator support (order is mention/id, then username, then discrim, then nick); Restructured the bot's code to import config/settings from other files; Fixed a bug where dead players' votes still counted

12/8/2016 - Added !session command for debugging; Players, night, and day will time out now (players get 5 mins before a warning and 1 min before dying, night is 2 mins, day is 10 mins); Added !time command to check remaining time; End of night/day/game will display elapsed time

12/7/2016 - Players' ids now show up when displaying stuff like !stats; Seer and wolf get pm'd with a list of alive players and ids

12/6/2016 - Made random more random; Added cursed villager role (seer sees them as a wolf, but they don't know they are cursed.); Werewolves get a list of players still alive, noting cursed villagers as well and other wolf roles (in the future); Added some owner-only commands to speed up testing (so i won't screw up !exec anymore); Fixed a bug where no one could do anything night 2 (part of changing the !leave stuff)

12/5/2016 - Wolfchat now works, so wolves can coordinate; Added !fday, !night commands; End game message shows roles followed by winners, rather than the reverse; Renamed !players to !stats and added some info to it

12/4/2016 - Initial log. Only roles are villager, wolf, and seer. Game engine and stuff seems fine for now.; Hopefully fixed players leaving during a game; they spontaneously combust; Added !coin command for decision making; Changed some ordering to make it more fair (remove roles before announcing who was killed). Also unmutes channel before removing player roles so you don't get that weird glitch where you can't talk for a moment; Fixed a bug where anyone, specifically non-players, could start the game; Added !admins to list all admins and did some formatting edits; !admins now lists available admins only; Fixed a bug where trying to lynch a dead player would cause bot to error; Fixed a bug where an end game message would appear twice if !fstop was used

## Acknowledgements
This bot was inspired by lykos, an IRC werewolf bot that runs in freenode's ##werewolf channel.