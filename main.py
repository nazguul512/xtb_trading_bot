from tradingview_ta import *
import urllib.parse
import pandas
#from yahoo_fin import stock_info
from termcolor import colored
import time
import telegram_send
import os.path
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import yfinance as yf

# revolut googleSheetId = '1bCOpwbWV49_XIrmJMjDHqiLNldqgttNxzvvgpNT79oI'
googleSheetId = '1sGiHOiauEBmPthBjZ08hG1FEUEshsS30LOMVvK-iiog'
#revolut worksheetName = 'Revolut stocks list'
worksheetName = 'Table 1'
sheet_range = 'A4:A1733'

sheetURL = 'https://docs.google.com/spreadsheets/d/{0}/gviz/tq?tqx=out:csv&sheet={1}&range={2}'.format(
	googleSheetId,
	urllib.parse.quote_plus(worksheetName),
	sheet_range
)

ticker_list = pandas.read_csv(sheetURL, header=None)
#df = pandas.read_csv(sheetURL, usecols=['Symbol', 'Market'])
tickers = ticker_list.to_string(header=False, index=False).split()
trading_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
first_time_run = 0
current_sell_list = []
current_buy_list = []
previous_sell_list = []
previous_buy_list = []
diff_sell_list = []
diff_buy_list = []
one_day_tickers="AAN AAP ABMD ABX ACN ADC AEE AFG AIZ AMG APT ARW ASH ASM ATNX ATO AUUD AX AYI BNFT CABO CLVSQ COO DAVA DLX DS EPC GSKY LRFC ONEM RCII SHLD SJI SPAQ SRNE STOR SWIR TCDA TTM TWTR WEBR"

#vars for portfolio spreadsheet connect and works
scopes = [
'https://www.googleapis.com/auth/spreadsheets',
'https://www.googleapis.com/auth/drive'
]
credentials = ServiceAccountCredentials.from_json_keyfile_name("pybotnasq_tok.json", scopes)

def trim_me(value_to_trim):
	if not isinstance(value_to_trim, str):
		value_to_trim = str(value_to_trim)

	value_index = value_to_trim.find(".") + 3
	strip_value = value_to_trim[:value_index]
	return float(strip_value)

while True:
	day_of_trade = time.strftime("%A")
	time_of_trade = time.strftime("%H%M%S")
	time_of_trade = int(time_of_trade)
	message_for_telegram = time.strftime("%d.%m.%Y %H:%M:%S\n")

	if time_of_trade >= 163001 and time_of_trade <= 164001:
		first_time_run = 1

	if day_of_trade in trading_days and time_of_trade >= 163001 and time_of_trade <= 230000:

		try:
			portfoliosheet = gspread.authorize(credentials)
			sheet = portfoliosheet.open('portfolio').worksheet('portfolio')
		except gspread.exceptions.APIError as e:
			print("could not establish connection this time")
			sheet_fail = 1

		my_portfolio_file = open("portofoliu.txt", "r")
		content_portofoliu = my_portfolio_file.read()
		portofoliu = content_portofoliu.split(" ")
		my_portfolio_file.close()

		my_wishlist_file = open("wishlist.txt", "r")
		content_wishlist = my_wishlist_file.read()
		wishlist = content_wishlist.split(" ")
		my_wishlist_file.close()

		for ticker in tickers:
			count = 0
			sheet_fail = 0
			current_price = 0

			ticker = ticker.split(".")
			if "US" in ticker[1]:
				ticker = ticker[0]
				try:
					stock_data = TA_Handler(
						symbol=ticker,
						exchange="NYSE",
						screener="america",
						interval=Interval.INTERVAL_1_DAY
					)
					tickerRSI = stock_data.get_analysis().indicators["RSI"]
					tickerBBU = stock_data.get_analysis().indicators["BB.upper"]
					tickerBBL = stock_data.get_analysis().indicators["BB.lower"]
				except Exception:
					try:
						stock_data = TA_Handler(
							symbol=ticker,
							exchange="NASDAQ",
							screener="america",
							interval=Interval.INTERVAL_1_DAY
						)
						tickerRSI = stock_data.get_analysis().indicators["RSI"]
						tickerBBU = stock_data.get_analysis().indicators["BB.upper"]
						tickerBBL = stock_data.get_analysis().indicators["BB.lower"]
					except Exception:
						print(colored("Couldn't get stock data for {}", "yellow").format(ticker))

				try:
					ticker_data = yf.Ticker(ticker)

					if ticker in one_day_tickers:
						current_price = trim_me(float(ticker_data.history(period="1d").Close.iloc[0]))
					else:
						current_price = trim_me(float(ticker_data.history(period="1m").Close.iloc[0]))
					#trailingPE = trim_me(ticker_data.info['trailingPE'])
					print("{0} at price {1}".format(ticker, current_price))
				except:
					print(colored("Couldn't get price data for {}", "yellow").format(ticker))
					sheet_fail = 1

				try:
					if tickerRSI >= 70 and current_price >= tickerBBU:
						if ticker in portofoliu:
							print(colored("Signal to sell {0} for {1}", "red", attrs=["bold", "underline"]).format(ticker, current_price))
							message_time = time.strftime("%d.%m.%Y %H:%M:%S\n")
							alert_message = "<b>!!! " + message_time + "You have this " + ticker + "\nMaybe SELL at: " + str(trim_me(current_price)) + "</b>"
							telegram_send.send(messages=[alert_message], parse_mode="html")
						else:
							print(colored("Signal to sell {0} for {1}", "red").format(ticker, current_price))
						current_sell_list.append(ticker)
					if tickerRSI <= 30 and current_price <= tickerBBL:
						if ticker in portofoliu:
							print(colored("Signal to buy {0} for {1}", "green", attrs=["bold", "underline"]).format(ticker, current_price))
							message_time = time.strftime("%d.%m.%Y %H:%M:%S\n")
							alert_message = "<b>!!! " + message_time + "You have this " + ticker + "\nBUY More at: " + str(trim_me(current_price)) + "</b>"
							telegram_send.send(messages=[alert_message], parse_mode="html")
						elif ticker in wishlist:
							print(colored("Signal to buy {0} for {1}", "blue", attrs=["bold", "underline"]).format(ticker, current_price))
							message_time = time.strftime("%d.%m.%Y %H:%M:%S\n")
							alert_message = "<b>!!! " + message_time + "You want this " + ticker + "\nBUY Now at: " + str(trim_me(current_price)) + "</b>"
							telegram_send.send(messages=[alert_message], parse_mode="html")
						else:
							print(colored("Signal to buy {0} for {1}", "green").format(ticker, current_price))
						current_buy_list.append(ticker)
				except:
					print(colored("Couldn't calculate data for {}", "cyan").format(ticker))

			if sheet_fail == 0:
				#Getting through gsheets list and update value with current price
				try:
					colvals = sheet.col_values(2)
					if ticker in colvals:
						for val in colvals:
							count+=1
							if val == ticker:
								price_cell="F"+str(count)
								print("{0} found at cell {1}".format(val, price_cell))
								current_price=trim_me(current_price)
								print("{0} has price {1}".format(val, current_price))
								sheet.update_acell(price_cell, current_price)
								print("price updated in sheet")
								sector_cell="C"+str(count)
								try:
									sector_data=ticker_data.info['industry']
									sheet.update_acell(sector_cell, sector_data)
								except:
									print ("could not update industry sector in gsheet for this ticker")
				except:
					print("could not update data in gsheet. Maybe at next run")

		if first_time_run == 1:
			if not current_sell_list:
				message_for_telegram = message_for_telegram + "Nothing to sell now\n"
			else:
				for ticker_to_sell in current_sell_list:
					message_for_telegram = message_for_telegram + "Sell signal for: " + ticker_to_sell + "\n"

			if not current_buy_list:
				message_for_telegram = message_for_telegram + "Nothing to buy now\n"
			else:
				for ticker_to_buy in current_buy_list:
					message_for_telegram = message_for_telegram + "Buy signal for: " + ticker_to_buy + "\n"

			telegram_send.send(messages=[message_for_telegram], parse_mode="html")
			first_time_run = 0
			previous_sell_list = current_sell_list.copy()
			previous_buy_list = current_buy_list.copy()
			current_sell_list.clear()
			current_buy_list.clear()
		else:
			diff_sell_list = [x for x in current_sell_list if x not in previous_sell_list]
			diff_buy_list = [x for x in current_buy_list if x not in previous_buy_list]

			if diff_sell_list or diff_buy_list:
				message_for_telegram = "<b><u>Update at " + message_for_telegram + "</u></b>\n"
			else:
				continue

			if diff_sell_list:
				for ticker_to_sell in diff_sell_list:
					if ticker_to_sell in portofoliu:
						message_for_telegram = message_for_telegram + "<b><u>Sell signal for: " + ticker_to_sell + "</u></b>\n"
					elif ticker_to_sell in wishlist:
						message_for_telegram = message_for_telegram + "<b><i>Sell signal for: " + ticker_to_sell + "</i></b>\n"
					else:
						message_for_telegram = message_for_telegram + "Sell signal for: " + ticker_to_sell + "\n"

			if diff_buy_list:
				for ticker_to_buy in diff_buy_list:
					if ticker_to_buy in portofoliu:
						message_for_telegram = message_for_telegram + "<b><u>Buy signal for: " + ticker_to_buy + "</u></b>\n"
					elif ticker_to_buy in wishlist:
						message_for_telegram = message_for_telegram + "<b><i>Buy signal for: " + ticker_to_buy + "</i></b>\n"
					else:
						message_for_telegram = message_for_telegram + "Buy signal for: " + ticker_to_buy + "\n"

			telegram_send.send(messages=[message_for_telegram], parse_mode="html")
			previous_sell_list.clear()
			previous_buy_list.clear()
			previous_sell_list = current_sell_list.copy()
			previous_buy_list = current_buy_list.copy()
			current_sell_list.clear()
			current_buy_list.clear()

	if time_of_trade > 230000:
		time.sleep(61200)