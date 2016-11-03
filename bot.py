import asyncio
import json
import discord
from discord.ext import commands

try:
    with open('ban_user.json', 'r') as f:
        try:
            ban_user = json.load(f)
        except ValueError:
            ban_user = []
except IOError:
    ban_user = []
try:
    with open('superadm.json', 'r') as f:
        try:
            superadm = json.load(f)
        except ValueError:
            superadm = ['your_id']
except IOError:
    superadm = ['your_id']
try:
    with open('adm_user.json', 'r') as f:
        try:
            adm_user = json.load(f)
        except ValueError:
            adm_user = []
except IOError:
    adm_user = []
try:
    with open('replya.json', 'r') as f:
        try:
            replya = json.load(f)
        except ValueError:
            replya = {}
except IOError:
    replya = {}
try:
    with open('pic_replya.json', 'r') as f:
        try:
            pic_replya = json.load(f)
        except ValueError:
            pic_replya = {}
except IOError:
    pic_replya = {}
try:
    with open('bgm_list.json', 'r') as f:
        try:
            bgm_list = json.load(f)
        except ValueError:
            bgm_list = {}
except IOError:
    bgm_list = {}

bgm_player = {}
typing = []

with open('avatar.png', 'rb') as f:
    avatar = f.read()

with open('player_avatar.png', 'rb') as f:
    player_avatar = f.read()

if not discord.opus.is_loaded():
    # the 'opus' library here is opus.dll on windows
    # or libopus.so on linux in the current directory
    # you should replace this with the location the
    # opus library is located in and with the proper filename.
    # note that on windows this DLL is automatically provided for you
    discord.opus.load_opus('opus')

class VoiceEntry:
    def __init__(self, message, player):
        self.requester = message.author
        self.channel = message.channel
        self.player = player

    def __str__(self):
        fmt = '*{0.title}* uploaded by {0.uploader} and requested by {1.display_name}'
        duration = self.player.duration
        if duration:
            fmt = fmt + ' [length: {0[0]}m {0[1]}s]'.format(divmod(duration, 60))
        return fmt.format(self.player, self.requester)

class VoiceState:
    def __init__(self, bot):
        self.current = None
        self.voice = None
        self.bot = bot
        self.play_next_song = asyncio.Event()
        self.songs = asyncio.Queue()
        self.skip_votes = set() # a set of user_ids that voted
        self.audio_player = self.bot.loop.create_task(self.audio_player_task())

    def is_playing(self):
        if self.voice is None or self.current is None:
            return False

        player = self.current.player
        return not player.is_done()

    @property
    def player(self):
        return self.current.player

    def skip(self):
        self.skip_votes.clear()
        if self.is_playing():
            self.player.stop()

    def toggle_next(self):
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)

    async def audio_player_task(self):
        while True:
            self.play_next_song.clear()
            self.current = await self.songs.get()
            await self.bot.send_message(self.current.channel, 'Now playing ' + str(self.current))
            self.current.player.start()
            await self.play_next_song.wait()

class Music:
    """Voice related commands.

    Works in multiple servers at once.
    """
    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, server):
        state = self.voice_states.get(server.id)
        if state is None:
            state = VoiceState(self.bot)
            self.voice_states[server.id] = state

        return state

    async def create_voice_client(self, channel):
        voice = await self.bot.join_voice_channel(channel)
        state = self.get_voice_state(channel.server)
        state.voice = voice

    def __unload(self):
        for state in self.voice_states.values():
            try:
                state.audio_player.cancel()
                if state.voice:
                    self.bot.loop.create_task(state.voice.disconnect())
            except:
                pass

    async def player_say(self, message, content):
        await self.bot.change_nickname(message.server.me, 'Player')
        await self.bot.edit_profile(avatar=player_avatar)
        await self.bot.send_message(message.channel, content)
        await self.bot.change_nickname(message.server.me, None)
        await self.bot.edit_profile(avatar=avatar)

    @commands.command(pass_context=True, no_pm=True)
    async def join(self, ctx, *, channel : discord.Channel):
        """Joins a voice channel."""
        try:
            await self.create_voice_client(channel)
        except discord.ClientException:
            await self.player_say(ctx.message, 'Already in a voice channel...')
        except discord.InvalidArgument:
            await self.player_say(ctx.message, 'This is not a voice channel...')
        else:
            await self.player_say(ctx.message, 'Ready to play audio in ' + channel.name)

    @commands.command(pass_context=True, no_pm=True)
    async def summon(self, ctx):
        """Summons the bot to join your voice channel."""
        summoned_channel = ctx.message.author.voice_channel
        if summoned_channel is None:
            await self.player_say(ctx.message, 'You are not in a voice channel.')
            return False

        state = self.get_voice_state(ctx.message.server)
        if state.voice is None:
            state.voice = await self.bot.join_voice_channel(summoned_channel)
        else:
            await state.voice.move_to(summoned_channel)

        return True

    @commands.command(pass_context=True, no_pm=True)
    async def play(self, ctx, *, song : str = None):
        """Plays a song.

        If there is a song currently in the queue, then it is
        queued until the next song is done playing.

        This command automatically searches as well from YouTube.
        The list of supported sites can be found here:
        https://rg3.github.io/youtube-dl/supportedsites.html
        """

        state = self.get_voice_state(ctx.message.server)
        opts = {
            'default_search': 'auto',
            'quiet': True,
        }

        if state.voice is None:
            success = await ctx.invoke(self.summon)
            if not success:
                return
        if song is None:
            song = 'https://www.youtube.com/watch?v=4kYSc64aU1w'

        try:
            player = await state.voice.create_ytdl_player(song, ytdl_options=opts, after=state.toggle_next)
        except Exception as e:
            fmt = 'An error occurred while processing this request: ```py\n{}: {}\n```'
            await self.bot.send_message(ctx.message.channel, fmt.format(type(e).__name__, e))
        else:
            player.volume = 0.2
            entry = VoiceEntry(ctx.message, player)
            await self.bot.change_nickname(ctx.message.server.me, 'Player')
            await self.bot.edit_profile(avatar=player_avatar)
            await self.player_say(ctx.message, 'Enqueued ' + str(entry))
            await self.bot.change_nickname(ctx.message.server.me, None)
            await self.bot.edit_profile(avatar=avatar)
            await state.songs.put(entry)

    @commands.command(pass_context=True, no_pm=True)
    async def volume(self, ctx, value : int):
        """Sets the volume of the currently playing song."""

        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.volume = value / 100
            await self.player_say(ctx.message, 'Set the volume to {:.0%}'.format(player.volume))

    @commands.command(pass_context=True, no_pm=True)
    async def pause(self, ctx):
        """Pauses the currently played song."""
        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.pause()

    @commands.command(pass_context=True, no_pm=True)
    async def resume(self, ctx):
        """Resumes the currently played song."""
        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.resume()

    @commands.command(pass_context=True, no_pm=True)
    async def stop(self, ctx):
        """Stops playing audio and leaves the voice channel.

        This also clears the queue.
        """
        server = ctx.message.server
        state = self.get_voice_state(server)

        if ctx.message.author.id not in adm_user:
            await bot.say('Sorry, {0.name} can\'t stop playing.'.format(ctx.message.author))
            return

        if state.is_playing():
            player = state.player
            player.stop()

        try:
            state.audio_player.cancel()
            del self.voice_states[server.id]
            await state.voice.disconnect()
            voice = self.bot.voice_client_in(server.id)
            voice.disconnect()
        except:
            pass

    @commands.command(pass_context=True, no_pm=True)
    async def skip(self, ctx):
        """Vote to skip a song. The song requester can automatically skip.

        3 skip votes are needed for the song to be skipped.
        """

        state = self.get_voice_state(ctx.message.server)
        if not state.is_playing():
            await self.player_say(ctx.message, 'Not playing any music right now...')
            return

        voter = ctx.message.author
        if voter == state.current.requester:
            await self.player_say(ctx.message, 'Requester requested skipping song...')
            state.skip()
        elif voter.id in adm_user:
            await self.player_say(ctx.message, 'Skipping song...')
            state.skip()
        elif voter.id not in state.skip_votes:
            state.skip_votes.add(voter.id)
            total_votes = len(state.skip_votes)
            if total_votes >= 3:
                await self.player_say(ctx.message, 'Skip vote passed, skipping song...')
                state.skip()
            else:
                await self.player_say(ctx.message, 'Skip vote added, currently at [{}/3]'.format(total_votes))
        else:
            await self.player_say(ctx.message, 'You have already voted to skip this song.')

    @commands.command(pass_context=True, no_pm=True)
    async def playing(self, ctx):
        """Shows info about the currently played song."""

        state = self.get_voice_state(ctx.message.server)
        if state.current is None:
            await self.player_say(ctx.message, 'Not playing anything.')
        else:
            skip_count = len(state.skip_votes)
            await self.player_say(ctx.message, 'Now playing {} [skips: {}/3]'.format(state.current, skip_count))

bot = commands.Bot(command_prefix='!', description='a simple discord bot')
music = Music(bot)
game_i = discord.Game()
bot.add_cog(music)
silent = False

@bot.event
async def on_ready():
    print('Logged in as:\n{0} (ID: {0.id})'.format(bot.user))
@bot.event
async def on_message(message):
    global silent
    # we do not want the bot to reply to itself
    if message.author == bot.user:
        return

    typing.clear()
    if message.content.startswith(bot.user.mention):
        if message.author.id not in adm_user:
            await bot.send_file(message.channel, 'avatar.png')
            return
        if '閉嘴' in message.content:
            silent = True
            await bot.send_message(message.channel, '\_(:з」∠)_')
        elif '說話' in message.content:
            silent = False
            await bot.send_message(message.channel, '>_>')
        else:
            await bot.send_message(message.channel, '¯\_(ツ)_/¯')
        return
    if silent:
        return
    if message.content.startswith('!'):
        if message.author.id in ban_user:
            await bot.send_message(message.channel, '{0.author.mention} 不要'.format(message))
            return
    else:
        for key in replya.keys():
            if key in message.content:
                msg = '{0.author.mention} '+replya[key]
                await bot.send_message(message.channel, msg.format(message))
                return

        for key in pic_replya.keys():
            if key in message.content:
                await bot.send_file(message.channel, 'pic/'+pic_replya[key])
                return

        for key in bgm_list.keys():
            if key in message.content:
                if message.author.id in ban_user:
                    await bot.send_message(message.channel, '{0.author.mention} 閉嘴'.format(message))
                    return
                state = music.get_voice_state(message.server)
                member = message.server.get_member(key)
                if member.voice_channel is None:
                    await bot.send_message(message.channel, '{0.name} is not in a voice channel.'.format(member))
                    return
                if state.voice is None:
                    state.voice = await bot.join_voice_channel(member.voice_channel)
                else:
                    await state.voice.move_to(member.voice_channel)
                if state.is_playing():
                    player = state.player
                    player.pause()
                if bgm_player.get(message.server.id) is not None:
                    if bgm_player[message.server.id].is_playing():
                        bgm_player[message.server.id].stop()
                bgm_player[message.server.id] = await state.voice.create_ytdl_player(bgm_list[key])
                bgm_player[message.server.id].start()
                return

    await bot.process_commands(message)

@bot.event
async def on_typing(channel, user, when):
    if silent:
        return
    if user == bot.user:
        return
    if typing.count(user.id) == 3:
        typing.clear()
        await bot.send_message(channel, '{0.mention} 請說'.format(user))
    else:
        typing.append(user.id)

@bot.command()
async def add_reply(keyword : str, reply : str):
    """add reply rule"""
    if keyword in replya.keys():
        replya[keyword] = reply
        await bot.say('Keyword '+keyword+' is changed')
    else:
        replya.update({keyword:reply})
        await bot.say('Keyword '+keyword+' is added')
    with open('replya.json', 'w') as f:
        json.dump(replya, f)

@bot.command()
async def del_reply(keyword : str):
    """delete reply rule"""
    if keyword in replya.keys():
        del replya[keyword]
        await bot.say('Keyword '+keyword+' is deleted')
    else:
        await bot.say('No keyword is named '+keyword)
    with open('replya.json', 'w') as f:
        json.dump(replya, f)

@bot.command()
async def add_picrep(keyword : str, reply : str):
    """add picture reply rule"""
    if keyword in pic_replya.keys():
        pic_replya[keyword] = reply
        await bot.say('Keyword '+keyword+' is changed')
    else:
        pic_replya.update({keyword:reply})
        await bot.say('Keyword '+keyword+' is added')
    with open('pic_replya.json', 'w') as f:
        json.dump(pic_replya, f)

@bot.command()
async def del_picrep(keyword : str):
    """delete picture reply rule"""
    if keyword in pic_replya.keys():
        del pic_replya[keyword]
        await bot.say('Keyword '+keyword+' is deleted')
    else:
        await bot.say('No keyword is named '+keyword)
    with open('pic_replya.json', 'w') as f:
        json.dump(pic_replya, f)

@bot.command(pass_context=True)
async def add_bgm(ctx, member : discord.Member, bgm : str):
    """add bgm"""
    if ctx.message.author.id not in adm_user:
        await bot.say('Sorry, {0.name} can\'t add bgm.'.format(ctx.message.author))
        return
    if member.id in bgm_list.keys():
        bgm_list[member.id] = bgm
        await bot.say('{0.name}\'s bgm is changed'.format(member))
    else:
        bgm_list.update({member.id:bgm})
        await bot.say('{0.name}\'s bgm is added'.format(member))
    with open('bgm_list.json', 'w') as f:
        json.dump(bgm_list, f)

@bot.command(pass_context=True)
async def del_bgm(ctx, member : discord.Member):
    """delete bgm"""
    if ctx.message.author.id not in adm_user:
        await bot.say('Sorry, {0.name} can\'t delete bgm.'.format(ctx.message.author))
        return
    if member.id in bgm_list.keys():
        del bgm_list[member.id]
        await bot.say('{0.name}\'s bgm is deleted'.format(member))
    else:
        await bot.say('No bgm is for {0.name}'.format(member))
    with open('bgm_list.json', 'w') as f:
        json.dump(bgm_list, f)

@bot.command(pass_context=True, hidden=True)
async def ban(ctx, member : discord.Member):
    """ban user"""

    if ctx.message.author.id not in adm_user:
        await bot.say('Sorry, {0.name} can\'t ban user.'.format(ctx.message.author))
        return
    
    if member.id in ban_user:
        await bot.say('{0.name} is already banned!'.format(member))
    else:
        ban_user.append(member.id)
        await bot.say('{0.name} has been banned!'.format(member))
    with open('ban_user.json', 'w') as f:
        json.dump(ban_user, f)

@bot.command(pass_context=True, hidden=True)
async def unban(ctx, member : discord.Member):
    """unban user"""

    if ctx.message.author.id not in adm_user:
        await bot.say('Sorry, {0.name} can\'t unban user.'.format(ctx.message.author))
        return

    if member.id in ban_user:
        ban_user.remove(member.id)
        await bot.say('{0.name} has been unbanned!'.format(member))
    else:
        await bot.say('{0.name} isn\'t banned!'.format(member))
    with open('ban_user.json', 'w') as f:
        json.dump(ban_user, f)

@bot.command(pass_context=True, hidden=True)
async def adm(ctx, member : discord.Member):
    """make user admin"""

    if ctx.message.author.id not in superadm:
        await bot.say('Sorry, {0.name} can\'t make user admin.'.format(ctx.message.author))
        return
    
    if member.id in adm_user:
        await bot.say('{0.name} is already admin!'.format(member))
    else:
        adm_user.append(member.id)
        await bot.say('{0.name} is admin!'.format(member))
    with open('adm_user.json', 'w') as f:
        json.dump(adm_user, f)

@bot.command(pass_context=True, hidden=True)
async def unadm(ctx, member : discord.Member):
    """make user not admin"""

    if ctx.message.author.id not in superadm:
        await bot.say('Sorry, {0.name} can\'t make user not admin.'.format(ctx.message.author))
        return

    if member.id in adm_user:
        adm_user.remove(member.id)
        await bot.say('{0.name} isn\'t admin now!'.format(member))
    else:
        await bot.say('{0.name} is already not admin!'.format(member))
    with open('adm_user.json', 'w') as f:
        json.dump(adm_user, f)

@bot.command(pass_context=True, hidden=True)
async def game(ctx, *, name : str = None):
    """update game status"""

    if ctx.message.author.id not in superadm:
        await bot.say('Sorry, {0.name} can\'t use this.'.format(ctx.message.author))
        return

    if name is None:
        await bot.change_presence()
    else:
        game_i.name=name
        await bot.change_presence(game=game_i)

@bot.command(pass_context=True, hidden=True)
async def twitch(ctx, *, url : str = None):
    """update game status"""

    if ctx.message.author.id not in superadm:
        await bot.say('Sorry, {0.name} can\'t use this.'.format(ctx.message.author))
        return

    if url is None:
        game_i.url=None
        game_i.type=0
        await bot.change_presence(game=game_i)
    else:
        game_i.url=url
        game_i.type=1
        await bot.change_presence(game=game_i)

bot.run('bot_token')
