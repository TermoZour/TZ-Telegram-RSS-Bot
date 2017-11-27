#!/usr/bin/python3
# -*- coding: utf-8 -*-

from telegram.ext import Updater, CommandHandler
from telegram import ParseMode

import configparser
import logging

import requests

import strings
import feedparser

from sqlalchemy import create_engine, Column, Integer, UnicodeText, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

# ---

# initializing config file
config = configparser.ConfigParser()
config.read("properties.ini")

# getting bot owner ID from config file
owner_id = int(config.get("ADMIN", "admin_id"))

# ---

def start(bot, update):
    update.effective_message.reply_text(strings.stringHelp)


def unknown(bot, update):
    update.effective_message.reply_text(strings.errorUnknownCommand)


def help(bot, update):

    # gather all commands help messages from the strings.py file
    help_all = strings.help_message

    update.effective_message.reply_text(text=help_all)


def test(bot, update):
    update.effective_message.reply_text("Bot status: Online, duh")


def server_ip(bot, update):
    # gather user data like username, first name, last name
    user = update.message.from_user

    # gather telegram user ID
    user_id = update.effective_user.id

    # check if the sender's ID is the same as the owner's ID set in the config. for security purposes
    if user_id == owner_id:

        #access the site
        res = requests.get("http://ipinfo.io/ip")

        #save the text into a variable to be sent later by the bot
        ip = res.text

        update.effective_message.reply_text("Server IP: " + ip)
    else:
        update.effective_message.reply_text("I'm sorry " + user.first_name + ", but I can't let you do that.")

# ---

def add_url(bot, update, args):
    # check if there is anything written as arguments
    if len(args[0]) < 3:
        # there's nothing written or it's too less text to be an actual URL
        update.effective_message.reply_text(strings.stringInvalidURL)
    else:
        # there is an actual URL written

        # gathers telegram user ID
        user_id = update.effective_user.id

        # gathers telegram chat ID (might be the same as user ID if message is sent to the bot via PM)
        chat_id = str(update.effective_chat.id)

        # gathers the URL from the command sent by the user
        url = args[0]

        #sets OldEntry as "none" to be stored in the DB so it can later be changed when updates occur
        OldEntry = 'none'

        # pass the URL to be processed by feedparser
        url_processed = feedparser.parse(url)

        # check if URL is a valid RSS Feed URL
        if url_processed.bozo == 1:
            # it's not a valid RSS Feed URL
            update.effective_message.reply_text(strings.stringInvalidURLbozo)
        else:
            # the RSS Feed URL is valid

            # gather the row which contains exactly that telegram user ID, group ID and URL for later comparison
            res = SESSION.query(RSS_Feed).filter(RSS_Feed.user_id == user_id, RSS_Feed.url == url, RSS_Feed.chat_id == chat_id).all()

            # check if there is an entry already added to the DB by the same user in the same group with the same URL
            if res:
                # there is already a link added to the DB
                update.effective_message.reply_text(strings.stringURLalreadyAdded)
            else:
                # there is no link added, so we'll add it now

                # prepare the action for the DB push
                action = RSS_Feed(user_id, chat_id, url, OldEntry)

                # add the action to the DB query
                SESSION.add(action)

                # commit the changes to the DB
                SESSION.commit()

                update.effective_message.reply_text(strings.stringURLadded)

                print("\n" + "###" + "\n" + "# New subscription for user " + user_id + " with URL " + url + "\n" + "###" + "\n")


def remove_url(bot, update, args):
    # check if there is anything written as arguments
    if len(args[0]) < 3:
        # there's nothing written or it's too less text to be an actual URL
        update.effective_message.reply_text(strings.stringInvalidURL)
    else:
        # gathers telegram user ID
        user_id = update.effective_user.id

        # gathers telegram chat ID (might be the same as user ID if message is sent to the bot via PM)
        chat_id = str(update.message.chat_id)

        # gathers the URL from the command sent by the user
        url = args[0]

        # pass the URL to be processed by feedparser
        url_processed = feedparser.parse(url)

        # check if URL is a valid RSS Feed URL
        if url_processed.bozo == 1:
            # it's not a valid RSS Feed URL
            update.effective_message.reply_text(strings.stringInvalidURLbozo)
        else:
            # it's a valid RSS Feed URL

            # gather all duplicates(if possible) for the same User ID, Chat ID and URL
            user_data = SESSION.query(RSS_Feed).filter(RSS_Feed.user_id == user_id, RSS_Feed.chat_id == chat_id, RSS_Feed.url == url).all()

            # check if it finds the URL in the database
            if user_data:

                # this loops to delete any possible duplicates for the same User ID, Chat ID and URL
                for i in user_data:
                    # add the action to the DB query
                    SESSION.delete(i)

                # commit the changes to the DB
                SESSION.commit()

                update.effective_message.reply_text(strings.stringURLremoved)
            else:
                update.effective_message.reply_text(strings.stringURLalreadyRemoved)


def rss_update(bot, job):
    # get all of the DB data
    user_data = SESSION.query(RSS_Feed).all()

    # this loop checks for every row in the DB
    for row in user_data:

        # get user/chat ID from DB
        user_id = row.chat_id

        # get RSS URL from DB
        url = row.url

        # process the feed
        feed_processed = feedparser.parse(url)

        #get the last update's entry from the DB
        OldEntry = row.old_entry

        # define empty list for when there's new updates to a RSS URL
        QueuedLinks = []

        # this loop checks for every entry from the RSS Feed URL from the DB row
        for entry in feed_processed.entries:
            # check if there are any new updates to the RSS Feed from the old entry
            if entry.link != OldEntry:

                # there is a new entry, so it's link is added to the QueuedLinks list for later usage
                QueuedLinks.append(entry.link)
            else:
                break
        # check if there's any new entries queued from the last check
        if QueuedLinks:

            # set the new old_entry with the latest update from the RSS Feed
            row.old_entry = QueuedLinks[0]

            # commit the changes to the DB
            SESSION.commit()
        else:
            print("\n" + "###" + "\n" + "# No new updates for chat " + str(user_id) + " with URL " + url + "\n" + "###" + "\n")

        # this loop sends every new update to each user from each group based on the DB
        for entry in QueuedLinks[::-1]:

            # make the final message with the layout: "Title: <rss_feed_title> and Link: <rss_feed_link>"
            final_message = "title: \"" + entry.title + "\"" + "\n\n" + "link: " + entry

            bot.send_message(chat_id=user_id, text=final_message, parse_mode=ParseMode.MARKDOWN)


# ---

def markdownTest(bot, update):
    chat_id = update.effective_chat.id

    bot.send_message(chat_id=chat_id, text="*bold* _italic_  `fixed width font` [link](http://google.com).", parse_mode=ParseMode.MARKDOWN)

# ---

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
    url = Column(UnicodeText)
    old_entry = Column(UnicodeText)

    def __init__(self, user_id, chat_id, url, old_entry):
        self.user_id = user_id
        self.chat_id = chat_id
        self.url = url
        self.old_entry = old_entry

    def __repr__(self):
        return "<RSS_Feed for {} with chatID {} at url {} with old entry {}>".format(self.user_id, self.chat_id, self.url, self.old_entry)


BASE.metadata.create_all()

# ---

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    updater = Updater(config.get("KEY", "tg_API_token"))

    job = updater.job_queue
    job_minute = job.run_repeating(rss_update, int(config.get("UPDATE", "update_interval")), first=0)
    job_minute.enabled = True

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help))
    dispatcher.add_handler(CommandHandler("ip", server_ip))

    dispatcher.add_handler(CommandHandler("feed", rss_update))
    dispatcher.add_handler(CommandHandler("test", test))

    dispatcher.add_handler(CommandHandler("markdown", markdownTest))

    dispatcher.add_handler(CommandHandler("add", add_url, pass_args=True))
    dispatcher.add_handler(CommandHandler("remove", remove_url, pass_args=True))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
