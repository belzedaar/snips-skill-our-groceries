# -*-: coding utf-8 -*-
""" Client to talk to Our Groceries API. """

import requests
import json
import sys
import re
from fuzzywuzzy import fuzz

class OurGroceriesClient:
    """Client to talk to Our Groceries API"""

    cookieName = 'ourgroceries-auth'
    url = 'https://www.ourgroceries.com/your-lists/'

    def __init__(self, username=None, password=None):
        """ Initialisation.
        
        :param username: Our Groceries email 
        :param password: Our Groceries password.
        """
        self.signed_in = False
        self.username = username
        payload = {
            'emailAddress': username, 
            'password': password, 
            'action': 'sign-me-in', 
            'staySignedIn': 'on' 
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36',
            'Referer': 'https://www.ourgroceries.com/sign-in',
            'Origin': 'https://www.ourgroceries.com'
        }
        r = requests.post('https://www.ourgroceries.com/sign-in', payload, allow_redirects=False, headers=headers)
        if r.status_code != 302:
            return

        self.sign_in_cookie =  r.cookies.get_dict()[OurGroceriesClient.cookieName]
        
        r = requests.get(OurGroceriesClient.url, headers=headers, cookies=self.get_cookie())
        match = re.search( r'var g_teamId = "([^"]+)"', r.text)
        if not match:
            return
        
        self.team_id = match.group(1)
        self.signed_in = True
        self.cached_list_ids = self.get_list_ids()
        
    def get_overview(self):
        """ Returns the overview - this is your list of lists, and your receipes. """
        return self.exec_command("getOverview")
    
    def get_list_names(self):
        """ Returns the list of shopping list names"""
        json = self.get_overview()
        if not json:
            return False
        
        lists = json["shoppingLists"]
        return [x["name"] for x in lists]
    
    def get_list_ids(self):
        """ Returns a dict st of shopping list ids and names."""
        json = self.get_overview()
        if not json:
            return False
        
        lists = json["shoppingLists"]
        return dict((x["name"], x["id"]) for x in lists)
        
    def get_master_list(self):
        """ Returns list of everything you've ever added to the lists"""
        return self.exec_command('getMasterList', {'version' : ''})

    def get_list(self, listId):
        """ Returns a specific list by id"""
        return self.exec_command('getList', {'listId': listId, 'version' : ''})

    def get_list_by_name(self, listName):
        """ Returns a specific list by name """
        return self.exec_command('getList', {'listId': self.get_list_id_from_name(listName), 'version' : ''})

    def add_item_to_list(self, listId, item, count = None):
        """ Adds an item to a list. Returns item id."""
        if count:
            item += ' ('
            item += str(count)
            item += ')'

        json = self.exec_command('insertItem', {'listId': listId, 'value' : item})
        return json["itemId"]

    def add_item_to_list_by_name(self, listName, item, count = None):
        """ Adds an item to a list, looking up the list Id by name """
        return self.add_item_to_list(self.get_list_id_from_name(listName), item, count)

    def delete_all_crossed_off_items(self, listId):
        """ Deletes all the crossed off items from the list"""
        return self.exec_command('deleteAllCrossedOffItems', {'listId': listId, 'version' : ''})

    def delete_item_from_list(self, listId, itemId):
        """ Delete an item from a list. """
        return self.exec_command('deleteItem',  {'listId': listId, 'itemId' : itemId})

    def delete_item_from_list_by_name(self, listName, itemId):
        """ Delete an item from a list, taking the list name. """
        return self.exec_command('deleteItem',  {'listId': self.get_list_id_from_name(listName), 'itemId' : itemId})

    def get_list_id_from_name(self, listName):
        """ Does a fuzzy search to find the closest list from the cache that we can"""
        fuzzyMatch = -1
        retVal = None
        for name in self.cached_list_ids:
            ratio = fuzz.ratio(name, listName)
            if ratio > fuzzyMatch:
                fuzzyMatch = ratio
                retVal = self.cached_list_ids[name]
        
        return retVal

    def exec_command(self, command, args = None):
        """ Posts a named command. """
        if not self.signed_in:
            return False
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36',
            'Referer': 'https://www.ourgroceries.com/your_lists',
            'Origin': 'https://www.ourgroceries.com'
        }

        # We always send these args
        json = { "command": command, "teamId" : self.team_id }
        # Add the passed in additional args to the standard ones
        if args:
            json.update(args)

        r = requests.post(OurGroceriesClient.url, json=json, headers=headers, cookies=self.get_cookie())
        return r.json()
        
    def get_cookie(self):
        return {OurGroceriesClient.cookieName : self.sign_in_cookie}

if __name__ == "__main__":
    client = OurGroceriesClient(sys.argv[1], sys.argv[2])
    print(client.cached_list_ids)
    print(client.add_item_to_list_by_name("Shopping List", "Apples"))

