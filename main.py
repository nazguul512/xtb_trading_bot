"""This module is a function based trading bot"""
import time
import datetime
import multiprocessing
import functools
import configparser
import os
from tradingview_ta import TA_Handler, Interval
from termcolor import colored
import telegram_send
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
from XTB_API.API import XTB # pylint: disable=import-error, no-name-in-module
#The line above will be changed once the lib will be pushed to pip

# Getting credentials from config.ini file
config = configparser.ConfigParser()
CONFIG_PATH = "config.ini"

excluded_dates_list = [
	datetime.date(2025, 1, 1),
	datetime.date(2025, 1,20),
	datetime.date(2025, 2,17),
	datetime.date(2025, 4,18),
	datetime.date(2025, 5,26),
	datetime.date(2025, 6,19),
	datetime.date(2025, 7, 4),
	datetime.date(2025, 9, 1),
	datetime.date(2025,11,27),
	datetime.date(2025,12,25)
]

# Define Manager objects to create shared lists
manager = multiprocessing.Manager()
current_sell_list = manager.list()
current_buy_list = manager.list()
no_data_ticker_list = manager.list()

def get_tickers():
	"""Function that gathers all tickers available from XTB on US market.

	Returns:
		list: A list of tickers provided by XTB broker.
	"""
	config.read('config.ini')
	user = config.get('XTB', 'XTB_user')
	password = config.get('XTB', 'XTB_pass')
	xtb_connect = XTB(user, password)
	ticker_list_local = xtb_connect.get_AllSymbols()
	ticker_list_local = [
		tickerdicts["symbol"].split(".")[0]
		for tickerdicts in ticker_list_local["returnData"]
		if "symbol" in tickerdicts
		and ".US" in tickerdicts["symbol"]
		and "STC" in tickerdicts["categoryName"]
		and "CLOSE ONLY" not in tickerdicts["description"]
		and "close only/" not in tickerdicts["description"]
		and "CFD" not in tickerdicts["description"]
	]
	ticker_list_local = sorted(ticker_list_local)
	xtb_connect.logout()
	print("XTB login and logout. Got all tickers for US market")
	return ticker_list_local

def trim_me(value_to_trim):
	"""Function to trim the value of argument received.

	Args:
		value_to_trim: Value passed to function to be trimmed at 2 points.

	Return:
		float: variable striped at 2 points
	"""
	if not isinstance(value_to_trim, str):
		value_to_trim = str(value_to_trim)

	value_index = value_to_trim.find(".") + 3
	strip_value = value_to_trim[:value_index]
	return float(strip_value)

def get_price(ticker):
	"""Retrieve the current price for the given ticker.
	
	Args:
		ticker (str): The ticker symbol.
		
	Returns:
		float or None: Latest price, or None if unavailable.
"""
	try:
		stock_data = yf.Ticker(ticker)
		history_data = stock_data.history(period="1d", interval="1m")
		if not history_data.empty:
			return trim_me(float(history_data.Close.iloc[0])) # Return the latest close price
		print(f"No price data available for {ticker}")
		no_data_ticker_list.append(ticker)
		return None
	except Exception as e: # pylint: disable=broad-except
		print(colored(f"Failed to get price data for {ticker}: {e}", "red"))
		return None

def get_dividend(ticker):
	"""Retrieve dividend data for the given ticker.
	
	Args:
		ticker (str): The ticker symbol.
	
	Returns:
		float or None: Latest dividend amount, or None is unavailable.
"""
	try:
		stock_data = yf.Ticker(ticker)
		dividend_data = stock_data.actions.Dividends
		if dividend_data is not None and not dividend_data.empty:
			return trim_me(float(dividend_data.iloc[-1])) # Return the latest dividend
		return None
	except Exception as e: # pylint: disable=broad-except
		print(colored(f"Failed to get dividend data for {ticker}: {e}", "red"))
		return None

def authorize_spreadsheet():
	"""Authorize Google Sheets access and retrieve the portfolio worksheet and tickers.

	Return:
		tuple: A tuple containing:
			sheet: The Google Sheets worksheet for the portfolio
			spreadsheet_tickers (list): A list of tickers already present in the spreadsheet
	"""
	try:
		scopes = [
			'https://www.googleapis.com/auth/spreadsheets',
			'https://www.googleapis.com/auth/drive'
		]

		credentials = Credentials.from_service_account_file("pybotnasq_tok.json", scopes=scopes)
		client = gspread.authorize(credentials)
		sheet = client.open('portfolio').worksheet('portfolio')
		return sheet
	except Exception as e: # pylint: disable=broad-except
		print(colored(f"Failed to establish connection to Google Sheets: {e}", "red"))
		return None

def get_tickers_from_sheet(sheet):
	"""Retrieve tickers from the specified Google Sheets worksheet.

	Args:
		sheet: The Google Sheets worksheet.

	Returns:
		list: A list of tickers already present in the spreadsheet
"""
	try:
		if sheet is not None:
			spreadsheet_tickers = sheet.col_values(2)[2:] # Skip header row
			return spreadsheet_tickers

		print(colored("Sheet object is None. Cannot retrieve tickers.", "red"))
		return []
	except Exception as e: #pylint: disable=broad-except
		print(colored(f"Failed to retrieve tickers from spreadsheet: {e}", "red"))
		return []

def update_spreadsheet(ticker, current_price, dividend_price, state):
	"""Update the spreadsheet with the current price and dividend for a given ticker.

	Args:
		ticker (list): List of tickers already present in the spreadsheet.
		ticker_data (dict): A dictionary containing 'ticker', 'current_price' and 'dividend_price'.
		first_time_update (bool): Indicates if this is the first time updating the dividends.
	"""
	sheet = authorize_spreadsheet()
	if sheet is not None:
		try:
			colvals = sheet.col_values(2)
			if ticker in colvals:
				count = colvals.index(ticker) + 1
				price_cell = f"F{count}"
				sheet.update_acell(price_cell, current_price)
				print(f"Price {current_price} updated for {ticker} in spreadsheet")
				if state["first_time_run"] == 1 or dividend_price is not None:
					div_cell = f"G{count}"
					sheet.update_acell(div_cell, dividend_price)
					print(f"Dividend {dividend_price} updated for {ticker} in spreadsheet")
		except Exception as e: # pylint: disable=broad-except
			print(colored(f"Failed to update price in spreadsheet for {ticker}: {e}", "red"))

def generate_telegram_message(ticker, signal_type, portfolio_type):
	"""Function to generate the telegram message

	Args:
		ticker: current ticker to send to telegram
		signal_type: string of signal type to send to telegram (buy/sell)
		portfolio_type: string of portfolio type to send to telegram (portfolio/wishlist)

	Return:
		string: message that is output to console
	"""
	if portfolio_type == "portfolio":
		signal_type_color = "green" if signal_type == "buy" else "yellow"
	elif portfolio_type == "wishlist":
		signal_type_color = "blue"
	else:
		signal_type_color = "white"
	return colored(f"{signal_type.upper()} signal for {ticker} ({portfolio_type})", signal_type_color)

def reload_config_if_changed(state):
	"""Reloads the config file only if it has been modified."""
	
	# Get the last modified time of config.ini
	current_mtime = os.path.getmtime(CONFIG_PATH)
	if state["last_config_mtime"] is None or current_mtime > state["last_config_mtime"]:
		print("Config file changed. Reloading config file ...")
		config.read(CONFIG_PATH)
		state["last_config_mtime"] = current_mtime

def return_portfolio_tickers(state):
	"""Function to return portfolio tickers from config file

	Return:
		string: string containing all the tickers in the portfolio section
	"""
	reload_config_if_changed(state)
	return config.get('finance', 'portfolio').split(" ")

def return_wishlist_tickers(state):
	"""Function to return wishlist tickers from config file

	Return:
		string: string containing all the tickers in the wishlist section
	"""
	reload_config_if_changed(state)
	return config.get('finance', 'wishlist').split(" ")

def get_technical_indicators(ticker):
	"""Fetch technical indicators (RSI, BB.upper, BB.lower) for the ticker"""

	try:
		stock_data = TA_Handler(
			symbol=ticker,
			exchange="NYSE",
			screener="america",
			interval=Interval.INTERVAL_1_DAY
		)
		return {
			"rsi": trim_me(float(stock_data.get_analysis().indicators["RSI"])),
			"bbu": trim_me(float(stock_data.get_analysis().indicators["BB.upper"])),
			"bbl": trim_me(float(stock_data.get_analysis().indicators["BB.lower"])),
		}
	except Exception: # pylint: disable=broad-except
		try:
			stock_data = TA_Handler(
				symbol=ticker,
				exchange="NASDAQ",
				screener="america",
				interval=Interval.INTERVAL_1_DAY
			)
			return {
				"rsi": trim_me(float(stock_data.get_analysis().indicators["RSI"])),
				"bbu": trim_me(float(stock_data.get_analysis().indicators["BB.upper"])),
				"bbl": trim_me(float(stock_data.get_analysis().indicators["BB.lower"])),
			}
		except Exception as e: # pylint: disable=broad-except
			print(colored(f"Couldn't get stock data for {ticker}: {e}", "yellow"))
			return None

def process_buy_signal(ticker, buy_list, portfolio, wishlist):
	"""Handles buy signal logic and appends to buy_list."""

	message = None

	if ticker in portfolio:
		message = generate_telegram_message(ticker, "buy", "portfolio")
	elif ticker in wishlist:
		message = generate_telegram_message(ticker, "buy", "wishlist")

	if message: # Only send if message is assigned
		message = message[5:][:-4] # Trim message
		telegram_send.send(messages=[message], parse_mode="html")

	buy_list.append(ticker)

def process_sell_signal(ticker, sell_list, portfolio):
	"""Handles sell signal logic and appends to sell_list."""

	if ticker in portfolio:
		message = generate_telegram_message(ticker, "sell", "portfolio")
		message = message[5:][:-4]
		telegram_send.send(messages=[message], parse_mode="html")

	sell_list.append(ticker)

def process_ticker(ticker, process_existing_tickers, context, state):
	"""Processes a stock ticker by analyzing price, indicators and updating records.

	Args:
		ticker: The stock ticker symbol.
		process_existing_tickers: List of tickers found in the spreadsheet.
		context (dict): Dictionary containing:
			portfolio: A list of tickers in the portfolio section.
			wishlist: A list of tickers in the wishlist section
			sell_list: List of tickers marked for SELL
			buy_list: List of tickers marked for BUY
	"""

	# Get stock price and dividend if any
	current_price = get_price(ticker)
	dividend_price = (
		get_dividend(ticker)
		if state["first_time_run"] == 1 and current_price is not None
		else None
	)

	if current_price is None:
		return # Skip if price is not available

	# Get technical indicators
	indicators = get_technical_indicators(ticker)
	if indicators is None:
		return # Skip if indicators could not be fetched

	ticker_rsi = indicators["rsi"]
	ticker_bbu = indicators["bbu"]
	ticker_bbl = indicators["bbl"]

	if ticker_rsi is not None and ticker_bbl is not None and ticker_bbu is not None:
		if ticker_rsi >= 70 and current_price >= ticker_bbu:
			process_sell_signal(ticker, context["sell_list"], context["portfolio"])

		if ticker_rsi <= 30 and current_price <= ticker_bbl:
			process_buy_signal(ticker, context["buy_list"], context["portfolio"], context["wishlist"])

		if ticker in process_existing_tickers:
			update_spreadsheet(ticker, current_price, dividend_price, state)

def check_market_status(time_of_trade):
	"""Check if the market is open, closed, or waiting to open."""

	if time_of_trade < 163000:
		print("Market is not opened yet, sleep until 16:30")
		target_time = datetime.time(16, 30, 1)
		time_slept = sleep_until_target_time(target_time)
		print(f"Slept for {time_slept} seconds until {target_time}")
		return False
	if time_of_trade > 230000:
		print("Market is closed, sleep until midnight")
		target_time = datetime.time(0, 0, 1)
		time_slept = sleep_until_target_time(target_time)
		print(f"Slept for {time_slept} seconds until {target_time}")
		return False
	return True # Market is open

def handle_ticker_processing(existing_tickers, portfolio, wishlist, process_ticker_list, state):
	"""Handles multiprocessing for processing tickers"""

	context = {
		"portfolio": portfolio,
		"wishlist": wishlist,
		"sell_list": current_sell_list,
		"buy_list": current_buy_list
	}

	#Use functools.partial to create a partial function with existing_tickers argument
	partial_process_ticker = functools.partial(
		process_ticker,
		process_existing_tickers=existing_tickers,
		context=context,
		state=state
	)

	#Use multiprocessing to process each ticker concurrently
	with multiprocessing.Pool() as pool:
		pool.map(partial_process_ticker, process_ticker_list)

def function_to_run(state):
	"""Main function that executes the code or keeps it idle

	Args:
		first_time_run: Indicates if this is the first time running the code.
		state_lists: A dictionary containing:
			previous_sell_list: list of tickers marked SELL on the previous iteration
			previous_buy_list: list of tickers marked BUY on the previous iteration
			diff_sell_list: List of tickers to be updated as SELL
			diff_buy_list: List of tickers to be updated as BUY
			ticker_list: the list of the tickers
	"""
	#global first_time_run, previous_sell_list, previous_buy_list, ticker_list

	time_of_trade = int(time.strftime("%H%M%S"))
	start_time = time.time()

	#Determine if it's the first time running
	state["first_time_run"] = 1 if 163000 <= time_of_trade <= 163500 else 0

	#Check market status
	if not check_market_status(time_of_trade):
		return #Exit early if market is closed

	#Market is open - proceed with processing
	sheet = authorize_spreadsheet()
	existing_tickers = get_tickers_from_sheet(sheet)
	portfolio = return_portfolio_tickers(state)
	wishlist = return_wishlist_tickers(state)

	if state["first_time_run"] == 1 or state["ticker_list"] is None:
		state["ticker_list"] = get_tickers()

	handle_ticker_processing(existing_tickers, portfolio, wishlist, state["ticker_list"], state)

	if state["first_time_run"] == 1:
		# Send initial Telegram message
		send_initial_telegram_message()
	else:
		# Check for updates and send Telegram messages
		send_telegram_updates(state)

		# Update previous lists
		state["previous_sell_list"] = list(current_sell_list)
		state["previous_buy_list"] = list(current_buy_list)
		current_sell_list[:] = []
		current_buy_list[:] = []

	#Cleanup tickers with no data
	print(f"no_data_ticker_list: {no_data_ticker_list}")
	state["ticker_list"][:] = [
		ticker for ticker in state["ticker_list"]
		if ticker not in set(no_data_ticker_list)
	]
	no_data_ticker_list[:] = []
	print(f"no_data_ticker_list: {no_data_ticker_list}")

	end_time = time.time()
	elapsed_time = end_time - start_time
	print(f"All tickers were processed in {elapsed_time} seconds")

def sleep_until_target_time(target_time):
	"""Function that forces code to 'sleep' so that CPU will get idle when market is not open

	Args:
		target_time: time on which the code starts running

	Return:
		int: returns the time until the code will 'sleep'
	"""
	current_datetime = datetime.datetime.now()
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
	"""Function that sends the initial message on the telegram channel

	Args:
		context: A dictionary containing transient data for the current run:
			current_sell_list: list of tickers marked SELL on the current iteration
			current_buy_list: list of tickers marked BUY on the current iteration
	"""

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

def send_telegram_updates(state):
	"""Function to send additional updates on telegram channel

	Args:
		current_sell_list: list of tickers marked SELL on the current iteration
		current_buy_list: list of tickers marked BUY on the current iteration
		previous_sell_list: list of tickers marked SELL on the previous iteration
		previous_buy_list: list of tickers marked BUY on the previous iteration
		diff_sell_list: list of tickers marked SELL between latest two iterations
		diff_buy_list: list of tickers marked BUY between latest two iteration
	"""
	portfolio = return_portfolio_tickers(state)
	wishlist = return_wishlist_tickers(state)
	message_for_telegram = ""

	# Calculate the differences between the processed tickers
	diff_sell_list = sorted(list(set(current_sell_list) - set(state["previous_sell_list"])))
	diff_buy_list = sorted(list(set(current_buy_list) - set(state["previous_buy_list"])))

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

def run_function_except_on_dates(excluded_dates, state):
	"""Function to make code not run on various dates when market is closed

	Args:
		excluded_dates: a list of dates on which the code will now run
	"""
	while True:
		current_date = datetime.datetime.now().date()
		# Check if the current date is in the excluded_dates list
		if current_date not in excluded_dates and current_date.weekday() not in (5, 6):
			function_to_run(state)
		else:
			print("Market closed because of bank holyday or weekend. Sleep until next day")
			target_time = datetime.time(0, 0, 1)
			time_slept = sleep_until_target_time(target_time)
			print(f"Slept for {time_slept} seconds until {target_time}")

def main():
	"""Main entry point of the script"""

	# Initialize state dictionary
	state = {
		"first_time_run": 0,
		"previous_sell_list": [],
		"previous_buy_list": [],
		"ticker_list": None,
		"last_config_mtime": None
	}

	run_function_except_on_dates(excluded_dates_list, state)

# Ensure the script runs only when executed directly
if __name__ == "__main__":
	main()
