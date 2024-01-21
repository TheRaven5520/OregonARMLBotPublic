import os
import dotenv
dotenv.load_dotenv()
TOKEN = os.getenv("TOKEN")

import discord
from discord.utils import get
from discord.ext import commands

from functionality import *
from discordHelper import discordHelper
from google_sheets.googleSheetsUpdater import google_sheet_updater
import asyncio

from itertools import cycle
status = cycle(['Oregon ARML POTDs', 'Oregon ARML POTDs.'])
from discord.ext import tasks

from textwrap import dedent 

def chain(*decs):
    def deco(f): 
        for dec in reversed(decs): f = dec(f)
        return f
    return deco

def check_float(x):
    '''checks if string x is a float'''
    try:
        x = float(x)
        return True
    except:
        return False

##################################################################################
# SET UP DISCORD BOT, CONSTANTS, AND LOAD DATA

MAX_ROW_PUBLIC_LEADERBOARD = 20
my_userid = 568622241902886934
DATA_DIR = "/home/ec2-user/PrivateData/"

driver, intents, client, helper = None, None, None, None

driver = Driver()
intents = discord.Intents.all()
client = commands.Bot(command_prefix='-', intents=intents)
gs_helper = google_sheet_updater()

##################################################################################
# SECURITY & STORAGE

def is_me(ctx: commands.Context) -> bool:
    '''
    Check if the user invoking the command is me.

    @param ctx (commands.Context): The context object representing the invocation context.

    @return (bool): Returns a boolean value indicating whether the user is me.
    '''
    return ctx.author.id == my_userid
def is_admin_channel(ctx: commands.Context) -> bool:
    '''
    Check if the provided context's channel is the admin channel.

    @param ctx (commands.Context): The context object representing the invocation context.

    @return (bool): Returns a boolean value indicating whether the context's channel is the admin channel.
    '''
    return is_me(ctx) or ctx.channel.id == constants["admin_channel"]
def is_administrator(ctx: commands.Context) -> bool:
    '''
    Check if the user invoking the command is an administrator.

    @param ctx (commands.Context): The context object representing the invocation context.
    
    @return (bool): Returns a boolean value indicating whether the user is an administrator.
    '''
    return is_me(ctx) or bool(ctx.author.guild_permissions.administrator)

def wrapper_funcs(func):
    async def wrapped_func(ctx, *args, **kwargs):
        with open(f"{DATA_DIR}data/log.txt", "a") as file:
            file.write(f"[{pd.Timestamp.now(tz=timezone)}] {ctx.author.id} -- {ctx.author.name} -- {ctx.author.display_name}: {func.__name__}({', '.join(map(str, args))}))" + "\n")
        value = await func(ctx, *args, **kwargs)
        store_data()
        return value 
    wrapped_func.__name__ = func.__name__
    wrapped_func.__doc__ = func.__doc__
    return wrapped_func

##################################################################################
# POTD USER COMMANDS

# Command to add an answer to the current season
@chain(client.command(), wrapper_funcs)
async def answer(ctx: commands.Context, problem_id: str, answer: str = "") -> None:
    '''
    Submits answer 'answer' to problem with id 'problem_id'.

    @param problem_id (int): The ID of the problem to submit the answer to.
    @param answer (str): The text answer to submit. Defaults to "" so you can ignore if you submit an image.
    @optional - attach image

    @returns: None
    '''

    season = driver.season
    problem = season.get_problem(problem_id)
    if not problem:
        await ctx.send("Problem not found")
        return
    
    try:
        result = (int(problem.answer) == int(answer))
        if not problem.in_interval():
            await ctx.send("Outside time interval.")
            return
        season.grade_answer(problem_id, str(ctx.author.id), (1 if result else 0))
        result = "correct" if result else "wrong"
        await ctx.send(f"Your answer `{answer}` was {result}.")
        channel = client.get_channel(int(constants["admin_channel"]))
        await channel.send(f"{ctx.author.display_name}'s answer of `{answer}` was marked {result}.")
        return
    except:
        pass
    
    filename = await helper.save_image_from_text(ctx)
    result, text = season.add_answer(problem_id, str(ctx.author.id), answer, filename)
    await ctx.send(text)
    if result:
        channel = client.get_channel(int(constants["admin_channel"]))
        await channel.send(f"Answer Added by {ctx.author.display_name}.")
    return 

# Command to add an answer to the current season
@chain(client.command(), wrapper_funcs)
async def rankings(ctx: commands.Context, season=None) -> None:
    '''
    Retrieves top rankings for a specific season, current season by default.

    @param season (int, optional): Optional. The season for which rankings are to be retrieved. Defaults to the current season.
    
    @returns: None
    '''
    if season == None: season = str(driver.season.CURRENT_SEASON)
    await ctx.send(string_rankings(get_rankings_df(season, True)))

@chain(client.command(), wrapper_funcs) 
async def myrank(ctx, season=None):
    '''Retrieves your rank, points for specific season, current season by default.
    
    @param season (int, optional): Optional. The season for which rankings are to be retrieved. Defaults to current season.
    
    @returns: None'''
    if season == None: season = str(driver.season.CURRENT_SEASON)
    rankings_df = get_rankings_df(season)
    if str(ctx.author.id) in rankings_df['Member ID'].values: 
        await ctx.send(string_rankings(rankings_df[rankings_df['Member ID'] == str(ctx.author.id)]))
    else:
        await ctx.send(f"You did not have any points in that season.")

@chain(client.command(), wrapper_funcs)
async def curseas(ctx):
    '''Gets current season'''
    await ctx.send(driver.season.CURRENT_SEASON)

##################################################################################
# POTD LEADERBOARD

def get_rankings_df(season_id: str, top: bool = False) -> pd.core.frame.DataFrame:
    """
    Retrieves the rankings DataFrame for a specific season.
    
    @param season_id (int): The season for which rankings are to be retrieved.
    
    @return (pd.core.frame.DataFrame): A DataFrame containing the rank, member ID, and points for each member in the rankings.
    """
    df = pd.DataFrame(driver.season.get_grades(season_id).items(), columns=['Member ID', 'Points']).sort_values('Points', ascending=False)
    df['Rank'] = df['Points'].rank(method='min', ascending=False).astype(int)
    if len(df) == 0: return df 
    if top: df = df[df['Rank'] <= int(df.iloc[min(MAX_ROW_PUBLIC_LEADERBOARD - 1, len(df) - 1)]['Rank'])]
    return df[['Rank', 'Member ID', 'Points']]
def string_rankings(df: pd.core.frame.DataFrame) -> str:
    """
    Returns a formatted string representation of the rankings DataFrame.

    @param df (pd.core.frame.DataFrame): The DataFrame containing the rankings.
    
    @return (str): A string representation of the rankings in a tabular format.
    """
    if df.empty:
        return "No one has any points."
    guild = helper.guild()
    df.loc[:, 'Member ID'] = df['Member ID'].apply(lambda x: guild.get_member(int(x)).display_name if guild.get_member(int(x)) else 'Unknown Member')
    return "```" + df.to_string(index=False) + "```"
async def update_leaderboard() -> None:
    '''
    Update the leaderboard message with the latest rankings.

    @returns: None
    '''
    global constants
    chn = helper.get_channel(constants["leaderboard_output_channel"])
    new_text = string_rankings(get_rankings_df(str(driver.season.CURRENT_SEASON), True))
    if constants["leaderboard_output_message"] == None:
        constants["leaderboard_output_message"] = await chn.send(new_text)
        constants["leaderboard_output_message"] = constants["leaderboard_output_message"].id 
    else:
        try:
            msg = await chn.fetch_message(constants["leaderboard_output_message"])
            await msg.edit(content=new_text)
        except:
            constants["leaderboard_output_message"] = await chn.send(new_text)
            constants["leaderboard_output_message"] = constants["leaderboard_output_message"].id 
    store_data()

@chain(client.command(), commands.check(is_administrator), wrapper_funcs)
async def sranks(ctx, season = None, rankmember: bool = False):
    '''[Admin only] Retrieves rankings for season 'season', current season if left blank, sorted alphabetically by name.

    @param rankmember (bool, optional): Optional. Whether to add rank & member columns. Defaults to False.
    @param season (int, optional): Optional. The season for which rankings are to be retrieved. Defaults to current season.

    @returns None:
    '''
    if season == None: season = str(driver.season.CURRENT_SEASON)
    if rankmember != False: rankmember = rankmember[0].lower() in ['t', 'y']

    df = get_rankings_df(season)
    members_with_role = [str(member.id) for member in ctx.guild.members if constants["year_role"] in [role.id for role in member.roles]]

    for member_id in members_with_role:
        if member_id not in df['Member ID'].values:
            df.loc[len(df.index)] = [None, member_id, 0]
    df = df[df['Member ID'].isin(members_with_role)].sort_values('Points', ascending=False)
    df['Rank'] = df['Points'].rank(method='min', ascending=False).astype(int)
    guild = helper.guild()
    df.loc[:, 'Member ID'] = df['Member ID'].apply(lambda x: guild.get_member(int(x)).display_name if guild.get_member(int(x)) else 'Unknown Member')
    df = df.sort_values('Member ID', ascending=True, key=lambda x:x.str.lower())
    df = df[["Rank", "Member ID", "Points"]]
    if not rankmember: df = df[["Points"]]
    await ctx.send("```" + df.to_string(header=False, index=False, justify="right")  + "```")

@chain(client.command(), commands.check(is_administrator), wrapper_funcs)
async def allrankings(ctx, season=None):
    '''[Admin only] Retrieves rankings for season 'season', current season if left blank.
    
    @param season (int, optional): Optional. The season for which rankings are to be retrieved. Defaults to current season.
    
    @returns: None'''
    if season == None: season = str(driver.season.CURRENT_SEASON)
    await ctx.send(string_rankings(get_rankings_df(season)))

@tasks.loop(minutes=5)
async def edit_leaderboard_msg():
    await update_leaderboard()

@edit_leaderboard_msg.before_loop
async def before_edit_leaderboard_msg():
    current_time = datetime.datetime.now()
    seconds_until_next_interval = (5 - current_time.minute % 5) * 60 + (60 - current_time.second)
    await asyncio.sleep(seconds_until_next_interval)

##################################################################################
# POTD PROBLEMS 

@chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
async def newprob(ctx, answer="None", start_time=None, end_time=None, problem_text=None):
    '''[Admin only] Adds new problem, sends it in designated problem-of-the-day channel.\nOnly accepts answers within time interval from start_time to end_time
    
    @param answer (int): Integer answer, type NA if non integer answer.
    @param start_time, end_time (dates): Format "MM-DD-YYYY HH:MM:SS"
    @param problem_text (string): In quotes, problem text to display

    @returns: None
    '''
    
    if start_time == None: start_time = (pd.Timestamp.now(tz=timezone).replace(hour=0, minute=0, second=0, microsecond=0) + pd.Timedelta(days=1)).strftime("%m-%d-%Y")
    if end_time == None: end_time = (pd.Timestamp(start_time, tz=timezone)+pd.Timedelta(days=1)).strftime("%m-%d-%Y")
    if problem_text == None: problem_text = pd.Timestamp(start_time, tz=timezone).strftime(f"<@&{constants['year_role']}> %m/%d/%Y Problem:")

    if constants["potd_output_channel"] == None:
        await ctx.send("No output channel.")
        return

    channel = client.get_channel(constants["potd_output_channel"])
    image_filename = await helper.save_image_from_text(ctx)
    result, text, problem = driver.season.add_problem(problem_text, answer, start_time, end_time)
    
    driver.add_scheduled_message({
        "text": dedent(f"""**{ctx.author.display_name}:** 
                           {problem_text}
                           **Season ID:** {driver.season.CURRENT_SEASON}
                           **Problem ID:** {problem.id}

                           Solutions accepted from **{pd.Timestamp(start_time, tz=timezone).strftime("%m/%d/%Y, %H:%M")}** till **{pd.Timestamp(end_time, tz=timezone).strftime("%m/%d/%Y, %H:%M")}**.
                           
                           Submit solutions using the command `-answer "Problem_ID" "ANSWER_TEXT"` Please DM your solutions to the bot. To attach an image, simply copy paste it onto your message."""),
        "filename": image_filename,
        "time": start_time,
        "channel": constants["potd_output_channel"]
    })

    image_filename = await helper.save_image_from_text(ctx)
    while image_filename != None:
        driver.add_scheduled_message({
            "text":"",
            "filename": image_filename,
            "time": end_time, 
            "channel": constants["potd_solution_channel"]
        })
        image_filename = await helper.save_image_from_text(ctx)

    await ctx.send("Problem added successfully.")

@chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
async def deleteprob(ctx, problem_id):
    '''[Admin only] Deletes a problem from the current season based on its ID.
    
    @param problem_id (int)'''
    result, text = driver.season.delete_problem(problem_id)
    await ctx.send(text)

@chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
async def upd_ans(ctx, problem_id, answer):
    '''[Admin only] Sets new answer to problem 

    @param problem_id (int)
    @param answer: new answer, "None" or (int)

    @returns: None'''
    result, text = driver.season.set_answer(problem_id, answer)
    await ctx.send(text)

@chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
async def upd_season(ctx, problem_id, season_id):
    '''[Admin only] Sets season for problem 

    @param problem_id (int)
    @param season_id (int)

    @returns: None'''
    result, text = driver.season.set_season(problem_id, season_id)
    await ctx.send(text)

##################################################################################
# POTD UPDATE USER DATA 

@chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
async def grade(ctx, grade, feedback = None, attempts_to_add = 1):
    '''[Admin only] Grades last answer as correct or wrong.\nis_correct = True (if grading as correct) or False (if grading is wrong)
    
    @param grade (int): 0 to 1 scale
    @param feedback (str, optional): Feedback to return the submitter
    @param attempts_to_add (int): attempts to add
    
    @returns: None'''

    # check input grade
    if not check_float(grade):
        await ctx.send("Please enter a decimal number for the grade between 0 and 1 (outside the range if extra credit).")
        return
    grade = float(grade)

    # get season, get last problem
    result, last = driver.season.get_last_ungraded()
    if not result:
        await ctx.send("No problems to grade.")
        return
    
    member = await client.fetch_user(int(last['person_id']))
    file = discord.File(f"{IMAGES_DIR}images/{last['filename']}") if last["filename"] else None

    driver.season.grade_last(grade, int(attempts_to_add))

    message = f"Grader: {ctx.message.author.nick}\nYour answer `{last['answer']}` was graded {grade}/1."
    if feedback != None: message += "\n\n**Feedback: **" + feedback
    await member.send(content=message, file=file)
    await ctx.send("Last answer graded successfully.")

@chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
async def last(ctx, gnext = "False"):
    '''[Admin only] Retrieves last ungraded answer and outputs it.
    
    @params gnext(bool, default=False): whether to get next ungraded problem. Put True if you want next, nothing otherwise

    @returns: None'''
    result, last = driver.season.get_last_ungraded(gnext.lower()[0] in ['t', 'y'])
    if not result:
        await ctx.send("No problems to grade.")
        return
    problem = driver.season.get_problem(last['problem_id'])
    if not problem:
        await ctx.send("Problem not found.")
        return
    
    name = ctx.guild.get_member(int(last['person_id'])).name
    disc = ctx.guild.get_member(int(last['person_id'])).discriminator
    realname = ctx.guild.get_member(int(last['person_id'])).display_name
    file = discord.File(f"{IMAGES_DIR}images/{last['filename']}") if last["filename"] else None
    await ctx.send(content=f"Problem Text: {problem.problem_text}\nProblem ID: {problem.id}\nAnswer Text: {last['answer']}\nPerson: {realname} -- {name}#{disc}", file=file)

# Command to update the number of attempts for a person in a problem (only for administrators)
@chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
async def upd_attempts(ctx, problem_id, person_name, num_attempts):
    '''[Admin only] Updates number of attempts 'person_name' took for problem 'problem_id' by adding 'num_attempts'.
    
    @param problem_id (int)
    @param person_name (string): mention person using @
    @param num_attempts (int): will add this to current number of attempts
    
    @returns: None'''
    person_name = person_name[2:-1]
    season = driver.season
    result, text, person = season.set_attempts(problem_id, person_name, int(num_attempts))
    await ctx.send(text)
    if result:
        member = await client.fetch_user(int(person_name))
        await member.send(f"Grader: {ctx.message.author.nick}\nYour number of attempts to problem {problem_id} has been updated to {person.num_attempts}.")

# Command to update the correctness attribute for a person in a problem (only for administrators)
@chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
async def upd_grade(ctx, problem_id, person_name, new_grade, feedback=None):
    '''[Admin only] Toggles whether 'person_name' got problem 'problem_id' correct.
    
    @param problem_id (int)
    @param person_name (string): mention person using @
    @param new_grade (int): new grade to give
    
    @returns: None'''
    person_name = person_name[2:-1]

    if not check_float(new_grade):
        await ctx.send(f"Grade {new_grade} is not a float.")
    new_grade = float(new_grade)
    result, text, person = driver.season.set_grade(problem_id, person_name, new_grade, False)
    
    await ctx.send(text)
    if result:
        member = await client.fetch_user(int(person_name))
        if feedback:
            await member.send(feedback)
        await member.send(f"Grader: {ctx.message.author.nick}\nYour answer to problem {problem_id} has been rescored to {person.grade}.")

##################################################################################
# POTD DATA 

def load_data():
    global constants
    driver.load_data()
    with open(f"{DATA_DIR}data/constants.json", "r") as file:
        constants = json.load(file)
    driver.season.CURRENT_SEASON = constants["CURRENT_SEASON"]
def store_data():
    global constants
    driver.store_data()
    constants["CURRENT_SEASON"] = driver.season.CURRENT_SEASON
    with open(f"{DATA_DIR}data/constants.json", "w") as file:
        json.dump(constants, file, indent=4)

@chain(client.command(), commands.check(is_admin_channel))
async def store(ctx):
    '''[Admin only] Manually stores data into data.csv & ungraded.json files.
    
    @returns: None'''
    store_data()
    await ctx.send("Data stored in data.csv successfully.")

@chain(client.command(), commands.check(is_admin_channel))
async def load(ctx):
    '''[Admin only] Manually loads data from data.csv & ungraded.json files.
    
    @returns: None'''
    load_data()
    await ctx.send("Data loaded from data.csv successfully.")

load_data()

##################################################################################
# SCHEDULE POSTS

@chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
async def schedule(ctx, channel, text, time):
    '''[Admin only] Schedules message "text" in channel "channel" at time "time".
    
    @param channel (string): tag channel using #
    @param text (string): text to send
    @param time (date): format "MM-DD-YYYY HH:MM:SS", when to send message
    
    @returns: None'''
    image_filename = await helper.save_image_from_text(ctx)
    driver.add_scheduled_message({
        "text": f"**{ctx.author.display_name}:**\n" + text, 
        "filename": image_filename,
        "time": time, 
        "channel": channel[2:-1]
    })
    image_filename = await helper.save_image_from_text(ctx)
    while image_filename != None:
        driver.add_scheduled_message({
            "text": f"**{ctx.author.display_name}:**",
            "filename": image_filename,
            "time": time, 
            "channel": channel[2:-1]
        })
        image_filename = await helper.save_image_from_text(ctx)
    
    await ctx.send(f"Message scheduled at {time}")

@chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
async def listsched(ctx):
    '''[Admin only] Lists scheduled messages.

    @params None

    @returns None'''
    if len(driver.scheduled_messages) == 0:
        await ctx.send("No scheduled messages.")
        return 
    for j, i in driver.scheduled_messages.items():
        file = None
        if i['filename']: file = discord.File(f"{IMAGES_DIR}images/{i['filename']}")
        await ctx.send(dedent(f"""**ID: {j}**
                                  **Text**: {i['text']}
                                  **Time**: {i['time']}
                                  **Channel**: <#{i['channel']}>"""), file=file)

@chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
async def remsched(ctx, smesid):
    '''[Admin only] Removes a scheduled message. Run -listsched first to see scheduled messages.

    @param smesid (int): id of scheduled message to remove

    @returns None'''
    
    if str(smesid) in driver.scheduled_messages:
        x = driver.scheduled_messages.pop(str(smesid))
        if x["filename"]: os.remove(f"{IMAGES_DIR}images/{x['filename']}")
        await ctx.send("Successfully removed scheduled message.")
    else:
        await ctx.send("Could not find scheduled message")

@tasks.loop(minutes=1)
async def check_scheduled_messages():
    '''sends scheduled messages on time'''
    global constants
    scheduled_messages = [(i, j) for i, j in driver.scheduled_messages.items() if pd.Timestamp(j["time"], tz=timezone) <= pd.Timestamp.now(tz=timezone)]
    for i, j in scheduled_messages:
        try:
            if not j["text"]: j["text"] = "​"
            channel = client.get_guild(constants["server_id"]).get_channel(int(j["channel"]))
            file = discord.File(f"{IMAGES_DIR}images/{j['filename']}") if j["filename"] else None
            await channel.send(content=j["text"], file=file)
            if j['filename']: os.remove(f"{IMAGES_DIR}images/{j['filename']}")
        except Exception as e:
            channel = helper.get_channel(constants["admin_channel"])
            await channel.send(f"Error sending scheduled message.")
            print(e)
        driver.scheduled_messages.pop(i)
    store_data()
    
@check_scheduled_messages.before_loop
async def before_check_scheduled_messages():
    current_time = datetime.datetime.now()
    seconds_until_next_interval = 60 - current_time.second
    await asyncio.sleep(seconds_until_next_interval)

##################################################################################
# STATISTICS & COMMUNICATION

@chain(client.command(), commands.check(is_administrator), wrapper_funcs)
async def reactstats(ctx, post_id):
    '''
    [Admin only] Gets all stats about reactions in a post.

    @param ctx (commands.Context): The context of the command.
    @param post_id (int): The ID of the post to get stats for.

    @returns: None
    '''
    post_id = int(post_id)
    
    try:
        post = await helper.get_post(post_id)
    except Exception as e:
        await ctx.send(f"Could not find post with id {post_id}.")
        print(e)
        return

    # first print each emoji & list of people who reacted to it
    reacting_users = {}
    for reaction in post.reactions:
        list = ", ".join([user.mention async for user in reaction.users()])
        await ctx.send(f"**{reaction.emoji}**: {list}", silent=True)
        async for user in reaction.users():
            if user not in reacting_users: reacting_users[user] = [reaction.emoji]
            else: reacting_users[user].append(reaction.emoji)

    # print all users that have no emoji 
    users_list = [user.mention for user in post.guild.members if user not in reacting_users and not user.bot]
    await ctx.send(f"**No reaction**: {', '.join(users_list) if len(users_list) > 0 else 'None'}", silent=True)

    # second print each person who reacted more than once & the emojis they reacted with 
    message = "More than one reaction:\n"
    for user, emojis in reacting_users.items():
        if len(emojis) > 1:
            message += f"**{user.mention}**: {', '.join(emojis)}\n"

    await ctx.send(message, silent=True)

    return 

@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def send(ctx, message, roles_to_match = "None", roles_to_exclude = "None", user_ids_to_match = "None", user_ids_to_exclude = "None", post_id = "None", additional_eval = "None"):
    '''
    Sends a message to all users that match the specified criteria.

    @param ctx (commands.Context): The context of the command.
    @param roles_to_match (list of @s, separated by spaces, in quotes): A list of role IDs to match.
    @param roles_to_exclude (list of @s, separated by spaces, in quotes): A list of role IDs to exclude.
    @param user_ids_to_match (list of @s, separated by spaces, in quotes): A list of user IDs to match.
    @param user_ids_to_exclude (list of @s, separated by spaces, in quotes): A list of user IDs to exclude.
    @param post_id (int): The ID of the post to check. Send a message to everyone who has not put a reaction on the post yet.

    @returns: None
    '''

    # Get list of all users in server 
    guild = ctx.guild 
    users = guild.members

    if roles_to_match == "None": roles_to_match = None
    if roles_to_exclude == "None": roles_to_exclude = None
    if user_ids_to_match == "None": user_ids_to_match = None
    if user_ids_to_exclude == "None": user_ids_to_exclude = None
    if post_id == "None": post_id = None

    if roles_to_match != None: roles_to_match = [int(role[3:-1]) for role in roles_to_match.strip().split(" ")]
    if roles_to_exclude != None: roles_to_exclude = [int(role[3:-1]) for role in roles_to_exclude.strip().split(" ")]
    if user_ids_to_match != None: user_ids_to_match = [int(user_id[2:-1]) for user_id in user_ids_to_match.strip().split(" ")]
    if user_ids_to_exclude != None: user_ids_to_exclude = [int(user_id[2:-1]) for user_id in user_ids_to_exclude.strip().split(" ")]
    if post_id != None: post_id = int(post_id)

    users = helper.get_users(roles_to_match, roles_to_exclude, user_ids_to_match, user_ids_to_exclude)
    if post_id != None:
        try:
            post = await helper.get_post(post_id)
        except Exception as e:
            await ctx.send(f"Could not find post with id {post_id}.")
            print(e)
            return

        reacting_users = set()
        for reaction in post.reactions:
            async for user in reaction.users():
                reacting_users.add(user)
        users = [user for user in users if user not in reacting_users]

    for user in users:
        try:
            customized_message = message.replace("`ping`", user.mention)
            customized_message = customized_message.split("{")
            for i in range(1, len(customized_message)):
                customized_message[i] = str(eval(customized_message[i].split("}")[0])) + customized_message[i].split("}")[1]
            customized_message = "".join(customized_message)
            await user.send(customized_message)
        except:
            ctx.send(f"Failed to send to {user.display_name}.")

    await ctx.send(f"Message sent to {[user.display_name for user in users]}.")
    await ctx.send(f"Message not sent to {[user.display_name for user in guild.members if user not in users and not user.bot]}.")

    return 

##################################################################################
# GOOGLE SHEETS COMMANDS

@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_update_role(ctx: commands.Context, role: str) -> None:
    '''Updates the people in the google sheet. Takes in a list of roles to update.
    
    @param ctx (commands.Context): The context of the command.
    @param role (str): The role to set as people for the google sheet.

    @returns: None
    '''
    try:
        gs_helper.update_people([str(user.display_name) for user in helper.get_users([int(role[3:-1])])])
        await ctx.send(f"Updated sheet's people to all with role.")
    except Exception as e:
        await ctx.send(e)


@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_update_people(ctx: commands.Context, people: str) -> None:
    '''[Admin only] Updates the people in the google sheet. Takes in a list of people to update.

    @param ctx (commands.Context): The context of the command.
    @param *args (list): The list of people to set as people for the google sheet.

    @returns: None
    '''
    gs_helper.update_people([helper.get_member(int(user[2:-1])).display_name for user in people.split(' ')])

# gs_create_sheet(sheet_name)
@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_create_sheet(ctx: commands.Context, sheet_name: str) -> None:
    '''[Admin only] Creates a google sheet with the given name.

    @param ctx (commands.Context): The context of the command.
    @param sheet_name (str): The name of the sheet to create.

    @returns: None
    '''
    gs_helper.update_display(sheet_name)

# gs_create_test_sheet(sheet_name, num_problems)
@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_create_test_sheet(ctx: commands.Context, sheet_name: str, num_problems: int) -> None:
    '''[Admin only] Creates a test sheet with the given name and number of problems.

    @param ctx (commands.Context): The context of the command.
    @param sheet_name (str): The name of the sheet to create.
    @param num_problems (int): The number of problems to create.

    @returns: None
    '''
    gs_helper.create_test_sheet(sheet_name, int(num_problems))

# gs_add_column(sheet_name, column_name, *args) where *args is list of values 
@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_add_column(ctx: commands.Context, sheet_name: str, column_name: str) -> None:
    '''[Admin only] Adds a column to the google sheet.

    @param ctx (commands.Context): The context of the command.
    @param sheet_name (str): The name of the sheet to add the column to.
    @param column_name (str): The name of the column to add.

    @returns: None
    '''
    gs_helper.add_column(sheet_name, column_name) 

# gs_add_potd_season()
@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_add_potd_season(ctx: commands.Context, date: str = "None", season_id: str = "None", sheet_name: str = "POTD Sheet") -> None:
    '''[Admin only] Adds a new season to the google sheet.

    @param ctx (commands.Context): The context of the command.
    @param date (str): The date of the season to add.
    @param season_id (str): The ID of the season to add.

    @returns: None
    '''
    if season_id == "None": season_id = str(driver.season.CURRENT_SEASON)
    gs_helper.add_potd_season(driver, helper, sheet_name, season_id, date)

# gs_del_sheet
@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_del_sheet(ctx: commands.Context, sheet_name: str) -> None:
    '''[Admin only] Deletes a google sheet.

    @param ctx (commands.Context): The context of the command.
    @param sheet_name (str): The name of the sheet to delete.

    @returns: None
    '''
    gs_helper.del_ws(sheet_name)

# gs_store_sheet
@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_store_sheet(ctx: commands.Context, sheet_name: str) -> None:
    '''[Admin only] Stores the google sheet.

    @param ctx (commands.Context): The context of the command.
    @param sheet_name (str): The name of the sheet to store.

    @returns: None
    '''
    gs_helper.store_display(sheet_name)

# potd_rankings_overall

##################################################################################
# RUN BOT

@client.event 
async def on_ready():
    '''starts some looped tasks

    @returns: None
    '''
    print('Bot is ready')
    still_alive.start()
    change_status.start()
    edit_leaderboard_msg.start()
    check_scheduled_messages.start()

##### PRINTS BOT STILL ALIVE
@tasks.loop(minutes=5)
async def still_alive():
    print("Still alive...")

##### KEEPS BOT ALIVE
@tasks.loop(minutes=5)
async def change_status():
  await client.change_presence(activity=discord.Game(next(status)))

helper = discordHelper(client, constants["server_id"])

client.run(TOKEN)

##################################################################################