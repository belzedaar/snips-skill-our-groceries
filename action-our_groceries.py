#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from hermes_python.hermes import Hermes
import os
from ourgroceriesclient import ourgroceriesclient
from snipshelpers.thread_handler import ThreadHandler
from snipshelpers.config_parser import SnipsConfigParser
import Queue

CONFIGURATION_ENCODING_FORMAT = "utf-8"

CONFIG_INI =  "config.ini"

MQTT_IP_ADDR = "localhost"
#MQTT_IP_ADDR = "192.168.86.2"
MQTT_PORT = 1883
MQTT_ADDR = "{}:{}".format(MQTT_IP_ADDR, str(MQTT_PORT))

_id = "snips-skill-our-groceries"

class Skill_OurGroceries:
    def __init__(self):
        try:
            config = SnipsConfigParser.read_configuration_file(CONFIG_INI)
        except :
            config = None
        username = None
        password = None
        if config and config.get('secret', None) is not None:
            if config.get('secret').get('username', None) is not None:
                username = config.get('secret').get('username')
                if username == "":
                    username = None
            if config.get('secret').get('password', None) is not None:
                code = config.get('secret').get(password)
                if password == "":
                    code = None
        if username is None or password is None:
            print('No configuration')
        self.client = ourgroceriesclient.OurGroceriesClient(username, password)
        self.queue = Queue.Queue()
        self.thread_handler = ThreadHandler()
        self.thread_handler.run(target=self.start_blocking)
        self.thread_handler.start_run_loop()

    def start_blocking(self, run_event):
        while run_event.is_set():
            try:
                self.queue.get(False)
            except Queue.Empty:
                with Hermes(MQTT_ADDR) as h:
                    h.subscribe_intents(self.callback).start()

    ####    section -> extraction of slot value
    def extract_items(self, intent_message):
        items = []
        if intent_message.slots.itemType:
            for item in intent_message.slots.itemType.all():
                print(type(item.value))
                items.append(item.value)
        return items

    ####    section -> handlers of intents
    def callback(self, hermes, intent_message):
        print("[OurGroceries] Received")
        ## all the intents have a house_room slot, extract here
        if intent_message.intent.intent_name == 'addToList':
            self.queue.put(self.add_to_list(hermes, intent_message))
        
    def add_to_list(self, hermes, intent_message):
        items = self.extract_items(intent_message)
        if len(items) > 0:
            for item in items:
                print(item)
        self.terminate_feedback(hermes, intent_message)

    ####    section -> feedback reply // future function
    def terminate_feedback(self, hermes, intent_message, mode='default'):
        if mode == 'default':
            hermes.publish_end_session(intent_message.session_id, "")
        else:
            #### more design
            hermes.publish_end_session(intent_message.session_id, "")

if __name__ == "__main__":
    Skill_OurGroceries()
