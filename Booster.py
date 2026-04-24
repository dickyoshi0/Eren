import discord
from discord.ext import commands
from discord.ui import View, Select, Button
import time

# --- DATA STORAGE ---
user_boosters = {}          # user_id -> {"active": [], "paused": []}
user_cooldown = {}          # user_id -> timestamp when cooldown expires
user_action_count = {}      # user_id -> number of actions performed
cooldown_seconds = 0        # duration of cooldown in seconds
cooldown_threshold = 0      # actions allowed before cooldown

OWNER_ID = 1426976674687225956

BOOSTER_DATA = {
    "triple.xp.24h": {"name": "Triple XP", "hours": 24, "emojis": "<:triplexp:1497147416204279970><:exclusive:1497225869024821339>"},
    "leg.explore.luck.1h": {"name": "Explore Luck", "hours": 1, "emojis": "<:luck:1497147371136487424><:legendary:1497147476506054748>"},
    "leg.explore.cd.1h": {"name": "Explore Cooldown", "hours": 1, "emojis": "<:cooldown:1497147271618498670><:legendary:1497147476506054748>"},
    "leg.explore.eff.1h": {"name": "Explore Efficiency", "hours": 1, "emojis": "<:efficiency:1497147324915257385><:legendary:1497147476506054748>"}
}

# --- PLAIN TEXT EMBEDS (no markdown) ---
def get_action_embed(user, booster_name, booster_emojis, action):
    action_emoji = "<:pause:1497156930899017768>" if action == "paused" else "<:up:1497157057286111242>"
    description = f"{action_emoji} You {action} your booster!\n\n{booster_emojis} {booster_name}"
    embed = discord.Embed(color=0xE77E23, description=description)
    embed.set_author(name="user's action", icon_url=user.display_avatar.url)
    if action == "paused":
        embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1497228862449389760.png")
    else:
        embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1497176482865217617.png")
    return embed

def get_selection_embed(user):
    description = "Select a booster from the menu below.\n\nPause or Resume only one booster at a time."
    embed = discord.Embed(color=0xE77E23, description=description)
    embed.set_author(name="Make a selection", icon_url=user.display_avatar.url)
    return embed

def get_error_embed(user, error_message):
    description = f"<:error:1497146924518867065> ERROR\n\n{error_message}"
    embed = discord.Embed(color=discord.Color.red(), description=description)
    embed.set_author(name="invalid type", icon_url=user.display_avatar.url)
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1497146924518867065.png")
    return embed

def get_success_embed(user, message):
    description = f"✅ SUCCESS\n\n{message}"
    embed = discord.Embed(color=0x00FF00, description=description)
    embed.set_author(name="success", icon_url=user.display_avatar.url)
    return embed

def get_help_embed(user):
    embed = discord.Embed(
        color=0xE77E23,
        title="<:exclusive:1497225869024821339> Bot Commands",
        description="Use the commands below to manage boosters and the bot."
    )
    embed.set_author(name="Help Menu", icon_url=user.display_avatar.url)
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1497225869024821339.png")
    embed.add_field(
        name="!booster",
        value="Opens your booster management panel.\nShows active & paused boosters with Pause/Resume buttons.",
        inline=False
    )
    embed.add_field(
        name="!sys addbooster <type>",
        value="Adds a booster to your active list.\nTypes: triple.xp.24h, leg.explore.luck.1h, leg.explore.cd.1h, leg.explore.eff.1h",
        inline=False
    )
    embed.add_field(
        name="!sys addall",
        value="Adds all boosters at once (stacks with existing).",
        inline=False
    )
    embed.add_field(
        name="!bot reset (owner only)",
        value="Resets ALL user booster data.\nClears all active and paused boosters for every user.",
        inline=False
    )
    embed.add_field(
        name="!bot addcd <seconds> (owner only)",
        value="Sets a global cooldown duration for pause/resume.\nExample: !bot addcd 30",
        inline=False
    )
    embed.add_field(
        name="!bot setcd <amount> (owner only)",
        value="Sets how many pause/resume actions allowed before cooldown.\nExample: !bot setcd 5",
        inline=False
    )
    embed.add_field(
        name="!help",
        value="Shows this help message.",
        inline=False
    )
    return embed

def get_booster_panel_embed(user):
    data = user_boosters.get(user.id, {"active": [], "paused": []})
    embed = discord.Embed(color=0xE77E23)
    embed.set_author(name="Booster Reload", icon_url=user.display_avatar.url)
    active_part = "<:ACTIVE:1497156838230331533> Activated\n"
    if not data['active']:
        active_part += "None\n"
    for b in data['active']:
        active_part += f"{b['emojis']} {b['name']}\n⏱ Expires in {b['hours']} hours\n"
    paused_part = ""
    if data['paused']:
        paused_part += f"\n<:pauseicon:1497228814625804368> Paused\n"
        for b in data['paused']:
            paused_part += f"{b['emojis']} {b['name']} (Paused)\n"
    embed.description = f"{active_part}\n{paused_part}"
    return embed

def get_cooldown_embed(user, remaining_seconds):
    if remaining_seconds >= 60:
        minutes = remaining_seconds // 60
        seconds = remaining_seconds % 60
        time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
        if seconds:
            time_str += f" and {seconds} second{'s' if seconds != 1 else ''}"
    else:
        time_str = f"{remaining_seconds} second{'s' if remaining_seconds != 1 else ''}"
    
    # Wrap time_str with ** to make it bold (appears larger in Discord)
    description = f"<:error2:1497225749005074512> COOLDOWN\n\n❌ You can use this command again in **{time_str}**\n\n• Buy [Rank](https://eren.bot) to unlock special perks to manage your booster"
    embed = discord.Embed(color=discord.Color.orange(), description=description)
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1497225749005074512.png")
    return embed
# --- COOLDOWN HELPERS (with action counter) ---
def is_on_cooldown(user_id):
    if cooldown_seconds <= 0:
        return False
    if user_id not in user_cooldown:
        return False
    return time.time() < user_cooldown[user_id]

def set_cooldown(user_id):
    if cooldown_seconds > 0:
        user_cooldown[user_id] = time.time() + cooldown_seconds
        user_action_count[user_id] = 0  # reset counter after cooldown

def record_action(user_id):
    if user_id not in user_action_count:
        user_action_count[user_id] = 0
    user_action_count[user_id] += 1
    # If the number of actions reaches the threshold, activate cooldown
    if cooldown_threshold > 0 and user_action_count[user_id] >= cooldown_threshold:
        set_cooldown(user_id)

def can_perform_action(user_id):
    return not is_on_cooldown(user_id)

# --- UI COMPONENTS ---
class BoosterSelect(Select):
    def __init__(self, boosters, mode, parent_view):
        self.parent_view = parent_view
        self.mode = mode
        options = []
        for b in boosters:
            emoji_str = b['emojis'].split()[0] if b['emojis'] else None
            options.append(discord.SelectOption(
                label=b['name'],
                value=b['name'],
                description=f"Time: {b['hours']}h",
                emoji=emoji_str
            ))
        super().__init__(placeholder="Select a booster...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            uid = interaction.user.id
            if not can_perform_action(uid):
                remaining = int(user_cooldown[uid] - time.time())
                return await interaction.followup.send(embed=get_cooldown_embed(interaction.user, remaining), ephemeral=True)

            selected_name = self.values[0]
            if uid not in user_boosters:
                user_boosters[uid] = {"active": [], "paused": []}

            if self.mode == "pause":
                item = next((b for b in user_boosters[uid]['active'] if b['name'] == selected_name), None)
                if not item:
                    return await interaction.followup.send(embed=get_error_embed(interaction.user, "That booster is no longer active."), ephemeral=True)
                user_boosters[uid]['active'].remove(item)
                user_boosters[uid]['paused'].append(item)
                action_str = "paused"
            else:
                item = next((b for b in user_boosters[uid]['paused'] if b['name'] == selected_name), None)
                if not item:
                    return await interaction.followup.send(embed=get_error_embed(interaction.user, "That booster is not paused."), ephemeral=True)
                user_boosters[uid]['paused'].remove(item)
                user_boosters[uid]['active'].append(item)
                action_str = "resumed"

            # Record the action (increment counter, possibly trigger cooldown)
            record_action(uid)

            # Update main panel
            try:
                await self.parent_view.message.edit(embed=get_booster_panel_embed(self.parent_view.user))
            except:
                await interaction.channel.send(embed=get_booster_panel_embed(self.parent_view.user), view=self.parent_view)

            await interaction.followup.send(embed=get_action_embed(interaction.user, item['name'], item['emojis'], action_str), ephemeral=True)
        except Exception as e:
            print(f"Select error: {e}")
            await interaction.followup.send(embed=get_error_embed(interaction.user, "Something went wrong. Please try again."), ephemeral=True)

class BoosterManager(View):
    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user
        self.message = None

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.green, emoji="<:pause:1497146998418309210>")
    async def pause_btn(self, button: Button, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            if interaction.user.id != self.user.id:
                return await interaction.followup.send(embed=get_error_embed(interaction.user, "Not your menu!"), ephemeral=True)

            if not can_perform_action(interaction.user.id):
                remaining = int(user_cooldown[interaction.user.id] - time.time())
                return await interaction.followup.send(embed=get_cooldown_embed(interaction.user, remaining), ephemeral=True)

            if self.user.id not in user_boosters:
                user_boosters[self.user.id] = {"active": [], "paused": []}

            data = user_boosters[self.user.id]
            if not data['active']:
                return await interaction.followup.send(embed=get_error_embed(interaction.user, "Nothing active!"), ephemeral=True)

            if len(data['active']) > 1:
                view = View()
                view.add_item(BoosterSelect(data['active'], "pause", self))
                await interaction.followup.send(embed=get_selection_embed(interaction.user), view=view, ephemeral=True)
            else:
                item = data['active'].pop(0)
                data['paused'].append(item)
                record_action(interaction.user.id)
                await interaction.edit_original_response(embed=get_booster_panel_embed(self.user))
                await interaction.followup.send(embed=get_action_embed(interaction.user, item['name'], item['emojis'], "paused"), ephemeral=True)
        except Exception as e:
            print(f"Pause error: {e}")
            await interaction.followup.send(embed=get_error_embed(interaction.user, "An error occurred. Please try again."), ephemeral=True)

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.green, emoji="<:resume:1497146773733638165>")
    async def resume_btn(self, button: Button, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            if interaction.user.id != self.user.id:
                return await interaction.followup.send(embed=get_error_embed(interaction.user, "Not your menu!"), ephemeral=True)

            if not can_perform_action(interaction.user.id):
                remaining = int(user_cooldown[interaction.user.id] - time.time())
                return await interaction.followup.send(embed=get_cooldown_embed(interaction.user, remaining), ephemeral=True)

            if self.user.id not in user_boosters:
                user_boosters[self.user.id] = {"active": [], "paused": []}

            data = user_boosters[self.user.id]
            if not data['paused']:
                return await interaction.followup.send(embed=get_error_embed(interaction.user, "Nothing paused!"), ephemeral=True)

            if len(data['paused']) > 1:
                view = View()
                view.add_item(BoosterSelect(data['paused'], "resume", self))
                await interaction.followup.send(embed=get_selection_embed(interaction.user), view=view, ephemeral=True)
            else:
                item = data['paused'].pop(0)
                data['active'].append(item)
                record_action(interaction.user.id)
                await interaction.edit_original_response(embed=get_booster_panel_embed(self.user))
                await interaction.followup.send(embed=get_action_embed(interaction.user, item['name'], item['emojis'], "resumed"), ephemeral=True)
        except Exception as e:
            print(f"Resume error: {e}")
            await interaction.followup.send(embed=get_error_embed(interaction.user, "An error occurred. Please try again."), ephemeral=True)

# --- BOT SETUP ---
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
bot.remove_command('help')

# --- HELP COMMAND ---
@bot.command(name="help")
async def help_command(ctx):
    await ctx.send(embed=get_help_embed(ctx.author))

# --- OWNER CONTROL PANEL ---
@bot.group(name="bot", invoke_without_command=True)
async def bot_group(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.send(embed=get_error_embed(ctx.author, "You are not authorized to use this command."))
        return
    embed = discord.Embed(
        color=0xE77E23,
        title="<:exclusive:1497225869024821339> Bot Control Panel",
        description="Use the commands below to manage the bot."
    )
    embed.set_author(name="Owner Panel", icon_url=ctx.author.display_avatar.url)
    embed.add_field(name="!bot reset", value="Resets ALL user booster data.", inline=False)
    embed.add_field(name="!bot addcd <seconds>", value="Sets a global cooldown duration.", inline=False)
    embed.add_field(name="!bot setcd <amount>", value="Sets actions allowed before cooldown.", inline=False)
    await ctx.send(embed=embed)

@bot_group.command(name="reset")
async def bot_reset(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.send(embed=get_error_embed(ctx.author, "You are not authorized to use this command."))
        return
    global user_boosters, user_cooldown, user_action_count
    user_boosters.clear()
    user_cooldown.clear()
    user_action_count.clear()
    await ctx.send(embed=get_success_embed(ctx.author, "All user booster data has been reset."))

@bot_group.command(name="addcd")
async def bot_addcd(ctx, seconds: int = None):
    if ctx.author.id != OWNER_ID:
        await ctx.send(embed=get_error_embed(ctx.author, "You are not authorized to use this command."))
        return
    global cooldown_seconds
    if seconds is None or seconds < 0:
        await ctx.send(embed=get_error_embed(ctx.author, "Invalid value. Use !bot addcd <seconds> (positive integer)."))
        return
    cooldown_seconds = seconds
    await ctx.send(embed=get_success_embed(ctx.author, f"Global cooldown set to {seconds} seconds."))

@bot_group.command(name="setcd")
async def bot_setcd(ctx, amount: int = None):
    if ctx.author.id != OWNER_ID:
        await ctx.send(embed=get_error_embed(ctx.author, "You are not authorized to use this command."))
        return
    global cooldown_threshold
    if amount is None or amount < 1:
        await ctx.send(embed=get_error_embed(ctx.author, "Invalid value. Use !bot setcd <amount> (positive integer)."))
        return
    cooldown_threshold = amount
    await ctx.send(embed=get_success_embed(ctx.author, f"Cooldown will trigger after {amount} pause/resume actions per user."))

# --- ORIGINAL COMMANDS ---
@bot.group(name="sys", invoke_without_command=True)
async def sys_group(ctx):
    embed = discord.Embed(
        color=discord.Color.red(),
        description=f"<:error:1497146924518867065> INVALID USAGE\n\nUse !sys addbooster <type> or !sys addall"
    )
    embed.set_author(name="error", icon_url=ctx.author.display_avatar.url)
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1497146924518867065.png")
    await ctx.send(embed=embed)

@sys_group.command(name="addbooster")
async def add_booster(ctx, b_type: str = None):
    if not b_type or b_type not in BOOSTER_DATA:
        await ctx.send(embed=get_error_embed(ctx.author, f"{b_type} is not a valid booster type.\nAvailable: triple.xp.24h, leg.explore.luck.1h, leg.explore.cd.1h, leg.explore.eff.1h"))
        return

    uid = ctx.author.id
    if uid not in user_boosters:
        user_boosters[uid] = {"active": [], "paused": []}

    source = BOOSTER_DATA[b_type]
    existing = None
    for b in user_boosters[uid]['active']:
        if b['name'] == source['name']:
            existing = b
            break
    if not existing:
        for b in user_boosters[uid]['paused']:
            if b['name'] == source['name']:
                existing = b
                break

    if existing:
        existing['hours'] += source['hours']
        await ctx.send(embed=get_success_embed(ctx.author, f"Stacked! {source['emojis']} {source['name']} is now {existing['hours']} hours."))
    else:
        user_boosters[uid]['active'].append(source.copy())
        await ctx.send(embed=get_success_embed(ctx.author, f"Added {source['emojis']} {source['name']}."))

@sys_group.command(name="addall")
async def add_all_boosters(ctx):
    uid = ctx.author.id
    if uid not in user_boosters:
        user_boosters[uid] = {"active": [], "paused": []}
    
    added_count = 0
    for b_type, source in BOOSTER_DATA.items():
        # Check if booster already exists (active or paused)
        existing = None
        for b in user_boosters[uid]['active']:
            if b['name'] == source['name']:
                existing = b
                break
        if not existing:
            for b in user_boosters[uid]['paused']:
                if b['name'] == source['name']:
                    existing = b
                    break
        
        if existing:
            existing['hours'] += source['hours']
        else:
            user_boosters[uid]['active'].append(source.copy())
            added_count += 1
    
    await ctx.send(embed=get_success_embed(ctx.author, f"Added {added_count} new boosters and stacked existing ones!"))

@bot.command(name="booster")
async def booster_view(ctx):
    view = BoosterManager(ctx.author)
    view.message = await ctx.send(embed=get_booster_panel_embed(ctx.author), view=view)

bot.run("tokem")
