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
    help_all = strings.help_message

    update.effective_message.reply_text(text=help_all)


def test(bot, update):
    update.effective_message.reply_text("Bot status: Online, duh")


def server_ip(bot, update):
    user = update.message.from_user
    user_id = update.effective_user.id

    if user_id == owner_id:
        res = requests.get("http://ipinfo.io/ip")
        ip = res.text  #  might need a .decode("utf-8") if you're using python 2. Test it!
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
        user_id = update.effective_user.id
        chat_id = str(update.effective_chat.id)
        url = args[0]
        OldEntry = 'none'

        url_processed = feedparser.parse(url)

        # check if URL is a valid RSS Feed URL
        if url_processed.bozo == 1:
            # it's not a valid RSS Feed URL
            update.effective_message.reply_text(strings.stringInvalidURLbozo)
        else:
            res = SESSION.query(RSS_Feed).filter(RSS_Feed.user_id == user_id, RSS_Feed.url == url, RSS_Feed.chat_id == chat_id).all()

            # check if there is an entry already added to the DB
            if res:
                update.effective_message.reply_text(strings.stringURLalreadyAdded)
            else:
                action = RSS_Feed(user_id, chat_id, url, OldEntry)
                SESSION.add(action)
                SESSION.commit()

                update.effective_message.reply_text(strings.stringURLadded)

                print("\n" + "###" + "\n" + "# New subscription for user " + user_id + " with URL " + url + "\n" + "###" + "\n")


def remove_url(bot, update, args):
    # check if there is anything written as arguments
    if len(args[0]) < 3:
        # there's nothing written or it's too less text to be an actual URL
        update.effective_message.reply_text(strings.stringInvalidURL)
    else:
        user_id = update.effective_user.id
        chat_id = str(update.message.chat_id)
        url = args[0]

        url_processed = feedparser.parse(url)

        # check if URL is a valid RSS Feed URL
        if url_processed.bozo == 1:
            # it's not a valid RSS Feed URL
            update.effective_message.reply_text(strings.stringInvalidURLbozo)
        else:
            user_data = SESSION.query(RSS_Feed).filter(RSS_Feed.user_id == user_id, RSS_Feed.chat_id == chat_id,
                                                       RSS_Feed.url == url).all()
            if user_data:
                for i in user_data:
                    SESSION.delete(i)

                SESSION.commit()

                update.effective_message.reply_text(strings.stringURLremoved)
            else:
                update.effective_message.reply_text(strings.stringURLalreadyRemoved)


def rss_update(bot, job):
    user_data = SESSION.query(RSS_Feed).all()

    #check every row in the DB
    for row in user_data:
        user_id = row.chat_id
        url = row.url
        feed_processed = feedparser.parse(url)
        OldEntry = row.old_entry
        CurrentEntry = feed_processed.entries[0].link

        #check if there are any new updates to the RSS Feed
        if CurrentEntry != OldEntry:
            row.old_entry = CurrentEntry
            SESSION.commit()

            final_message = "title: \"" + feed_processed.entries[0].title + "\"" + "\n\n" + "link: " + \
                            feed_processed.entries[0].link

            bot.send_message(chat_id=user_id, text=final_message)
        else:
            print("\n" + "###" + "\n" + "# No new updates for user " + user_id + " with URL " + CurrentEntry + "\n" + "###" + "\n")


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
