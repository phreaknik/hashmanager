#!/usr/bin/env python
  
# Copyright 2018 Blade M. Doyle
# Copyright 2019 Phreaknik
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os
import sys
import time
import json
import pprint
import requests
import traceback
import toml
from datetime import datetime, timedelta
pp = pprint.PrettyPrinter(indent=4)

## Load user config
config = toml.load("config.toml")
API_ID = config['nicehash']['API_ID']
API_KEY = config['nicehash']['API_KEY']
PRICE_ADJUST_RATE = config['nicehash']['PRICE_ADJUST_RATE']

if PRICE_ADJUST_RATE == "slow":
    MAX_INCREASE = 0.0001   # Maximum amount to increase at once
    TARGET_MIN_ADD = 0.0000 # Amount to set order price over the absolute minimum
elif PRICE_ADJUST_RATE == "medium":
    MAX_INCREASE = 0.0002   # Maximum amount to increase at once
    TARGET_MIN_ADD = 0.0001 # Amount to set order price over the absolute minimum
elif PRICE_ADJUST_RATE == "fast":
    MAX_INCREASE = 0.0005   # Maximum amount to increase at once
    TARGET_MIN_ADD = 0.0001 # Amount to set order price over the absolute minimum
else:
    print("Error:  Missing config for nicehash PRICE_ADJUST_RATE")
    print("  Make sure PRICE_ADJUST_RATE is set to either \"slow\", \"medium\", or \"fast\" in config.toml")
    print("{}".format(str(e)))
    print("  ")
    sys.exit(1)

orders = {}

# Location Numbers (as defined: https://www.nicehash.com/doc-api)
# 0 for Europe (NiceHash), 1 for USA (WestHash);
LOCATIONS = {
        "EU": 0,
        "US": 1,
    }

# Algorithms
ALGOS = {
        # ... Add More as needed
        "GrinCuckaroo29": 38,
        "GrinCuckaroo31": 39,
    }

def __getLocationName(loc_num):
    if type(loc_num) == "String":
        loc_num = int(loc_num)
    for name, number in LOCATIONS.items():
        if number == loc_num:
            return name

def __getAlgoName(alg_num):
    if type(alg_num) == "String":
        alg_num = int(alg_num)
    for name, number in ALGOS.items():
        if number == alg_num:
            return name

def __callNicehashApi(method, args):
    url = "https://api.nicehash.com/api?method=" + method
    for arg, val in args.items():
        url +=  "&{}={}".format(arg, val)
          
    time.sleep(5)
    r = requests.get(
            url=url,
        )
    if r.status_code >= 300 or r.status_code < 200:
        error_msg = "Error calling {}.  Code: {} Reason: {}".format(url, r.status_code, r.reason)
        raise Exception(error_msg)
        
    r_json = r.json()
    result = r_json["result"]
    if "error" in result:
        message = result["error"]
        method = r_json["method"]
        error_msg = "Error calling {}. Reason: {}".format(method, message)
        raise Exception(error_msg)
    return result


def updateOrders():
    # Get all current orders
    current_orders = {}
    for location in LOCATIONS.values():
        for algo in ALGOS.values():
            getMyOrders_args = {
                "id": API_ID,
                "key": API_KEY,
                "location": location,
                "algo": algo,
                }
            result = __callNicehashApi("orders.get&my", getMyOrders_args)
            for order in result["orders"]:
                order_id = order["id"]
                current_orders[order_id] = order
                current_orders[order_id]["algo"] = int(algo)
                current_orders[order_id]["location"] = int(location)

    # Update the orders we are tracking
    # Remove orders that no longer exist
    for order_id in orders.keys():
        if not order_id in current_orders:
            print("Order no longer exists: {}".format(order_id))
            del orders[order_id]

    # Add new orders
    for order_id in current_orders.keys():
        if not order_id in orders:
            print("New order added: {}".format(order_id))
            orders[order_id] = current_orders[order_id]
            orders[order_id]["last_decreased"] = datetime(1970, 1, 1)

    # Update existing orders
    for order_id in current_orders.keys():
        if order_id in orders:
            orders[order_id]["limit_speed"] = float(current_orders[order_id]["limit_speed"])
            orders[order_id]["alive"] = current_orders[order_id]["alive"]
            orders[order_id]["price"] = float(current_orders[order_id]["price"])
            orders[order_id]["workers"] = int(current_orders[order_id]["workers"])
            orders[order_id]["accepted_speed"] = float(current_orders[order_id]["accepted_speed"])

    # Find the lowest price thats has miners working for each algo in each location
    target_prices = {}
    for location_name, location in LOCATIONS.items():
        for algo_name, algo in ALGOS.items():
            # Get all orders in this location and algo
            getOrders_args = {
                "id": API_ID,
                "key": API_KEY,
                "location": location,
                "algo": algo,
                }
            try:
                result = __callNicehashApi("orders.get", getOrders_args)
                # Get minimum price, throw out the lowest value
                prices = [o["price"] for o in result["orders"] if int(o["workers"]) > 2 and float(o["accepted_speed"]) > 0.00000005 and int(o["type"]) == 0]
                prices = sorted(prices)
                target_price = float(prices[0])
                if location not in target_prices:
                    target_prices[location] = {}
                target_prices[location][algo] = round(target_price+TARGET_MIN_ADD, 4)
            except Exception as e:
                print("Error: {}".format(str(e)))
                print(traceback.print_exc())
    
    # Update each order
    for order_id, order in orders.items():
        location = order["location"]
        algo = order["algo"]
        # Decrease or Increase Order price
        order["target_price"] = target_prices[location][algo]
        order["delta"] = order["price"] - order["target_price"]
        if order["price"] > order["target_price"]:
            # Decrease Order Price
            decreasePrice_args = {
                "id": API_ID,
                "key": API_KEY,
                "location": location,
                "algo": algo,
                "order": order_id,
                }
            try:
                result = __callNicehashApi("orders.set.price.decrease", decreasePrice_args)
                orders[order_id]["last_decreased"] = datetime.now()
                orders[order_id]["change"] = "-{}".format(0.0001)
            except Exception as e:
                orders[order_id]["change"] = "None: error: {}".format(str(e))
        elif order["price"] < order["target_price"]:
            # Increase Order price
            increase_to = min(order["price"]+MAX_INCREASE, order["target_price"])
            increasePrice_args = {
                "id": API_ID,
                "key": API_KEY,
                "location": location,
                "algo": algo,
                "order": order_id,
                "price": increase_to,
                }
            try:
                result = __callNicehashApi("orders.set.price", increasePrice_args)
                orders[order_id]["change"] = increase_to - order["price"]
            except Exception as e:
                orders[order_id]["change"] = "None: error: {}".format(str(e))
        else:
            orders[order_id]["change"] = "None needed"


    ## Print Report
        
    print("##  Completed control loop: {} - {}".format(PRICE_ADJUST_RATE, datetime.now()))
    print("##")
    print("#           |       |                  |  Current  |  Target  |          |  Price          ")
    print("#     Id    |  Loc  |    Algorithm     |  Price    |  Price   |  Delta   |  Change         ")
    print("  ----------|-------|------------------|-----------|----------|----------|-----------------------")
    for order_id, order in orders.items():
        print("  {} {} {} {} {} {}   {}".format(
                str(order["id"]).center(10),
                __getLocationName(order["location"]).center(7),
                __getAlgoName(order["algo"]).center(18),
                str(round(order["price"], 4)).center(11),
                str(round(order["target_price"], 4)).center(10),
                str(round(order["delta"], 4)).center(10),
                order["change"],
            ))
