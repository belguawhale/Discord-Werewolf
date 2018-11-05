import asyncio
import sys
import io
import inspect
import traceback
import discord
from discord.ext import commands

def cleanup_code(content):
    '''Automatically removes code blocks from the code.'''
    # remove ```py\n```
    if content.startswith('```') and content.endswith('```'):
        return '\n'.join(content.split('\n')[1:-1])

    # remove `foo`
    return content.strip('` \n')

def get_syntax_error(e):
    if e.text is None:
        return f'```py\n{e.__class__.__name__}: {e}\n```'
    return f'```py\n{e.text}{"^":>{e.offset}}\n{e.__class__.__name__}: {e}```'

class Owner():
    '''Owner-only commands.'''
    def __init__(self, bot):
        self.bot = bot
    
    async def __local_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    def convert_extension_name(self, name):
        if not name.startswith('cogs.'):
            return f'cogs.{name[0].lower()}{name[1:]}'
        return name

    @commands.command()
    async def shutdown(self, ctx):
        '''Shuts down the bot. Owner-only.'''
        await ctx.send('Shutting down...')
        await self.bot.logout()
    
    @commands.command()
    async def restart(self, ctx):
        '''Restarts the bot. Owner-only.'''
        await ctx.send('Restarting...')
        self.bot.restart = True
        await self.bot.logout()
    
    @commands.command()
    async def load(self, ctx, *, cog=None):
        '''Loads <cog>. Owner-only.'''
        if not cog:
            await ctx.invoke(self.bot.get_command('help'), 'load')
        elif self.convert_extension_name(cog) in self.bot.extensions:
            await ctx.send(f'Module {cog} is already loaded.')
        else:
            try:
                self.bot.load_extension(self.convert_extension_name(cog))
            except ModuleNotFoundError as e:
                await ctx.send(str(e))
            else:
                await ctx.send(':thumbsup:')
    
    @commands.command()
    async def unload(self, ctx, *, cog=None):
        '''Unloads <cog>. Owner-only.'''
        if not cog:
            await ctx.invoke(self.bot.get_command('help'), 'unload')
        elif self.convert_extension_name(cog) in self.bot.extensions:
            self.bot.unload_extension(self.convert_extension_name(cog))
            await ctx.send(':thumbsup:')
        else:
            await ctx.send(f'Module {cog} is not loaded.')

    @commands.command()
    async def reload(self, ctx, *, cog=None):
        '''Reloads <cog>. Owner-only.'''
        if not cog:
            await ctx.invoke(self.bot.get_command('help'), 'reload')
        elif self.convert_extension_name(cog) in self.bot.extensions:
            self.bot.reload_extension(self.convert_extension_name(cog))
            await ctx.send(':thumbsup:')
        else:
            await ctx.error(f'Module {cog} is not loaded.')
    
    @commands.command('eval')
    async def eval_(self, ctx, *, expression=None):
        '''Evaluates <expression> as a Python expression. Owner-only.'''
        if not expression:
            await ctx.invoke(self.bot.get_command('help'), 'eval')
            return
        try:
            output = eval(expression)
        except:
            traceback.print_exc()
            await ctx.send(f'```\n{traceback.format_exc()}\n```')
            return
        if asyncio.iscoroutine(output):
            output = await output
        await ctx.send(f'```\n{output}\n```')
    
    @commands.command('exec')
    async def exec_(self, ctx, *, code=None):
        '''Executes python <code>. Owner-only.'''
        if not code:
            await ctx.invoke(self.bot.get_command('help'), 'exec')
            return
        old_stdout = sys.stdout
        redirected_output = sys.stdout = io.StringIO()
        try:
            exec(code)
        except Exception:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
            return
        finally:
            sys.stdout = old_stdout
        if redirected_output.getvalue() is not None:
            await ctx.send(redirected_output.getvalue())
            return
        await ctx.send(':thumbsup:')
    
    @commands.command()
    async def repl(self, ctx):
        '''Launches an interactive REPL session. Owner-only.'''
        variables = {
            'ctx': ctx,
            'bot': self.bot,
            'message': ctx.message,
            'guild': ctx.guild,
            'channel': ctx.channel,
            'author': ctx.author,
            '_': None,
        }
        await ctx.send('Enter code to execute or evaluate. `exit()` or `quit` to exit.')

        def check(m):
            return m.author.id == ctx.author.id and \
                m.channel.id == ctx.channel.id

        while True:
            try:
                response = await self.bot.wait_for('message', check=check, timeout=10 * 60.0)
            except asyncio.TimeoutError:
                await ctx.send(f'{ctx.author.mention}: Exiting REPL session due to inactivity.')
                break

            cleaned = cleanup_code(response.content)

            if cleaned in ('quit', 'exit', 'exit()'):
                await ctx.send('Exiting REPL session.')
                return

            executor = exec
            if cleaned.count('\n') == 0:
                # single statement, potentially 'eval'
                try:
                    code = compile(cleaned, '<repl session>', 'eval')
                except SyntaxError:
                    pass
                else:
                    executor = eval

            if executor is exec:
                try:
                    cleaned = 'async def func():\n    locals().update(globals())\n' \
                                '{}\n    globals().update(locals())'.format('\n'.join(f'    {x}' for x in cleaned.split('\n')))
                    code = compile(cleaned, '<repl session>', 'exec')
                    exec(code, variables)
                except SyntaxError as e:
                    await ctx.send(get_syntax_error(e))
                    continue
                else:
                    executor = eval
                    code = compile('func()', '<repl session>', 'eval')

            variables['message'] = response

            fmt = None

            old_stdout = sys.stdout
            sys.stdout = stdout = io.StringIO()

            try:
                result = executor(code, variables)
                if inspect.isawaitable(result):
                    result = await result
            except Exception as e:
                value = stdout.getvalue()
                fmt = f'```py\n{value}{traceback.format_exc()}\n```'
            else:
                value = stdout.getvalue()
                if result is not None:
                    fmt = f'```py\n{value}{result}\n```'
                    variables['_'] = result
                elif value:
                    fmt = f'```py\n{value}\n```'
            finally:
                sys.stdout = old_stdout

            try:
                if fmt is None:
                    fmt = ':thumbsup:'
                if len(fmt) > 2000:
                    await ctx.send('Content too big to be printed.')
                else:
                    await ctx.send(fmt)
            except discord.Forbidden:
                pass
            except discord.HTTPException as e:
                await ctx.send('Unexpected error: `{}`'.format(e))
    
def setup(bot):
    bot.add_cog(Owner(bot))