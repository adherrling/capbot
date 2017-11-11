#!/usr/bin/python3.6
"""Reads in clan data html and parses out the list of clan members."""
import time
from html.parser import HTMLParser
from random import shuffle
import argparse
import datetime
import requests
import feedparser
import discord
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ENGINE = create_engine(f"sqlite:////home/austin/Documents/capbot/clancaps.db")
SESSION = sessionmaker(bind=ENGINE)
BASE = declarative_base()

session = SESSION()

class Account(BASE):
    """Defines the class to handle account names and historical caps"""
    __tablename__ = 'account'
    name = Column(String(50), primary_key=True)
    last_cap_reported = Column(DateTime)
    last_cap_actual = Column(DateTime)
    total_caps = Column(Integer)

# class LastReset(BASE):
#     """Stores the date of the last reset, for comparison"""
#     __tablename__ = "lastReset"
#     lid = Column(Integer, primary_key=True)
#     last_reset = Column(DateTime)

def init_db():
    """Initialized and optionally clears out the database"""
    BASE.metadata.bind = ENGINE
    BASE.metadata.create_all(ENGINE)

class MyHTMLParser(HTMLParser):
    """Builds an HTML parser."""
    def handle_data(self, data):
        if data.startswith("\nvar data;"):
            list_start = data.find("[")
            list_end = data.find("]")
            clan_members = data[list_start+1:list_end]
            clan_members = clan_members.split(", ")
            clan_list = []
            for item in clan_members:
                add_item = item[1:-1]
                add_item = add_item.replace(u'\xa0', u' ')
                clan_list.append(add_item)
            shuffle(clan_list)
            self.data = clan_list

def check_cap(user):
    """Given a feed url, returns true if the cap message is present."""
    feed_str = ""
    with open("/home/austin/Documents/capbot/url.txt", "r") as url_file:
        feed_str += url_file.read().strip()
    feed_str += user
    print(feed_str)
    user_feed = feedparser.parse(feed_str)
    try:
        print(user_feed['feed']['title'])
    except KeyError:
        print("User profile private.")
        return None
    for entry in user_feed['entries']:
        if entry.title == "Capped at my Clan Citadel.":
            print(f"{user} has capped.")
            return entry.published
    return None

def add_cap_to_db(clan_list):
    """Displays cap info for a list of users."""
    add_list = []
    capped_users = []
    for user in clan_list:
        time.sleep(2)
        cap_date = check_cap(user)
        if cap_date is not None:
            cap_date = datetime.datetime.strptime(cap_date, "%a, %d %b %Y %H:%M:%S %Z")
            # If the cap date is not None, that means the user has a cap in their adventurer's log.
            # We need to do a few things. First, check to see if the cap date is already stored in
            # the database under last_cap_reported
            previous_report = session.query(
                Account.last_cap_reported).filter(Account.name == user).first()
            # Two outcomes: previous report is None, or it has a value. If it is none, then we
            # update it to be cap_date, and store the current time as last_cap_actual.
            # If it has a value, and it is the same as cap_date, we don't do anything. If it
            # has a different value, then we need to update the account dict in the same way as
            # if the previous report is none.
            if previous_report is None or previous_report[0] < cap_date:
                primary_key_map = {"name": user}
                account_dict = {"name": user,
                                "last_cap_reported": cap_date,
                                "last_cap_actual": datetime.datetime.now()}
                account_record = Account(**account_dict)
                add_list.append(upsert(Account, primary_key_map, account_record))
                print(f"{user} last capped at the citadel on {cap_date}.")
                capped_users.append((user, cap_date))
        else:
            print(f"{user} has not capped at the citadel.")

    add_list = [item for item in add_list if item is not None]
    session.add_all(add_list)
    session.commit()
    return capped_users

def upsert(table, primary_key_map, obj):
    """Decides whether to insert or update an object."""
    first = session.query(table).filter_by(**primary_key_map).first()
    if first != None:
        keys = table.__table__.columns.keys()
        session.query(table).filter_by(**primary_key_map).update(
            {column: getattr(obj, column) for column in keys})
        return None
    return obj

# def erase_caps():
#     """Run this to zero out the caps."""
#     users = session.query(Account).all()
#     for user in users:
#         total = session.query(Account.total_caps).filter(Account.name == user.name).first()[0]
#         capped = session.query(
#             Account.capped_this_week).filter(Account.name == user.name).first()[0]
#         if total is None:
#             total = 0
#         if capped:
#             session.query(Account).filter(
#                 Account.name == user.name).update({Account.total_caps: total+1})
#     for user in users:
#         session.query(Account).filter(
#             Account.name == user.name).update({Account.capped_this_week: False})
#     primary_key_map = {"lid": 1}
#     reset_dict = {"lid": 1, "last_reset": datetime.datetime.now()}
#     reset = LastReset(**reset_dict)
#     reset_obj = upsert(LastReset, primary_key_map, reset)
#     if reset_obj is not None:
#         session.add(reset_obj)
#     session.commit()

def main():
    """Runs the stuff."""
    parser = argparse.ArgumentParser(
        description="Choose to check for new caps or zero out existing caps.")
    parser.add_argument("-c", "--check", help="Runs the cap check and bot", action="store_true")
    parser.add_argument("-b", "--bot", help="Runs only the bot", action="store_true")
    # parser.add_argument("-r", "--reset", help="Zeros out existing caps", action="store_true")
    parser.add_argument("-i", "--init", help="Reinitializes the database", action="store_true")
    args = parser.parse_args()
    # if args.reset:
    #     erase_caps()
    if args.check:
        clan_parser = MyHTMLParser()
        url_str = ""
        with open("/home/austin/Documents/capbot/clanlist.txt", "r") as url_file:
            url_str = url_file.read().strip()
        req_data = requests.get(url_str)
        req_html = req_data.text
        clan_parser.feed(req_html)
        clan_list = clan_parser.data
        print(clan_list)
        capped_users = add_cap_to_db(clan_list)
        token = ""
        with open("/home/austin/Documents/capbot/token.txt", "r") as tokenfile:
            token = tokenfile.read().strip()
        run_bot(capped_users, token)
    elif args.init:
        init_db()
    elif args.bot:
        token = ""
        with open("/home/austin/Documents/capbot/token.txt", "r") as tokenfile:
            token = tokenfile.read().strip()
        run_bot([], token)


def run_bot(capped_users, token):
    """Actually runs the bot"""
    # The regular bot definition things
    client = discord.Client()

    @client.event
    async def on_ready():
        """Prints bot initialization info"""
        print('Logged in as')
        print(client.user.name)
        print(client.user.id)
        print('------')
        servers = client.servers
        for server in servers:
            def_chan = server.default_channel
        user_updates = ""
        for (user, cap_date) in capped_users:
            curdate = datetime.datetime.now(datetime.timezone.utc).strftime("%a %b %d, %H:%M:%S")
            user_updates += f"Cap: {user} has capped at the citadel at approximately: {curdate}.\n"
            user_updates += f"Adventurer's Log time: {cap_date}.\n"
        if user_updates != "":
            await client.send_message(discord.Object(id='350087804564275200'),
                                      user_updates)

    # @client.event
    # async def query_database(channel, statement, connection):
    #     """Performs a simple sql query against the database"""
    #     result = connection.execute(statement)
    #     result_list = [row for row in result]
    #     await client.send_message(channel, result_list)

    @client.event
    async def on_message(message):
        """Handles commands based on messages sent"""
        if message.content.startswith('!caplist'):
            capped_users = session.query(Account.name).all()
            users = []
            for user in capped_users:
                users.append(user[0])
            ret_str = ""
            for i in range(len(users)):
                ret_str += f"{i+1}. {users[i]}\n"
            await client.send_message(message.channel, ret_str)

        elif message.content.startswith('!vis'):
            await client.send_message(message.channel, "Fuck you")

        elif message.content.startswith('!delmsgs'):
            role_list = [role.name for role in message.author.roles]
            if "cap handler" in role_list:
                info = message.content.split(" ")[1]
                if info == "all":
                    async for msg in client.logs_from(message.channel, limit=500):
                        if msg.author == client.user:
                            await client.delete_message(msg)
                else:
                    # Try to interpret info as a message id. Thankfully bots fail gracefully
                    before_msg = await client.get_message(message.channel, info)
                    async for msg in client.logs_from(
                            message.channel, limit=500, before=before_msg):
                        if msg.author == client.user:
                            await client.delete_message(msg)

        elif message.author.name == "Roscroft" and message.channel.is_private:
            if not message.content == "Roscroft":
                await client.send_message(discord.Object(id='307708375142105089'),
                                          message.content)
        # id='350087804564275200'),

        elif message.content.startswith('!help'):
            await client.send_message(
                message.channel, ("Use !delmsgs <id> do delete all messages before the provided "
                                  "message id. Use '!delmsgs all' to delete all bot messages."))

        elif message.content.startswith('!list'):
            userlist = []
            async for msg in client.logs_from(message.channel, limit=500):
                if msg.author == client.user and msg.content.startswith("Cap:"):
                    user_name = msg.content.split(" ")[1]
                    userlist.append(user_name)
            print(userlist)
            ret_str = ""
            for i in range(len(userlist)):
                ret_str += f"{i+1}. {userlist[i]}\n"
            await client.send_message(message.channel, ret_str)

    client.run(token)

if __name__ == "__main__":
    main()
