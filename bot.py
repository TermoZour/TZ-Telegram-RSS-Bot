#!/usr/bin/python3
# -*- coding: utf-8 -*-

from telegram.ext import Updater, CommandHandler
from telegram.utils.helpers import escape_markdown
from telegram import ParseMode

import telegram.constants

import configparser
import logging

import requests

import strings
import feedparser

from sqlalchemy import create_engine, Column, Integer, UnicodeText, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

# initializing config file
config = configparser.ConfigParser()
config.read("properties.ini")

# getting bot owner ID from config file
owner_id = int(config.get("OWNER", "owner_id"))


def start(bot, update):
    update.effective_message.reply_text(strings.stringHelp)


def help_message(bot, update):
    # gather all commands help messages from the strings.py file
    help_all = strings.help_message + strings.help_url + strings.help_list + strings.help_add + strings.help_remove

    update.effective_message.reply_text(text=help_all)


def test(bot, update):
    update.effective_message.reply_text("Bot status: Online, duh")


def server_ip(bot, update):
    # gather user data like username, first name, last name
    user = update.message.from_user

    # gather telegram user ID
    tg_user_id = update.effective_user.id

    # check if the sender's ID is the same as the owner's ID set in the config. for security purposes
    if tg_user_id == owner_id:
        # access the site
        row = requests.get("http://ipinfo.io/ip")

        # save the text into a variable to be sent later by the bot
        ip = row.text

        update.effective_message.reply_text("Server IP: " + ip)
    else:
        update.effective_message.reply_text("I'm sorry " + user.first_name + ", but I can't let you do that.")


def show_url(bot, update, args):
    # gather telegram chat ID (might be the same as user ID if message is sent to the bot via PM)
    tg_chat_id = str(update.effective_chat.id)

    # check if there is anything written as argument (will give out of range if there's no argument)
    if len(args[0]) < 3:
        # there's nothing written or it's too less text to be an actual link
        update.effective_message.reply_text(strings.stringInvalidURL)
    else:
        # there is an actual link written

        tg_feed_link = args[0]
        link_processed = feedparser.parse(tg_feed_link)

        feed_title = link_processed.feed.title
        feed_description = link_processed.feed.description
        feed_link = link_processed.feed.link

        entry_title = link_processed.entries[0].title
        entry_description = link_processed.entries[0].description
        entry_link = link_processed.entries[0].link

        # check if there's any * in the title so that proper markdown can be applied
        if '*' in feed_title:
            # there is a * in the title string
            print("# Found * in feed title. Parsing...")

            # strips the * from the title string
            feed_title.rstrip('*')
        else:
            # there is no * in the title string
            print("# No * found in feed title. Proceeding...")

        # check if there's any * in the title so that proper markdown can be applied
        if '*' in entry_title:
            # there is a * in the title string
            print("# Found * in entry title. Parsing...")

            # strips the * from the title string
            entry_title.rstrip('*')
        else:
            # there is no * in the title string
            print("# No * found in entry title. Proceeding...")

        final_message = "feed title: " + "*" + feed_title + "*" + "\n\n" + "feed description: " + escape_markdown(feed_description) + "\n\n" + "feed link: " + escape_markdown(feed_link) + "\n\n" + "entry title: " + "*" + entry_title + "*" + "\n\n" + "entry description: " + escape_markdown(entry_description) + "\n\n" + "entry link: " + escape_markdown(entry_link)
        bot.send_message(chat_id=tg_chat_id, text=final_message, parse_mode=ParseMode.MARKDOWN)


def list_urls(bot, update):
    # gather telegram chat ID (might be the same as user ID if message is sent to the bot via PM)
    tg_chat_id = str(update.effective_chat.id)

    # gather telegram user ID
    tg_user_id = update.effective_user.id

    # gather link data from DB based on who sent the message and from where
    user_data = SESSION.query(RSS_Feed).filter(RSS_Feed.user_id == tg_user_id, RSS_Feed.chat_id == tg_chat_id).all()

    # make an empty list for later usage
    links_list = []

    # this loops gets every link from the DB based on the filter above and appends it to the list
    for row in user_data:
        links_list.append(row.feed_link)

    # make an empty string for later usage
    final_content = ""

    # this neatly arranges the links from links_list to be properly sent by the bot
    final_content += "\n\n".join(links_list)

    # check if the length of the message is too long to be posted in 1 chat bubble
    if len(final_content) <= telegram.constants.MAX_MESSAGE_LENGTH:
        bot.send_message(chat_id=tg_chat_id, text= "This chat is subscribed to the following links:" + "\n" + final_content)
    else:
        bot.send_message(chat_id=tg_chat_id, text="*Warning: *" + strings.errorMsgLong)
        print("\n" + "# Message too long for chat " + str(tg_chat_id))


def add_url(bot, update, args):
    # check if there is anything written as argument (will give out of range if there's no argument)
    if len(args[0]) < 3:
        # there's nothing written or it's too less text to be an actual link
        update.effective_message.reply_text(strings.stringInvalidURL)
    else:
        # there is an actual link written

        # gather telegram chat data
        chat = update.effective_chat

        # gather telegram user ID
        tg_user_id = update.effective_user.id

        # gather telegram chat ID (might be the same as user ID if message is sent to the bot via PM)
        tg_chat_id = str(update.effective_chat.id)

        # gather the feed link from the command sent by the user
        tg_feed_link = args[0]

        # check if the user who issued the command is the chat's admin or owner (to prevent spam)
        if chat.get_member(tg_user_id).status == 'administrator' or chat.get_member(tg_user_id).status == 'owner' or tg_user_id == owner_id:
            # pass the link to be processed by feedparser
            link_processed = feedparser.parse(tg_feed_link)

            # check if link is a valid RSS Feed link
            if link_processed.bozo == 1:
                # it's not a valid RSS Feed link
                update.effective_message.reply_text(strings.stringInvalidURLbozo)
            else:
                # the RSS Feed link is valid

                # set old_entry_link as the last entry from the rss link to be stored in the DB so it can later be changed when updates occur
                tg_old_entry_link = link_processed.entries[0].link

                # gather the row which contains exactly that telegram user ID, group ID and link for later comparison
                row = SESSION.query(RSS_Feed).filter(RSS_Feed.user_id == tg_user_id, RSS_Feed.feed_link == tg_feed_link, RSS_Feed.chat_id == tg_chat_id).all()

                # check if there is an entry already added to the DB by the same user in the same group with the same link
                if row:
                    # there is already a link added to the DB
                    update.effective_message.reply_text(strings.stringURLalreadyAdded)
                else:
                    # there is no link added, so we'll add it now

                    # prepare the action for the DB push
                    action = RSS_Feed(tg_user_id, tg_chat_id, tg_feed_link, tg_old_entry_link)

                    # add the action to the DB query
                    SESSION.add(action)

                    # commit the changes to the DB
                    SESSION.commit()

                    update.effective_message.reply_text(strings.stringURLadded)

                    print("\n" + "# New subscription for user " + str(tg_user_id) + " with link " + tg_feed_link + "\n")
        else:
            update.effective_message.reply_text(strings.errorAdmin)


def remove_url(bot, update, args):
    # check if there is anything written as argument (will give out of range if there's no argument)
    if len(args[0]) < 3:
        # there's nothing written or it's too less text to be an actual link
        update.effective_message.reply_text(strings.stringInvalidURL)
    else:
        # there is an actual link written

        # gather telegram chat data
        chat = update.effective_chat

        # gather telegram user ID
        tg_user_id = update.effective_user.id

        # gather telegram chat ID (might be the same as user ID if message is sent to the bot via PM)
        tg_chat_id = str(update.effective_chat.id)

        # gather the feed link from the command sent by the user
        tg_feed_link = args[0]

        # check if the user who issued the command is the chat's admin or owner (to prevent spam)
        if chat.get_member(tg_user_id).status == 'administrator' or chat.get_member(tg_user_id).status == 'owner' or tg_user_id == owner_id:
            # pass the link to be processed by feedparser
            link_processed = feedparser.parse(tg_feed_link)

            # check if link is a valid RSS Feed link
            if link_processed.bozo == 1:
                # it's not a valid RSS Feed link
                update.effective_message.reply_text(strings.stringInvalidURLbozo)
            else:
                # the RSS Feed link is valid

                # gather all duplicates (if possible) for the same TG User ID, TG Chat ID and link
                user_data = SESSION.query(RSS_Feed).filter(RSS_Feed.chat_id == tg_chat_id, RSS_Feed.feed_link == tg_feed_link).all()

                # check if it finds the link in the database
                if user_data:
                    # there is an link in the DB

                    # this loops to delete any possible duplicates for the same TG User ID, TG Chat ID and link
                    for i in user_data:
                        # add the action to the DB query
                        SESSION.delete(i)

                    # commit the changes to the DB
                    SESSION.commit()

                    update.effective_message.reply_text(strings.stringURLremoved)
                else:
                    update.effective_message.reply_text(strings.stringURLalreadyRemoved)
        else:
            update.effective_message.reply_text(strings.errorAdmin)


def rss_update(bot, job):
    # get all of the DB data
    user_data = SESSION.query(RSS_Feed).all()

    # this loop checks for every row in the DB
    for row in user_data:
        # get telegram chat ID from DB
        tg_chat_id = row.chat_id

        # get RSS link from DB
        tg_feed_link = row.feed_link

        # process the feed from DB
        feed_processed = feedparser.parse(tg_feed_link)

        # get the last update's entry from the DB
        tg_old_entry_link = row.old_entry_link

        # define empty list of entry links for when there's new updates to a RSS link
        new_entry_links = []

        # define empty list of entry titles for when there's new updates to a RSS link
        new_entry_titles = []

        # this loop checks for every entry from the RSS Feed link from the DB row
        for entry in feed_processed.entries:
            # check if there are any new updates to the RSS Feed from the old entry
            if entry.link != tg_old_entry_link:
                # there is a new entry, so it's link is added to the new_entry_links list for later usage
                new_entry_links.append(entry.link)

                # there is a new entry, so it's title is added to the new_entry_titles list for later usage
                new_entry_titles.append(entry.title)
            else:
                break

        # check if there's any new entries queued from the last check
        if new_entry_links:
            # set the new old_entry_link with the latest update from the RSS Feed
            row.old_entry_link = new_entry_links[0]

            # commit the changes to the DB
            SESSION.commit()
        else:
            # there's no new entries
            print("\n" + "# No new updates for chat " + str(tg_chat_id) + " with link " + tg_feed_link + "\n")

        # this loop sends every new update to each user from each group based on the DB entries
        for link, title in zip(reversed(new_entry_links), reversed(new_entry_titles)):
            print("\n" + "# New entry from " + title + " with link " + link)

            # check if there's any * in the title so that proper markdown can be applied
            if '*' in title:
                # there is a * in the title string
                print("# Found * in title. Parsing...")

                # strips the * from the title string
                title.rstrip('*')
            else:
                # there is no * in the title string
                print("# No * found in title. Proceeding...")

            # make the final message with the layout: "<rss_feed_title> <rss_feed_link>"
            final_message = "*" + title + "*" + "\n\n" + escape_markdown(link)

            # check if the length of the message is too long to be posted in 1 chat bubble
            if len(final_message) <= telegram.constants.MAX_MESSAGE_LENGTH:
                print("\n" + "# Check passed. Message doesn't exceed Telegram limit " + "\n")
                bot.send_message(chat_id=tg_chat_id, text=final_message, parse_mode=ParseMode.MARKDOWN)
            else:
                print("\n" + "# Message too long for entry link " + link)
                bot.send_message(chat_id=tg_chat_id, text="*Warning: *" + strings.errorMsgLong)


BASE = declarative_base()

engine = create_engine(config.get("DB", "db_url"), client_encoding="utf8")

BASE.metadata.bind = engine

BASE.metadata.create_all(engine)

SESSION = scoped_session(sessionmaker(bind=engine, autoflush=False))


class RSS_Feed(BASE):
    __tablename__ = "RSS_Feed"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    chat_id = Column(UnicodeText, nullable=False)
    feed_link = Column(UnicodeText)
    old_entry_link = Column(UnicodeText)

    def __init__(self, user_id, chat_id, feed_link, old_entry_link):
        self.user_id = user_id
        self.chat_id = chat_id
        self.feed_link = feed_link
        self.old_entry_link = old_entry_link

    def __repr__(self):
        return "<RSS_Feed for {} with chatID {} at feed_link {} with old entry {}>".format(self.user_id, self.chat_id, self.feed_link, self.old_entry_link)


BASE.metadata.create_all()


def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    updater = Updater(config.get("KEY", "tg_API_token"))

    job = updater.job_queue
    job_minute = job.run_repeating(rss_update, int(config.get("UPDATE", "update_interval")), first=0)
    job_minute.enabled = True

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_message))
    dispatcher.add_handler(CommandHandler("ip", server_ip))

    dispatcher.add_handler(CommandHandler("url", show_url, pass_args=True))
    dispatcher.add_handler(CommandHandler("list", list_urls))
    dispatcher.add_handler(CommandHandler("feed", rss_update))

    dispatcher.add_handler(CommandHandler("test", test))

    dispatcher.add_handler(CommandHandler("add", add_url, pass_args=True))
    dispatcher.add_handler(CommandHandler("remove", remove_url, pass_args=True))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
