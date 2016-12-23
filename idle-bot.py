#!/usr/bin/env python3

import os
import sys
import logging
import configparser
import requests
import re
import subprocess
import time
import multiprocessing
import platform

import bs4

from optparse import OptionParser
from ctypes import CDLL

os.chdir(os.path.dirname(__file__))

class Error(Exception):
    name = None
    def __init__(self, message):
        log = logging.getLogger(self.name)
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
    def __init__(self, config, log_level=logging.INFO):
        if not config["auth"]["sessionid"]:
            raise AuthError("«sessionid» not set")
        if not config["auth"]["steamLogin"]:
            raise AuthError("«steamLogin» not set")
        self.cookies = {"sessionid": config["auth"]["sessionid"], "steamLogin": config["auth"]["steamLogin"]}

        self.idleTime = int(config["main"]["idletime"])
        if not self.idleTime:
            self.idleTime = 300

        self.idleGames = int(config["main"]["idleGames"])
        if not self.idleGames:
            self.idleGames = 1

        self.log_level = log_level
        self.__logger()

        self.err_queue = multiprocessing.Queue()

        self.gamesInProgress = []

    def __logger(self):
        self.log = logging.getLogger('Bot')
        formatter = logging.Formatter('[%(asctime)s][%(name)s][%(processName)s][%(levelname)s]: %(message)s',
                                      "%Y-%m-%d %H:%M:%S")
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        self.log.addHandler(console)
        self.log.setLevel(self.log_level)

    def __getstate__(self):
        self_dict = self.__dict__
        try:
            self_dict.pop('log')
        except:
            pass

        return self_dict

    def __setstate__(self, d):
        self.__dict__.update(d)
        self.__logger()

    def start(self):
        profileURL = "http://steamcommunity.com/profiles/%s" % config["auth"]["steamLogin"][:17]
        badgesURL = "%s/badges/" % profileURL

        badges_req = requests.get(badgesURL, cookies=self.cookies)
        badgePageData = bs4.BeautifulSoup(badges_req.text, "lxml")

        auth = badgePageData.find("a",{"class": "user_avatar"}) != None
        if not auth:
            raise AuthError("Can't log in to Steam. Check cookie.")

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
            badges_req = requests.get("%(url)s?p=%(page)s" % {"url": badgesURL, "page": currentPage}, cookies=self.cookies)
            badgePageData = bs4.BeautifulSoup(badges_req.text, "lxml")
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
                    process = multiprocessing.Process(target=self.idle_process, args=(game, ), name=game["title"])
                    process.start()
                    self.log.info("Starting idle game «%s» to get %s cards" % (game["title"], game["cards"]))
                    self.gamesInProgress.append(game)
                    break
                else:
                    self.idle_games()

        self.idle_games()

        self.log.info("All cards recive.")

    def stop(self):
        for child in multiprocessing.active_children():
            child.terminate()

        sys.exit()

    def idle_games(self):
        time.sleep(5)
        if not self.err_queue.empty():
            msg = self.err_queue.get()
            self.err_queue.put(msg)
            raise SteamApiError(msg)

        self.log.debug("Idle %02d:%02d min." % divmod(self.idleTime, 60))
        time.sleep(self.idleTime)

        for child in multiprocessing.active_children():
            child.terminate()

        time.sleep(5)
        newGamesInProgress = []
        for game in self.gamesInProgress:
            self.log.debug("Check cards left for «%s» game" % game["title"])
            badge_req = requests.get(game["url"], cookies=self.cookies)
            badgeData = bs4.BeautifulSoup(badge_req.text, "lxml")
            newBadgeDropLeft = int(
                re.findall("\d+", badgeData.find("span", {"class": "progress_info_bold"}).get_text())[0])
            if newBadgeDropLeft > 0:
                if game['cards'] != newBadgeDropLeft:
                    game['cards'] = newBadgeDropLeft
                    process = multiprocessing.Process(target=self.idle_process, args=(game,), name=game["title"])
                    process.start()
                    self.log.info("Continuing idle game «%s» to get %s cards" % (game["title"], game['cards']))
                else:
                    process = multiprocessing.Process(target=self.idle_process, args=(game,), name=game["title"])
                    process.start()

                newGamesInProgress.append(game)

        self.gamesInProgress = newGamesInProgress

    def idle_process(self, game):
        try:
            if sys.platform.startswith('win32'):
                self.log.debug('Loading Windows library')
                try:
                    steam_api = CDLL('steam_api.dll')
                except:
                    self.err_queue.put("Couldn't initialize Steam API. Make sure that in bot folder have steam_api library.")
                    time.sleep(self.idleTime)
            elif sys.platform.startswith('linux'):
                if platform.architecture()[0].startswith('32bit'):
                    self.log.debug('Loading Linux 32bit library')
                    try:
                        steam_api = CDLL('./libsteam_api32.so')
                    except:
                        self.err_queue.put("Couldn't initialize Steam API. Make sure that in bot folder have steam_api library.")
                        time.sleep(self.idleTime)
                elif platform.architecture()[0].startswith('64bit'):
                    self.log.debug('Loading Linux 64bit library')
                    try:
                        steam_api = CDLL('./libsteam_api64.so')
                    except:
                        self.err_queue.put("Couldn't initialize Steam API. Make sure that in bot folder have steam_api library.")
                        time.sleep(self.idleTime)
                else:
                    raise ArchitectureError('Linux architecture not supported')
            elif sys.platform.startswith('darwin'):
                self.log.debug('Loading OSX library')
                try:
                    steam_api = CDLL('./libsteam_api.dylib')
                except:
                    self.err_queue.put("Couldn't initialize Steam API. Make sure that in bot folder have steam_api library.")
                    time.sleep(self.idleTime)
            else:
                raise OSError('Operating system not supported')

            os.environ["SteamAppId"] = str(game['id'])
            stderr = os.dup(2)
            silent = os.open(os.devnull, os.O_WRONLY)
            os.dup2(silent, 2)
            apiInit = int(steam_api.SteamAPI_Init())
            os.dup2(stderr, 2)
            if not apiInit:
                self.err_queue.put("Couldn't initialize Steam API. Make sure that in bot folder have steam_api library.")

            while True:
                time.sleep(3000)
        except KeyboardInterrupt:
            self.log.debug("Interrupted by user.")
            self.stop()


if __name__ == '__main__':
    opt_parser = OptionParser()
    opt_parser.add_option("--debug", action="store_true", dest="debug", default=False, help="Enable debug messanges")
    options, args = opt_parser.parse_args()

    log = logging.getLogger('Main')
    formatter = logging.Formatter('[%(asctime)s][%(name)s][%(processName)s][%(levelname)s]: %(message)s', "%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    log.addHandler(console)

    if options.debug == True:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    log.setLevel(log_level)

    log.info("WELCOME TO PYTHON IDLE MASTER REBORN")

    config = configparser.ConfigParser()
    try:
        config.read_file(open("idle-bot.ini"))
    except FileNotFoundError:
        log.error("No config file. Please copy «idle-bot.exp» as «idle-bot.ini» and edit it.")
        sys.exit()

    idleBot = IdleBot(config, log_level=log_level)
    try:
        idleBot.start()
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
        idleBot.stop()
    except (SteamApiError, AuthError, ArchitectureError, OSError):
        idleBot.stop()