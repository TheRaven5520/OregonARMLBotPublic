import sys
sys.path.append('..')
from discordHelper import *

# keeps track of certain data for each user

class user_data:

    def __init__(self):

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
    
    def df_to_data(self, df, helper):
        for index, row in df.iterrows():
            print([index, row])
        
        # deepcopy data into olddata
        # self.olddata = self.data.copy()
        # self.data = {key:val for key, val in self.data.items() if val != "-"}
        # self.store_data()
        return True 

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


ud = user_data()