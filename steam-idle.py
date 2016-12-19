#!/usr/bin/env python3
from __future__ import print_function
import os
import sys
import platform
import logging
import time

from ctypes import CDLL

log = logging.getLogger('Idle')
formatter = logging.Formatter('[%(asctime)s][%(name)s][%(levelname)s]: %(message)s')
console = logging.StreamHandler()
console.setFormatter(formatter)
log.addHandler(console)
log.setLevel(logging.DEBUG)

def get_steam_api():
    if sys.platform.startswith('win32'):
        log.debug('Loading Windows library')
        steam_api = CDLL('steam_api.dll')
        CDLL()
    elif sys.platform.startswith('linux'):
        if platform.architecture()[0].startswith('32bit'):
            log.debug('Loading Linux 32bit library')
            steam_api = CDLL('./libsteam_api32.so')
        elif platform.architecture()[0].startswith('64bit'):
            log.debug('Loading Linux 64bit library')
            steam_api = CDLL('./libsteam_api64.so')
        else:
            log.debug('Linux architecture not supported')
    elif sys.platform.startswith('darwin'):
        log.debug('Loading OSX library')
        steam_api = CDLL('./libsteam_api.dylib')
    else:
        log.error('Operating system not supported')
        sys.exit(1)
        
    return steam_api
    
if __name__ == '__main__':
    if len(sys.argv) != 2:
        log.error("Wrong number of arguments")
        sys.exit(1)

    str_app_id = sys.argv[1]

    os.environ["SteamAppId"] = str_app_id
    signal = 1
    steam_api = get_steam_api()
    try:
        status = int(steam_api.SteamAPI_Init())
        if not status:
            log.error("Couldn't initialize Steam API")
            sys.exit(1)

        while signal:
            signal = int(input())
            log.debug("Recive signal: %s" % signal)

        #steam_api.SteamAPI_Shutdown()

        sys.exit(0)

    except EOFError:
        pass
    except:
        log.error("Couldn't initialize Steam API")
        sys.exit(1)
    