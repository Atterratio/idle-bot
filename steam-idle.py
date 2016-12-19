#!/usr/bin/env python3
from __future__ import print_function
import os
import sys
import platform
import logging
import time

from ctypes import CDLL
try: #Python 2
    from urllib2 import urlopen
except ImportError: # Python 3
    from urllib.request import urlopen
try:
    import Tkinter as tk
except ImportError:
    import tkinter as tk

log = logging.getLogger('Idle')
formatter = logging.Formatter('[%(asctime)s][%(name)s][%(levelname)s]: %(message)s')
console = logging.StreamHandler()
console.setFormatter(formatter)
log.addHandler(console)
log.setLevel(logging.DEBUG)

def get_steam_api():
    if sys.platform.startswith('win32'):
        log.info('Loading Windows library')
        steam_api = CDLL('steam_api.dll')
    elif sys.platform.startswith('linux'):
        if platform.architecture()[0].startswith('32bit'):
            log.info('Loading Linux 32bit library')
            steam_api = CDLL('./libsteam_api32.so')
        elif platform.architecture()[0].startswith('64bit'):
            log.info('Loading Linux 64bit library')
            steam_api = CDLL('./libsteam_api64.so')
        else:
            log.info('Linux architecture not supported')
    elif sys.platform.startswith('darwin'):
        log.info('Loading OSX library')
        steam_api = CDLL('./libsteam_api.dylib')
    else:
        log.info('Operating system not supported')
        sys.exit(1)
        
    return steam_api
    
if __name__ == '__main__':
    if len(sys.argv) != 2:
        log.error("Wrong number of arguments")
        sys.exit()
        
    str_app_id = sys.argv[1]
    
    os.environ["SteamAppId"] = str_app_id
    try:
        get_steam_api().SteamAPI_Init()
    except:
        log.error("Couldn't initialize Steam API")
        sys.exit()
    