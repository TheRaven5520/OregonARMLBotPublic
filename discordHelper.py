from unique_id.unique_id import unique_id

DATA_DIR = "/home/ec2-user/PrivateData/"

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

    def get_member(self, member_id):
        member = self.guild().get_member(member_id)
        if member is None:
            raise Exception("Member not found")
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