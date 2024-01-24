import gspread
from gspread_dataframe import get_as_dataframe
from oauth2client.service_account import ServiceAccountCredentials
import json
import pandas as pd

import os 
import warnings
warnings.filterwarnings("ignore")

# set all maxes for df display to None 
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
pd.set_option('display.max_colwidth', None)

SHEET_NAME = "[Current] 2024 ARML Log (Responses)"
rootDir = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/") + "/"
DATA_DIR='/home/ec2-user/PrivateData/'

def cs(n):
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string

class google_sheet_updater:
    def __init__(self, helper):
        self.client = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_name(f'{rootDir}google_sheets_key.json',[ 'https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/drive.file' ]))

        self.SHEET = self.client.open(SHEET_NAME)
        self.helper = helper

        self.load_data()

    ############################################################################
    # HELPERS 

    def get_ws(self, sheet_name, ws = True):
        if ws:
            try:
                ws = self.SHEET.worksheet(sheet_name)
            except:
                ws = None
        else:
            ws = None
        return ws, None if not os.path.exists(f"{DATA_DIR}gsdata/{sheet_name}.csv") else pd.read_csv(f"{DATA_DIR}gsdata/{sheet_name}.csv", dtype=str).fillna("")

    def del_ws(self, sheet_name):
        ws, df = self.get_ws(sheet_name)
        if ws is not None: self.SHEET.del_worksheet(ws)
        if not (df is None): os.remove(f"{DATA_DIR}gsdata/{sheet_name}.csv")
        return ws is not None or not (df is None)

    def store_ws(self, sheet_name, df):
        df.astype(str).fillna("").to_csv(f"{DATA_DIR}gsdata/{sheet_name}.csv", index=False)

    ############################################################################
    # DATA STORAGE 

    def load_data(self):
        with open(f'{DATA_DIR}gsdata/data.json') as file:
            self.data = json.load(file)
    def store_data(self):
        with open(f'{DATA_DIR}gsdata/data.json', 'w') as file:
            json.dump(self.data, file, indent=4)
    
    ############################################################################
    # DISPLAY UPDATES

    def store_display(self, sheet_name):
        ws, df = self.get_ws(sheet_name)
        new_df = get_as_dataframe(ws, evaluate_formulas=False, parse_dates=False).fillna("")
        users = {user.display_name: user.id for user in self.helper.guild().members}
        for i in range(len(new_df["Name"])):
            if new_df.loc[i, "Name"] in users:
                new_df.loc[i, "Name"] = users[new_df.loc[i, "Name"]]
        self.store_ws(sheet_name, new_df)
        self.store_data()

    def store_all_displays(self):
        for file in os.listdir(f'{DATA_DIR}gsdata/'):
            filename, extension = os.path.splitext(file)
            if extension == '.csv':
                self.store_display(filename)

    def update_display(self, sheet_name):
        # OPEN/CREATE SHEET & CSV 
        ws, df = self.get_ws(sheet_name)
        if ws is None: ws = self.SHEET.add_worksheet(sheet_name, len(self.data["names"]) + 1, 2)
        if df is None: df = pd.DataFrame(columns=["Name"], dtype=str)

        # PROCESS NAMES
        for name in self.data["names"]:
            if name not in df["Name"].values:
                df = pd.concat([df, pd.DataFrame({"Name": [name]})], ignore_index=True)

        df_names = df[df["Name"].isin(self.data["names"])].fillna("")

        for i in range(len(df_names["Name"])):
            try:
                member = self.helper.get_member(int(df_names.loc[i, "Name"]))
                df_names.loc[i, "Name"] = member.display_name
            except:
                continue 

        df_names = df_names.sort_values(by=["Name"]).reset_index(drop=True)
        
        # UPDATE DISPLAY
        ws.resize(cols=len(df_names.columns), rows=len(df_names.index) + 1)
        ws.update(values=[df_names.columns.values.tolist()] + df_names.values.tolist(), range_name=None, value_input_option='USER_ENTERED')

        # STORE CSV
        self.store_ws(sheet_name, df)

    def update_people(self, names):
        self.data["names"] = names
        self.store_data()

        for file in os.listdir(f'{DATA_DIR}gsdata/'):
            filename, extension = os.path.splitext(file)
            if extension == '.csv':
                self.update_display(filename)

    ############################################################################
    # ADD COLUMNS TO SHEET

    def add_column(self, sheet_name, column_name, upd_display = True):
        ws, df = self.get_ws(sheet_name)
        if df is None: return None
        if column_name in df.columns: return None
        df.insert(len(df.columns), column_name, "")

        self.store_ws(sheet_name, df)
        if upd_display: self.update_display(sheet_name)

    def add_potd_season(self, driver, helper, sheet_name, season = "None", date = "None"):
        if date == "None":
            date = (pd.Timestamp.today() - pd.Timedelta(days=pd.Timestamp.today().dayofweek + 7)).strftime("%m/%d/%Y")
        if season == "None": season = str(driver.season.CURRENT_SEASON - 1)

        ws, df = self.get_ws(sheet_name)
        if df is None: return None

        self.add_column(sheet_name, f"{season}: {date}", False) 

        users = {user.display_name: str(user.id) for user in helper.guild().members}
        scores = driver.season.get_grades(season)
        for i in range(len(df["Name"])):
            score = scores[df.loc[i, "Name"]] if df.loc[i, "Name"] in scores else "0"
            df.loc[i, f"{season}: {date}"] = str(score)

        self.store_ws(sheet_name, df)

        self.update_display(sheet_name)

    ############################################################################
    # CREATE SPECIALIZED SHEETS

    def create_test_sheet(self, test_name, num_questions):
        # create sheet with test_name
        self.client.open(SHEET_NAME).add_worksheet(test_name, len(self.data["names"]) + 1, num_questions + 1 + 3)

        # entire DF type is str
        cols = ["Name"] + [f"P{i + 1}" for i in range(num_questions)] + ["TOTAL SCORE", "RANKINGS", "SCORES"]
        df = pd.DataFrame(columns=cols, dtype=str)
        df["Name"] = self.data["names"]
        df = df.fillna("")

        col = cs(2 + num_questions - 1)
        for i in range(len(self.data["names"])):
            df.loc[i, "TOTAL SCORE"] = f"=SUM(B{i + 2}:{col}{i + 2})"

        total_score_column = cs(2 + num_questions)
        df.loc[0, "RANKINGS"] = f"=SORT(A2:A, {total_score_column}2:{total_score_column}, FALSE)"
        df.loc[0, "SCORES"] = f"=SORT({total_score_column}2:{total_score_column}, {total_score_column}2:{total_score_column}, FALSE)"

        with open(f"{DATA_DIR}gsdata/{test_name}.csv", "w") as file:
            df.to_csv(file, index=False)

        # update sheet
        self.update_display(test_name)

################################################################################