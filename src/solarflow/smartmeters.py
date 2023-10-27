from paho.mqtt import client as mqtt_client
from datetime import datetime, timedelta
import logging
import json
import sys
from utils import TimewindowBuffer, RepeatedTimer, deep_get
import requests

green = "\x1b[33;32m"
reset = "\x1b[0m"
FORMAT = '%(asctime)s:%(levelname)s: %(message)s'
logging.basicConfig(stream=sys.stdout, level="INFO", format=FORMAT)
log = logging.getLogger("")

class Smartmeter:

    def __init__(self, client: mqtt_client, base_topic:str, cur_accessor:str = "Power.Power_curr", total_accessor:str = "Power.Total_in"):
        self.client = client
        self.base_topic = base_topic
        self.power = TimewindowBuffer(minutes=1)
        self.phase_values = {}
        self.cur_accessor = cur_accessor
        self.total_accessor = total_accessor
    
    def __str__(self):
        return ' '.join(f'{green}SMT: \
                        P:{self.power.wavg():>3.1f}W {self.power}{reset}'.split())
                        
    def subscribe(self):
        topics = [f'{self.base_topic}']
        for t in topics:
            self.client.subscribe(t)
            log.info(f'Smartmeter subscribing: {t}')
    
    def ready(self):
        return len(self.phase_values) > 0

    def updPower(self):
        phase_sum = sum(self.phase_values.values())
        self.power.add(phase_sum)

    def handleMsg(self, msg):
        if msg.topic.startswith(self.base_topic) and msg.payload:
            payload = json.loads(msg.payload.decode())

            if type(payload) is float or type(payload) is int:
                self.phase_values.update({msg.topic:payload})
            if type(payload) is dict:
                value = float(deep_get(payload,self.cur_accessor))
                self.phase_values.update({msg.topic:value})

            self.updPower()

    def getPower(self):
        return self.power.wavg()


class Poweropti(Smartmeter):
    POWEROPTI_API = "https://backend.powerfox.energy/api/2.0/my/main/current"

    def __init__(self, client: mqtt_client, user:str, password:str):
        self.client = client
        self.user = user
        self.password = password
        self.power = TimewindowBuffer(minutes=1)
        self.phase_values = {}
        self.session = None

    def __str__(self):
        return ' '.join(f'{green}SMT: \
                        T:PowerOpti \
                        P:{self.power.wavg():>3.1f}W {self.power}{reset}'.split())

    def pollPowerfoxAPI(self):
        if self.session == None:
            self.session = requests.Session()
            self.session.auth = (self.user, self.password)

        with self.session as s:
            resp = s.get(self.POWEROPTI_API)
            try:
                current = resp.json()
                watt = int(current['Watt'])
                outdated = bool(current['Outdated'])
                self.phase_values.update({"poweropti":watt})
                self.updPower()
                #self.client.publish(f'poweropti/power',watt)
            except:
                log.exception()

    def subscribe(self):
        updater = RepeatedTimer(5, self.pollPowerfoxAPI)

    def handleMsg(self, msg):
        pass
            
