#!/usr/bin/python3.6
"""Reads in clan data html and parses out the list of clan members."""
from html.parser import HTMLParser
from random import shuffle
import time
import subprocess
import argparse
import datetime
import json
import requests
import discord
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ENGINE = create_engine(f"sqlite:////home/austin/Documents/capbot/clancaps.db")
MASTER_SESSION = sessionmaker(bind=ENGINE)
BASE = declarative_base()
REQUEST_SESSION = requests.session()
SESSION = MASTER_SESSION()

class Account(BASE):
    """Defines the class to handle account names and historical caps"""
    __tablename__ = 'account'
    name = Column(String(50), primary_key=True)
    last_cap_time = Column(DateTime)
    total_caps = Column(Integer)

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
            self.data = clan_list

def check_cap(user):
    """Given a user, return cap date if it is in their activity history."""
    url_str = ""
    with open("/home/austin/Documents/capbot/url.txt", "r") as url_file:
        url_str = url_file.read().strip()
    url_str += user
    url_str += "&activities=20"
    data = REQUEST_SESSION.get(url_str).content
    data_json = json.loads(data)
    try:
        activities = data_json['activities']
    except KeyError:
        print(f"{user}'s profile is private.")
        return None
    for activity in activities:
        if "capped" in activity['details']:
            date = activity['date']
            print(f"Cap found: {user} capped on {date}.")
            return activity['date']
    return None

def add_cap_to_db(clan_list):
    """Displays cap info for a list of users."""
    add_list = []
    capped_users = []
    for user in clan_list:
        cap_date = check_cap(user)
        if cap_date is not None:
            db_date = datetime.datetime.strptime(cap_date, "%d-%b-%Y %H:%M")
            # cap_date = datetime.datetime.strptime(cap_date, "%a, %d %b %Y %H:%M:%S %Z")
            # If the cap date is not None, that means the user has a cap in their adventurer's log.
            # We need to do a few things. First, check to see if the cap date is already stored in
            # the database under last_cap_reported
            previous_report = SESSION.query(
                Account.last_cap_time).filter(Account.name == user).first()
            # Two outcomes: previous report is None, or it has a value. If it is none, then we
            # update it to be cap_date, and store the current time as last_cap_actual.
            # If it has a value, and it is the same as cap_date, we don't do anything. If it
            # has a different value, then we need to update the account dict in the same way as
            # if the previous report is none.
            if previous_report is None or previous_report[0] < db_date:
                # Check to see if the time is in the database. If so, probably indicates a name
                # change. If the time is already in, then we do not need to report it.
                same_time = SESSION.query(Account.name, Account.last_cap_time).filter(Account.last_cap_time == db_date).first()
                if same_time is not None:
                    print("Name change found.")
                else:
                    primary_key_map = {"name": user}
                    account_dict = {"name": user, "last_cap_time": db_date}
                    account_record = Account(**account_dict)
                    add_list.append(upsert(Account, primary_key_map, account_record))
                    print(f"{user} last capped at the citadel on {cap_date}.")
                    capped_users.append((user, cap_date))
                    # print(capped_users)
        else:
            pass
            # print(f"{user} has not capped at the citadel.")

    add_list = [item for item in add_list if item is not None]
    SESSION.add_all(add_list)
    SESSION.commit()
    return capped_users

def upsert(table, primary_key_map, obj):
    """Decides whether to insert or update an object."""
    first = SESSION.query(table).filter_by(**primary_key_map).first()
    if first != None:
        keys = table.__table__.columns.keys()
        SESSION.query(table).filter_by(**primary_key_map).update(
            {column: getattr(obj, column) for column in keys})
        return None
    return obj

def main():
    """Runs the stuff."""
    parser = argparse.ArgumentParser(
        description="Choose to check for new caps or zero out existing caps.")
    parser.add_argument("-c", "--check", help="Runs the cap check and bot", action="store_true")
    parser.add_argument("-u", "--update", help="Runs only the cap check", action="store_true")
    parser.add_argument("-b", "--bot", help="Runs only the bot", action="store_true")
    # parser.add_argument("-r", "--reset", help="Zeros out existing caps", action="store_true")
    parser.add_argument("-i", "--init", help="Reinitializes the database", action="store_true")
    parser.add_argument("-f", "--force", help="Force sends a message", action="store_true")
    args = parser.parse_args()
    # if args.reset:
    #     erase_caps()
    if args.check or args.update:
        clan_parser = MyHTMLParser()
        url_str = ""
        with open("/home/austin/Documents/capbot/clanlist.txt", "r") as url_file:
            url_str = url_file.read().strip()
        req_data = requests.get(url_str)
        req_html = req_data.text
        clan_parser.feed(req_html)
        clan_list = clan_parser.data
        # print(clan_list)
        capped_users = add_cap_to_db(clan_list)
        token = ""
        with open("/home/austin/Documents/capbot/token.txt", "r") as tokenfile:
            token = tokenfile.read().strip()
        if args.check:
            run_bot(capped_users, token)
    elif args.init:
        init_db()
    elif args.bot:
        token = ""
        with open("/home/austin/Documents/capbot/token.txt", "r") as tokenfile:
            token = tokenfile.read().strip()
        run_bot([], token)
    elif args.force:
        token = ""
        with open("/home/austin/Documents/capbot/token.txt", "r") as tokenfile:
            token = tokenfile.read().strip()
        capped_users = [("iMath", "16-Nov-2017 05:17")]
        run_bot(capped_users, token)

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

    async def report_caps():
        """Reports caps."""
        await client.wait_until_ready()
        with open("/home/austin/Documents/capbot/channel.txt", "r") as channel_file:
            channel_id = channel_file.read().strip()
        capped_users.reverse()
        for (user, cap_date) in capped_users:
            datetime_list = cap_date.split(" ")
            date_report = datetime_list[0]
            time_report = datetime_list[1]
            msg_string = f"{user} has capped at the citadel on {date_report} at {time_report}."
            await client.send_message(
                discord.Object(id=channel_id), msg_string)

    @client.event
    async def on_message(message):
        """Handles commands based on messages sent"""
        if message.content.startswith('!vis'):
            await client.send_message(message.channel, "It's actually ~vis")

        elif message.content.startswith('!delmsgs'):
            role_list = [role.name for role in message.author.roles]
            if "cap handler" in role_list:
                info = message.content.split(" ")[1]
                if info == "all":
                    async for msg in client.logs_from(message.channel, limit=1000):
                        if msg.author == client.user:
                            time.sleep(1)
                            await client.delete_message(msg)
                elif info == "noncap":
                    async for msg in client.logs_from(message.channel, limit=1000):
                        if msg.author == client.user and "capped" not in msg.content:
                            time.sleep(1)
                            await client.delete_message(msg)
                else:
                    # Try to interpret info as a message id. Thankfully bots fail gracefully
                    before_msg = await client.get_message(message.channel, info)
                    async for msg in client.logs_from(
                            message.channel, limit=1000, before=before_msg):
                        if msg.author == client.user:
                            time.sleep(1)
                            await client.delete_message(msg)

        elif message.content.startswith('!help'):
            await client.send_message(
                message.channel, ("Commands:\n!delmsgs <argument> - using a message id will "
                                  "delete all messages before that id. Using 'all' will delete "
                                  "all messages, and using 'noncap' will delete all non-cap report "
                                  "messages.\n!update - force a manual check of all alogs.\n!list "
                                  "- generates a list of all users who have capped recently, by "
                                  "looking at cap reports in the channel. Note that if there are "
                                  "no cap messages, this will do nothing.\n!force <argument> - "
                                  "the bot will check the database for cap info about the user, "
                                  "and will send a message to the channel if cap info exists. "
                                  "Using 'all' will send an update message to the channel for "
                                  "every user in the database."))

        elif message.content.startswith('!list'):
            userlist = []
            async for msg in client.logs_from(message.channel, limit=500):
                if msg.author == client.user and ("capped" in msg.content):
                    msg_lines = msg.content.split("\n")
                    for cap_report in msg_lines:
                        name_index = cap_report.find(" has")
                        userlist.append(cap_report[:name_index])
            print(userlist)
            ret_str = ""
            for i in range(len(userlist)):
                ret_str += f"{i+1}. {userlist[i]}\n"
            await client.send_message(message.channel, ret_str)

        elif message.content.startswith('!update'):
            role_list = [role.name for role in message.author.roles]
            if "cap handler" in role_list:
                await client.send_message(message.channel, "Manually updating...")
                subprocess.call(['./runcapbot.sh'])

        elif message.content.startswith('!force'):
            role_list = [role.name for role in message.author.roles]
            if "cap handler" in role_list:
                user = message.content.split(" ")[1]
                if user == "all":
                    capped_users = SESSION.query(Account.name, Account.last_cap_time).all()
                    with open("/home/austin/Documents/capbot/channel.txt", "r") as channel_file:
                        channel_id = channel_file.read().strip()
                    for (user, cap_date) in capped_users:
                        cap_date = datetime.datetime.strftime(cap_date, "%d-%b-%Y %H:%M")
                        datetime_list = cap_date.split(" ")
                        date_report = datetime_list[0]
                        time_report = datetime_list[1]
                        msg_string = f"{user} has capped at the citadel on {date_report} at {time_report}."
                        await client.send_message(
                            discord.Object(id=channel_id), msg_string)
                else:
                    cap_date = SESSION.query(Account.last_cap_time).filter(Account.name == user).first()
                    if cap_date is not None:
                        cap_date = cap_date[0]
                        with open("/home/austin/Documents/capbot/channel.txt", "r") as channel_file:
                            channel_id = channel_file.read().strip()
                        cap_date = datetime.datetime.strftime(cap_date, "%d-%b-%Y %H:%M")
                        datetime_list = cap_date.split(" ")
                        date_report = datetime_list[0]
                        time_report = datetime_list[1]
                        msg_string = f"{user} has capped at the citadel on {date_report} at {time_report}."
                        await client.send_message(
                            discord.Object(id=channel_id), msg_string)

    client.loop.create_task(report_caps())
    client.run(token)

if __name__ == "__main__":
    main()
