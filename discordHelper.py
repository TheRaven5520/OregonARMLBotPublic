from unique_id.unique_id import unique_id
import pandas as pd, numpy as np, json, copy as cp
import os, sys, dotenv
import asyncio, traceback

######################################## DISCORD SET UP STUFF

import discord
from discord.utils import get
from discord.ext import commands, tasks
from itertools import cycle 
status = cycle(['Helping users.', 'Managing servers.'])

intents = discord.Intents.all()
client = commands.Bot(command_prefix='-', intents=intents)

######################################## CONSTANTS

# data dir is parent_dir/PrivateData/
DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/PrivateData/"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

timezone = 'America/Los_Angeles'

def log_error(e, act=True):
    '''logs error e'''
    with open(f"{DATA_DIR}error_log.txt", "a") as file:
        file.write(f"[{pd.Timestamp.now(tz='America/Los_Angeles')}]\n{e}\n")
        if act: traceback.print_exc(file=file)

######################################## DISCORD HELPER

class discordHelper:
    def __init__(self, client, server_id):
        self.server_id = server_id
        self.client = client

    ################ RETRIEVE

    def guild(self):
        return self.client.get_guild(self.server_id)

    def get_channel(self, channel_id):
        channel = self.guild().get_channel(channel_id)
        if channel is None:
            raise Exception("Channel not found")
        return channel

    async def get_message(self, channel_id, message_id):
        channel_id = [channel_id] if type(channel_id) == int else [channel.id for channel in self.guild().channels if channel.type == discord.ChannelType.text]
        for channel_id in channel_id:
            chn = self.get_channel(channel_id)
            try:
                message = await chn.fetch_message(int(message_id))
                return True, message
            except:
                continue
        return False, None 

    def get_member(self, member_id):
        member = self.guild().get_member(member_id)
        if member is None:
            print(f"Member {member_id} not found")
            raise Exception(f"Member {member_id} not found")
        return member

    async def get_post(self, post_id, channel_id = None):
        if channel_id is not None:
            channel = self.get_channel(channel_id)
            post = await channel.fetch_message(post_id)
            if post is None:
                raise Exception("Post not found.")
            return post

        for channel in self.guild().channels:
            try:
                post = await channel.fetch_message(post_id)
                return post
            except:
                continue 
        
        raise Exception("Post not found.")

    def get_users(self, role_ids = None, not_role_ids = None, member_ids = None, not_member_ids = None):
        users = []
        for user in self.guild().members:
            if not_member_ids != None and user.id in not_member_ids: continue 
            if member_ids != None and user.id in member_ids:
                users.append(user)
                continue
            if not_role_ids != None and any(role.id in not_role_ids for role in user.roles): continue 
            if role_ids != None and any(role.id in role_ids for role in user.roles):
                users.append(user)
                continue
        return users

    async def save_image_from_text(self, ctx):
        if len(ctx.message.attachments) > 0:
            attachment = ctx.message.attachments[0]
            ctx.message.attachments = ctx.message.attachments[1:]
            filename = str(unique_id()) + '.png' 
            await attachment.save(f"{DATA_DIR}images/{filename}")
            return filename
        else:
            return None

    ################ INPUT PARSERS

    def parse_role(self, role):
        if role == "None": return None
        return self.guild().get_role(int(role[3:-1]))
    def parse_roles(self, roles):
        if roles == "None": return None
        return [self.parse_role(role) for role in roles.split(" ") if role != '']

    def parse_user(self, user):
        if user == "None": return None
        return self.get_member(int(user[2:-1]))
    def parse_users(self, users):
        if users == "None": return None
        return [self.parse_user(user) for user in users.split(" ") if user != '']

    def parse_channel(self, channel):
        if channel == "None": return None
        return self.get_channel(int(channel[2:-1]))

    def parse_boolean(self, boolean):
        if boolean == "None": return None
        return boolean.lower()[0] in ['t', 'y']
    def parse_type(self, type, val):
        try: return type(val)
        except: return None

    