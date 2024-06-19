from tradingview_ta import *
from termcolor import colored
import time
import telegram_send
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import yfinance as yf
from API import XTB
import datetime
import multiprocessing
import functools
import configparser

# Getting credentials from config.ini file
config = configparser.ConfigParser()
config.read('config.ini')
user = config.get('XTB', 'XTB_user')
password = config.get('XTB', 'XTB_pass')

excluded_dates_list = [
	datetime.date(2024, 1, 1),
	datetime.date(2024, 1,15),
	datetime.date(2024, 2,19),
	datetime.date(2024, 3,29),
	datetime.date(2024, 5,27),
	datetime.date(2024, 6,19),
	datetime.date(2024, 7, 4),
	datetime.date(2024, 9, 2),
	datetime.date(2024,11,28),
	datetime.date(2024,12,25)
]

first_time_run = 0
previous_sell_list = []
previous_buy_list = []
diff_sell_list = []
diff_buy_list = []
existing_tickers = []
sheet = None
ticker_list = None

# Define Manager objects to create shared lists
manager = multiprocessing.Manager()
current_sell_list = manager.list()
current_buy_list = manager.list()

#vars for portfolio spreadsheet connect and works
scopes = [
'https://www.googleapis.com/auth/spreadsheets',
'https://www.googleapis.com/auth/drive'
]
credentials = ServiceAccountCredentials.from_json_keyfile_name("pybotnasq_tok.json", scopes)

def get_tickers():
	API = XTB(user, password)
	ticker_list = API.get_AllSymbols()
	ticker_list = [tickerdicts["symbol"].split(".")[0] for tickerdicts in ticker_list["returnData"] if "symbol" in tickerdicts and ".US" in tickerdicts["symbol"] and "CLOSE ONLY" not in tickerdicts["description"] and "(Cboe BZX Real-Time Quote)" in tickerdicts["description"]]
	ticker_list = sorted(ticker_list)
	API.logout()
	print("XTB login and logout")
	return ticker_list

def trim_me(value_to_trim):
	if not isinstance(value_to_trim, str):
		value_to_trim = str(value_to_trim)

	value_index = value_to_trim.find(".") + 3
	strip_value = value_to_trim[:value_index]
	return float(strip_value)

def get_stock_data(ticker):
	global first_time_run
	dividend_data = None
	try:
		stock_data = yf.Ticker(ticker)
		if first_time_run == 1:
			dividend_data = stock_data.actions.Dividends
		history_data = stock_data.history(period="1m")
		if not history_data.empty and dividend_data is not None and not dividend_data.empty:
			return trim_me(float(history_data.Close.iloc[0])), float(dividend_data.iloc[-1])
		elif not history_data.empty and (dividend_data is None or dividend_data.empty):
			return trim_me(float(history_data.Close.iloc[0])), None
		else:
			print(f"No data available for {ticker}")
			return None, None
	except Exception as e:
		print(colored(f"Failed to get data for {ticker}: {e}", "red"))
		return None, None

def authorize_spreadsheet():
	try:
		portfoliosheet = gspread.auth.authorize(credentials)
		sheet = portfoliosheet.open('portfolio').worksheet('portfolio')
		# Get the list of tickers already present in the spreadsheet
		existing_tickers = sheet.col_values(2)[2:]  # Skip header row
		return sheet, existing_tickers
	except Exception as e:
		print(colored(f"Failed to establish connection to Google Sheets: {e}", "red"))
		return None, None

def update_spreadsheet(sheet, ticker, current_price, dividend_price):
	global first_time_run
	sheet, existing_tickers = authorize_spreadsheet()
	if sheet is not None:
		try:
			colvals = sheet.col_values(2)
			if ticker in colvals:
				count = colvals.index(ticker) + 1
				price_cell = f"F{count}"
				sheet.update_acell(price_cell, current_price)
				print(f"Price {current_price} updated for {ticker} in spreadsheet")
				if first_time_run == 1 or dividend_price is not None:
					div_cell = f"G{count}"
					sheet.update_acell(div_cell, dividend_price)
					print(f"Dividend {dividend_price} updated for {ticker} in spreadsheet")
		except Exception as e:
			print(colored(f"Failed to update price in spreadsheet for {ticker}: {e}", "red"))

def generate_telegram_message(ticker, signal_type, portfolio_type):
	if portfolio_type == "portfolio":
		signal_type_color = "green" if signal_type == "buy" else "yellow"
	elif portfolio_type == "wishlist":
		signal_type_color = "blue"
	else:
		signal_type_color = "white"
	return colored(f"{signal_type.upper()} signal for {ticker} ({portfolio_type})", signal_type_color)

def return_portfolio_tickers():
	portfolio = config.get('finance', 'portfolio')
	portfolio = portfolio.split(" ")
	return portfolio

def return_wishlist_tickers():
	wishlist = config.get('finance', 'wishlist')
	wishlist = wishlist.split(" ")
	return wishlist

def process_ticker(ticker, existing_tickers, portfolio, wishlist, sheet, current_sell_list, current_buy_list):
	current_price, dividend_price = get_stock_data(ticker)

	if current_price is not None:
		try:
			try:
				stock_data = TA_Handler(
					symbol=ticker,
					exchange="NYSE",
					screener="america",
					interval=Interval.INTERVAL_1_DAY
				)
				tickerRSI = trim_me(float(stock_data.get_analysis().indicators["RSI"]))
				tickerBBU = trim_me(float(stock_data.get_analysis().indicators["BB.upper"]))
				tickerBBL = trim_me(float(stock_data.get_analysis().indicators["BB.lower"]))
			except Exception:
				try:
					stock_data = TA_Handler(
						symbol=ticker,
						exchange="NASDAQ",
						screener="america",
						interval=Interval.INTERVAL_1_DAY
					)
					tickerRSI = trim_me(float(stock_data.get_analysis().indicators["RSI"]))
					tickerBBU = trim_me(float(stock_data.get_analysis().indicators["BB.upper"]))
					tickerBBL = trim_me(float(stock_data.get_analysis().indicators["BB.lower"]))
				except Exception as e:
					print(colored("Couldn't get stock data for {0}: {1}", "yellow").format(ticker, e))
					tickerRSI = None
					tickerBBL = None
					tickerBBU = None

			if tickerRSI is not None and tickerBBL is not None and tickerBBU is not None:
				if tickerRSI >= 70 and current_price >= tickerBBU:
					if ticker in portfolio:
						message = generate_telegram_message(ticker, "sell", "portfolio")
						message = message[5:][:-4]
						telegram_send.send(messages=[message], parse_mode="html")
						current_sell_list.append(ticker)
					else:
						current_sell_list.append(ticker)
				if tickerRSI <= 30 and current_price <= tickerBBL:
					if ticker in portfolio:
						message = generate_telegram_message(ticker, "buy", "portfolio")
						message = message[5:][:-4]
						telegram_send.send(messages=[message], parse_mode="html")
						current_buy_list.append(ticker)
					elif ticker in wishlist:
						message = generate_telegram_message(ticker, "buy", "wishlist")
						message = message[5:][:-4]
						telegram_send.send(messages=[message], parse_mode="html")
						current_buy_list.append(ticker)
					else:
						current_buy_list.append(ticker)

				if ticker in existing_tickers:
					update_spreadsheet(sheet, ticker, current_price, dividend_price)

		except Exception as e:
			print(colored("Error processing ticker {0}: {1}".format(ticker, e), "yellow"))

def function_to_run():
	global first_time_run, previous_sell_list, previous_buy_list, ticker_list, current_sell_list, current_buy_list

	day_of_trade = time.strftime("%A")
	time_of_trade = int(time.strftime("%H%M%S"))

	start_time = time.time()

	if 163000 <= time_of_trade <= 163500:
		first_time_run = 1
	else:
		first_time_run = 0

	current_date = datetime.datetime.now().date()

	if time_of_trade < 163000:
		print(f"Market is not open yet, sleep until 16:30")
		target_time = datetime.time(16, 30, 1)
		time_slept = sleep_until_target_time(target_time)
		print(f"Slept for {time_slept} seconds until {target_time}")
	elif time_of_trade > 230000:
		print(f"Market just closed, sleep until midnight")
		target_time = datetime.time(0, 0, 1)
		time_slept = sleep_until_target_time(target_time)
		print(f"Slept for {time_slept} seconds until {target_time}")
	elif 163000 <= time_of_trade <= 230000:
		sheet, existing_tickers = authorize_spreadsheet()
		portfolio = return_portfolio_tickers()
		wishlist = return_wishlist_tickers()
		if first_time_run == 1 or ticker_list is None:
			ticker_list = get_tickers()

		#Use functools.partial to create a partial function with existing_tickers argument
		partial_process_ticker = functools.partial(
			process_ticker,
			existing_tickers=existing_tickers,
			portfolio=portfolio,
			wishlist=wishlist,
			sheet=sheet,
			current_sell_list=current_sell_list,
			current_buy_list=current_buy_list
		)

		#Use multiprocessing to process each ticker concurrently
		with multiprocessing.Pool() as pool:
			pool.map(partial_process_ticker, ticker_list)

		if first_time_run == 1:
			current_sell_list = list(set(current_sell_list))
			current_buy_list = list(set(current_buy_list))
			# Send initial Telegram message
			send_initial_telegram_message()
		else:
			# Check for updates and send Telegram messages
			send_telegram_updates()

			# Update previous lists
			previous_sell_list = list(set(current_sell_list))
			previous_buy_list = list(set(current_buy_list))
			current_sell_list[:] = []
			current_buy_list[:] = []

	end_time = time.time()
	elapsed_time = end_time - start_time
	print(elapsed_time)

def sleep_until_target_time(target_time):
	current_datetime = datetime.datetime.now()
	current_time = current_datetime.time()
	# Get today's date
	today_date = current_datetime.date()
	# Combine today's date with the target time
	target_datetime = datetime.datetime.combine(today_date, target_time)
	# Check if the target time is in the past
	if target_datetime < current_datetime:
		# If so, add one day to the date
		target_datetime += datetime.timedelta(days=1)

	# Calculate  the time until the target time
	time_until_target = target_datetime - current_datetime
	time_until_target_seconds = time_until_target.total_seconds()
	# Sleep until the target time
	time.sleep(time_until_target_seconds)
	# Return the time slept
	return time_until_target_seconds

def send_initial_telegram_message():
	global current_sell_list, current_buy_list
	message_for_telegram = ""
	if not current_sell_list:
		message_for_telegram += "Nothing to sell now\n"
	else:
		message_for_telegram += "Sell signals:\n"
		for ticker in current_sell_list:
			message_for_telegram += f"Sell signal for {ticker}\n"

	if not current_buy_list:
		message_for_telegram += "Nothing to buy now\n"
	else:
		message_for_telegram += "Buy signals:\n"
		for ticker in current_buy_list:
			message_for_telegram += f"Buy signal for: {ticker}\n"
	print(f"message for telegram to be sent: {message_for_telegram}")

	telegram_send.send(messages=[message_for_telegram], parse_mode="html")

def send_telegram_updates():
	portfolio = return_portfolio_tickers()
	wishlist = return_wishlist_tickers()
	global current_sell_list, current_buy_list, previous_sell_list, previous_buy_list
	message_for_telegram = ""

	# Calculate the differences between the processed tickers
	diff_sell_list = sorted(list(set(current_sell_list) - set(previous_sell_list)))
	diff_buy_list = sorted(list(set(current_buy_list) - set(previous_buy_list)))

	if diff_sell_list:
		message_for_telegram += "Sell signals:\n"
		for ticker in diff_sell_list:
			if ticker in portfolio:
				message_for_telegram += f"Sell signal for: {ticker} (portfolio)\n"
			elif ticker in wishlist:
				message_for_telegram += f"Sell signal for: {ticker} (wishlist)\n"
			else:
				message_for_telegram += f"Sell signal for: {ticker}\n"

	if diff_buy_list:
		message_for_telegram += "Buy signals:\n"
		for ticker in diff_buy_list:
			if ticker in portfolio:
				message_for_telegram += f"Buy signal for: {ticker} (portfolio)\n"
			elif ticker in wishlist:
				message_for_telegram += f"Buy signal for: {ticker} (wishlist)\n"
			else:
				message_for_telegram += f"Buy signal for: {ticker}\n"

	print(f"message for telegram to be sent: {message_for_telegram}")
	if message_for_telegram:
		telegram_send.send(messages=[message_for_telegram], parse_mode="html")

def run_function_except_on_dates(excluded_dates):
	while True:
		current_date = datetime.datetime.now().date()
		# Check if the current date is in the excluded_dates list
		if current_date not in excluded_dates and current_date.weekday() not in (5, 6):
			function_to_run()
		else:
			print("Market is closed because of bank holyday or weekend. Sleep until next day")
			target_time = datetime.time(0, 0, 1)
			time_slept = sleep_until_target_time(target_time)
			print(f"Slept for {time_slept} seconds until {target_time}")

run_function_except_on_dates(excluded_dates_list)
