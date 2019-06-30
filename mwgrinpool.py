#!/usr/bin/python3
  
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
import json
import getpass
import requests
import datetime
import argparse
import subprocess
import toml


class Pool_Payout:
    def __init__(self):
        self.poolname = "MWGrinPool"
        self.mwURL = "https://api.mwgrinpool.com"
        self.POOL_MINIMUM_PAYOUT = 0.1
        self.tmpfile = "payment_slate.json"
        self.dont_clean = False
        self.prompted = False
        self.username = None
        self.password = None
        self.wallet_pass = None
        self.user_id = None
        self.wallet_cmd = None
        self.balance = 0.0
        self.unsigned_slate = None
        self.signed_slate = None

    # Print progress message
    def print_progress(self, message):
        sys.stdout.write("   ... {}:  ".format(message))
        sys.stdout.flush()

    # Print success message
    def print_success(self, message=None):
        if message is None:
            sys.stdout.write("Ok\n")
        else:
            message = str(message)
            sys.stdout.write(message)
            if not message.endswith("\n"):
                sys.stdout.write("\n")
        sys.stdout.flush()
      
    # Print an error message, footer, and exit
    def error_exit(self, message):
        print(" ")
        print(" ")
        print("   *** Error: {}".format(message))
        sys.exit(1)
        
    # Delete any existing slate and slate response
    def clean_slate_files(self):
        if self.dont_clean == False:
            return
        unsigned_slate_filename = self.tmpfile
        signed_slate_filename = self.tmpfile+".response"
        for slatefile in [unsigned_slate_filename, signed_slate_filename]:
            if os.path.exists(slatefile):
                os.remove(filename)

    # Find the wallets executable, from the path, cwd, and build directories
    def find_wallet(self):
        ##
        # Find Grin Wallet Command
        grin_wallet_cmd = None
        cwd = os.getcwd()
        path = os.environ.get('PATH')
        path_add = [
            path,
            cwd,
            cwd + "/grin",
            cwd + "/grin/target/debug",
            cwd + "/grin/target/release",
            cwd + "/grin-wallet",
            cwd + "/grin-wallet/target/debug",
            cwd + "/grin-wallet/target/release",
        ]
        path = ":".join(path_add)
        for directory in path.split(":"):
            if os.path.isfile(directory + "/grin-wallet"):
                grin_wallet_cmd = [directory + "/grin-wallet"]
            elif os.path.isfile(directory + "/grin-wallet.exe"):
                grin_wallet_cmd = [directory + "/grin-wallet.exe"]
        if grin_wallet_cmd is None:
            for directory in path.split(":"):
                if os.path.isfile(directory + "/grin"):
                    grin_wallet_cmd = [directory + "/grin", "wallet"]
                elif os.path.isfile(directory + "/grin.exe"):
                    grin_wallet_cmd = [directory + "/grin.exe", "wallet"]
        if grin_wallet_cmd is None:
            return("Could not find wallet executable, please add it to your PATH or copy it into this directory.")
    
        # Wallet Sanity Check
        wallettest_cmd = grin_wallet_cmd + [ "-p", self.wallet_pass, "info" ]
        message = None
        try:
            message = subprocess.check_output(wallettest_cmd, stderr=subprocess.STDOUT, shell=False)
            self.wallet_cmd = grin_wallet_cmd
            return(message)
        except subprocess.CalledProcessError as exc:
            return "Wallet test failed with output: {}".format(exc.output.decode("utf-8"))
        except Exception as e:
            return "Wallet test failed with error {}".format(str(e))

    # Get my pool user_id
    def get_user_id(self):
        get_user_id_url = self.mwURL + "/pool/users"
        r = requests.get(
                url = get_user_id_url,
                auth = (self.username, self.password),
        )
        message = None
        if r.status_code != 200:
            message = "Failed to get your account information from {}: {}".format(self.poolname, r.text)
            return message
        self.user_id = str(r.json()["id"])
        return None

    # Get the users balance
    def get_balance(self):
        get_user_balance = self.mwURL + "/worker/utxo/" + self.user_id
        r = requests.get(
                url = get_user_balance,
                auth = (self.username, self.password),
        )
        if r.status_code != 200:
            return "Failed to get your account balance: {}".format(r.text)
        if r.json() is None:
            balance_nanogrin = 0
        else:
            balance_nanogrin = r.json()["amount"]
        self.balance = balance_nanogrin / 1000000000.0
        if self.balance < 0:
            self.balance = 0.0

    def get_unsigned_slate(self):
        ##
        # Get the initial tx slate and write it to a file
        get_tx_slate_url = self.mwURL + "/pool/payment/get_tx_slate/" + self.user_id
        r = requests.post(
                url = get_tx_slate_url,
                auth = (self.username, self.password),
        )
        if r.status_code != 200:
            return "Failed to get a payment slate: {}".format(r.text)
        self.unsigned_slate = r.text

    # Write json slate to a file
    def write_unsigned_slate_file(self):
        try:
            f = open(self.tmpfile, "w")
            f.write(self.unsigned_slate) 
            f.flush()
            f.close()
            return None
        except Exception as e:
            return "Error saving payment slate to file: {}".format(str(e))
        
    def sign_slate_with_wallet_cli(self):
        ##
        # Call the wallet CLI to receive and sign the slate
        recv_cmd = self.wallet_cmd + [
                "-p", self.wallet_pass,
              "receive",
                "-i", self.tmpfile,
        ]
        try:
            output = subprocess.check_output(recv_cmd, stderr=subprocess.STDOUT, shell=False)
            with open(self.tmpfile + '.response', 'r') as tx_slate_response:
                self.signed_slate = tx_slate_response.read()
        except subprocess.CalledProcessError as exc:
            return "Signing slate failed with output: {}".format(exc.output.decode("utf-8"))
        except Exception as e:
            return "Wallet receive failed with error: {}".format(str(e))
        
    def return_payment_slate(self):
        ##
        # Submit the signed slate back to the pool to be finalized and posted to the network
        submit_tx_slate_url = self.mwURL + "/pool/payment/submit_tx_slate/" + self.user_id
        r = requests.post(
                url = submit_tx_slate_url,
                data = self.signed_slate,
                auth = (self.username, self.password),
        )
        if r.status_code != 200:
            return "Failed to submit signed slate - {}".format(r.text)



        
    def run_local_wallet(self):
        ##
        # Do payout 

        # Check for unsubmitted signed slate
        # xxx

        # Cleanup
        self.clean_slate_files()
    
        # Find wallet Command
        self.print_progress("Locating your grin wallet command");
        message = self.find_wallet()
        if self.wallet_cmd is None:
            self.error_exit(message)
        self.print_success()

	    # Find User ID
        self.print_progress("Getting your pool User ID");
        message = self.get_user_id()
        if self.user_id is None:
            self.error_exit(message)
        self.print_success()
    
        # Find balance
        self.print_progress("Getting your Avaiable Balance");
        message = self.get_balance()
        if self.balance == None:
            self.error_exit(message)
        self.print_success(self.balance)
        # Only continue if there are funds available
        if self.balance < self.POOL_MINIMUM_PAYOUT:
            self.error_exit("Insufficient Available Balance for payout: Minimum: {}, Available: {}".format(self.POOL_MINIMUM_PAYOUT, self.balance))

        # Get payment slate from Pool
        self.print_progress("Requesting a Payment from the pool");
        message = self.get_unsigned_slate()
        if self.unsigned_slate is None:
            self.error_exit(message)
        # Write the slate to file
        message = self.write_unsigned_slate_file()
        if not os.path.isfile(self.tmpfile):
            self.error_exit(message)
        self.print_success()

        # Call grin wallet to receive the slate and sign it
        self.print_progress("Processing the payment with your wallet")
        message = self.sign_slate_with_wallet_cli()
        if message is not None:
            self.error_exit(message)
        self.print_success()

        # Return the signed slate to the pool
        self.print_progress("Returning the signed payment slate to the pool");
        message = self.return_payment_slate()
        if message is not None:
            self.error_exit(message)
        self.print_success()

        # Cleanup
        self.clean_slate_files()




if __name__ == "__main__":
    # Disable "bracketed paste mode"
    try:
        os.system('printf "\e[?2004l"')
    except:
        pass

    payout = Pool_Payout()
    payout.run_local_wallet()
    sys.exit(0)
