# Discord Werewolf
Discord Werewolf is a bot that runs the game Werewolf (Mafia) on Discord. It is written in Python using discord.py. You can find me on Discord as belungawhale#4813.

## Setting the bot up
Install Python 3.5 or 3.6. The latest version of Python that works is 3.6.8, which can be installed from https://www.python.org/downloads/release/python-368/. If you are running on Windows, then be sure to check the box that will add Python to PATH.

Clone this repository. Rename `config.py.example` to `config.py` and `settings.py.example` to `settings.py`, and fill in the fields inside config.py. To change some gameplay-related settings, edit settings.py.

## Dependencies
Discord Werewolf has hard dependencies on discord.py and aiohttp. You can run `pip install -r requirements.txt` to install the required dependencies. Note that the bot uses an older version of discord.py, but with an additional fix to accommodate Discord's API update.

## Running the bot
You must first create a new bot account at https://discordapp.com/developers/applications/me. Put the bot's token inside config.py. Next, add the bot to your server using the OAuth2 link `https://discordapp.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot&permissions=8` for faster setup or `https://discordapp.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot&permissions=268536848` for finer tuning of permissions, replacing CLIENT_ID with the client id. If you are running on Windows, run `python bot.py` or double-click run.bat to launch the auto-restarter (it will restart the bot if it crashes for whatever reason). If you are running on a UNIX-based system, run either `python3 bot.py`, or `python3.5 bot.py` or `python3.6 bot.py`, depending on the version of Python that you are using.

## Changelog

11/29/2020 - Credits to Picowchew: Fixed misdirection and luck totems potentially misdirecting to the wrong player, including that the redirected target for misdirection totem potentially being adjacent to the command invoker as opposed to the original target; Fixed the player pool of redirected targets for misdirection and luck totems, and below are some key notes: {The player pool does not include players with the luck totem; Succubus cannot receive a harmful action if the command invoker is entranced; Succubus can be shot, though it will never die by gun, as per the usual mechanics; The player pool for shaman, crazed shaman, and wolf shaman does not include themselves nor succubus if they are entranced (regardless of their totems); The player pool for shaman, crazed shaman, wolf shaman, and guardian angel does not include the players that they targetted the previous night; The target will not be redirected if there are no \[other\] potential targets}; The check conditions for valid targets now all occur before the checks for misdirection and luck totems; Fixed an error from potentially occurring and fixed night potentially not ending, with the result being less kills than expected, when a wolf kills more than one player in a night and either the wolf is given a misdirection totem or one or more of the targets have a luck totem; Vengeful ghost's target can now be affected by misdirection and luck totems; Fixed game loop breaking if a vengeful ghost has the misdirection totem and idles out its night action; Serial killer's target can now be affected by misdirection totem; Fixed serial killer being told the redirected target instead of the original target when targetting someone with the luck totem; Fixed an error from occurring when a piper attempts to charm a player with the luck totem; If a piper passes and then attempts to charm, then it is now told that it has already chosen to not charm anyone tonight, as opposed to being told that it is already charming tonight; If a piper passes and then attempts to pass again, then there is now no response, as opposed to being told again that it has already chosen to not charm anyone tonight; If a piper idles out its night ability, then it is now told that it has chosen to not charm anyone tonight, as opposed to there being no response, and this pass is now logged; If a silenced piper passes and then attempts to charm, then it is now told that it has already chosen to not charm anyone tonight, as opposed to being told that it has been silenced; Fixed guardian angel targetting a dead player allowing it to then target the same person that it did the previous night; Fixed wolf shaman being able to give a totem to the same person on consecutive nights; Fixed wolf shaman being able to give a harmful totem to a succubus when it is entranced; Silenced wolf shaman is now told the totem that it would be able to give if it was not silenced; Crazed shaman's totem is now always logged, regardless of being silenced; Fixed shaman and crazed shaman being unable to give their harmful totems to another player if during the same night, they earlier gave their totems to a succubus and then the succubus entranced them; Entranced shaman, wolf shaman, and crazed shaman now cannot give their totems to a succubus when idling out their night actions, in case of giving harmful totems; Fixed entranced vengeful ghost and assassin potentially targetting a succubus when idling out their night actions; Fixed idled out night actions of shaman, wolf shaman, crazed shaman, vengeful ghost, clone, and assassin potentially targetting a dead vengeful ghost; Fixed game loop breaking if shaman, wolf shaman, crazed shaman, vengeful ghost, or assassin idle out their night actions without any available targets, now resorting to targetting a player with a luck totem, and for the different shaman types, afterwards resorting to targetting the same player as the previous night; Fixed night certainly having to last its full length (and then game loop breaking) if a vengeful ghost has no available targets; If a vengeful ghost does not have any available targets and tries to kill someone, then it is now told like so; If a vengeful ghost attempts to kill itself, then it is now told that suicide is bad, as opposed to there being no response; Fixed amnesiac such that it now abides to its win conditions; Fixed game loop breaking if an amnesiac blocks the bot and is lynched with a revealing totem; Fixed succubus dying by sharpshooter; The logging for serial killer's night action is now similar to that of wolf; Fixed game loop sometimes breaking if more than two players die in a single night in the noreveal game mode; Fixed an error from occurring when a hag invokes the hex command without any parameters; Fixed an error from occurring when the async command is invoked without any parameters; Fixed `basic` appearing in vengeful ghost's living players list when it does not have any available targets; Fixed `diff` appearing in the revealroles command when there are no players in the game; Fixed message formatting of the stats command when there is no active game; Fixed message formatting of the join command when the command invoker has stasis; A bit of code cleanup

08/31/2020 - Thank you, Picowchew: The bot now automatically syncs upon restart

08/30/2020 - Once again, credits to Picowchew: Users with stasis now cannot notify others with the notify command; The notify command now has a server-wide cooldown, defaulting to three minutes; The notify command now does not ping the user in the list of pings; Fixed night actions potentially showing when the votes command is executed during the night to day transition; If it is night and wolf is targetting someone, then fstop and fstop -force now do not give an error anymore; fstop -force when there is no game now gives the message that there is no currently running game; Executioner that turned into a jester now shows as executioner (instead of jester) in stats and shows as jester in end game stats (instead of executioner); The bot now always says "No one wins" in the end game message if the game ends with no winners; Fixed there being two abstain messages when the village abstains in the mudkip game mode; Harlot's death message does not show anymore if it is protected by guardian angel and visits a wolf; Bodyguard's death message does not show anymore if it is given a protection totem and guards the wolf's victim; A matched hot potato swapping with its lover now cannot result in one or both lovers loving themselves; Fixed game loop breaking if a priest who hasn't blessed yet is cloned; Fixed how executioner is cloned; Clone and hot potato are now given their new role information upon becoming a different role; Fixed hot potato that swaps with minion not receiving the wolf list; Fixed clone that turns into a minion after the first night not receiving the wolf list; Fixed minion's myrole command after the first night not giving the wolf list; Clone is now given the living players list on the first night and its myrole command now works as it should; Assassin is now not repeatedly told its target on nights after the first; Fixed executioner not possibly being given template-related messages on nights after the first; Executioner that turned into jester due to its target dying not via lynch is now sent the role information of jester; Fixed some potential message duplication being sent to executioner; Gunner and sharpshooter are now not told anymore that they have a gun with 0 bullets at night, unless the player receives a gun for the first time in the belunga game mode; In the belunga game mode, a player now cannot have more than one gunner template; A bit of code cleanup

07/28/2020 - Thanks to Picowchew again: Fixed wolf cub dying at night not giving wolf team an additional kill the next night; Night now does not end until werecrow has observed; Vengeful ghost now receives a message if it mistypes a player’s name; Monster now has a higher winning priority over serial killer; Templates now appear in stats in roles game mode

06/27/2020 - Credits to Picowchew: Added bishop template; Rebalanced default game mode at higher player count; Made some changes to the random game mode (Slightly reduced the maximum ratio of wolves to total players; Slightly reduced the chances of being cursed and the chances of being gunner; There is now the possibility of being assigned assassin, mayor, and/or blessed villager at the beginning of the game); Blessed villager now appears in end game stats; Death by doomsayer's see is now set to be a kill by wolf team instead of village team; Serial killer's retract does not appear in wolf chat anymore; Bodyguard now protects against serial killer's kill; Silenced shaman is now told the totem that it would be able to give if it was not silenced; Vengeful ghost now receives a message if it is consecrated and tries to kill; The death messages of the entranced when all succubi die are now in one sentence; Edited turncoat's description to include that it can pass; Fixed {p} appearing instead of prefix when trying to start the game without joining; Fixed ! always appearing, regardless of prefix, when game start reaches timeout; Fixed some message formatting regarding the hot potato, succubus, and bodyguard roles as well as the !notify command

05/03/2020 - Thank afands for fixing ! always appearing, regardless of prefix, when trying to start the game without joining

05/02/2020 - Special thanks to Xinverse: Messages containing more characters than Discord’s message size limit will be recursively broken down into shorter messages; 23+ players joining will no longer result in game loop breaking; Abstaining in mudkip while double lynching will no longer result in game loop breaking; Bot’s playing status now displays correctly after triggering the on_ready event

04/26/2020 - Credits to Picowchew: Fixed member id appearing in the leave message instead of member name for the automated inserver; Clarified priest description regarding consecration

04/18/2020 - Thanks to Picowchew: The buggy !inserver command is now removed, its features are fixed and automated, and leaving the server in game now additionally gives QUIT_GAME_STASIS stasis; If the !fleave command is used before a game starts, bringing player count to 0, then the bot now appears online instead of idle

11/30/2019 - Credits to Picowchew: Additions: Serial killer role; Executioner role; Hot potato role; Bloodbath game mode, which includes the serial killer role; The command !inserver force leaves players who leave the server before or during a game, regardless of whether they rejoin; Some more turncoat siding aliases; Crazy game mode now has a different role set; Fixes: Shamans could give their totem to the same person two nights in a row if they let their totem random; If a wolf was silenced, then night had to last 2:00; Having the influence totem doubled the player's abstain vote; An error occurred when hunter attempted to kill a non-existing player; Priest could not start out cursed; Bodyguard could not protect against vengeful ghost kill; Wolf mystic could not detect win-stealing roles; Player count when players tried to join a game soon after a game finished; Message order of gunner-revenge; Description of luck totem; Some of the formatting of assassin's messages; The command !fstop -force broke under a certain condition

11/25/2018 - Huge update - all thanks to Poke: Made role and gamemode lists nicer; Fixed a couple current lycanthropy bugs and separated doomsayer and totem lycans; Made piper give full charmed list each night; Bug fixing; Fixed some bodyguard bugs; Fixed werecrow not seeing some roles; Fixed kill teams a little; Amnesiac turning when dead; Default mode roles changed; Chaos mode roles changed; Drunkfire and orgy changed minorly; Gave belunga, evilvillage, and valentines higher maximum player counts; Revamped gamemode choosing to that of lykos; Added mad scientist, clone, lycan, time lord, turncoat roles; Added mad, lycan, rapidfire, noreveal, aleatoire modes

8/25/2018 - Charming update - all credits to imad: Fixed succubus unlimited entrance; Fixed amnesiac winning if dead even when villagers lose; Fixed amnesiac turning into an amnesiac; Lycanthropes are now hidden in !stats; Shamans (including wolf shamans and cs) can no longer give totems twice to same person in a row; Fixed doomsayer charging up dooms and basically destroy anyone if patient; vg is no longer guaranteed a win if they die of gun suicide, instead they are guaranteed defeat; !roles default table and other role tables no longer cause errors and just ignore the command if they were to break; vengeful ghost can no longer use the kill command while alive; Added charming gamemode and the warlock, bodyguard, piper roles

8/16/2018 - Fixed a game-breaking bug of wolf not being able to kill

8/15/2018 - Thank Poke and imad for fixing mudkip abstain and various other things; Fixed game crashing at high player counts

5/19/2018 - Fixed some bugs such as succubus crashing the game and various miscellaneous stuff

2/14/2018 - Valentines update! Added valentines, mudkip, evilvillage gamemodes; Added jester, minion, doomsayer, wolf shaman, priest, amnesiac, vengeful ghost, succubus, monster roles; Added assassin, blessed, sharpshooter, mayor templates; Added misdirection, silence, luck, pestilence, desparation totems; Added Guardian Angel to Random and Template gamemodes; Added Wolf cub lobby message for when it grows up; Added more in-depth role and totem explanations.; Upped player count from 20 to 23 for the Default gamemode and up to 24 for the Foolish gamemode; Thanks to imad and Pyro!

11/25/2017 - Anniversary update! Reduced wait on join to 15 seconds; Finally prevented shaman from giving totem to same player twice in a row; Added Guardian Angel role; Added GA to gamemodes

10/26/2017 - I'm alive!!!; Fixed a bug where game loop would break if there were no retribution targets; Fixed augur being affected by deceit totem; Fixed wolf cub being the only wolf that could kill in random; Fixed blinding totem not working; Fixed retribution totem not working with multiple wolf kills; Fixed cs lovers being duplicated in the winners list

8/28/2017 - Matchmaker role (thanks to imad!); Fixed some bugs and streamlined cmd_choose and end of game stats; Fixed role order with matchmaker; Replaced shaman in orgy gamemode with matchmaker; Added valentines gamemode; Fixed a bug where matchmaker would be automatically forced to end night

8/7/2017 - Fixed using commands before bot is ready; Added grace period before join start and !wait command; Fixed mentions being broken

7/19/2017 - Added error checking in role attribution to reduce reliance on admins; Made the game loop stronger and self-restarting; Added error checking to sending message in lobby; Added oracle and augur roles; Added oracle and augur to gamemodes

6/26/2017 - Fixed a bug where virtually no one would be notified; Detective reveal now gives you the id of the detective due to issues before -_-; Fixed a bug where game cancel would screw up session

6/26/2017 - **WOLF CUB UPDATE!** !frevive command now logs in debug logs; Fixed a bug where blinding totem would stay on dead players; Implemented angry status and added the related message in preparation for wolf cub; Stasised players will not be notified by !notify; Werekitten cannot be cursed; Changed format of living players in dm to be more readable (the old one was a huge blob of text at higher player counts, unreadable especially for wolfteam); Night only ends if all wolves choose the same targets now. If night times out, random targets are chosen; Added support for multiple kills (in preparation for wolf cub); Added wolf cub grow up condition (wolf cub grows up before traitor turn); Added confirmation before doing !quit; Added wolf cub death assigning angry condition (if wolf cub dies for any reason other than idling out/leaving during game, wolves get two kills the following night); Reworked kill command to support killing multiple targets; Added wolf cub to gamemodes

6/3/2017 - Fixed a bug that made lycan activate on the night it was given rather than the night after; Fixed a bug where an injured player could still use the abstain command

5/30/2017 - Fixed a bug where shooting werekitten would be counted as shooting a wolf; Optimized the code for that

5/29/2017 - MASSIVE UPDATE! Added sorcerer role; Added !rr alias for !revealroles; Added !role list so you can get a list of all roles during a game; Stasis is now removed on game start rather than on game end; Made stasis amount given on using !q/idling out configurable; Made secondary idle timer configurable (after the "you are idling" message is sent); Fixed a bug where foolish was unplayable for player counts under 12; Language files are loaded locally first now; !refresh command will edit the actual language file now; Added the ability to change the Playing... status in config.py; Added the !async command, which is like a better version of eval and exec; Reverted speeding up game end since it was causing problems due to discord ratelimits; Fixed member leaving the server causing idling out to error; All players are mentioned on game start/end; Fixed village win condition so that if all wolves are dead, village wins (rather than when all wolfteam roles are dead); Added sorcerer to gamemodes, replacing werecrow in a bunch of them

5/18/2017 - Rebalanced default due to two 16p default games where wolves got destroyed; Sped up game end and fixed a bug where GAME_START_TIMEOUT would not activate due to a timing issue; Hopefully fixed the issue with reporting how long day and night took; Increased player cap to 20 for gamemodes default and foolish; Rebalanced gamemodes again

5/14/2017 - Added detective role; Added detective to gamemodes and rebalanced foolish

5/10/2017 - Fixed a bug where random role assignment could error if there were no cursed villager choices; Added deceit totem; Changed lycanthropy and deceit so they take effect on the night after they were given; Fixed a spelling error; Fixed an issue with gunner revenge where multiple gunner revenge deaths (possible with harlot) would only count the last one

5/1/2017 - Added random gamemode and gamemode descriptions; Made a common function to do autocompletion; Added autocompletion for role names and gamemodes; Added !game command to view information on gamemodes; Fixed a few minor bugs with gamemode minimum and maximum players

4/24/2017 - Fixed injured traitor and no other wolfteam ending the game in a villwin (injured mechanic should only apply to wolfwin); Fixed multiple gunner templates being applied to a wolf that kills multiple gunners; Any gunner death caused by wolf allows wolf to steal gun (harlot-gunner visiting wolf/victim), and wolf targeting gunner-harlot while they are visiting will not allow wolf to steal gun; Night deaths and a whole slew of more things are now sorted; Lycanthropy now works on harlot visiting wolf, harlot visiting victim; Added a new CS totem

4/7/2017 - Rebalanced default slightly; Disabled restrictions on voting for belunga mode; Added hunter; Added hunter to gamemodes

3/31/2017 - Added roles gamemode that allows you to select an arbitrary roleset using !fgame; Fixed sort_roles; Fixed up !fgame slightly; Fixed neutral roles having a gun; Fixed !stats in roles gamemode; Made session[7] contain a role dict of roles in the current game

3/29/2017 - Added werekitten and belungas; Added -fleave flag to !shutdown

3/24/2017 - Fixed a serious bug with influence totem attempting to lynch dead players; Fixed a minor bug with dead players with impatience totem still playing impatience message

3/23/2017 - Added werecrow and gunners to chaos (in chaos, anyone could be gunner); Added !frevive command for debugging purposes

3/21/2017 - Fixed a possible issue with abusing gunner mechanics; Fixed a serious issue with game ending on sunrise causing bot to error; Made the game loop its own function for debugging purposes; Fixed wolves stealing a lycan'd gunner's gun; Buffed !fjoin to allow ranges of fake players; All commands with lists of players are now sorted!

3/20/2017 - Fixed !stats; Fixed a minor timing issue with !fnight and day cycle of run_game

3/19/2017 - MASSIVE UPDATE! Slightly redid how gamemodes are stored and processed; Added !verifygamemode command to ensure gamemodes are valid; !role command can now return information on gamemodes other than default; Made a common function between !myrole and the initial role pms; Fixed !myrole; Re-did a small section on how commands are processed in preparation for more roles that share commands (e.g. oracle and seer would both use !see); Added gunner template; Added role guide and role table; Added injured mechanic to go with gunner; Fixed an annoying bug where traitor turn message would play after game was over; Rebalanced gamemodes to include gunner template

3/13/2017 - Spelling error smh; Fixed a game-breaking bug where retribution totem stays until end of game; Added more debugging info in case of an error; Fixed a bug where lycanthropy totem and death totem combined with protection and death would cause bot to error; Fixed a bug where no players alive would count as wolfwin

3/12/2017 - Fixed no wolfkill message being displayed when harlot was attacked; Fixed a bug where !retract would display a message even if there was no vote; Forgot to add permissions to the gamemodes command so re-added them; Minor fix to death totem messages so a wolfkill, prot, and death will result in just a wolfkill message; Added some *mysterious* totems

3/9/2017 - Added votes to start; Added voting for gamemodes; Hopefully squashed weird lynch messages after game end for good; Minor spelling fixes

3/3/2017 - I'm alive! Redid how commands are added to the bot to use a decorator instead of a huge dictionary :o; Minor change to printing errors in console; Redid how wins are calculated; Fixed a stupid bug that caused get_role on game end to screw up; CS win condition!!! :D; Weird lynch messages displaying after idle death should be fixed; Added !q as an alias for !leave

2/11/2017 - Fixed an encoding issue with writing to log; If everyone has an impatience totem, it randomly chooses a player to be lynched; Fixed a bug where cs was not strong enough to prevent night from ending; Fixed a bug where death of 2 or more players would display all except last as a player id rather than a name

2/8/2017 - Changed how debug logs are done to speed up bot considerably; !list is sorted now; Made death message code more efficient; Removed a bunch of unnecessary comments; Added crazy gamemode

2/7/2017 - Fixed a SyntaxWarning with faftergame; Changed how wolfchat works in preparation for other stuff; Fixed uptime's minutes displaying incorrectly

2/6/2017 - Roles other than villager can be cursed now; Changed how votes left at end of day work: majority gets the lynch, if no votes or 2 players have equal numbers of votes then no lynch occurs; Added a warning that day or night is about to end

2/5/2017 - Added gamemode to !stats; !notify only notifies you if you are not playing and does not work in game; Added crazed shaman to default mode; Added !uptime command; Added orgy gamemode as a joke

2/3/2017 - Fixed a bug where harlot with protection totem was protected if they visited someone; Fixed a bug where fool was too op for revealing totem; Crazed shaman works, but only has the same totems as shaman right now; Fixed a bug where using !time during sunrise would screw stuff up; Fixed a bug with !myrole; Added !faftergame command to make it easier to do updates

1/31/2017 - Added !fother command to manipulate other flag (totems, traitor)

1/30/2017 - Added !ftemplate command to set templates and added ability to stop a game in !shutdown

1/29/2017 - Gamemode structure works now and they can be set using !fgame; Secret update!

1/27/2017 - Change in how role counts are stored

1/22/2017 - Bot now gets languages from my repository rather than an external one

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
