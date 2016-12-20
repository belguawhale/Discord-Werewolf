# Discord Werewolf
Discord Werewolf is a bot that runs the game Werewolf (Mafia) on Discord. It is written in Python using discord.py. You can find me on Discord as belungawhale#4813.

## Setting the bot up
Clone this repository and fill in the fields inside config.py. To change some settings, edit settings.py.

## Running the bot
You must first create a new bot account at https://discordapp.com/developers/applications/me. Put the bot's token inside config.py. If you are running on Windows, run `python bot.py` or double-click run.bat to launch the auto-restarter (it will restart the bot if it crashes for whatever reason). If you are running on a UNIX-based system, run either `python3 bot.py` or `python3.5 bot.py`.

## Changelog

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