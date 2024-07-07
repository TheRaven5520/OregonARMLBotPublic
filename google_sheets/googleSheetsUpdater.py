import gspread
from gspread_dataframe import get_as_dataframe
from oauth2client.service_account import ServiceAccountCredentials

import sys
sys.path.append('..')
from discordHelper import *

import warnings
warnings.filterwarnings("ignore")

# set all maxes for df display to None 
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
pd.set_option('display.max_colwidth', None)

SHEET_NAME = "[Current] 2025 ARML Registration (Responses)"
rootDir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/"

def cs(n):
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string

class google_sheet_updater:
    def __init__(self, helper):
        self.client = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_name(f"{DATA_DIR}gsdata/google_sheets_key.json", ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']))

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
        return ws, None if not os.path.exists(f"{DATA_DIR}gsdata/{sheet_name}.csv") else pd.read_csv(f"{DATA_DIR}gsdata/{sheet_name}.csv", dtype=str).fillna("").reset_index(drop=True)

    def get_df_fromsheet(self, sheet_name):
        return get_as_dataframe(self.SHEET.worksheet(sheet_name), evaluate_formulas=False, parse_dates=False).fillna("").astype(str)

    def del_ws(self, sheet_name):
        ws, df = self.get_ws(sheet_name)
        if ws is not None: self.SHEET.del_worksheet(ws)
        if not (df is None): os.remove(f"{DATA_DIR}gsdata/{sheet_name}.csv")
        return ws is not None or not (df is None)

    def change_ws_name(self, old_name, new_name):
        ws, df = self.get_ws(old_name)
        if ws is not None: ws.update_title(new_name)
        if not (df is None): os.rename(f"{DATA_DIR}gsdata/{old_name}.csv", f"{DATA_DIR}gsdata/{new_name}.csv")
        return ws is not None or not (df is None)

    def store_df_to_csv(self, sheet_name, df):
        df.astype(str).fillna("").reset_index(drop=True).to_csv(f"{DATA_DIR}gsdata/{sheet_name}.csv", index=False)

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
        new_df = self.get_df_fromsheet(sheet_name)

        # change display names to user IDs where possible
        users = {user.display_name: str(user.id) for user in self.helper.guild().members}
        new_df["Name"] = [users.get(name, name) for name in new_df["Name"]]

        # merge new_df with df, keeping union of keeps but prioritizing new_df
        df = df.reindex(columns=new_df.columns, fill_value="")
        df = pd.merge(df, new_df, how="outer").drop_duplicates(subset='Name', keep='last', ignore_index=True)

        self.store_df_to_csv(sheet_name, df)
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
        df = df.reset_index(drop=True)


        df_names = df[df["Name"].isin(self.data["names"])].fillna("").reset_index(drop=True)

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
        self.store_df_to_csv(sheet_name, df)

    def update_people(self, names):
        self.data["names"] = names
        self.store_data()

        for file in os.listdir(f'{DATA_DIR}gsdata/'):
            filename, extension = os.path.splitext(file)
            if extension == '.csv':
                self.update_display(filename)

    def post_df_to_sheet(self, df, sheet_name):
        ws, _ = self.get_ws(sheet_name)
        if ws is None: ws = self.SHEET.add_worksheet(sheet_name, 1, 1)

        ws.resize(cols=len(df.columns), rows=len(df.index) + 1)

        ws.update(values=[df.columns.values.tolist()] + df.values.tolist(), range_name=None, value_input_option='USER_ENTERED')

    ############################################################################
    # ADD COLUMNS TO SHEET

    def add_column(self, sheet_name, column_name, upd_display = True):
        ws, df = self.get_ws(sheet_name)
        if df is None: return None
        if column_name in df.columns: return None
        df.insert(len(df.columns), column_name, "")

        self.store_df_to_csv(sheet_name, df)
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

        self.store_df_to_csv(sheet_name, df)

        self.update_display(sheet_name)

    ############################################################################
    # CREATE SPECIALIZED SHEETS

    def create_test_sheet(self, test_name, num_questions):
        # create sheet with test_name
        self.client.open(SHEET_NAME).add_worksheet(test_name, len(self.data["names"]) + 1, num_questions + 1 + 4)  # Add 1 to account for the "Adjustments" column

        # entire DF type is str
        cols = ["Name", "Adj."] + [f"P{i + 1}" for i in range(num_questions)] + ["TOTAL SCORE", "RANKINGS", "SCORES"] 
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