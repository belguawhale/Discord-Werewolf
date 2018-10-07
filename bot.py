import discord
import asyncio
import aiohttp
import os
import random
import traceback
import sys
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from config import *
from settings import *
import json
import urllib.request
from collections import OrderedDict
from itertools import chain

################## START INIT #####################
client = discord.Client()
# [playing?, {players dict}, day?, [night start, day start], [night elapsed, day elapsed], first join, gamemode, {original roles amount}]
session = [False, OrderedDict(), False, [0, 0], [timedelta(0), timedelta(0)], 0, '', {}]
PLAYERS_ROLE = None
ADMINS_ROLE = None
WEREWOLF_NOTIFY_ROLE = None
ratelimit_dict = {}
pingif_dict = {}
notify_me = []
stasis = {}
commands = {}

wait_bucket = WAIT_BUCKET_INIT
wait_timer = datetime.now()

faftergame = None
starttime = None
with open(NOTIFY_FILE, 'a+') as notify_file:
    notify_file.seek(0)
    notify_me = notify_file.read().split(',')

if os.path.isfile(STASIS_FILE):
    with open(STASIS_FILE, 'r') as stasis_file:
        stasis = json.load(stasis_file)
else:
    with open(STASIS_FILE, 'a+') as stasis_file:
        stasis_file.write('{}')

random.seed(datetime.now())

def get_jsonparsed_data(url):
    try:
        response = urllib.request.urlopen(url)
    except urllib.error.HTTPError:
        return None, None # url does not exist
    data = response.read().decode("utf-8")
    return json.loads(data), data

def load_language(language):
    file = 'lang/{}.json'.format(language)
    if not os.path.isfile(file):
        file = 'lang/en.json'
        print("Could not find language file {}.json, fallback on en.json".format(language))
    with open(file, 'r', encoding='utf-8') as f:
        return json.load(f)

lang = load_language(MESSAGE_LANGUAGE)

def cmd(name, perms, description, *aliases):
    def real_decorator(func):
        commands[name] = [func, perms, description.format(BOT_PREFIX)]
        for alias in aliases:
            if alias not in commands:
                commands[alias] = [func, perms, "```\nAlias for {0}{1}.```".format(BOT_PREFIX, name)]
            else:
                print("ERROR: Cannot assign alias {0} to command {1} since it is already the name of a command!".format(alias, name))
        return func
    return real_decorator

################### END INIT ######################

@client.event
async def on_ready():
    global starttime
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')
    if starttime:
        await log(1, 'on_ready triggered again!')
        return
    await log(1, 'on_ready triggered!')
    # [playing : True | False, players : {player id : [alive, role, action, template, other]}, day?, [datetime night, datetime day], [elapsed night, elapsed day], first join time, gamemode]
    for role in client.get_server(WEREWOLF_SERVER).role_hierarchy:
        if role.name == PLAYERS_ROLE_NAME:
            global PLAYERS_ROLE
            PLAYERS_ROLE = role
        if role.name == ADMINS_ROLE_NAME:
            global ADMINS_ROLE
            ADMINS_ROLE = role
        if role.name == WEREWOLF_NOTIFY_ROLE_NAME:
            global WEREWOLF_NOTIFY_ROLE
            WEREWOLF_NOTIFY_ROLE = role
    if PLAYERS_ROLE:
        await log(0, "Players role id: " + PLAYERS_ROLE.id)
    else:
        await log(3, "Could not find players role " + PLAYERS_ROLE_NAME)
    if ADMINS_ROLE:
        await log(0, "Admins role id: " + ADMINS_ROLE.id)
    else:
        await log(3, "Could not find admins role " + ADMINS_ROLE_NAME)
    if WEREWOLF_NOTIFY_ROLE:
        await log(0, "Werewolf Notify role id: " + WEREWOLF_NOTIFY_ROLE.id)
    else:
        await log(2, "Could not find Werewolf Notify role " + WEREWOLF_NOTIFY_ROLE_NAME)
    if PLAYING_MESSAGE:
        await client.change_presence(status=discord.Status.online, game=discord.Game(name=PLAYING_MESSAGE))
    starttime = datetime.now()

@client.event
async def on_resume():
    print("RESUMED")
    await log(1, "on_resume triggered!")

@client.event
async def on_message(message):
    if not starttime:
        return
    if message.author.id in [client.user.id] + IGNORE_LIST or not client.get_server(WEREWOLF_SERVER).get_member(message.author.id):
        if not (message.author.id in ADMINS or message.author.id == OWNER_ID):
            return
    if await rate_limit(message):
        return

    if message.channel.is_private:
        await log(0, 'pm from ' + message.author.name + ' (' + message.author.id + '): ' + message.content)
        if session[0] and message.author.id in session[1]:
            if session[1][message.author.id][1] in WOLFCHAT_ROLES and session[1][message.author.id][0]:
                if not message.content.strip().startswith(BOT_PREFIX):
                    await wolfchat(message)

    if message.content.strip().startswith(BOT_PREFIX):
        # command
        command = message.content.strip()[len(BOT_PREFIX):].lower().split(' ')[0]
        parameters = ' '.join(message.content.strip().lower().split(' ')[1:])
        if has_privileges(1, message) or message.channel.id == GAME_CHANNEL or message.channel.is_private:
            await parse_command(command, message, parameters)
    elif message.channel.is_private:
        command = message.content.strip().lower().split(' ')[0]
        parameters = ' '.join(message.content.strip().lower().split(' ')[1:])
        await parse_command(command, message, parameters)

############# COMMANDS #############
@cmd('shutdown', [2, 2], "```\n{0}shutdown takes no arguments\n\nShuts down the bot. Owner-only.```")
async def cmd_shutdown(message, parameters):
    if parameters.startswith("-fstop"):
        await cmd_fstop(message, "-force")
    elif parameters.startswith("-stop"):
        await cmd_fstop(message, parameters[len("-stop"):])
    elif parameters.startswith("-fleave"):
        await cmd_fleave(message, 'all')
    await reply(message, "Shutting down...")
    await client.logout()

@cmd('ping', [0, 0], "```\n{0}ping takes no arguments\n\nTests the bot\'s responsiveness.```")
async def cmd_ping(message, parameters):
    msg = random.choice(lang['ping']).format(
        bot_nick=client.user.display_name, author=message.author.name, p=BOT_PREFIX)
    await reply(message, msg)

@cmd('eval', [2, 2], "```\n{0}eval <evaluation string>\n\nEvaluates <evaluation string> using Python\'s eval() function and returns a result. Owner-only.```")
async def cmd_eval(message, parameters):
    output = None
    parameters = ' '.join(message.content.split(' ')[1:])
    if parameters == '':
        await reply(message, commands['eval'][2].format(BOT_PREFIX))
        return
    try:
        output = eval(parameters)
    except:
        await reply(message, '```\n' + str(traceback.format_exc()) + '\n```')
        traceback.print_exc()
        return
    if asyncio.iscoroutine(output):
        output = await output
    await reply(message, '```py\n' + str(output) + '\n```', cleanmessage=False)

@cmd('exec', [2, 2], "```\n{0}exec <exec string>\n\nExecutes <exec string> using Python\'s exec() function. Owner-only.```")
async def cmd_exec(message, parameters):
    parameters = ' '.join(message.content.split(' ')[1:])
    if parameters == '':
        await reply(message, commands['exec'][2].format(BOT_PREFIX))
        return
    old_stdout = sys.stdout
    redirected_output = sys.stdout = StringIO()
    try:
        exec(parameters)
    except Exception:
        await reply(message, '```py\n{}\n```'.format(traceback.format_exc()))
        return
    finally:
        sys.stdout = old_stdout
    output = str(redirected_output.getvalue())
    if output == '':
        output = ":thumbsup:"
    await client.send_message(message.channel, output)

@cmd('async', [2, 2], "```\n{0}async <code>\n\nExecutes <code> as a coroutine.```")
async def cmd_async(message, parameters, recursion=0):
    if parameters == '':
        await reply(message, commands['async'][2].format(PREFIX))
        return
    env = {'message' : message,
           'parameters' : parameters,
           'recursion' : recursion,
           'client' : client,
           'channel' : message.channel,
           'author' : message.author,
           'server' : message.server}
    env.update(globals())
    old_stdout = sys.stdout
    redirected_output = sys.stdout = StringIO()
    result = None
    exec_string = "async def _temp_exec():\n"
    exec_string += '\n'.join(' ' * 4 + line for line in parameters.split('\n'))
    try:
        exec(exec_string, env)
    except Exception:
        traceback.print_exc()
        result = traceback.format_exc()
    else:
        _temp_exec = env['_temp_exec']
        try:
            returnval = await _temp_exec()
            value = redirected_output.getvalue()
            if returnval == None:
                result = value
            else:
                result = value + '\n' + str(returnval)
        except Exception:
            traceback.print_exc()
            result = traceback.format_exc()
    finally:
        sys.stdout = old_stdout
    await client.send_message(message.channel, "```py\n{}\n```".format(result))

@cmd('help', [0, 0], "```\n{0}help <command>\n\nReturns hopefully helpful information on <command>. Try {0}list for a listing of commands.```")
async def cmd_help(message, parameters):
    if parameters == '':
        parameters = 'help'
    if parameters in commands:
        await reply(message, commands[parameters][2].format(BOT_PREFIX))
    else:
        await reply(message, 'No help found for command ' + parameters)

@cmd('list', [0, 0], "```\n{0}list takes no arguments\n\nDisplays a listing of commands. Try {0}help <command> for help regarding a specific command.```")
async def cmd_list(message, parameters):
    cmdlist = []
    for key in commands:
        if message.channel.is_private:
            if has_privileges(commands[key][1][1], message):
                cmdlist.append(key)
        else:
            if has_privileges(commands[key][1][0], message):
                cmdlist.append(key)
    await reply(message, "Available commands: {}".format(", ".join(sorted(cmdlist))))

@cmd('join', [0, 1], "```\n{0}join [<gamemode>]\n\nJoins the game if it has not started yet. Votes for [<gamemode>] if it is given.```", 'j')
async def cmd_join(message, parameters):
    global wait_timer # ugh globals
    global wait_bucket
    if session[0]:
        return
    if message.author.id in stasis and stasis[message.author.id] > 0:
        await reply(message, "You are in stasis for **{}** game{}. Please do not break rules, idle out or use !leave during a game.".format(
                                stasis[message.author.id], '' if stasis[message.author.id] == 1 else 's'))
        return
    if len(session[1]) >= MAX_PLAYERS:
        await reply(message, random.choice(lang['maxplayers']).format(MAX_PLAYERS))
        return
    if message.author.id in session[1]:
        await reply(message, random.choice(lang['alreadyin']).format(message.author.name))
    else:
        session[1][message.author.id] = [True, '', '', [], []]
        if len(session[1]) == 1:
            wait_bucket = WAIT_BUCKET_INIT
            wait_timer = datetime.now() + timedelta(seconds=WAIT_AFTER_JOIN)
            client.loop.create_task(game_start_timeout_loop())
            client.loop.create_task(wait_timer_loop())
            await client.change_presence(game=client.get_server(WEREWOLF_SERVER).me.game, status=discord.Status.idle)
            await send_lobby(random.choice(lang['gamestart']).format(
                                            message.author.name, p=BOT_PREFIX))
        else:
            await client.send_message(message.channel, "**{}** joined the game and raised the number of players to **{}**.".format(
                                                        message.author.name, len(session[1])))
        if parameters:
            await cmd_vote(message, parameters)
        #                            alive, role, action, [templates], [other]
        await client.add_roles(client.get_server(WEREWOLF_SERVER).get_member(message.author.id), PLAYERS_ROLE)
        wait_timer = datetime.now() + timedelta(seconds=WAIT_AFTER_JOIN)
        client.loop.create_task(player_idle(message))

@cmd('leave', [0, 1], "```\n{0}leave takes no arguments\n\nLeaves the current game. If you need to leave, please do it before the game starts.```", 'q')
async def cmd_leave(message, parameters):
    if session[0] and message.author.id in session[1] and session[1][message.author.id][0]:
        if parameters != '-force':
            msg = await client.send_message(message.channel, "Are you sure you want to quit during game? Doing "
                                                             "so will result in {} games of stasis. You may bypass "
                                                             "this confirmation by using `{}leave -force`.".format(
                                                                 QUIT_GAME_STASIS, BOT_PREFIX))
            def check(m):
                c = m.content.lower()
                return c in ['yes', 'y', 'no', 'n']
            response = await client.wait_for_message(author=message.author, channel=message.channel, timeout=5, check=check)
            await client.delete_message(msg)
            if not response or response.content.lower() not in ['yes', 'y']:
                return
        if not session[1][message.author.id][0]:
            # prevent race condition where user runs this command multiple times and then says "yes"
            return
        await send_lobby(random.choice(lang['leavedeath']).format(
            message.author.name, get_role(message.author.id, 'death')))
        await player_deaths({message.author.id : ('leave', "bot")})
        if message.author.id in stasis:
            stasis[message.author.id] += QUIT_GAME_STASIS
        else:
            stasis[message.author.id] = QUIT_GAME_STASIS
        if session[0] and win_condition() == None:
            await check_traitor()
        await log(1, "{} ({}) QUIT DURING GAME".format(message.author.display_name, message.author.id))
    else:
        if message.author.id in session[1]:
            if session[0]:
                await reply(message, "wot?")
                return
            await player_deaths({message.author.id : ('leave', "bot")})
            await send_lobby(random.choice(lang['leavelobby']).format(message.author.name, len(session[1])))
            if len(session[1]) == 0:
                await client.change_presence(game=client.get_server(WEREWOLF_SERVER).me.game, status=discord.Status.online)
        else:
            await reply(message, random.choice(lang['notplayingleave']))

@cmd('wait', [0, 1], "```\n{0}wait takes no arguments\n\nIncreases the wait time until {0}start may be used.```", 'w')
async def cmd_wait(message, parameters):
    global wait_bucket
    global wait_timer
    if session[0] or message.author.id not in session[1]:
        return
    if wait_bucket <= 0:
        wait_bucket = 0
        await reply(message, "That command is ratelimited.")
    else:
        wait_timer = max(datetime.now() + timedelta(seconds=EXTRA_WAIT), wait_timer + timedelta(seconds=EXTRA_WAIT))
        wait_bucket -= 1
        await send_lobby("**{}** increased the wait time by {} seconds.".format(message.author.name, EXTRA_WAIT))

@cmd('fjoin', [1, 1], "```\n{0}fjoin <mentions of users>\n\nForces each <mention> to join the game.```")
async def cmd_fjoin(message, parameters):
    if session[0]:
        return
    if parameters == '':
        await reply(message, commands['fjoin'][2].format(BOT_PREFIX))
        return
    raw_members = parameters.split(' ')
    join_list = []
    for member in raw_members:
        if member.strip('<!@>').isdigit():
            join_list.append(member.strip('<!@>'))
        elif '-' in member:
            left = member.split('-')[0]
            right = member.split('-')[1]
            if left.isdigit() and right.isdigit():
                join_list += list(map(str, range(int(left), int(right) + 1)))
    if join_list == []:
        await reply(message, "ERROR: no valid mentions found")
        return
    join_msg = ""
    for member in sort_players(join_list):
        session[1][member] = [True, '', '', [], []]
        join_msg += "**" + get_name(member) + "** was forced to join the game.\n"
        if client.get_server(WEREWOLF_SERVER).get_member(member):
            await client.add_roles(client.get_server(WEREWOLF_SERVER).get_member(member), PLAYERS_ROLE)
    join_msg += "New player count: **{}**".format(len(session[1]))
    if len(session[1]) > 0:
        await client.change_presence(game=client.get_server(WEREWOLF_SERVER).me.game, status=discord.Status.idle)
    await client.send_message(message.channel, join_msg)
    await log(2, "{0} ({1}) used FJOIN {2}".format(message.author.name, message.author.id, parameters))

@cmd('fleave', [1, 1], "```\n{0}fleave <mentions of users | all>\n\nForces each <mention> to leave the game. If the parameter is all, removes all players from the game.```")
async def cmd_fleave(message, parameters):
    if parameters == '':
        await reply(message, commands['fleave'][2].format(BOT_PREFIX))
        return
    raw_members = parameters.split(' ')
    leave_list = []
    if parameters == 'all':
        leave_list = list(session[1])
    else:
        for member in raw_members:
            if member.strip('<!@>').isdigit():
                leave_list.append(member.strip('<!@>'))
            elif '-' in member:
                left = member.split('-')[0]
                right = member.split('-')[1]
                if left.isdigit() and right.isdigit():
                    leave_list += list(map(str, range(int(left), int(right) + 1)))
    if leave_list == []:
        await reply(message, "ERROR: no valid mentions found")
        return
    leave_msg = ""

    for member in sort_players(leave_list):
        if member in list(session[1]):
            if session[0]:
                leave_msg += "**" + get_name(member) + "** was forcibly shoved into a fire. The air smells of freshly burnt **" + get_role(member, 'death') + "**.\n"
            else:
                leave_msg += "**" + get_name(member) + "** was forced to leave the game.\n"
    if not session[0]:
        leave_msg += "New player count: **{}**".format((len(session[1])) - 1)
        if len(session[1]) == 0:
            await client.change_presence(game=client.get_server(WEREWOLF_SERVER).me.game, status=discord.Status.online)
    await send_lobby(leave_msg)
    leave_dict = {}
    for p in [x for x in sort_players(leave_list) if x in session[1]]:
        leave_dict[p] = ('fleave', "bot")
    await player_deaths(leave_dict)
    await log(2, "{0} ({1}) used FLEAVE {2}".format(message.author.name, message.author.id, parameters))
    if session[0] and win_condition() == None:
        await check_traitor()

@cmd('refresh', [1, 1], "```\n{0}refresh [<language file>]\n\nRefreshes the current language's language file from GitHub. Admin only.```")
async def cmd_refresh(message, parameters):
    global lang
    if parameters == '':
        parameters = MESSAGE_LANGUAGE
    url = "https://raw.githubusercontent.com/belguawhale/Discord-Werewolf/master/lang/{}.json".format(parameters)
    codeset = parameters
    temp_lang, temp_str = get_jsonparsed_data(url)
    if not temp_lang:
        await reply(message, "Could not refresh language {} from Github.".format(parameters))
        return
    with open('lang/{}.json'.format(parameters), 'w', encoding='utf-8') as f:
        f.write(temp_str)
    lang = temp_lang
    await reply(message, 'The messages with language code `' + codeset + '` have been refreshed from GitHub.')

@cmd('start', [0, 1], "```\n{0}start takes no arguments\n\nVotes to start the game. A game needs at least " +\
                      str(MIN_PLAYERS) + " players to start.```")
async def cmd_start(message, parameters):
    if session[0]:
        return
    if message.author.id not in session[1]:
        await reply(message, random.choice(lang['notplayingstart']))
        return
    if len(session[1]) < MIN_PLAYERS:
        await reply(message, random.choice(lang['minplayers']).format(MIN_PLAYERS))
        return
    if session[1][message.author.id][1]:
        return
    if datetime.now() < wait_timer:
        await reply(message, "Please wait at least {} more second{}.".format(
            int((wait_timer - datetime.now()).total_seconds()), '' if int((wait_timer - datetime.now()).total_seconds()) == 1 else 's'))
        return
    session[1][message.author.id][1] = 'start'
    votes = len([x for x in session[1] if session[1][x][1] == 'start'])
    votes_needed = max(2, min(len(session[1]) // 4 + 1, 4))
    if votes < votes_needed:
        await send_lobby("**{}** has voted to start the game. **{}** more vote{} needed.".format(
            message.author.display_name, votes_needed - votes, '' if (votes_needed - votes == 1) else 's'))
    else:
        await run_game()
    if votes == 1:
        await start_votes(message.author.id)

@cmd('fstart', [1, 2], "```\n{0}fstart takes no arguments\n\nForces game to start.```")
async def cmd_fstart(message, parameters):
    if session[0]:
        return
    if len(session[1]) < MIN_PLAYERS:
        await reply(message, random.choice(lang['minplayers']).format(MIN_PLAYERS))
    else:
        await send_lobby("**" + message.author.name + "** forced the game to start.")
        await log(2, "{0} ({1}) FSTART".format(message.author.name, message.author.id))
        await run_game()

@cmd('fstop', [1, 1], "```\n{0}fstop [<-force|reason>]\n\nForcibly stops the current game with an optional [<reason>]. Use {0}fstop -force if "
                      "bot errors.```")
async def cmd_fstop(message, parameters):
    msg = "Game forcibly stopped by **" + message.author.name + "**"
    if parameters == "":
        msg += "."
    elif parameters == "-force":
        if not session[0]:
            return
        msg += ". Here is some debugging info:\n```py\n{0}\n```".format(str(session))
        session[0] = False
        perms = client.get_channel(GAME_CHANNEL).overwrites_for(client.get_server(WEREWOLF_SERVER).default_role)
        perms.send_messages = True
        await client.edit_channel_permissions(client.get_channel(GAME_CHANNEL), client.get_server(WEREWOLF_SERVER).default_role, perms)
        player_dict = {}
        for player in list(session[1]):
            player_dict[player] = ('fstop', "bot")
        await player_deaths(player_dict)
        session[3] = [datetime.now(), datetime.now()]
        session[4] = [timedelta(0), timedelta(0)]
        session[6] = ''
        session[7] = {}
        await send_lobby(msg)
        return
    else:
        msg += " for reason: `" + parameters + "`."

    if not session[0]:
        await reply(message, "There is no currently running game!")
        return
    else:
        await log(2, "{0} ({1}) FSTOP {2}".format(message.author.name, message.author.id, parameters))
    await end_game(msg + '\n\n' + end_game_stats())

@cmd('sync', [1, 1], "```\n{0}sync takes no arguments\n\nSynchronizes all player roles and channel permissions with session.```")
async def cmd_sync(message, parameters):
    for member in client.get_server(WEREWOLF_SERVER).members:
        if member.id in session[1] and session[1][member.id][0]:
            if not PLAYERS_ROLE in member.roles:
                await client.add_roles(member, PLAYERS_ROLE)
        else:
            if PLAYERS_ROLE in member.roles:
                await client.remove_roles(member, PLAYERS_ROLE)
    perms = client.get_channel(GAME_CHANNEL).overwrites_for(client.get_server(WEREWOLF_SERVER).default_role)
    if session[0]:
        perms.send_messages = False
    else:
        perms.send_messages = True
    await client.edit_channel_permissions(client.get_channel(GAME_CHANNEL), client.get_server(WEREWOLF_SERVER).default_role, perms)
    await log(2, "{0} ({1}) SYNC".format(message.author.name, message.author.id))
    await reply(message, "Sync successful.")

@cmd('op', [1, 1], "```\n{0}op takes no arguments\n\nOps yourself if you are an admin```")
async def cmd_op(message, parameters):
    await log(2, "{0} ({1}) OP {2}".format(message.author.name, message.author.id, parameters))
    if parameters == "":
        await client.add_roles(client.get_server(WEREWOLF_SERVER).get_member(message.author.id), ADMINS_ROLE)
        await reply(message, ":thumbsup:")
    else:
        member = client.get_server(WEREWOLF_SERVER).get_member(parameters.strip("<!@>"))
        if member:
            if member.id in ADMINS:
                await client.add_roles(member, ADMINS_ROLE)
                await reply(message, ":thumbsup:")

@cmd('deop', [1, 1], "```\n{0}deop takes no arguments\n\nDeops yourself so you can play with the players ;)```")
async def cmd_deop(message, parameters):
    await log(2, "{0} ({1}) DEOP {2}".format(message.author.name, message.author.id, parameters))
    if parameters == "":
        await client.remove_roles(client.get_server(WEREWOLF_SERVER).get_member(message.author.id), ADMINS_ROLE)
        await reply(message, ":thumbsup:")
    else:
        member = client.get_server(WEREWOLF_SERVER).get_member(parameters.strip("<!@>"))
        if member:
            if member.id in ADMINS:
                await client.remove_roles(member, ADMINS_ROLE)
                await reply(message, ":thumbsup:")

@cmd('role', [0, 0], "```\n{0}role [<role | number of players | gamemode>] [<number of players>]\n\nIf a <role> is given, "
                     "displays a description of <role>. If a <number of players> is given, displays the quantity of each "
                     "role for the specified <number of players> for the specified <gamemode>, defaulting to default. If "
                     "only a <gamemode> is given, displays a role guide for <gamemode>. "
                     "If left blank, displays a list of roles.```", 'roles')
async def cmd_role(message, parameters):
    if parameters == "" and not session[0] or parameters == 'list':
        await reply(message, "Roles: " + ", ".join(sort_roles(roles)))
        return
    elif parameters == "" and session[0]:
        msg = "**{}** players playing **{}** gamemode:```\n".format(len(session[1]),
        'roles' if session[6].startswith('roles') else session[6])
        if session[6] in ('random',):
            msg += "!role is disabled for the {} gamemode.\n```".format(session[6])
            await reply(message, msg)
            return

        game_roles = dict(session[7])

        msg += '\n'.join(["{}: {}".format(x, game_roles[x]) for x in sort_roles(game_roles)])
        msg += '```'
        await reply(message, msg)
        return
    elif _autocomplete(parameters, roles)[1] == 1:
        role = _autocomplete(parameters, roles)[0]
        await reply(message, "```\nRole name: {}\nTeam: {}\nDescription: {}\n```".format(role, roles[role][0], roles[role][2]))
        return
    params = parameters.split(' ')
    gamemode = 'default'
    num_players = -1
    choice, num = _autocomplete(params[0], gamemodes)
    if num == 1:
        gamemode = choice

    if params[0].isdigit():
        num_players = params[0]
    elif len(params) == 2 and params[1].isdigit():
        num_players = params[1]
    if num_players == -1:
        if len(params) == 2:
            if params[1] == 'table':
                # generate role table
                WIDTH = 20
                role_dict = dict()
                for role in gamemodes[gamemode]['roles']:
                    if max(gamemodes[gamemode]['roles'][role]):
                        role_dict.update({role : gamemodes[gamemode]['roles'][role]})
                role_guide = "Role table for gamemode **{}**:\n".format(gamemode)
                role_guide += "```\n" + " " * (WIDTH + 2)
                role_guide += ','.join("{}{}".format(' ' * (2 - len(str(x))), x) for x in range(gamemodes[gamemode]['min_players'], gamemodes[gamemode]['max_players'] + 1)) + '\n'
                role_guide += '\n'.join(role + ' ' * (WIDTH - len(role)) + ": " + repr(\
                role_dict[role][gamemodes[gamemode]['min_players'] - MIN_PLAYERS:gamemodes[gamemode]['max_players']]) for role in sort_roles(role_dict))
                role_guide += "\n```"
            elif params[1] == 'guide':
                # generate role guide
                role_dict = gamemodes[gamemode]['roles']
                prev_dict = dict((x, 0) for x in roles if x != 'villager')
                role_guide = 'Role guide for gamemode **{}**:\n'.format(gamemode)
                for i in range(gamemodes[gamemode]['max_players'] - MIN_PLAYERS + 1):
                    current_dict = {}
                    for role in sort_roles(roles):
                        if role == 'villager':
                            continue
                        if role in role_dict:
                            current_dict[role] = role_dict[role][i]
                        else:
                            current_dict[role] = 0
                    # compare previous and current
                    if current_dict == prev_dict:
                        # same
                        continue
                    role_guide += '**[{}]** '.format(i + MIN_PLAYERS)
                    for role in sort_roles(roles):
                        if role == 'villager':
                            continue
                        if current_dict[role] == 0 and prev_dict[role] == 0:
                            # role not in gamemode
                            continue
                        if current_dict[role] > prev_dict[role]:
                            # role increased
                            role_guide += role
                            if current_dict[role] > 1:
                                role_guide += " ({})".format(current_dict[role])
                            role_guide += ', '
                        elif prev_dict[role] > current_dict[role]:
                            role_guide += '~~{}'.format(role)
                            if prev_dict[role] > 1:
                                role_guide += " ({})".format(prev_dict[role])
                            role_guide += '~~, '
                    role_guide = role_guide.rstrip(', ') + '\n'
                    # makes a copy
                    prev_dict = dict(current_dict)
            else:
                role_guide = "Please choose one of the following: " + ', '.join(['guide', 'table'])
        else:
            role_guide = "Please choose one of the following for the third parameter: {}".format(', '.join(['guide', 'table']))
        if not len(role_guide)>2000:
            await reply(message, role_guide)
        else:
            pass # temporary until a solution is found
    else:
        num_players = int(num_players)
        if num_players in range(gamemodes[gamemode]['min_players'], gamemodes[gamemode]['max_players'] + 1):
            if gamemode in ('random',):
                msg = "!role is disabled for the **{}** gamemode.".format(gamemode)
            else:
                msg = "Roles for **{}** players in gamemode **{}**:```\n".format(num_players, gamemode)
                game_roles = get_roles(gamemode, num_players)
                msg += '\n'.join("{}: {}".format(x, game_roles[x]) for x in sort_roles(game_roles))
                msg += '```'
            await reply(message, msg)
        else:
            await reply(message, "Please choose a number of players between " + str(gamemodes[gamemode]['min_players']) +\
            " and " + str(gamemodes[gamemode]['max_players']) + ".")

async def _send_role_info(player, sendrole=True):
    if session[0] and player in session[1]:
        member = client.get_server(WEREWOLF_SERVER).get_member(player)
        if member and session[1][player][0]:
            role = get_role(player, 'role') if get_role(player, 'role') not in ['amnesiac', 'vengeful ghost'] else "villager"
            templates = get_role(player, 'templates')
            if member and session[1][player][0]:
                try:
                    if sendrole:
                        await client.send_message(member, "Your role is **" + role + "**. " + roles[role][2] + '\n')
                    msg = []
                    living_players = sort_players(x for x in session[1] if session[1][x][0])
                    living_players_string = ['{} ({})'.format(get_name(x), x) for x in living_players]
                    if role in COMMANDS_FOR_ROLE['kill'] and roles[role][0] == 'wolf':
                        if 'angry' in session[1][player][4]:
                            num_kills = session[1][player][4].count('angry')
                            msg.append("You are **angry** tonight, and may kill {} targets by using `kill {}`.\n".format(
                                num_kills + 1, ' AND '.join('player' + str(x + 1) for x in range(num_kills + 1))))
                    if roles[role][0] == 'wolf' and role != 'cultist' and (role != 'minion' or str(session[4][1]) == "0:00:00"):
                        living_players_string = []
                        for plr in living_players:
                            temprole = get_role(plr, 'role')
                            temptemplates = get_role(plr, 'templates')
                            role_string = []
                            if 'cursed' in temptemplates and role != 'minion':
                                role_string.append('cursed')
                            if roles[temprole][0] == 'wolf' and temprole not in ['minion', 'cultist']:
                                role_string.append(temprole)
                            living_players_string.append("{} ({}){}".format(get_name(plr), plr,
                            ' ({})'.format(' '.join(role_string)) if role_string else ''))
                    if role == 'succubus':
                        living_players_string = []
                        for plr in living_players:
                            temprole = get_role(plr, 'role')
                            role_string = []
                            if 'entranced' in session[1][plr][4]:
                                role_string.append('entranced')
                            if temprole == 'succubus':
                                role_string.append(temprole)
                            living_players_string.append("{} ({}){}".format(get_name(plr), plr,
                            ' ({})'.format(' '.join(role_string)) if role_string else ''))
                    if role == 'piper':
                        living_players_string = []
                        for plr in living_players:
                            temprole = get_role(plr, 'role')
                            role_string = []
                            if 'charmed' in session[1][plr][4]:
                                role_string.append('charmed')
                            if temprole == 'piper':
                                role_string.append(temprole)
                            living_players_string.append("{} ({}){}".format(get_name(plr), plr,
                            ' ({})'.format(' '.join(role_string)) if role_string else ''))
                    if role in ['shaman', 'wolf shaman']:
                        totem = ''
                        if session[1][player][2] in totems:
                            totem = session[1][player][2]
                        elif [x for x in session[1][player][4] if x.startswith("totem:")]:
                            totem = [x.split(':')[1] for x in session[1][player][4] if x.startswith("totem:")].pop()
                        if totem:
                            msg.append("You have the **{}**. {}\n".format(totem.replace('_', ' '), totems[totem]))
                    if role in ['wolf', 'werecrow', 'doomsayer', 'wolf cub', 'werekitten', 'wolf shaman', 'wolf mystic', 'traitor', 'sorcerer', 'seer',
                                'oracle', 'shaman', 'harlot', 'hunter', 'augur', 'detective', 'guardian angel',
                                'crazed shaman', 'succubus', 'hag', 'piper', 'bodyguard', 'warlock']:
                        msg.append("Living players: ```basic\n" + '\n'.join(living_players_string) + '\n```')
                    #mystic stuff/wolf mystic stuff
                    if role == 'mystic':
                        wolfcount = 0
                        for player in session[1]:
                            if get_role(player, 'actualteam') == 'wolf' and session[1][player][0]:
                                wolfcount += 1
                        try:
                            if member:
                                await client.send_message(member, "You sense that there are **{}** wolves.".format(wolfcount))
                        except discord.Forbidden:
                            pass
                    if role == 'wolf mystic':
                        vilcount = 0
                        for player in session[1]:
                            if ((get_role(player, 'actualteam') == 'village' and get_role(player, 'role') != 'villager') or get_role(player, 'role') == ('fool' or 'monster' or 'succubus' or  'piper' or 'demoniac')) and session[1][player][0]:
                                vilcount += 1
                        try:
                            if member:
                                await client.send_message(member, "You sense that there are **{}** villagers.".format(vilcount))
                        except discord.Forbidden:
                            pass
                    if 'gunner' in templates:
                        msg.append("You have a gun and **{}** bullet{}. Use the command "
                                   "`{}role gunner` for more information.".format(
                            session[1][player][4].count('bullet'), '' if session[1][player][4].count('bullet') == 1 else 's',
                            BOT_PREFIX))
                    if 'sharpshooter' in templates:
                        msg.append("You have a gun and **{}** bullet{}. Use the command "
                                   "`{}role sharpshooter` for more information.".format(
                            session[1][player][4].count('bullet'), '' if session[1][player][4].count('bullet') == 1 else 's',
                            BOT_PREFIX))
                    if 'assassin' in templates:
                        target = ""
                        for o in session[1][player][4]:
                            if o.startswith("assassinate:"):
                                target = o.split(":")[1]
                        if target:
                            if role == 'village drunk':
                                msg.append("In your drunken stupor you have selected **{0}** as your target. Use the command `{1}role assassin` for more information.".format(get_name(target), BOT_PREFIX))
                            else:
                                msg.append("Your target is **{0}**. Use the command `{1}role assassin`"
                                   "for more information.".format(get_name(target), BOT_PREFIX))
                        else:
                            msg.append("You are an **assassin**, and wish to spread chaos. Type `target <player>` to make them your target. If you die, you take them with you, but if they die, you may choose another target.\nLiving players: ```basic\n" + '\n'.join(living_players_string) + '\n```')
                    if role == 'matchmaker' and sendrole:
                        msg.append("Living players: ```basic\n" + '\n'.join(living_players_string) + '\n```')
                    if role == 'minion' and str(session[4][1]) == "0:00:00":
                        msg.append("Living players: ```basic\n" + '\n'.join(living_players_string) + '\n```')
                    if msg:
                        await client.send_message(member, '\n'.join(msg))
                except discord.Forbidden:
                    await send_lobby(member.mention + ", you cannot play the game if you block me")
        elif member and get_role(player, 'role') == 'vengeful ghost' and [x for x in session[1][player][4] if x.startswith("vengeance:")]:
            try:
                against = 'wolf'
                if [x for x in session[1][player][4] if x.startswith("vengeance:")]:
                    against = [x.split(':')[1] for x in session[1][player][4] if x.startswith('vengeance:')].pop()
                await client.send_message(member, "You are a **vengeful ghost**, sworn to take revenge on the {0} that you believe killed you. You must kill one of them with `kill <player>` tonight. If you do not, one of them will be selected at random.".format('wolves' if against == 'wolf' else 'villagers'))
                living_players = sort_players(x for x in session[1] if session[1][x][0] if roles[get_role(x, "role")][0] == against)
                living_players_string = ['{} ({})'.format(get_name(x), x) for x in living_players]
                await client.send_message(member, "Living players: ```basic\n" + '\n'.join(living_players_string) + '\n```')
            except discord.Forbidden:
                pass
        
@cmd('myrole', [0, 0], "```\n{0}myrole takes no arguments\n\nTells you your role in pm.```")
async def cmd_myrole(message, parameters):
    await _send_role_info(message.author.id)

@cmd('stats', [0, 0], "```\n{0}stats takes no arguments\n\nLists current players in the lobby during the join phase, and lists game information in-game.```")
async def cmd_stats(message, parameters):
    #TODO: rewrite
    if session[0]:
        reply_msg = "It is now **" + ("day" if session[2] else "night") + "time**. Using the **{}** gamemode.".format(
            'roles' if session[6].startswith('roles') else session[6])
        reply_msg += "\n**" + str(len(session[1])) + "** players playing: **" + str(len([x for x in session[1] if session[1][x][0]])) + "** alive, "
        reply_msg += "**" + str(len([x for x in session[1] if not session[1][x][0]])) + "** dead\n"
        reply_msg += "```basic\nLiving players:\n" + "\n".join(get_name(x) + ' (' + x + ')' for x in sort_players(session[1]) if session[1][x][0]) + '\n'
        reply_msg += "Dead players:\n" + "\n".join(get_name(x) + ' (' + x + ')' for x in sort_players(session[1]) if not session[1][x][0]) + '\n'

        if session[6] in ('random',):
            reply_msg += '\n!stats is disabled for the {} gamemode.```'.format(session[6])
            await reply(message, reply_msg)
            return
        orig_roles = dict(session[7])
        # make a copy
        role_dict = {}
        traitorvill = 0
        traitor_turned = False
        for other in [session[1][x][4] for x in session[1]]:
            if 'traitor' in other:
                traitor_turned = True
                break
        for role in roles: # Fixes !stats crashing with !frole of roles not in game
            role_dict[role] = [0, 0]
            # [min, max] for traitor and similar roles
        for player in session[1]:
            # Get maximum numbers for all roles
            role_dict[get_role(player, 'role') if not [x for x in session[1][player][4] if x.startswith('turned:')] else [x for x in session[1][player][4] if x.startswith('turned:')].pop().split(':')[1]][0] += 1
            role_dict[get_role(player, 'role') if not [x for x in session[1][player][4] if x.startswith('turned:')] else [x for x in session[1][player][4] if x.startswith('turned:')].pop().split(':')[1]][1] += 1
            if get_role(player, 'role') in ['villager', 'traitor']:
                traitorvill += 1

        #reply_msg += "Total roles: " + ", ".join(sorted([x + ": " + str(roles[x][3][len(session[1]) - MIN_PLAYERS]) for x in roles if roles[x][3][len(session[1]) - MIN_PLAYERS] > 0])).rstrip(", ") + '\n'
        # ^ saved this beast for posterity

        reply_msg += "Total roles: "
        total_roles = dict(orig_roles)
        reply_msg += ', '.join("{}: {}".format(x, total_roles[x]) for x in sort_roles(total_roles))

        for role in list(role_dict):
            # list is used to make a copy
            if role in TEMPLATES_ORDERED:
                del role_dict[role]

        if traitor_turned:
            role_dict['wolf'][0] += role_dict['traitor'][0]
            role_dict['wolf'][1] += role_dict['traitor'][1]
            role_dict['traitor'] = [0, 0]

        for player in session[1]:
            # Subtract dead players
            if not session[1][player][0]:
                role = get_role(player, 'role')
                reveal = get_role(player, 'deathstats')

                if role == 'traitor' and traitor_turned:
                    # player died as traitor but traitor turn message played, so subtract from wolves
                    reveal = 'wolf'

                if reveal == 'villager':
                    traitorvill -= 1
                    # could be traitor or villager
                    if 'traitor' in role_dict:
                        role_dict['traitor'][0] = max(0, role_dict['traitor'][0] - 1)
                        if role_dict['traitor'][1] > traitorvill:
                            role_dict['traitor'][1] = traitorvill

                    role_dict['villager'][0] = max(0, role_dict['villager'][0] - 1)
                    if role_dict['villager'][1] > traitorvill:
                        role_dict['villager'][1] = traitorvill
                else:
                    # player died is definitely that role
                    role_dict[reveal][0] = max(0, role_dict[reveal][0] - 1)
                    role_dict[reveal][1] = max(0, role_dict[reveal][1] - 1)

        reply_msg += "\nCurrent roles: "
        for template in TEMPLATES_ORDERED:
            if template in orig_roles:
                del orig_roles[template]
        print(role_dict)
        for role in sort_roles(list(set(roles) - set(TEMPLATES_ORDERED))):
            if role in orig_roles or role_dict[role][0]:
                if role_dict[role][0] == role_dict[role][1]:
                    if role_dict[role][0] == 1:
                        reply_msg += role
                    else:
                        reply_msg += roles[role][1]
                    reply_msg += ": " + str(role_dict[role][0])
                else:
                    reply_msg += roles[role][1] + ": {}-{}".format(role_dict[role][0], role_dict[role][1])
                reply_msg += ", "
        reply_msg = reply_msg.rstrip(", ") + "```"
        await reply(message, reply_msg)
    else:
        players = ["{} ({})".format(get_name(x), x) for x in sort_players(session[1])]
        num_players = len(session[1])
        if num_players == 0:
            await client.send_message(message.channel, "There is currently no active game. Try {}join to start a new game!".format(BOT_PREFIX))
        else:
            await client.send_message(message.channel, "{} players in lobby: ```\n{}\n```".format(num_players, '\n'.join(players)))

@cmd('revealroles', [1, 1], "```\n{0}revealroles takes no arguments\n\nDisplays what each user's roles are and sends it in pm.```", 'rr')
async def cmd_revealroles(message, parameters):
    msg = ["**Gamemode**: {}```diff".format(session[6])]
    for player in sort_players(session[1]):
        msg.append("{} {} ({}): {}; action: {}; other: {}".format(
            '+' if session[1][player][0] else '-', get_name(player), player, get_role(player, 'actual'),
            session[1][player][2], ' '.join(session[1][player][4])))
    msg.append("```")
    await client.send_message(message.channel, '\n'.join(msg))
    await log(2, "{0} ({1}) REVEALROLES".format(message.author.name, message.author.id))

@cmd('see', [2, 0], "```\n{0}see <player>\n\nIf you are a seer, uses your power to detect <player>'s role. If you are a doomsayer, dooms <player> with either sickness, lycanthropy or death.```")
async def cmd_see(message, parameters):
    if not session[0] or message.author.id not in session[1] or not session[1][message.author.id][0]:
        return
    role = get_role(message.author.id, 'role')
    if role not in COMMANDS_FOR_ROLE['see']:
        return
    if session[2]:
        await reply(message, "You may only see during the night.")
        return
    if session[1][message.author.id][2] and (role != 'doomsayer' or not [x for x in session[1][message.author.id][4] if x.startswith('doom:')]):
        await reply(message, "You have already used your power.")
        return
    if "silence_totem2" in session[1][message.author.id][4]:
        await reply(message, "You have been silenced, and are unable to use any special powers.")
        return
    else:
        if parameters == "":
            await reply(message, roles[role][2])
        else:
            player = get_player(parameters)
            if player:
                if role != 'doomsayer':
                    if player == message.author.id:
                        await reply(message, "Using your power on yourself would be a waste.")
                    elif 'entranced' in session[1][message.author.id][4] and get_role(player, 'role') == 'succubus':
                        await reply(message, "You may not see a succubus.")
                    elif not session[1][player][0]:
                        await reply(message, "Player **" + get_name(player) + "** is dead!")
                    else:
                        session[1][message.author.id][2] = player
                        if 'misdirection_totem2' in session[1][message.author.id][4]:
                            player = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                        elif 'luck_totem2' in session[1][player][4]:
                            player = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and x != message.author.id and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                        if role == 'seer':
                            seen_role = get_role(player, 'seen')
                            if (session[1][player][4].count('deceit_totem2') +\
                                session[1][message.author.id][4].count('deceit_totem2')) % 2 == 1:
                                if seen_role == 'wolf':
                                    seen_role = 'villager'
                                else:
                                    seen_role = 'wolf'
                            reply_msg = "is a **{}**".format(seen_role)
                        elif role == 'oracle':
                            seen_role = get_role(player, 'seenoracle')
                            if (session[1][player][4].count('deceit_totem2') +\
                                session[1][message.author.id][4].count('deceit_totem2')) % 2 == 1:
                                # getting team will return either village or wolf team
                                if seen_role == 'wolf':
                                    seen_role = 'villager'
                                else:
                                    seen_role = 'wolf'
                            reply_msg = "is {}a **wolf**".format('**not** ' if seen_role == 'villager' else '')
                        elif role == 'augur':
                            seen_role = get_role(player, 'actualteam')
                            if get_role(player, 'role') == 'amnesiac':
                                seen_role = roles[[x.split(':')[1].replace("_", " ") for x in session[1][player][4] if x.startswith("role:")].pop()][0]
                            reply_msg = "exudes a **{}** aura".format(
                                'red' if seen_role == 'wolf' else 'blue' if seen_role == 'village' else 'grey')
                        await reply(message, "You have a vision... in your vision you see that **{}** {}!".format(
                            get_name(player), reply_msg))
                        await log(1, "{0} ({1}) SEE {2} ({3}) AS {4}".format(get_name(message.author.id), message.author.id, get_name(player), player, seen_role))
                else:
                    if player == message.author.id:
                        await reply(message, "Seeing yourself would be a waste.")
                        return
                    elif 'entranced' in session[1][message.author.id][4] and get_role(player, 'role') == 'succubus':
                        await reply(message, "You may not see a succubus.")
                        return
                    elif not session[1][player][0]:
                        await reply(message, "Player **" + get_name(player) + "** is dead!")
                        return
                    elif get_role(player, 'role') in WOLFCHAT_ROLES:
                        await reply(message, "Seeing another wolf would be a waste.")
                        return
                    else:
                        if 'misdirection_totem2' in session[1][message.author.id][4]:
                            player = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and get_role(x, 'role') not in WOLFCHAT_ROLES and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                        elif 'luck_totem2' in session[1][player][4]:
                            player = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and x != message.author.id and get_role(x, 'role') not in WOLFCHAT_ROLES and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    doom = 'lycan'
                    if [x for x in session[1][message.author.id][4] if x.startswith('doom:')]:
                        doom = [x.split(':')[1] for x in session[1][message.author.id][4] if x.startswith('doom:')].pop()
                    if doom == 'lycan':
                        await reply(message, "You have a vision that **{0}** is transforming into a savage beast tomorrow night.".format(get_name(player)))
                        session[1][player][4].append('lycanthropy')
                    elif doom == 'death':
                        await reply(message, "You have a vision that **{0}** will meet an untimely end tonight.".format(get_name(player)))
                        session[1][message.author.id][4].append('doomdeath:{}'.format(player))
                    elif doom == 'sick':
                        await reply(message, "You have a vision that **{0}** will become incredibly ill tomorrow and unable to do anything.".format(get_name(player)))
                        session[1][player][4].append('sick')
                    try:
                        session[1][message.author.id][4].remove('doom:{}'.format(doom))
                    except ValueError as e:
                        await log(2, "```py\n{}\n```".format(traceback.format_exc()))
                    await log(1, "{} ({}) {} DOOM {} ({})".format(get_name(message.author.id), message.author.id, doom,
                        get_name(player), player))
            else:
                await reply(message, "Could not find player " + parameters)

@cmd('bless', [2, 0], "```\n{0}bless <player>\n\nIf you are a priest, gives a blessing to <player>```")
async def cmd_bless(message, parameters):
    if not session[0] or message.author.id not in session[1] or not session[1][message.author.id][0]:
        return
    role = get_role(message.author.id, 'role')
    if role not in COMMANDS_FOR_ROLE['bless']:
        return
    if not session[2]:
        await reply(message, "You may only bless during the day.")
        return
    if 'bless' not in session[1][message.author.id][4]:
        await reply(message, "You have already blessed someone this game.")
        return
    if "silence_totem2" in session[1][message.author.id][4]:
        await reply(message, "You have been silenced, and are unable to use any special powers.")
        return
    else:
        if parameters == "":
            await reply(message, roles[role][2])
        else:
            player = get_player(parameters)
            if player:
                if player == message.author.id:
                    await reply(message, "You may not bless yourself.")
                elif not session[1][player][0]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                else:
                    session[1][message.author.id][4].remove('bless')
                    if 'misdirection_totem2' in session[1][message.author.id][4]:
                        player = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    elif 'luck_totem2' in session[1][player][4]:
                        player = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and x != message.author.id and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    await reply(message, "You have given a blessing to **{0}**.".format(get_name(player)))
                    session[1][player][3].append('blessed')
                    member = client.get_server(WEREWOLF_SERVER).get_member(player)
                    if member:
                        try:
                            await client.send_message(member, "You suddenly feel very safe.")
                        except discord.Forbidden:
                            pass
                    await log(1, "{} ({}) BLESS {} ({})".format(get_name(message.author.id), message.author.id,
                        get_name(player), player))

@cmd('consecrate', [2, 0], "```\n{0}consecrate <player>\n\nIf you are a priest, prevents <player> if they are a vengeful ghost from killing the following night, doing so removes your ability to participate in the vote that day```")
async def cmd_consecrate(message, parameters):
    if not session[0] or message.author.id not in session[1] or not session[1][message.author.id][0]:
        return
    role = get_role(message.author.id, 'role')
    if role not in COMMANDS_FOR_ROLE['consecrate']:
        return
    if not session[2]:
        return
    if 'consecrated' in session[1][message.author.id][4]:
        return
    if "silence_totem2" in session[1][message.author.id][4]:
        await reply(message, "You have been silenced, and are unable to use any special powers.")
        return
    else:
        if parameters == "":
            await reply(message, roles[role][2])
        else:
            player = get_player(parameters)
            if player:
                if session[1][player][0]:
                    await reply(message, "**{0}** is not dead.".format(get_name(player)))
                else:
                    if 'misdirection_totem2' in session[1][message.author.id][4]:
                        player = misdirect(message.author.id, alive_players=[x for x in session[1] if not session[1][x][0]])
                    elif 'luck_totem2' in session[1][player][4]:
                        player = misdirect(player, alive_players=[x for x in session[1] if not session[1][x][0]])
                    await reply(message, "You have consecrated the body of **{0}**.".format(get_name(player)))
                    session[1][player][4].append('consecrated')
                    session[1][message.author.id][4].append('consecrated')
                    session[1][message.author.id][4].append('injured')
                    session[1][message.author.id][2] = ''
                    await log(1, "{} ({}) CONSECRATE {} ({})".format(get_name(message.author.id), message.author.id,
                        get_name(player), player))

@cmd('hex', [2, 0], "```\n{0}hex <player>\n\nIf you are a hag, hexes <player>```")
async def cmd_hex(message, parameters):
    if not session[0] or message.author.id not in session[1] or not session[1][message.author.id][0]:
        return
    if get_role(message.author.id, 'role') not in COMMANDS_FOR_ROLE['hex']:
        return
    if session[2]:
        return
    if session[1][message.author.id][2]:
        await reply(message, "You have already hexed someone tonight.")
        return
    if "silence_totem2" in session[1][message.author.id][4]:
        await reply(message, "You have been silenced, and are unable to use any special powers.")
        return
    else:
        if parameters == "":
            await reply(message, roles[role][2])
        else:
            player = get_player(parameters)
            if player:
                if not session[1][player][0]:
                    await reply(message, "**{0}** is dead.".format(get_name(player)))
                elif 'lasttarget:{}'.format(player) in session[1][message.author.id][4]:
                    await reply(message, "You hexed **{0}** last night. You cannot hex the same person two nights in a row.".format(get_name(player)))
                elif 'entranced' in session[1][message.author.id][4] and get_role(player, 'role') == 'succubus':
                    await reply(message, "You may not hex a succubus.")
                elif get_role(player, 'role') in WOLFCHAT_ROLES:
                    await reply(message, "Hexing a wolf would be a waste.")
                else:
                    if 'misdirection_totem2' in session[1][message.author.id][4]:
                        player = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and get_role(x, 'role') not in WOLFCHAT_ROLES and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    elif 'luck_totem2' in session[1][player][4]:
                        player = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and get_role(x, 'role') not in WOLFCHAT_ROLES and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    await reply(message, "You have cast a hex on **{0}**.".format(get_name(player)))
                    await wolfchat("**{0}** has cast a hex on **{1}**.".format(get_name(message.author.id), get_name(player)))
                    session[1][message.author.id][2] = player
                    session[1][message.author.id][4] = [x for x in session[1][message.author.id][4] if not x.startswith('lasttarget:')] + ['lasttarget:{}'.format(player)]
                    await log(1, "{} ({}) HEX {} ({})".format(get_name(message.author.id), message.author.id,
                        get_name(player), player))

@cmd('choose', [2, 0], "```\n{0}choose <player1> and <player2>\n\nIf you are a matchmaker, Selects two players to fall in love. You may select yourself as one of the lovers.```", 'match')
async def cmd_choose(message, parameters):
    if not session[0] or get_role(message.author.id, 'role') not in COMMANDS_FOR_ROLE['choose'] or not session[1][message.author.id][0] or not message.channel.is_private:
        return
    if parameters == "":
        await reply(message, roles[session[1][message.author.id][1]][2].format(BOT_PREFIX))
    else:
        if get_role(message.author.id, 'role') == 'matchmaker':
            if 'match' not in session[1][message.author.id][4]:
                await reply(message, "You have already chosen lovers.")
                return
            targets = parameters.split(' and ')
            if len(targets) == 2:
                actual_targets = []
                for target in targets:
                    player = get_player(target)
                    if not player:
                        await reply(message, "Could not find player " + target)
                        return
                    actual_targets.append(player)
                actual_targets = set(actual_targets)
                valid_targets = []
                if len(actual_targets) != 2:
                    await reply(message, "You may only choose **2** unique players to match.")
                    return
                for player in actual_targets:
                    if not session[1][player][0]:
                        await reply(message, "Player **" + get_name(player) + "** is dead!")
                        return
                    else:
                        valid_targets.append(player)
                valid_targets = sort_players(valid_targets)
                redirected_targets = []
                for player in valid_targets:
                    if 'misdirection_totem2' in session[1][message.author.id][4]:
                        new_target = misdirect(message.author.id)
                        while new_target in redirected_targets:
                            new_target = misdirect(message.author.id)
                        redirected_targets.append(new_target)
                    elif 'luck_totem2' in session[1][player][4]:
                        new_target = misdirect(player)
                        while new_target in redirected_targets:
                            new_target = misdirect(message.author.id)
                        redirected_targets.append(new_target)
                    else:
                        redirected_targets.append(player)
                await reply(message, "You have selected **{}** and **{}** to be lovers.".format(*map(get_name, redirected_targets)))
                session[1][message.author.id][4].remove('match')
                player1 = redirected_targets[0]
                player2 = redirected_targets[1]
                if "lover:" + player2 not in session[1][player1][4]:
                    session[1][player1][4].append("lover:" + player2)
                if "lover:" + player1 not in session[1][player2][4]:
                    session[1][player2][4].append("lover:" + player1)
                await log(1, "{} ({}) CHOOSE {} ({}) AND {} ({})".format(get_name(message.author.id), message.author.id,
                    get_name(player1), player1, get_name(player2), player2))
                love_msg = "You are in love with **{}**. If that player dies for any reason, the pain will be too much for you to bear and you will commit suicide."
                member1 = client.get_server(WEREWOLF_SERVER).get_member(player1)
                member2 = client.get_server(WEREWOLF_SERVER).get_member(player2)
                if member1:
                    try:
                        await client.send_message(member1, love_msg.format(get_name(player2)))
                    except discord.Forbidden:
                        pass
                if member2:
                    try:
                        await client.send_message(member2, love_msg.format(get_name(player1)))
                    except discord.Forbidden:
                        pass
            else:
                await reply(message, "You must choose two different players.")

@cmd('kill', [2, 0], "```\n{0}kill <player>\n\nIf you are a wolf, casts your vote to target <player>. If you are a "
                     "hunter or a vengeful ghost, <player> will die the following night.```")
async def cmd_kill(message, parameters):
    if not session[0] or message.author.id not in session[1] or get_role(message.author.id, 'role') not in COMMANDS_FOR_ROLE['kill']:
        return
    if get_role(message.author.id, 'role') == "vengeful ghost":
        if session[1][message.author.id][0] or not [x for x in session[1][message.author.id][4] if x.startswith("vengeance:")]:
            return
    if session[2]:
        await reply(message, "You may only kill someone during the night.")
        return
    if parameters == "":
        await reply(message, roles[session[1][message.author.id][1]][2])
    else:
        if get_role(message.author.id, 'role') == 'hunter':
            if 'hunterbullet' not in session[1][message.author.id][4]:
                await reply(message, "You have already killed someone this game.")
                return
            elif session[1][message.author.id][2] not in ['', message.author.id]:
                await reply(message, "You have already chosen to kill **{}**.".format(get_name(session[1][message.author.id][2])))
                return
            if "silence_totem2" in session[1][message.author.id][4]:
                await reply(message, "You have been silenced, and are unable to use any special powers.")
                return
            player = get_player(parameters)
            if 'misdirection_totem2' in session[1][message.author.id][4]:
                player = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
            elif 'luck_totem2' in session[1][player][4]:
                player = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and x != message.author.id and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
            if player:
                if player == message.author.id:
                    await reply(message, "Suicide is bad for you.")
                elif 'entranced' in session[1][message.author.id][4] and get_role(player, 'role') == 'succubus':
                    await reply(message, "You may not kill a succubus.")
                elif not session[1][player][0]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                else:
                    session[1][message.author.id][2] = player
                    await reply(message, "You have chosen to kill **" + get_name(player) + "** tonight.")
                    await log(1, "{0} ({1}) HUNTERKILL {2} ({3})".format(get_name(message.author.id), message.author.id, get_name(player), player))
            else:
                await reply(message, "Could not find player " + parameters)
        elif roles[get_role(message.author.id, 'role')][0] == 'wolf':
            num_kills = session[1][message.author.id][4].count('angry') + 1
            targets = parameters.split(' and ')
            actual_targets = []
            for target in targets:
                player = get_player(target)
                if not player:
                    await reply(message, "Could not find player " + target)
                    return
                actual_targets.append(player)
            actual_targets = set(actual_targets)
            valid_targets = []
            if len(actual_targets) > num_kills:
                await reply(message, "You may only kill **{}** targets.".format(num_kills))
                return
            for player in actual_targets:
                if player == message.author.id:
                    await reply(message, "Suicide is bad for you.")
                    return
                elif 'entranced' in session[1][message.author.id][4] and get_role(player, 'role') == 'succubus':
                    await reply(message, "You may not kill a succubus.")
                    return
                elif get_role(message.author.id, 'actualteam') == 'wolf' and \
                get_role(player, 'actualteam') == 'wolf' and get_role(player, 'role') not in ['minion', 'cultist']:
                    await reply(message, "You can't kill another wolf.")
                    return
                elif not session[1][player][0]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                    return
                else:
                    if "silence_totem2" in session[1][message.author.id][4]:
                        await reply(message, "You have been silenced, and are unable to use any special powers.")
                        return
                    elif "ill_wolf" in session[1][message.author.id][4]:
                        await reply(message, "You are feeling ill tonight, and are unable to kill anyone.")
                        return
                    valid_targets.append(player)
            valid_targets = sort_players(valid_targets)
            redirected_targets = []
            for player in valid_targets:
                if 'misdirection_totem2' in session[1][message.author.id][4]:
                    new_target = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and get_role(x, "role") not in WOLFCHAT_ROLES and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    while new_target in redirected_targets:
                        new_target = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and get_role(x, "role") not in WOLFCHAT_ROLES and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    redirected_targets.append(new_target)
                elif 'luck_totem2' in session[1][player][4]:
                    new_target = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and get_role(x, "role") not in WOLFCHAT_ROLES])
                    while new_target in redirected_targets:
                        new_target = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and get_role(x, "role") not in WOLFCHAT_ROLES])
                    redirected_targets.append(new_target)
                else:
                    redirected_targets.append(player)
            session[1][message.author.id][2] = ','.join(redirected_targets)
            await reply(message, "You have voted to kill **{}**.".format('** and **'.join(
                map(get_name, valid_targets))))
            await wolfchat("**{}** has voted to kill **{}**.".format(get_name(message.author.id), '** and **'.join(
                map(get_name, valid_targets))))
            await log(1, "{0} ({1}) KILL {2} ({3})".format(get_name(message.author.id), message.author.id,
            ' and '.join(map(get_name, valid_targets)), ','.join(valid_targets)))
        elif get_role(message.author.id, 'role') == 'vengeful ghost' and 'consecrated' not in session[1][message.author.id][4] and 'driven' not in session[1][message.author.id][4]:
            if session[1][message.author.id][2] != '':
                await reply(message, "You have already chosen to kill **{}**.".format(get_name(session[1][message.author.id][2])))
                return
            player = get_player(parameters)
            against = 'wolf'
            if [x for x in session[1][message.author.id][4] if x.startswith("vengeance:")]:
                against = [x.split(":")[1] for x in session[1][message.author.id][4] if x.startswith("vengeance:")].pop()
            if player:
                if player == message.author.id:
                    return
                elif not session[1][player][0]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                elif get_role(player, 'actualteam') != against:
                    await reply(message, "You must target a {}.".format('villager' if against == 'village' else 'wolf'))
                else:
                    session[1][message.author.id][2] = player
                    await reply(message, "You have chosen to kill **" + get_name(player) + "** tonight.")
                    await log(1, "{0} ({1}) VENGEFUL KILL {2} ({3})".format(get_name(message.author.id), message.author.id, get_name(player), player))

@cmd('vote', [0, 0], "```\n{0}vote [<gamemode | player>]\n\nVotes for <gamemode> during the join phase or votes to lynch <player> during the day. If no arguments "
                     "are given, replies with a list of current votes.```", 'v')
async def cmd_vote(message, parameters):
    if session[0]:
        await cmd_lynch(message, parameters)
    else:
        if message.channel.is_private:
            await reply(message, "Please use vote in channel.")
            return
        if parameters == "":
            await cmd_votes(message, parameters)
        else:
            if session[6]:
                await reply(message, "An admin has already set a gamemode.")
                return
            if message.author.id in session[1]:
                choice, num = _autocomplete(parameters, gamemodes)
                if num == 0:
                    await reply(message, "Could not find gamemode {}".format(parameters))
                elif num == 1:
                    session[1][message.author.id][2] = choice
                    await reply(message, "You have voted for the **{}** gamemode.".format(choice))
                else:
                    await reply(message, "Multiple options: {}".format(', '.join(sorted(choice))))
            else:
                await reply(message, "You cannot vote for a gamemode if you are not playing!")

@cmd('lynch', [0, 0], "```\n{0}lynch [<player>]\n\nVotes to lynch [<player>] during the day. If no arguments are given, replies with a list of current votes.```")
async def cmd_lynch(message, parameters):
    if not session[0] or not session[2]:
        return
    if parameters == "":
        await cmd_votes(message, parameters)
    else:
        if message.author.id not in session[1]:
            return
        if message.channel.is_private:
            await reply(message, "Please use lynch in channel.")
            return
        if 'illness' in session[1][message.author.id][4]:
            try:
                await client.send_message(message.author, "You are staying home due to your illness and cannot participate in the vote.")
            except discord.Forbidden:
                pass
            return
        if 'injured' in session[1][message.author.id][4]:
            await reply(message, "You are injured and unable to vote.")
            return
        to_lynch = get_player(parameters.split(' ')[0])
        if not to_lynch:
            to_lynch = get_player(parameters)
        if to_lynch:
            if not session[1][to_lynch][0]:
                await reply(message, "Player **" + get_name(to_lynch) + "** is dead!")
            else:
                session[1][message.author.id][2] = to_lynch
                await reply(message, "You have voted to lynch **" + get_name(to_lynch) + "**.")
                vote_list = list(chain.from_iterable([[int(i.split(':')[1]) for i in session[1][x][4] if i.startswith("vote:")] for x in session[1]]))
                if len(vote_list) == 0:
                    session[1][message.author.id][4].append("vote:1")
                else:
                    session[1][message.author.id][4] = [x for x in session[1][message.author.id][4] if not x.startswith('vote:')]
                    session[1][message.author.id][4].append("vote:{}".format(max(vote_list) + 1))
                await log(1, "{0} ({1}) LYNCH {2} ({3})".format(get_name(message.author.id), message.author.id, get_name(to_lynch), to_lynch))
        else:
            await reply(message, "Could not find player " + parameters)

@cmd('votes', [0, 0], "```\n{0}votes takes no arguments\n\nDisplays votes for gamemodes during the join phase or current votes to lynch during the day.```")
async def cmd_votes(message, parameters):
    if not session[0]:
        vote_dict = {'start' : []}
        for player in session[1]:
            if session[1][player][2] in vote_dict:
                vote_dict[session[1][player][2]].append(player)
            elif session[1][player][2] != '':
                vote_dict[session[1][player][2]] = [player]
            if session[1][player][1] == 'start':
                vote_dict['start'].append(player)
        reply_msg = "**{}** player{} in the lobby, **{}** vote{} required to choose a gamemode, **{}** votes needed to start.```\n".format(
            len(session[1]), '' if len(session[1]) == 1 else 's', len(session[1]) // 2 + 1, '' if len(session[1]) // 2 + 1 == 1 else 's',
            max(2, min(len(session[1]) // 4 + 1, 4)))
        for gamemode in vote_dict:
            if gamemode == 'start':
                continue
            reply_msg += "{} ({} vote{}): {}\n".format(gamemode, len(vote_dict[gamemode]), '' if len(vote_dict[gamemode]) == 1 else 's',
                                                     ', '.join(map(get_name, vote_dict[gamemode])))
        reply_msg += "{} vote{} to start: {}\n```".format(len(vote_dict['start']), '' if len(vote_dict['start']) == 1 else 's',
                                                       ', '.join(map(get_name, vote_dict['start'])))
        await reply(message, reply_msg)
    elif session[0] and session[2]:
        vote_dict = {'abstain': []}
        alive_players = [x for x in session[1] if session[1][x][0]]
        able_voters = [x for x in alive_players if 'injured' not in session[1][x][4]]
        for player in able_voters:
            if session[1][player][2] in vote_dict:
                vote_dict[session[1][player][2]].append(player)
            elif session[1][player][2] != '':
                vote_dict[session[1][player][2]] = [player]
        abstainers = vote_dict['abstain']
        reply_msg = "**{}** living players, **{}** votes required to lynch, **{}** players available to vote, **{}** player{} refrained from voting.\n".format(
            len(alive_players), len(able_voters) // 2 + 1, len(able_voters), len(abstainers), '' if len(abstainers) == 1 else 's')

        if len(vote_dict) == 1 and vote_dict['abstain'] == []:
            reply_msg += "No one has cast a vote yet. Do `{}lynch <player>` in #{} to lynch <player>. ".format(BOT_PREFIX, client.get_channel(GAME_CHANNEL).name)
        else:
            reply_msg += "Current votes: ```\n"
            for voted in [x for x in vote_dict if x != 'abstain']:
                reply_msg += "{} ({}) ({} vote{}): {}\n".format(
                    get_name(voted), voted, len(vote_dict[voted]), '' if len(vote_dict[voted]) == 1 else 's', ', '.join(['{} ({})'.format(get_name(x), x) for x in vote_dict[voted]]))
            reply_msg += "{} vote{} to abstain: {}\n".format(
                len(vote_dict['abstain']), '' if len(vote_dict['abstain']) == 1 else 's', ', '.join(['{} ({})'.format(get_name(x), x) for x in vote_dict['abstain']]))
            reply_msg += "```"
        await reply(message, reply_msg)

@cmd('retract', [0, 0], "```\n{0}retract takes no arguments\n\nRetracts your gamemode and vote to start during the join phase, "
                        "or retracts your vote to lynch or kill during the game.```", 'r')
async def cmd_retract(message, parameters):
    if message.author.id not in session[1]:
        # not playing
        return
    if not session[0] and session[1][message.author.id][2] == '' and session[1][message.author.id][1] == '':
        # no vote to start nor vote for gamemode
        return
    if session[0] and session[1][message.author.id][2] == '':
        # no target
        return
    if not session[0]:
        if message.channel.is_private:
            await reply(message, "Please use retract in channel.")
            return
        session[1][message.author.id][2] = ''
        session[1][message.author.id][1] = ''
        await reply(message, "You retracted your vote.")
        session[1][message.author.id][4] = [x for x in session[1][message.author.id][4] if not x.startswith("vote:")]
    elif session[0] and session[1][message.author.id][0]:
        if session[2]:
            if message.channel.is_private:
                await reply(message, "Please use retract in channel.")
                return
            session[1][message.author.id][2] = ''
            await reply(message, "You retracted your vote.")
            await log(1, "{0} ({1}) RETRACT VOTE".format(get_name(message.author.id), message.author.id))
        else:
            if session[1][message.author.id][1] in COMMANDS_FOR_ROLE['kill']:
                if get_role(message.author.id, 'actualrole') == ('hunter' or 'vengeful ghost'):
                    return
                if not message.channel.is_private:
                    try:
                        await client.send_message(message.author, "Please use retract in pm.")
                    except discord.Forbidden:
                        pass
                    return
                session[1][message.author.id][2] = ''
                await reply(message, "You retracted your kill.")
                await wolfchat("**{}** has retracted their kill.".format(get_name(message.author.id)))
                await log(1, "{0} ({1}) RETRACT KILL".format(get_name(message.author.id), message.author.id))

@cmd('abstain', [0, 2], "```\n{0}abstain takes no arguments\n\nRefrain from voting someone today.```", 'abs', 'nl')
async def cmd_abstain(message, parameters):
    if not session[0] or not session[2] or not message.author.id in session[1] or not session[1][message.author.id][0]:
        return
    if session[6] == 'evilvillage':
        await send_lobby("The evilvillage cannot abstain.")
        return
    if session[4][1] == timedelta(0):
        await send_lobby("The village may not abstain on the first day.")
        return
    if 'injured' in session[1][message.author.id][4]:
        await reply(message, "You are injured and unable to vote.")
        return
    session[1][message.author.id][2] = 'abstain'
    await log(1, "{0} ({1}) ABSTAIN".format(get_name(message.author.id), message.author.id))
    await send_lobby("**{}** votes to not lynch anyone today.".format(get_name(message.author.id)))

@cmd('coin', [0, 0], "```\n{0}coin takes no arguments\n\nFlips a coin. Don't use this for decision-making, especially not for life or death situations.```")
async def cmd_coin(message, parameters):
    value = random.randint(1,100)
    reply_msg = ''
    if value == 1:
        reply_msg = 'its side'
    elif value == 100:
        reply_msg = client.user.name
    elif value < 50:
        reply_msg = 'heads'
    else:
        reply_msg = 'tails'
    await reply(message, 'The coin landed on **' + reply_msg + '**!')

@cmd('admins', [0, 0], "```\n{0}admins takes no arguments\n\nLists online/idle admins if used in pm, and **alerts** online/idle admins if used in channel (**USE ONLY WHEN NEEDED**).```")
async def cmd_admins(message, parameters):
    await reply(message, 'Available admins: ' + ', '.join('<@{}>'.format(x) for x in ADMINS if is_online(x)), cleanmessage=False)

@cmd('fday', [1, 2], "```\n{0}fday takes no arguments\n\nForces night to end.```")
async def cmd_fday(message, parameters):
    if session[0] and not session[2]:
        session[2] = True
        await reply(message, ":thumbsup:")
        await log(2, "{0} ({1}) FDAY".format(message.author.name, message.author.id))

@cmd('fnight', [1, 2], "```\n{0}fnight takes no arguments\n\nForces day to end.```")
async def cmd_fnight(message, parameters):
    if session[0] and session[2]:
        session[2] = False
        await reply(message, ":thumbsup:")
        await log(2, "{0} ({1}) FNIGHT".format(message.author.name, message.author.id))

@cmd('frole', [1, 2], "```\n{0}frole <player> <role>\n\nSets <player>'s role to <role>.```")
async def cmd_frole(message, parameters):
    if parameters == '':
        return
    player = parameters.split(' ')[0]
    role = parameters.split(' ', 1)[1]
    temp_player = get_player(player)
    if temp_player:
        if session[0]:
            if role in roles or role in ['cursed']:
                if role not in ['cursed'] + TEMPLATES_ORDERED:
                    session[1][temp_player][1] = role
                if role == 'cursed villager':
                    session[1][temp_player][1] = 'villager'
                    for i in range(session[1][temp_player][3].count('cursed')):
                        session[1][temp_player][3].remove('cursed')
                    session[1][temp_player][3].append('cursed')
                elif role == 'cursed':
                    for i in range(session[1][temp_player][3].count('cursed')):
                        session[1][temp_player][3].remove('cursed')
                    session[1][temp_player][3].append('cursed')
                elif role in TEMPLATES_ORDERED:
                    for i in range(session[1][temp_player][3].count(role)):
                        session[1][temp_player][3].remove(role)
                    session[1][temp_player][3].append(role)
                await reply(message, "Successfully set **{}**'s role to **{}**.".format(get_name(temp_player), role))
            else:
                await reply(message, "Cannot find role named **" + role + "**")
        else:
            session[1][temp_player][1] = role
    else:
        await reply(message, "Cannot find player named **" + player + "**")
    await log(2, "{0} ({1}) FROLE {2}".format(message.author.name, message.author.id, parameters))

@cmd('force', [1, 2], "```\n{0}force <player> <target>\n\nSets <player>'s target flag (session[1][player][2]) to <target>.```")
async def cmd_force(message, parameters):
    if parameters == '':
        await reply(message, commands['force'][2].format(BOT_PREFIX))
        return
    player = parameters.split(' ')[0]
    target = ' '.join(parameters.split(' ')[1:])
    temp_player = get_player(player)
    if temp_player:
        session[1][temp_player][2] = target
        await reply(message, "Successfully set **{}**'s target to **{}**.".format(get_name(temp_player), target))
    else:
        await reply(message, "Cannot find player named **" + player + "**")
    await log(2, "{0} ({1}) FORCE {2}".format(message.author.name, message.author.id, parameters))

@cmd('session', [1, 1], "```\n{0}session takes no arguments\n\nReplies with the contents of the session variable in pm for debugging purposes. Admin only.```")
async def cmd_session(message, parameters):
    await client.send_message(message.author, "```py\n{}\n```".format(str(session)))
    await log(2, "{0} ({1}) SESSION".format(message.author.name, message.author.id))

@cmd('time', [0, 0], "```\n{0}time takes no arguments\n\nChecks in-game time.```", 't')
async def cmd_time(message, parameters):
    if session[0]:
        seconds = 0
        timeofday = ''
        sunstate = ''
        if session[2]:
            seconds = DAY_TIMEOUT - (datetime.now() - session[3][1]).seconds
            timeofday = 'daytime'
            sunstate = 'sunset'
        else:
            seconds = NIGHT_TIMEOUT - (datetime.now() - session[3][0]).seconds
            timeofday = 'nighttime'
            sunstate = 'sunrise'
        await reply(message, "It is now **{0}**. There is **{1:02d}:{2:02d}** until {3}.".format(timeofday, seconds // 60, seconds % 60, sunstate))
    else:
        if len(session[1]) > 0:
            timeleft = GAME_START_TIMEOUT - (datetime.now() - session[5]).seconds
            await reply(message, "There is **{0:02d}:{1:02d}** left to start the game until it will be automatically cancelled. "
                                 "GAME_START_TIMEOUT is currently set to **{2:02d}:{3:02d}**.".format(
                                     timeleft // 60, timeleft % 60, GAME_START_TIMEOUT // 60, GAME_START_TIMEOUT % 60))

@cmd('give', [2, 0], "```\n{0}give <player>\n\nIf you are a shaman or wolf shaman, gives your totem to <player>. You can see your totem by using `myrole` in pm.```")
async def cmd_give(message, parameters):
    if not session[0] or message.author.id not in session[1] or session[1][message.author.id][1] not in ['shaman', 'crazed shaman', 'wolf shaman'] or not session[1][message.author.id][0]:
        return
    if session[2]:
        await reply(message, "You may only give totems during the night.")
        return
    if session[1][message.author.id][2] not in totems and session[1][message.author.id][1] != 'wolf shaman':
        await reply(message, "You have already given your totem to **" + get_name(session[1][message.author.id][2]) + "**.")
        return
    elif session[1][message.author.id][1] == 'wolf shaman' and not [x for x in session[1][message.author.id][4] if x.startswith('totem:')]:
        given_to = [x.split(":")[1] for x in session[1][message.author.id][4] if x.startswith('lasttarget:')]
        if given_to:
            await reply(message, "You have already given your totem to **{}**.".format(get_name(given_to[0])))
            return
    if "silence_totem2" in session[1][message.author.id][4]:
        await reply(message, "You have been silenced, and are unable to use any special powers.")
        return
    else:
        if parameters == "":
            await reply(message, roles[session[1][message.author.id][1]][2])
        else:
            player = get_player(parameters)
            if player:
                if not session[1][player][0]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                else:
                    if 'lasttarget:{}'.format(player) in session[1][message.author.id][4]:
                        await reply(message, "You gave your totem to **{}** last time, you must choose someone else.".format(get_name(player)))
                        return
                    if session[1][message.author.id][1] in ["shaman", "crazed shaman"]:
                        totem = session[1][message.author.id][2]
                    else:
                        totem = [x for x in session[1][message.author.id][4] if x.startswith("totem:")][0].split(':')[1]
                    if 'misdirection_totem2' in session[1][message.author.id][4]:
                        player = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    elif 'luck_totem2' in session[1][player][4]:
                        player = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and x != message.author.id and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    session[1][player][4].append(totem)
                    if session[1][message.author.id][1] == "wolf shaman":
                        session[1][message.author.id][4] = [x for x in session[1][message.author.id][4] if x != "totem:{}".format(totem)]

                    else:
                        if 'entranced' in session[1][message.author.id][4] and get_role(player, 'role') == 'succubus' and totem not in ["protection_totem", "revealing_totem", "desperation_totem", "influence_totem", "luck_totem", "pestilence_totem", "retribution_totem"]:
                            await reply(message, "You may not give a harmful totem to a succubus.")
                            return
                        session[1][message.author.id][2] = player
                        session[1][message.author.id][4] = [x for x in session[1][message.author.id][4] if not x.startswith('lasttarget:')] + ['lasttarget:{}'.format(player)]
                    await reply(message, "You have given your totem to **" + get_name(player) + "**.")
                    if session[1][message.author.id][1] == 'wolf shaman':
                        await wolfchat("**{0}** has given a totem to **{1}**.".format(get_name(message.author.id), get_name(player)))
                    session[1][message.author.id][4].append('given:{}'.format(totem))
                    await log(1, "{0} ({1}) GAVE {2} ({3}) {4}".format(get_name(message.author.id), message.author.id, get_name(player), player, totem))
            else:
                await reply(message, "Could not find player " + parameters)

@cmd('info', [0, 0], "```\n{0}info takes no arguments\n\nGives information on how the game works.```")
async def cmd_info(message, parameters):
    msg = "In Werewolf, there are two teams, village and wolves. The villagers try to get rid of all of the wolves, and the wolves try to kill all of the villagers.\n"
    msg += "There are two phases, night and day. During night, the wolf/wolves choose a target to kill, and some special village roles like seer perform their actions. "
    msg += "During day, the village discusses everything and chooses someone to lynch. "
    msg += "Once you die, you can't talk in the lobby channel but you can discuss the game with the spectators in #spectator-chat.\n\n"
    msg += "To join a game, use `{0}join`. If you cannot chat in #lobby, then either a game is ongoing or you are dead.\n"
    msg += "For a list of roles, use the command `{0}roles`. For information on a particular role, use `{0}role role`. For statistics on the current game, use `{0}stats`. "
    msg += "For a list of commands, use `{0}list`. For help on a command, use `{0}help command`. To see the in-game time, use `{0}time`.\n\n"
    msg += "Please let belungawhale know about any bugs you might find."
    await reply(message, msg.format(BOT_PREFIX))

@cmd('notify_role', [0, 0], "```\n{0}notify_role [<true|false>]\n\nGives or take the " + WEREWOLF_NOTIFY_ROLE_NAME + " role.```")
async def cmd_notify_role(message, parameters):
    if not WEREWOLF_NOTIFY_ROLE:
        await reply(message, "Error: A " + WEREWOLF_NOTIFY_ROLE_NAME + " role does not exist. Please let an admin know.")
        return
    member = client.get_server(WEREWOLF_SERVER).get_member(message.author.id)
    if not member:
        await reply(message, "You are not in the server!")
    has_role = WEREWOLF_NOTIFY_ROLE in member.roles
    if parameters == '':
        has_role = not has_role
    elif parameters in ['true', '+', 'yes']:
        has_role = True
    elif parameters in ['false', '-', 'no']:
        has_role = False
    else:
        await reply(message, commands['notify_role'][2].format(BOT_PREFIX))
        return
    if has_role:
        await client.add_roles(member, WEREWOLF_NOTIFY_ROLE)
        await reply(message, "You will be notified by @" + WEREWOLF_NOTIFY_ROLE.name + ".")
    else:
        await client.remove_roles(member, WEREWOLF_NOTIFY_ROLE)
        await reply(message, "You will not be notified by @" + WEREWOLF_NOTIFY_ROLE.name + ".")

@cmd('ignore', [1, 1], "```\n{0}ignore <add|remove|list> <user>\n\nAdds or removes <user> from the ignore list, or outputs the ignore list.```")
async def cmd_ignore(message, parameters):
    parameters = ' '.join(message.content.strip().split(' ')[1:])
    parameters = parameters.strip()
    global IGNORE_LIST
    if parameters == '':
        await reply(message, commands['ignore'][2].format(BOT_PREFIX))
    else:
        action = parameters.split(' ')[0].lower()
        target = ' '.join(parameters.split(' ')[1:])
        member_by_id = client.get_server(WEREWOLF_SERVER).get_member(target.strip('<@!>'))
        member_by_name = client.get_server(WEREWOLF_SERVER).get_member_named(target)
        member = None
        if member_by_id:
            member = member_by_id
        elif member_by_name:
            member = member_by_name
        if action not in ['+', 'add', '-', 'remove', 'list']:
            await reply(message, "Error: invalid flag `" + action + "`. Supported flags are add, remove, list")
            return
        if not member and action != 'list':
            await reply(message, "Error: could not find target " + target)
            return
        if action in ['+', 'add']:
            if member.id in IGNORE_LIST:
                await reply(message, member.name + " is already in the ignore list!")
            else:
                IGNORE_LIST.append(member.id)
                await reply(message, member.name + " was added to the ignore list.")
        elif action in ['-', 'remove']:
            if member.id in IGNORE_LIST:
                IGNORE_LIST.remove(member.id)
                await reply(message, member.name + " was removed from the ignore list.")
            else:
                await reply(message, member.name + " is not in the ignore list!")
        elif action == 'list':
            if len(IGNORE_LIST) == 0:
                await reply(message, "The ignore list is empty.")
            else:
                msg_dict = {}
                for ignored in IGNORE_LIST:
                    member = client.get_server(WEREWOLF_SERVER).get_member(ignored)
                    msg_dict[ignored] = member.name if member else "<user not in server with id " + ignored + ">"
                await reply(message, str(len(IGNORE_LIST)) + " ignored users:\n```\n" + '\n'.join([x + " (" + msg_dict[x] + ")" for x in msg_dict]) + "```")
        else:
            await reply(message, commands['ignore'][2].format(BOT_PREFIX))
        await log(2, "{0} ({1}) IGNORE {2}".format(message.author.name, message.author.id, parameters))

# TODO
async def cmd_pingif(message, parameters):
    global pingif_dict
    if parameters == '':
        if message.author.id in pingif_dict:
            await reply(message, "You will be notified when there are at least **{}** players.".format(pingif_dict[message.author.id]))
        else:
            await reply(message, "You have not set a pingif yet. `{}pingif <number of players>`".format(BOT_PREFIX))
    elif parameters.isdigit():
        num = int(parameters)
        if num in range(MIN_PLAYERS, MAX_PLAYERS + 1):
            pingif_dict[message.author.id] = num
            await reply(message, "You will be notified when there are at least **{}** players.".format(pingif_dict[message.author.id]))
        else:
            await reply(message, "Please enter a number between {} and {} players.".format(MIN_PLAYERS, MAX_PLAYERS))
    else:
        await reply(message, "Please enter a valid number of players to be notified at.")

@cmd('online', [1, 1], "```\n{0}online takes no arguments\n\nNotifies all online users.```")
async def cmd_online(message, parameters):
    members = [x.id for x in message.server.members]
    online = ["<@{}>".format(x) for x in members if is_online(x)]
    await reply(message, "PING! {}".format(''.join(online)), cleanmessage=False)

@cmd('notify', [0, 0], "```\n{0}notify [<true|false>]\n\nNotifies all online users who want to be notified, or adds/removes you from the notify list.```")
async def cmd_notify(message, parameters):
    if session[0]:
        return
    notify = message.author.id in notify_me
    if parameters == '':
        online = ["<@{}>".format(x) for x in notify_me if is_online(x) and x not in session[1] and\
        (x in stasis and stasis[x] == 0 or x not in stasis)]
        await reply(message, "PING! {}".format(''.join(online)), cleanmessage=False)
    elif parameters in ['true', '+', 'yes']:
        if notify:
            await reply(message, "You are already in the notify list.")
            return
        notify_me.append(message.author.id)
        await reply(message, "You will be notified by {}notify.".format(BOT_PREFIX))
    elif parameters in ['false', '-', 'no']:
        if not notify:
            await reply(message, "You are not in the notify list.")
            return
        notify_me.remove(message.author.id)
        await reply(message, "You will not be notified by {}notify.".format(BOT_PREFIX))
    else:
        await reply(message, commands['notify'][2].format(BOT_PREFIX))

@cmd('getrole', [1, 1], "```\n{0}getrole <player> <revealtype>\n\nTests get_role command.```")
async def cmd_getrole(message, parameters):
    if not session[0] or parameters == '':
        await reply(message, commands['getrole'][2].format(BOT_PREFIX))
        return
    player = parameters.split(' ')[0]
    revealtype = ' '.join(parameters.split(' ')[1:])
    temp_player = get_player(player)
    if temp_player:
        role = get_role(temp_player, revealtype)
        await reply(message, "**{}** is a **{}** using revealtype **{}**".format(get_name(temp_player), role, revealtype))
    else:
        await reply(message, "Cannot find player named **" + player + "**")

@cmd('entrance', [2, 0], "```\n{0}entrance <player>\n\nIf you are a succubus, entrances <player>. You will die if you visit the victim of the wolves.```")
async def cmd_entrance(message, parameters):
    if not session[0] or message.author.id not in session[1] or get_role(message.author.id, 'role') not in COMMANDS_FOR_ROLE['entrance'] or not session[1][message.author.id][0]:
        return
    if session[2]:
        await reply(message, "You may only entrance during the night.")
        return
    if session[1][message.author.id][2]:
        await reply(message, "You are already entrancing **{}** tonight.".format(get_name(session[1][message.author.id][2])))
        return
    if "silence_totem2" in session[1][message.author.id][4]:
        await reply(message, "You have been silenced, and are unable to use any special powers.")
        return
    else:
        if parameters == "":
            await reply(message, roles[session[1][message.author.id][1]][2])
        else:
            player = get_player(parameters)
            if player:
                if player == message.author.id:
                    await reply(message, "You may not entrance yourself. Use `pass` to not entrance anyone tonight.")
                if get_role(player, 'role') == 'succubus':
                    await reply(message, "You cannot entrance another succubus.")
                elif not session[1][player][0]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                else:
                    if 'misdirection_totem2' in session[1][message.author.id][4]:
                        player = misdirect(message.author.id)
                    elif 'luck_totem2' in session[1][player][4]:
                        player = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and x != message.author.id])
                    if 'entranced' not in session[1][player][4]:
                        await reply(message, "You are entrancing **{}** tonight.".format(get_name(player)))
                        session[1][message.author.id][2] = player
                        member = client.get_server(WEREWOLF_SERVER).get_member(player)
                        role = get_role(player, 'role')
                        templates = get_role(player, 'templates')
                        session[1][player][4].append('entranced')
                        succubus_message = "You have become entranced by **{0}**. From this point on, you must vote along with them or risk dying. You **cannot win with your own team**, but you will win should all alive players become entranced."
                        if role in COMMANDS_FOR_ROLE['kill'] and message.author.id in session[1][player][2]:
                            session[1][player][2] = ''
                            succubus_message += " You discover that **{0}** is a succubus and have retracted your kill as a result.\n".format(get_name(message.author.id))
                        if 'assassin' in templates and 'assassinate:{}'.format(message.author.id) in session[1][player][4]:
                            session[1][player][4].remove('assassinate:{}'.format(message.author.id))
                            succubus_message += " You discover that **{0}** is a succubus and must now target someone else.\n".format(get_name(message.author.id))
                        if role == 'hag' and session[1][player][2] == message.author.id:
                            succubus_message += " You discover that **{0}** is a succubus and have retracted your hex as a result.\n".format(get_name(message.author.id))
                            session[1][player][2] = ''
                            session[1][player][4].remove('lasttarget:{}'.format(message.author.id))
                        if role == 'piper' and ('tocharm' in session[1][message.author.id][4] or 'charmed' in session[1][message.author.id][4]):
                            succubus_message += " You discover that **{0}** is a succubus and have retracted your charm as a result.\n".format(get_name(message.author.id))
                            session[1][message.author.id][4] = [x for x in session[1][message.author.id][4] if x not in ['charmed', 'tocharm']]
                            session[1][player][4].append('charm')
                        if role in COMMANDS_FOR_ROLE['give']:
                            totem = ''
                            if role == 'wolf shaman' and not [x for x in session[1][player][4] if x.startswith('totem:')] and 'lasttarget:{}'.format(message.author.id) in session[1][player][4]:
                                totem = [x.split(':')[1] for x in session[1][player][4] if x.startswith('given:')].pop()
                            elif message.author.id == session[1][player][2]:
                                totem = [x.split(':')[1] for x in session[1][player][4] if x.startswith('given:')].pop()
                            if totem not in ["protection_totem", "revealing_totem", "desperation_totem", "influence_totem", "luck_totem", "pestilence_totem", "retribution_totem", '']:
                                succubus_message += " You discover that **{0}** is a succubus and have retracted your totem as a result."
                                session[1][message.author.id][4].remove(totem)
                                session[1][player][4].remove('given:{}'.format(totem))
                                session[1][player][4].remove('lasttarget:{}'.format(message.author.id))
                                if role == 'wolf shaman':
                                    session[1][player][4].append('totem:{}'.format(totem))
                                else:
                                    session[1][player][2] == totem
                        if member:
                            try:
                                await client.send_message(member, succubus_message.format(get_name(message.author.id)))
                            except discord.Forbidden:
                                pass
                        await log(1, "{0} ({1}) ENTRANCE {2} ({3})".format(get_name(message.author.id), message.author.id, get_name(player), player))
                    else:
                        await reply(message, "**{}** is already entranced.".format(get_name(player)))
            else:
                await reply(message, "Could not find player " + parameters)

@cmd('curse', [2, 0], "```\n{0}curse <player>\n\nIf you are a warlock, curses <player>. Be fast though as the curse takes effect as soon as you use the command.```")
async def cmd_curse(message, parameters):
    if not session[0] or message.author.id not in session[1] or get_role(message.author.id, 'role') not in COMMANDS_FOR_ROLE['curse'] or not session[1][message.author.id][0]:
        return
    if session[2]:
        await reply(message, "You may only curse during the night.")
        return
    if session[1][message.author.id][2]:
        await reply(message, "You have already cursed someone tonight.")
        return
    if "silence_totem2" in session[1][message.author.id][4]:
        await reply(message, "You have been silenced, and are unable to use any special powers.")
        return
    else:
        if parameters == "":
            await reply(message, roles[session[1][message.author.id][1]][2])
        else:
            player = get_player(parameters)
            if player:
                if player == message.author.id:
                    await reply(message, "That would be a waste.")
                elif player in [x for x in session[1] if roles[get_role(x, 'role')][0] == 'wolf' and get_role(x, 'role') not in ['minion', 'cultist']]:
                    await reply(message, "Cursing a fellow wolf would be a waste.")
                elif not session[1][player][0]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                elif 'entranced' in session[1][message.author.id][4] and get_role(player, 'role') == 'succubus':
                    await reply(message, "You may not curse a succubus.")
                else:
                    if 'misdirection_totem2' in session[1][message.author.id][4]:
                        player = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and get_role(x, 'role') not in WOLFCHAT_ROLES and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    elif 'luck_totem2' in session[1][player][4]:
                        player = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and get_role(x, 'role') not in WOLFCHAT_ROLES and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    templates = get_role(player, 'templates')
                    if 'cursed' not in templates:
                        await reply(message, "You have cast a curse on **{}**.".format(get_name(player)))
                        await wolfchat("**{}** has cast a curse on **{}**.".format(get_name(message.author.id), get_name(player)))
                        session[1][message.author.id][2] = player
                        session[1][player][3].append('cursed')
                        await log(1, "{0} ({1}) CURSE {2} ({3})".format(get_name(message.author.id), message.author.id, get_name(player), player))
                    else:
                        await reply(message, "**{}** is already cursed.".format(get_name(player)))
            else:
                await reply(message, "Could not find player " + parameters)

@cmd('charm', [2, 0], "```\n{0}charm <player1> [and <player2>]\n\nIf you are a piper, charms <player1> and <player2>. You can choose to charm only one player.```")
async def cmd_charm(message, parameters):
    if not session[0] or get_role(message.author.id, 'role') not in COMMANDS_FOR_ROLE['charm'] or not session[1][message.author.id][0] or not message.channel.is_private:
        return
    if parameters == "":
        await reply(message, roles[session[1][message.author.id][1]][2].format(BOT_PREFIX))
    else:
        if 'charm' not in session[1][message.author.id][4]:
            await reply(message, "You are already charming tonight.")
            return
        targets = parameters.split(' and ')
        if len(targets) <= 2:
            actual_targets = []
            for target in targets:
                player = get_player(target)
                if not player:
                    await reply(message, "Could not find player " + target)
                    return
                actual_targets.append(player)
            actual_targets = set(actual_targets)
            valid_targets = []
            for player in actual_targets:
                if not session[1][player][0]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                    return
                elif 'charmed' in session[1][player][4] or 'tocharm' in session[1][player][4]:
                    await reply(message, "**{}** is already charmed!".format(get_name(player)))
                    return
                elif get_role(player, 'role') == 'piper':
                    await reply(message, "That would be a waste.")
                    return
                elif 'entranced' in session[1][message.author.id][4] and get_role(player, 'role') == 'succubus':
                    await reply(message, "You may not charm a succubus.")
                    return
                else:
                    valid_targets.append(player)
            valid_targets = sort_players(valid_targets)
            redirected_targets = []
            for player in valid_targets:
                if 'misdirection_totem2' in session[1][message.author.id][4]:
                    new_target = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and get_role(x, 'role') not in WOLFCHAT_ROLES and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4]) and not ('charmed' in session[1][x][4] or 'tocharm' in session[1][x][4])])
                    redirected_targets.append(new_target)
                elif 'luck_totem2' in session[1][player][4]:
                    new_target = misdirect(player)
                    redirected_targets.append(new_targe, alive_players=[x for x in session[1] if session[1][x][0] and get_role(x, 'role') not in WOLFCHAT_ROLES and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4]) and not 'charmed' in session[1][x][4] or 'tocharm' in session[1][x][4]])
                else:
                    redirected_targets.append(player)
            if len(valid_targets) == 2:
                await reply(message, "You have charmed **{}** and **{}**.".format(*map(get_name, redirected_targets)))
                await log(1, "{} ({}) CHARM {} ({}) AND {} ({})".format(get_name(message.author.id), message.author.id, get_name(redirected_targets[0]), redirected_targets[0], get_name(redirected_targets[1]), redirected_targets[1]))
                for piper in [x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'piper' and x != message.author.id]:
                    member = client.get_server(WEREWOLF_SERVER).get_member(piper)
                    if member:
                        try:
                            await client.send_message(member, "Another piper has charmed **{}** and **{}**!".format(*map(get_name, redirected_targets)))
                        except discord.Forbidden:
                            pass
            elif len(valid_targets) == 1:
                await reply(message, "You have charmed **{}**.".format(*map(get_name, redirected_targets)))
                await log(1, "{} ({}) CHARM {} ({})".format(get_name(message.author.id), message.author.id, get_name(redirected_targets[0]), redirected_targets[0]))
                for piper in [x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'piper' and x != message.author.id]:
                    member = client.get_server(WEREWOLF_SERVER).get_member(piper)
                    if member:
                        try:
                            await client.send_message(member, "Another piper has charmed **{}**!".format(*map(get_name, redirected_targets)))
                        except discord.Forbidden:
                            pass
            session[1][message.author.id][4].remove('charm')
            for charmed in redirected_targets:
                session[1][charmed][4].append('tocharm')
        else:
            await reply(message, "You must choose two different players.")

@cmd('visit', [2, 0], "```\n{0}visit <player>\n\nIf you are a harlot, visits <player>. You can stay home by visiting yourself. "
                      "You will die if you visit a wolf or the victim of the wolves. If you are a succubus, entrances <player>```")
async def cmd_visit(message, parameters):
    if not session[0] or message.author.id not in session[1] or get_role(message.author.id, 'role') not in COMMANDS_FOR_ROLE['visit'] or not session[1][message.author.id][0]:
        return
    if get_role(message.author.id, 'role') == 'succubus':
        await cmd_entrance(message, parameters)
        return
    if session[2]:
        await reply(message, "You may only visit during the night.")
        return
    if session[1][message.author.id][2]:
        await reply(message, "You are already spending the night with **{}**.".format(get_name(session[1][message.author.id][2])))
        return
    if "silence_totem2" in session[1][message.author.id][4]:
        await reply(message, "You have been silenced, and are unable to use any special powers.")
        return
    else:
        if parameters == "":
            await reply(message, roles[session[1][message.author.id][1]][2])
        else:
            player = get_player(parameters)
            if player:
                if player == message.author.id:
                    await reply(message, "You have chosen to stay home tonight.")
                    session[1][message.author.id][2] = message.author.id
                    await log(1, "{0} ({1}) STAY HOME".format(get_name(message.author.id), message.author.id))
                elif 'entranced' in session[1][message.author.id][4] and get_role(player, 'role') == 'succubus':
                    await reply(message, "You may not visit a succubus.")
                elif not session[1][player][0]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                else:
                    if 'misdirection_totem2' in session[1][message.author.id][4]:
                        player = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    elif 'luck_totem2' in session[1][player][4]:
                        player = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and x != message.author.id and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    await reply(message, "You are spending the night with **{}**. Have a good time!".format(get_name(player)))
                    session[1][message.author.id][2] = player
                    member = client.get_server(WEREWOLF_SERVER).get_member(player)
                    if member:
                        try:
                            await client.send_message(member, "You are spending the night with **{}**. Have a good time!".format(get_name(message.author.id)))
                        except discord.Forbidden:
                            pass
                    await log(1, "{0} ({1}) VISIT {2} ({3})".format(get_name(message.author.id), message.author.id, get_name(player), player))
            else:
                await reply(message, "Could not find player " + parameters)

@cmd('totem', [0, 0], "```\n{0}totem [<totem>]\n\nReturns information on a totem, or displays a list of totems.```", 'totems')
async def cmd_totem(message, parameters):
    if not parameters == '':
        reply_totems = []
        for totem in totems:
            if totem.startswith(parameters):
                reply_totems.append(totem)
        if _autocomplete(parameters, totems)[1] == 1:
            totem = _autocomplete(parameters, totems)[0]
            reply_msg = "```\n"
            reply_msg += totem[0].upper() + totem[1:].replace('_', ' ') + "\n\n"
            reply_msg += totems[totem] + "```"
            await reply(message, reply_msg)
            return
    await reply(message, "Available totems: " + ", ".join(sorted([x.replace('_', ' ') for x in totems])))

@cmd('fgame', [1, 2], "```\n{0}fgame [<gamemode>]\n\nForcibly sets or unsets [<gamemode>].```")
async def cmd_fgame(message, parameters):
    if session[0]:
        return
    if parameters == '':
        if session[6] != '':
            session[6] = ''
            await reply(message, "Successfully unset gamemode.")
        else:
            await reply(message, "Gamemode has not been set.")
    else:
        if parameters.startswith('roles'):
            role_string = ' '.join(parameters.split(' ')[1:])
            if role_string == '':
                await reply(message, "`{}fgame roles wolf:1,traitor:1,shaman:2,cursed villager:2,etc.`".format(BOT_PREFIX))
            else:
                session[6] = parameters
                await reply(message, "Successfully set gamemode roles to `{}`".format(role_string))
        else:
            choices, num = _autocomplete(parameters, gamemodes)
            if num == 1:
                session[6] = choices
                await reply(message, "Successfuly set gamemode to **{}**.".format(choices))
            elif num > 1:
                await reply(message, "Multiple choices: {}".format(', '.join(sorted(choices))))
            else:
                await reply(message, "Could not find gamemode {}".format(parameters))
    await log(2, "{0} ({1}) FGAME {2}".format(message.author.name, message.author.id, parameters))

@cmd('github', [0, 0], "```\n{0}github takes no arguments\n\nReturns a link to the bot's Github repository.```")
async def cmd_github(message, parameters):
    await reply(message, "http://github.com/belguawhale/Discord-Werewolf")

@cmd('ftemplate', [1, 2], "```\n{0}ftemplate <player> [<add|remove|set>] [<template1 [template2 ...]>]\n\nManipulates a player's templates.```")
async def cmd_ftemplate(message, parameters):
    if not session[0]:
        return
    if parameters == '':
        await reply(message, commands['ftemplate'][2].format(BOT_PREFIX))
        return
    params = parameters.split(' ')
    player = get_player(params[0])
    if len(params) > 1:
        action = parameters.split(' ')[1]
    else:
        action = ""
    if len(params) > 2:
        templates = parameters.split(' ')[2:]
    else:
        templates = []
    if player:
        reply_msg = "Successfully "
        if action in ['+', 'add', 'give']:
            session[1][player][3] += templates
            reply_msg += "added templates **{0}** to **{1}**."
        elif action in ['-', 'remove', 'del']:
            for template in templates[:]:
                if template in session[1][player][3]:
                    session[1][player][3].remove(template)
                else:
                    templates.remove(template)
            reply_msg += "removed templates **{0}** from **{1}**."
        elif action in ['=', 'set']:
            session[1][player][3] = templates
            reply_msg += "set **{1}**'s templates to **{0}**."
        else:
            reply_msg = "**{1}**'s templates: " + ', '.join(session[1][player][3])
    else:
        reply_msg = "Could not find player {1}."

    await reply(message, reply_msg.format(', '.join(templates), get_name(player)))
    await log(2, "{0} ({1}) FTEMPLATE {2}".format(message.author.name, message.author.id, parameters))

@cmd('fother', [1, 2], "```\n{0}fother <player> [<add|remove|set>] [<other1 [other2 ...]>]\n\nManipulates a player's other flag (totems, traitor).```")
async def cmd_fother(message, parameters):
    if not session[0]:
        return
    if parameters == '':
        await reply(message, commands['fother'][2].format(BOT_PREFIX))
        return
    params = parameters.split(' ')
    player = get_player(params[0])
    if len(params) > 1:
        action = parameters.split(' ')[1]
    else:
        action = ""
    if len(params) > 2:
        others = parameters.split(' ')[2:]
    else:
        others = []
    if player:
        reply_msg = "Successfully "
        if action in ['+', 'add', 'give']:
            session[1][player][4] += others
            reply_msg += "added **{0}** to **{1}**'s other flag."
        elif action in ['-', 'remove', 'del']:
            for other in others[:]:
                if other in session[1][player][4]:
                    session[1][player][4].remove(other)
                else:
                    others.remove(other)
            reply_msg += "removed **{0}** from **{1}**'s other flag."
        elif action in ['=', 'set']:
            session[1][player][4] = others
            reply_msg += "set **{1}**'s other flag to **{0}**."
        else:
            reply_msg = "**{1}**'s other flag: " + ', '.join(session[1][player][4])
    else:
        reply_msg = "Could not find player {1}."

    await reply(message, reply_msg.format(', '.join(others), get_name(player)))
    await log(2, "{0} ({1}) FOTHER {2}".format(message.author.name, message.author.id, parameters))

@cmd('faftergame', [2, 2], "```\n{0}faftergame <command> [<parameters>]\n\nSchedules <command> to run with [<parameters>] after the next game ends.```")
async def cmd_faftergame(message, parameters):
    if parameters == "":
        await reply(message, commands['faftergame'][2].format(BOT_PREFIX))
        return
    command = parameters.split(' ')[0]
    if command in commands:
        global faftergame
        faftergame = message
        await reply(message, "Command `{}` will run after the next game ends.".format(parameters))
    else:
        await reply(message, "{} is not a valid command!".format(command))

@cmd('uptime', [0, 0], "```\n{0}uptime takes no arguments\n\nChecks the bot's uptime.```")
async def cmd_uptime(message, parameters):
    delta = datetime.now() - starttime
    output = [[delta.days, 'day'],
              [delta.seconds // 3600, 'hour'],
              [delta.seconds // 60 % 60, 'minute'],
              [delta.seconds % 60, 'second']]
    for i in range(len(output)):
        if output[i][0] != 1:
            output[i][1] += 's'
    reply_msg = ''
    if output[0][0] != 0:
        reply_msg += "{} {} ".format(output[0][0], output[0][1])
    for i in range(1, len(output)):
        reply_msg += "{} {} ".format(output[i][0], output[i][1])
    reply_msg = reply_msg[:-1]
    await reply(message, "Uptime: **{}**".format(reply_msg))

@cmd('fstasis', [1, 1], "```\n{0}fstasis <player> [<add|remove|set>] [<amount>]\n\nManipulates a player's stasis.```")
async def cmd_fstasis(message, parameters):
    if parameters == '':
        await reply(message, commands['fstasis'][2].format(BOT_PREFIX))
        return
    params = parameters.split(' ')
    player = params[0].strip('<!@>')
    member = client.get_server(WEREWOLF_SERVER).get_member(player)
    name = "user not in server with id " + player
    if member:
        name = member.display_name
    if len(params) > 1:
        action = parameters.split(' ')[1]
    else:
        action = ''
    if len(params) > 2:
        amount = parameters.split(' ')[2]
        if amount.isdigit():
            amount = int(amount)
        else:
            amount = -1
    else:
        amount = -2
    if player.isdigit():
        if action and amount >= -1:
            if amount >= 0:
                if player not in stasis:
                    stasis[player] = 0
                reply_msg = "Successfully "
                if action in ['+', 'add', 'give']:
                    stasis[player] += amount
                    reply_msg += "increased **{0}** ({1})'s stasis by **{2}**."
                elif action in ['-', 'remove', 'del']:
                    amount = min(amount, stasis[player])
                    stasis[player] -= amount
                    reply_msg += "decreased **{0}** ({1})'s stasis by **{2}**."
                elif action in ['=', 'set']:
                    stasis[player] = amount
                    reply_msg += "set **{0}** ({1})'s stasis to **{2}**."
                else:
                    if player not in stasis:
                        amount = 0
                    else:
                        amount = stasis[player]
                    reply_msg = "**{0}** ({1}) is in stasis for **{2}** game{3}."
            else:
                reply_msg = "Stasis must be a non-negative integer."
        else:
            if player not in stasis:
                amount = 0
            else:
                amount = stasis[player]
            reply_msg = "**{0}** ({1}) is in stasis for **{2}** game{3}."
    else:
        reply_msg = "Invalid mention/id: {0}."

    await reply(message, reply_msg.format(name, player, amount, '' if int(amount) == 1 else 's'))
    await log(2, "{0} ({1}) FSTASIS {2}".format(message.author.name, message.author.id, parameters))

@cmd('gamemode', [0, 0], "```\n{0}gamemode [<gamemode>]\n\nDisplays information on [<gamemode>] or displays a "
                         "list of gamemodes.```", 'game', 'gamemodes')
async def cmd_gamemode(message, parameters):
    gamemode, num = _autocomplete(parameters, gamemodes)
    if num == 1 and parameters != '':
        await reply(message, "```\nGamemode: {}\nPlayers: {}\nDescription: {}\n\nUse the command "
                             "`!roles {} table` to view roles for this gamemode.```".format(gamemode,
        str(gamemodes[gamemode]['min_players']) + '-' + str(gamemodes[gamemode]['max_players']),
        gamemodes[gamemode]['description'], gamemode))
    else:
        await reply(message, "Available gamemodes: {}".format(', '.join(sorted(gamemodes))))

@cmd('verifygamemode', [1, 1], "```\n{0}verifygamemode [<gamemode>]\n\nChecks to make sure [<gamemode>] is valid.```", 'verifygamemodes')
async def cmd_verifygamemode(message, parameters):
    if parameters == '':
        await reply(message, "```\n{}\n```".format(verify_gamemodes()))
    elif _autocomplete(parameters, gamemodes)[1] == 1:
        await reply(message, "```\n{}\n```".format(verify_gamemode(_autocomplete(parameters, gamemodes)[0])))
    else:
        await reply(message, "Invalid gamemode: {}".format(parameters))

@cmd('shoot', [0, 2], "```\n{0}shoot <player>\n\nIf you have a gun, shoots <player> during the day. You may only use this command in channel.```")
async def cmd_shoot(message, parameters):
    if not session[0] or message.author.id not in session[1] or not session[1][message.author.id][0]:
        return
    if ('gunner' not in get_role(message.author.id, 'templates') and 'sharpshooter' not in get_role(message.author.id, 'templates')):
        try:
            await client.send_message(message.author, "You don't have a gun.")
        except discord.Forbidden:
            pass
        return
    if not session[2]:
        try:
            await client.send_message(message.author, "You may only shoot players during the day.")
        except discord.Forbidden:
            pass
        return
    if "silence_totem2" in session[1][message.author.id][4]:
        try:
            await client.send_message(message.author, "You have been silenced, and are unable to use any special powers.")
        except discord.Forbidden:
            pass
        return
    msg = ''
    pm = False
    ded = None
    outcome = ''
    if session[1][message.author.id][4].count('bullet') < 1:
        msg = "You have no more bullets."
        pm = True
    else:
        if parameters == "":
            msg = commands['shoot'][2].format(BOT_PREFIX)
            pm = True
        else:
            target = get_player(parameters.split(' ')[0])
            if not target:
                target = get_player(parameters)
            if not target:
                msg = 'Could not find player {}'.format(parameters)
            elif target == message.author.id:
                msg = "You are holding it the wrong way."
            elif not session[1][target][0]:
                msg = "Player **{}** is dead!".format(get_name(target))
            else:
                if 'misdirection_totem2' in session[1][message.author.id][4]:
                    target = misdirect(message.author.id)
                elif 'luck_totem2' in session[1][target][4]:
                    target = misdirect(target, alive_players=[x for x in session[1] if session[1][x][0] and x != message.author.id])
                if get_role(message.author.id, 'role') == 'village drunk':
                    SUICIDE = DRUNK_SUICIDE
                    MISS = DRUNK_MISS
                    HEADSHOT = DRUNK_HEADSHOT
                    INJURE = DRUNK_INJURE
                else:
                    SUICIDE = GUNNER_SUICIDE
                    MISS = GUNNER_MISS
                    HEADSHOT = GUNNER_HEADSHOT
                    INJURE = GUNNER_INJURE
                wolf = get_role(message.author.id, 'role') in WOLFCHAT_ROLES
                session[1][message.author.id][4].remove('bullet')
                if wolf:
                    if get_role(target, 'role') in WOLFCHAT_ROLES:
                        outcome = 'miss'
                else:
                    if get_role(target, 'role') in ACTUAL_WOLVES:
                        if get_role(target, 'role') in ['werekitten']:
                            outcome = random.choice((['suicide'] * SUICIDE + ['miss'] * (MISS + HEADSHOT + INJURE)) if 'sharpshooter' not in get_role(message.author.id, 'templates') else ['miss'])
                        else:
                            outcome = 'killwolf'
                    elif get_role(target, 'role') == 'succubus':
                        outcome = random.choice((['suicide'] * SUICIDE + ['miss'] * (MISS + HEADSHOT) + ['injure'] * INJURE) if 'sharpshooter' not in get_role(message.author.id, 'templates') else ['killvictim'])
                if outcome == '':
                    outcome = random.choice((['miss'] * MISS + ['suicide'] * SUICIDE \
                                             + ['killvictim'] * HEADSHOT + ['injure'] * INJURE)  if 'sharpshooter' not in get_role(message.author.id, 'templates') else ['killvictim'])
                if outcome in ['injure', 'killvictim', 'killwolf']:
                    msg = "**{}** shoots **{}** with a bullet!\n\n".format(get_name(message.author.id), get_name(target))
                if outcome == 'miss':
                    msg += "**{}** is a lousy shooter and missed!".format(get_name(message.author.id))
                elif outcome == 'killwolf':
                    msg += "**{}** is a **{}** and is dying from the silver bullet!".format(get_name(target),
                            get_role(target, 'death'))
                    ded = target
                elif outcome == 'suicide':
                    msg += "Oh no! **{}**'s gun was poorly maintained and has exploded! ".format(get_name(message.author.id))
                    msg += "The village mourns a **gunner-{}**.".format(get_role(message.author.id, 'death'))
                    ded = message.author.id
                elif outcome == 'killvictim':
                    msg += "**{}** is not a wolf but was fatally injured. The village has sacrificed a **{}**.".format(
                            get_name(target), get_role(target, 'death'))
                    ded = target
                elif outcome == 'injure':
                    msg += "**{}** is a villager and was injured. Luckily the injury is minor and will heal after a day of rest.".format(
                            get_name(target))
                    session[1][target][4].append('injured')
                else:
                    msg += "wtf? (this is an error, please report to an admin)"

                await log(1, "{} ({}) SHOOT {} ({}) WITH OUTCOME {}".format(get_name(message.author.id), message.author.id,
                    get_name(target), target, outcome))

    if pm:
        target = message.author
    else:
        target = client.get_channel(GAME_CHANNEL)
    try:
        await client.send_message(target, msg)
    except discord.Forbidden:
        pass

    if ded:
        await player_deaths({ded : ('gunner ' + outcome, get_role(message.author.id, "actualteam"))})
        await check_traitor()

@cmd('target', [2, 0], "```\n{0}target <player>\n\nIf you are an assassin, makes <player> your target during the night.```", 'assassinate')
async def cmd_target(message, parameters):
    if not session[0] or message.author.id not in session[1] or COMMANDS_FOR_ROLE['target'][0] not in get_role(message.author.id, "templates") or not session[1][message.author.id][0]:
        return
    if session[2]:
        await reply(message, "You may only target a player during the night.")
        return
    if [x for x in session[1][message.author.id][4] if x.startswith("assassinate:")]:
        await reply(message, "You have already targeted someone. You must wait until they die to target again.")
    else:
        if parameters == "":
            await reply(message, roles[session[1][message.author.id][1]][2])
        else:
            player = get_player(parameters)
            if player:
                if player == message.author.id:
                    await reply(message, "You can't target yourself!")
                elif 'entranced' in session[1][message.author.id][4] and get_role(player, 'role') == 'succubus':
                    await reply(message, "You may not target a succubus.")
                elif not session[1][player][0]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                else:
                    if 'misdirection_totem2' in session[1][message.author.id][4]:
                        player = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    elif 'luck_totem2' in session[1][player][4]:
                        player = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and x != message.author.id and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    session[1][message.author.id][4].append("assassinate:{}".format(player))
                    await reply(message, "You have chosen to target **{}**. They will be your target until they die.".format(
                        get_name(player)))
                    await log(1, "{0} ({1}) TARGET {2} ({3})".format(get_name(message.author.id), message.author.id, get_name(player), player))
            else:
                await reply(message, "Could not find player " + parameters)

@cmd('fsay', [1, 1], "```\n{0}fsay <message>\n\nSends <message> to the lobby channel.```")
async def cmd_fsay(message, parameters):
    if parameters:
        await send_lobby(parameters)
        await log(2, "{} ({}) FSAY {}".format(message.author.name, message.author.id, parameters))
    else:
        await reply(message, commands['fsay'][2].format(BOT_PREFIX))

@cmd('observe', [2, 0], "```\n{0}observe <player>\n\nIf you are a werecrow, tells you if <player> was in their bed for the night. "
                        "If you are a sorcerer, tells you if <player> has supernatural powers (seer, etc.).```")
async def cmd_observe(message, parameters):
    if not session[0] or message.author.id not in session[1] or get_role(message.author.id, 'role') not in COMMANDS_FOR_ROLE['observe'] or not session[1][message.author.id][0]:
        return
    if session[2]:
        await reply(message, "You may only observe during the night.")
        return
    if get_role(message.author.id, 'role') == 'werecrow':
        if 'observe' in session[1][message.author.id][4]:
            await reply(message, "You are already observing someone!.")
            return
        if "silence_totem2" in session[1][message.author.id][4]:
            await reply(message, "You have been silenced, and are unable to use any special powers.")
            return
        else:
            if parameters == "":
                await reply(message, roles[session[1][message.author.id][1]][2])
            else:
                player = get_player(parameters)
                if player:
                    if player == message.author.id:
                        await reply(message, "That would be a waste.")
                    elif player in [x for x in session[1] if roles[get_role(x, 'role')][0] == 'wolf' and get_role(x, 'role') not in ['minion', 'cultist']]:
                        await reply(message, "Observing another wolf is a waste of time.")
                    elif not session[1][player][0]:
                        await reply(message, "Player **" + get_name(player) + "** is dead!")
                    elif 'entranced' in session[1][message.author.id][4] and get_role(player, 'role') == 'succubus':
                        await reply(message, "You may not observe a succubus.")
                    else:
                        session[1][message.author.id][4].append('observe')
                        if 'misdirection_totem2' in session[1][message.author.id][4]:
                            player = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                        elif 'luck_totem2' in session[1][player][4]:
                            player = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and get_role(x, 'role') not in WOLFCHAT_ROLES and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                        await reply(message, "You transform into a large crow and start your flight to **{0}'s** house. You will "
                                            "return after collecting your observations when day begins.".format(get_name(player)))
                        await wolfchat("**{}** is observing **{}**.".format(get_name(message.author.id), get_name(player)))
                        await log(1, "{0} ({1}) OBSERVE {2} ({3})".format(get_name(message.author.id), message.author.id, get_name(player), player))
                        while not session[2] and win_condition() == None and session[0]:
                            await asyncio.sleep(0.1)
                        if 'observe' in session[1][message.author.id][4]:
                            session[1][message.author.id][4].remove('observe')
                        if get_role(player, 'role') in ['seer', 'oracle', 'harlot', 'hunter', 'augur']\
                            and session[1][player][2] in set(session[1]) - set(player)\
                            or get_role(player, 'role') in ['shaman', 'crazed shaman']\
                            and session[1][player][2] in session[1]:
                                msg = "not in bed all night"
                        else:
                                msg = "sleeping all night long"
                        try:
                            await client.send_message(message.author, "As the sun rises, you conclude that **{}** was {}, and you fly back to your house.".format(
                                get_name(player), msg))
                        except discord.Forbidden:
                            pass
                else:
                    await reply(message, "Could not find player " + parameters)
    elif get_role(message.author.id, 'role') == 'sorcerer':
        if session[1][message.author.id][2]:
            await reply(message, "You have already used your power.")
        elif parameters == "":
            await reply(message, roles[session[1][message.author.id][1]][2])
        else:
            player = get_player(parameters)
            if player:
                if player == message.author.id:
                    await reply(message, "Using your power on yourself would be a waste.")
                elif player in [x for x in session[1] if roles[get_role(x, 'role')][0] == 'wolf' and get_role(x, 'role') != 'cultist']:
                    await reply(message, "Observing another wolf is a waste of time.")
                elif not session[1][player][0]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                elif 'entranced' in session[1][message.author.id][4] and get_role(player, 'role') == 'succubus':
                    await reply(message, "You may not observe a succubus.")
                else:
                    if 'misdirection_totem2' in session[1][message.author.id][4]:
                        player = misdirect(message.author.id, alive_players=[x for x in session[1] if session[1][x][0] and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    elif 'luck_totem2' in session[1][player][4]:
                        player = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and get_role(x, 'role') not in WOLFCHAT_ROLES and not (get_role(x, 'role') == 'succubus' and 'entranced' in session[1][message.author.id][4])])
                    session[1][message.author.id][2] = player
                    target_role = get_role(player, 'role')
                    if target_role == 'amnesiac':
                        target_role = [x.split(':')[1].replace("_", " ") for x in session[1][player][4] if x.startswith("role:")].pop()
                    if target_role in ['seer', 'oracle', 'augur']:
                        debug_msg = target_role
                        msg = "**{}** is a **{}**!".format(get_name(player), get_role(player, 'role'))
                    else:
                        debug_msg = "not paranormal"
                        msg = "**{}** does not have paranormal senses.".format(get_name(player))
                    await wolfchat("**{}** is observing **{}**.".format(get_name(message.author.id), get_name(player)))
                    await reply(message, "After casting your ritual, you determine that " + msg)
                    await log(1, "{0} ({1}) OBSERVE {2} ({3}) AS {4}".format(get_name(message.author.id), message.author.id, get_name(player), player, debug_msg))
            else:
                await reply(message, "Could not find player " + parameters)

@cmd('id', [2, 0], "```\n{0}id <player>\n\nIf you are a detective, investigates <player> during the day.```")
async def cmd_id(message, parameters):
    if not session[0] or message.author.id not in session[1] or get_role(message.author.id, 'role') not in COMMANDS_FOR_ROLE['id'] or not session[1][message.author.id][0]:
        return
    if not session[2]:
        await reply(message, "You may only investigate during the day.")
        return
    if 'investigate' in session[1][message.author.id][4]:
        await reply(message, "You have already investigated someone.")
        return
    if "silence_totem2" in session[1][message.author.id][4]:
        await reply(message, "You have been silenced, and are unable to use any special powers.")
        return
    else:
        if parameters == "":
            await reply(message, roles[session[1][message.author.id][1]][2])
        else:
            player = get_player(parameters)
            if player:
                if player == message.author.id:
                    await reply(message, "Investigating yourself would be a waste.")
                elif not session[1][player][0]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                else:
                    session[1][message.author.id][4].append('investigate')
                    if 'misdirection_totem2' in session[1][message.author.id][4]:
                        player = misdirect(message.author.id)
                    elif 'luck_totem2' in session[1][player][4]:
                        player = misdirect(player, alive_players=[x for x in session[1] if session[1][x][0] and x != message.author.id])
                    await reply(message, "The results of your investigation have returned. **{}** is a **{}**!".format(
                        get_name(player), get_role(player, 'role') if not get_role(player, 'role') == 'amnesiac' else [x.split(':')[1].replace("_", " ") for x in session[1][player][4] if x.startswith("role:")].pop()))
                    await log(1, "{0} ({1}) INVESTIGATE {2} ({3})".format(get_name(message.author.id), message.author.id, get_name(player), player))
                    if random.random() < DETECTIVE_REVEAL_CHANCE:
                        await wolfchat("Someone accidentally drops a paper. The paper reveals that **{}** ({}) is the detective!".format(
                            get_name(message.author.id), message.author.id))
                        await log(1, "{0} ({1}) DETECTIVE REVEAL".format(get_name(message.author.id), message.author.id))
                    while session[2] and win_condition() == None and session[0]:
                        await asyncio.sleep(0.1)
                    if 'investigate' in session[1][message.author.id][4]:
                        session[1][message.author.id][4].remove('investigate')
            else:
                await reply(message, "Could not find player " + parameters)

@cmd('frevive', [1, 2], "```\n{0}frevive <player>\n\nRevives <player>. Used for debugging purposes.```")
async def cmd_frevive(message, parameters):
    if not session[0]:
        return
    if parameters == "":
        await reply(message, commands['frevive'][2].format(BOT_PREFIX))
    else:
        player = get_player(parameters)
        if player:
            if session[1][player][0]:
                await reply(message, "Player **{}** is already alive!".format(player))
            else:
                session[1][player][0] = True
                await reply(message, ":thumbsup:")
        else:
            await reply(message, "Could not find player {}".format(parameters))
    await log(2, "{} ({}) FREVIVE {}".format(message.author.name, message.author.id, parameters))

@cmd('pass', [2, 0], "```\n{0}pass takes no arguments\n\nChooses to not perform your action tonight.```")
async def cmd_pass(message, parameters):
    role = get_role(message.author.id, 'role')
    if not session[0] or message.author.id not in session[1] or role not in COMMANDS_FOR_ROLE['pass'] or not session[1][message.author.id][0]:
        return
    if session[2] and role in ('harlot', 'hunter', 'guardian angel'):
        await reply(message, "You may only pass during the night.")
        return
    if session[1][message.author.id][2] != '':
        return
    if role == 'harlot':
        session[1][message.author.id][2] = message.author.id
        await reply(message, "You have chosen to stay home tonight.")
    if role == 'succubus':
        session[1][message.author.id][2] = message.author.id
        await reply(message, "You have chosen to not entrance anyone tonight.")
    if role == 'warlock':
        session[1][message.author.id][2] = message.author.id
        await reply(message, "You have chosen not to curse anyone tonight.")
        await wolfchat("**{}** has chosen not to curse anyone tonight.".format(get_name(message.author.id)))
    elif role == 'hunter':
        session[1][message.author.id][2] = message.author.id
        await reply(message, "You have chosen to not kill anyone tonight.")
    elif role in ['guardian angel', 'bodyguard']:
        session[1][message.author.id][2] = 'pass'
        await reply(message, "You have chosen to not guard anyone tonight.")
    elif role == 'piper':
        session[1][message.author.id][4] = [x for x in session[1][message.author.id][4] if x != 'charm']
        await reply(message, "You have chosen not to charm anyone tonight.")
    else:
        await reply(message, "wtf? (this is an error; please report to an admin")
    await log(1, "{0} ({1}) PASS".format(get_name(message.author.id), message.author.id))

@cmd('cat', [0, 0], "```\n{0}cat takes no arguments\n\nFlips a cat.```")
async def cmd_cat(message, parameters):
    await reply(message, "The cat landed on **its feet**!")

@cmd('fgoat', [1, 1], "```\n{0}fgoat <target>\n\nForcibly sends a goat to violently attack <target>.```")
async def cmd_fgoat(message, parameters):
    if parameters == '':
        await reply(message, commands['fgoat'][2].format(BOT_PREFIX))
        return
    action = random.choice(['kicks', 'headbutts'])
    await send_lobby("**{}**'s goat walks by and {} **{}**.".format(message.author.name, action, parameters))

@cmd('guard', [2, 0], "```\n{0}guard <target>\n\nGuards <player>, preventing them from dying this night. Can guard yourself, however "
                      "cannot be used on the same target twice in a row.```", 'protect')
async def cmd_guard(message, parameters):
    if not session[0] or message.author.id not in session[1] or get_role(message.author.id, 'role') not in COMMANDS_FOR_ROLE['guard'] \
    or not session[1][message.author.id][0]:
        return
    if session[2]:
        await reply(message, "You may only guard players during the night.")
        return
    if session[1][message.author.id][2]:
        await reply(message, "You are already guarding **{}**.".format(get_name(session[1][message.author.id][2])))
        return
    if "silence_totem2" in session[1][message.author.id][4]:
        await reply(message, "You have been silenced, and are unable to use any special powers.")
        return
    else:
        if parameters == "":
            await reply(message, roles[session[1][message.author.id][1]][2])
        else:
            player = get_player(parameters)
            if player:
                if 'lasttarget:' + player in session[1][message.author.id][4]: # so hacky but whaterver
                    await reply(message, "You already guarded **{}** last night. You may not guard the same player two nights in a row.".format(get_name(player)))
                    return
                session[1][message.author.id][4][:] = [x for x in session[1][message.author.id][4] if not x.startswith('lasttarget:')]
                if not session[1][player][0]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                    return
                if 'misdirection_totem2' in session[1][message.author.id][4]:
                    new_target = misdirect(message.author.id)
                    while 'lasttarget:' + new_target in session[1][message.author.id][4]:
                        new_target = misdirect(message.author.id)
                    player = new_target
                elif 'luck_totem2' in session[1][player][4]:
                    new_target = misdirect(player)
                    while 'lasttarget:' + new_target in session[1][message.author.id][4]:
                        new_target = misdirect(player)
                    player = new_target
                if get_role(message.author.id, 'role') == 'guardian angel':
                    session[1][message.author.id][4].append('lasttarget:' + player)
                if player == message.author.id:
                    if get_role(message.author.id, 'role') == 'guardian angel':
                        await reply(message, "You have chosen to guard yourself tonight.")
                        session[1][message.author.id][2] = message.author.id
                        session[1][message.author.id][4].append("guarded")
                        await log(1, "{0} ({1}) GUARD SELF".format(get_name(message.author.id), message.author.id))
                    else:
                        await reply(message, "You cannot guard yourself. Use pass if you do not wish to guard anyone tonight.")
                        return
                else:
                    await reply(message, "You have chosen to guard **{}**.".format(get_name(player)))
                    session[1][message.author.id][2] = player
                    if get_role(message.author.id, 'role') == 'guardian angel':
                        session[1][player][4].append("guarded")
                    elif get_role(message.author.id, 'role') == 'guardian angel':
                        session[1][player][4].append("bodyguard:{}".format(message.author.id))
                    member = client.get_server(WEREWOLF_SERVER).get_member(player)
                    if member:
                        try:
                            await client.send_message(member, "You can sleep well tonight, for you are being protected.")
                        except discord.Forbidden:
                            pass
                    await log(1, "{0} ({1}) GUARD {2} ({3})".format(get_name(message.author.id), message.author.id, get_name(player), player))
            else:
                await reply(message, "Could not find player " + parameters)

######### END COMMANDS #############

def misdirect(player, alive_players=None):
    if not alive_players:
        alive_players = [x for x in session[1] if session[1][x][0]]
    return random.choice([alive_players[len(alive_players)-1] if alive_players.index(player) == 0 else alive_players[alive_players.index(player)-1], alive_players[0] if alive_players.index(player) == len(alive_players)-1 else alive_players[alive_players.index(player)+1]])

def has_privileges(level, message):
    if message.author.id == OWNER_ID:
        return True
    elif level == 1 and message.author.id in ADMINS:
        return True
    elif level == 0:
        return True
    else:
        return False

async def reply(message, text, cleanmessage=True):
    if cleanmessage:
        text = text.replace('@', '@\u200b')
    await client.send_message(message.channel, message.author.mention + ', ' + str(text))

async def send_lobby(text):
    for i in range(3):
        try:
            msg = await client.send_message(client.get_channel(GAME_CHANNEL), text)
            return msg
            break
        except:
            await log(3, "Error in sending message `{}` to lobby: ```py\n{}\n```".format(
                text, traceback.format_exc()))
            await asyncio.sleep(5)
    else:
        await log(3, "Unable to send message `{}` to lobby: ```py\n{}\n```".format(
            text, traceback.format_exc()))

async def parse_command(commandname, message, parameters):
    await log(0, 'Parsing command ' + commandname + ' with parameters `' + parameters + '` from ' + message.author.name + ' (' + message.author.id + ')')
    if commandname in commands:
        pm = 0
        if message.channel.is_private:
            pm = 1
        if has_privileges(commands[commandname][1][pm], message):
            try:
                await commands[commandname][0](message, parameters)
            except Exception:
                traceback.print_exc()
                print(session)
                msg = '```py\n{}\n```\n**session:**```py\n{}\n```'.format(traceback.format_exc(), session)
                await log(3, msg)
                await client.send_message(message.channel, "An error has occurred and has been logged.")
        elif has_privileges(commands[commandname][1][0], message):
            if session[0] and message.author.id in session[1] and session[1][message.author.id][0]:
                if commandname in COMMANDS_FOR_ROLE and (get_role(message.author.id, 'role') in COMMANDS_FOR_ROLE[commandname]\
                or not set(get_role(message.author.id, 'templates')).isdisjoint(set(COMMANDS_FOR_ROLE[commandname]))):
                    await reply(message, "Please use command " + commandname + " in channel.")
        elif has_privileges(commands[commandname][1][1], message):
            if session[0] and message.author.id in session[1] and session[1][message.author.id][0]:
                if commandname in COMMANDS_FOR_ROLE and get_role(message.author.id, 'role') in COMMANDS_FOR_ROLE[commandname]:
                    try:
                        await client.send_message(message.author, "Please use command " + commandname + " in private message.")
                    except discord.Forbidden:
                        pass
            elif message.author.id in ADMINS:
                await reply(message, "Please use command " + commandname + " in private message.")
        else:
            await log(2, 'User ' + message.author.name + ' (' + message.author.id + ') tried to use command ' + commandname + ' with parameters `' + parameters + '` without permissions!')

async def log(loglevel, text):
    # loglevels
    # 0 = DEBUG
    # 1 = INFO
    # 2 = WARNING
    # 3 = ERROR
    levelmsg = {0 : '[DEBUG] ',
                1 : '[INFO] ',
                2 : '**[WARNING]** ',
                3 : '**[ERROR]** <@' + OWNER_ID + '> '
                }
    logmsg = levelmsg[loglevel] + str(text)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write("[{}] {}\n".format(datetime.now(), logmsg))
    if loglevel >= MIN_LOG_LEVEL:
        await client.send_message(client.get_channel(DEBUG_CHANNEL), logmsg)

def balance_roles(massive_role_list, default_role='villager', num_players=-1):
    if num_players == -1:
        num_players = len(session[1])
    extra_players = num_players - len(massive_role_list)
    if extra_players > 0:
        massive_role_list += [default_role] * extra_players
        return (massive_role_list, "Not enough roles; added {} {} to role list".format(extra_players, default_role))
    elif extra_players < 0:
        random.shuffle(massive_role_list)
        removed_roles = []
        team_roles = [0, 0, 0]
        for role in massive_role_list:
            if role in WOLF_ROLES_ORDERED:
                team_roles[0] += 1
            elif role in VILLAGE_ROLES_ORDERED:
                team_roles[1] += 1
            elif role in NEUTRAL_ROLES_ORDERED:
                team_roles[2] += 1
        for i in range(-1 * extra_players):
            team_fractions = list(x / len(massive_role_list) for x in team_roles)
            roles_to_remove = set()
            if team_fractions[0] > 0.35:
                roles_to_remove |= set(WOLF_ROLES_ORDERED)
            if team_fractions[1] > 0.7:
                roles_to_remove |= set(VILLAGE_ROLES_ORDERED)
            if team_fractions[2] > 0.15:
                roles_to_remove |= set(NEUTRAL_ROLES_ORDERED)
            if len(roles_to_remove) == 0:
                roles_to_remove = set(roles)
                if team_fractions[0] < 0.25:
                    roles_to_remove -= set(WOLF_ROLES_ORDERED)
                if team_fractions[1] < 0.5:
                    roles_to_remove -= set(VILLAGE_ROLES_ORDERED)
                if team_fractions[2] < 0.05:
                    roles_to_remove -= set(NEUTRAL_ROLES_ORDERED)
                if len(roles_to_remove) == 0:
                    roles_to_remove = set(roles)
            for role in massive_role_list[:]:
                if role in roles_to_remove:
                    massive_role_list.remove(role)
                    removed_roles.append(role)
                    break
        return (massive_role_list, "Too many roles; removed {} from the role list".format(', '.join(sort_roles(removed_roles))))
    return (massive_role_list, '')

async def assign_roles(gamemode):
    massive_role_list = []
    gamemode_roles = get_roles(gamemode, len(session[1]))

    if not gamemode_roles:
        # Second fallback just in case
        gamemode_roles = get_roles('default', len(session[1]))
        session[6] = 'default'

    # Generate list of roles

    for role in gamemode_roles:
        if role in roles and role not in TEMPLATES_ORDERED:
            massive_role_list += [role] * gamemode_roles[role]

    massive_role_list, debugmessage = balance_roles(massive_role_list)
    if debugmessage != '':
        await log(2, debugmessage)

    if session[6].startswith('roles'):
        session[7] = dict((x, massive_role_list.count(x)) for x in roles if x in massive_role_list)
    else:
        session[7] = dict(gamemode_roles)

    random.shuffle(massive_role_list)
    for player in session[1]:
        role = massive_role_list.pop()
        session[1][player][1] = role
        if role == 'hunter':
            session[1][player][4].append('hunterbullet')
        elif role == 'matchmaker':
            session[1][player][4].append('match')
        elif role == 'amnesiac':
            session[1][player][4].append('role:{}'.format(random.choice(list(set(roles) - set(["minion", "matchmaker", "villager", "cultist", "amnesiac"] + TEMPLATES_ORDERED)))))
            if 'role:hunter' in session[1][player][4]:
                session[1][player][4].append('hunterbullet')
            if 'role:priest' in session[1][player][4]:
                session[1][player][4].append('bless')
            if 'role:matchmaker' in session[1][player][4]:
                session[1][player][4].append('match')
        elif role == 'priest':
            session[1][player][4].append('bless')

    for i in range(gamemode_roles['cursed villager'] if 'cursed villager' in gamemode_roles else 0):
        cursed_choices = [x for x in session[1] if get_role(x, 'role') not in\
        ACTUAL_WOLVES + ['seer', 'priest', 'oracle', 'augur', 'fool'] and 'cursed' not in session[1][x][3]]
        if cursed_choices:
            cursed = random.choice(cursed_choices)
            session[1][cursed][3].append('cursed')
    for i in range(gamemode_roles['mayor'] if 'mayor' in gamemode_roles else 0):
        if gamemode == 'random':
            mayor_choices = [x for x in session[1] if 'mayor' not in session[1][x][3]]
        else:
            mayor_choices = [x for x in session[1] if get_role(x, 'role') not in\
        ['monster', 'jester', 'fool'] and 'mayor' not in session[1][x][3]]
        if mayor_choices:
            mayor = random.choice(mayor_choices)
            session[1][mayor][3].append('mayor')
            session[1][mayor][4].append('unrevealed')
    for i in range(gamemode_roles['gunner'] if 'gunner' in gamemode_roles else 0):
        if gamemode in ['chaos', 'random']:
            gunner_choices = [x for x in session[1] if ('gunner' not in session[1][x][3] and 'sharpshooter' not in session[1][x][3])]
        else:
            gunner_choices = [x for x in session[1] if get_role(x, 'role') not in \
            WOLF_ROLES_ORDERED + NEUTRAL_ROLES_ORDERED + ['priest'] and ('gunner' not in session[1][x][3] and 'sharpshooter' not in session[1][x][3])]
        if gunner_choices:
            pewpew = random.choice(gunner_choices)
            if get_role(pewpew, 'role') == 'village drunk':
                session[1][pewpew][3].append('gunner')
                session[1][pewpew][4] += ['bullet'] * int(GUNNER_MULTIPLIER * len(session[1]) + 1) * DRUNK_MULTIPLIER
            elif random.random() > 0.2:
                session[1][pewpew][3].append('gunner')
                session[1][pewpew][4] += ['bullet'] * int(GUNNER_MULTIPLIER * len(session[1]) + 1)
            else:
                session[1][pewpew][3].append('sharpshooter')
                session[1][pewpew][4] += ['bullet'] * int(SHARPSHOOTER_MULTIPLIER * len(session[1]) + 1)
    gunners = [x for x in session[1] if 'gunner' in session[1][x][3]]
    for i in range(gamemode_roles['sharpshooter'] if 'sharpshooter' in gamemode_roles else 0):
        sharpshooter_choices = [x for x in gunners if 'sharpshooter' not in session[1][x][3]]
        if sharpshooter_choices:
            pewpew = random.choice(sharpshooter_choices)
            session[1][pewpew][3].remove('gunner')
            session[1][pewpew][4] = [x for x in session[1][pewpew][4] if x != 'bullet']
            session[1][pewpew][3].append('sharpshooter')
            session[1][pewpew][4] += ['bullet'] * int(SHARPSHOOTER_MULTIPLIER * len(session[1]) + 1)
    for i in range(gamemode_roles['assassin'] if 'assassin' in gamemode_roles else 0):
        if gamemode == 'random':
            assassin_choices = [x for x in session[1] if 'assassin' not in session[1][x][3]]
        else:
            assassin_choices = [x for x in session[1] if get_role(x, 'role') not in\
        ACTUAL_WOLVES + NEUTRAL_ROLES_ORDERED + ["traitor", "seer", "augur", "oracle", "harlot", "detective", "guardian angel"] and 'assassin' not in session[1][x][3]]
        if assassin_choices:
            assassin = random.choice(assassin_choices)
            session[1][assassin][3].append('assassin')
            if get_role(assassin, 'role') == 'village drunk':
                session[1][assassin][4].append('assassinate:{}'.format(random.choice([x for x in session[1] if x != assassin])))
    for i in range(gamemode_roles['blessed villager'] if 'blessed villager' in gamemode_roles else 0):
        if gamemode == 'random':
            blessed_choices = [x for x in session[1] if 'blessed' not in session[1][x][3]]
        else:
            blessed_choices = [x for x in session[1] if get_role(x, 'role') == 'villager' and not session[1][x][3]]
        if blessed_choices:
            blessed = random.choice(blessed_choices)
            session[1][blessed][3].append('blessed')
    if gamemode == 'belunga':
        for player in session[1]:
            session[1][player][4].append('belunga_totem')

async def end_game(reason, winners=None):
    global faftergame
    await client.change_presence(game=client.get_server(WEREWOLF_SERVER).me.game, status=discord.Status.online)
    if not session[0]:
        return
    session[0] = False
    if session[2]:
        if session[3][1]:
            session[4][1] += datetime.now() - session[3][1]
    else:
        if session[3][0]:
            session[4][0] += datetime.now() - session[3][0]
    msg = "<@{}> Game over! Night lasted **{:02d}:{:02d}**. Day lasted **{:02d}:{:02d}**. Game lasted **{:02d}:{:02d}**. \
          \n{}\n\n".format('> <@'.join(sort_players(session[1])), session[4][0].seconds // 60, session[4][0].seconds % 60,
          session[4][1].seconds // 60, session[4][1].seconds % 60, (session[4][0].seconds + session[4][1].seconds) // 60,
          (session[4][0].seconds + session[4][1].seconds) % 60, reason)
    if winners or session[6] == 'crazy':
        for player in session[1]:
            # ALTERNATE WIN CONDITIONS
            if session[1][player][0] and get_role(player, 'role') == 'crazed shaman':
                winners.append(player)
        winners = sort_players(set(winners)) # set ensures winners are unique
        if len(winners) == 0:
            msg += "No one wins!"
        elif len(winners) == 1:
            msg += "The winner is **{}**!".format(get_name(winners[0]))
        elif len(winners) == 2:
            msg += "The winners are **{}** and **{}**!".format(get_name(winners[0]), get_name(winners[1]))
        else:
            msg += "The winners are **{}**, and **{}**!".format('**, **'.join(map(get_name, winners[:-1])), get_name(winners[-1]))
    await send_lobby(msg)
    await log(1, "WINNERS: {}".format(winners))

    players = list(session[1])
    session[3] = [datetime.now(), datetime.now()]
    session[4] = [timedelta(0), timedelta(0)]
    session[6] = ''
    session[7] = {}

    perms = client.get_channel(GAME_CHANNEL).overwrites_for(client.get_server(WEREWOLF_SERVER).default_role)
    perms.send_messages = True
    await client.edit_channel_permissions(client.get_channel(GAME_CHANNEL), client.get_server(WEREWOLF_SERVER).default_role, perms)
    player_dict = {}
    for player in players:
        player_dict[player] = ('game end', "bot")
    await player_deaths(player_dict)

    if faftergame:
        # !faftergame <command> [<parameters>]
        # faftergame.content.split(' ')[0] is !faftergame
        command = faftergame.content.split(' ')[1]
        parameters = ' '.join(faftergame.content.split(' ')[2:])
        await commands[command][0](faftergame, parameters)
        faftergame = None

def win_condition():
    teams = {'village' : 0, 'wolf' : 0, 'neutral' : 0}
    injured_wolves = 0
    for player in session[1]:
        if session[1][player][0]:
            if 'injured' in session[1][player][4]:
                if get_role(player, 'actualteam') == 'wolf' and session[1][player][1] not in ['cultist', 'minion'] and 'entranced' not in session[1][player][4]:
                    injured_wolves += 1
            else:
                if session[1][player][1] in ['cultist', 'minion'] and session[6] != 'evilvillage':
                    teams['village'] += 1
                else:
                    teams[roles[session[1][player][1]][0]] += 1
    winners = []
    win_team = ''
    win_lore = ''
    win_msg = ''
    lovers = []
    players = session[1]
    for plr in players:
        for o in players[plr][4]:
            if o.startswith("lover:"):
                lvr = o.split(':')[1]
                if lvr in players:
                    if plr not in lovers and session[1][plr][0]:
                        lovers.append(plr)
                    if lvr not in lovers and session[1][lvr][0]:
                        lovers.append(lvr)
    if len([x for x in session[1] if session[1][x][0]]) == 0:
        win_lore = 'Everyone died. The town sits abandoned, collecting dust.'
        win_team = 'no win'
    elif len(lovers) == len([x for x in session[1] if session[1][x][0]]):
        win_team = 'lovers'
        win_lore = "Game over! The remaining villagers through their inseparable love for each other have agreed to stop all of this senseless violence and coexist in peace forever more. All remaining players win."
    elif len([x for x in session[1] if session[1][x][0] and (get_role(x, 'role') == 'succubus' or 'entranced' in session[1][x][4])]) == len([x for x in session[1] if session[1][x][0]]):
        win_team = 'succubi'
        win_lore = "Game over! The succub{} completely enthralled the village, making them officers in an ever-growing army set on spreading their control and influence throughout the entire world.".format('i' if len([x for x in session[1] if get_role(x, 'role') == 'succubus']) > 1 else 'us')
    elif len([x for x in session[1] if session[1][x][0] and (get_role(x, 'role') == 'piper' or 'charmed' in session[1][x][4])]) == len([x for x in session[1] if session[1][x][0]]):
        win_team = 'pipers'
        win_lore = "Game over! Everyone has fallen victim to the charms of the piper{0}. The piper{0} lead{1} the villagers away from the village, never to return...".format('' if len([x for x in session[1] if get_role(x, 'role') == 'piper']) < 2 else 's', 's' if len([x for x in session[1] if get_role(x, 'role') == 'piper']) < 2 else '')
    elif teams['village'] + teams['neutral'] <= teams['wolf'] and not (session[6] == 'evilvillage' and teams['village']):
        if session[6] == 'evilvillage':
            if not teams['village']:
                if [x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'monster']:
                    win_team = 'monster'
                    win_lore = "Game over! All the villagers are dead! As The cultists rejoice, they get destroyed by the monster{0}, causing the monster{0} to win.".format('s' if len([x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'monster']) > 1 else '')
                elif not [x for x in session[1] if session[1][x][0] and get_role(x, 'role') not in ['cultist', 'minion']]:
                    win_team = 'no win'
                    win_lore = "Game over! All the villagers are dead, but the cult needed to sacrifice the wolves to accomplish that. The cult disperses shortly thereafter, and nobody wins."
                else:
                    win_team = 'wolf'
                    win_lore = "Game over! All the villagers are dead! The cultists rejoice with their wolf buddies and start plotting to take over the next village."
        elif [x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'monster']:
            win_team = 'monster'
            win_lore = "Game over! The number of uninjured villagers is equal or less than the number of living wolves! The wolves overpower the villagers but then get destroyed by the monster{0}, causing the monster{0} to win.".format('s' if len([x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'monster']) > 1 else '')
        else:
            win_team = 'wolf'
            win_lore = 'The number of uninjured villagers is equal or less than the number of living wolves! The wolves overpower the remaining villagers and devour them whole.'
    elif len([x for x in session[1] if session[1][x][0] and get_role(x, 'role') in ACTUAL_WOLVES + ['traitor']]) == 0:
        # old version: teams['wolf'] == 0 and injured_wolves == 0:
        if [x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'monster']:
            win_team = 'monster'
            win_lore = "Game over! All the wolves are dead! As the villagers start preparing the BBQ, the monster{0} quickly kill{1} the remaining villagers, causing the monster{0} to win.".format('s' if len([x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'monster']) > 1 else '', '' if len([x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'monster']) > 1 else 's')
        else:
            if len([x for x in session[1] if session[1][x][0] and get_role(x, 'role') in ['cultist', 'minion']]) == teams['wolf'] and session[6] == 'evilvillage':
                win_team = 'village'
                win_lore = "Game over! All the wolves are dead! The villagers round up the remaining cultists, hang them, and live happily ever after."
            else:
                win_team = 'village'
                win_lore = 'All the wolves are dead! The surviving villagers gather the bodies of the dead wolves, roast them, and have a BBQ in celebration.'
    elif teams['village'] + teams['neutral'] >= teams['wolf'] and session[6] == 'evilvillage':
        if [x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'monster']:
            win_team = 'monster'
            win_lore = "Game over! The number of uninjured cultists is equal or less than the number of living villagers! as the villagers regain control over the village, the monster{0} quickly kill{1} the remaining villagers, causing the monster{0} to win.".format('s' if len([x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'monster']) > 1 else '', '' if len([x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'monster']) > 1 else 's')
        elif not [x for x in session[1] if session[1][x][0] and get_role(x, 'role') in ['cultist', 'minion']]:
            win_team = 'village'
            win_lore = "Game over! All the cultists are dead! The now-exposed wolves are captured and killed by the remaining villagers. A BBQ party commences shortly thereafter."
        else:
            win_team = 'village'
            win_lore = "Game over! The number of uninjured cultists is equal or less than the number of living villagers! They manage to regain control of the village and dispose of the remaining cultists."
    else:
        return None

    for player in session[1]:
        lovers = []
        for n in session[1][player][4]:
            if n.startswith('lover:'):
                lovers.append(n.split(':')[1])
        role = get_role(player, 'role')
        templates = get_role(player, 'templates')
        if get_role(player, 'role') == 'piper' and win_team == 'pipers':
            winners.append(player)
        if ('entranced' in session[1][player][4] or get_role(player, 'role') == 'succubus') and win_team == 'succubi':
            winners.append(player)
        if get_role(player, 'actualteam') == win_team and 'entranced' not in session[1][player][4] and 'charmed' not in session[1][player][4]:
            winners.append(player)
        if [x for x in lovers if session[1][x][0]]:
            winners.append(player)
        if get_role(player, 'role') == 'jester' and 'lynched' in session[1][player][4]:
            winners.append
        if get_role(player, 'role') == 'vengeful ghost' and not session[1][player][0] and [x.split(':')[1] for x in session[1][player][4] if x.startswith("vengeance:")] and [x.split(':')[1] for x in session[1][player][4] if x.startswith("vengeance:")].pop() != win_team:
            winners.append(player)
        if (get_role(player, 'role') == 'amnesiac' or (get_role(player, 'role') == 'vengeful ghost' and session[1][player][0])) and win_team == 'village' and 'entranced' not in session[1][player][4]:
            winners.append(player)
        if get_role(player, 'role') == 'jester' and 'lynched' in session[1][player][4]:
            winners.append(player)
        if get_role(player, 'role') == 'monster' and session[1][player][0] and win_team == 'monster':
            winners.append(player)
    return [win_team, win_lore + '\n\n' + end_game_stats(), winners]

def end_game_stats():
    role_msg = ""
    role_dict = {}
    for role in roles:
        role_dict[role] = []
    for player in session[1]:
        if 'traitor' in session[1][player][4]:
            session[1][player][1] = 'traitor'
            session[1][player][4].remove('traitor')
        if 'wolf_cub' in session[1][player][4]:
            session[1][player][1] = 'wolf cub'
            session[1][player][4].remove('wolf_cub')
        role_dict[session[1][player][1]].append(player)
        if 'cursed' in session[1][player][3]:
            role_dict['cursed villager'].append(player)
        if 'gunner' in session[1][player][3]:
            role_dict['gunner'].append(player)
        if 'assassin' in session[1][player][3]:
            role_dict['assassin'].append(player)
        if 'mayor' in session[1][player][3]:
            role_dict['mayor'].append(player)
        if 'sharpshooter' in session[1][player][3]:
            role_dict['sharpshooter'].append(player)

    for key in sort_roles(role_dict):
        value = sort_players(role_dict[key])
        if len(value) == 0:
            pass
        elif len(value) == 1:
            role_msg += "The **{}** was **{}**. ".format(key, get_name(value[0]))
        elif len(value) == 2:
            role_msg += "The **{}** were **{}** and **{}**. ".format(roles[key][1], get_name(value[0]), get_name(value[1]))
        else:
            role_msg += "The **{}** were **{}**, and **{}**. ".format(roles[key][1], '**, **'.join(map(get_name, value[:-1])), get_name(value[-1]))

    lovers = []

    for player in session[1]:
        for o in session[1][player][4]:
            if o.startswith("lover:"):
                lover = o.split(':')[1]
                lovers.append(tuple(sort_players([player, lover])))
    lovers = list(set(lovers))
    # create a list of unique lover pairs
    sorted_second_lover = sort_players(x[1] for x in lovers)
    sorted_first_lover = sort_players(x[0] for x in lovers)
    # sort by second lover then first lover in the pair
    lovers_temp = []
    for l in sorted_second_lover:
        for pair in list(lovers):
            if pair[1] == l:
                lovers_temp.append(pair)
                lovers.remove(pair)
    lovers = list(lovers_temp)
    lovers_temp = []
    for l in sorted_first_lover:
        for pair in list(lovers):
            if pair[0] == l:
                lovers_temp.append(pair)
                lovers.remove(pair)
    lovers = list(lovers_temp)
    if len(lovers) == 0:
        pass
    elif len(lovers) == 1:
        # *map(get_name, lovers[0]) just applies get_name to each lover then unpacks the result into format
        role_msg += "The **lovers** were **{}/{}**. ".format(*map(get_name, lovers[0]))
    elif len(lovers) == 2:
        role_msg += "The **lovers** were **{}/{}** and **{}/{}**. ".format(*map(get_name, lovers[0] + lovers[1]))
    else:
        role_msg += "The **lovers** were {}, and **{}/{}**. ".format(
            ', '.join('**{}/{}**'.format(*map(get_name, x)) for x in lovers[:-1]), *map(get_name, lovers[-1]))
    return role_msg

def get_name(player):
    member = client.get_server(WEREWOLF_SERVER).get_member(player)
    if member:
        return str(member.display_name)
    else:
        return str(player)

def get_player(string):
    string = string.lower()
    users = []
    discriminators = []
    nicks = []
    users_contains = []
    nicks_contains = []
    for player in session[1]:
        if string == player.lower() or string.strip('<@!>') == player:
            return player
        member = client.get_server(WEREWOLF_SERVER).get_member(player)
        if member:
            if member.name.lower().startswith(string):
                users.append(player)
            if string.strip('#') == member.discriminator:
                discriminators.append(player)
            if member.display_name.lower().startswith(string):
                nicks.append(player)
            if string in member.name.lower():
                users_contains.append(player)
            if string in member.display_name.lower():
                nicks_contains.append(player)
        elif get_player(player).lower().startswith(string):
            users.append(player)
    if len(users) == 1:
        return users[0]
    if len(discriminators) == 1:
        return discriminators[0]
    if len(nicks) == 1:
        return nicks[0]
    if len(users_contains) == 1:
        return users_contains[0]
    if len(nicks_contains) == 1:
        return nicks_contains[0]
    return None

def sort_players(players):
    fake = []
    real = []
    for player in players:
        if client.get_server(WEREWOLF_SERVER).get_member(player):
            real.append(player)
        else:
            fake.append(player)
    return sorted(real, key=get_name) + sorted(fake, key=int)

def get_role(player, level):
    # level: {team: reveal team only; actualteam: actual team; seen: what the player is seen as; death: role taking into account cursed and cultist and traitor; actual: actual role}
    # (terminology: role = what you are, template = additional things that can be applied on top of your role)
    # cursed, gunner, blessed, mayor, assassin are all templates
    # so you always have exactly 1 role, but can have 0 or more templates on top of that
    # revealing totem (and similar powers, like detective id) only reveal roles
    if player in session[1]:
        role = session[1][player][1]
        templates = session[1][player][3]
        if level == 'team':
            if roles[role][0] == 'wolf':
                if not role in ROLES_SEEN_VILLAGER:
                    return "wolf"
            return "village"
        elif level == 'actualteam':
            return roles[role][0]
        elif level == 'seen':
            seen_role = None
            if role in ROLES_SEEN_WOLF:
                seen_role = 'wolf'
            elif session[1][player][1] in ROLES_SEEN_VILLAGER:
                seen_role = 'villager'
            else:
                seen_role = role
            for template in templates:
                if template in ROLES_SEEN_WOLF:
                    seen_role = 'wolf'
                    break
                if template in ROLES_SEEN_VILLAGER:
                    seen_role = 'villager'
            return seen_role
        elif level == 'seenoracle':
            seen_role = get_role(player, 'seen')
            if seen_role != 'wolf':
                seen_role = 'villager'
            return seen_role
        elif level == 'death':
            returnstring = ''
            if role == 'traitor':
                returnstring += 'villager'
            else:
                returnstring += role
            return returnstring
        elif level == 'deathstats':
            returnstring = ''
            if role == 'traitor':
                returnstring += 'villager'
            else:
                returnstring += role
            return returnstring
        elif level == 'role':
            return role
        elif level == 'templates':
            return templates
        elif level == 'actual':
            return ' '.join(templates + [role])
    return None

def get_roles(gamemode, players):
    if gamemode.startswith('roles'):
        role_string = ' '.join(gamemode.split(' ')[1:])
        if role_string != '':
            gamemode_roles = {}
            separator = ','
            if ';' in role_string:
                separator = ';'
            for role_piece in role_string.split(separator):
                piece = role_piece.strip()
                if '=' in piece:
                    role, amount = piece.split('=')
                elif ':' in piece:
                    role, amount = piece.split(':')
                else:
                    return None
                amount = amount.strip()
                if amount.isdigit():
                    gamemode_roles[role.strip()] = int(amount)
            return gamemode_roles
    elif gamemode in gamemodes:
        if players in range(gamemodes[gamemode]['min_players'], gamemodes[gamemode]['max_players'] + 1):
            if gamemode == 'random':
                exit = False
                while not exit:
                    exit = True
                    available_roles = [x for x in roles if x not in TEMPLATES_ORDERED\
                                        and x not in ('villager', 'cultist')]
                    gamemode_roles = dict((x, 0) for x in available_roles)
                    gamemode_roles[random.choice([x for x in ACTUAL_WOLVES if x != 'wolf cub'])] += 1 # ensure at least 1 wolf that can kill
                    for i in range(players - 1):
                        gamemode_roles[random.choice(available_roles)] += 1
                    gamemode_roles['gunner'] = random.randrange(int(players ** 1.2 / 4))
                    gamemode_roles['cursed villager'] = random.randrange(int(players ** 1.2 / 3))
                    teams = {'village' : 0, 'wolf' : 0, 'neutral' : 0}
                    for role in gamemode_roles:
                        if role not in TEMPLATES_ORDERED:
                            teams[roles[role][0]] += gamemode_roles[role]
                    if teams['wolf'] >= teams['village'] + teams['neutral']:
                        exit = False
                for role in dict(gamemode_roles):
                    if gamemode_roles[role] == 0:
                        del gamemode_roles[role]
                return gamemode_roles
            else:
                gamemode_roles = {}
                for role in roles:
                    if role in gamemodes[gamemode]['roles'] and gamemodes[gamemode]['roles'][role][\
                    players - MIN_PLAYERS] > 0:
                        gamemode_roles[role] = gamemodes[gamemode]['roles'][role][players - MIN_PLAYERS]
                return gamemode_roles
    return None

def get_votes(totem_dict):
    voteable_players = [x for x in session[1] if session[1][x][0]]
    able_players = [x for x in voteable_players if 'injured' not in session[1][x][4]]
    vote_dict = {'abstain' : 0}
    for player in voteable_players:
        vote_dict[player] = 0
    able_voters = [x for x in able_players if totem_dict[x] == 0]
    for player in able_voters:
        if session[1][player][2] in vote_dict:
            vote_dict[session[1][player][2]] += 1
        if 'influence_totem' in session[1][player][4] and session[1][player][2] in vote_dict:
            vote_dict[session[1][player][2]] += 1
    for player in [x for x in able_players if totem_dict[x] != 0]:
        if totem_dict[player] < 0:
            vote_dict['abstain'] += 1
        else:
            for p in [x for x in voteable_players if x != player]:
                vote_dict[p] += 1
    return vote_dict

def _autocomplete(string, lst):
    if string in lst:
        return (string, 1)
    else:
        choices = []
        for item in lst:
            if item.startswith(string):
                choices.append(item)
        if len(choices) == 1:
            return (choices[0], 1)
        else:
            return (choices, len(choices))

def verify_gamemode(gamemode, verbose=True):
    msg = ''
    good = True
    for i in range(gamemodes[gamemode]['max_players'] - gamemodes[gamemode]['min_players'] + 1):
        total = sum(gamemodes[gamemode]['roles'][role][i + gamemodes[gamemode]['min_players'] - MIN_PLAYERS] for role in gamemodes[gamemode]['roles']\
        if role not in TEMPLATES_ORDERED)
        msg += str(total)
        if total != i + gamemodes[gamemode]['min_players'] and total != 0:
            good = False
            msg += ' - should be ' + str(i + gamemodes[gamemode]['min_players'])
        msg += '\n'
    msg = msg[:-1]
    if verbose:
        return msg
    else:
        return good

def verify_gamemodes(verbose=True):
    msg = ''
    good = True
    for gamemode in sorted(gamemodes):
        msg += gamemode + '\n'
        result = verify_gamemode(gamemode)
        resultlist = result.split('\n')
        for i in range(len(resultlist)):
            if resultlist[i] != str(i + gamemodes[gamemode]['min_players']) and resultlist[i] != '0':
                msg += result
                good = False
                break
        else:
            msg += 'good'
        msg += '\n\n'
    if verbose:
        return msg
    else:
        return good

async def wolfchat(message, author=''):
    if isinstance(message, discord.Message):
        author = message.author.id
        msg = message.content
    else:
        msg = str(message)

    member = client.get_server(WEREWOLF_SERVER).get_member(author)
    if member:
        athr = member.display_name
    else:
        athr = author
    for wolf in [x for x in session[1] if x != author and session[1][x][0] and session[1][x][1] in WOLFCHAT_ROLES and client.get_server(WEREWOLF_SERVER).get_member(x)]:
        try:
            pfx = "**[Wolfchat]**"
            if athr != '':
                pfx += " message from **{}**".format(athr)
            await client.send_message(client.get_server(WEREWOLF_SERVER).get_member(wolf), "{}: {}".format(pfx, msg))
        except discord.Forbidden:
            pass

async def player_idle(message):
    while message.author.id in session[1] and not session[0]:
        await asyncio.sleep(1)
    while message.author.id in session[1] and session[0] and session[1][message.author.id][0]:
        def check(msg):
            if not message.author.id in session[1] or not session[1][message.author.id][0] or not session[0]:
                return True
            if msg.author.id == message.author.id and msg.channel.id == client.get_channel(GAME_CHANNEL).id:
                return True
            return False
        msg = await client.wait_for_message(author=message.author, channel=client.get_channel(GAME_CHANNEL), timeout=PLAYER_TIMEOUT, check=check)
        if msg == None and message.author.id in session[1] and session[0] and session[1][message.author.id][0]:
            await send_lobby(message.author.mention + "**, you have been idling for a while. Please say something soon or you might be declared dead.**")
            try:
                await client.send_message(message.author, "**You have been idling in #" + client.get_channel(GAME_CHANNEL).name + " for a while. Please say something soon or you might be declared dead.**")
            except discord.Forbidden:
                pass
            msg = await client.wait_for_message(author=message.author, channel=client.get_channel(GAME_CHANNEL), timeout=PLAYER_TIMEOUT2, check=check)
            if msg == None and message.author.id in session[1] and session[0] and session[1][message.author.id][0]:
                await send_lobby("**" + get_name(message.author.id) + "** didn't get out of bed for a very long time and has been found dead. "
                                          "The survivors bury the **" + get_role(message.author.id, 'death') + '**.')
                if message.author.id in stasis:
                    stasis[message.author.id] += QUIT_GAME_STASIS
                else:
                    stasis[message.author.id] = QUIT_GAME_STASIS
                await player_deaths({message.author.id : ('idle', "bot")})
                await check_traitor()
                await log(1, "{} ({}) IDLE OUT".format(message.author.display_name, message.author.id))

def is_online(user_id):
    member = client.get_server(WEREWOLF_SERVER).get_member(user_id)
    if member:
        if member.status in [discord.Status.online, discord.Status.idle]:
            return True
    return False

async def player_deaths(players_dict): # players_dict = {dead : (reason, kill_team), ...}
    for player in players_dict:
        reason = players_dict[player][0]
        kill_team = players_dict[player][1]
        if player not in session[1]:
            return
        ingame = 'IN GAME'
        if session[0] and reason != 'game cancel':
            session[1][player][0] = False
            lovers = []
            for o in session[1][player][4]:
                if o.startswith('lover:'):
                    lovers.append(o.split(":")[1])
            assassin_target = ""
            for o in session[1][player][4]:
                if o.startswith('assassinate:') and "assassin" in get_role(player, "templates") and kill_team != "bot":
                    assassin_target = o.split(":")[1]
                    break
            if session[0]:
                if assassin_target:
                    if session[1][assassin_target][0] and assassin_target not in players_dict and not ("protection_totem2" in session[1][assassin_target][4] or "guarded" in session[1][assassin_target][4]) and not 'blessed' in get_role(assassin_target, 'templates') and not [x for x in session[1][assassin_target][4] if x.startswith('bodyguard:')]:
                        await send_lobby("Before dying, **{0}** quickly slits **{1}**'s throat. The village mourns the loss of a{2} **{3}**.".format(get_name(player), get_name(assassin_target), "n" if get_role(assassin_target, "death").lower()[0] in ['a', 'e', 'i', 'o', 'u'] else "", get_role(assassin_target, "death")))
                        await player_deaths({assassin_target : ("assassination", get_role(player, 'actualteam'))})
                    elif 'blessed' in get_role(assassin_target, 'templates'):
                        try:
                            await client.send_message(client.get_server(WEREWOLF_SERVER).get_member(player), "**{0}** seems to be blessed, causing your assassination attempt to fail.".format(get_name(assassin_target)))
                        except discord.Forbidden:
                            pass
                    elif "protection_totem2" in session[1][assassin_target][4]:
                        await send_lobby("Before dying, **{0}** quickly attempts to slit **{1}**'s throat; however, {1}'s totem emits a brilliant flash of light, causing the attempt to miss.".format(get_name(player), get_name(assassin_target)))
                    elif "guarded" in session[1][assassin_target][4]:
                        await send_lobby("Before dying, **{0}** quickly attempts to slit **{1}**'s throat; however, a guardian angel was on duty and able to foil the attempt.".format(get_name(player), get_name(assassin_target)))
                    elif [x for x in session[1][assassin_target][4] if x.startswith('bodyguard:')]:
                        await send_lobby("Sensing danger, **{2}** shoves **{1}** aside to save them from **{0}**.".format(get_name(player), get_name(assassin_target), get_name([x for x in session[1][assassin_target][4] if x.startswith('bodyguard:')].pop().split(':')[1])))
                for lover in lovers:
                    if session[1][lover][0] and kill_team != "bot" and lover not in players_dict:
                        await send_lobby("Saddened by the loss of their lover, **{0}**, a{1} **{2}**, commits suicide.".format(get_name(lover), "n" if get_role(lover, "death").lower()[0] in ['a', 'e', 'i', 'o', 'u'] else "", get_role(lover, "death")))
                        await player_deaths({lover : ("lover suicide", kill_team)})
                if 'desperation_totem' in session[1][player][4] and reason == "lynch":
                    end_voter = ""
                    for x in session[1]:
                        if max(list(chain.from_iterable([[i for i in session[1][x][4] if i.startswith("vote:")] for x in session[1] if session[1][x][0]]))) in session[1][x][4] and session[1][x][2] == player:
                            end_voter = x
                    if end_voter and end_voter not in players_dict and get_role(player, 'role') != 'fool':
                        await send_lobby("As the noose is being fitted, **{0}**'s totem emits a brilliant flash of light. When the villagers are able to see again, they discover that **{1}**, a{2} **{3}**, has fallen over dead.".format(get_name(player), get_name(end_voter), "n" if get_role(end_voter, "death").lower()[0] in ['a', 'e', 'i', 'o', 'u'] else "", get_role(end_voter, "death")))
                        await player_deaths({end_voter : ("desperation", get_role(player, 'actualteam'))})
                if get_role(player, 'role') ==  'succubus' and not [x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'succubus']:
                    if kill_team != 'bot':
                        foul_dict = {}
                        foul_message = ''
                        for entranced in [x for x in session[1] if session[1][x][0] and 'entranced' in session[1][x][4] and x not in players_dict]:
                            foul_message += "As the last remaining succubus dies, a foul curse causes **{0}**, a{1} **{2}** to wither away and die in front of the astonished village.\n".format(get_name(entranced), "n" if get_role(entranced, "death").lower()[0] in ['a', 'e', 'i', 'o', 'u'] else "", get_role(entranced, "death"))
                            foul_dict[entranced] = ('foul curse', kill_team)
                        if foul_message:
                            await send_lobby(foul_message)
                            await player_deaths(foul_dict)
                    else:
                        for entranced in [x for x in session[1] if session[1][x][0] and 'entranced' in session[1][x][4] and x not in players_dict]:
                            session[1][entranced][4].remove('entranced')
                            member = client.get_server(WEREWOLF_SERVER).get_member(entranced)
                            if member:
                                try:
                                    await client.send_message(member, "You are no longer entranced. **Your win conditions have reset to normal.**")
                                except discord.Forbidden:
                                    pass
                if get_role(player, 'role') == "vengeful ghost" and (kill_team != "bot" and not reason == 'gunner suicide'):
                    session[1][player][4].append("vengeance:{}".format(kill_team))
                    member = client.get_server(WEREWOLF_SERVER).get_member(player)
                    if member:
                        try:
                            await client.send_message(member, "OOOooooOOOOooo! You are the **vengeful ghost**. It is now your job to exact your revenge on the **{0}** that killed you.".format('villagers' if kill_team == 'village' else 'wolves'))
                        except discord.Forbidden:
                            pass
                if get_role(player, 'role') == 'piper' and not [x for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'piper']:
                    for player_ in session[1]:
                        session[1][player_][4] = [x for x in session[1][player_][4] if not x in ['charmed', 'tocharm']]
        else:
            ingame = 'NOT IN GAME'
            del session[1][player]
        member = client.get_server(WEREWOLF_SERVER).get_member(player)
        if member:
            await client.remove_roles(member, PLAYERS_ROLE)
        if session[0] and kill_team != "bot":
            if get_role(player, 'role') == 'wolf cub':
                for p in session[1]:
                    if session[1][p][0] and get_role(p, 'role') in ACTUAL_WOLVES + ['traitor']:
                        session[1][p][4].append('angry')
        for p in [x for x in session[1] if "assassin" in get_role(x, "templates") and "assassinate:{}".format(player) in session[1][x][4]]:
            session[1][p][4] = [x for x in session[1][p][4] if x != "assassinate:{}".format(player)]
            if get_role(p, 'role') == 'village drunk':
                session[1][p][4].append('assassinate:{}'.format(random.choice([x for x in session[1] if x != p])))
        await log(0, "{} ({}) PLAYER DEATH {} FOR {}".format(get_name(player), player, ingame, reason))

async def check_traitor():
    if not session[0] and win_condition() == None:
        return
    wolf_cub_turned = False
    for other in [session[1][x][4] for x in session[1]]:
        if 'traitor' in other:
            # traitor already turned
            return
    wolf_team_alive = [x for x in session[1] if session[1][x][0] and get_role(x, 'role') in [
        'traitor'] + ACTUAL_WOLVES]
    if len(wolf_team_alive) == 0:
        # no wolves alive; don't play traitor turn message
        return
    wolf_team_no_traitors = [x for x in wolf_team_alive if get_role(x, 'role') != 'traitor']
    wolf_team_no_cubs = [x for x in wolf_team_no_traitors if get_role(x, 'role') != 'wolf cub']
    if len(wolf_team_no_cubs) == 0:
        cubs = [x for x in wolf_team_alive if get_role(x, 'role') == 'wolf cub']
        if cubs:
            await log(1, ', '.join(cubs) + " grew up into wolf")
            for cub in cubs:
                session[1][cub][4].append('wolf_cub')
                session[1][cub][1] = 'wolf'
                member = client.get_server(WEREWOLF_SERVER).get_member(cub)
                if member:
                    try:
                        await client.send_message(member, "You have grown up into a wolf and vowed to take revenge for your dead parents!")
                    except discord.Forbidden:
                        pass
                    await send_lobby("**The villagers listen horrified as they hear growling deepen in pitch. The wolf will do whatever it takes to avenge their parents!**")
    if len(wolf_team_no_traitors) == 0:
        traitors = [x for x in wolf_team_alive if get_role(x, 'role') == 'traitor']
        await log(1, ', '.join(traitors) + " turned into wolf")
        for traitor in traitors:
            session[1][traitor][4].append('traitor')
            session[1][traitor][1] = 'wolf'
            member = client.get_server(WEREWOLF_SERVER).get_member(traitor)
            if member:
                try:
                    await client.send_message(member, "HOOOOOOOOOWL. You have become... a wolf!\nIt is up to you to avenge your fallen leaders!")
                except discord.Forbidden:
                    pass
        await send_lobby("**The villagers, during their celebrations, are frightened as they hear a loud howl. The wolves are not gone!**")

def sort_roles(role_list):
    role_list = list(role_list)
    result = []
    for role in WOLF_ROLES_ORDERED + VILLAGE_ROLES_ORDERED + NEUTRAL_ROLES_ORDERED + TEMPLATES_ORDERED:
        result += [role] * role_list.count(role)
    return result

async def run_game():
    await client.change_presence(game=client.get_server(WEREWOLF_SERVER).me.game, status=discord.Status.dnd)
    session[0] = True
    session[2] = False
    if session[6] == '':
        vote_dict = {}
        for player in session[1]:
            vote = session[1][player][2]
            if vote in vote_dict:
                vote_dict[vote] += 1
            elif vote != '':
                vote_dict[vote] = 1
        for gamemode in vote_dict:
            if vote_dict[gamemode] >= len(session[1]) // 2 + 1:
                session[6] = gamemode
                break
        else:
            if datetime.now().date() == __import__('datetime').date(2018, 4, 1):
                session[6] = random.choice(gamemodes)
            else:
                session[6] = 'default'
    for player in session[1]:
        session[1][player][1] = ''
        session[1][player][2] = ''
    perms = client.get_channel(GAME_CHANNEL).overwrites_for(client.get_server(WEREWOLF_SERVER).default_role)
    perms.send_messages = False
    await client.edit_channel_permissions(client.get_channel(GAME_CHANNEL), client.get_server(WEREWOLF_SERVER).default_role, perms)
    if not get_roles(session[6], len(session[1])):
        session[6] = 'default' # Fallback if invalid number of players for gamemode or invalid gamemode somehow

    for stasised in [x for x in stasis if stasis[x] > 0]:
        stasis[stasised] -= 1
    await send_lobby("<@{}>, Welcome to Werewolf, the popular detective/social party game (a theme of Mafia). "
                              "Using the **{}** game mode with **{}** players.\nAll players check for PMs from me for instructions. "
                              "If you did not receive a pm, please let {} know.".format('> <@'.join(sort_players(session[1])),
                              'roles' if session[6].startswith('roles') else session[6], len(session[1]),
                              client.get_server(WEREWOLF_SERVER).get_member(OWNER_ID).name))
    for i in range(RETRY_RUN_GAME):
        try:
            if datetime.now().date() == __import__('datetime').date(2018, 4, 1):
                gamemode = "mudkip" if session[6] == 'default' else ('default' if session[6] == 'mudkip' else session[6])
            else:
                gamemode = session[6]
            await assign_roles(gamemode)
            break
        except:
            await log(2, "Role attribution failed with error: ```py\n{}\n```".format(traceback.format_exc()))
    else:
        msg = await send_lobby("<@{}>, role attribution failed 3 times. Cancelling game. "
                                                                          "Here is some debugging info:```py\n{}\n```".format(
                  '> <@'.join(sort_players(session[1])), session))
        await cmd_fstop(msg, '-force')
        return

    for i in range(RETRY_RUN_GAME):
        try:
            if i == 0:
                await game_loop()
            else:
                await game_loop(session)
            break
        except:
            await send_lobby("<@{}>, game loop broke. Attempting to resume game...".format(
                '> <@'.join(sort_players(session[1])), session))
            await log(3, "Game loop broke with error: ```py\n{}\n```".format(traceback.format_exc()))
    else:
        msg = await send_lobby("<@{}>, game loop broke 3 times. Cancelling game.".format(
                  '> <@'.join(sort_players(session[1])), session))
        await cmd_fstop(msg, '-force')

async def game_loop(ses=None):
    if ses:
        await send_lobby("<@{}>, Welcome to Werewolf, the popular detective/social party game (a theme of Mafia). "
                              "Using the **{}** game mode with **{}** players.\nAll players check for PMs from me for instructions. "
                              "If you did not receive a pm, please let {} know.".format('> <@'.join(sort_players(session[1])),
                              'roles' if session[6].startswith('roles') else session[6], len(session[1]),
                              client.get_server(WEREWOLF_SERVER).get_member(OWNER_ID).name))
        globals()['session'] = ses
    await log(1, "Game object: ```py\n{}\n```".format(session))
    night = 1
    # GAME START
    while win_condition() == None and session[0]:
        if not session[2]: # NIGHT
            session[3][0] = datetime.now()
            log_msg = ['SUNSET LOG:']
            num_kills = 1
            for player in session[1]:
                member = client.get_server(WEREWOLF_SERVER).get_member(player)
                role = get_role(player, 'role')
                if role in ['shaman', 'crazed shaman', 'wolf shaman'] and session[1][player][0]:
                    if role == 'shaman':
                        if session[6] == "mudkip":
                            session[1][player][2] = random.choice(["pestilence_totem", "death_totem"]) if not night == 1 else "death_totem"
                        else:
                            session[1][player][2] = random.choice(SHAMAN_TOTEMS)
                    elif role == 'wolf shaman':
                        if session[6] == "mudkip":
                            session[1][player][4].append("totem:{}".format(random.choice(["protection_totem", "misdirection_totem"])))
                        else:
                            session[1][player][4].append("totem:{}".format(random.choice(WOLF_SHAMAN_TOTEMS)))
                    elif role == 'crazed shaman':
                        session[1][player][2] = random.choice(list(totems))
                    log_msg.append("{} ({}) HAS {}".format(get_name(player), player, (session[1][player][2] if role != "wolf shaman" else [x.split(":")[1] for x in session[1][player][4] if x.startswith("totem:")].pop())))
                elif role == 'hunter' and session[1][player][0] and 'hunterbullet' not in session[1][player][4]:
                    session[1][player][2] = player
                elif role == 'doomsayer':
                    session[1][player][4].append('doom:{}'.format(random.choice(['sick', 'lycan', 'death'])))
                elif role == 'piper':
                    session[1][player][4].append('charm')
                if night == 1:
                    await _send_role_info(player)
                else:
                    await _send_role_info(player, sendrole=False)        
            await log(1, '\n'.join(log_msg))
            
            session[3][0] = datetime.now()
            await send_lobby("It is now **nighttime**.")
            warn = False
            # NIGHT LOOP
            while win_condition() == None and not session[2] and session[0]:
                end_night = True
                wolf_kill_dict = {}
                num_wolves = 0
                for player in session[1]:
                    role = get_role(player, 'role')
                    templates = get_role(player, 'templates')
                    if session[1][player][0]:
                        if role in ['wolf', 'werecrow', 'doomsayer', 'werekitten', 'wolf shaman', 'wolf mystic', 'sorcerer',
                                    'seer', 'oracle', 'harlot', 'hunter', 'augur',
                                    'guardian angel', 'succubus', 'hag', 'warlock', 'bodyguard'] and 'silence_totem2' not in session[1][player][4]:
                            end_night = end_night and (session[1][player][2] != '')
                        if role in ['shaman', 'crazed shaman']:
                            end_night = end_night and (session[1][player][2] in session[1])
                        if role == "wolf shaman":
                            end_night = end_night and not [x for x in session[1][player][4] if x.startswith("totem:")]
                        if role == 'matchmaker':
                            end_night = end_night and 'match' not in session[1][player][4]
                        if role == 'piper':
                            end_night = end_night and 'charm' not in session[1][player][4]
                        if "assassin" in templates:
                            end_night = end_night and [x for x in session[1][player][4] if x.startswith("assassinate:")]
                        if role == "vengeful ghost" and [x for x in session[1][player][4] if x.startswith("vengeance:")]:
                            end_night = end_night and session[1][player][4] != ''
                        if role == 'doomsayer':
                            end_night = end_night and not [x for x in session[1][player][4] if x.startswith("doom:")]
                        if roles[role][0] == 'wolf' and role in COMMANDS_FOR_ROLE['kill']:
                            num_wolves += 1
                            num_kills = session[1][player][4].count('angry') + 1
                            t = session[1][player][2]
                            # if no target then t == '' and that will be a key in wolf_kill_dict
                            targets = t.split(',')
                            for target in targets:
                                try:
                                    wolf_kill_dict[target] += 1
                                except KeyError:
                                    wolf_kill_dict[target] = 1
                end_night = end_night and len(wolf_kill_dict) == num_kills
                for t in wolf_kill_dict:
                    end_night = end_night and wolf_kill_dict[t] == num_wolves
                    # night will only end if all wolves select same target(s)
                end_night = end_night or (datetime.now() - session[3][0]).total_seconds() > NIGHT_TIMEOUT
                if end_night:
                    session[2] = True
                    session[3][1] = datetime.now() # attempted fix for using !time right as night ends
                if (datetime.now() - session[3][0]).total_seconds() > NIGHT_WARNING and warn == False:
                    warn = True
                    await send_lobby("**A few villagers awake early and notice it is still dark outside. "
                                            "The night is almost over and there are still whispers heard in the village.**")
                await asyncio.sleep(0.1)
            night_elapsed = datetime.now() - session[3][0]
            session[4][0] += night_elapsed

            # BETWEEN NIGHT AND DAY
            session[3][1] = datetime.now() # fixes using !time screwing stuff up
            killed_msg = ''
            killed_dict = {}
            for player in session[1]:
                if "blessed" in get_role(player, 'templates'):
                    killed_dict[player] = -1
                else:
                    killed_dict[player] = 0
            killed_players = []
            alive_players = sort_players(x for x in session[1] if (session[1][x][0] or (get_role(x, 'role') == "vengeful ghost" and [a for a in session[1][x][4] if a.startswith("vengeance:")])))
            log_msg = ["SUNRISE LOG:"]
            if session[0]:
                for player in alive_players:
                    role = get_role(player, 'role')
                    templates = get_role(player, 'templates')
                    member = client.get_server(WEREWOLF_SERVER).get_member(player)
                    if "silence_totem2" in session[1][player][4] and (role != 'matchmaker'):
                        if "assassin" in templates and not [x for x in session[1][player][4] if x.startswith("assassinate:")]:
                            if "misdirection_totem2" in session[1][player][4]:
                                target = misdirect(player)
                            else:
                                target = random.choice([x for x in alive_players if x != player and "luck_totem2" not in session[1][x][4]])
                            session[1][player][4].append("assassinate:{}".format(target))
                            log_msg.append("{0} ({1}) TARGET RANDOMLY {2} ({3})".format(get_name(player), player, get_name(target), target))

                            if member:
                                try:
                                    await client.send_message(member, "Because you forgot to select a target at night, you are now targeting **{0}**.".format(get_name(target)))
                                except discord.Forbidden:
                                    pass
                        continue
                    if role == 'doomsayer':
                        session[1][player][4] = [x for x in session[1][player][4] if not x.startswith('doom:')]
                    if role == 'piper':
                        session[1][player][4] = [x for x in session[1][player][4] if not x == 'charm']
                    if (role in ['shaman', 'crazed shaman'] and session[1][player][2] in totems) or (role == "wolf shaman" and [x for x in session[1][player][4] if x.startswith("totem:")]):
                        if "misdirection_totem2" in session[1][player][4]:
                            totem_target = misdirect(player)
                        else:
                            totem_target = random.choice([x for x in alive_players if x != player and "luck_totem2" not in session[1][x][4]])
                        if role in ['shaman', 'crazed shaman']:
                            totem = session[1][player][2]
                        else:
                            totem = [x for x in session[1][player][4] if x.startswith("totem:")][0].split(":")[1]
                        session[1][totem_target][4].append(totem)
                        if role in ['shaman', 'crazed shaman']:
                            session[1][player][2] = totem_target
                        else:
                            session[1][player][4] = [x for x in session[1][player][4] if not x.startswith("totem:")]
                        session[1][player][4] = [x for x in session[1][player][4] if not x.startswith("lasttarget")] + ["lasttarget:{}".format(totem_target)]
                        log_msg.append(player + '\'s ' + totem + ' given to ' + totem_target)
                        if member:
                            try:
                                random_given = "wtf? this is a bug; pls report to admins"
                                if role in ['shaman', 'wolf shaman']:
                                    random_given = "Because you forgot to give your totem out at night, your **{0}** was randomly given to **{1}**.".format(
                                        totem.replace('_', ' '), get_name(totem_target))
                                elif role == 'crazed shaman':
                                    random_given = "Because you forgot to give your totem out at night, your totem was randomly given to **{0}**.".format(get_name(totem_target))
                                await client.send_message(member, random_given)
                            except discord.Forbidden:
                                pass
                    elif role == 'matchmaker' and 'match' in session[1][player][4] and str(session[4][1]) == "0:00:00":
                        trycount = 0
                        alreadytried = []
                        while True:
                            player1 = random.choice([x for x in session[1] if session[1][x][0]])
                            player2 = random.choice([x for x in session[1] if session[1][x][0] and x != player1])
                            if not ("lover:" + player2 in session[1][player1][4] or "lover:" + player1 in session[1][player2][4]):
                                session[1][player][4].remove('match')
                                session[1][player1][4].append('lover:' + player2)
                                session[1][player2][4].append('lover:' + player1)
                                try:
                                    await client.send_message(client.get_server(WEREWOLF_SERVER).get_member(player1),
                                                        "You are in love with **{0}**. If that player dies for any reason, the pain will be too much for you to bear and you will commit suicide.".format(
                                                            get_name(player2)))
                                except:
                                    pass
                                try:
                                    await client.send_message(client.get_server(WEREWOLF_SERVER).get_member(player2),
                                                        "You are in love with **{0}**. If that player dies for any reason, the pain will be too much for you to bear and you will commit suicide.".format(
                                                            get_name(player1)))
                                except:
                                    pass
                                await log(1, "{0} ({1}) MATCH {2} ({3}) AND {4} ({5})".format(get_name(player), player, get_name(player1), player1, get_name(player2), player2))
                                break
                            elif [player1 + player2] not in alreadytried:
                                trycount += 1
                                alreadytried.append([player1 + player2])
                            if trycount >= (len([x for x in session[1] if session[1][x][0]])*(len([x for x in session[1] if session[1][x][0]]) - 1)): #all possible lover sets are done
                                break
                        try:
                            await client.send_message(client.get_server(WEREWOLF_SERVER).get_member(player),
                                                      "Because you forgot to choose lovers at night, two lovers have been selected for you.")
                        except:
                            pass
                    elif role == 'harlot' and session[1][player][2] == '':
                        session[1][player][2] = player
                        log_msg.append("{0} ({1}) STAY HOME".format(get_name(player), player))
                        if member:
                            try:
                                await client.send_message(member, "You will stay home tonight.")
                            except discord.Forbidden:
                                pass
                    elif role == 'succubus' and session[1][player][2] == '':
                        session[1][player][2] = player
                        log_msg.append("{0} ({1}) STAY HOME".format(get_name(player), player))
                        if member:
                            try:
                                await client.send_message(member, "You have chosen to not entrance anyone tonight.")
                            except discord.Forbidden:
                                pass
                    elif role == 'hunter' and session[1][player][2] == '':
                        session[1][player][2] = player
                        log_msg.append("{0} ({1}) PASS".format(get_name(player), player))
                        if member:
                            try:
                                await client.send_message(member, "You have chosen to not kill anyone tonight.")
                            except discord.Forbidden:
                                pass
                    elif role == 'guardian angel' and session[1][player][2] in ['pass', '']:
                        session[1][player][2] = ''
                        session[1][player][4][:] = [x for x in session[1][player][4] if not x.startswith('lasttarget:')]
                        # clear previous target since no target selected
                        log_msg.append("{0} ({1}) NO GUARD".format(get_name(player), player))
                        if member and not session[1][player][2]:
                            try:
                                await client.send_message(member, "You have chosen to not guard anyone tonight.")
                            except discord.Forbidden:
                                pass
                    elif role == 'vengeful ghost' and [x for x in session[1][player][4] if x.startswith('vengeance:')] and not session[1][player][0] and session[1][player][2] == '' and 'consecrated' not in session[1][player][4] and 'driven' not in session[1][player][4]:
                        against = 'wolf'
                        if [x for x in session[1][player][4] if x.startswith("vengeance:")]:
                            against = [x.split(':')[1] for x in session[1][player][4] if x.startswith('vengeance:')].pop()
                        if "misdirection_totem2" in session[1][player][4]:
                            target = misdirect(player, alive_players=[x for x in alive_players if x != player and get_role(x, 'actualteam') == against and 'luck_totem2' not in session[1][x][4]])
                        else:
                            target = random.choice([x for x in alive_players if x != player and "luck_totem2" not in session[1][x][4] and get_role(x, 'actualteam') == against])
                        session[1][player][2] = target
                        log_msg.append("{0} ({1}) VENGEFUL KILL {2} ({3})".format(get_name(player), player, get_name(target), target))
                    if "assassin" in templates and not [x for x in session[1][player][4] if x.startswith("assassinate:")]:
                        if "misdirection_totem2" in session[1][player][4]:
                            target = misdirect(player)
                        else:
                            target = random.choice([x for x in alive_players if x != player and "luck_totem2" not in session[1][x][4]])
                        session[1][player][4].append("assassinate:{}".format(target))
                        log_msg.append("{0} ({1}) TARGET RANDOMLY {2} ({3})".format(get_name(player), player, get_name(target), target))
                        if member:
                            try:
                                await client.send_message(member, "Because you forgot to select a target at night, you are now targeting **{0}**.".format(get_name(target)))
                            except discord.Forbidden:
                                pass

            # BELUNGA
            for player in [x for x in session[1] if session[1][x][0]]:
                for i in range(session[1][player][4].count('belunga_totem')):
                    session[1][player][4].append(random.choice(list(totems) + ['belunga_totem', 'bullet']))
                    if random.random() < 0.1 and ('gunner' not in get_role(player, 'templates') or 'sharpshooter' not in get_role(player, 'templates')):
                        session[1][player][3].append('gunner')

            # Wolf kill
            wolf_votes = {}
            wolf_killed = []
            gunner_revenge = []
            wolf_deaths = []
            wolf_turn = []

            for player in alive_players:
                if roles[get_role(player, 'role')][0] == 'wolf' and get_role(player, 'role') in COMMANDS_FOR_ROLE['kill']:
                    for t in session[1][player][2].split(','):
                        if t in wolf_votes:
                            wolf_votes[t] += 1
                        elif t != "":
                            wolf_votes[t] = 1
            if wolf_votes != {}:
                sorted_votes = sorted(wolf_votes, key=lambda x: wolf_votes[x], reverse=True)
                wolf_killed = sort_players(sorted_votes[:num_kills])
                log_msg.append("WOLFKILL: " + ', '.join('{} ({})'.format(get_name(x), x) for x in wolf_killed))
                for k in wolf_killed:
                    if get_role(k, 'role') == 'harlot' and session[1][k][2] != k:
                        killed_msg += "The wolves' selected victim was not at home last night, and avoided the attack.\n"
                    elif get_role(k, 'role') == 'monster':
                        pass
                    else:
                        killed_dict[k] += 1
                        wolf_deaths.append(k)

            # Guardian Angel stuff
            guarded = []
            guardeded = [] # like protect_totemed

            for angel in [x for x in alive_players if get_role(x, 'role') == 'guardian angel']:
                target = session[1][angel][2]
                if target: # GA makes more sense working on target even if they are harlot not at home
                    killed_dict[target] -= 50
                    guarded.append(target)

            # Harlot stuff
            for harlot in [x for x in alive_players if get_role(x, 'role') == 'harlot']:
                visited = session[1][harlot][2]
                if visited != harlot:
                    if visited in wolf_killed and not ('protection_totem' in session[1][visited][4] or 'blessed' in session[1][visited][4] or harlot in guarded):
                        killed_dict[harlot] += 1
                        killed_msg += "**{}**, a **harlot**, made the unfortunate mistake of visiting the victim's house last night and is now dead.\n".format(get_name(harlot))
                        wolf_deaths.append(harlot)
                    elif get_role(visited, 'role') in ACTUAL_WOLVES:
                        killed_dict[harlot] += 1
                        killed_msg += "**{}**, a **harlot**, made the unfortunate mistake of visiting a wolf's house last night and is now dead.\n".format(get_name(harlot))
                        wolf_deaths.append(harlot)

            # Succubus stuff
            for succubus in [x for x in alive_players if get_role(x, 'role') == 'succubus']:
                visited = session[1][succubus][2]
                if visited != succubus:
                    if visited in wolf_killed and not ('protection_totem' in session[1][visited][4] or 'blessed' in session[1][visited][4] or succubus in guarded):
                        killed_dict[succubus] += 1
                        killed_msg += "**{}**, a **succubus**, made the unfortunate mistake of visiting the victim's house last night and is now dead.\n".format(get_name(succubus))
                        wolf_deaths.append(succubus)
            for disobeyer in [x for x in alive_players if 'disobey' in session[1][x][4]]:
                if random.random() < 0.5:
                    killed_dict[disobeyer] += 100 # this is what happens to bad bois

            # Hag stuff
            for hag in [x for x in alive_players if get_role(x, 'role') == 'hag']:
                hexed = session[1][hag][2]
                if hexed:
                    session[1][hexed][4].append('hex')

            # Doomsayer stuff
            for doomsayer in [x for x in session[1] if get_role(x, 'role') == 'doomsayer' and [a for a in session[1][x][4] if a.startswith('doomdeath:')]]:
                target = [a.split(':')[1] for a in session[1][doomsayer][4] if a.startswith('doomdeath:')].pop()
                killed_dict[target] += 1
                session[1][doomsayer][4] = [a for a in session[1][doomsayer][4] if not a.startswith('doomdeath:')]

            # Hunter stuff
            for hunter in [x for x in session[1] if get_role(x, 'role') == 'hunter']:
                target = session[1][hunter][2]
                if target not in [hunter, '']:
                    if 'hunterbullet' in session[1][hunter][4]:
                        session[1][hunter][4].remove('hunterbullet')
                        killed_dict[target] += 100

            # Bodyguard stuff
            for bodyguard in [x for x in alive_players if get_role(x, 'role') == 'bodyguard']:
                target = session[1][bodyguard][2]
                if target in session[1]:
                    if target in wolf_killed and not ('protection_totem' in session[1][target][4] or 'blessed' in session[1][target][4] or bodyguard in guarded):
                        killed_dict[bodyguard] += 1
                        print(killed_dict[bodyguard])
                        killed_dict[target] -= 1
                        print(killed_dict[target])
                        killed_msg += "**{}** sacrificed their life to guard that of another.\n".format(get_name(bodyguard))
                        wolf_deaths.append(bodyguard)
                        wolf_deaths.remove(target)
                    elif get_role(target, 'role') in ACTUAL_WOLVES:
                        killed_dict[bodyguard] += 1
                        killed_msg += "**{}**, a **bodyguard**, made the unfortunate mistake of guarding a wolf last night and is now dead.\n".format(get_name(bodyguard))
                        wolf_deaths.append(bodyguard)

            # Vengeful ghost stuff
            for ghost in [x for x in session[1] if get_role(x, 'role') == 'vengeful ghost' and not session[1][x][0] and [a for a in session[1][x][4] if a.startswith('vengeance:')]]:
                target = session[1][ghost][2]
                if target:
                    killed_dict[target] += 1
                    if 'retribution_totem2' in session[1][target][4]:
                        session[1][ghost][4].append('driven')
                        killed_msg += "**{0}**'s totem emitted a brilliant flash of light last night. It appears that **{1}**'s spirit was driven away by the flash.\n".format(get_name(target), get_name(ghost))

            # Totem stuff
            totem_holders = []
            protect_totemed = []
            death_totemed = []
            ill_wolves = []
            revengekill = ""

            for player in sort_players(session[1]):
                if len([x for x in session[1][player][4] if x in totems]) > 0:
                    totem_holders.append(player)
                prot_tots = 0
                death_tots = 0
                death_tots += session[1][player][4].count('death_totem')
                killed_dict[player] += death_tots
                if get_role(player, 'role') != 'harlot' or session[1][player][2] == player:
                    # fix for harlot with protect
                    prot_tots = session[1][player][4].count('protection_totem')
                    killed_dict[player] -= prot_tots
                if player in wolf_killed and killed_dict[player] < 1 and not (get_role(player, 'role') == 'harlot' and session[1][player][2] != player):
                    # if player was targeted by wolves but did not die and was not harlot avoiding attack
                    if player in guarded:
                        guardeded.append(player)
                    elif 'protection_totem' in session[1][player][4]:
                        protect_totemed.append(player)
                if 'death_totem' in session[1][player][4] and killed_dict[player] > 0 and death_tots - prot_tots - guarded.count(player) > 0:
                    death_totemed.append(player)

                if 'cursed_totem' in session[1][player][4]:
                    if 'cursed' not in get_role(player, 'templates'):
                        session[1][player][3].append('cursed')

                if player in wolf_deaths and killed_dict[player] > 0 and player not in death_totemed:
                    # player was targeted and killed by wolves
                    if session[1][player][4].count('lycanthropy_totem2') > 0:
                        killed_dict[player] = 0
                        wolf_turn.append(player)
                        await wolfchat("{} is now a **wolf**!".format(get_name(player)))
                        try:
                            member = client.get_server(WEREWOLF_SERVER).get_member(player)
                            if member:
                                await client.send_message(member, "You awake to a sharp pain, and realize you are being attacked by a werewolf! "
                                                                "Your totem emits a bright flash of light, and you find yourself turning into a werewolf!")
                        except discord.Forbidden:
                            pass
                    elif "pestilence_totem2" in session[1][player][4]:
                        for p in session[1]:
                            if roles[get_role(p, 'role')][0] == 'wolf' and get_role(p, 'role') in COMMANDS_FOR_ROLE['kill']:
                                ill_wolves.append(p)
                    if session[1][player][4].count('retribution_totem') > 0 and player not in wolf_turn:
                        revenge_targets = [x for x in session[1] if session[1][x][0] and get_role(x, 'role') in [
                            'wolf', 'doomsayer', 'werecrow', 'werekitten', 'wolf shaman', 'wolf mystic']]
                        if get_role(player, 'role') == 'harlot' and get_role(session[1][player][2], 'role') in [
                            'wolf', 'doomsayer', 'werecrow', 'wolf cub', 'werekitten', 'wolf shaman', 'wolf mystic']:
                            revenge_targets[:] = [session[1][player][2]]
                        else:
                            revenge_targets[:] = [x for x in revenge_targets if player in session[1][x][2].split(',')]
                        if revenge_targets:
                            revengekill = random.choice(revenge_targets)
                            killed_dict[revengekill] += 100
                            if killed_dict[revengekill] > 0:
                                killed_msg += "While being attacked last night, **{}**'s totem emitted a bright flash of light. The dead body of **{}**".format(
                                                get_name(player), get_name(revengekill))
                                killed_msg += ", a **{}**, was found at the scene.\n".format(get_role(revengekill, 'role'))


                other = session[1][player][4][:]
                for o in other[:]:
                    # hacky way to get specific mechanismes to last 2 nights
                    if o in ['death_totem', 'cursed_totem', 'retribution_totem', 'lycanthropy_totem2',
                            'deceit_totem2', 'angry', 'silence_totem2', 'luck_totem2', 'misdirection_totem2',
                            'pestilence_totem2', 'consecrated', 'illness', 'disobey']:
                        other.remove(o)
                    elif o.startswith('given:'):
                        other.remove(o)
                    elif o == 'protection_totem':
                        other.remove(o)
                        other.append('protection_totem2') # only protects from assassin
                    elif o in ['lycanthropy_totem', 'lycanthropy']:
                        other.remove(o)
                        other.append('lycanthropy_totem2')
                    elif o == 'deceit_totem':
                        other.remove(o)
                        other.append('deceit_totem2')
                    elif o in ['silence_totem', 'hex']:
                        other.remove(o)
                        other.append('silence_totem2')
                    elif o == 'misdirection_totem':
                        other.remove(o)
                        other.append('misdirection_totem2')
                    elif o == 'luck_totem':
                        other.remove(o)
                        other.append('luck_totem2')
                    elif o == 'pestilence_totem':
                        other.remove(o)
                        other.append('pestilence_totem2')
                    elif o == 'sick':
                        other.remove(o)
                        other.append('silence_totem2')
                        other.append('illness')
                session[1][player][4] = other
            for player in session[1]:
                session[1][player][4] = [x for x in session[1][player][4] if x != "ill_wolf"]
            for wolf in ill_wolves:
                session[1][wolf][4].append("ill_wolf")
            for player in sort_players(wolf_deaths):
                if ('gunner' in get_role(player, 'templates') or 'sharpshooter' in get_role(player, 'templates')) and \
                session[1][player][4].count('bullet') > 0 and killed_dict[player] > 0:
                    if random.random() < GUNNER_REVENGE_WOLF:
                        revenge_targets = [x for x in session[1] if session[1][x][0] and get_role(x, 'role') in [
                            'wolf', 'doomsayer', 'werecrow', 'werekitten', 'wolf shaman', 'wolf mystic']]
                        if get_role(player, 'role') == 'harlot' and get_role(session[1][player][2], 'role') in [
                            'wolf', 'doomsayer', 'werecrow', 'wolf cub', 'werekitten', 'wolf shaman', 'wolf mystic']:
                            revenge_targets[:] = [session[1][player][2]]
                        else:
                            revenge_targets[:] = [x for x in revenge_targets if session[1][x][2] in wolf_killed]
                        revenge_targets[:] = [x for x in revenge_targets if x not in gunner_revenge]
                        if revenge_targets:
                            target = random.choice(revenge_targets)
                            gunner_revenge.append(target)
                            session[1][player][4].remove('bullet')
                            killed_dict[target] += 100
                            if killed_dict[target] > 0:
                                killed_msg += "Fortunately **{}** had bullets and **{}**, a **{}**, was shot dead.\n".format(
                                    get_name(player), get_name(target), get_role(target, 'death'))
                    if session[1][player][4].count('bullet') > 0:
                        give_gun_targets = [x for x in session[1] if session[1][x][0] and get_role(x, 'role') in WOLFCHAT_ROLES]
                        if len(give_gun_targets) > 0:
                            give_gun = random.choice(give_gun_targets)
                            if not 'gunner' in get_role(give_gun, 'templates'):
                                session[1][give_gun][3].append('gunner')
                            session[1][give_gun][4].append('bullet')
                            member = client.get_server(WEREWOLF_SERVER).get_member(give_gun)
                            if member:
                                try:
                                    await client.send_message(member, "While searching through **{}**'s belongings, you discover a gun loaded with 1 "
                                    "silver bullet! You may only use it during the day. If you shoot at a wolf, you will intentionally miss. If you "
                                    "shoot a villager, it is likely that they will be injured.".format(get_name(player)))
                                except discord.Forbidden:
                                    pass

            for player in killed_dict:
                if killed_dict[player] > 0:
                    killed_players.append(player)

            killed_players = sort_players(killed_players)

            killed_temp = killed_players[:]

            log_msg.append("PROTECT_TOTEMED: " + ", ".join("{} ({})".format(get_name(x), x) for x in protect_totemed))
            if guarded:
                log_msg.append("GUARDED: " + ", ".join("{} ({})".format(get_name(x), x) for x in guarded))
            if guardeded:
                log_msg.append("ACTUALLY GUARDED: " + ", ".join("{} ({})".format(get_name(x), x) for x in guardeded))
            log_msg.append("DEATH_TOTEMED: " + ", ".join("{} ({})".format(get_name(x), x) for x in death_totemed))
            log_msg.append("PLAYERS TURNED WOLF: " + ", ".join("{} ({})".format(get_name(x), x) for x in wolf_turn))
            if revengekill:
                log_msg.append("RETRIBUTED: " + "{} ({})".format(get_name(revengekill), revengekill))
            if gunner_revenge:
                log_msg.append("GUNNER_REVENGE: " + ", ".join("{} ({})".format(get_name(x), x) for x in gunner_revenge))
            log_msg.append("DEATHS FROM WOLF: " + ", ".join("{} ({})".format(get_name(x), x) for x in wolf_deaths))
            log_msg.append("KILLED PLAYERS: " + ", ".join("{} ({})".format(get_name(x), x) for x in killed_players))

            await log(1, '\n'.join(log_msg))

            if guardeded:
                for gded in sort_players(guardeded):
                    killed_msg += "**{0}** was attacked last night, but luckily the guardian angel was on duty.\n".format(get_name(gded))

            if protect_totemed:
                for protected in sort_players(protect_totemed):
                    killed_msg += "**{0}** was attacked last night, but their totem emitted a brilliant flash of light, blinding their attacker and allowing them to escape.\n".format(
                                        get_name(protected))



            if death_totemed:
                for ded in sort_players(death_totemed):
                    killed_msg += "**{0}**'s totem emitted a brilliant flash of light last night. The dead body of **{0}**, a **{1}** was found at the scene.\n".format(
                                        get_name(ded), get_role(ded, 'death'))
                    killed_players.remove(ded)
            if revengekill and revengekill in killed_players:
                # retribution totem
                killed_players.remove(revengekill)

            for player in gunner_revenge:
                if player in killed_players:
                    killed_players.remove(player)

            if len(killed_players) == 0:
                if not (guardeded or protect_totemed or death_totemed or [x for x in wolf_killed if get_role(x, 'role') == 'harlot']):
                    killed_msg += random.choice(lang['nokills']) + '\n'
            elif len(killed_players) == 1:
                killed_msg += "The dead body of **{}**, a **{}**, was found. Those remaining mourn the tragedy.\n".format(get_name(killed_players[0]), get_role(killed_players[0], 'death'))
            else:
                killed_msg += "The dead bodies of **{}**, and **{}**, a **{}**, were found. Those remaining mourn the tragedy.\n".format(
                    '**, **'.join(get_name(x) + '**, a **' + get_role(x, 'death') for x in killed_players[:-1]), get_name(killed_players[-1]), get_role(killed_players[-1], 'death'))

            if session[0] and win_condition() == None:
                await send_lobby("Night lasted **{0:02d}:{1:02d}**. The villagers wake up and search the village.\n\n{2}".format(
                                                                                        night_elapsed.seconds // 60, night_elapsed.seconds % 60, killed_msg))

            killed_dict = {}
            for player in killed_temp:
                kill_team = "wolf" if player not in gunner_revenge + list(revengekill) + death_totemed and player in wolf_deaths else "village"
                killed_dict[player] = ("night kill", kill_team)
            if killed_dict:
                await player_deaths(killed_dict)

            if session[0] and win_condition() == None:
                totem_holders = sort_players(totem_holders)
                if len(totem_holders) == 0:
                    pass
                elif len(totem_holders) == 1:
                    await send_lobby(random.choice(lang['hastotem']).format(get_name(totem_holders[0])))
                elif len(totem_holders) == 2:
                    await send_lobby(random.choice(lang['hastotem2']).format(get_name(totem_holders[0]), get_name(totem_holders[1])))
                else:
                    await send_lobby(random.choice(lang['hastotems']).format('**, **'.join([get_name(x) for x in totem_holders[:-1]]), get_name(totem_holders[-1])))

            for player in wolf_turn:
                session[1][player][4].append('turned:{}'.format(get_role(player, 'role')))
                session[1][player][1] = 'wolf'

            for player in session[1]:
                session[1][player][2] = ''

            charmed = sort_players([x for x in alive_players if 'charmed' in session[1][x][4]])
            tocharm = sort_players([x for x in alive_players if 'tocharm' in session[1][x][4]])
            for player in tocharm:
                charmed_total = [x for x in charmed + tocharm if x != player]
                session[1][player][4].remove('tocharm')
                session[1][player][4].append('charmed')
                piper_message = "You hear the sweet tones of a flute coming from outside your window... You inexorably walk outside and find yourself in the village square. "
                if len(charmed_total) > 2:
                    piper_message += "You find out that **{0}**, and **{1}** are also charmed!".format('**, **'.join(map(get_name, charmed_total[:-1])), get_name(charmed_total[-1]))
                elif len(charmed_total) == 2:
                    piper_message += "You find out that **{0}** and **{1}** are also charmed!".format(get_name(charmed_total[0]), get_name(charmed_total[1]))
                elif len(charmed_total) == 1:
                    piper_message += "You find out that **{}** is also charmed!".format(get_name(charmed_total[0]))
                try:
                    member = client.get_server(WEREWOLF_SERVER).get_member(player)
                    if member and piper_message:
                        await client.send_message(member,piper_message)
                except discord.Forbidden:
                    pass
            for player in charmed:
                piper_message = ''
                if len(tocharm) > 2:
                    piper_message = "**{0}**, and **{1}** are now charmed!".format('**, **'.join(map(get_name, tocharm[:-1])), get_name(tocharm[-1]))
                elif len(tocharm) == 2:
                    piper_message = "**{0}** and **{1}** are now charmed!".format(get_name(tocharm[0]), get_name(tocharm[1]))
                elif len(tocharm) == 1:
                    piper_message = "**{}** is now charmed!".format(get_name(tocharm[0]))
                try:
                    member = client.get_server(WEREWOLF_SERVER).get_member(player)
                    if member and piper_message:
                        await client.send_message(member,piper_message)
                except discord.Forbidden:
                    pass

            if session[0] and win_condition() == None:
                await check_traitor()
        else: # DAY
            session[3][1] = datetime.now()
            if session[0] and win_condition() == None:
                for player in session[1]:
                    session[1][player][4] = [x for x in session[1][player][4] if x not in ["guarded", "protection_totem2"] and not x.startswith('bodyguard:')]
                await send_lobby("It is now **daytime**. Use `{}lynch <player>` to vote to lynch <player>.".format(BOT_PREFIX))

            for player in session[1]:
                if session[1][player][0] and 'blinding_totem' in session[1][player][4]:
                    if 'injured' not in session[1][player][4]:
                        session[1][player][4].append('injured')
                        for i in range(session[1][player][4].count('blinding_totem')):
                            session[1][player][4].remove('blinding_totem')
                        try:
                            member = client.get_server(WEREWOLF_SERVER).get_member(player)
                            if member:
                                await client.send_message(member, "Your totem emits a brilliant flash of light. "
                                                                "It seems like you cannot see anything! Perhaps "
                                                                "you should just rest during the day...")
                        except discord.Forbidden:
                            pass
                if 'illness' in session[1][player][4]:
                    session[1][player][4].append('injured')
                if get_role(player, 'role') == 'doomsayer':
                    session[1][player][4] = [x for x in session[1][player][4] if not x.startswith('doom:')]
            if session[6] != 'mudkip':
                lynched_player = None
                warn = False
                totem_dict = {} # For impatience and pacifism
                # DAY LOOP
                while win_condition() == None and session[2] and lynched_player == None and session[0]:
                    for player in [x for x in session[1]]:
                        totem_dict[player] = session[1][player][4].count('impatience_totem') - session[1][player][4].count('pacifism_totem')
                    vote_dict = get_votes(totem_dict)
                    if vote_dict['abstain'] >= len([x for x in session[1] if session[1][x][0] and 'injured' not in session[1][x][4]]) / 2:
                        lynched_player = 'abstain'
                    max_votes = max([vote_dict[x] for x in vote_dict])
                    max_voted = []
                    if max_votes >= len([x for x in session[1] if session[1][x][0] and 'injured' not in session[1][x][4]]) // 2 + 1:
                        for voted in vote_dict:
                            if vote_dict[voted] == max_votes:
                                max_voted.append(voted)
                        lynched_player = random.choice(max_voted)
                    if (datetime.now() - session[3][1]).total_seconds() > DAY_TIMEOUT:
                        session[3][0] = datetime.now() # hopefully a fix for time being weird
                        session[2] = False
                    if (datetime.now() - session[3][1]).total_seconds() > DAY_WARNING and warn == False:
                        warn = True
                        await send_lobby("**As the sun sinks inexorably toward the horizon, turning the lanky pine "
                                                "trees into fire-edged silhouettes, the villagers are reminded that very little time remains for them to reach a "
                                                "decision; if darkness falls before they have done so, the majority will win the vote. No one will be lynched if "
                                                "there are no votes or an even split.**")
                    await asyncio.sleep(0.1)
                if not lynched_player and win_condition() == None and session[0]:
                    vote_dict = get_votes(totem_dict)
                    max_votes = max([vote_dict[x] for x in vote_dict])
                    max_voted = []
                    for voted in vote_dict:
                        if vote_dict[voted] == max_votes and voted != 'abstain':
                            max_voted.append(voted)
                    if len(max_voted) == 1:
                        lynched_player = max_voted[0]
                if session[0]:
                    session[3][0] = datetime.now() # hopefully a fix for time being weird
                    day_elapsed = datetime.now() - session[3][1]
                    session[4][1] += day_elapsed
                lynched_msg = ""
                if lynched_player and win_condition() == None and session[0]:
                    if lynched_player == 'abstain':
                        for player in [x for x in totem_dict if session[1][x][0] and totem_dict[x] < 0]:
                            lynched_msg += "**{}** meekly votes to not lynch anyone today.\n".format(get_name(player))
                        lynched_msg += "The village has agreed to not lynch anyone today."
                        await send_lobby(lynched_msg)
                    else:
                        for player in [x for x in totem_dict if session[1][x][0] and totem_dict[x] > 0 and x != lynched_player]:
                            lynched_msg += "**{}** impatiently votes to lynch **{}**.\n".format(get_name(player), get_name(lynched_player))
                        lynched_msg += '\n'
                        if 'revealing_totem' in session[1][lynched_player][4]:
                            lynched_msg += 'As the villagers prepare to lynch **{0}**, their totem emits a brilliant flash of light! When the villagers are able to see again, '
                            lynched_msg += 'they discover that {0} has escaped! The left-behind totem seems to have taken on the shape of a **{1}**.'
                            if get_role(lynched_player, 'role') == 'amnesiac':
                                role = [x.split(':')[1].replace("_", " ") for x in session[1][lynched_player][4] if x.startswith("role:")].pop()
                                session[1][lynched_player][1] = role
                                session[1][lynched_player][4] = [x for x in session[1][lynched_player][4] if not x.startswith("role:")]
                                try:
                                    await client.send_message(client.get_server(WEREWOLF_SERVER).get_member(lynched_player), "Your totem clears your amnesia and you now fully remember who you are!")
                                    await _send_role_info(lynched_player)
                                    if role in WOLFCHAT_ROLES:
                                        await wolfchat("{0} is now a **{1}**!".format(get_name(lynched_player), role))
                                except discord.Exception:
                                    pass
                            lynched_msg = lynched_msg.format(get_name(lynched_player), get_role(lynched_player, 'role'))
                            await send_lobby(lynched_msg)
                        elif 'mayor' in get_role(lynched_player, 'templates') and 'unrevealed' in session[1][lynched_player][4]:
                            lynched_msg += "While being dragged to the gallows, **{}** reveals that they are the **mayor**. The village agrees to let them live for now.".format(get_name(lynched_player))
                            session[1][lynched_player][4].remove('unrevealed')
                            await send_lobby(lynched_msg)
                        else:
                            if 'luck_totem2' in session[1][lynched_player][4]:
                                lynched_player = misdirect(lynched_player)
                            lynched_msg += random.choice(lang['lynched']).format(get_name(lynched_player), get_role(lynched_player, 'death'))
                            await send_lobby(lynched_msg)
                            if get_role(lynched_player, 'role') == 'jester':
                                session[1][lynched_player][4].append('lynched')
                            lynchers_team = [get_role(x, 'actualteam') for x in session[1] if session[1][x][0] and session[1][x][2] == lynched_player]
                            await player_deaths({lynched_player : ('lynch', 'wolf' if lynchers_team.count('wolf') > lynchers_team.count('village') else 'village')})

                        if get_role(lynched_player, 'role') == 'fool' and 'revealing_totem' not in session[1][lynched_player][4]:
                            win_msg = "The fool has been lynched, causing them to win!\n\n" + end_game_stats()
                            lovers = []
                            for n in session[1][lynched_player][4]:
                                if n.startswith('lover:'):
                                    lover = n.split(':')[1]
                                    if session[1][lover][0]:
                                        lovers.append(lover)

                            await end_game(win_msg, [lynched_player] + (lovers if session[6] == "random" else []) + [x for x in session[1] if get_role(x, "role") == "jester" and "lynched" in session[1][x][4]])
                            return
                elif lynched_player == None and win_condition() == None and session[0]:
                    await send_lobby("Not enough votes were cast to lynch a player.")
            else:
                lynched_players = []
                warn = False
                totem_dict = {} # For impatience and pacifism
                # DAY LOOP
                while win_condition() == None and session[2] and not lynched_players and session[0]:
                    for player in [x for x in session[1]]:
                        totem_dict[player] = session[1][player][4].count('impatience_totem') - session[1][player][4].count('pacifism_totem')
                    vote_dict = get_votes(totem_dict)
                    max_votes = max([vote_dict[x] for x in vote_dict])
                    max_voted = []
                    if vote_dict['abstain'] >= len([x for x in session[1] if session[1][x][0] and 'injured' not in session[1][x][4]]) / 2:
                        lynched_players = 'abstain'
                    elif max_votes >= len([x for x in session[1] if session[1][x][0] and 'injured' not in session[1][x][4]]) // 2 + 1 or not [x for x in session[1] if not session[1][x][2] and session[1][x][0]]:
                        for voted in vote_dict:
                            if vote_dict[voted] == max_votes:
                                lynched_players.append(voted)
                    if (datetime.now() - session[3][1]).total_seconds() > DAY_TIMEOUT:
                        session[3][0] = datetime.now() # hopefully a fix for time being weird
                        session[2] = False
                    if (datetime.now() - session[3][1]).total_seconds() > DAY_WARNING and warn == False:
                        warn = True
                        await send_lobby("**As the sun sinks inexorably toward the horizon, turning the lanky pine "
                                                "trees into fire-edged silhouettes, the villagers are reminded that very little time remains for them to reach a "
                                                "decision; if darkness falls before they have done so, the majority will win the vote. No one will be lynched if "
                                                "there are no votes or an even split.**")
                    await asyncio.sleep(0.1)
                if not lynched_players and win_condition() == None and session[0]:
                    vote_dict = get_votes(totem_dict)
                    max_votes = max([vote_dict[x] for x in vote_dict])
                    max_voted = []
                    for voted in vote_dict:
                        if vote_dict[voted] == max_votes and voted != 'abstain':
                            max_voted.append(voted)
                    if max_voted:
                        lynched_players = max_voted
                if session[0]:
                    session[3][0] = datetime.now() # hopefully a fix for time being weird
                    day_elapsed = datetime.now() - session[3][1]
                    session[4][1] += day_elapsed
                lynched_msg = ""
                lynch_deaths = {}
                if lynched_players and win_condition() == None and session[0]:
                    if lynched_players == 'abstain':
                        for player in [x for x in totem_dict if session[1][x][0] and totem_dict[x] < 0]:
                            lynched_msg += "**{}** meekly votes to not lynch anyone today.\n".format(get_name(player))
                        lynched_msg += "The village has agreed to not lynch anyone today."
                        await send_lobby(lynched_msg)
                    else:
                        for lynched_player in lynched_players:
                            lynched_msg += "\n"
                            if 'revealing_totem' in session[1][lynched_player][4]:
                                lynched_msg += 'As the villagers prepare to lynch **{0}**, their totem emits a brilliant flash of light! When the villagers are able to see again, '
                                lynched_msg += 'they discover that {0} has escaped! The left-behind totem seems to have taken on the shape of a **{1}**.'
                                if get_role(lynched_player, 'role') == 'amnesiac':
                                    role = [x.split(':')[1].replace("_", " ") for x in session[1][lynched_player][4] if x.startswith("role:")].pop()
                                    session[1][lynched_player][1] = role
                                    session[1][lynched_player][4] = [x for x in session[1][lynched_player][4] if not x.startswith("role:")]
                                    try:
                                        await client.send_message(client.get_server(WEREWOLF_SERVER).get_member(lynched_player), "Your totem clears your amnesia and you now fully remember who you are!")
                                        await _send_role_info(lynched_player)
                                        if role in WOLFCHAT_ROLES:
                                            await wolfchat("{0} is now a **{1}**!".format(get_name(lynched_player), role))
                                    except discord.Exception:
                                        pass
                                lynched_msg = lynched_msg.format(get_name(lynched_player), get_role(lynched_player, 'role'))
                                await send_lobby(lynched_msg)
                            else:
                                if 'luck_totem2' in session[1][lynched_player][4]:
                                    lynched_player = misdirect(lynched_player)
                                lynched_msg += random.choice(lang['lynched']).format(get_name(lynched_player), get_role(lynched_player, 'death'))
                                if get_role(lynched_player, 'role') == 'jester':
                                    session[1][lynched_player][4].append('lynched')
                                lynchers_team = [get_role(x, 'actualteam') for x in session[1] if session[1][x][0] and session[1][x][2] == lynched_player]
                                lynch_deaths.update({lynched_player : ('lynch', 'wolf' if lynchers_team.count('wolf') > lynchers_team.count('village') else 'village')})

                            if get_role(lynched_player, 'role') == 'fool' and 'revealing_totem' not in session[1][lynched_player][4]:
                                win_msg = "The fool has been lynched, causing them to win!\n\n" + end_game_stats()
                                lovers = []
                                for n in session[1][lynched_player][4]:
                                    if n.startswith('lover:'):
                                        lover = n.split(':')[1]
                                        if session[1][lover][0]:
                                            lovers.append(lover)

                                await end_game(win_msg, [lynched_player] + (lovers if session[6] == "random" else []) + [x for x in session[1] if get_role(x, "role") == "jester" and "lynched" in session[1][x][4]])
                                return
                    await send_lobby(lynched_msg)
                    await player_deaths(lynch_deaths)
                elif lynched_players == None and win_condition() == None and session[0]:
                    await send_lobby("Not enough votes were cast to lynch a player.")
            # BETWEEN DAY AND NIGHT
            session[2] = False
            night += 1
            if session[0] and win_condition() == None:
                await send_lobby("Day lasted **{0:02d}:{1:02d}**. The villagers, exhausted from the day's events, go to bed.".format(
                                                                    day_elapsed.seconds // 60, day_elapsed.seconds % 60))
                for player in [x for x in session[1] if session[1][x][0] and 'entranced' in session[1][x][4]]:
                    if session[1][player][2] not in [session[1][x][2] for x in session[1] if session[1][x][0] and get_role(x, 'role') == 'succubus']:
                        session[1][player][4].append('disobey')
                for player in session[1]:
                    session[1][player][4][:] = [x for x in session[1][player][4] if x not in [
                        'revealing_totem', 'influence_totem', 'impatience_totem', 'pacifism_totem', 'injured', 'desperation_totem']]
                    session[1][player][2] = ''
                    session[1][player][4] = [x for x in session[1][player][4] if not x.startswith('vote:')]
                    if get_role(player, 'role') == 'amnesiac' and night == 3:
                        role = [x.split(':')[1].replace("_", " ") for x in session[1][player][4] if x.startswith("role:")].pop()
                        session[1][player][1] = role
                        session[1][player][4] = [x for x in session[1][player][4] if not x.startswith("role:")]
                        try:
                            await client.send_message(client.get_server(WEREWOLF_SERVER).get_member(player), "Your amnesia clears and you now remember that you are a{0} **{1}**!".format("n" if role.lower()[0] in ['a', 'e', 'i', 'o', 'u'] else "", role))
                            if role in WOLFCHAT_ROLES:
                                await wolfchat("{0} is now a **{1}**!".format(get_name(player), role))
                        except:
                            pass
            if session[0] and win_condition() == None:
                await check_traitor()
            
    # GAME END
    if session[0]:
        win_msg = win_condition()
        await end_game(win_msg[1], win_msg[2])

async def start_votes(player):
    start = datetime.now()
    while (datetime.now() - start).total_seconds() < 60:
        votes_needed = max(2, min(len(session[1]) // 4 + 1, 4))
        votes = len([x for x in session[1] if session[1][x][1] == 'start'])
        if votes >= votes_needed or session[0] or votes == 0:
            break
        await asyncio.sleep(0.1)
    else:
        for player in session[1]:
            session[1][player][1] = ''
        await send_lobby("Not enough votes to start, resetting start votes.")

async def rate_limit(message):
    if not (message.channel.is_private or message.content.startswith(BOT_PREFIX)) or message.author.id in ADMINS or message.author.id == OWNER_ID:
        return False
    global ratelimit_dict
    global IGNORE_LIST
    if message.author.id not in ratelimit_dict:
        ratelimit_dict[message.author.id] = 1
    else:
        ratelimit_dict[message.author.id] += 1
    if ratelimit_dict[message.author.id] > IGNORE_THRESHOLD:
        if not message.author.id in IGNORE_LIST:
            IGNORE_LIST.append(message.author.id)
            await log(2, message.author.name + " (" + message.author.id + ") was added to the ignore list for rate limiting.")
        try:
            await reply(message, "You've used {0} commands in the last {1} seconds; I will ignore you from now on.".format(IGNORE_THRESHOLD, TOKEN_RESET))
        except discord.Forbidden:
            await send_lobby(message.author.mention +
                                      " used {0} commands in the last {1} seconds and will be ignored from now on.".format(IGNORE_THRESHOLD, TOKEN_RESET))
        finally:
            return True
    if message.author.id in IGNORE_LIST or ratelimit_dict[message.author.id] > TOKENS_GIVEN:
        if ratelimit_dict[message.author.id] > TOKENS_GIVEN:
            await log(2, "Ignoring message from " + message.author.name + " (" + message.author.id + "): `" + message.content + "` since no tokens remaining")
        return True
    return False

async def do_rate_limit_loop():
    await client.wait_until_ready()
    global ratelimit_dict
    while not client.is_closed:
        for user in ratelimit_dict:
            ratelimit_dict[user] = 0
        await asyncio.sleep(TOKEN_RESET)

async def game_start_timeout_loop():
    session[5] = datetime.now()
    while not session[0] and len(session[1]) > 0 and datetime.now() - session[5] < timedelta(seconds=GAME_START_TIMEOUT):
        await asyncio.sleep(0.1)
    if not session[0] and len(session[1]) > 0:
        session[0] = True
        await client.change_presence(game=client.get_server(WEREWOLF_SERVER).me.game, status=discord.Status.online)
        await send_lobby("{0}, the game has taken too long to start and has been cancelled. "
                          "If you are still here and would like to start a new game, please do `!join` again.".format(PLAYERS_ROLE.mention))
        perms = client.get_channel(GAME_CHANNEL).overwrites_for(client.get_server(WEREWOLF_SERVER).default_role)
        perms.send_messages = True
        await client.edit_channel_permissions(client.get_channel(GAME_CHANNEL), client.get_server(WEREWOLF_SERVER).default_role, perms)
        player_dict = {}
        for player in list(session[1]):
            player_dict[player] = ('game cancel', "bot")
        await player_deaths(player_dict)
        session[0] = False
        session[3] = [datetime.now(), datetime.now()]
        session[4] = [timedelta(0), timedelta(0)]
        session[6] = ''
        session[7] = {}

async def wait_timer_loop():
    global wait_bucket
    timer = datetime.now()
    while not session[0] and len(session[1]) > 0:
        if datetime.now() - timer > timedelta(seconds=WAIT_BUCKET_DELAY):
            timer = datetime.now()
            wait_bucket = min(wait_bucket + 1, WAIT_BUCKET_MAX)
        await asyncio.sleep(0.5)

async def backup_settings_loop():
    while not client.is_closed:
        print("BACKING UP SETTINGS")
        with open(NOTIFY_FILE, 'w') as notify_file:
            notify_file.write(','.join([x for x in notify_me if x != '']))
        with open(STASIS_FILE, 'w') as stasis_file:
            json.dump(stasis, stasis_file)
        await asyncio.sleep(BACKUP_INTERVAL)

############## POST-DECLARATION STUFF ###############
COMMANDS_FOR_ROLE = {'see' : ['seer', 'oracle', 'augur', 'doomsayer'],
                     'kill' : ['wolf', 'werecrow', 'werekitten', 'wolf shaman', 'hunter', 'vengeful ghost', 'doomsayer', 'wolf mystic'],
                     'give' : ['shaman', 'wolf shaman'],
                     'visit' : ['harlot', 'succubus'],
                     'shoot' : ['gunner', 'sharpshooter'],
                     'observe' : ['werecrow', 'sorcerer'],
                     'pass' : ['harlot', 'hunter', 'guardian angel', 'succubus', 'warlock', 'bodyguard', 'piper'],
                     'id' : ['detective'],
                     'choose' : ['matchmaker'],
                     'guard' : ['guardian angel', 'bodyguard'],
                     'target' : ['assassin'],
                     'bless' : ['priest'],
                     'consecrate' : ['priest'],
                     'entrance' : ['succubus'],
                     'hex' : ['hag'],
                     'curse' : ['warlock'],
                     'charm' : ['piper']}
GAMEPLAY_COMMANDS = ['join', 'j', 'start', 'vote', 'lynch', 'v', 'abstain', 'abs', 'nl', 'stats', 'leave', 'q', 'role', 'roles']
GAMEPLAY_COMMANDS += list(COMMANDS_FOR_ROLE)

# {role name : [team, plural, description]}
roles = {'wolf' : ['wolf', 'wolves', "Your job is to kill all of the villagers. Type `kill <player>` in private message to kill them."],
         'werecrow' : ['wolf', 'werecrows', "You are part of the wolfteam. Use `observe <player>` during the night to see if they were in bed or not. "
                                            "You may also use `kill <player>` to kill them."],
         'wolf cub' : ['wolf', 'wolf cubs', "You are part of the wolfteam. While you cannot kill anyone, the other wolves will "
                                            "become enraged if you die and will get two kills the following night."],
         'werekitten' : ['wolf', 'werekittens', "You are like a normal wolf, except due to your cuteness, you are seen as a villager "
                                                "and gunners will always miss when they shoot you. Use `kill <player>` in private message "
                                                "to vote to kill <player>."],
         'wolf shaman' : ['wolf', 'wolf shamans', "You are part of the wolfteam. You may use `kill <player>` to kill a villager. You can also select "
                                                  "a player to receive a totem each night by using `give <player>.` You may give yourself a totem, "
                                                  "but you may not give the same player a totem two nights in a row. If you do not give the totem "
                                                  "to anyone, it will be given to a random player."],
         'traitor' : ['wolf', 'traitors', "You are exactly like a villager, but you are part of the wolf team. Only the detective can reveal your true "
                                          "identity. Once all other wolves die, you will turn into a wolf."],
         'sorcerer' : ['wolf', 'sorcerers', "You may use `observe <player>` in pm during the night to observe someone and determine if they "
                                            "are the seer, oracle, or augur. You are seen as a villager; only detectives can reveal your true identity."],
         'cultist' : ['wolf', 'cultists', "Your job is to help the wolves kill all of the villagers. But you do not know who the wolves are."],
         'seer' : ['village', 'seers', "Your job is to detect the wolves; you may have a vision once per night. Type `see <player>` in private message to see their role."],
         'oracle' : ['village', 'oracles', "Your job is to detect the wolves; you may have a vision once per night. Type `see <player>` in private message to see whether or not they are a wolf."],
         'shaman' : ['village', 'shamans', "You select a player to receive a totem each night by using `give <player>`. You may give a totem to yourself, but you may not give the same"
                                           " person a totem two nights in a row. If you do not give the totem to anyone, it will be given to a random player. "
                                           "To see your current totem, use the command `myrole`."],
         'harlot' : ['village', 'harlots', "You may spend the night with one player each night by using `visit <player>`. If you visit a victim of a wolf, or visit a wolf, "
                                           "you will die. You may visit yourself to stay home."],
         'hunter' : ['village', 'hunters', "Your job is to help kill the wolves. Once per game, you may kill another player using `kill <player>`. "
                                           "If you do not wish to kill anyone tonight, use `pass` instead."],
         'augur' : ['village', 'augurs', "Your job is to detect the wolves; you may have a vision once per night. Type `see <player>` in private message to see the aura they exude."
                                         " Blue is villager, grey is neutral, and red is wolf."],
         'detective' : ['village', 'detectives', "Your job is to determine all of the wolves and traitors. During the day, you may use `id <player>` in private message "
                                                 "to determine their true identity. However you risk a {}% chance of revealing your role to the wolves every time you use your ability.".format(int(DETECTIVE_REVEAL_CHANCE * 100))],
         'villager' : ['village', 'villagers', "Your job is to lynch all of the wolves."],
         'crazed shaman' : ['neutral', 'crazed shamans', "You select a player to receive a random totem each night by using `give <player>`. You may give a totem to yourself, "
                                                         "but you may not give the same person a totem two nights in a row. If you do not give the totem to anyone, "
                                                         "it will be given to a random player. You win if you are alive by the end of the game."],
         'fool' : ['neutral', 'fools', "You become the sole winner if you are lynched during the day. You cannot win otherwise."],
         'cursed villager' : ['template', 'cursed villagers', "This template is hidden and is seen as a wolf by the seer. Roles normally seen as wolf, the seer, and the fool cannot be cursed."],
         'gunner' : ['template', 'gunners', "This template gives the player a gun. Type `{0}shoot <player>` in channel during the day to shoot <player>. "
                                            "If you are a villager and shoot a wolf, they will die. Otherwise, there is a chance of killing them, injuring "
                                            "them, or the gun exploding. If you are a wolf and shoot at a wolf, you will intentionally miss."],
         'assassin' : ['template', 'assassins', "Choose a target with `target <player>`. If you die you will take out your target with you. If your target dies you may choose another one. "
                                                "Wolves and info-obtaining roles (such as seer and oracle) may not be assassin."],
         'matchmaker' : ['village', 'matchmakers', "You can select two players to be lovers with `choose <player1> and <player2>`."
                                                   " If one lover dies, the other will as well. You may select yourself as one of the lovers."
                                                   " You may only select lovers during the first night."
                                                   " If you do not select lovers, they will be randomly selected and you will not be told who they are (unless you are one of them)."],
         'guardian angel' : ['village', 'guardian angels', "Your job is to protect the villagers. Use `guard <player>` in private message during night to protect "
                                                           "them from dying. You may protect yourself, however you may not guard the same player two nights in a row."],
         'jester' : ['neutral', 'jesters', "You will win alongside the normal winners if you are lynched during the day. You cannot otherwise win this game."],
         'minion' : ['wolf', 'minions', "It is your job to help the wolves kill all of the villagers. You are told who your leaders are on the first night, otherwise, you are a cultist."],
         'amnesiac' : ['neutral', 'amnesiacs', "You have forgotten your original role and need to wait a few nights to let the fog clear. You will win with the default role, until you remember your original role."],
         'blessed villager' : ['template', 'blessed villagers', "You feel incredibly safe. You won't be able to die as a normal villager, unless two players target you, or you are lynched at day."],
         'vengeful ghost' : ['neutral', 'vengeful ghosts', "Your soul will never be at rest. If you are killed during the game, you will swear eternal revenge upon team that killed you."
                                                           " Use `kill <player>` once per night after dying to kill an alive player. You only win if the team you swore revenge upon loses."],
         'priest' : ['village', 'priests', "Once per game during the day, you may bless someone with `bless <player>` to prevent them from being killed. Furthermore, you may consecrate the dead during the day with `consecrate <player>` to settle down restless spirits and prevent the corpse from rising as undead; doing so removes your ability to participate in the vote that day."],
         'doomsayer' : ['wolf', 'doomsayers', "You can see how bad luck will befall someone at night by using `see <player>` on them. You may also use `kill <player>` to kill a villager."],
         'succubus' : ['neutral', 'succubi', "You may entrance someone and make them follow you by visiting them at night. If all alive players are entranced, you win. Use `visit <player>` to visit a player or `pass` to stay home. If you visit the victim of the wolves, you will die."],
         'mayor' : ['template', 'mayors', "If the mayor would by lynched during the day, they reveal that they are the mayor and nobody is lynched that day. A mayor that has previously been revealed will be lynched as normal."],
         'monster' : ['neutral', 'monsters', "You cannot be killed by the wolves. If you survive until the end of the game, you win instead of the normal winners."],
         'sharpshooter' : ['template', 'sharpshooters', "This template is like the gunner template but due to it's holder's skills, they may never miss their target."],
         'village drunk': ['village', 'village drunks', "You have been drinking too much!"],
         'hag' : ['wolf', 'hags', "You can hex someone to prevent them from using any special powers they may have during the next day and night. Use `hex <player>` to hex them. Only detectives can reveal your true identity, seers will see you as a regular villager."],
         'bodyguard' : ['village', 'bodyguards', "It is your job to protect the villagers. If you guard a victim, you will sacrifice yourself to save them. Use `guard <player>` to guard a player or `pass` to not guard anyone tonight."],
         'piper' : ['neutral', 'pipers', "You can select up to two players to charm each night. The charmed players will know each other, but not who charmed them. You win when all other players are charmed. Use `charm <player1> and <player2>` to select the players to charm, or `charm <player>` to charm just one player."],
         'warlock' : ['wolf', 'warlocks', "Each night you can curse someone with `curse <player>` to turn them into a cursed villager, so the seer sees them as wolf. Act quickly, as your curse applies as soon as you cast it! Only detectives can reveal your true identity, seers will see you as a regular villager."],
         'mystic' : ['village', 'mystics', "Each night you will sense the number of evil villagers there are."],
         'wolf mystic' : ['wolf', 'wolf mystics', "Each night you will sense the number of good villagers with a power there are. You can also use `kill <player>` to kill a villager."]}

gamemodes = {
    'default' : {
        'description' : "The default gamemode.",
        'min_players' : 4,
        'max_players' : 24,
        'roles' : {
            #4, 5, 6, 7, 8, 9, 10,11,12,13,14,15,16,17,18,19,20,21,22,23,24
            'wolf' :
            [1, 1, 1, 1, 1, 1,  1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3],
            'werecrow' :
            [0, 0, 0, 0, 0, 0,  0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'wolf cub' :
            [0, 0, 0, 0, 0, 0,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'traitor' :
            [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1 ,1 ,1, 1],
            'sorcerer' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
            'cultist' :
            [0, 0, 0, 1, 0, 0,  0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            'seer' :
            [1, 1, 1, 1, 1, 1,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'shaman' :
            [0, 0, 0, 1, 1, 1,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'harlot' :
            [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'hunter' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'augur' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
            'detective' :
            [0, 0, 0, 0, 0, 0,  0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'matchmaker' :
            [0, 0, 0, 0, 0, 0,  0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'guardian angel' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1],
            'villager' :
            [2, 3, 4, 3, 3, 3,  3, 3, 2, 2, 3, 3, 2, 3, 3, 4, 3, 3, 4, 4, 4],
            'crazed shaman' :
            [0, 0, 0, 0, 0, 1,  1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2],
            'amnesiac' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
            'cursed villager' :
            [0, 0, 1, 1, 1, 1,  1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3],
            'gunner' :
            [0, 0, 0, 0, 0, 0,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2],
            'assassin' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'mayor' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
            'monster' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'hag' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]}
        },
#    'test' : {
#        'description' : "Gamemode for testing stuff.",
#        'min_players' : 5,
#        'max_players' : 23,
#        'roles' : {
#            #4, 5, 6, 7, 8, 9, 10,11,12,13,14,15,16,17,18,19,20,21,22,23,24
#            'wolf' :
#            [1, 1, 1, 1, 1, 1,  1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3],
#            'werecrow' :
#            [0, 0, 0, 0, 0, 0,  0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
#            'wolf cub' :
#            [0, 0, 0, 0, 0, 0,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
#            'traitor' :
#            [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1 ,1 ,1, 1],
#            'sorcerer' :
#            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
#            'cultist' :
#            [0, 0, 0, 1, 0, 0,  0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'seer' :
#            [1, 1, 1, 1, 1, 1,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
#            'shaman' :
#            [0, 0, 0, 1, 1, 1,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
#            'harlot' :
#            [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
#            'hunter' :
#            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
#            'augur' :
#            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
#            'detective' :
#            [0, 0, 0, 0, 0, 0,  0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
#            'matchmaker' :
#            [0, 0, 0, 0, 0, 0,  0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
#            'guardian angel' :
#            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1],
#            'villager' :
#            [2, 3, 4, 3, 3, 3,  3, 3, 2, 2, 3, 3, 2, 3, 3, 4, 3, 3, 4, 4, 4],
#            'crazed shaman' :
#            [0, 0, 0, 0, 0, 1,  1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2],
#            'amnesiac' :
#            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
#            'cursed villager' :
#            [0, 0, 1, 1, 1, 1,  1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3],
#            'gunner' :
#            [0, 0, 0, 0, 0, 0,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2],
#            'assassin' :
#            [0, 0, 0, 0, 0, 0,  0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
#            'mayor' :
#            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
#            'monster' :
#            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1],
#            'hag' :
#            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]}
#    },
    'foolish' : {
        'description' : "Watch out, because the fool is always there to steal the win.",
        'min_players' : 8,
        'max_players' : 24,
        'roles' : {
            #4, 5, 6, 7, 8, 9, 10,11,12,13,14,15,16,17,18,19,20,21,22,23,24
            'wolf' :
            [0, 0, 0, 0, 1, 1,  2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 4],
            'wolf cub' :
            [0, 0, 0, 0, 0, 0,  0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'traitor' :
            [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2],
            'sorcerer' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'oracle' :
            [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'shaman' :
            [0, 0, 0, 0, 0, 0,  0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'harlot' :
            [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2],
            'hunter' :
            [0, 0, 0, 0, 0, 1,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'augur' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'bodyguard' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
            'villager' :
            [0, 0, 0, 0, 3, 3,  3, 2, 2, 3, 4, 3, 4, 3, 4, 5, 5, 5, 6, 7, 7],
            'crazed shaman' :
            [0, 0, 0, 0, 0, 0,  0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'fool' :
            [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'cursed villager' :
            [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'gunner' :
            [0, 0, 0, 0, 0, 0,  0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2]}
    },
    'chaos' : {
        'description' : "Chaotic and unpredictable. Any role, including wolves, can be a gunner.",
        'min_players' : 4,
        'max_players' : 16,
        'roles' : {
            #4, 5, 6, 7, 8, 9, 10,11,12,13,14,15,16
            'wolf' :
            [1, 1, 1, 1, 1, 1,  2, 2, 2, 3, 3, 3, 3],
            'traitor' :
            [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 2, 2],
            'cultist' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0],
            'seer' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0],
            'shaman' :
            [3, 4, 4, 4, 3, 4,  3, 2, 3, 1, 2, 1, 1],
            'harlot' :
            [0, 0, 0, 1, 1, 1,  2, 2, 2, 3, 3, 3, 4],
            'crazed shaman' :
            [0, 0, 0, 0, 1, 1,  1, 2, 2, 3, 3, 4, 4],
            'fool' :
            [0, 0, 1, 1, 1, 1,  1, 2, 2, 2, 2, 2, 2],
            'cursed villager' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0],
            'gunner' :
            [1, 1, 1, 1, 1, 2,  2, 2, 2, 3, 3, 3, 3]}
    },
    'orgy' : {
        'description' : "Be careful who you visit! ( ͡° ͜ʖ ͡°)",
        'min_players' : 4,
        'max_players' : 16,
        'roles' : {
            #4, 5, 6, 7, 8, 9, 10,11,12,13,14,15,16
            'wolf' :
            [1, 1, 1, 1, 1, 1,  2, 2, 2, 3, 3, 3, 3],
            'traitor' :
            [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 2, 2],
            'harlot' :
            [3, 4, 4, 4, 3, 4,  3, 2, 3, 1, 2, 1, 1],
            'matchmaker' :
            [0, 0, 0, 1, 1, 1,  2, 2, 2, 3, 3, 3, 4],
            'crazed shaman' :
            [0, 0, 0, 0, 1, 1,  1, 2, 2, 3, 3, 4, 4],
            'fool' :
            [0, 0, 1, 1, 1, 1,  1, 2, 2, 2, 2, 2, 2],
            'cursed villager' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0]}
    },
    'crazy' : {
        'description' : "Random totems galore.",
        'min_players' : 4,
        'max_players' : 16,
        'roles' : {
            #4, 5, 6, 7, 8, 9, 10,11,12,13,14,15,16
            'wolf' :
            [1, 1, 1, 1, 1, 1,  1, 1, 2, 2, 1, 1, 2],
            'traitor' :
            [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 2, 2, 2],
            'crazed shaman' :
            [3, 4, 5, 6, 5, 6,  7, 7, 7, 8, 8, 9, 9],
            'fool' :
            [0, 0, 0, 0, 1, 1,  1, 2, 2, 2, 3, 3, 3],
            'cursed villager' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0]}
    },
    'belunga' : {
        'description' : "Originally an april fool's joke, this gamemode is interesting, to say the least.",
        'min_players' : 4,
        'max_players' : 20,
        'roles' : {}
        },
    'valentines' : {
        'description' : "Love and death are in the air, as the default role is matchmaker.",
        # [8] wolf, wolf(2), matchmaker, matchmaker(2), matchmaker(3), matchmaker(4), matchmaker(5), matchmaker(6)
        # [9] matchmaker(7) [10] matchmaker(8) [11] matchmaker(9) [12] monster [13] wolf(3) [14] matchmaker(10) [15] matchmaker(11)
        # [16] matchmaker(12) [17] wolf(4) [18] mad scientist [19] matchmaker(13) [20] matchmaker(14) [21] wolf(5) [22] matchmaker(15) [23] matchmaker(16) [24] wolf(6)
        'min_players' : 8,
        'max_players' : 20,
        'roles' : {
            #4, 5, 6, 7, 8, 9, 10,11,12,13,14,15,16,17,18,19,20
            'wolf' :
            [0, 0, 0, 0, 2, 2,  2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4],
            'matchmaker' :
            [0, 0, 0, 0, 6, 7,  8, 9, 9, 9,10,11,12,12,12,13,14],
            'crazed shaman' :
            [0, 0, 0, 0, 0, 0,  0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1],
            'monster' :
            [0, 0, 0, 0, 0, 0,  0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1]}
    },
    'evilvillage' : {
        'description' : 'Majority of the village is wolf aligned, safes must secretly try to kill the wolves.',
        'min_players' : 6,
        'max_players' : 15,
        'roles' : {
            #4, 5, 6, 7, 8, 9, 10,11,12,13,14,15
            'wolf' :
            [0, 0, 1, 1, 1, 1,  1, 1, 1, 1, 1, 2],
            'cultist' :
            [0, 0, 4, 5, 5, 6,  4, 5, 5, 6, 7, 6],
            'seer' :
            [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 1],
            'shaman' :
            [0, 0, 0, 0, 0, 0,  0, 0, 1, 1, 1, 1],
            'hunter' :
            [0, 0, 1, 1, 1, 1,  1, 1, 1, 1, 1, 2],
            'guardian angel' :
            [0, 0, 0, 0, 0, 0,  1, 1, 1, 1, 1, 1],
            'fool' :
            [0, 0, 0, 0, 0, 0,  1, 1, 1, 1, 1, 1],
            'minion' :
            [0, 0, 0, 0, 0, 0,  1, 1, 1, 1, 1, 1],
            'mayor' :
            [0, 0, 0, 0, 0, 0,  0, 0, 1, 1, 1, 1]}
    },
    'drunkfire' : {
        'description' : "Most players get a gun, quickly shoot all the wolves!",
        'min_players' : 8,
        'max_players' : 17,
        'roles' : {
            #4, 5, 6, 7, 8, 9, 10,11,12,13,14,15
            'wolf' :
            [0, 0, 0, 0, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3],
            'traitor' :
            [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2],
            'hag' :
            [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1],
            'seer' :
            [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'village drunk' :
            [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5],
            'villager' :
            [0, 0, 0, 0, 4, 5, 4, 5, 3, 4, 3, 4, 3, 4],
            'crazed shaman' :
            [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1],
            'cursed villager' :
            [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'gunner' :
            [0, 0, 0, 0, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9],
            'assassin' :
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1]
        }
    },
    'random' : {
        'description' : "Other than ensuring the game doesn't end immediately, no one knows what roles will appear.",
        'min_players' : 8,
        'max_players' : 20,
        'roles' : {
        }
    },
    'mudkip' : {
        'description' : "Why are all the professors named after trees?",
        'min_players' : 4,
        'max_players' : 15,
        'roles' : {
            'wolf' :
            [1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2],
            'wolf shaman' :
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1],
            'doomsayer' :
            [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1],
            'minion' :
            [0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
            'shaman' :
            [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1],
            'detective' :
            [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'guardian angel' :
            [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'priest' :
            [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1],
            'villager' :
            [2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3],
            'jester' :
            [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'amnesiac' :
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
            'vengeful ghost' :
            [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1],
            'succubus' :
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
            'assassin' :
            [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1]
        }
    },
    'charming' : {
        'description' : "Charmed players must band together to find the piper in this game mode.",
        'min_players' : 6,
        'max_players' : 24,
         'roles' : {
            'seer' :
            [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'harlot' :
            [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'shaman' :
            [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2],
            'detective' :
            [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'bodyguard' :
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2],
            'wolf' :
            [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3],
            'traitor' :
            [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'werekitten' :
            [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'warlock' :
            [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'sorcerer' :
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1],
            'piper' :
            [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'vengeful ghost' :
            [0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'cursed villager' :
            [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'gunner' :
            [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2],
            'mayor' :
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'sharpshooter' :
            [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2],
            'assassin' :
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            'villager' :
            [0, 0, 3, 4, 3, 4, 3, 3, 2, 3, 3, 4, 4, 5, 5, 5, 6, 7, 6, 7, 8]
         }
    }
#    'template' : {
#        'description' : "This is a template you can use for making your own gamemodes.",
#        'min_players' : 0,
#        'max_players' : 0,
#        'roles' : {
#            #4, 5, 6, 7, 8, 9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24
#            'wolf' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'werecrow' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'wolf cub' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'werekitten' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'traitor' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'sorcerer' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'cultist' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'seer' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'oracle' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'shaman' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'harlot' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'hunter' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'augur' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'detective' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'matchmaker' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'guardian angel' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'villager' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'jester' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'fool' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'crazed shaman' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'amnesiac' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'cursed villager' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'gunner' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'assassin' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'minion' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'monster' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'mayor' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
#            'hag' :
#            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
#        }
#    }
}
gamemodes['belunga']['roles'] = dict(gamemodes['default']['roles'])

VILLAGE_ROLES_ORDERED = ['seer', 'oracle', 'shaman', 'harlot', 'hunter', 'augur', 'detective', 'matchmaker', 'guardian angel', 'bodyguard', 'priest', 'village drunk', 'mystic', 'villager']
WOLF_ROLES_ORDERED = ['wolf', 'werecrow', 'doomsayer', 'wolf cub', 'werekitten', 'wolf shaman', 'wolf mystic', 'traitor', 'hag', 'sorcerer', 'warlock', 'minion', 'cultist']
NEUTRAL_ROLES_ORDERED = ['jester', 'crazed shaman', 'monster', 'piper', 'amnesiac', 'fool', 'vengeful ghost', 'succubus']
TEMPLATES_ORDERED = ['cursed villager', 'blessed villager', 'gunner', 'sharpshooter', 'mayor', 'assassin']
totems = {'death_totem' : 'The player who is given this totem will die tonight.',
          'protection_totem': 'The player who is given this totem is protected from dying tonight.',
          'revealing_totem': 'If the player who is given this totem is lynched, their role is revealed to everyone instead of them dying.',
          'influence_totem': 'Votes by the player who is given this totem count twice.',
          'impatience_totem' : 'The player who is given this totem is counted as voting for everyone except themselves, even if they do not lynch.',
          'pacifism_totem' : 'The player who is given this totem is always counted as abstaining, regardless of their vote.',
          'cursed_totem' : 'The player who is given this totem will gain the cursed template if they do not have it.',
          'lycanthropy_totem' : 'If the player who is given this totem is targeted by wolves the following night, they turn into a wolf instead of dying.',
          'retribution_totem' : 'If the player who is given this totem is targeted by wolves during the night, they kill a random wolf in turn.',
          'blinding_totem' : 'The player who is given this totem will be injured and unable to vote the following day.',
          'deceit_totem' : 'If the player who is given this totem is seen by the seer/oracle the following night, the '
                           'vision will return the opposite of what they are. If a seer/oracle is given this totem, '
                           'all of their visions will return the opposite.',
          'misdirection_totem' : 'If the player who is given this totem attempts to use a power the following day or night'
                                 ', they will target a player adjacent to their intended target instead of the player they targeted.',
          'luck_totem' : 'If the player who is given this totem is targeted tomorrow night, one of the players adjacent '
                         'to them will be targeted instead.',
          'silence_totem' : 'The player who is given this totem will be unable to use any special powers during the'
                            ' day tomorrow and the night after.',
          'pestilence_totem': 'If the player who is given this totem is killed by wolves tomorrow night,'
                              ' the wolves will not be able to kill the night after.',
          'desperation_totem': 'If the player who is given this totem is lynched, the last player to vote '
                               'them will also die.'}
SHAMAN_TOTEMS = ['death_totem', 'protection_totem', 'revealing_totem', 'influence_totem', 'impatience_totem', 'pacifism_totem', 'silence_totem', 'desperation_totem']
WOLF_SHAMAN_TOTEMS = ['protection_totem', 'impatience_totem', 'pacifism_totem', 'retribution_totem', 'deceit_totem', 'lycanthropy_totem', 'luck_totem', 'misdirection_totem', 'silence_totem']
ROLES_SEEN_VILLAGER = ['werekitten', 'traitor', 'sorcerer', 'warlock', 'minion', 'cultist', 'villager', 'jester', 'fool', 'amnesiac', 'vengeful ghost', 'hag', 'piper']
ROLES_SEEN_WOLF = ['wolf', 'werecrow', 'doomsayer', 'wolf cub', 'wolf shaman', 'wolf mystic', 'cursed', 'monster', 'succubus']
ACTUAL_WOLVES = ['wolf', 'werecrow', 'doomsayer', 'wolf cub', 'werekitten', 'wolf shaman', 'wolf mystic']
WOLFCHAT_ROLES = ['wolf', 'werecrow', 'doomsayer', 'wolf cub', 'werekitten', 'wolf shaman', 'wolf mystic', 'traitor', 'sorcerer', 'warlock', 'hag']

########### END POST-DECLARATION STUFF #############
client.loop.create_task(do_rate_limit_loop())
client.loop.create_task(backup_settings_loop())
try:
    client.loop.run_until_complete(client.start(TOKEN))
finally:
    try:
        try:
            client.loop.run_until_complete(client.logout())
        except:
            pass
        pending = asyncio.Task.all_tasks()
        gathered = asyncio.gather(*pending)

        try:
            gathered.cancel()
            client.loop.run_until_complete(gathered)
            gathered.exception()
        except:
            pass
    except:
        print("Error in cleanup:\n" + traceback.format_exc())
    client.loop.close()
