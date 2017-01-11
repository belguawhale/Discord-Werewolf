import discord
import asyncio
import os
import random
import traceback
import sys
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from config import *
from settings import *

################## START INIT #####################
client = discord.Client()
session = [False, {}, False, [0, 0], [timedelta(0), timedelta(0)], 0, '']
PLAYERS_ROLE = None
ADMINS_ROLE = None
WEREWOLF_NOTIFY_ROLE = None
ratelimit_dict = {}
pingif_dict = {}
notify_me = []
with open(NOTIFY_FILE, 'a+') as notify_file:
    notify_file.seek(0)
    notify_me = notify_file.read().split(',')
random.seed(datetime.now())
################### END INIT ######################

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')
    await log(0, 'on_ready triggered!')
    # [playing : True | False, players : {player id : [alive, role, action, template]}, day?, [datetime night, datetime day], [elapsed night, elapsed day], first join time]
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
        await log(2, "Could not find players role " + PLAYERS_ROLE_NAME)
    if ADMINS_ROLE:
        await log(0, "Admins role id: " + ADMINS_ROLE.id)
    else:
        await log(2, "Could not find admins role " + ADMINS_ROLE_NAME)
    if WEREWOLF_NOTIFY_ROLE:
        await log(0, "Werewolf Notify role id: " + WEREWOLF_NOTIFY_ROLE.id)
    else:
        await log(1, "Could not find Werewolf Notify role " + WEREWOLF_NOTIFY_ROLE_NAME)

@client.event
async def on_message(message):
    if message.author.id in [client.user.id] + IGNORE_LIST or not client.get_server(WEREWOLF_SERVER).get_member(message.author.id):
        if not (message.author.id in ADMINS or message.author.id == OWNER_ID):
            return
    if await rate_limit(message):
        return

    if message.channel.is_private:
        await log(0, 'pm from ' + message.author.name + ' (' + message.author.id + '): ' + message.content)
        if session[0] and message.author.id in session[1].keys():
            if session[1][message.author.id][1] in WOLFCHAT_ROLES and session[1][message.author.id][0]:
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
async def cmd_shutdown(message, parameters):    
    await reply(message, "Shutting down...")
    await client.logout()

async def cmd_ping(message, parameters):    
    PING_MSGS = ['Pong!',
                 '**PONG! ' + client.user.display_name + '** smashes the ball into **' + message.author.name + '**\'s face!',
                 'Ping!',
                 '\\*ping\\*. ' + client.user.display_name + ' taps the ball, which brushes the net and falls onto ' + message.author.name + '\'s side.'
                 ]
    msg = random.choice(PING_MSGS)
    await reply(message, msg)

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
    if output:
        await reply(message, '```\n' + str(output) + '\n```')
    else:
        await reply(message, ':thumbsup:')

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
        formatted_lines = traceback.format_exc().splitlines()
        await reply(message, '```py\n{}\n{}\n```'.format(formatted_lines[-1], '\n'.join(formatted_lines[4:-1])))
        return
    finally:
        sys.stdout = old_stdout
    if redirected_output.getvalue():
        await client.send_message(message.channel, redirected_output.getvalue())
        return
    await client.send_message(message.channel, ':thumbsup:')

async def cmd_help(message, parameters):    
    if parameters == '':
        parameters = 'help'
    if parameters in commands.keys():
        await reply(message, commands[parameters][2].format(BOT_PREFIX))
    else:
        await reply(message, 'No help found for command ' + parameters)

async def cmd_list(message, parameters):
    cmdlist = []
    for key in commands.keys():
        if message.channel.is_private:
            if has_privileges(commands[key][1][1], message):
                cmdlist.append(key)
        else:
            if has_privileges(commands[key][1][0], message):
                cmdlist.append(key)
    await reply(message, "Available commands: " + ", ".join(cmdlist).rstrip(", "))

async def cmd_join(message, parameters):
    if session[0]:
        return
    if len(list(list(session[1].keys()))) >= MAX_PLAYERS:
        await reply(message, "The maximum number of players have already joined the game.")
        return
    if message.author.id in list(session[1].keys()):
        await reply(message, "You are already playing!")
    else:
        if len(session[1].keys()) == 0:
            client.loop.create_task(game_start_timeout_loop())
            await client.send_message(client.get_channel(GAME_CHANNEL), "**{}** has started a game of Werewolf. Type `{p}join` to join. Type `{p}start` to start the game.".format(
                                            message.author.name, p=BOT_PREFIX))
        else:
            await client.send_message(message.channel, "**" + message.author.name + "** joined the game and raised the number of players to **{}**.".format(len(session[1]) + 1))
        #                            alive, role, action, [templates], [other]
        session[1][message.author.id] = [True, '', '', [], []]
        await client.add_roles(client.get_server(WEREWOLF_SERVER).get_member(message.author.id), PLAYERS_ROLE)
        await player_idle(message)

async def cmd_leave(message, parameters):
    if session[0] and message.author.id in list(session[1].keys()) and session[1][message.author.id][0]:
        session[1][message.author.id][0] = False
        quit_msgs = ['**{0}** spontaneously combusted. The air smells of freshly burnt **{1}**.',
                     'While wearing a red triangular hat, **{0}**, a **{1}**, was shot dead by a hunter.',
                     'While wearing a yellow square hat, **{0}**, a **{1}**, was rammed by a tank.',
                     'While wearing a blue pentagonal hat, **{0}**, a **{1}**, was destroyed by a giant cannonball.',
                     'While wearing an oversized blue pentagonal hat, **{0}**, a **{1}**, was annihilated by a humongous mortar shell.',
                     'After jumping into a tank, **{0}** drowned. The fish consumed the dead **{1}**\'s body.']
        await client.send_message(client.get_channel(GAME_CHANNEL), random.choice(quit_msgs).format(message.author.name, get_role(message.author.id, 'death')))
        await client.remove_roles(client.get_server(WEREWOLF_SERVER).get_member(message.author.id), PLAYERS_ROLE)
        if session[0] and await win_condition() == None:
            await check_traitor()
    else:
        if message.author.id in list(session[1].keys()):
            del session[1][message.author.id]
            await client.send_message(client.get_channel(GAME_CHANNEL), "**" + message.author.name + "** left the game. New player count: **{}**".format(
                                                                                                    len(session[1].keys())))
            await client.remove_roles(client.get_server(WEREWOLF_SERVER).get_member(message.author.id), PLAYERS_ROLE)
        else:
            await reply(message, "You are not in the game!")

async def cmd_fjoin(message, parameters):
    if session[0]:
        return
    if parameters == '':
        await reply(message, commands['fjoin'][2].format(BOT_PREFIX))
        return
    raw_members = parameters.split(' ')
    join_list = []
    join_names = []
    for member in raw_members:
        if member.strip('<!@>').isdigit():
            if isinstance(client.get_server(WEREWOLF_SERVER).get_member(member.strip('<!@>')), discord.Member):
                join_list.append(member.strip('<!@>'))
                join_names.append(client.get_server(WEREWOLF_SERVER).get_member(member.strip('<!@>')).name)
            else:
                join_list.append(member.strip('<!@>'))
                join_names.append(member.strip('<!@>'))
    if join_list == []:
        await reply(message, "ERROR: no valid mentions found")
        return
    join_msg = ""
    for i, member in enumerate(join_list):
        session[1][member] = [True, '', '', [], []]
        join_msg += "**" + join_names[i] + "** was forced to join the game.\n"
        if client.get_server(WEREWOLF_SERVER).get_member(member):
            await client.add_roles(client.get_server(WEREWOLF_SERVER).get_member(member), PLAYERS_ROLE)
    join_msg += "New player count: **{}**".format(len(session[1].keys()))
    await client.send_message(message.channel, join_msg)
    await log(1, "{0} ({1}) used fjoin {2}".format(message.author.name, message.author.id, parameters))

async def cmd_fleave(message, parameters):
    if parameters == '':
        await reply(message, commands['fleave'][2].format(BOT_PREFIX))
        return
    raw_members = parameters.split(' ')
    leave_list = []
    if parameters == 'all':
        leave_list = list(session[1].keys())
    else:
        for member in raw_members:
            if member.strip('<!@>').isdigit():
                leave_list.append(member.strip('<!@>'))
    if leave_list == []:
        await reply(message, "ERROR: no valid mentions found")
        return
    leave_msg = ""
    for i, member in enumerate(leave_list):
        if member in list(session[1].keys()):
            if session[0]:
                session[1][member][0] = False
                leave_msg += "**" + get_name(member) + "** was forcibly shoved into a fire. The air smells of freshly burnt **" + get_role(member, 'death') + "**.\n"
            else:
                del session[1][member]
                leave_msg += "**" + get_name(member) + "** was forced to leave the game.\n"
            if client.get_server(WEREWOLF_SERVER).get_member(member):
                await client.remove_roles(client.get_server(WEREWOLF_SERVER).get_member(member), PLAYERS_ROLE)
    if not session[0]:
        leave_msg += "New player count: **{}**".format(len(session[1].keys()))
    await client.send_message(client.get_channel(GAME_CHANNEL), leave_msg)
    await log(1, "{0} ({1}) used fleave {2}".format(message.author.name, message.author.id, parameters))
    if session[0] and await win_condition() == None:
        await check_traitor()

async def cmd_start(message, parameters):
    if session[0]:
        return
    if message.author.id not in session[1].keys():
        await reply(message, "You are not playing! Type `!join` to join the game.")
        return
    if len(list(list(session[1].keys()))) < MIN_PLAYERS:
        await reply(message, "Please wait until there are at least " + str(MIN_PLAYERS) + " players.")
        return
    await run_game(message)

async def cmd_fstart(message, parameters):
    if session[0]:
        return
    if len(list(list(session[1].keys()))) < MIN_PLAYERS:
        await reply(message, "Please wait until there are at least " + str(MIN_PLAYERS) + " players.")
    else:
        await client.send_message(client.get_channel(GAME_CHANNEL), "**" + message.author.name + "** forced the game to start.")
        await log(1, "{0} ({1}) used fstart".format(message.author.name, message.author.id))
        await run_game(message)

async def cmd_fstop(message, parameters):
    if not session[0]:
        await reply(message, "There is no currently running game!")
        return
    await log(1, "{0} ({1}) used fstop".format(message.author.name, message.author.id))
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
        for player in list(list(session[1].keys())):
            del session[1][player]
            member = client.get_server(WEREWOLF_SERVER).get_member(player)
            if member:
                await client.remove_roles(member, PLAYERS_ROLE)
        session[3] = [0, 0]
        session[4] = [timedelta(0), timedelta(0)]
        await client.send_message(client.get_channel(GAME_CHANNEL), msg)
    else:
        msg += " for reason: `" + parameters + "`."
            
    await end_game(msg + '\n\n' + end_game_stats())

async def cmd_sync(message, parameters):
    for member in client.get_server(WEREWOLF_SERVER).members:
        if member.id in list(session[1].keys()):
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
    await reply(message, "Sync successful.")

async def cmd_op(message, parameters):
    if parameters == "":
        await client.add_roles(client.get_server(WEREWOLF_SERVER).get_member(message.author.id), ADMINS_ROLE)
        await reply(message, ":thumbsup:")
    else:
        member = client.get_server(WEREWOLF_SERVER).get_member(parameters.strip("<!@>"))
        if member:
            if member.id in ADMINS:
                await client.add_roles(member, ADMINS_ROLE)
                await reply(message, ":thumbsup:")

async def cmd_deop(message, parameters):
    if parameters == "":
        await client.remove_roles(client.get_server(WEREWOLF_SERVER).get_member(message.author.id), ADMINS_ROLE)
        await reply(message, ":thumbsup:")
    else:
        member = client.get_server(WEREWOLF_SERVER).get_member(parameters.strip("<!@>"))
        if member:
            if member.id in ADMINS:
                await client.remove_roles(member, ADMINS_ROLE)
                await reply(message, ":thumbsup:")

async def cmd_role(message, parameters):
    if parameters == "" and not session[0]:
        await reply(message, "Roles: " + ", ".join(sort_roles(roles.keys())))
    elif parameters == "" and session[0]:
        msg = "**" + str(len(list(session[1].keys()))) + "** players playing:```\n"
        for role in sort_roles(roles.keys()):
            if roles[role][3][len(list(session[1].keys())) - MIN_PLAYERS] > 0:
                msg += role + ": " + str(roles[role][3][len(list(session[1].keys())) - MIN_PLAYERS]) + '\n'
        msg += '```'
        await reply(message, msg)
    elif parameters in roles.keys():
        await reply(message, "```\nRole name: " + parameters + "\nSide: " + roles[parameters][0] + "\nDescription: " + roles[parameters][2] + "```")
    elif parameters.isdigit():
        if int(parameters) in range(MIN_PLAYERS, MAX_PLAYERS + 1):
            msg = "```\n"
            for role in sort_roles(roles.keys()):
                if roles[role][3][int(parameters) - MIN_PLAYERS] > 0:
                    msg += role + ": " + str(roles[role][3][int(parameters) - MIN_PLAYERS]) + '\n'
            msg += '```'
            await reply(message, msg)
        else:
            await reply(message, "Please choose a number of players between " + str(MIN_PLAYERS) + " and " + str(MAX_PLAYERS) + ".")
    else:
        await reply(message, "Could not find role named " + parameters)

async def cmd_myrole(message, parameters):
    if session[0] and message.author.id in session[1].keys():
        player = message.author.id
        member = client.get_server(WEREWOLF_SERVER).get_member(player)
        if member and session[1][player][0]:
            role = session[1][player][1]
            if member and session[1][player][0]:
                try:
                    temp_players = []
                    for plr in [x for x in session[1].keys() if session[1][x][0]]:
                        temp_players.append('**' + get_name(plr) + '** (' + plr + ')')
                    living_players = ', '.join(temp_players).rstrip(', ')
                    await client.send_message(member, "Your role is **" + role + "**. " + roles[role][2] + '\n')
                    msg = ''
                    if roles[role][0] == 'wolf' and role != 'cultist':
                        temp_players = []
                        for plr in [x for x in session[1].keys() if session[1][x][0]]:
                            if roles[session[1][plr][1]][0] in ['wolf']:
                                temp_players.append('**' + get_name(plr) + '** (' + plr + ') (**' + session[1][plr][1] + '**)')
                            elif 'cursed' in session[1][plr][3]:
                                temp_players.append('**' + get_name(plr) + '** (' + plr + ') (**cursed**)')
                            else:
                                temp_players.append('**' + get_name(plr) + '** (' + plr + ')')
                        msg += "Living players: " + ', '.join(temp_players).rstrip(', ') + '\n'
                    elif role == 'shaman':
                        if session[1][player][2] in totems:
                            totem = session[1][player][2]
                            msg += "You have the **{0}**. {1}".format(totem.replace('_', ' '), totems[totem]) + '\n'
                    if role in ['seer', 'shaman']:
                        msg += "Living players: " + living_players + '\n'
                    if msg != '':
                        await client.send_message(member, msg)
                except discord.Forbidden:
                    await client.send_message(client.get_channel(GAME_CHANNEL), member.mention + ", you cannot play the game if you block me")

async def cmd_stats(message, parameters):
    if session[0]:
        reply_msg = "It is now **" + ("day" if session[2] else "night") + "time**."
        reply_msg += "\n**" + str(len(session[1].keys())) + "** players playing: **" + str(len([x for x in session[1].keys() if session[1][x][0]])) + "** alive, "
        reply_msg += "**" + str(len([x for x in session[1].keys() if not session[1][x][0]])) + "** dead\n"
##        reply_msg += "```\nLiving players: " + ", ".join(sorted([get_name(x) + ' (' + x + ')' for x in list(session[1].keys()) if session[1][x][0]])) + '\n'
##        reply_msg += "Dead players: " + ", ".join(sorted([get_name(x) + ' (' + x + ')' for x in list(session[1].keys()) if not session[1][x][0]])) + '\n'
        reply_msg += "```basic\nLiving players:\n" + "\n".join(sorted([get_name(x) + ' (' + x + ')' for x in list(session[1].keys()) if session[1][x][0]])) + '\n'
        reply_msg += "Dead players:\n" + "\n".join(sorted([get_name(x) + ' (' + x + ')' for x in list(session[1].keys()) if not session[1][x][0]])) + '\n'

        orig_roles = {}
        for role in roles.keys():
            if roles[role][3][len(session[1].keys()) - MIN_PLAYERS] > 0:
                orig_roles[role] = roles[role][3][len(session[1].keys()) - MIN_PLAYERS]
        role_dict = {}
        traitorvill = 0
        traitor_turned = False
        for other in [session[1][x][4] for x in session[1].keys()]:
            if 'traitor' in other:
                traitor_turned = True
                break
            
        #for role in [r for r in roles.keys() if roles[r][3][len(session[1].keys()) - MIN_PLAYERS] > 0]:
        # for role in [session[1][x][1] for x in session[1].keys()]: this gets the roles from players
        for role in orig_roles.keys():
            #role_dict[role] = 0
            role_dict[role] = [0, 0]
            # [min, max] for traitor and similar roles
        for player in list(session[1].keys()):
            # Get maximum numbers for all roles
            role_dict[get_role(player, 'role')][0] += 1
            role_dict[get_role(player, 'role')][1] += 1
            if get_role(player, 'role') in ['villager', 'traitor']:
                traitorvill += 1
            
        #reply_msg += "Total roles: " + ", ".join(sorted([x + ": " + str(roles[x][3][len(session[1].keys()) - MIN_PLAYERS]) for x in roles.keys() if roles[x][3][len(session[1].keys()) - MIN_PLAYERS] > 0])).rstrip(", ") + '\n'

        reply_msg += "Total roles: "
        total_roles = sort_roles([x for x in roles.keys() if roles[x][3][len(session[1]) - MIN_PLAYERS] > 0])
        reply_msg += ', '.join(["{}: {}".format(x, roles[x][3][len(session[1]) - MIN_PLAYERS]) for x in total_roles])
        
        for role in list(role_dict.keys()):
            if role in ['cursed villager']:
                del role_dict[role]

        if traitor_turned:
            role_dict['wolf'][0] += role_dict['traitor'][0]
            role_dict['wolf'][1] += role_dict['traitor'][1]
            role_dict['traitor'] = [0, 0]
        
        for player in session[1].keys():
            # Subtract dead players
            if not session[1][player][0]:
                role = get_role(player, 'role')
                reveal = get_role(player, 'death')
                
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
        for role in sort_roles(role_dict.keys()):
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
        #reply_msg += "Current roles: " + ", ".join(sorted([x + ": " + str(role_dict[x]) for x in role_dict.keys()])) + "```"
        await reply(message, reply_msg)
    else:
        formatted_list = []
        for player in list(session[1].keys()):
            if client.get_server(WEREWOLF_SERVER).get_member(player):
                formatted_list.append(client.get_server(WEREWOLF_SERVER).get_member(player).name + ' (' + player + ')')
            else:
                formatted_list.append(player + ' (' + player + ')')
        num_players = len(list(list(session[1].keys())))
        if num_players == 0:
            await client.send_message(message.channel, "There is currently no active game. Try {}join to start a new game!".format(BOT_PREFIX))
        else:
            await client.send_message(message.channel, str(len(list(session[1].keys()))) + " players in lobby: ```\n" + "\n".join(sorted(formatted_list)) + "```")

async def cmd_revealroles(message, parameters):
    msg = "```diff\n"
    for player in sorted(list(list(session[1].keys()))):
        msg += "{} ".format('+' if session[1][player][0] else '-') + get_name(player) + ' (' + player + '): ' + get_role(player, 'actual')
        msg += "; action: " + session[1][player][2] + "; other: " + ' '.join(session[1][player][4]) + "\n"
    msg += "```"
    await client.send_message(message.channel, msg)
    await log(1, "{0} ({1}) used revealroles".format(message.author.name, message.author.id))

async def cmd_see(message, parameters):
    if not session[0] or message.author.id not in session[1].keys() or session[1][message.author.id][1] != 'seer' or not session[1][message.author.id][0] or session[2]:
        return
    if session[2]:
        await reply(message, "You may only see during the night.")
        return
    if session[1][message.author.id][2]:
        await reply(message, "You have already used your power.")
    else:
        if parameters == "":
            await reply(message, roles[session[1][message.author.id][1]][2])
        else:
            player = get_player(parameters)
            if player:
                if player == message.author.id:
                    await reply(message, "Using your power on yourself would be a waste.")
                elif player in [x for x in list(session[1].keys()) if not session[1][x][0]]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                else:
                    session[1][message.author.id][2] = player
                    # (SAVE FOR DETECTIVE) await reply(message, "You have a vision... in your vision you see that **" + get_name(player) + "** is a **" + session[1][player][1] + "**!")
##                    seen_role = ''
##                    if session[1][player][1] in ROLES_SEEN_WOLF:
##                        seen_role = 'wolf'
##                    elif session[1][player][1] in ROLES_SEEN_VILLAGER:
##                        seen_role = 'villager'
##                    else:
##                        seen_role = session[1][player][1]
##                    for template in session[1][player][3]:
##                        if template in ROLES_SEEN_WOLF:
##                            seen_role = 'wolf'
##                            break
##                        if template in ROLES_SEEN_VILLAGER:
##                            seen_role = 'villager'
                    seen_role = get_role(player, 'seen')
                    await reply(message, "You have a vision... in your vision you see that **" + get_name(player) + "** is a **" + seen_role + "**!")
                    await log(0, "{0} ({1}) SEE {2} ({3}) AS {4}".format(get_name(message.author.id), message.author.id, get_name(player), player, seen_role))
            else:        
                await reply(message, "Could not find player " + parameters)
    
async def cmd_kill(message, parameters):
    if not session[0] or message.author.id not in session[1].keys() or session[1][message.author.id][1] != 'wolf' or not session[1][message.author.id][0] or session[2]:
        return
    if session[2]:
        await reply(message, "You may only kill during the night.")
        return
    if session[1][message.author.id][2]:
        await reply(message, "You have already chosen **" + get_name(session[1][message.author.id][2]) + "** to kill.")
    else:
        if parameters == "":
            await reply(message, roles[session[1][message.author.id][1]][2])
        else:
            player = get_player(parameters)
            if player:
                if player == message.author.id:
                    await reply(message, "You can't kill yourself.")
                elif player in [x for x in list(session[1].keys()) if roles[session[1][x][1]][0] == 'wolf' and session[1][x][1] != 'cultist']:
                    await reply(message, "You can't kill another wolf.")
                elif player in [x for x in list(session[1].keys()) if not session[1][x][0]]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                else:
                    session[1][message.author.id][2] = player
                    await reply(message, "You have chosen to kill **" + get_name(player) + "**.")
                    await log(0, "{0} ({1}) KILL {2} ({3})".format(get_name(message.author.id), message.author.id, get_name(player), player))
            else:        
                await reply(message, "Could not find player " + parameters)

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
        to_lynch = get_player(parameters.split(' ', 1)[0])
        if not to_lynch:
            to_lynch = get_player(parameters)
        if to_lynch:
            if to_lynch in [x for x in list(session[1].keys()) if not session[1][x][0]]:
                await reply(message, "Player **" + get_name(to_lynch) + "** is dead!")
            else:
                session[1][message.author.id][2] = to_lynch
                await reply(message, "You have voted to lynch **" + get_name(to_lynch) + "**.")
                await log(0, "{0} ({1}) LYNCH {2} ({3})".format(get_name(message.author.id), message.author.id, get_name(to_lynch), to_lynch))
        else:
            await reply(message, "Could not find player " + parameters)

async def cmd_votes(message, parameters):
    if not session[0] or not session[2]:
        return
    vote_dict = {'abstain': []}
    alive_players = [x for x in session[1] if session[1][x][0]]
    for player in alive_players:
        if session[1][player][2] in vote_dict:
            vote_dict[session[1][player][2]].append(player)
        elif session[1][player][2] != '':
            vote_dict[session[1][player][2]] = [player]
    abstainers = vote_dict['abstain']
    reply_msg = "**{}** players, **{}** votes required to lynch, **{}** players available to vote, **{}** player{} refrained from voting.\n".format(
        len(alive_players), len(alive_players) // 2 + 1, len(alive_players), len(abstainers), '' if len(abstainers) == 1 else 's')
    # TODO: Silenced players
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
            
async def cmd_retract(message, parameters):
    if not session[0] or message.author.id not in session[1].keys() or not session[1][message.author.id][0] or session[1][message.author.id][2] == '':
        return
    if session[2]:
        if message.channel.is_private:
            await reply(message, "Please use retract in channel.")
            return
        session[1][message.author.id][2] = ''
        await reply(message, "You retracted your vote.")
        await log(0, "{0} ({1}) RETRACT VOTE".format(get_name(message.author.id), message.author.id))
    else:
        if session[1][message.author.id][1] in ['wolf']:
            if not message.channel.is_private:
                await client.send_message(message.author, "Please use retract in pm.")
                return
            session[1][message.author.id][2] = ''
            await reply(message, "You retracted your kill.")
            await log(0, "{0} ({1}) RETRACT KILL".format(get_name(message.author.id), message.author.id))

async def cmd_abstain(message, parameters):
    if not session[0] or not session[2] or not message.author.id in [x for x in session[1] if session[1][x][0]]:
        return
    if session[4][1] == timedelta(0):
        await client.send_message(client.get_channel(GAME_CHANNEL), "The village may not abstain on the first day.")
        return
    session[1][message.author.id][2] = 'abstain'
    await log(0, "{0} ({1}) ABSTAIN".format(get_name(message.author.id), message.author.id))
    await client.send_message(client.get_channel(GAME_CHANNEL), "**{}** votes to not lynch anyone today.".format(get_name(message.author.id)))

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

async def cmd_admins(message, parameters):
    # await reply(message, 'Available admins: **' + '**, **'.join([client.get_server(WEREWOLF_SERVER).get_member(x).name for x in ADMINS if client.get_server(WEREWOLF_SERVER).get_member(x)]).rstrip("**, **") + "**")
##    available = [x for x in ADMINS if is_online(x)]
##    for admin in ADMINS:
##        admin_member = client.get_server(WEREWOLF_SERVER).get_member(admin)
##        if admin_member:
##            if admin_member.status in [discord.Status.online, discord.Status.idle]:
##                available.append(admin_member)
    await reply(message, 'Available admins: ' + ', '.join(['<@{}>'.format(x) for x in ADMINS if is_online(x)]))

async def cmd_fday(message, parameters):
    if session[0] and not session[2]:
        session[2] = True
        await reply(message, ":thumbsup:")
        await log(1, "{0} ({1}) used fday".format(message.author.name, message.author.id))

async def cmd_fnight(message, parameters):
    if session[0] and session[2]:
        session[2] = False
        await reply(message, ":thumbsup:")
        await log(1, "{0} ({1}) used fnight".format(message.author.name, message.author.id))

async def cmd_frole(message, parameters):
    if not session[0] or parameters == '':
        return
    player = parameters.split(' ')[0]
    role = parameters.split(' ', 1)[1]
    temp_player = get_player(player)
    if temp_player:
        if role in roles.keys() or role == 'cursed':
            if role != 'cursed':
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
            await reply(message, "Successfully set **{}**'s role to **{}**.".format(get_name(temp_player), role))
        else:
            await reply(message, "Cannot find role named **" + role + "**")
    else:
        await reply(message, "Cannot find player named **" + player + "**")

async def cmd_force(message, parameters):
    if not session[0] or parameters == '':
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

async def cmd_session(message, parameters):
    await client.send_message(message.author, "```py\n{}\n```".format(str(session)))
    await log(1, "{0} ({1}) used session".format(message.author.name, message.author.id))

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
        if len(session[1].keys()) > 0:
            timeleft = GAME_START_TIMEOUT - (datetime.now() - session[5]).seconds
            await reply(message, "There is **{0:02d}:{1:02d}** left to start the game until it will be automatically cancelled. "
                                 "GAME_START_TIMEOUT is currently set to **{2:02d}:{3:02d}**.".format(
                                     timeleft // 60, timeleft % 60, GAME_START_TIMEOUT // 60, GAME_START_TIMEOUT % 60))              

async def cmd_give(message, parameters):
    if not session[0] or message.author.id not in session[1].keys() or session[1][message.author.id][1] != 'shaman' or not session[1][message.author.id][0] or session[2]:
        return
    if session[2]:
        await reply(message, "You may only give totems during the night.")
        return
    if session[1][message.author.id][2] not in totems.keys():
        await reply(message, "You have already given your totem to **" + get_name(session[1][message.author.id][2]) + "**.")
    else:
        if parameters == "":
            await reply(message, roles[session[1][message.author.id][1]][2])
        else:
            player = get_player(parameters)
            if player:
                if player in [x for x in list(session[1].keys()) if not session[1][x][0]]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                else:
                    totem = session[1][message.author.id][2]
                    session[1][player][4].append(totem)
                    session[1][message.author.id][2] = player
                    await reply(message, "You have given your totem to **" + get_name(player) + "**.")
                    await log(0, "{0} ({1}) GAVE {2} ({3}) {4}".format(get_name(message.author.id), message.author.id, get_name(player), player, totem))
            else:        
                await reply(message, "Could not find player " + parameters)

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

async def cmd_notify_role(message, parameters):
    if not WEREWOLF_NOTIFY_ROLE:
        await reply(message, "Error: A " + WEREWOLF_NOTIFY_ROLE_NAME + " role does not exist. Please let an admin know.")
        return
    member = client.get_server(WEREWOLF_SERVER).get_member(message.author.id)
    if not member:
        await reply(message, "You are not in the server!")
    has_role = (WEREWOLF_NOTIFY_ROLE in member.roles)
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
                await reply(message, str(len(IGNORE_LIST)) + " ignored users:\n```\n" + '\n'.join([x + " (" + msg_dict[x] + ")" for x in list(msg_dict.keys())]) + "```")
        else:
            await reply(message, commands['ignore'][2].format(BOT_PREFIX))
        await log(1, "{0} ({1}) used ignore {2}".format(message.author.name, message.author.id, parameters))
        
async def cmd_pingif(message, parameters):
    global pingif_dict
    if parameters == '':
        if message.author.id in pingif_dict.keys():
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

async def cmd_online(message, parameters):
    members = [x.id for x in message.server.members]
    online = ["<@{}>".format(x) for x in members if is_online(x)]
    await reply(message, "PING! {}".format(''.join(online)))

async def cmd_notify(message, parameters):
    notify = message.author.id in notify_me
    if parameters == '':
        online = ["<@{}>".format(x) for x in notify_me if is_online(x)]
        await reply(message, "PING! {}".format(''.join(online)))
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

async def cmd_visit(message, parameters):
    if not session[0] or message.author.id not in session[1].keys() or session[1][message.author.id][1] != 'harlot' or not session[1][message.author.id][0]:
        return
    if session[2]:
        await reply(message, "You may only visit during the night.")
        return
    if session[1][message.author.id][2]:
        await reply(message, "You are already spending the night with **{}**.".format(get_name(session[1][message.author.id][2])))
    else:
        if parameters == "":
            await reply(message, roles[session[1][message.author.id][1]][2])
        else:
            player = get_player(parameters)
            if player:
                if player == message.author.id:
                    await reply(message, "You have chosen to stay home tonight.")
                    session[1][message.author.id][2] = message.author.id
                    await log(0, "{0} ({1}) STAY HOME".format(get_name(message.author.id), message.author.id))
                elif player in [x for x in list(session[1].keys()) if not session[1][x][0]]:
                    await reply(message, "Player **" + get_name(player) + "** is dead!")
                else:
                    await reply(message, "You are spending the night with **{}**. Have a good time!".format(get_name(player)))
                    session[1][message.author.id][2] = player
                    member = client.get_server(WEREWOLF_SERVER).get_member(player)
                    try:
                        await client.send_message(member, "You are spending the night with **{}**. Have a good time!".format(get_name(message.author.id)))
                    except:
                        pass
                    await log(0, "{0} ({1}) VISIT {2} ({3})".format(get_name(message.author.id), message.author.id, get_name(player), player))
            else:        
                await reply(message, "Could not find player " + parameters)
        
######### END COMMANDS #############

def has_privileges(level, message):
    if message.author.id == OWNER_ID:
        return True
    elif level == 1 and message.author.id in ADMINS:
        return True
    elif level == 0:
        return True
    else:
        return False

async def reply(message, text): 
    await client.send_message(message.channel, message.author.mention + ', ' + str(text))

async def parse_command(commandname, message, parameters):
    await log(0, 'Parsing command ' + commandname + ' with parameters `' + parameters + '` from ' + message.author.name + ' (' + message.author.id + ')')
    if commandname in commands.keys():
        pm = 0
        if message.channel.is_private:
            pm = 1
        if has_privileges(commands[commandname][1][pm], message):
            try:
                await commands[commandname][0](message, parameters)
            except Exception:
                formatted_lines = traceback.format_exc().splitlines()
                await client.send_message(message.channel, "An error has occurred and has been logged.")
                msg = '```py\n{}\n{}\n```'.format(formatted_lines[-1], '\n'.join(formatted_lines[4:-1]))
                await log(2, msg)
                print(msg)
        elif has_privileges(commands[commandname][1][0], message):
            await reply(message, "Please use command " + commandname + " in channel.")
        elif has_privileges(commands[commandname][1][1], message):
            if session[0] and message.author.id in [x for x in session[1].keys() if session[1][x][0]]:
                if session[1][message.author.id][1] in [COMMANDS_FOR_ROLE[x] for x in COMMANDS_FOR_ROLE if commandname == x]:
                    try:
                        await client.send_message(message.author, "Please use command " + commandname + " in private message.")
                    except discord.Forbidden:
                        pass
            elif message.author.id in ADMINS:
                await reply(message, "Please use command " + commandname + " in private message.")
        else:
            await log(1, 'User ' + message.author.name + ' (' + message.author.id + ') tried to use command ' + commandname + ' with parameters `' + parameters + '` without permissions!')

async def log(loglevel, text):
    # loglevels
    # 0 = DEBUG
    # 1 = WARNING
    # 2 = ERROR
    levelmsg = {0 : '[DEBUG] ',
                1 : '**[WARNING]** ',
                2 : '**[ERROR]** <@' + OWNER_ID + '> '
                }
    logmsg = levelmsg[loglevel] + str(text)
    await client.send_message(discord.Object(DEBUG_CHANNEL), logmsg)

async def assign_roles(gamemode):
    
    massive_role_list = []

    if gamemode == 'default':
        for role in roles.keys():
            for i in range(roles[role][3][len(list(list(session[1].keys()))) - MIN_PLAYERS]):
                massive_role_list.append(role)
        random.shuffle(massive_role_list)
        for player in list(session[1].keys()):
            session[1][player][1] = massive_role_list.pop()
            if session[1][player][1] == 'cursed villager':
                session[1][player][1] = 'villager'
                session[1][player][3].append('cursed')

async def end_game(reason):
    if not session[0]:
        return
    session[0] = False
    if session[2]:
        session[4][1] += datetime.now() - session[3][1]
    else:
        session[4][0] += datetime.now() - session[3][0]
    await client.send_message(client.get_channel(GAME_CHANNEL), PLAYERS_ROLE.mention + " Game over! Night lasted **{0:02d}:{1:02d}**. "
                                                                                       "Day lasted **{2:02d}:{3:02d}**. "
                                                                                       "Game lasted **{4:02d}:{5:02d}**. \n{6}".format(
                              session[4][0].seconds // 60, session[4][0].seconds % 60, session[4][1].seconds // 60, session[4][1].seconds % 60,
                              (session[4][0].seconds + session[4][1].seconds) // 60, (session[4][0].seconds + session[4][1].seconds) % 60, reason))
    perms = client.get_channel(GAME_CHANNEL).overwrites_for(client.get_server(WEREWOLF_SERVER).default_role)
    perms.send_messages = True
    await client.edit_channel_permissions(client.get_channel(GAME_CHANNEL), client.get_server(WEREWOLF_SERVER).default_role, perms)
    for player in list(list(session[1].keys())):
        del session[1][player]
        member = client.get_server(WEREWOLF_SERVER).get_member(player)
        if member:
            await client.remove_roles(member, PLAYERS_ROLE)
    session[3] = [0, 0]
    session[4] = [timedelta(0), timedelta(0)]
    session[6] = ''

async def win_condition():
    teams = {'village' : 0, 'wolf' : 0}
    for player in list(session[1].keys()):
        if session[1][player][0]:
            if session[1][player][1] == 'cultist':
                teams['village'] += 1
            else:
                teams[roles[session[1][player][1]][0]] += 1
    winners = []
    win_team = ''
    win_lore = ''
    win_msg = ''
    if teams['village'] <= teams['wolf']:
        win_team = 'wolf'
        win_lore = 'The number of living villagers is equal or less than the number of living wolves! The wolves overpower the remaining villagers and devour them whole.'
    elif teams['wolf'] == 0:
        win_team = 'village'
        win_lore = 'All the wolves are dead! The surviving villagers gather the bodies of the dead wolves, roast them, and have a BBQ in celebration.'
    elif len(session[1].keys()) == 0:
        win_lore = 'Everyone died. The town sits abandoned, collecting dust.'
        win_team = 'no win'
    else:
        return None
    
    for player in list(session[1].keys()):
        if roles[session[1][player][1]][0] == win_team:
            winners.append(get_name(player))
    if len(winners) == 0:
        win_msg = "No one wins!"
    elif len(winners) == 1:
        win_msg = "The winner is **" + winners[0] + "**!"
    elif len(winners) == 2:
        win_msg = "The winners are **" + winners[0] + "** and **" + winners[1] + "**!"
    else:
        win_msg = "The winners are **" + "**, **".join(winners[:-1]) + "**, and **" + winners[-1] + "**!"
    return [win_team, win_lore + '\n\n' + end_game_stats() + '\n\n' + win_msg]

def end_game_stats():
    role_msg = ""
    role_dict = {}
    for role in roles.keys():
        role_dict[role] = []
    for player in list(session[1].keys()):
        if 'traitor' in session[1][player][4]:
            session[1][player][1] = 'traitor'
            session[1][player][4].remove('traitor')
        role_dict[session[1][player][1]].append(get_name(player))
        if 'cursed' in session[1][player][3]:
            role_dict['cursed villager'].append(get_name(player))
    for key in sort_roles(role_dict.keys()):
        value = role_dict[key]
        if len(value) == 0:
            pass
        elif len(value) == 1:
            role_msg += "The **" + key + "** was **" + value[0] + "**. "
        elif len(value) == 2:
            role_msg += "The **" + roles[key][1] + "** were **" + value[0] + "** and **" + value[1] + "**. "
        else:
            role_msg += "The **" + roles[key][1] + "** were **" + "**, **".join(value[:-1]) + "**, and **" + value[-1] + "**. "
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
    for player in list(session[1].keys()):
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

def get_role(player, level):
    # level: {team: reveal team only; seen: what the player is seen as; death: role taking into account cursed and cultist and traitor; actual: actual role}
##(terminology: role = what you are, template = additional things that can be applied on top of your role) 
##cursed, gunner, blessed, mayor, assassin are all templates 
##so you always have exactly 1 role, but can have 0 or more templates on top of that 
##revealing totem (and similar powers, like detective id) only reveal roles 
    if session[0]:
        if player in session[1].keys():
            role = session[1][player][1]
            templates = session[1][player][3]
            if level == 'team':
                if roles[role][0] == 'wolf':
                    if not role in ['cultist', 'traitor']:
                        return "wolf"
                return "villager"
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
            elif level == 'death':
                if role == 'traitor':
                    return 'villager'
                return role
            elif level == 'role':
                return role
            elif level == 'actual':
                return ' '.join(templates) + ' ' + role
    return None

async def wolfchat(message):
    for wolf in [x for x in session[1].keys() if x != message.author.id and session[1][x][0] and session[1][x][1] in WOLFCHAT_ROLES and client.get_server(WEREWOLF_SERVER).get_member(x)]:
        try:
            await client.send_message(client.get_server(WEREWOLF_SERVER).get_member(wolf), "**[Wolfchat]** message from **" + message.author.name + "**: " + message.content)
        except discord.Forbidden:
            pass

async def cmd_test(message, parameters):
    pass

async def player_idle(message):
    while message.author.id in session[1].keys() and not session[0]:
        await asyncio.sleep(1)
    while message.author.id in session[1].keys() and session[0] and session[1][message.author.id][0]:
        def check(msg):
            if not message.author.id in session[1].keys() or not session[1][message.author.id][0] or not session[0]:
                return True
            if msg.author.id == message.author.id and msg.channel.id == client.get_channel(GAME_CHANNEL).id:
                return True
            return False
        msg = await client.wait_for_message(author=message.author, channel=client.get_channel(GAME_CHANNEL), timeout=PLAYER_TIMEOUT, check=check)
        if msg == None and message.author.id in session[1].keys() and session[0] and session[1][message.author.id][0]:
            await client.send_message(client.get_channel(GAME_CHANNEL), message.author.mention + "**, you have been idling for a while. Please say something soon or you might be declared dead.**")
            try:
                await client.send_message(message.author, "**You have been idling in " + client.get_channel(GAME_CHANNEL).name + " for a while. Please say something soon or you might be declared dead.**")
            except discord.Forbidden:
                pass
            msg = await client.wait_for_message(author=message.author, channel=client.get_channel(GAME_CHANNEL), timeout=60, check=check)
            if msg == None and message.author.id in session[1].keys() and session[0] and session[1][message.author.id][0]:
                await client.send_message(client.get_channel(GAME_CHANNEL), "**" + get_name(message.author.id) + "** didn't get out of bed for a very long time and has been found dead. "
                                          "The survivors bury the **" + get_role(message.author.id, 'death') + '**.')
                session[1][message.author.id][0] = False
                await client.remove_roles(client.get_server(WEREWOLF_SERVER).get_member(message.author.id), PLAYERS_ROLE)

def is_online(user_id):
    member = client.get_server(WEREWOLF_SERVER).get_member(user_id)
    if member:
        if member.status in [discord.Status.online, discord.Status.idle]:
            return True
    return False

async def check_traitor():
    if not session[0]:
        return
    for other in [session[1][x][4] for x in session[1].keys()]:
        if 'traitor' in other:
            # traitor already turned
            return
        
    if len([x for x in session[1].keys() if session[1][x][0] and get_role(x, 'role') in WOLFCHAT_ROLES and get_role(x, 'role') != 'traitor']) == 0:
        traitors = [x for x in session[1].keys() if session[1][x][0] and get_role(x, 'role') == 'traitor']
        await log(0, ', '.join(traitors) + " turned into wolf")
        for traitor in traitors:
            session[1][traitor][4].append('traitor')
            session[1][traitor][1] = 'wolf'
            member = client.get_server(WEREWOLF_SERVER).get_member(traitor)
            if member:
                try:
                    await client.send_message(member, "HOOOOOOOOOWL. You have become... a wolf!\nIt is up to you to avenge your fallen leaders!")
                except discord.Forbidden:
                    pass
        await client.send_message(client.get_channel(GAME_CHANNEL), "**The villagers, during their celebrations, are frightened as they hear a loud howl. The wolves are not gone!**")        

def sort_roles(roles):
    return [x for x in WOLF_ROLES_ORDERED + VILLAGE_ROLES_ORDERED + NEUTRAL_ROLES_ORDERED + TEMPLATES_ORDERED if x in roles]

async def run_game(message):
    session[0] = True
    session[2] = False
    session[6] = 'default' # Change for gamemodes later
    perms = client.get_channel(GAME_CHANNEL).overwrites_for(client.get_server(WEREWOLF_SERVER).default_role)
    perms.send_messages = False
    await client.edit_channel_permissions(client.get_channel(GAME_CHANNEL), client.get_server(WEREWOLF_SERVER).default_role, perms)
    await client.send_message(client.get_channel(GAME_CHANNEL), PLAYERS_ROLE.mention + ", Welcome to Werewolf, the popular detective/social party game (a theme of Mafia). "
                              "Using the **{}** game mode.\nAll players check for PMs from me for instructions. "
                              "If you did not receive a pm, please let {} know.".format(session[6], client.get_server(WEREWOLF_SERVER).get_member(OWNER_ID).name))
    await assign_roles(session[6])
    await log(0, str(session))
    first_night = True
    # GAME START
    while await win_condition() == None and session[0]:
        for player in session[1].keys():
            member = client.get_server(WEREWOLF_SERVER).get_member(player)
            role = session[1][player][1]
            if role == 'shaman':
                session[1][player][2] = random.choice(list(totems.keys()))
                await log(0, "{} ({}) HAS {}".format(get_name(player), player, session[1][player][2]))
            if member and session[1][player][0]:
                try:
                    temp_players = []
                    for plr in [x for x in session[1].keys() if session[1][x][0]]:
                        temp_players.append('**' + get_name(plr) + '** (' + plr + ')')
                    living_players = ', '.join(temp_players).rstrip(', ')
                    if first_night:
                        await client.send_message(member, "Your role is **" + role + "**. " + roles[role][2] + '\n')
                    msg = ''
                    if roles[role][0] == 'wolf' and role != 'cultist':
                        temp_players = []
                        for plr in [x for x in session[1].keys() if session[1][x][0]]:
                            if roles[session[1][plr][1]][0] == 'wolf' and session[1][plr][1] != 'cultist':
                                temp_players.append('**' + get_name(plr) + '** (' + plr + ') (**' + session[1][plr][1] + '**)')
                            elif 'cursed' in session[1][plr][3]:
                                temp_players.append('**' + get_name(plr) + '** (' + plr + ') (**cursed**)')
                            else:
                                temp_players.append('**' + get_name(plr) + '** (' + plr + ')')
                        msg += "Living players: " + ', '.join(temp_players).rstrip(', ') + '\n'
                    elif role == 'shaman':
                        totem = session[1][player][2]
                        msg += "You have the **{0}**. {1}".format(totem.replace('_', ' '), totems[totem]) + '\n'
                    if role in ['seer', 'shaman', 'harlot']:
                        msg += "Living players: " + living_players + '\n'
                    if msg != '':
                        await client.send_message(member, msg)
                except discord.Forbidden:
                    await client.send_message(client.get_channel(GAME_CHANNEL), member.mention + ", you cannot play the game if you block me")
        if session[3][0] == 0:
            first_night = False
        # NIGHT
        session[3][0] = datetime.now()
        await client.send_message(client.get_channel(GAME_CHANNEL), "It is now **nighttime**.")
        while await win_condition() == None and not session[2] and session[0]:
            end_night = True
            for player in list(session[1].keys()):
                if session[1][player][0] and session[1][player][1] in ['seer', 'wolf', 'harlot']:
                    end_night = end_night and (session[1][player][2] != '')
                if session[1][player][0] and session[1][player][1] in ['shaman']:
                    end_night = end_night and (session[1][player][2] in session[1])
            end_night = end_night or (datetime.now() - session[3][0]).total_seconds() > NIGHT_TIMEOUT
            if end_night:
                session[2] = True
            await asyncio.sleep(0.1)
        night_elapsed = datetime.now() - session[3][0]
        session[4][0] += night_elapsed

        # BETWEEN NIGHT AND DAY
        killed_msg = ''
        killed_dict = {}
        for player in list(session[1].keys()):
            killed_dict[player] = 0   
        killed_players = []

        alive_players = [x for x in list(session[1].keys()) if session[1][x][0]]
        if session[0] and await win_condition() == None:
            for player in alive_players:
                role = get_role(player, 'role')
                if role == 'shaman' and session[1][player][2] in totems:
                    totem_target = random.choice([x for x in alive_players if x != player])
                    totem = session[1][player][2]
                    session[1][totem_target][4].append(totem)
                    session[1][player][2] = totem_target
                    await log(0, player + '\'s ' + totem + ' given to ' + totem_target)
                    member = client.get_server(WEREWOLF_SERVER).get_member(player)
                    if member:
                        try:
                            await client.send_message(member, "Because you forgot to give your totem out at night, your **{0}** was randomly given to **{1}**.".format(
                                totem.replace('_', ' '), get_name(totem_target)))
                        except discord.Forbidden:
                            pass
                elif role == 'harlot' and session[1][player][2] == '':
                    member = client.get_server(WEREWOLF_SERVER).get_member(player)
                    if member:
                        try:
                            await client.send_message(member, "You will stay home tonight.")
                            session[1][player][2] = player
                            await log(0, "{0} ({1}) STAY HOME".format(get_name(player), player))
                        except discord.Forbidden:
                            pass

        # Wolf kill
        wolf_votes = {}
        wolf_killed = None
        for player in [x for x in list(session[1].keys()) if session[1][x][0]]:
            if session[1][player][1] == 'wolf':
                if session[1][player][2] in wolf_votes.keys():
                    wolf_votes[session[1][player][2]] += 1
                elif session[1][player][2] != "":
                    wolf_votes[session[1][player][2]] = 1
        if wolf_votes != {}:
            max_votes = max([wolf_votes[x] for x in wolf_votes])
            temp_players = []
            for target in wolf_votes:
                if wolf_votes[target] == max_votes:
                    temp_players.append(target)
            if len(temp_players) == 1:
                wolf_killed = temp_players[0]
                if get_role(wolf_killed, 'role') == 'harlot' and session[1][wolf_killed][2] != wolf_killed:
                    killed_msg += "The wolves' selected victim was not at home last night, and avoided the attack.\n"
                else:
                    killed_dict[temp_players[0]] += 1
            else:
                pass

        # Harlot stuff
        for harlot in [x for x in session[1].keys() if get_role(x, 'role') == 'harlot']:
            visited = session[1][harlot][2]
            if visited != harlot:
                if visited == wolf_killed and not 'protection_totem' in session[1][visited][4]:
                    killed_dict[harlot] += 1
                    killed_msg += "**{}**, a **harlot**, made the unfortunate mistake of visiting the victim's house last night and is now dead.\n".format(get_name(harlot))
                elif visited in [x for x in session[1].keys() if get_role(x, 'role') in ['wolf']]:
                    killed_dict[harlot] += 1
                    killed_msg += "**{}**, a **harlot**, made the unfortunate mistake of visiting a wolf's house last night and is now dead.\n".format(get_name(harlot))

        
        # Totem stuff
        totem_holders = []
        protect_totemed = []
        death_totemed = []
        
        for player in list(session[1].keys()):
            if len([x for x in session[1][player][4] if x in totems.keys()]) > 0:
                totem_holders.append(player)
            killed_dict[player] += session[1][player][4].count('death_totem')
            killed_dict[player] -= session[1][player][4].count('protection_totem')
            if wolf_killed == player and 'protection_totem' in session[1][player][4] and killed_dict[player] < 1:
                protect_totemed.append(player)
            if 'death_totem' in session[1][player][4] and killed_dict[player] > 0:
                death_totemed.append(player)
            session[1][player][4][:] = [x for x in session[1][player][4] if x != 'death_totem' and x != 'protection_totem']
            
        for player in killed_dict.keys():
            if killed_dict[player] > 0:
                killed_players.append(player)

        random.shuffle(killed_players)
        
        for player in killed_players:
            member = client.get_server(WEREWOLF_SERVER).get_member(player)
            if member:
                await client.remove_roles(member, PLAYERS_ROLE)

        killed_temp = killed_players[:]
        
        if protect_totemed != []:
            for protected in protect_totemed:
                killed_msg += "**{0}** was attacked last night, but their totem emitted a brilliant flash of light, blinding their attacker and allowing them to escape.\n".format(
                                    get_name(protected))
        if death_totemed != []:
            for ded in death_totemed:
                killed_msg += "**{0}**'s totem emitted a brilliant flash of light last night. The dead body of **{0}**, a **{1}** was found at the scene.\n".format(
                                    get_name(ded), get_role(ded, 'death'))
                killed_players.remove(ded)
        
        if len(killed_players) == 0:
            if protect_totemed == [] and death_totemed == []:
                killed_msg += random.choice(['The villagers discover the dead body of a beloved penguin pet, but lucklily no one was harmed.',
                                        'Paw prints and tufts of fur are found circling the village, but everyone seems unharmed.'])
        elif len(killed_players) == 1:
            killed_msg += "The dead body of **" + get_name(killed_players[0]) + "**, a **" + get_role(killed_players[0], 'death') + "**, was found. Those remaining mourn the tragedy."
        elif len(killed_players) == 2:
            killed_msg += "The dead bodies of **" + get_name(killed_players[0]) + "**, a **" + get_role(killed_players[0], 'death')
            killed_msg += "**, and **" + get_name(killed_players[1]) + "**, a **" + get_role(killed_players[1], 'death') + "**, were found. Those remaining mourn the tragedy."
        else:
            killed_msg += "The dead bodies of **" + "**, **".join([x + "**, a **" + get_role(x, 'death') for x in killed_players[:-1]]) + "**, and **" + killed_players[-1]
            killed_msg += "**, a **" + get_role(killed_players[-1], 'death') + "**, were found. Those remaining mourn the tragedy."
        if session[0] and await win_condition() == None:
            await client.send_message(client.get_channel(GAME_CHANNEL), "Night lasted **{0:02d}:{1:02d}**. The villagers wake up and search the village.\n\n{2}".format(
                                                                                    night_elapsed.seconds // 60, night_elapsed.seconds % 60, killed_msg))
        if session[0] and await win_condition() == None:
            if len(totem_holders) == 0:
                pass
            elif len(totem_holders) == 1:
                await client.send_message(client.get_channel(GAME_CHANNEL), "**" + get_name(totem_holders[0]) + "** is in possession of a mysterious totem...")
            elif len(totem_holders) == 2:
                await client.send_message(client.get_channel(GAME_CHANNEL), "**" + get_name(totem_holders[0]) + "** and **" + get_name(totem_holders[1]) + "** are in possession of a mysterious totem...")
            else:
                await client.send_message(client.get_channel(GAME_CHANNEL), "**" + "**, **".join([get_name(x) for x in totem_holders[:-1]]) + "**, and **" + get_name(totem_holders[-1]) + "** are in possession of a mysterious totem...")

        for player in killed_temp:
            session[1][player][0] = False
        
        for player in list(session[1].keys()):
            session[1][player][2] = ''
            
        if session[0] and await win_condition() == None:
            await check_traitor()
            
        # DAY
        session[3][1] = datetime.now()
        if session[0] and await win_condition() == None:
            await client.send_message(client.get_channel(GAME_CHANNEL), "It is now **daytime**. Use `{}lynch <player>` to vote to lynch <player>.".format(BOT_PREFIX))

        lynched_player = None
        
        while await win_condition() == None and session[2] and lynched_player == None and session[0]:
            vote_dict = {'abstain' : 0}
            for player in [x for x in session[1] if session[1][x][0]]:
                if session[1][player][2] in vote_dict:
                    vote_dict[session[1][player][2]] += 1
                elif session[1][player][2] not in ['']:
                    vote_dict[session[1][player][2]] = 1
                if 'influence_totem' in session[1][player][4] and session[1][player][2] not in ['']:
                    vote_dict[session[1][player][2]] += 1
            if vote_dict != {}:
                if vote_dict['abstain'] >= len([x for x in session[1] if session[1][x][0]]) / 2:
                    lynched_player = 'abstain'
                max_votes = max([vote_dict[x] for x in vote_dict])
                if max_votes >= len([x for x in session[1] if session[1][x][0]]) // 2 + 1:
                    for voted in vote_dict:
                        if vote_dict[voted] == max_votes:
                            lynched_player = voted
            if (datetime.now() - session[3][1]).total_seconds() > DAY_TIMEOUT:
                session[2] = False
            await asyncio.sleep(0.1)
        day_elapsed = datetime.now() - session[3][1]
        session[4][1] += day_elapsed
        if lynched_player:
            if lynched_player == 'abstain':
                await client.send_message(client.get_channel(GAME_CHANNEL), "The village has agreed to not lynch anyone today.")
            elif 'revealing_totem' in session[1][lynched_player][4]:
                lynched_msg = 'As the villagers prepare to lynch **{0}**, their totem emits a brilliant flash of light! When the villagers are able to see again, '
                lynched_msg += 'they discover that {0} has escaped! The left-behind totem seems to have taken on the shape of a **{1}**.'
                lynched_msg = lynched_msg.format(get_name(lynched_player), get_role(lynched_player, 'role'))
                await client.send_message(client.get_channel(GAME_CHANNEL), lynched_msg)
                session[1][lynched_player][4][:] = [x for x in session[1][lynched_player][4] if x != 'revealing_totem']
            else:
                lynched_msg = random.choice(['The villagers have agreed to lynch **{0}**, a **{1}**.',
                                             'Reluctantly, the villagers lead **{0}** to the gallows, who is later found to be a **{1}**.',
                                             'The villagers sacrifice **{0}** to the belunga god, who is satisfied with the **{1}** for now.',
                                             'For SCIENCE, the villagers throw **{0}** into a volcano. They discover that the melting point of a **{1}** is less than that of lava.',
                                             'The villagers force **{0}** to play Russian Roulette. The town square is stained with the remains of the **{1}**.',
                                             'The villagers, after much debate, finally decide on lynching **{0}**, who turned out to be... a **{1}**.',
                                             'After a prolonged struggle, **{0}** is forced to the gallows, and is discovered after death to be a **{1}**.',
                                             'The villagers choose to hang **{0}**; however, the rope stretches and breaks, and the ensuing fall kills the **{1}**.'])
                lynched_msg = lynched_msg.format(get_name(lynched_player), get_role(lynched_player, 'death'))
                await client.send_message(client.get_channel(GAME_CHANNEL), lynched_msg)
                session[1][lynched_player][0] = False
                member = client.get_server(WEREWOLF_SERVER).get_member(lynched_player)
                if member:
                    await client.remove_roles(member, PLAYERS_ROLE)
        elif lynched_player == None and await win_condition() == None and session[0]:
            await client.send_message(client.get_channel(GAME_CHANNEL), "Not enough votes were cast to lynch a player.")
        # BETWEEN DAY AND NIGHT
        session[2] = False
        if session[0] and await win_condition() == None:
            await client.send_message(client.get_channel(GAME_CHANNEL), "Day lasted **{0:02d}:{1:02d}**. The villagers, exhausted from the day's events, go to bed.".format(
                                                                  day_elapsed.seconds // 60, day_elapsed.seconds % 60))
            for player in list(session[1].keys()):
                session[1][player][4][:] = [x for x in session[1][player][4] if x != 'revealing_totem' and x != 'influence_totem']
                session[1][player][2] = ''
                
        if session[0] and await win_condition() == None:
            await check_traitor()
            
    if session[0]:
        win_msg = await win_condition()
        await end_game(win_msg[1])

async def rate_limit(message):
    if not (message.channel.is_private or message.content.startswith(BOT_PREFIX)) or message.author.id in ADMINS or message.author.id == OWNER_ID:
        return False
    global ratelimit_dict
    global IGNORE_LIST
    if message.author.id not in ratelimit_dict.keys():
        ratelimit_dict[message.author.id] = 1
    else:
        ratelimit_dict[message.author.id] += 1
    if ratelimit_dict[message.author.id] > IGNORE_THRESHOLD:
        if not message.author.id in IGNORE_LIST:
            IGNORE_LIST.append(message.author.id)
            await log(1, message.author.name + " (" + message.author.id + ") was added to the ignore list for rate limiting.")
        try:
            await reply(message, "You've used {0} commands in the last {1} seconds; I will ignore you from now on.".format(IGNORE_THRESHOLD, TOKEN_RESET))
        except discord.Forbidden:
            await client.send_message(client.get_channel(GAME_CHANNEL), message.author.mention +
                                      " used {0} commands in the last {1} seconds and will be ignored from now on.".format(IGNORE_THRESHOLD, TOKEN_RESET))
        finally:
            return True
    if message.author.id in IGNORE_LIST or ratelimit_dict[message.author.id] > TOKENS_GIVEN:
        if ratelimit_dict[message.author.id] > TOKENS_GIVEN:
            await log(1, "Ignoring message from " + message.author.name + " (" + message.author.id + "): `" + message.content + "` since no tokens remaining")
        return True
    return False

async def do_rate_limit_loop():
    await client.wait_until_ready()
    global ratelimit_dict
    while not client.is_closed:
        for user in list(ratelimit_dict.keys()):
            ratelimit_dict[user] = 0
        await asyncio.sleep(TOKEN_RESET)

async def game_start_timeout_loop():
    session[5] = datetime.now()
    while not session[0] and len(session[1].keys()) > 0 and datetime.now() - session[5] < timedelta(seconds=GAME_START_TIMEOUT):
        await asyncio.sleep(0.1)
    if not session[0] and len(session[1].keys()) > 0:
        await client.send_message(client.get_channel(GAME_CHANNEL), "{0}, the game has taken too long to start and has been cancelled. "
                          "If you are still here and would like to start a new game, please do `!join` again.".format(PLAYERS_ROLE.mention))
        session[0] = False
        perms = client.get_channel(GAME_CHANNEL).overwrites_for(client.get_server(WEREWOLF_SERVER).default_role)
        perms.send_messages = True
        await client.edit_channel_permissions(client.get_channel(GAME_CHANNEL), client.get_server(WEREWOLF_SERVER).default_role, perms)
        for player in list(list(session[1].keys())):
            del session[1][player]
            member = client.get_server(WEREWOLF_SERVER).get_member(player)
            if member:
                await client.remove_roles(member, PLAYERS_ROLE)
        session[3] = [0, 0]
        session[4] = [timedelta(0), timedelta(0)]

async def backup_settings_loop():
    while not client.is_closed:
        print("BACKING UP SETTINGS")
        with open(NOTIFY_FILE, 'w') as notify_file:
            notify_file.write(','.join([x for x in notify_me if x != '']))
        await asyncio.sleep(BACKUP_INTERVAL)

############## POST-DECLARATION STUFF ###############
# {command name : [function, permissions [in channel, in pm], description]}
commands = {'shutdown' : [cmd_shutdown, [2, 2], "```\n{0}shutdown takes no arguments\n\nShuts down the bot. Owner-only.```"],
            'ping' : [cmd_ping, [0, 0], "```\n{0}ping takes no arguments\n\nTests the bot\'s responsiveness.```"],
            'eval' : [cmd_eval, [2, 2], "```\n{0}eval <evaluation string>\n\nEvaluates <evaluation string> using Python\'s eval() function and returns a result. Owner-only.```"],
            'exec' : [cmd_exec, [2, 2], "```\n{0}exec <exec string>\n\nExecutes <exec string> using Python\'s exec() function. Owner-only.```"],
            'help' : [cmd_help, [0, 0], "```\n{0}help <command>\n\nReturns hopefully helpful information on <command>. Try {0}list for a listing of commands.```"],
            'list' : [cmd_list, [0, 0], "```\n{0}list takes no arguments\n\nDisplays a listing of commands. Try {0}help <command> for help regarding a specific command.```"],
            'join' : [cmd_join, [0, 1], "```\n{0}join takes no arguments\n\nJoins the game if it has not started yet```"],
            'j' : [cmd_join, [0, 1], "```\nAlias for {0}join.```"],
            'leave' : [cmd_leave, [0, 1], "```\n{0}leave takes no arguments\n\nLeaves the current game. If you need to leave, please do it before the game starts.```"],
            'start' : [cmd_start, [0, 1], "```\n{0}start takes no arguemnts\n\nStarts the game. A game needs at least " + str(MIN_PLAYERS) + " players to start.```"],
            'sync' : [cmd_sync, [1, 1], "```\n{0}sync takes no arguments\n\nSynchronizes all player roles and channel permissions with session.```"],
            'op' : [cmd_op, [1, 1], "```\n{0}op takes no arguments\n\nOps yourself if you are an admin```"],
            'deop' : [cmd_deop, [1, 1], "```\n{0}deop takes no arguments\n\nDeops yourself so you can play with the players ;)```"],
            'fjoin' : [cmd_fjoin, [1, 1], "```\n{0}fjoin <mentions of users>\n\nForces each <mention> to join the game.```"],
            'fleave' : [cmd_fleave, [1, 1], "```\n{0}fleave <mentions of users | all>\n\nForces each <mention> to leave the game. If the parameter is all, removes all players from the game.```"],
            'role' : [cmd_role, [0, 0], "```\n{0}role [<role> | <number of players>]\n\nIf a <role> is given, displays a description of <role>. "
                                        "If a <number of players> is given, displays the quantity of each role for the specified <number of players>. "
                                        "If left blank, displays a list of roles.```"],
            'roles' : [cmd_role, [0, 0], "```\nAlias for {0}role.```"],
            'myrole' : [cmd_myrole, [0, 0], "```\n{0}myrole takes no arguments\n\nTells you your role in pm.```"],
            'stats' : [cmd_stats, [0, 0], "```\n{0}stats takes no arguments\n\nLists current players in the lobby during the join phase, and lists game information in-game.```"],
            'fstop' : [cmd_fstop, [1, 1], "```\n{0}fstop [<-force|reason>]\n\nForcibly stops the current game with an optional [<reason>]. Use {0}fstop -force if "
                                          "bot errors.```"],
            'revealroles' : [cmd_revealroles, [2, 1], "```\n{0}revealroles takes no arguments\n\nDisplays what each user's roles are and sends it in pm.```"],
            'see' : [cmd_see, [2, 0], "```\n{0}see <player>\n\nIf you are a seer, uses your power to detect <player>'s role.```"],
            'kill' : [cmd_kill, [2, 0], "```\n{0}kill <player>\n\nIf you are a wolf, casts your vote to target <player>.```"],
            'lynch' : [cmd_lynch, [0, 2], "```\n{0}lynch [<player>]\n\nVotes to lynch [<player>] during the day. If no arguments are given, replies with a list of current votes.```"],
            'retract' : [cmd_retract, [0, 0], "```\n{0}retract takes no arguments\n\nRetracts your vote to lynch or kill.```"],
            'votes' : [cmd_votes, [0, 0], "```\n{0}votes takes no arguments\n\nDisplays current votes to lynch.```"],
            'abstain' : [cmd_abstain, [0, 2], "```\n{0}abstain takes no arguments\n\nRefrain from voting someone today.```"],
            'abs' : [cmd_abstain, [0, 2], "```\nAlias for {0}abstain.```"],
            'nl' : [cmd_abstain, [0, 2], "```\nAlias for {0}abstain.```"],
            'v' : [cmd_lynch, [0, 2], "```\nAlias for {0}lynch.```"],
            'r' : [cmd_retract, [0, 0], "```\nAlias for {0}retract.```"],
            'coin' : [cmd_coin, [0, 0], "```\n{0}coin takes no arguments\n\nFlips a coin. Don't use this for decision-making, especially not for life or death situations.```"],
            'admins' : [cmd_admins, [0, 0], "```\n{0}admins takes no arguments\n\nLists online/idle admins if used in pm, and **alerts** online/idle admins if used in channel (**USE ONLY WHEN NEEDED**).```"],
            'fday' : [cmd_fday, [1, 2], "```\n{0}fday takes no arguments\n\nForces night to end.```"],
            'fnight' : [cmd_fnight, [1, 2], "```\n{0}fnight takes no arguments\n\nForces day to end.```"],
            'fstart' : [cmd_fstart, [1, 2], "```\n{0}fstart takes no arguments\n\nForces game to start.```"],
            'frole' : [cmd_frole, [1, 2], "```\n{0}frole <player> <role>\n\nSets <player>'s role to <role>.```"],
            'force' : [cmd_force, [1, 2], "```\n{0}force <player> <target>\n\nSets <player>'s target flag (session[1][player][2]) to <target>.```"],
            'session' : [cmd_session, [2, 1], "```\n{0}session takes no arguments\n\nReplies with the contents of the session variable in pm for debugging purposes. Admin only.```"],
            'time' : [cmd_time, [0, 0], "```\n{0}time takes no arguments\n\nChecks in-game time.```"],
            't' : [cmd_time, [0, 0], "```\nAlias for {0}time.```"],
            'give' : [cmd_give, [2, 0], "```\n{0}give <player>\n\nIf you are a shaman, gives your totem to <player>. You can see your totem by using `myrole` in pm.```"],
            'info' : [cmd_info, [0, 0], "```\n{0}info takes no arguments\n\nGives information on how the game works.```"],
            'notify_role' : [cmd_notify_role, [0, 0], "```\n{0}notify_role [<true|false>]\n\nGives or take the " + WEREWOLF_NOTIFY_ROLE_NAME + " role.```"],
            'ignore' : [cmd_ignore, [1, 1], "```\n{0}ignore <add|remove|list> <user>\n\nAdds or removes <user> from the ignore list, or outputs the ignore list.```"],
            'notify' : [cmd_notify, [0, 0], "```\n{0}notify [<true|false>]\n\nNotifies all online users who want to be notified, or adds/removes you from the notify list.```"],
            'online' : [cmd_online, [1, 1], "```\n{0}online takes no arguments\n\nNotifies all online users.```"],
            'getrole' : [cmd_getrole, [2, 2], "```\n{0}getrole <player> <revealtype>\n\nTests get_role command.```"],
            'visit' : [cmd_visit, [2, 0], "```\n{0}visit <player>\n\nIf you are a harlot, visits <player>. You can stay home by visiting yourself. "
                                          "You will die if you visit a wolf or the victim of the wolves.```"],
            'test' : [cmd_test, [1, 0], "test"]}

COMMANDS_FOR_ROLE = {'see' : 'seer',
                     'kill' : 'wolf',
                     'give' : 'shaman',
                     'visit' : 'harlot'}

# {role name : [team, plural, description, [# players config]
#                   4, 5, 6, 7, 8, 9, 10,11,12,13,14,15,16

##roles = {'wolf' : ['wolf', 'wolves', "Your job is to kill all of the villagers. Type `kill <player>` in private message to kill them.",
##                   [1, 1, 1, 1, 1, 2,  2, 2, 2, 2, 2, 2, 2]],
##         'villager' : ['village', 'villagers', "Your job is to lynch all of the wolves.",
##                   [2, 3, 3, 3, 3, 4,  5, 4, 4, 5, 6, 6, 6]],
##         'cursed villager' : ['village', 'cursed villagers', "You are a villager but are seen by the seer as a wolf, due to being cursed.",
##                   [0, 0, 1, 1, 1, 1,  2, 2, 2, 2, 2, 2, 2]],
##         'seer' : ['village', 'seers', "Your job is to detect the wolves; you may have a vision once per night. Type `see <player>` in private message to see their role.",
##                   [1, 1, 1, 1, 1, 1,  1, 1, 1, 1, 1, 1, 2]],
##         'gunner' : ['village', 'gunners', "Your job is to eliminate the wolves. Type `{0}shoot <player` in channel during the day to shoot them.",
##                   [0, 0, 0, 0, 1, 1,  1, 1, 1, 2, 2, 2, 2]],
##         'cultist' : ['wolf', 'cultists', "Your job is to help the wolves kill all of the villagers.",
##                   [0, 0, 0, 1, 0, 0,  0, 0, 1, 0, 0, 1, 0]],
##         'traitor' : ['wolf', 'traitors', "You appear as a villager to the seer, but you are part of the wolf team. Once all other wolves die, you will turn into a wolf.",
##                   [0, 0, 0, 0, 1, 0,  1, 1, 1, 1, 1, 1, 2]]}
#                   4, 5, 6, 7, 8, 9, 10,11,12,13,14,15,16
roles = {'wolf' : ['wolf', 'wolves', "Your job is to kill all of the villagers. Type `kill <player>` in private message to kill them.",
                   [1, 1, 1, 1, 1, 1,  1, 1, 2, 2, 2, 2, 2]],
         'villager' : ['village', 'villagers', "Your job is to lynch all of the wolves.",
                   [2, 3, 3, 2, 2, 3,  3, 4, 5, 5, 5, 5, 5]],
         'seer' : ['village', 'seers', "Your job is to detect the wolves; you may have a vision once per night. Type `see <player>` in private message to see their role.",
                   [1, 1, 1, 1, 1, 1,  1, 1, 1, 2, 2, 2, 2]],
         'cursed villager' : ['village', 'cursed villagers', "This template is a villager but is seen by the seer as a wolf. Roles normally seen as wolf and the seer cannot be cursed.",
                   [0, 0, 1, 1, 1, 1,  1, 1, 1, 1, 2, 2, 2]],
         'shaman' : ['village', 'shamans', "You can select a player to receive a totem each night by using `give <player>`. You may give a totem to yourself, but you may not give the same"
                                           " person a totem two nights in a row. If you do not give the totem to anyone, it will be given to a random player.",
                   [0, 0, 0, 1, 1, 1,  1, 1, 1, 1, 1, 2, 2]],
         'cultist' : ['wolf', 'cultists', "Your job is to help the wolves kill all of the villagers.",
                   [0, 0, 0, 1, 0, 0,  1, 1, 0, 0, 0, 0, 1]],
         'traitor' : ['wolf', 'traitors', "You appear as a villager to the seer, but you are part of the wolf team. Once all other wolves die, you will turn into a wolf.",
                   [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 1, 1]],
         'harlot' : ['village', 'harlots', "You may spend the night with one player each night by using `visit <player>`. If you visit a victim of a wolf, or visit a wolf, "
                                           "you will die. You may visit yourself to stay home.",
                   [0, 0, 0, 0, 1, 1,  1, 1, 1, 1, 1, 1, 1]]}
VILLAGE_ROLES_ORDERED = ['seer', 'shaman', 'harlot', 'villager']
WOLF_ROLES_ORDERED = ['wolf', 'traitor', 'cultist']
NEUTRAL_ROLES_ORDERED = []
TEMPLATES_ORDERED = ['cursed villager']
totems = {'death_totem' : 'The player who is given this totem will die tonight.',
          'protection_totem': 'The player who is given this totem is protected from dying tonight.',
          'revealing_totem': 'If the player who is given this totem is lynched, their role is revealed to everyone instead of them dying.',
          'influence_totem': 'Votes by the player who is given this totem count twice.'}
ROLES_SEEN_VILLAGER = ['villager', 'seer', 'traitor', 'cultist']
ROLES_SEEN_WOLF = ['wolf', 'cursed']
WOLFCHAT_ROLES = ['wolf', 'traitor']

########### END POST-DECLARATION STUFF #############
client.loop.create_task(do_rate_limit_loop())
client.loop.create_task(backup_settings_loop())
client.run(TOKEN)
