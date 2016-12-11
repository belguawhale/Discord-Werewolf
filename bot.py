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
session = [False, {}, False, [0, 0], [timedelta(0), timedelta(0)]]
PLAYERS_ROLE = None
ADMINS_ROLE = None
random.seed(datetime.now())
################### END INIT ######################

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')
    await log(0, 'on_ready triggered!')
    # [playing : True | False, players : {player id : [alive, role, action, template]}, day?, [datetime night, datetime day], [elapsed night, elapsed day]]
    for role in client.get_server(WEREWOLF_SERVER).role_hierarchy:
        if role.name == PLAYERS_ROLE_NAME:
            global PLAYERS_ROLE
            PLAYERS_ROLE = role
        if role.name == ADMINS_ROLE_NAME:
            global ADMINS_ROLE
            ADMINS_ROLE = role
    if PLAYERS_ROLE:
        await log(0, "Players role id: " + PLAYERS_ROLE.id)
    else:
        await log(2, "Could not find players role " + PLAYERS_ROLE_NAME)
    if ADMINS_ROLE:
        await log(0, "Admins role id: " + ADMINS_ROLE.id)
    else:
        await log(2, "Could not find admins role " + ADMINS_ROLE_NAME)

@client.event
async def on_message(message):
    if message.author.id in [client.user.id] or not client.get_server(WEREWOLF_SERVER).get_member(message.author.id):
        return
    #print(message.content.strip())
    if message.channel.is_private:
        await log(0, 'pm from ' + message.author.name + ' (' + message.author.id + '): ' + message.content)
        if session[0] and message.author.id in session[1].keys():
            if roles[session[1][message.author.id][1]][0] == 'wolf' and session[1][message.author.id][0]:
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
        await reply(message, cmd_eval.__doc__)
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
        await reply(message, cmd_exec.__doc__)
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
    if message.author.id in list(session[1].keys()):
        await reply(message, "You are already playing!")
    else:
        session[1][message.author.id] = [True, '', '', '']
        await client.send_message(message.channel, "**" + message.author.name + "** joined the game.")
        await client.add_roles(client.get_server(WEREWOLF_SERVER).get_member(message.author.id), PLAYERS_ROLE)
        await player_idle(message)

async def cmd_leave(message, parameters):
    if session[0] and message.author.id in list(session[1].keys()) and session[1][message.author.id][0]:
        session[1][message.author.id][0] = False
        await client.send_message(client.get_channel(GAME_CHANNEL), "**" + message.author.name + "** spontaneously combusted. The air smells of freshly burnt **" + session[1][message.author.id][1] + "**.")
        await client.remove_roles(client.get_server(WEREWOLF_SERVER).get_member(message.author.id), PLAYERS_ROLE)
    else:
        if message.author.id in list(session[1].keys()):
            del session[1][message.author.id]
            await client.send_message(client.get_channel(GAME_CHANNEL), "**" + message.author.name + "** left the game.")
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
        session[1][member] = [True, '', '', '']
        join_msg += "**" + join_names[i] + "** was forced to join the game.\n"
        if client.get_server(WEREWOLF_SERVER).get_member(member):
            await client.add_roles(client.get_server(WEREWOLF_SERVER).get_member(member), PLAYERS_ROLE)
    await client.send_message(message.channel, join_msg)

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
                if client.get_server(WEREWOLF_SERVER).get_member(member.strip('<!@>')):
                    leave_list.append(member.strip('<!@>'))
                else:
                    leave_list.append(member.strip('<!@>'))
    if leave_list == []:
        await reply(message, "ERROR: no valid mentions found")
        return
    leave_msg = ""
    for i, member in enumerate(leave_list):
        if member in list(session[1].keys()):
            if session[0]:
                session[1][member][0] = False
                leave_msg += "**" + get_name(member) + "** was forcibly shoved into a fire. The air smells of freshly burnt **" + session[1][member][1] + "**.\n"
            else:
                del session[1][member]
                leave_msg += "**" + get_name(member) + "** was forced to leave the game.\n"
            if client.get_server(WEREWOLF_SERVER).get_member(member):
                await client.remove_roles(client.get_server(WEREWOLF_SERVER).get_member(member), PLAYERS_ROLE)
    await client.send_message(client.get_channel(GAME_CHANNEL), leave_msg)

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
        await run_game(message)

async def cmd_fstop(message, parameters):
    if not session[0]:
        await reply(message, "There is no currently running game!")
        return
    msg = "Game forcibly stopped by **" + message.author.name + "**"
    if parameters == "":
        msg += "."
    else:
        msg += " for reason: `" + parameters + "`."

    role_msg = ""
    role_dict = {}
    for role in roles.keys():
        role_dict[role] = []
    for player in list(session[1].keys()):
        role_dict[session[1][player][1]].append(get_name(player))
        if session[1][player][3] == 'cursed':
            role_dict['cursed villager'].append(get_name(player))
    for key in role_dict.keys():
        value = role_dict[key]
        if len(value) == 0:
            pass
        elif len(value) == 1:
            role_msg += "The **" + key + "** was **" + value[0] + "**. "
        elif len(value) == 2:
            role_msg += "The **" + roles[key][1] + "** were **" + value[0] + "** and **" + value[1] + "**. "
        else:
            role_msg += "The **" + roles[key][1] + "** were **" + "**, **".join(value[:-1]) + "**, and **" + value[-1] + "**. "
            
    await end_game(msg + '\n\n' + role_msg)
        

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
        await reply(message, "Roles: " + ", ".join(list(roles.keys())).rstrip(', '))
    elif parameters == "" and session[0]:
        msg = "**" + str(len(list(session[1].keys()))) + "** players playing:```\n"
        for role in roles.keys():
            if roles[role][3][len(list(session[1].keys())) - MIN_PLAYERS] > 0:
                msg += role + ": " + str(roles[role][3][len(list(session[1].keys())) - MIN_PLAYERS]) + '\n'
        msg += '```'
        await reply(message, msg)
    elif parameters in roles.keys():
        await reply(message, "```\nRole name: " + parameters + "\nSide: " + roles[parameters][0] + "\nDescription: " + roles[parameters][2] + "```")
    elif parameters.isdigit():
        if int(parameters) in range(MIN_PLAYERS, MAX_PLAYERS + 1):
            msg = "```\n"
            for role in roles.keys():
                if roles[role][3][int(parameters) - MIN_PLAYERS] > 0:
                    msg += role + ": " + str(roles[role][3][int(parameters) - MIN_PLAYERS]) + '\n'
            msg += '```'
            await reply(message, msg)
        else:
            await reply(message, "Please choose a number of players between " + str(MIN_PLAYERS) + " and " + str(MAX_PLAYERS) + ".")
    else:
        await reply(message, "Could not find role named " + parameters)

async def cmd_myrole(message, parameters):
    if session[0]:
        player = message.author.id
        member = client.get_server(WEREWOLF_SERVER).get_member(player)
        if member and session[1][player][0]:
            role = session[1][player][1]
            try:
                await client.send_message(member, "Your role is **" + role + "**. " + roles[role][2])
                if roles[role][0] == 'wolf':
                    temp_players = []
                    for plr in [x for x in session[1].keys() if session[1][x][0]]:
                        if roles[session[1][plr][1]][0] == 'wolf':
                            temp_players.append('**' + get_name(plr) + '** (' + plr + ') (**' + session[1][plr][1] + '**)')
                        elif session[1][plr][3] == 'cursed':
                            temp_players.append('**' + get_name(plr) + '** (' + plr + ') (**cursed**)')
                        else:
                            temp_players.append('**' + get_name(plr) + '** (' + plr + ')')
                    await client.send_message(member, "Players still alive: " + ', '.join(temp_players).rstrip(', '))
                elif role == 'seer':
                    temp_players = []
                    for plr in [x for x in session[1].keys() if session[1][x][0]]:
                        temp_players.append('**' + get_name(plr) + '** (' + plr + ')')
                    await client.send_message(member, "Players still alive: " + ', '.join(temp_players).rstrip(', '))
            except:
                await client.send_message(client.get_channel(GAME_CHANNEL), member.mention + ", you cannot play the game if you block me")

async def cmd_stats(message, parameters):
    if session[0]:
        reply_msg = "It is now **" + ("day" if session[2] else "night") + "time**."
        reply_msg += "\n**" + str(len(session[1].keys())) + "** players playing: **" + str(len([x for x in session[1].keys() if session[1][x][0]])) + "** alive, "
        reply_msg += "**" + str(len([x for x in session[1].keys() if not session[1][x][0]])) + "** dead\n"
        reply_msg += "```\nLiving players: " + ", ".join(sorted([get_name(x) + ' (' + x + ')' for x in list(session[1].keys()) if session[1][x][0]])).rstrip(", ") + '\n'
        reply_msg += "Dead players: " + ", ".join(sorted([get_name(x) + ' (' + x + ')' for x in list(session[1].keys()) if not session[1][x][0]])).rstrip(", ") + '\n'
        role_dict = {}
        for role in roles.keys():
            role_dict[role] = 0
        for player in list(session[1].keys()):
            if session[1][player][0]:
                role_dict[session[1][player][1]] += 1
        reply_msg += "Total roles: " + ", ".join(sorted([x + ": " + str(roles[x][3][len(session[1].keys()) - MIN_PLAYERS]) for x in roles.keys() if roles[x][3][len(session[1].keys()) - MIN_PLAYERS] > 0])).rstrip(", ") + '\n'
        reply_msg += "Remaining roles: " + ", ".join(sorted([x + ": " + str(role_dict[x]) for x in role_dict.keys() if role_dict[x] > 0])).rstrip(", ") + "```"
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
            await client.send_message(message.channel, str(len(list(session[1].keys()))) + " players in lobby: ```\n" + "\n".join(sorted(formatted_list)).rstrip("\n") + "```")

async def cmd_revealroles(message, parameters):
    msg = "```\n"
    for player in sorted(list(list(session[1].keys()))):
        msg += get_name(player) + ' (' + player + '): ' + session[1][player][3] + " " + session[1][player][1] + "\n"
    msg += "```"
    await client.send_message(message.channel, msg)

async def cmd_see(message, parameters):
    if not session[0] or session[1][message.author.id][1] != 'seer' or not session[1][message.author.id][0] or session[2]:
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
                    await reply(message, "Player **" + get_player(player) + "** is dead!")
                else:
                    session[1][message.author.id][2] = player
                    # (SAVE FOR DETECTIVE) await reply(message, "You have a vision... in your vision you see that **" + get_name(player) + "** is a **" + session[1][player][1] + "**!")
                    seen_role = ''
                    if session[1][player][1] in ROLES_SEEN_WOLF or session[1][player][3] in ROLES_SEEN_WOLF:
                        seen_role = 'wolf'
                    elif session[1][player][1] in ROLES_SEEN_VILLAGER or session[1][player][3] in ROLES_SEEN_VILLAGER:
                        seen_role = 'villager'
                    else:
                        seen_role = session[1][player][1]
                    await reply(message, "You have a vision... in your vision you see that **" + get_name(player) + "** is a **" + seen_role + "**!")
            else:        
                await reply(message, "Could not find player " + parameters)
    
async def cmd_kill(message, parameters):
    if not session[0] or session[1][message.author.id][1] != 'wolf' or not session[1][message.author.id][0] or session[2]:
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
                elif player in [x for x in list(session[1].keys()) if roles[session[1][x][1]][0] == 'wolf']:
                    await reply(message, "You can't kill another wolf.")
                elif player in [x for x in list(session[1].keys()) if not session[1][x][0]]:
                    await reply(message, "Player **" + get_player(player) + "** is dead!")
                else:
                    session[1][message.author.id][2] = player
                    await reply(message, "You have chosen to kill **" + get_name(player) + "**.")
            else:        
                await reply(message, "Could not find player " + parameters)

async def cmd_lynch(message, parameters):
    if not session[0] or not session[2]:
        return
    if parameters == "":
        reply_msg = "Current votes: (**" + str(int(len([x for x in list(session[1].keys()) if session[1][x][0]]) / 2) + 1) + "** votes required to lynch)```\n"
        vote_dict = {}
        for player in list(session[1].keys()):
            if session[1][player][2] in vote_dict:
                vote_dict[session[1][player][2]].append(get_name(player) + ' (' + player + ')')
            elif session[1][player][2] != '':
                vote_dict[session[1][player][2]] = [get_name(player) + ' (' + player + ')']
        if vote_dict == {}:
            reply_msg = "No one has cast a vote to lynch yet. Do `{}lynch <player>` in #{} to lynch <player>. ".format(BOT_PREFIX, client.get_channel(GAME_CHANNEL).name)
            reply_msg += "**{}** votes are required to lynch.".format(str(int(len([x for x in list(session[1].keys()) if session[1][x][0]]) / 2) + 1))
        else:
            for voted in vote_dict.keys():
                reply_msg += get_name(voted) + ' (' + voted + ') (' + str(len(vote_dict[voted])) + " votes): " + ', '.join(vote_dict[voted]).rstrip(", ") + "\n"
            reply_msg += "```"
        await reply(message, reply_msg)
##    elif parameters in [get_name(x) for x in list(session[1].keys()) if session[1][x][0]]:
##        player = ""
##        for x in list(session[1].keys()):
##            if get_name(x) == parameters:
##                player = x
##        if player == "":
##            await reply(message, "??? (report to admins pls)")
##        else:
##            session[1][message.author.id][2] = player
##            await reply(message, "You have voted to lynch **" + get_name(player) + "**.")
##    elif parameters.strip("<!@>") in [x for x in list(session[1].keys()) if session[1][x][0]]:
##        parameters = parameters.strip("<!@>")
##        session[1][message.author.id][2] = parameters
##        await reply(message, "You have voted to lynch **" + get_name(parameters) + "**.")
##    elif parameters.strip("<!@>") in [x for x in list(session[1].keys()) if not session[1][x][0]] or parameters in [get_name(x) for x in list(session[1].keys()) if not session[1][x][0]]:
##        await reply(message, "Player **" + parameters + "** is dead!")
    else:
        to_lynch = get_player(parameters.split(' ', 1)[0])
        if not to_lynch:
            to_lynch = get_player(parameters)
        if to_lynch:
            if to_lynch in [x for x in list(session[1].keys()) if not session[1][x][0]]:
                await reply(message, "Player **" + get_name(to_lynch) + "** is dead!")
            else:
                session[1][message.author.id][2] = to_lynch
                await reply(message, "You have voted to lynch **" + get_name(to_lynch) + "**.")
        else:
            await reply(message, "Could not find player " + parameters)
            
async def cmd_retract(message, parameters):
    if not session[0] or not session[1][message.author.id][0] or not session[2] or session[1][message.author.id][2] == '':
        return
    session[1][message.author.id][2] = ''
    await reply(message, "You retracted your vote.")

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
    available = []
    for admin in ADMINS:
        admin_member = client.get_server(WEREWOLF_SERVER).get_member(admin)
        if admin_member:
            if admin_member.status in [discord.Status.online, discord.Status.idle]:
                available.append(admin_member)
    await reply(message, 'Available admins: ' + ', '.join([x.mention for x in available]).rstrip(', '))

async def cmd_fday(message, parameters):
    if session[0] and not session[2]:
        session[2] = True
        await reply(message, ":thumbsup:")

async def cmd_fnight(message, parameters):
    if session[0] and session[2]:
        session[2] = False
        await reply(message, ":thumbsup:")

async def cmd_frole(message, parameters):
    if not session[0] or parameters == '':
        return
    player = parameters.split(' ')[0]
    role = parameters.split(' ', 1)[1]
    temp_player = get_player(player)
    if temp_player:
        if role in roles.keys() or role == 'cursed':
            session[1][temp_player][1] = role
            if role in ['cursed villager', 'cursed']:
                session[1][temp_player][1] = 'villager'
                session[1][temp_player][3] = 'cursed'
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
    target = parameters.split(' ', 1)[1]
    temp_player = get_player(player)
    if temp_player:
        session[1][temp_player][2] = target
        await reply(message, "Successfully set **{}**'s target to **{}**.".format(get_name(temp_player), target))
    else:
        await reply(message, "Cannot find player named **" + player + "**")

async def cmd_session(message, parameters):
    await client.send_message(message.author, "```py\n{}\n```".format(str(session)))

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

async def cmd_rules(message, parameters):
    pass

async def cmd_info(message, parameters):
    pass

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
                    await reply(message, "Please use command " + commandname + " in private message.")
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

async def assign_roles():
    massive_role_list = []
    for role in roles.keys():
        for i in range(roles[role][3][len(list(list(session[1].keys()))) - MIN_PLAYERS]):
            massive_role_list.append(role)
    random.shuffle(massive_role_list)
    for player in list(session[1].keys()):
        session[1][player][1] = massive_role_list.pop()
        if session[1][player][1] == 'cursed villager':
            session[1][player][1] = 'villager'
            session[1][player][3] = 'cursed'

async def end_game(reason):
    if not session[0]:
        return
    session[0] = False
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

async def win_condition():
    teams = {'village' : 0, 'wolf' : 0}
    for player in list(session[1].keys()):
        if session[1][player][0]:
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

    role_msg = ""
    role_dict = {}
    for role in roles.keys():
        role_dict[role] = []
    for player in list(session[1].keys()):
        role_dict[session[1][player][1]].append(get_name(player))
        if session[1][player][3] == 'cursed':
            role_dict['cursed villager'].append(get_name(player))
    for key in role_dict.keys():
        value = role_dict[key]
        if len(value) == 0:
            pass
        elif len(value) == 1:
            role_msg += "The **" + key + "** was **" + value[0] + "**. "
        elif len(value) == 2:
            role_msg += "The **" + roles[key][1] + "** were **" + value[0] + "** and **" + value[1] + "**. "
        else:
            role_msg += "The **" + roles[key][1] + "** were **" + "**, **".join(value[:-1]) + "**, and **" + value[-1] + "**. "
    
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
    return [win_team, win_lore + '\n\n' + role_msg + '\n\n' + win_msg]

def get_name(player):
    member = client.get_server(WEREWOLF_SERVER).get_member(player)
    if member:
        return str(member.name)
    else:
        return str(player)

##def get_player(string):
##    temp_list = []
##    for player in list(session[1].keys()):
##        if get_name(player).lower().startswith(string.lower()) or string.strip("<!@>") == player:
##            temp_list.append(player)
##    if len(temp_list) == 1:
##        return temp_list[0]
##    elif temp_list == []:
##        return None
##    else:
##        return False

def get_player(string):
    string = string.lower()
    users = []
    discriminators = []
    nicks = []
    for player in list(session[1].keys()):
        if string == player.lower() or string.strip('<@!>') == player:
            return player
        member = client.get_server(WEREWOLF_SERVER).get_member(player)
        if member:
            if member.name.lower().startswith(string):
                users.append(player)
            if string.strip('#') == member.discriminator:
                discriminators.append(player)
            if member.display_name.startswith(string):
                nicks.append(player)
        elif get_player(player).lower().startswith(string):
            users.append(player)
    if len(users) == 1:
        return users[0]
    if len(discriminators) == 1:
        return discriminators[0]
    if len(nicks) == 1:
        return nicks[0]
    return None

async def wolfchat(message):
    for wolf in [x for x in session[1].keys() if x != message.author.id and roles[session[1][x][1]][0] == 'wolf' and client.get_server(WEREWOLF_SERVER).get_member(x)]:
        try:
            await client.send_message(client.get_server(WEREWOLF_SERVER).get_member(wolf), "**[Wolfchat]** message from **" + message.author.name + "**: " + message.content)
        except:
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
            await client.send_message(message.author, "**You have been idling in " + client.get_channel(GAME_CHANNEL).name + " for a while. Please say something soon or you might be declared dead.**")
            msg = await client.wait_for_message(author=message.author, channel=client.get_channel(GAME_CHANNEL), timeout=60, check=check)
            if msg == None and message.author.id in session[1].keys() and session[0] and session[1][message.author.id][0]:
                await client.send_message(client.get_channel(GAME_CHANNEL), "**" + get_name(message.author.id) + "** didn't get out of bed for a very long time and has been found dead. "
                                                                            "The survivors bury the **" + session[1][message.author.id][3] + ' ' + session[1][message.author.id][1] + '**.')
                session[1][message.author.id][0] = False
                await client.remove_roles(client.get_server(WEREWOLF_SERVER).get_member(message.author.id), PLAYERS_ROLE)

async def run_game(message):
    session[0] = True
    session[2] = False
    perms = client.get_channel(GAME_CHANNEL).overwrites_for(client.get_server(WEREWOLF_SERVER).default_role)
    perms.send_messages = False
    await client.edit_channel_permissions(client.get_channel(GAME_CHANNEL), client.get_server(WEREWOLF_SERVER).default_role, perms)
    await client.send_message(client.get_channel(GAME_CHANNEL), PLAYERS_ROLE.mention + ", werewolf game is starting now! All players check their PMs for their role. "
                                                 "If you did not receive a pm, please let " + client.get_server(WEREWOLF_SERVER).get_member(OWNER_ID).name + " know.")
    await assign_roles()
    await log(0, str(session))
    # GAME START
    while await win_condition() == None and session[0]:
        for player in session[1].keys():
            member = client.get_server(WEREWOLF_SERVER).get_member(player)
            if member and session[1][player][0]:
                try:
                    role = session[1][player][1]
                    await client.send_message(member, "Your role is **" + role + "**. " + roles[role][2])
                    if roles[role][0] == 'wolf':
                        temp_players = []
                        for plr in [x for x in session[1].keys() if session[1][x][0]]:
                            if roles[session[1][plr][1]][0] == 'wolf':
                                temp_players.append('**' + get_name(plr) + '** (' + plr + ') (**' + session[1][plr][1] + '**)')
                            elif session[1][plr][3] == 'cursed':
                                temp_players.append('**' + get_name(plr) + '** (' + plr + ') (**cursed**)')
                            else:
                                temp_players.append('**' + get_name(plr) + '** (' + plr + ')')
                        await client.send_message(member, "Players still alive: " + ', '.join(temp_players).rstrip(', '))
                    elif role == 'seer':
                        temp_players = []
                        for plr in [x for x in session[1].keys() if session[1][x][0]]:
                            temp_players.append('**' + get_name(plr) + '** (' + plr + ')')
                        await client.send_message(member, "Players still alive: " + ', '.join(temp_players).rstrip(', '))
                except:
                    await client.send_message(client.get_channel(GAME_CHANNEL), member.mention + ", you cannot play the game if you block me")
                    
        # NIGHT
        session[3][0] = datetime.now()
        await client.send_message(client.get_channel(GAME_CHANNEL), "It is now **nighttime**.")
        while await win_condition() == None and not session[2] and session[0]:
            end_night = True
            for player in list(session[1].keys()):
                if session[1][player][0] and session[1][player][1] in ['seer', 'wolf']:
                    end_night = end_night and (session[1][player][2] != '')
            end_night = end_night or (datetime.now() - session[3][0]).total_seconds() > NIGHT_TIMEOUT
            if end_night:
                session[2] = True
            await asyncio.sleep(0.1)
        night_elapsed = datetime.now() - session[3][0]
        session[4][0] += night_elapsed
        # BETWEEN NIGHT AND DAY
##            leave_players = []
##            for player in list(session[1].keys()):
##                if session[1][player][2] == 'leave':
##                    leave_players.append(player)
##                    del session[1][player]
##
##            if leave_players != []:
##                await client.send_message(client.get_channel(GAME_CHANNEL), "**" + "**, **".join([get_name(x) for x in leave_players]).rstrip("**, **") + "** spontaneously combusted.")
            
        killed_dict = {}
        for player in list(session[1].keys()):
            if session[1][player][1] == 'wolf':
                if session[1][player][2] in killed_dict:
                    killed_dict[session[1][player][2]] += 1
                elif session[1][player][2] != "":
                    killed_dict[session[1][player][2]] = 1
        killed_players = []
        if killed_dict != {}:
            max_votes = max([killed_dict[x] for x in killed_dict])
            temp_players = []
            for dead in killed_dict:
                if killed_dict[dead] == max_votes:
                    temp_players.append(dead)
            if len(temp_players) == 1:
                killed_players.append(temp_players[0])
            else:
                pass

        for player in killed_players:
            member = client.get_server(WEREWOLF_SERVER).get_member(player)
            if member:
                await client.remove_roles(member, PLAYERS_ROLE)
            session[1][player][0] = False
        
        if len(killed_players) == 0:
            killed_msg = random.choice(['The villagers discover the dead body of a beloved penguin pet, but lucklily no one was harmed.',
                                        'Paw prints and tufts of fur are found circling the village, but everyone seems unharmed.'])
        elif len(killed_players) == 1:
            killed_msg = "The dead body of **" + get_name(killed_players[0]) + "**, a **" + session[1][killed_players[0]][1] + "**, was found."
        elif len(killed_players) == 2:
            killed_msg = "The dead bodies of **" + get_name(killed_players[0]) + "**, a **" + session[1][killed_players[0]][1]
            killed_msg += "**, and **" + get_name(killed_players[0]) + "**, a **" + session[1][killed_players[1]][1] + "**, were found."
        else:
            killed_msg = "The dead bodies of **" + "**, **".join([x + "**, a **" + session[1][x][1] for x in killed_players[:-1]]) + "**, and **" + killed_players[-1]
            killed_msg += "**, a **" + session[1][killed_players[-1]][1] + "**, were found."
        if session[0] and await win_condition() == None:
            await client.send_message(client.get_channel(GAME_CHANNEL), "Night lasted **{0:02d}:{1:02d}**. The villagers wake up and search the village.\n\n{2}".format(
                                                                                    night_elapsed.seconds // 60, night_elapsed.seconds % 60, killed_msg))
            

        for player in list(session[1].keys()):
            session[1][player][2] = ''
        # DAY
        session[3][1] = datetime.now()
        if session[0] and await win_condition() == None:
            await client.send_message(client.get_channel(GAME_CHANNEL), "It is now **daytime**. Use `{}lynch <player>` to vote to lynch <player>.".format(BOT_PREFIX))

        lynched_player = None
        
        while await win_condition() == None and session[2] and lynched_player == None and session[0]:
            vote_dict = {}
            for player in [x for x in session[1].keys() if session[1][x][0]]:
                if session[1][player][2] in vote_dict:
                    vote_dict[session[1][player][2]] += 1
                elif session[1][player][2] not in ['', 'leave']:
                    vote_dict[session[1][player][2]] = 1
            if vote_dict != {}:
                max_votes = max([vote_dict[x] for x in vote_dict])
                if max_votes >= int(len([x for x in list(session[1].keys()) if session[1][x][0]]) / 2) + 1:
                    for voted in vote_dict:
                        if vote_dict[voted] == max_votes:
                            lynched_player = voted
            if (datetime.now() - session[3][1]).total_seconds() > DAY_TIMEOUT:
                session[2] = False
            await asyncio.sleep(0.1)
        day_elapsed = datetime.now() - session[3][1]
        session[4][1] += day_elapsed
        if lynched_player:
            lynched_msg = random.choice(['The villagers have agreed to lynch **{0}**, a **{1}**.',
                                         'Reluctantly, the villagers lead **{0}** to the gallows, who is later found to be a **{1}**.',
                                         'The villagers sacrifice **{0}** to the belunga god, who is satisfied with the **{1}** for now.',
                                         'For SCIENCE, the villagers throw **{0}** into a volcano. They discover that the melting point of a **{1}** is less than that of lava.',
                                         'The villagers force **{0}** to play Russian Roulette. The town square is stained with the remains of the **{1}**.'])
            lynched_msg = lynched_msg.format(get_name(lynched_player), session[1][lynched_player][1])
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
            
##            leave_players = []
##            for player in list(session[1].keys()):
##                if session[1][player][2] == 'leave':
##                    leave_players.append(player)
##                    del session[1][player]
##                else:
##                    session[1][player][2] = ''
##
##            if leave_players != []:
##                await client.send_message(client.get_channel(GAME_CHANNEL), "**" + "**, **".join([get_name(x) for x in leave_players]).rstrip("**, **") + "** spontaneously combusted.")
            for player in session[1].keys():
                session[1][player][2] = ''
    if session[0]:
        win_msg = await win_condition()
        await end_game(win_msg[1])

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
            'fstop' : [cmd_fstop, [1, 1], "```\n{0}fstop [<reason>]\n\nForcibly stops the current game with an optional [<reason>].```"],
            'revealroles' : [cmd_revealroles, [2, 1], "```\n{0}revealroles takes no arguments\n\nDisplays what each user's roles are and sends it in pm.```"],
            'see' : [cmd_see, [2, 0], "```\n{0}see <player>\n\nIf you are a seer, uses your power to detect <player>'s role.```"],
            'kill' : [cmd_kill, [2, 0], "```\n{0}kill <player>\n\nIf you are a wolf, casts your vote to target <player>.```"],
            'lynch' : [cmd_lynch, [0, 2], "```\n{0}lynch [<player>]\n\nVotes to lynch [<player>] during the day. If no arguments are given, replies with a list of current votes.```"],
            'retract' : [cmd_retract, [0, 2], "```\n{0}retract takes no arguments\n\nRetracts your vote to lynch.```"],
            'v' : [cmd_lynch, [0, 2], "```\nAlias for {0}lynch.```"],
            'r' : [cmd_retract, [0, 2], "```\nAlias for {0}retract.```"],
            'coin' : [cmd_coin, [0, 0], "```\n{0}coin takes no arguments\n\nFlips a coin. Don't use this for decision-making, especially not for life or death situations.```"],
            'admins' : [cmd_admins, [0, 0], "```\n{0}admins takes no arguments\n\nLists online/idle admins if used in pm, and **alerts** online/idle admins if used in channel (**USE ONLY WHEN NEEDED**).```"],
            'fday' : [cmd_fday, [1, 2], "```\n{0}fday takes no arguments\n\nForces night to end.```"],
            'fnight' : [cmd_fnight, [1, 2], "```\n{0}fnight takes no arguments\n\nForces day to end.```"],
            'fstart' : [cmd_fstart, [1, 2], "```\n{0}fstart takes no arguments\n\nForces game to start.```"],
            'frole' : [cmd_frole, [2, 2], "```\n{0}frole <player> <role>\n\nSets <player>'s role to <role>.```"],
            'force' : [cmd_force, [2, 2], "```\n{0}force <player> <target>\n\nSets <player>'s target flag (session[1][player][2]) to <target>.```"],
            'session' : [cmd_session, [2, 1], "```\n{0}session takes no arguments\n\nReplies with the contents of the session variable in pm for debugging purposes. Admin only.```"],
            'time' : [cmd_time, [0, 0], "```\n{0}time takes no arguments\n\nChecks in-game time.```"],
            'test' : [cmd_test, [1, 0], "test"]}

COMMANDS_FOR_ROLE = {'see' : 'seer',
                     'kill' : 'wolf'}

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
roles = {'wolf' : ['wolf', 'wolves', "Your job is to kill all of the villagers. Type `kill <player>` in private message to kill them.",
                   [1, 1, 1, 1, 1, 2,  2, 2, 2, 2, 2, 2, 2]],
         'villager' : ['village', 'villagers', "Your job is to lynch all of the wolves.",
                   [2, 3, 3, 4, 5, 5,  6, 7, 8, 9, 10, 11, 11]],
         'seer' : ['village', 'seers', "Your job is to detect the wolves; you may have a vision once per night. Type `see <player>` in private message to see their role.",
                   [1, 1, 1, 1, 1, 1,  1, 1, 1, 1, 1, 1, 2]],
         'cursed villager' : ['village', 'cursed villagers', "This template is a villager but is seen by the seer as a wolf. Roles normally seen as wolf and the seer cannot be cursed.",
                   [0, 0, 1, 1, 1, 1,  1, 1, 1, 1, 1, 1, 1]]}
ROLES_SEEN_VILLAGER = ['villager', 'seer', 'traitor']
ROLES_SEEN_WOLF = ['wolf', 'cursed']

########### END POST-DECLARATION STUFF #############
client.run(TOKEN)
