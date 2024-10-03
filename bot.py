from discordHelper import *

dotenv.load_dotenv()
TOKEN = os.getenv("TOKEN")

# arml specific functionality
from POTDfunctionality import *
from google_sheets.googleSheetsUpdater import google_sheet_updater
from user_data.user_data import user_data

# python functionality
from textwrap import dedent
import datetime

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

potd_driver, helper, gs_helper, ud = None, None, None, None

# potd_driver = Driver()

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
    if is_me(ctx): return True
    if ctx.guild is None: return False
    return ctx.channel.id == constants["admin_channel"]
def is_administrator(ctx: commands.Context) -> bool:
    '''
    Check if the user invoking the command is an administrator.

    @param ctx (commands.Context): The context object representing the invocation context.
    
    @return (bool): Returns a boolean value indicating whether the user is an administrator.
    '''
    if is_me(ctx): return True
    if ctx.guild is None: return False
    return bool(ctx.author.guild_permissions.administrator)

async def async_exec(code, ctx):
    async def func(ctx):
        exec(
            "async def __ex(ctx): " +
            "".join(f"\n    {l}" for l in code.split("\n")),
            globals()
        )
        return await globals()["__ex"](ctx)
    return await func(ctx)
@chain(client.command(), commands.check(is_me))
async def ev(ctx: commands.Context) -> None:
    '''
    Evaluates the provided code.

    @param ctx (commands.Context): The context object representing the invocation context.
    @param code (str): The code to evaluate.

    @returns: None
    '''
    try:
        await ctx.send("Please enter the code to evaluate.")
        chk = lambda m: m.author == ctx.author and m.channel == ctx.channel
        msg = await client.wait_for('message', check=chk, timeout=60)
        code = msg.content.split('```')[1]
        await async_exec(code, ctx)
    except Exception as e:
        await ctx.send(f"``` Error: {e}```")
        await ctx.send(f"```{traceback.format_exc()}```")

def wrapper_funcs(func):
    async def wrapped_func(ctx, *args, **kwargs):
        with open(f"{DATA_DIR}data/log.txt", "a") as file:
            file.write(f"[{pd.Timestamp.now(tz=timezone)}] {ctx.author.id} -- {ctx.author.name} -- {ctx.author.display_name}: {func.__name__}({', '.join(map(str, args))}))" + "\n")
        try:
            value = await func(ctx, *args, **kwargs)
        except Exception as e:
            log_error(f"Error in {func.__name__}({', '.join(map(str, args))}) -- {e}")
            await ctx.send("Unknown error in command. Please contact the bot administrator.")
            return None
        store_data()
        return value
    wrapped_func.__name__ = func.__name__
    wrapped_func.__doc__ = func.__doc__
    return wrapped_func

##################################################################################
# USER DATA

def map_names(df, column_name):
    id_to_name = {str(user.id): user.display_name for user in helper.guild().members}
    df[column_name] = df[column_name].map(lambda x: id_to_name.get(x, x))

def get_ud_data():
    '''
    Retrieves the user data for the current season in a DF
    ''' 
    df = ud.data_as_df()
    df = pd.DataFrame({key: df.get(key, '-') for key in ud.keys})

    # add year_role users if not alr in by comparing useR_ids 
    users_to_add = [str(user.id) for user in helper.get_users([constants["year_role"]]) if str(user.id) not in df.index]
    df = pd.concat([df, pd.DataFrame(index=users_to_add, columns=df.columns).fillna("-")], axis=0) 

    # add _Competitor column mapping user ids --> id_to_role[user.id]
    id_to_role = {str(user.id): (1 if any(constants["year_role"] == role.id for role in user.roles) else 0) for user in helper.guild().members}
    df["Competitor_"] = df.index.map(lambda x : id_to_role.get(x, x))
    df = df[['Competitor_'] + [col for col in df.columns if col != 'Competitor_']]

    # # make display_names
    # member_ids = [member.id for member in helper.guild().members]
    # df.index = [helper.guild().get_member(int(index)).display_name for index in df.index if int(index) in member_ids]

    return df

@chain(client.command(), wrapper_funcs)
async def ud_mydata(ctx: commands.Context) -> None:
    '''
    Retrieves the user data for the invoking user.

    @param ctx (commands.Context): The context object representing the invocation context.

    @returns: None
    '''
    df = get_ud_data()

    # get member & create if not already in DF
    if str(ctx.author.id) not in df.index:
        ud.create_user(str(ctx.author.id))
        df.loc[str(ctx.author.id)] = '-'

    # transpose 
    df = df.T.loc[~df.columns.str.endswith('_'), [str(ctx.author.id)]].rename(columns={str(ctx.author.id): ctx.author.display_name})

    await ctx.send(f"```{df.to_string(index=True)}```")

@chain(client.command(), commands.check(is_administrator), wrapper_funcs)
async def ud_update_gs(ctx: commands.Context) -> None:
    '''
    [Admin only] Updates the google sheet with the user data.

    @param ctx (commands.Context): The context object representing the invocation context.

    @returns: None
    '''
    df = get_ud_data()
    df = df.reset_index().rename(columns={"index": "Name"})


    map_names(df, "Name")
    log_error(df, False)

    if ud.post_df(df): 
        await ctx.send(f"Data updated successfully.")
        return 
    
    await ctx.send(f"Data failed to update.")

@chain(client.command(), commands.check(is_administrator), wrapper_funcs)
async def gs_update_ud(ctx: commands.Context) -> None:
    '''
    [Admin only] Updates the user data with the google sheet.

    @param ctx (commands.Context): The context object representing the invocation context.

    @returns: None
    '''
    gs_df = ud.get_df()
    users = helper.guild().members
    display_to_id = {user.display_name: str(user.id) for user in users}
    key_order = gs_df.columns.tolist()
    key_order.remove("Competitor_")
    key_order.remove("Name")
    print(key_order)
    
    for _, row in gs_df.iterrows():
        id = display_to_id[row['Name']]
        for key, val in row.items():
            if key=="Name": continue
            if val=='-' or val=="":
                if id in ud.data and key in ud.data[id]: del ud.data[id][key]
                continue
            ud.set_user_data(id, key, val)
    ud.store_data()
    await ctx.send("Data stored successfully.")

@chain(client.command(), wrapper_funcs)
async def ud_update_mydata(ctx: commands.Context, key: str, value: str) -> None:
    '''
    Updates the user data for the invoking user.

    @param ctx (commands.Context): The context object representing the invocation context.
    @param key (str): The key to update.


    @returns: None
    '''
    ctx_author = helper.get_member(ctx.author.id)
    result = ud.set_user_data(str(ctx_author.id), key, value)
    await ctx.send(f"Data updated successfully." if result else f"Key not valid.")

@chain(client.command(), commands.check(is_administrator), wrapper_funcs)
async def ud_update_data(ctx: commands.Context, user: str, key: str, value: str) -> None:
    '''
    [Admin only] Updates the user data for a specific user.

    @param ctx (commands.Context): The context object representing the invocation context.
    @param user (str): The user to update the data for, mention using @
    @param key (str): The key to update.
    @param value (str): The value to update the key to.

    @returns: None
    '''
    user = helper.parse_user(user)
    result = ud.set_user_data(str(user.id), key, value)
    await ctx.send(f"Data updated successfully." if result else f"Key not valid.")

@chain(client.command(), commands.check(is_administrator), wrapper_funcs)
async def ud_add_key(ctx: commands.Context, key: str) -> None:
    '''
    [Admin only] Adds a key to the user data.

    @param ctx (commands.Context): The context object representing the invocation context.
    @param key (str): The key to add.

    @returns: None
    '''
    result = ud.add_key(key)
    if result:
        await ctx.send(f"Key added successfully.")
    else:
        await ctx.send(f"Key already exists.")

@chain(client.command(), commands.check(is_administrator), wrapper_funcs)
async def ud_remove_key(ctx: commands.Context, key: str) -> None:
    '''
    [Admin only] Removes a key from the user data.

    @param ctx (commands.Context): The context object representing the invocation context.
    @param key (str): The key to remove.

    @returns: None
    '''
    result = ud.remove_key(key)
    if result:
        await ctx.send(f"Key removed successfully.")
    else:
        await ctx.send(f"Key not valid.")

@chain(client.command(), commands.check(is_administrator), wrapper_funcs)
async def get_emails(ctx: commands.Context, roles_to_match = "None", roles_to_exclude = "None", user_ids_to_match = "None", user_ids_to_exclude = "None", parent="False") -> None:
    '''
    [Admin only] Retrieves the emails for users based on the provided roles and user ids.

    @param ctx (commands.Context): The context object representing the invocation context.
    @param roles_to_match (str): The roles to match.
    @param roles_to_exclude (str): The roles to exclude.
    @param user_ids_to_match (str): The user ids to match.
    @param user_ids_to_exclude (str): The user ids to exclude.
    @param parent (str): Whether to include parent emails.

    @returns: None
    '''
    
    roles_to_match = [role.id for role in helper.parse_roles(roles_to_match)] if roles_to_match != "None" else []
    roles_to_exclude = [role.id for role in helper.parse_roles(roles_to_exclude)] if roles_to_exclude != "None" else []
    user_ids_to_match = [user.id for user in helper.parse_users(user_ids_to_match)] if user_ids_to_match != "None" else []
    user_ids_to_exclude = [user.id for user in helper.parse_users(user_ids_to_exclude)] if user_ids_to_exclude != "None" else []
    parent = helper.parse_boolean(parent)

    users = [str(user.id) for user in helper.get_users(roles_to_match, roles_to_exclude, user_ids_to_match, user_ids_to_exclude)]

    emails_to_get = ["Email_"] + ([] if not parent else ["Parent Email_", "Parent Email 2_"])
    df = get_ud_data()
    df = df.loc[df.index.isin(users), emails_to_get]
    dfstr = set(map(str, df.values.flatten()))
    
    str_send = ""
    for em in dfstr:
        if em == '-': continue 
        if len(str_send + em) >= 1800:
            await ctx.send(f"```{str_send}```")
            str_send = ""
        str_send += em + ' '
    if str_send != "":
        await ctx.send(f"```{str_send}```")

@tasks.loop(hours=24)
async def check_bdays() -> None:
    '''
    Checks for birthdays and sends messages to the admin channel.

    @returns: None
    '''
    df = get_ud_data().loc[:, ["Date of Birth_"]] 
    df = df[df["Date of Birth_"] != "-"]
    df["Date of Birth_"] = df["Date of Birth_"].map(lambda x: "/".join(x.split("/")[:2]))

    df = df[df["Date of Birth_"] == f"{datetime.datetime.now().month}/{datetime.datetime.now().day}"]
    id_to_mention = {str(user.id): user.mention for user in helper.guild().members}
    df.index = df.index.map(lambda x: id_to_mention.get(x, "-1"))
    df = df[df.index != "-1"]
    
    if len(df.index) == 0: return

    channel = client.get_channel(int(1222873409923580009))
    df_index = list(df.index)
    if len(df_index) == 1:
        await channel.send(f"Happy Birthday to {df_index[0]}!")
    elif len(df_index) == 2:
        await channel.send(f"Happy Birthday to {df_index[0]} and {df_index[1]}!")
    else:
        df_index[-1] = f"and {df_index[-1]}"
        await channel.send(f"Happy Birthday to {', '.join(df_index)}!")

    return 

@check_bdays.before_loop
async def before_check_bdays():
    current_time = datetime.datetime.now()
    next_day = datetime.datetime.now() + datetime.timedelta(days=1)
    next_day = next_day.replace(hour=0, minute=1, second=0, microsecond=0)
    seconds_until_next_interval = (next_day - current_time).total_seconds()
    
    await asyncio.sleep(seconds_until_next_interval)

##################################################################################
# POTD USER COMMANDS

# # Command to add an answer to the current season
# @chain(client.command(), wrapper_funcs)
# async def answer(ctx: commands.Context, problem_id: str, answer: str = "") -> None:
#     '''
#     Submits answer 'answer' to problem with id 'problem_id'.

#     @param problem_id (int): The ID of the problem to submit the answer to.
#     @param answer (str): The text answer to submit. Defaults to "" so you can ignore if you submit an image.
#     @optional - attach image

#     @returns: None
#     '''

#     ctx_author = helper.get_member(ctx.author.id)

#     season = potd_driver.season
#     problem = season.get_problem(problem_id)
#     if not problem:
#         await ctx.send("Problem not found")
#         return
    
#     if not problem.in_interval():
#         await ctx.send("Outside time interval.")
#         return

#     try:
#         already_correct= (str(ctx.author.id) in problem.persons and float(problem.persons[str(ctx.author.id)].grade) == 1)
#         result = (float(problem.answer) == float(answer))
#         season.grade_answer(problem_id, str(ctx_author.id), (1 if result else 0))
#         person = problem.get_person(str(ctx_author.id))
#         person.responses.append(str(answer))
#         if already_correct:
#             problem.set_attempts(str(ctx_author.id), -1, True)
#         result = "correct" if result else "wrong"
#         await ctx.send(f"Your answer `{answer}` was {result}.")
#         channel = client.get_channel(int(constants["admin_channel"]))
#         await channel.send(f"{ctx_author.display_name}'s answer of `{answer}` was marked {result}.")
#         return
#     except Exception as e:
#         print(e)
#         pass
    
#     filename = await helper.save_image_from_text(ctx)
#     result, text = season.add_answer(problem_id, str(ctx_author.id), answer, filename)
#     await ctx.send(text)
#     if result:
#         channel = client.get_channel(int(constants["admin_channel"]))
#         await channel.send(f"Answer Added by {ctx_author.display_name}.")
#     return 

# # Command to add an answer to the current season
# @chain(client.command(), wrapper_funcs)
# async def potd_rankings(ctx: commands.Context, season=None) -> None:
#     '''
#     Retrieves top rankings for a specific season, current season by default.

#     @param season (int, optional): Optional. The season for which rankings are to be retrieved. Defaults to the current season.
    
#     @returns: None
#     '''
#     if season == None: season = str(potd_driver.season.CURRENT_SEASON)
#     await ctx.send(string_rankings(get_rankings_df(season, True)))

# @chain(client.command(), wrapper_funcs) 
# async def potd_myrank(ctx, season=None):
#     '''Retrieves your rank, points for specific season, current season by default.
    
#     @param season (int, optional): Optional. The season for which rankings are to be retrieved. Defaults to current season.
    
#     @returns: None'''
#     ctx_author = helper.get_member(ctx.author.id)
#     if season == None: season = str(potd_driver.season.CURRENT_SEASON)
#     rankings_df = get_rankings_df(season)
#     if str(ctx_author.id) in rankings_df['Member ID'].values:
#         await ctx.send(string_rankings(rankings_df[rankings_df['Member ID'] == str(ctx_author.id)]))
#     else:
#         await ctx.send(f"You did not have any points in that season.")

# @chain(client.command(), wrapper_funcs)
# async def potd_curseas(ctx):
#     '''Gets current season'''
#     await ctx.send(potd_driver.season.CURRENT_SEASON)

# POTD LEADERBOARD

# def get_ovrrankings_df(is_sorted: bool = True) -> pd.core.frame.DataFrame:
#     '''
#     Retrieves the overall rankings DataFrame.

#     @param is_sorted (bool): Whether to sort the rankings DataFrame. Defaults to True.

#     @return (pd.core.frame.DataFrame): A DataFrame containing the rank, member ID, and points for each member in the rankings.
#     '''
#     # get & process DF (names)
#     _, df = gs_helper.get_ws('POTD Sheet')
#     users = {str(user.id): user.display_name for user in helper.guild().members}
#     # rename name to Member ID
#     df = df.rename(columns={'Name': 'Member ID'})
#     df['Member ID'] = df['Member ID'].replace(users)
#     df.set_index('Member ID', inplace=True, drop=True)

#     # get points
#     def calc_points(row):
#         row = sorted([float(val) for val in row if val])
#         row = row[len(row)//5:]
#         return float(f"{sum(row)/len(row):.2f}") if len(row) > 0 else 0
#     df['Points'] = df.apply(calc_points, axis=1)
#     df = df.reset_index().rename(columns={'index':'Member ID'})

#     # correct members
#     users = [user.display_name for user in helper.get_users([constants["year_role"]])]
#     df = df[df['Member ID'].isin(users)][['Member ID', 'Points']]
#     for user in users:
#         if user not in df['Member ID'].values:
#             df.loc[len(df.index)] = [user, 0]

#     # for google sheet
#     if is_sorted:
#         df = df.sort_values('Member ID', ascending=True)[['Points']]
#         return df 

#     # process usual DF
#     df = df.drop(df[df['Member ID'].isin(['Shreyan Paliwal', 'Anay Aggarwal'])].index)
#     df['Rank'] = df['Points'].rank(ascending=False).astype(int)
#     df = df[['Rank', 'Member ID', 'Points']].sort_values('Rank', ascending=True)
#     return df
# def get_rankings_df(season_id: str, top: bool = False) -> pd.core.frame.DataFrame:
#     """
#     Retrieves the rankings DataFrame for a specific season.
    
#     @param season_id (int): The season for which rankings are to be retrieved.
    
#     @return (pd.core.frame.DataFrame): A DataFrame containing the rank, member ID, and points for each member in the rankings.
#     """
#     df = pd.DataFrame(potd_driver.season.get_grades(season_id).items(), columns=['Member ID', 'Points']).sort_values('Points', ascending=False)
#     df['Rank'] = df['Points'].rank(method='min', ascending=False).astype(int)
#     if len(df) == 0: return df 
#     if top: df = df[df['Rank'] <= int(df.iloc[min(MAX_ROW_PUBLIC_LEADERBOARD - 1, len(df) - 1)]['Rank'])]
#     return df[['Rank', 'Member ID', 'Points']]
# def string_rankings(df: pd.core.frame.DataFrame) -> str:
#     """
#     Returns a formatted string representation of the rankings DataFrame.

#     @param df (pd.core.frame.DataFrame): The DataFrame containing the rankings.
    
#     @return (str): A string representation of the rankings in a tabular format.
#     """
#     if df.empty:
#         return "No one has any points."
#     guild = helper.guild()
#     def f(x):
#         try:
#             return guild.get_member(int(x)).display_name if guild.get_member(int(x)) else 'Unknown Member'
#         except:
#             return x
#     df.loc[:, 'Member ID'] = df['Member ID'].apply(f)
#     return "```" + df.to_string(index=False) + "```"
# async def update_leaderboard() -> None:
#     '''
#     Update the leaderboard message with the latest rankings.

#     @returns: None
#     '''
#     global constants
#     chn = helper.get_channel(constants["leaderboard_output_channel"])
#     new_text = f"**Season {str(potd_driver.season.CURRENT_SEASON)} Rankings:**\n" + string_rankings(get_rankings_df(str(potd_driver.season.CURRENT_SEASON), True))
#     new_ovrtext = f"**Overall Rankings:**\n" + string_rankings(get_ovrrankings_df(False))

#     res1, mes1 = await helper.get_message(chn.id, constants["leaderboard_output_message"][0])
#     res2, mes2 = await helper.get_message(chn.id, constants["leaderboard_output_message"][1])

#     if not res1:
#         if res2: await mes2.delete()
#         mes2 = await chn.send(new_ovrtext)
#         mes1 = await chn.send(new_text)
#     elif not res2:
#         await mes1.edit(content=new_ovrtext)
#         mes2 = await chn.send(new_text)
#     else:
#         await mes1.edit(content=new_ovrtext)
#         await mes2.edit(content=new_text)
#     constants["leaderboard_output_message"] = [mes1.id, mes2.id]
#     store_data()

# @chain(client.command(), commands.check(is_administrator), wrapper_funcs)
# async def potd_sranks(ctx, season = None, rankmember: bool = False):
#     '''[Admin only] Retrieves rankings for season 'season', current season if left blank, sorted alphabetically by name.

#     @param rankmember (bool, optional): Optional. Whether to add rank & member columns. Defaults to False.
#     @param season (int, optional): Optional. The season for which rankings are to be retrieved. Defaults to current season.

#     @returns None:
#     '''
#     if season == None: season = str(potd_driver.season.CURRENT_SEASON)
#     if rankmember != False: rankmember = rankmember[0].lower() in ['t', 'y']

#     df = get_rankings_df(season)
#     members_with_role = [str(member.id) for member in ctx.guild.members if constants["year_role"] in [role.id for role in member.roles]]

#     for member_id in members_with_role:
#         if member_id not in df['Member ID'].values:
#             df.loc[len(df.index)] = [None, member_id, 0]
#     df = df[df['Member ID'].isin(members_with_role)].sort_values('Points', ascending=False)
#     df['Rank'] = df['Points'].rank(method='min', ascending=False).astype(int)
#     guild = helper.guild()
#     df.loc[:, 'Member ID'] = df['Member ID'].apply(lambda x: guild.get_member(int(x)).display_name if guild.get_member(int(x)) else 'Unknown Member')
#     df = df.sort_values('Member ID', ascending=True, key=lambda x:x.str.lower())
#     df = df[["Rank", "Member ID", "Points"]]
#     if not rankmember: df = df[["Points"]]
#     await ctx.send("```" + df.to_string(header=False, index=False, justify="right")  + "```")

# @chain(client.command(), commands.check(is_administrator), wrapper_funcs)
# async def potd_allrankings(ctx, season=None):
#     '''[Admin only] Retrieves rankings for season 'season', current season if left blank.
    
#     @param season (int, optional): Optional. The season for which rankings are to be retrieved. Defaults to current season.
    
#     @returns: None'''
#     if season == None: season = str(potd_driver.season.CURRENT_SEASON)
#     await ctx.send(string_rankings(get_rankings_df(season)))

# @tasks.loop(minutes=5)
# async def edit_leaderboard_msg():
#     await update_leaderboard()

# @edit_leaderboard_msg.before_loop
# async def before_edit_leaderboard_msg():
#     current_time = datetime.datetime.now()
#     seconds_until_next_interval = (5 - current_time.minute % 5) * 60 + (60 - current_time.second)
#     await asyncio.sleep(seconds_until_next_interval)

# POTD PROBLEMS 

# @chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
# async def potd_newprob(ctx, answer="None", start_time=None, end_time=None, problem_text=None):
#     '''[Admin only] Adds new problem, sends it in designated problem-of-the-day channel.\nOnly accepts answers within time interval from start_time to end_time
    
#     @param answer (int): Integer answer, type NA if non integer answer.
#     @param start_time, end_time (dates): Format "MM-DD-YYYY HH:MM:SS"
#     @param problem_text (string): In quotes, problem text to display

#     @returns: None
#     '''
#     ctx_author = helper.get_member(ctx.author.id)
    
#     if start_time == None: start_time = (pd.Timestamp.now(tz=timezone).replace(hour=0, minute=0, second=0, microsecond=0) + pd.Timedelta(days=1)).strftime("%m-%d-%Y")
#     if end_time == None: end_time = (pd.Timestamp(start_time, tz=timezone)+pd.Timedelta(days=1)).strftime("%m-%d-%Y")
#     if problem_text == None: problem_text = pd.Timestamp(start_time, tz=timezone).strftime(f"<@&{constants['year_role']}> %m/%d/%Y Problem:")

#     if constants["potd_output_channel"] == None:
#         await ctx.send("No output channel.")
#         return

#     channel = client.get_channel(constants["potd_output_channel"])
#     image_filename = await helper.save_image_from_text(ctx)
#     result, text, problem = potd_driver.season.add_problem(problem_text, answer, start_time, end_time)
    
#     potd_driver.add_scheduled_message({
#         "text": dedent(f"""
#             **{ctx_author.display_name}:** 
#             {problem_text}
#             **Season ID:** {potd_driver.season.CURRENT_SEASON}
#             **Problem ID:** {problem.id}

#             Solutions accepted from **{pd.Timestamp(start_time, tz=timezone).strftime("%m/%d/%Y, %H:%M")}** till **{pd.Timestamp(end_time, tz=timezone).strftime("%m/%d/%Y, %H:%M")}**.
            
#             Submit solutions using the command `-answer "Problem_ID" "ANSWER_TEXT"` Please DM your solutions to the bot. To attach an image, simply copy paste it onto your message."""),
#         "filename": image_filename,
#         "time": start_time,
#         "channel": constants["potd_output_channel"]
#     })

#     image_filename = await helper.save_image_from_text(ctx)
#     while image_filename != None:
#         potd_driver.add_scheduled_message({
#             "text":"",
#             "filename": image_filename,
#             "time": end_time, 
#             "channel": constants["potd_solution_channel"]
#         })
#         image_filename = await helper.save_image_from_text(ctx)

#     await ctx.send("Problem added successfully.")

# @chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
# async def potd_deleteprob(ctx, problem_id):
#     '''[Admin only] Deletes a problem from the current season based on its ID.
    
#     @param problem_id (int)'''
#     result, text = potd_driver.season.delete_problem(problem_id)
#     await ctx.send(text)

# @chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
# async def potd_upd_ans(ctx, problem_id, answer):
#     '''[Admin only] Sets new answer to problem 

#     @param problem_id (int)
#     @param answer: new answer, "None" or (int)

#     @returns: None'''
#     result, text, people_updated = potd_driver.season.set_answer(problem_id, answer)
#     for i, j, k in people_updated:
#         member = helper.get_member(int(i))
#         await member.send(f"Your answer to problem {problem_id} has been updated to {1 if j else 0} and you have used {k} attempts.")
#         await ctx.send(f"{member.mention}'s grade has been updated to {1 if j else 0} and number of attempts has been updated to {k}.")
#     await ctx.send(text)

# @chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
# async def potd_upd_season(ctx, problem_id, season_id):
#     '''[Admin only] Sets season for problem 

#     @param problem_id (int)
#     @param season_id (int)

#     @returns: None'''
#     result, text = potd_driver.season.set_season(problem_id, season_id)
#     await ctx.send(text)

# @chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
# async def potd_upd_time(ctx, problem_id, start_time, end_time):
#     '''[Admin only] Sets new time interval for problem

#     @param problem_id (int)
#     @param start_time, end_time (dates): Format "MM-DD-YYYY HH:MM:SS"

#     @returns: None'''
#     result, text = potd_driver.season.set_time(problem_id, start_time, end_time)
#     await ctx.send(text)

# @chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
# async def potd_newseason(ctx, val="1"):
#     '''[Admin only] Creates new season
    
#     @param val (int): default 1, number of seasons to change by

#     @returns: None'''
#     val = int(val)
#     potd_driver.create_season(val)
#     await ctx.send(f"Season created successfully. New season: {potd_driver.season.CURRENT_SEASON}")

# POTD UPDATE USER DATA 

# @chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
# async def potd_grade(ctx, grade, feedback = None, attempts_to_add = 1):
#     '''[Admin only] Grades last answer as correct or wrong.\nis_correct = True (if grading as correct) or False (if grading is wrong)
    
#     @param grade (int): 0 to 1 scale
#     @param feedback (str, optional): Feedback to return the submitter
#     @param attempts_to_add (int): attempts to add
    
#     @returns: None'''

#     # check input grade
#     if not check_float(grade):
#         await ctx.send("Please enter a decimal number for the grade between 0 and 1 (outside the range if extra credit).")
#         return
#     grade = float(grade)

#     # get season, get last problem
#     result, last = potd_driver.season.get_last_ungraded()
#     if not result:
#         await ctx.send("No problems to grade.")
#         return
    
#     member = await client.fetch_user(int(last['person_id']))
#     file = discord.File(f"{DATA_DIR}images/{last['filename']}") if last["filename"] else None

#     potd_driver.season.grade_last(grade, int(attempts_to_add))

#     message = f"Grader: {ctx.message.author.nick}\nYour answer `{last['answer']}` was graded {grade}/1."
#     if feedback != None: message += "\n\n**Feedback: **" + feedback
#     await member.send(content=message, file=file)
#     await ctx.send("Last answer graded successfully.")

# @chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
# async def potd_last(ctx, gnext = "False"):
#     '''[Admin only] Retrieves last ungraded answer and outputs it.
    
#     @params gnext(bool, default=False): whether to get next ungraded problem. Put True if you want next, nothing otherwise

#     @returns: None'''
#     result, last = potd_driver.season.get_last_ungraded(gnext.lower()[0] in ['t', 'y'])
#     if not result:
#         await ctx.send("No problems to grade.")
#         return
#     problem = potd_driver.season.get_problem(last['problem_id'])
#     if not problem:
#         await ctx.send("Problem not found.")
#         return
    
#     name = ctx.guild.get_member(int(last['person_id'])).name
#     disc = ctx.guild.get_member(int(last['person_id'])).discriminator
#     realname = ctx.guild.get_member(int(last['person_id'])).display_name
#     file = discord.File(f"{DATA_DIR}images/{last['filename']}") if last["filename"] else None
#     await ctx.send(content=f"Problem Text: {problem.problem_text}\nProblem ID: {problem.id}\nAnswer Text: {last['answer']}\nPerson: {realname} -- {name}#{disc}", file=file)

# # Command to update the number of attempts for a person in a problem (only for administrators)
# @chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
# async def potd_upd_attempts(ctx, problem_id, person_name, num_attempts):
#     '''[Admin only] Updates number of attempts 'person_name' took for problem 'problem_id' by adding 'num_attempts'.
    
#     @param problem_id (int)
#     @param person_name (string): mention person using @
#     @param num_attempts (int): will add this to current number of attempts
    
#     @returns: None'''
#     person_name = person_name[2:-1]
#     season = potd_driver.season
#     result, text, person = season.set_attempts(problem_id, person_name, int(num_attempts))
#     await ctx.send(text)
#     if result:
#         member = await client.fetch_user(int(person_name))
#         await member.send(f"Grader: {ctx.message.author.nick}\nYour number of attempts to problem {problem_id} has been updated to {person.num_attempts}.")

# # Command to update the correctness attribute for a person in a problem (only for administrators)
# @chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
# async def potd_upd_grade(ctx, problem_id, person_name, new_grade, feedback=None):
#     '''[Admin only] Toggles whether 'person_name' got problem 'problem_id' correct.
    
#     @param problem_id (int)
#     @param person_name (string): mention person using @
#     @param new_grade (int): new grade to give
#     @param feedback (str, optional): feedback to return the submitter
    
#     @returns: None'''
#     person_name = person_name[2:-1]

#     if not check_float(new_grade):
#         await ctx.send(f"Grade {new_grade} is not a float.")
#     new_grade = float(new_grade)
#     result, text, person = potd_driver.season.set_grade(problem_id, person_name, new_grade, False)
    
#     await ctx.send(text)
#     if result:
#         member = await client.fetch_user(int(person_name))
#         if feedback:
#             await member.send(feedback)
#         await member.send(f"Grader: {ctx.message.author.nick}\nYour answer to problem {problem_id} has been rescored to {person.grade}.")

# POTD DATA 

# @chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
# async def list_constants(ctx):
#     '''[Admin only] Lists all constants.
    
#     @returns: None'''
#     await ctx.send(f"```{constants}```")

# @chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
# async def update_constant(ctx, key, value, is_int = False):
#     '''[Admin only] Updates constant 'key' to 'value'.
    
#     @param key (string): constant to update
#     @param value (string): value to update to
    
#     @returns: None'''
#     global constants
#     constants[key] = value
#     if is_int:
#         constants[key] = int(value)
#     await ctx.send(f"Constant {key} updated to {value}.")


# @chain(client.command(), commands.check(is_admin_channel))
# async def store(ctx):
#     '''[Admin only] Manually stores data into data.csv & ungraded.json files.
    
#     @returns: None'''
#     store_data()
#     await ctx.send("Data stored in data.csv successfully.")

# @chain(client.command(), commands.check(is_admin_channel))
# async def load(ctx):
#     '''[Admin only] Manually loads data from data.csv & ungraded.json files.
    
#     @returns: None'''
#     load_data()
#     await ctx.send("Data loaded from data.csv successfully.")

##################################################################################
# SCHEDULE POSTS

@chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
async def schedule(ctx, channel, text, time):
    '''[Admin only] Schedules message "text" in channel "channel" at time "time".
    
    @param channel (string): tag channel using #
    @param text (string): text to send
    @param time (date): format "MM-DD-YYYY HH:MM:SS", when to send message
    
    @returns: None'''
    ctx_author = helper.get_member(ctx.author.id)
    image_filename = await helper.save_image_from_text(ctx)
    potd_driver.add_scheduled_message({
        "text": f"**{ctx_author.display_name}:**\n" + text, 
        "filename": image_filename,
        "time": time, 
        "channel": channel[2:-1]
    })
    image_filename = await helper.save_image_from_text(ctx)
    while image_filename != None:
        potd_driver.add_scheduled_message({
            "text": f"**{ctx_author.display_name}:**",
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
    if len(potd_driver.scheduled_messages) == 0:
        await ctx.send("No scheduled messages.")
        return 
    for j, i in potd_driver.scheduled_messages.items():
        file = None
        if i['filename']: file = discord.File(f"{DATA_DIR}images/{i['filename']}")
        await ctx.send(dedent("""
                **ID: {0}**
                **Text**:
                {1}
                **Time**: {2}
                **Channel**: <#{3}>""").format(j, i['text'], i['time'], i['channel']), file=file)

@chain(client.command(), commands.check(is_admin_channel), wrapper_funcs)
async def remsched(ctx, smesid):
    '''[Admin only] Removes a scheduled message. Run -listsched first to see scheduled messages.

    @param smesid (int): id of scheduled message to remove

    @returns None'''
    
    if str(smesid) in potd_driver.scheduled_messages:
        x = potd_driver.scheduled_messages.pop(str(smesid))
        if x["filename"]: os.remove(f"{DATA_DIR}images/{x['filename']}")
        await ctx.send("Successfully removed scheduled message.")
    else:
        await ctx.send("Could not find scheduled message")

@tasks.loop(minutes=1)
async def check_scheduled_messages():
    '''sends scheduled messages on time'''
    global constants
    scheduled_messages = [(i, j) for i, j in potd_driver.scheduled_messages.items() if pd.Timestamp(j["time"], tz=timezone) <= pd.Timestamp.now(tz=timezone)]
    for i, j in scheduled_messages:
        try:
            if not j["text"]: j["text"] = "​"
            channel = client.get_guild(constants["server_id"]).get_channel(int(j["channel"]))
            file = discord.File(f"{DATA_DIR}images/{j['filename']}") if j["filename"] else None
            await channel.send(content=j["text"], file=file)
            if j['filename']: os.remove(f"{DATA_DIR}images/{j['filename']}")
        except Exception as e:
            channel = helper.get_channel(constants["admin_channel"])
            await channel.send(f"Error sending scheduled message.")
            raise Exception(e)
        potd_driver.scheduled_messages.pop(i)
    store_data()
    
@check_scheduled_messages.before_loop
async def before_check_scheduled_messages():
    current_time = datetime.datetime.now()
    seconds_until_next_interval = 60 - current_time.second
    await asyncio.sleep(seconds_until_next_interval)

##################################################################################
# STATISTICS & COMMUNICATION

@chain(client.command(), commands.check(is_administrator), wrapper_funcs)
async def reactstats(ctx, post_id, role_needed = None):
    '''
    [Admin only] Gets all stats about reactions in a post.

    @param ctx (commands.Context): The context of the command.
    @param post_id (int): The ID of the post to get stats for.
    @param role_needed (int, optional): The ID of the role needed to be counted. Defaults to None.

    @returns: None
    '''
    post_id = helper.parse_type(int, post_id)
    role_needed = helper.parse_role(role_needed).id if role_needed is not None else constants["year_role"]
    
    try:
        post = await helper.get_post(post_id)
    except Exception as e:
        await ctx.send(f"Could not find post with id {post_id}.")
        print(e)
        return

    user_list = {user.display_name:user for user in post.guild.members if not user.bot and any(role.id == role_needed for role in user.roles)}

    reacting_users = {}
    for reaction in post.reactions:
        list = [user.mention async for user in reaction.users() if user.display_name in user_list]
        await ctx.send(f"**{reaction.emoji}**: {', '.join(list)}", silent=True)
        async for user in reaction.users():
            if user.display_name not in reacting_users: reacting_users[user] = [reaction.emoji] 
            else: reacting_users[user].append(reaction.emoji)

    users_list = [user.mention for user in user_list.values() if user not in reacting_users]
    await ctx.send(f"**No reaction**: {', '.join(users_list) if len(users_list) > 0 else 'None'}", silent=True)

    message = "More than one reaction:\n"
    for user, emojis in reacting_users.items():
        if len(emojis) > 1:
            if not any(role.id == role_needed for role in user.roles): continue
            message += f"**{user.mention}**: {', '.join(emojis)}\n"

    await ctx.send(message, silent=True)

    return 

@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def send(ctx, message, roles_to_match = "None", roles_to_exclude = "None", user_ids_to_match = "None", user_ids_to_exclude = "None", post_id = "None"):
    '''
    Sends a message to all users that match the specified criteria.

    @param ctx (commands.Context): The context of the command.
    @param message (str): The message to send.
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

    roles_to_match = [int(role.id) for role in helper.parse_roles(roles_to_match)] if roles_to_match != "None" else []
    roles_to_exclude = [int(role.id) for role in helper.parse_roles(roles_to_exclude)] if roles_to_exclude != "None" else []
    user_ids_to_match = [int(user.id) for user in helper.parse_users(user_ids_to_match)] if user_ids_to_match != "None" else []
    user_ids_to_exclude = [int(user.id) for user in helper.parse_users(user_ids_to_exclude)] if user_ids_to_exclude != "None" else []
    post_id = helper.parse_type(int, post_id) if post_id != "None" else None

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

@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def mod_role(ctx, role_name, members):
    '''
    Creates a role with the specified name and assigns it to the specified members.

    @param ctx (commands.Context): The context of the command.
    @param role_name (str): The name of the role to create; @role if alr exists
    @param members (list of @s, separated by spaces, in quotes): The list of members to assign the role to.

    @returns: None
    '''
    role_name = helper.parse_role(role_name) if role_name[0] == '<' else (await helper.create_role(role_name))

    users = helper.parse_users(members)

    await helper.add_members_to_role(role_name, users)

    await ctx.send(f"Role assigned to {', '.join([user.mention for user in users])}.")

##################################################################################
# GOOGLE SHEETS COMMANDS

@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_update_role(ctx: commands.Context, role: str) -> None:
    '''Updates the people in the google sheet. Takes in a list of roles to update.
    
    @param ctx (commands.Context): The context of the command.
    @param role (str): The role to set as people for the google sheet.

    @returns: None
    '''
    gs_helper.update_people([str(user.id) for user in helper.get_users([int(role[3:-1])])])
    await ctx.send(f"Updated sheet's people to all with role.")

@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_update_people(ctx: commands.Context, people: str) -> None:
    '''[Admin only] Updates the people in the google sheet. Takes in a list of people to update.

    @param ctx (commands.Context): The context of the command.
    @param *args (list): The list of people to set as people for the google sheet.

    @returns: None
    '''
    gs_helper.update_people([user[2:-1] for user in people.split(' ')])
    await ctx.send(f"Updated sheet's people.")

# gs_create_sheet(sheet_name)
@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_create_sheet(ctx: commands.Context, sheet_name: str) -> None:
    '''[Admin only] Creates a google sheet with the given name.

    @param ctx (commands.Context): The context of the command.
    @param sheet_name (str): The name of the sheet to create.

    @returns: None
    '''
    gs_helper.update_display(sheet_name)
    await ctx.send(f"Created sheet '{sheet_name}'.")

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
    await ctx.send(f"Created test sheet '{sheet_name}' with {num_problems} problems.")

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
    await ctx.send(f"Added column '{column_name}' to sheet '{sheet_name}'.")

# gs_add_potd_season()
@chain(client.command(), commands.check(is_administrator), wrapper_funcs)
async def gs_add_potd_season(ctx: commands.Context, date: str = "None", season_id: str = "None", sheet_name: str = "POTD Sheet") -> None:
    '''[Admin only] Adds a new season to the google sheet.

    @param ctx (commands.Context): The context of the command.
    @param date (str): The date of the season to add.
    @param season_id (str): The ID of the season to add.

    @returns: None
    '''
    if season_id == "None": season_id = str(potd_driver.season.CURRENT_SEASON - 1)
    gs_helper.add_potd_season(potd_driver, helper, sheet_name, season_id, date)
    await ctx.send(f"Added season {season_id} to sheet '{sheet_name}'.")

# gs_del_sheet
@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_del_sheet(ctx: commands.Context, sheet_name: str) -> None:
    '''[Admin only] Deletes a google sheet.

    @param ctx (commands.Context): The context of the command.
    @param sheet_name (str): The name of the sheet to delete.

    @returns: None
    '''
    gs_helper.del_ws(sheet_name)
    await ctx.send(f"Deleted sheet '{sheet_name}'.")

# gs_store_sheet
@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_store_sheet(ctx: commands.Context, sheet_name: str) -> None:
    '''[Admin only] Stores the google sheet.

    @param ctx (commands.Context): The context of the command.
    @param sheet_name (str): The name of the sheet to store.

    @returns: None
    '''
    gs_helper.store_display(sheet_name)
    await ctx.send(f"Stored sheet '{sheet_name}'.")

# gs_store_sheets
@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_store_sheets(ctx: commands.Context) -> None:
    '''[Admin only] Stores all google sheets.

    @param ctx (commands.Context): The context of the command.

    @returns: None
    '''
    gs_helper.store_all_displays()
    await ctx.send(f"Stored all sheets.")

# # potd_rankings_overall
# @chain(client.command(), wrapper_funcs)
# async def potd_rankings_overall(ctx: commands.Context, is_sorted = "False") -> None:
#     '''[Admin only] Updates the overall rankings.

#     @param ctx (commands.Context): The context of the command.
#     @param sheet_name (str): The name of the sheet to update.

#     @returns: None
#     '''
#     # parse data
#     is_sorted = is_sorted[0].lower() in ['t', 'y']
    
#     df = get_ovrrankings_df(is_sorted)

#     await ctx.send('```' + df.to_string(index=False) + '```')

# Refresh sheet display
@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_refresh(ctx: commands.Context, sheet_name: str) -> None:
    '''[Admin only] Refreshes the google sheet display.

    @param ctx (commands.Context): The context of the command.
    @param sheet_name (str): The name of the sheet to refresh.

    @returns: None
    '''
    gs_helper.update_display(sheet_name)
    await ctx.send(f"Refreshed sheet '{sheet_name}'.")

@chain(client.command(), commands.check(is_me), wrapper_funcs)
async def gs_change_sheet_name(ctx: commands.Context, old_name: str, new_name: str) -> None:
    '''[Admin only] Changes the name of a google sheet.

    @param ctx (commands.Context): The context of the command.
    @param old_name (str): The old name of the sheet.
    @param new_name (str): The new name of the sheet.

    @returns: None
    '''
    gs_helper.change_ws_name(old_name, new_name)
    await ctx.send(f"Changed sheet name from '{old_name}' to '{new_name}'.")

##################################################################################
# DATA

def load_data():
    global constants
    # potd_driver.load_data()
    with open(f"{DATA_DIR}data/constants.json", "r") as file:
        constants = json.load(file)
    # potd_driver.season.CURRENT_SEASON = constants["CURRENT_SEASON"]
def store_data():
    global constants
    # potd_driver.store_data()
    # constants["CURRENT_SEASON"] = potd_driver.season.CURRENT_SEASON
    with open(f"{DATA_DIR}data/constants.json", "w") as file:
        json.dump(constants, file, indent=4)

load_data()

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
    # edit_leaderboard_msg.start()
    check_scheduled_messages.start()
    check_bdays.start()

##### PRINTS BOT STILL ALIVE
@tasks.loop(minutes=5)
async def still_alive():
    print("Still alive...")

##### KEEPS BOT ALIVE
@tasks.loop(minutes=5)
async def change_status():
  await client.change_presence(activity=discord.Game(next(status)))

helper = discordHelper(client, constants["server_id"])
gs_helper = google_sheet_updater(helper)
ud = user_data(helper)

client.run(TOKEN)

##################################################################################