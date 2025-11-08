from oauth2client.service_account import ServiceAccountCredentials
import gspread

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
gc = gspread.authorize(creds)


SHEET_ID = "1-4D2XlYCv4gOe_5LksHRv10O3wCszCoX2WCIqf4jlo8"
sh = gc.open_by_key(SHEET_ID)
ws = sh.worksheet("companies")
ws.append_row(["TestCo","test.com","","","","","","","","","","","","","Low","Hi","https://test.com","",""])
print("✅ Sheet write succeeded")
