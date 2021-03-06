#!/usr/bin/env python3

import os
import sys
import logging
import configparser
import requests
import re
import time
import multiprocessing
import platform

import bs4

from optparse import OptionParser
from ctypes import CDLL

try:
    import lxml
except:
    PARSER = "html.parser"
else:
    PARSER = "lxml"

os.chdir(os.path.dirname(__file__))


class Error(Exception):
    name = None

    def __init__(self, message):
        log = logging.getLogger(self.name)
        if not log.hasHandlers():
            formatter = logging.Formatter('[%(asctime)s][%(name)s][%(processName)s][%(levelname)s]: %(message)s', "%Y-%m-%d %H:%M:%S")
            console = logging.StreamHandler()
            console.setFormatter(formatter)
            log.addHandler(console)
        log.setLevel(logging.ERROR)
        log.error(message)


class AuthError(Error):
    name = "Auth"


class SteamApiError(Error):
    name = "Steam Api"


class ArchitectureError(Error):
    pass


class OSError(Error):
    pass


class IdleBot:
    def __init__(self, config, log_level):
        self.config = config

        self.log = logging.getLogger('Bot')
        if not self.log.hasHandlers():
            formatter = logging.Formatter('[%(asctime)s][%(name)s][%(processName)s][%(levelname)s]: %(message)s', "%Y-%m-%d %H:%M:%S")
            console = logging.StreamHandler()
            console.setFormatter(formatter)
            self.log.addHandler(console)
        self.log.setLevel(log_level)

        if not config["auth"]["steamLoginSecure"]:
            raise AuthError("«steamLoginSecure» not set")
        self.cookies = {"steamLoginSecure": config["auth"]["steamLoginSecure"]}

        self.idleTime = int(config["main"]["idletime"])
        if not self.idleTime:
            self.idleTime = 300

        self.idleGames = int(config["main"]["idleGames"])
        if not self.idleGames:
            self.idleGames = 1
        try:
            self.blacklist = [int(x.strip()) for x in config['main']['blacklist'].split(',') if x]
        except:
            self.blacklist = []

        self.err_queue = multiprocessing.Queue()

        self.gamesInProgress = []

    def start(self):
        profileURL = "http://steamcommunity.com/profiles/%s" % self.config["auth"]["steamLogin"][:17]
        badgesURL = "%s/badges/" % profileURL

        badges_html = requests.get('http://steamcommunity.com/', cookies=self.cookies).text
        badgePageData = bs4.BeautifulSoup(badges_html, PARSER)

        auth = badgePageData.find("a",{"class": "user_avatar"})
        if not auth:
            raise AuthError("Can't login to Steam. Check cookie.")

        try:
            # TODO: find way cath error if trying find wrong tag
            badgePages = int(badgePageData.find_all("a",{"class": "pagelink"})[-1].get_text())
        except IndexError:
            badgePages = 1

        badgeSet = []
        badgesLeft = []
        cardsLeft = 0
        currentPage = 1
        while currentPage <= badgePages:
            badges_html = requests.get("%(url)s?p=%(page)s" % {"url": badgesURL, "page": currentPage}, cookies=self.cookies).text
            badgePageData = bs4.BeautifulSoup(badges_html, PARSER)
            badgeSet = badgeSet + badgePageData.find_all("div", {"class": "badge_row"})
            currentPage += 1

        for badge in badgeSet:
            try:
                dropCount = int(re.findall("\d+", badge.find_all("span",{"class": "progress_info_bold"})[0].get_text())[0])
            except:
                continue

            if dropCount > 0:
                badgeURL = badge.find("a", {"class": "badge_row_overlay"})["href"]
                badgeId = int(re.findall("\d+", badgeURL)[0])
                badgeTitle = badge.find("div", {"class": "badge_title"}).get_text().rsplit("\t", 1)[0].strip()
                badgeData = {"id": badgeId, "url": badgeURL, "title": badgeTitle, "cards": dropCount}
                if badgeId not in self.blacklist:
                    badgesLeft.append(badgeData)
                    cardsLeft += dropCount

        self.log.info("Idle Master needs to idle %s games for %s cards" % (len(badgesLeft), cardsLeft))

        for game in badgesLeft:
            while True:
                if not self.err_queue.empty():
                    msg = self.err_queue.get()
                    self.err_queue.put(msg)
                    raise SteamApiError(msg)

                if len(self.gamesInProgress) < self.idleGames:
                    process = multiprocessing.Process(target=spawner, args=(game, self.err_queue, self.idleTime), name=game["title"])
                    process.start()
                    self.log.info("Starting idle game «%s» to get %s cards" % (game["title"], game["cards"]))
                    self.gamesInProgress.append(game)
                    break
                else:
                    self.idle_games()

        while self.gamesInProgress:
            self.idle_games()

        self.log.info("All cards recive.")

    def stop(self):
        for child in multiprocessing.active_children():
            child.terminate()

        sys.exit()

    def idle_games(self):
        if not self.err_queue.empty():
            msg = self.err_queue.get()
            self.err_queue.put(msg)
            raise SteamApiError(msg)

        self.log.debug("Idle %02d:%02d min." % divmod(self.idleTime, 60))
        time.sleep(self.idleTime)

        for child in multiprocessing.active_children():
            child.terminate()

        gamesInProgress = []
        for game in self.gamesInProgress:
            self.log.debug("Check cards left for «%s» game" % game["title"])
            badges_html = requests.get(game["url"], cookies=self.cookies).text
            badgeData = bs4.BeautifulSoup(badges_html, PARSER)
            try:
                newBadgeDropLeft = int(re.findall("\d+", badgeData.find("span", {"class": "progress_info_bold"}).get_text())[0])
            except (IndexError, AttributeError):
                newBadgeDropLeft = 0

            if newBadgeDropLeft > 0:
                if game['cards'] != newBadgeDropLeft:
                    game['cards'] = newBadgeDropLeft
                    process = multiprocessing.Process(target=spawner, args=(game, self.err_queue, self.idleTime), name=game["title"])
                    process.start()
                    gamesInProgress.append(game)
                    self.log.info("Continuing idle game «%s» to get %s cards" % (game["title"], game['cards']))
                else:
                    process = multiprocessing.Process(target=spawner, args=(game, self.err_queue, self.idleTime), name=game["title"])
                    process.start()
                    gamesInProgress.append(game)

            else:
                self.log.info("Stoping idle game «%s»" % game["title"])

        self.gamesInProgress = gamesInProgress


def spawner(game, err_queue, idle):
    try:
        if sys.platform.startswith('win32'):
            try:
                steam_api = CDLL('steam_api.dll')
            except:
                err_queue.put("Couldn't initialize Steam API. Make sure that in bot folder have steam_api library.")

        elif sys.platform.startswith('linux'):
            try:
                steam_api = CDLL('./libsteam_api.so')
            except:
                err_queue.put("Couldn't initialize Steam API. Make sure that in bot folder have steam_api library.")

        elif sys.platform.startswith('darwin'):
            try:
                steam_api = CDLL('./libsteam_api.dylib')
            except:
                err_queue.put("Couldn't initialize Steam API. Make sure that in bot folder have steam_api library.")
        else:
            raise OSError('Operating system not supported')

        os.environ["SteamAppId"] = str(game['id'])
        stderr = os.dup(2)
        silent = os.open(os.devnull, os.O_WRONLY)
        os.dup2(silent, 2)
        apiInit = int(steam_api.SteamAPI_Init())
        os.dup2(stderr, 2)
        if not apiInit:
            err_queue.put("Couldn't initialize Steam API. Make sure that Steam is running.")

        while True:
            time.sleep(idle)

    except KeyboardInterrupt:
        for child in multiprocessing.active_children():
            child.terminate()

        sys.exit()

def main():
    #multiprocessing.set_start_method('spawn')  #set mp start method like on windows for testing
    opt_parser = OptionParser()
    opt_parser.add_option("--debug", action="store_true", dest="debug", default=False, help="Enable debug messanges")
    options, args = opt_parser.parse_args()

    log = logging.getLogger('Main')
    if not log.hasHandlers():
        formatter = logging.Formatter('[%(asctime)s][%(name)s][%(processName)s][%(levelname)s]: %(message)s', "%Y-%m-%d %H:%M:%S")
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        log.addHandler(console)

    if options.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    log.setLevel(log_level)

    log.info("WELCOME TO PYTHON IDLE MASTER REBORN")

    config = configparser.ConfigParser()
    try:
        config.read_file(open("idle_bot.ini"))
    except FileNotFoundError:
        log.error("No config file. Please copy «idle_bot.exp» as «idle_bot.ini» and edit it.")
        sys.exit()

    bot = IdleBot(config, log_level)
    try:
        bot.start()
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
        bot.stop()
    except Error:
        bot.stop()

if __name__ == '__main__':
    main()
