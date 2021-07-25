#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from snipsTools import SnipsConfigParser
from hermes_python.hermes import Hermes
import os
import re
import inflect
import queue
import paho.mqtt.publish as publish
import json
import asyncio
from ourgroceries import OurGroceries

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
        self.loop = asyncio.get_event_loop()
        self.og = OurGroceries(username, password)
        self.loop.run_until_complete(self.og.login())
        self.default_list = config.get('global').get("defaultlist")
        print("Default List is " + self.default_list)
        self.inflect_engine = inflect.engine()
        self.inject_personal_data()
        self.start_blocking()
        
    def inject_personal_data(self):
        """ Uses MQTT to inject the master list and list of lists """
        print("Injecting Entites")
        my_lists = self.loop.run_until_complete(self.og.get_my_lists())
        master_list_id = my_lists["masterListId"]
        
        master_list_contents = self.loop.run_until_complete(self.og.get_list_items(list_id=master_list_id))
        master_list_items = [x["value"] for x in master_list_contents["list"]["items"]]

        list_names = [x['name'] for x in my_lists['shoppingLists']]

        # while we are in here, store a mapping from name to ID for use later
        self.list_name_to_id = { x['name'] : x['id'] for x in my_lists['shoppingLists']}
        
        operation = {"itemType" : master_list_items, "listName" : list_names}
        
        operations = [["add", operation]]
        payload = {"operations" : operations}

        publish.single("hermes/injection/perform", json.dumps(payload), hostname=MQTT_IP_ADDR, port=MQTT_PORT)
        print("Finished Injection")

    ####    section -> extraction of slot value
    def extract_items(self, intent_message):
        items = []
        try:
            if intent_message.slots.itemType:
                for item in intent_message.slots.itemType.all():
                    items.append(item.value)
        except AttributeError:
            pass
        return items

    def extract_list(self, intent_message):
        try:
            if intent_message.slots.listName:
                for list_name in intent_message.slots.listName.all():
                    return list_name.value
        except AttributeError:
            pass
        return self.default_list
    
    ####    section -> handlers of intents
    def callback(self, hermes, intent_message):
        print("[OurGroceries] Received")
        intent_name = intent_message.intent.intent_name
        # strip off any user specific prefix
        intent_name = re.sub(r'^\w+:', '', intent_name)        
        if intent_name == 'addToList':
            self.add_to_list(hermes, intent_message)
        if intent_name == "readList":
            self.read_list(hermes, intent_message)
        if intent_name == "removeFromList":
            self.remove_from_list(hermes, intent_message)
        if intent_name == "listQuery":
            self.list_query(hermes, intent_message)

    # --> Register callback function and start MQTT
    def start_blocking(self):
        with Hermes(MQTT_ADDR) as h:
            h.subscribe_intents(self.callback).start()

    def add_to_list(self, hermes, intent_message):
        """ Handles addToList intent"""
        items = self.extract_items(intent_message)
        list_name = self.extract_list(intent_message)
        list_id = self.list_name_to_id[list_name]
        if len(items) > 0:
            for item in items:
                if item == "nothing":
                    self.terminate_feedback(hermes, intent_message, "Ok, sorry.")
                    return
                if item == "unknownword":
                    self.terminate_feedback(hermes, intent_message, "I do not recognize that item")
                    return
                
                self.loop.run_until_complete(self.og.add_item_to_list(list_id, item))
        
        text = 'Added ' + self.get_item_set_description(items) + ' to the ' + self.get_list_description(list_name)
        
        self.terminate_feedback(hermes, intent_message, text)

    def remove_from_list(self, hermes, intent_message):
        """ Handles the removeFromList intent """
        items = self.extract_items(intent_message)
        list_name = self.extract_list(intent_message)
        list_id = self.list_name_to_id[list_name]
        removed = []
        not_found = []
        current_list_contents = self.loop.run_until_complete(self.og.get_list_items(list_id))
        current_list_name_to_id = {x["value"] : x["id"] for x in current_list_contents["list"]["items"]}
        if len(items) > 0:
            for item in items:
                if item in current_list_name_to_id:
                    item_id = current_list_name_to_id[item]
                    self.loop.run_until_complete(self.og.remove_item_from_list(list_id, item_id))
                    removed.append(item)
                else:
                    not_found.append(item)

        text = ""
        if len(removed) != 0:
            text += 'Removed ' + self.get_item_set_description(removed) + ' from the ' + self.get_list_description(list_name) + '. '
        if len(not_found) != 0:
            text += "I could not find " +  self.get_item_set_description(not_found) + ' in the ' + self.get_list_description(list_name) +  '. '
 
        self.terminate_feedback(hermes, intent_message, text)

    def read_list(self, hermes, intent_message):
        """ Reads out the specified or default list """
        list_name = self.extract_list(intent_message)
        list_id = self.list_name_to_id[list_name]
        items_on_list = self.loop.run_until_complete(self.og.get_list_items(list_id))
        active_items = []
        
        for item in items_on_list["list"]["items"]:
            if item.get("crossedOff", False):
                continue
            active_items.append(item["value"])    

        count = len(active_items) 
        
        if count == 0:
            text = "The " + self.get_list_description(list_name) + " is empty."
        else:
            text = "Items on the " + self.get_list_description(list_name) + ': '

            text += self.get_item_set_description(active_items)
        
        self.terminate_feedback(hermes, intent_message, text)

    def list_query(self, hermes, intent_message):
        """ Handles the listQuery intent """
        items = self.extract_items(intent_message)
        list_name = self.extract_list(intent_message)
        list_id = self.list_name_to_id[list_name]
        items_on_list = self.loop.run_until_complete(self.og.get_list_items(list_id))
        names = []
        for item in items_on_list["list"]["items"]:
            if item.get("crossedOff", False):
                continue
            names.add(item["value"])

        found = []
        not_found = []
        for query in items:
            if query in names:
                found.add(query)
            else:
                not_found.add(query)

        text = ""
        if len(found) > 0:
            if len(found) >= 2:
                text += self.get_item_set_description(found) + " are on the list. "
            else:
                text += self.get_item_set_description(found) + " is not on the list. "
        if len(not_found) > 0:
            if len(not_found) >= 2:
                text += self.get_item_set_description(not_found) + " are not the list. "
            else:
                text += self.get_item_set_description(not_found) + " is on the list. "
        
        self.terminate_feedback(hermes, intent_message, text)    

    def get_list_description(self, list_name):
        """Returns list name for speaking """
        # if the list name doesn't already end in "list" add it for the purposes of speaking it
        if not re.search(' list$', list_name, re.I):
            list_name += ' List'
        
        return list_name

    def get_item_description(self, item):
        """ Formats an item name for speaking"""
        match = re.match(r'(.*) \((\d+)\)', item)
        if not match:
            return item
        
        # make sure if the thing has a number, that we treat it as plural
        item_text = match.group(1)
        singular = self.inflect_engine.singular_noun(item_text)
        # singular_noun returns False if it's already singular
        if singular == False:
            plural = self.inflect_engine.plural_noun(item_text)            
        else:
            plural = item_text
        return match.group(2) + " " + plural

    def get_item_set_description(self, item_set):
        """ Returns a speakable version of a list of items"""
        text = ""
        count = len(item_set)
        for idx, item in enumerate(item_set):
            text += self.get_item_description(item)
            if idx == count - 2:
                text += ', and '
            else:
                text += ', '

        return text
        
    ####    section -> feedback reply // future function
    def terminate_feedback(self, hermes, intent_message, text=""):
        hermes.publish_end_session(intent_message.session_id, text)

if __name__ == "__main__":
    Skill_OurGroceries()
