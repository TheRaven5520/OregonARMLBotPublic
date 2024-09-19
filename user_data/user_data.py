import sys
sys.path.append('..')
from discordHelper import *

import gspread
from gspread_dataframe import get_as_dataframe
from oauth2client.service_account import ServiceAccountCredentials


# keeps track of certain data for each user

SHEET_NAME = "User Data"
WORKSHEET_NAME = "User Data"

class user_data:

    def __init__(self, helper):

        self.client = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_name(f"{DATA_DIR}gsdata/google_sheets_key.json", ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']))

        self.SHEET = self.client.open(SHEET_NAME)
        self.helper = helper

        self.keys = []
        self.data = {}
        self.load_data()

    # load & store
    def load_data(self):
        with open(f'{DATA_DIR}user_data/data.json') as file:
            self.data = json.load(file)
            self.keys, self.data = self.data['keys'], self.data['data']

    def store_data(self):
        with open(f'{DATA_DIR}user_data/data.json', 'w') as file:
            json.dump({'keys': self.keys, 'data': self.data}, file, indent=4)
    
    # accessors 
    def data_as_df(self):
        return pd.DataFrame(self.data).fillna("-").astype(str).T

    # mutators
    def create_user(self, user_id):
        if user_id in self.data:
            return False
        user_id = str(user_id)
        self.data[user_id] = {}
        return True

    def set_user_data(self, user_id, key, value):
        user_id = str(user_id)
        if user_id not in self.data:
            self.create_user(user_id)
        if key in self.keys:
            self.data[user_id][key] = value
            self.store_data()
            return True
        else:
            return False

    def add_key(self, key):
        if key not in self.keys:
            self.keys.append(key)
            self.store_data()
            return True
        else:
            return False
    
    def remove_key(self, key):
        if key in self.keys:
            self.keys.remove(key)
            self.store_data()
            return True
        else:
            return False
        
    def post_df(self, df):
        try:
            ws = self.SHEET.worksheet(WORKSHEET_NAME)
        except:
            ws = None

        if ws is None:
            return False 
        
        ws.resize(cols=len(df.columns), rows=len(df.index) + 1)
        ws.update(values=[df.columns.values.tolist()] + df.values.tolist(), range_name=None, value_input_option='USER_ENTERED')

    def get_df(self):
        get_as_dataframe(self.SHEET.worksheet(WORKSHEET_NAME), evaluate_formulas=False, parse_dates=False).fillna("").astype(str)
