#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from hermes_python.hermes import Hermes
import os
import re
from ourgroceriesclient import ourgroceriesclient
from snipshelpers.thread_handler import ThreadHandler
from snipshelpers.config_parser import SnipsConfigParser
import Queue

CONFIGURATION_ENCODING_FORMAT = "utf-8"

CONFIG_INI =  "config.ini"

MQTT_IP_ADDR = "localhost"
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
                password = config.get('secret').get('password')
                if password == "":
                    code = None
        if username is None or password is None:
            print('Bad configuration')
        self.client = ourgroceriesclient.OurGroceriesClient(username, password)
        self.default_list = config.get('global').get("defaultlist")
        print("Default List is " + self.default_list)
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
                items.append(item.value)
        return items

    def extract_list(self, intent_message):
        if intent_message.slots.listName:
            for list_name in intent_message.slots.listName.all():
                return list_name.value
        return self.default_list
    
    ####    section -> handlers of intents
    def callback(self, hermes, intent_message):
        print("[OurGroceries] Received")
        intent_name = intent_message.intent.intent_name
        # strip off any user specific prefix
        intent_name = re.sub(r'^\w+:', '', intent_name)        
        if intent_name == 'addToList':
            self.queue.put(self.add_to_list(hermes, intent_message))
        
    def add_to_list(self, hermes, intent_message):
        items = self.extract_items(intent_message)
        list_name = self.extract_list(intent_message)
        if len(items) > 0:
            for item in items:
                self.client.add_item_to_list_by_name(list_name, item)

        # if the list name doesn't already end in "list" add it for the purposes
        # of speaking it
        if not re.search(' list$', list_name, re.I):
            list_name += ' List'
            
        text = 'Added ' + ' and '.join(items) + ' to the ' + list_name
        
        self.terminate_feedback(hermes, intent_message, text)

    ####    section -> feedback reply // future function
    def terminate_feedback(self, hermes, intent_message, text=""):
        hermes.publish_end_session(intent_message.session_id, text)

if __name__ == "__main__":
    Skill_OurGroceries()
