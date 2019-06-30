#!/usr/bin/env python

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
import toml
import nicehash
import mwgrinpool


def __updateNicehashOrders():
    nicehash.updateOrders()

def __withdrawFromPool():
    payout = mwgrinpool.Pool_Payout()
    payout.username = MWGRINPOOL_USER
    payout.password = MWGRINPOOL_PASS
    payout.wallet_pass = WALLET_PASSWORD
    payout.run_local_wallet()


if __name__ == "__main__":
    ## Load user config
    config = toml.load("config.toml")
    LOOP_DELAY_MINUTES = 60 * config['hashmanager']['LOOP_DELAY_MINUTES']
    MWGRINPOOL_USER = config['mwgrinpool']['USERNAME']
    MWGRINPOOL_PASS = config['mwgrinpool']['PASSWORD']
    WALLET_PASSWORD = config['wallet']['PASSWORD']

    ## Print banner
    print("################################################################################")
    print("##                                Hash Manager                                ##")
    print("################################################################################")


    while(1):
        ## Open new Nicehash orders
        # Any BTC funds sitting in Nicehash should be committed to hash orders.

        ## Update existing Nicehash orders
        # Existing orders should be updated to track lowest possible price
        try:
            print("Updating existing Nicehash orders...")
            __updateNicehashOrders()
        except Exception as e:
            print("Error: {}".format(str(e)))

        ## Withdraw from mining pool
        try:
            __withdrawFromPool()
        except Exception as e:
            print("Error: {}".format(str(e)))

        ## Deposit GRIN to exchange

        ## Exchange funds for BTC

        ## Withdraw BTC to Nicehash

        ## Sleep
        time.sleep(LOOP_DELAY_MINUTES)
