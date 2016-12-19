#!/usr/bin/python3

import os
import sys
import logging
import configparser
import requests
import re
import subprocess
import time
import signal

import bs4

log = logging.getLogger('Main')
formatter = logging.Formatter('[%(asctime)s][%(name)s][%(levelname)s]: %(message)s')
console = logging.StreamHandler()
console.setFormatter(formatter)
log.addHandler(console)
log.setLevel(logging.DEBUG)


def main():
    log.info("WELCOME TO PYTHON IDLE MASTER REBORN")
    config = configparser.ConfigParser()
    try:
        config.read_file(open("config.ini"))

        sessionId = config["auth"]["sessionid"]
        if not sessionId:
            log.error("No sessionid set")

        steamLogin = config["auth"]["steamLogin"]
        if not steamLogin:
            log.error("No steamLogin set")

        idleTime = int(config["main"]["idletime"])
        if not idleTime:
            idleTime = 600

        if not sessionId or not steamLogin:
            sys.exit()

    except FileNotFoundError:
        log.error("No config file. Create empty.")
        config["main"] = {"idletime": 600}
        config["auth"] = {"sessionid": "", "steamlogin": ""}
        configfile = open('config.ini', 'w')
        config.write(configfile)
        sys.exit()

    myProfileURL = "http://steamcommunity.com/profiles/%s" % steamLogin[:17]

    cookies = {"sessionid": sessionId, "steamLogin": steamLogin}

    myBadgesURL = "%s/badges/" % myProfileURL
    # TODO: catch exceptions
    badges_req = requests.get("%s/badges/" % myProfileURL, cookies=cookies)

    badgePageData = bs4.BeautifulSoup(badges_req.text)

    loged = badgePageData.find("a",{"class": "user_avatar"}) != None
    if not loged:
        log.error("Invalid cookie data, cannot log in to Steam")
        sys.exit()

    try:
        badgePages = int(badgePageData.find_all("a",{"class": "pagelink"})[-1].text)
    except IndexError:
        badgePages = 1

    badgeSet = []
    badgesLeft = []
    currentpage = 1
    while currentpage <= badgePages:
        badges_req = requests.get("%(url)s?p=%(page)s" % {"url": myBadgesURL, "page": currentpage}, cookies=cookies)
        badgePageData = bs4.BeautifulSoup(badges_req.text)
        badgeSet = badgeSet + badgePageData.find_all("div", {"class": "badge_row"})
        currentpage = currentpage + 1

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

    log.info("Idle Master needs to idle %s games" % len(badgesLeft))

    for game in badgesLeft:
        gameId = game["id"]
        badgeURL = game["url"]
        badgeDropLeft = game["cards"]
        gameTitle = game["title"]

        log.info("Starting game «%s» to idle %s cards" % (gameTitle, badgeDropLeft))

        while badgeDropLeft > 0:
            process_idle = subprocess.Popen(["./steam-idle.py", str(gameId)])

            log.info("Idle %s min." % (idleTime // 60))
            time.sleep(idleTime)

            log.info("Check cards left for «%s» game" % gameTitle)
            process_idle.terminate()
            process_idle.communicate()
            time.sleep(10)
            badge_req = requests.get(badgeURL, cookies=cookies)
            badgeRawData = bs4.BeautifulSoup(badge_req.text)
            badgeDropLeft = int(re.findall("\d+", badgeRawData.find("span", {"class": "progress_info_bold"}).get_text())[0])

        log.info("End «%s» game idle " % gameTitle)

if __name__ == '__main__':
    main()


